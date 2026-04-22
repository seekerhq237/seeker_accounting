"""Dialog shown to admin users on login when there are unreviewed abnormal sessions."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.administration.dto.user_session_dto import (
    ABNORMAL_EXPLANATION_CHOICES,
    REQUIRES_ADMIN_ATTENTION_CODES,
    UserSessionDTO,
)

_EXPLANATION_LABELS: dict[str, str] = dict(ABNORMAL_EXPLANATION_CHOICES)

_ATTENTION_STYLE = "background-color: #FFF3CD; color: #856404; font-weight: 600; padding: 2px 6px;"
_NORMAL_STYLE = "padding: 2px 6px;"


class AdminAbnormalSessionDialog(QDialog):
    """One-time dialog shown on admin login listing unreviewed abnormal session reports.

    The admin can acknowledge individual entries or dismiss the dialog.
    """

    def __init__(
        self,
        sessions: list[UserSessionDTO],
        on_acknowledge: callable | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Abnormal Session Reports")
        self.setModal(True)
        self.setMinimumWidth(700)
        self.resize(760, 460)

        self._sessions = list(sessions)
        self._on_acknowledge = on_acknowledge

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel(
            "The following session(s) were not properly closed and have been reported by users.\n"
            "Items highlighted may require developer or system administrator attention."
        )
        header.setWordWrap(True)
        header.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(header)

        # Table
        self._table = QTableWidget(len(sessions), 6, self)
        self._table.setHorizontalHeaderLabels([
            "User", "Login Time", "Reason", "Note", "Host", "",
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        for row, s in enumerate(sessions):
            needs_attention = s.abnormal_explanation_code in REQUIRES_ADMIN_ATTENTION_CODES
            style = _ATTENTION_STYLE if needs_attention else _NORMAL_STYLE

            user_item = QTableWidgetItem(s.user_display_name)
            user_item.setData(Qt.ItemDataRole.ToolTipRole, f"User ID {s.user_id}")
            self._table.setItem(row, 0, user_item)

            time_item = QTableWidgetItem(s.login_at.strftime("%Y-%m-%d %H:%M"))
            self._table.setItem(row, 1, time_item)

            reason_label = _EXPLANATION_LABELS.get(
                s.abnormal_explanation_code or "", s.abnormal_explanation_code or "—"
            )
            reason_item = QTableWidgetItem(reason_label)
            self._table.setItem(row, 2, reason_item)

            note_item = QTableWidgetItem(s.abnormal_explanation_note or "")
            self._table.setItem(row, 3, note_item)

            host_item = QTableWidgetItem(s.hostname or "")
            self._table.setItem(row, 4, host_item)

            # Acknowledge button
            ack_btn = QPushButton("Acknowledge")
            ack_btn.setFixedWidth(100)
            ack_btn.clicked.connect(lambda checked, r=row, sid=s.id: self._acknowledge_row(r, sid))
            self._table.setCellWidget(row, 5, ack_btn)

            # Apply highlight
            if needs_attention:
                for col in range(5):
                    item = self._table.item(row, col)
                    if item:
                        item.setBackground(Qt.GlobalColor.yellow)

        layout.addWidget(self._table, 1)

        # Dismiss button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

    def _acknowledge_row(self, row: int, session_id: int) -> None:
        if self._on_acknowledge:
            self._on_acknowledge(session_id)
        # Visually mark as acknowledged
        for col in range(5):
            item = self._table.item(row, col)
            if item:
                item.setBackground(Qt.GlobalColor.lightGray)
                item.setForeground(Qt.GlobalColor.gray)
        btn = self._table.cellWidget(row, 5)
        if btn:
            btn.setEnabled(False)
            btn.setText("Done")

    @classmethod
    def prompt(
        cls,
        sessions: list[UserSessionDTO],
        on_acknowledge: callable | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Show the dialog. Returns after admin dismisses it."""
        if not sessions:
            return
        dlg = cls(sessions, on_acknowledge=on_acknowledge, parent=parent)
        dlg.exec()
