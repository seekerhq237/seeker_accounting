"""Step 2 — Preview: shows counts before the export is written to disk."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.audit.dto.audit_export_dto import AuditExportPreviewDTO
from seeker_accounting.modules.wizards.audit_export import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class PreviewStep(WizardStep):
    key = "preview"
    title = "Preview export"
    subtitle = "Confirm the volume and contents before writing the package."

    def __init__(self) -> None:
        super().__init__()
        self._summary_label: QLabel | None = None
        self._counts_form: QFormLayout | None = None
        self._je_value: QLabel | None = None
        self._line_value: QLabel | None = None
        self._event_value: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        self._summary_label = QLabel(root)
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._summary_label)

        self._counts_form = QFormLayout()
        self._counts_form.setContentsMargins(0, 0, 0, 0)
        self._je_value = QLabel("—", root)
        self._line_value = QLabel("—", root)
        self._event_value = QLabel("—", root)
        self._counts_form.addRow("Posted journal entries", self._je_value)
        self._counts_form.addRow("Posted journal lines", self._line_value)
        self._counts_form.addRow("Audit events", self._event_value)
        outer.addLayout(self._counts_form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        from_d = state.get(K.KEY_FROM_DATE)
        to_d = state.get(K.KEY_TO_DATE)
        include_events = bool(state.get(K.KEY_INCLUDE_AUDIT_EVENTS, True))
        if not isinstance(from_d, date) or not isinstance(to_d, date):
            return
        preview = context.service_registry.audit_export_service.preview(
            company_id, from_d, to_d, include_audit_events=include_events
        )
        state[K.KEY_PREVIEW] = preview
        self._render(preview, state.get(K.KEY_OUTPUT_DIR))

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def _render(self, preview: AuditExportPreviewDTO, output_dir: object) -> None:
        if self._summary_label is not None:
            scope = "AR/AP control accounts and audit events" if preview.include_audit_events \
                else "posted journal entries only"
            out_dir_text = output_dir if isinstance(output_dir, str) else "(not set)"
            self._summary_label.setText(
                f"<b>Date range:</b> {preview.from_date.isoformat()} to "
                f"{preview.to_date.isoformat()}<br>"
                f"<b>Scope:</b> {scope}<br>"
                f"<b>Output folder:</b> {out_dir_text}"
            )
        if self._je_value is not None:
            self._je_value.setText(f"{preview.posted_journal_entry_count:,}")
        if self._line_value is not None:
            self._line_value.setText(f"{preview.posted_journal_line_count:,}")
        if self._event_value is not None:
            if preview.include_audit_events:
                self._event_value.setText(f"{preview.audit_event_count:,}")
            else:
                self._event_value.setText("(excluded)")
