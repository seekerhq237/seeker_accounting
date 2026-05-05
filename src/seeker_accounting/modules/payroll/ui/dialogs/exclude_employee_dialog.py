"""Exclude-employee reason picker dialog (Phase 3 / P3.S6).

Replaces the bare ``QInputDialog.getText`` reason capture with a small
form dialog that picks a structured reason code and an optional /
mandatory note. The dialog returns the canonical stored string via
:func:`payroll_exclusion_reasons.format_reason`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from seeker_accounting.modules.payroll.services.payroll_exclusion_reasons import (
    REASON_CHOICES,
    ExclusionReasonChoice,
    ExclusionReasonCode,
    format_reason,
    parse_reason,
)
from seeker_accounting.shared.ui.components.form_dialog import FormDialog


class ExcludeEmployeeDialog(FormDialog):
    """Pick a reason + optional note for excluding an employee."""

    def __init__(
        self,
        employee_name: str,
        *,
        existing_reason: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            f"Exclude {employee_name}",
            parent=parent,
            primary_label="Exclude",
            secondary_label="Cancel",
            min_width=480,
            min_height=320,
        )

        section = self.add_section("Reason")

        self._reason_combo = QComboBox()
        for choice in REASON_CHOICES:
            self._reason_combo.addItem(choice.label, choice.code.value)
        self._reason_combo.currentIndexChanged.connect(self._on_reason_changed)
        section.addRow("Reason", self._reason_combo)

        self._note_edit = QPlainTextEdit()
        self._note_edit.setPlaceholderText("Optional note…")
        self._note_edit.setFixedHeight(96)
        section.addRow("Note", self._note_edit)

        self._hint_label = QLabel("")
        self._hint_label.setObjectName("ExcludeReasonHint")
        self._hint_label.setWordWrap(True)
        self._hint_label.setTextFormat(Qt.TextFormat.PlainText)
        section.addRow("", self._hint_label)

        # Pre-fill if editing an existing exclusion.
        if existing_reason:
            code, note = parse_reason(existing_reason)
            if code is not None:
                idx = self._reason_combo.findData(code)
                if idx >= 0:
                    self._reason_combo.setCurrentIndex(idx)
            if note:
                self._note_edit.setPlainText(note)

        self._on_reason_changed()
        self._result: str | None = None

    # ── helpers ───────────────────────────────────────────────────────

    def _current_choice(self) -> ExclusionReasonChoice:
        code_value = self._reason_combo.currentData()
        for choice in REASON_CHOICES:
            if choice.code.value == code_value:
                return choice
        return REASON_CHOICES[0]

    def _on_reason_changed(self) -> None:
        choice = self._current_choice()
        if choice.requires_note:
            self._note_edit.setPlaceholderText("Required: explain the reason…")
        else:
            self._note_edit.setPlaceholderText("Optional note…")
        self._hint_label.setText(choice.description)
        self._hint_label.setVisible(bool(choice.description))

    # ── FormDialog hook ───────────────────────────────────────────────

    def on_submit(self) -> bool:
        choice = self._current_choice()
        note = self._note_edit.toPlainText().strip()
        if choice.requires_note and not note:
            self.show_error("A note is required for this reason.")
            return False
        self._result = format_reason(choice.code, note)
        return True

    @property
    def stored_reason(self) -> str | None:
        return self._result
