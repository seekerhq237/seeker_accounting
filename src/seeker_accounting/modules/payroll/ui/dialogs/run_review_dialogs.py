"""Submit-for-review and approve dialogs (Phase 3 / P3.S7).

These dialogs replace the bare yes/no QMessageBox prompts on the
cockpit's primary actions with a small form that captures an optional
note. The note is forwarded to the service layer where it is recorded
in the audit log alongside the state transition / event.
"""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit, QWidget

from seeker_accounting.shared.ui.components.form_dialog import FormDialog


class _NoteCaptureDialog(FormDialog):
    """Shared base for review-style dialogs."""

    def __init__(
        self,
        title: str,
        *,
        primary_label: str,
        prompt: str,
        body_hint: str = "",
        require_note: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title,
            parent=parent,
            primary_label=primary_label,
            secondary_label="Cancel",
            min_width=480,
            min_height=300,
        )
        section = self.add_section(prompt)
        self._note_edit = QPlainTextEdit()
        self._note_edit.setPlaceholderText(
            body_hint or ("Required note…" if require_note else "Optional note…")
        )
        self._note_edit.setFixedHeight(120)
        section.addRow("Note", self._note_edit)
        self._require_note = require_note
        self._note_value: str | None = None

    def on_submit(self) -> bool:
        text = self._note_edit.toPlainText().strip()
        if self._require_note and not text:
            self.show_error("A note is required for this action.")
            return False
        self._note_value = text or None
        return True

    @property
    def note(self) -> str | None:
        return self._note_value


class SubmitForReviewDialog(_NoteCaptureDialog):
    """Capture a preparer note when submitting a run for approval."""

    def __init__(self, run_reference: str, parent: QWidget | None = None) -> None:
        super().__init__(
            "Submit for review",
            primary_label="Submit",
            prompt=f"Submit run {run_reference} for review",
            body_hint=(
                "Optional note for the approver — context, "
                "anomalies, special circumstances."
            ),
            parent=parent,
        )


class ApproveRunDialog(_NoteCaptureDialog):
    """Capture an optional approver note when approving a run."""

    def __init__(self, run_reference: str, parent: QWidget | None = None) -> None:
        super().__init__(
            "Approve payroll run",
            primary_label="Approve",
            prompt=f"Approve run {run_reference}",
            body_hint=(
                "Optional note recorded with the approval audit event."
            ),
            parent=parent,
        )
