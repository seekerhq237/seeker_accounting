"""Dialog shown on login when the previous session was not cleanly closed."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.administration.dto.user_session_dto import (
    ABNORMAL_EXPLANATION_CHOICES,
    EXPLANATION_OTHER,
    UserSessionDTO,
)


class AbnormalShutdownDialog(QDialog):
    """Mandatory prompt when login detects an unclosed previous session.

    The user must select a reason before proceeding. The dialog cannot be
    dismissed without making a choice.
    """

    def __init__(
        self,
        sessions: list[UserSessionDTO],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Session Not Properly Closed")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.resize(540, 420)
        # Remove close button from title bar
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        self._selected_code: str | None = None
        self._note: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel(
            "Your previous session was not properly closed.\n"
            "Please indicate what happened so we can keep accurate records."
        )
        header.setWordWrap(True)
        header.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(header)

        # Session info (show most recent)
        if sessions:
            s = sessions[0]
            info_text = (
                f"<b>Last login:</b> {s.login_at.strftime('%Y-%m-%d %H:%M')}"
                f"&nbsp;&nbsp;|&nbsp;&nbsp;<b>Host:</b> {s.hostname or 'unknown'}"
            )
            info = QLabel(info_text)
            info.setTextFormat(Qt.TextFormat.RichText)
            info.setStyleSheet("color: #666; font-size: 12px;")
            layout.addWidget(info)

        # Radio options
        self._button_group = QButtonGroup(self)
        self._radio_map: dict[int, str] = {}
        for idx, (code, label) in enumerate(ABNORMAL_EXPLANATION_CHOICES):
            rb = QRadioButton(label, self)
            self._button_group.addButton(rb, idx)
            self._radio_map[idx] = code
            layout.addWidget(rb)

        # Free-text field for "Other"
        self._note_edit = QPlainTextEdit(self)
        self._note_edit.setPlaceholderText("Please describe what happened...")
        self._note_edit.setMaximumHeight(80)
        self._note_edit.setVisible(False)
        layout.addWidget(self._note_edit)

        self._button_group.idToggled.connect(self._on_option_changed)

        # Buttons
        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        self._ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Submit")
        self._ok_btn.setEnabled(False)
        self._button_box.accepted.connect(self._on_submit)
        layout.addWidget(self._button_box)

    # ── Slots ──────────────────────────────────────────────────────────

    def _on_option_changed(self, button_id: int, checked: bool) -> None:
        if not checked:
            return
        code = self._radio_map.get(button_id, "")
        self._note_edit.setVisible(code == EXPLANATION_OTHER)
        self._ok_btn.setEnabled(True)

    def _on_submit(self) -> None:
        checked_id = self._button_group.checkedId()
        if checked_id < 0:
            return
        self._selected_code = self._radio_map[checked_id]
        self._note = (
            self._note_edit.toPlainText().strip()[:500]
            if self._selected_code == EXPLANATION_OTHER
            else None
        )
        self.accept()

    def reject(self) -> None:
        """Prevent dismissal without a selection — do nothing."""
        pass

    # ── Result helpers ─────────────────────────────────────────────────

    @property
    def explanation_code(self) -> str | None:
        return self._selected_code

    @property
    def explanation_note(self) -> str | None:
        return self._note

    # ── Convenience class method ───────────────────────────────────────

    @classmethod
    def prompt(
        cls,
        sessions: list[UserSessionDTO],
        parent: QWidget | None = None,
    ) -> tuple[str, str | None] | None:
        """Show the dialog and return ``(code, note)`` or ``None`` if skipped (shouldn't happen)."""
        dlg = cls(sessions, parent)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted and dlg.explanation_code:
            return dlg.explanation_code, dlg.explanation_note
        return None
