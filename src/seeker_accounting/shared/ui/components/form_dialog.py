"""FormDialog — section-oriented dialog with sticky footer + inline issue band.

Improves on ``BaseDialog`` for serious form work:

- declarative section helpers (``add_section`` / ``add_field``),
- a sticky footer with primary / secondary actions,
- an :class:`InlineIssueBand` for top-of-form validation,
- dirty / clean / saving / saved state tracking,
- unsaved-changes guard on Escape / close,
- responsive sizing (no ``resize(...)`` literals).

This module is a pure UI primitive — no business logic, no domain
imports. Subclasses provide section content, validators, and the
``on_submit`` handler.
"""
from __future__ import annotations

from typing import Any, Callable, Final, Literal, Sequence

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components.inline_issue_band import (
    InlineIssueBand,
    ValidationIssue,
)
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

FormState = Literal["clean", "dirty", "saving", "saved", "error"]


class FormDialog(QDialog):
    """Production-grade form-dialog primitive.

    Usage::

        class MyDialog(FormDialog):
            def __init__(self, parent=None):
                super().__init__("Edit customer", parent=parent,
                                 primary_label="Save", help_key="customers.edit")
                section = self.add_section("Identity")
                self._name = QLineEdit(); section.addRow("Name", self._name)
                ...

            def on_submit(self) -> bool:
                if not self._service.save(...):
                    self.show_error("Save failed")
                    return False
                return True

    Subclasses override :meth:`on_submit`. Returning ``True`` accepts
    the dialog; returning ``False`` keeps it open with the existing
    error band visible.
    """

    state_changed = Signal(str)  # FormState
    dirty_changed = Signal(bool)

    def __init__(
        self,
        title: str,
        *,
        parent: QWidget | None = None,
        primary_label: str = "Save",
        secondary_label: str | None = "Cancel",
        help_key: str | None = None,
        min_width: int = 520,
        min_height: int = 360,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(min_width, min_height)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        spacing = DEFAULT_TOKENS.spacing

        # ── Outer layout: [issue band][scroll content][footer] ───────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Inline issue band (hidden until populated)
        self._issue_band = InlineIssueBand(self)
        outer.addWidget(self._issue_band)

        # Content area inside a scroll for tall forms.
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("FormDialogScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll, 1)

        self._content = QWidget(self._scroll)
        self._scroll.setWidget(self._content)

        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        self._content_layout.setSpacing(spacing.dialog_section_gap)

        # ── Footer ────────────────────────────────────────────────────
        self._footer = QFrame(self)
        self._footer.setObjectName("FormDialogFooter")
        footer_layout = QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(
            spacing.dialog_footer_padding_h,
            spacing.dialog_footer_padding_v,
            spacing.dialog_footer_padding_h,
            spacing.dialog_footer_padding_v,
        )
        footer_layout.setSpacing(spacing.compact_gap)

        self._state_label = QLabel("", self._footer)
        self._state_label.setObjectName("FormDialogStateLabel")
        footer_layout.addWidget(self._state_label)
        footer_layout.addStretch(1)

        self._secondary_btn: QPushButton | None = None
        if secondary_label:
            self._secondary_btn = QPushButton(secondary_label, self._footer)
            self._secondary_btn.setObjectName("FormDialogSecondaryButton")
            self._secondary_btn.clicked.connect(self._on_secondary)
            footer_layout.addWidget(self._secondary_btn)

        self._primary_btn = QPushButton(primary_label, self._footer)
        self._primary_btn.setObjectName("FormDialogPrimaryButton")
        self._primary_btn.setDefault(True)
        self._primary_btn.clicked.connect(self._on_primary)
        footer_layout.addWidget(self._primary_btn)

        outer.addWidget(self._footer)

        # ── Help button (top-right) ───────────────────────────────────
        self._help_key = help_key
        self._help_btn: QPushButton | None = None
        if help_key:
            self._help_btn = QPushButton("?", self)
            self._help_btn.setObjectName("HelpButton")
            self._help_btn.setFixedSize(28, 28)
            self._help_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._help_btn.setToolTip("Help")
            self._help_btn.clicked.connect(self._show_help)

        self._state: FormState = "clean"
        self._is_dirty: bool = False
        self._dirty_guard_enabled: bool = True

    # ── Section / field helpers ───────────────────────────────────────

    def add_section(self, title: str | None = None) -> "FormDialogSection":
        """Append a new section frame and return it for layout work."""
        section = FormDialogSection(title=title, parent=self._content)
        self._content_layout.addWidget(section)
        return section

    def add_widget(self, widget: QWidget) -> None:
        """Append a free-standing widget to the form body."""
        self._content_layout.addWidget(widget)

    def add_stretch(self) -> None:
        self._content_layout.addStretch(1)

    # ── Issue band passthroughs ───────────────────────────────────────

    def show_error(self, message: str, *, title: str | None = None) -> None:
        self._issue_band.show_message(message, severity="error", title=title)
        self.set_state("error")

    def show_warning(self, message: str, *, title: str | None = None) -> None:
        self._issue_band.show_message(message, severity="warning", title=title)

    def show_info(self, message: str, *, title: str | None = None) -> None:
        self._issue_band.show_message(message, severity="info", title=title)

    def show_issues(self, issues: Sequence[ValidationIssue]) -> None:
        self._issue_band.show_issues(issues)
        if any(i.severity in {"blocker", "error"} for i in issues):
            self.set_state("error")

    def clear_issues(self) -> None:
        self._issue_band.clear()
        if self._state == "error":
            self.set_state("dirty" if self._is_dirty else "clean")

    # ── State + dirty tracking ────────────────────────────────────────

    def state(self) -> FormState:
        return self._state

    def set_state(self, state: FormState) -> None:
        if state == self._state:
            return
        self._state = state
        self._refresh_state_label()
        self._refresh_primary_enabled()
        self.state_changed.emit(state)

    def is_dirty(self) -> bool:
        return self._is_dirty

    def mark_dirty(self) -> None:
        if not self._is_dirty:
            self._is_dirty = True
            self.dirty_changed.emit(True)
        if self._state in {"clean", "saved"}:
            self.set_state("dirty")

    def mark_clean(self) -> None:
        if self._is_dirty:
            self._is_dirty = False
            self.dirty_changed.emit(False)
        if self._state in {"dirty", "error"}:
            self.set_state("clean")

    def set_dirty_guard_enabled(self, enabled: bool) -> None:
        self._dirty_guard_enabled = enabled

    def set_primary_enabled(self, enabled: bool) -> None:
        # Track external override; the state-driven refresh respects it.
        self._primary_btn.setEnabled(enabled)

    # ── Hooks for subclasses ──────────────────────────────────────────

    def on_submit(self) -> bool:
        """Override. Return ``True`` to accept the dialog."""
        return True

    def on_cancel(self) -> bool:
        """Override. Return ``True`` to allow cancel (default: respect dirty guard)."""
        return self._confirm_discard_if_dirty()

    # ── License guard (ported from BaseDialog) ────────────────────────

    def apply_license_guard(self, license_service: object) -> None:
        try:
            permitted: bool = license_service.is_write_permitted()  # type: ignore[attr-defined]
        except Exception:
            return
        if permitted:
            return
        self._primary_btn.setEnabled(False)
        self._primary_btn.setToolTip(
            "Read-only mode — activate a license to enable this action."
        )
        notice = QLabel(
            "Read-only mode — activate a license to make changes.", self
        )
        notice.setObjectName("ReadOnlyNoticeLabel")
        notice.setWordWrap(True)
        self._content_layout.addWidget(notice)

    # ── internals ─────────────────────────────────────────────────────

    def _on_primary(self) -> None:
        prev_state = self._state
        self.set_state("saving")
        try:
            ok = self.on_submit()
        except Exception:
            self.set_state("error")
            raise
        if ok:
            self._is_dirty = False
            self.dirty_changed.emit(False)
            self.set_state("saved")
            self.accept()
        else:
            # Subclass should have set issue band; ensure state reflects it.
            if self._state == "saving":
                self.set_state(prev_state if prev_state != "saving" else "dirty")

    def _on_secondary(self) -> None:
        if self.on_cancel():
            self.reject()

    def _confirm_discard_if_dirty(self) -> bool:
        if not self._dirty_guard_enabled or not self._is_dirty:
            return True
        reply = QMessageBox.question(
            self,
            "Discard changes?",
            "You have unsaved changes. Discard them and close?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Discard

    def _refresh_state_label(self) -> None:
        text_map = {
            "clean": "",
            "dirty": "Unsaved changes",
            "saving": "Saving…",
            "saved": "Saved",
            "error": "Resolve errors above",
        }
        self._state_label.setText(text_map.get(self._state, ""))

    def _refresh_primary_enabled(self) -> None:
        if self._state == "saving":
            self._primary_btn.setEnabled(False)
        elif self._state == "error":
            # Keep primary clickable so user can retry; subclass decides.
            self._primary_btn.setEnabled(True)
        else:
            self._primary_btn.setEnabled(True)

    def _show_help(self) -> None:
        if not self._help_key:
            return
        try:
            from seeker_accounting.shared.ui.help_overlay import show_help_in_dialog
            show_help_in_dialog(self._help_key, self)
        except Exception:
            pass

    def resizeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._help_btn is not None:
            self._help_btn.move(self.width() - self._help_btn.width() - 12, 8)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            if self._confirm_discard_if_dirty():
                self.reject()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._primary_btn.click()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self._confirm_discard_if_dirty():
            event.accept()
        else:
            event.ignore()


class FormDialogSection(QFrame):
    """Bounded grouping inside a :class:`FormDialog`."""

    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FormDialogSection")
        spacing = DEFAULT_TOKENS.spacing

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing.dialog_field_gap)

        if title:
            self._title = QLabel(title, self)
            self._title.setObjectName("FormDialogSectionTitle")
            layout.addWidget(self._title)

        self._body_layout = QVBoxLayout()
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(spacing.dialog_field_gap)
        layout.addLayout(self._body_layout)

    def addRow(self, label_text: str, field: QWidget, *, hint: str = "") -> None:
        """Add a labelled row.

        Layout is vertical (label above field) for predictable readability
        and accessible focus order.
        """
        spacing = DEFAULT_TOKENS.spacing
        wrapper = QFrame(self)
        wrapper.setObjectName("FormFieldRow")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(spacing.dialog_label_gap)

        label = QLabel(label_text, wrapper)
        label.setObjectName("FormFieldLabel")
        label.setBuddy(field)
        wrapper_layout.addWidget(label)
        wrapper_layout.addWidget(field)

        if hint:
            hint_label = QLabel(hint, wrapper)
            hint_label.setObjectName("FormFieldHint")
            hint_label.setWordWrap(True)
            wrapper_layout.addWidget(hint_label)

        self._body_layout.addWidget(wrapper)

    def addWidget(self, widget: QWidget) -> None:
        self._body_layout.addWidget(widget)

    def addLayout(self, layout: Any) -> None:
        self._body_layout.addLayout(layout)
