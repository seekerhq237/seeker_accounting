"""Step 3 — Confirm and commit (create or update sequence)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
    UpdateDocumentSequenceCommand,
)
from seeker_accounting.modules.wizards.document_numbering import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class CommitStep(WizardStep):
    key = "commit"
    title = "Commit"
    subtitle = "Save the sequence."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._result: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._summary)
        self._result = QLabel(root)
        self._result.setStyleSheet("color: #2a7;")
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            prefix = state.get(K.KEY_PREFIX) or ""
            suffix = state.get(K.KEY_SUFFIX) or ""
            nn = int(state.get(K.KEY_NEXT_NUMBER) or 1)
            pad = int(state.get(K.KEY_PADDING_WIDTH) or 4)
            html = (
                f"<b>Mode:</b> {state.get(K.KEY_MODE)}<br>"
                f"<b>Document type:</b> {state.get(K.KEY_DOCUMENT_TYPE_CODE)}<br>"
                f"<b>Format preview:</b> {prefix}{str(nn).zfill(pad)}{suffix}<br>"
                f"<b>Reset:</b> {state.get(K.KEY_RESET_FREQUENCY_CODE) or 'never'}"
            )
            self._summary.setText(html)
        if self._result is not None and state.get(K.KEY_PREVIEW_NUMBER):
            self._result.setText(f"Saved. Server preview: {state[K.KEY_PREVIEW_NUMBER]}")

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_PREVIEW_NUMBER):
            return
        company_id = context.require_company_id()
        svc = context.service_registry.numbering_setup_service
        if state.get(K.KEY_MODE) == "create":
            cmd = CreateDocumentSequenceCommand(
                document_type_code=str(state[K.KEY_DOCUMENT_TYPE_CODE]),
                next_number=int(state[K.KEY_NEXT_NUMBER]),
                padding_width=int(state[K.KEY_PADDING_WIDTH]),
                prefix=state.get(K.KEY_PREFIX),
                suffix=state.get(K.KEY_SUFFIX),
                reset_frequency_code=state.get(K.KEY_RESET_FREQUENCY_CODE),
            )
            seq = svc.create_document_sequence(company_id, cmd)
        else:
            sid = int(state[K.KEY_SEQUENCE_ID])
            cmd_u = UpdateDocumentSequenceCommand(
                document_type_code=str(state[K.KEY_DOCUMENT_TYPE_CODE]),
                next_number=int(state[K.KEY_NEXT_NUMBER]),
                padding_width=int(state[K.KEY_PADDING_WIDTH]),
                prefix=state.get(K.KEY_PREFIX),
                suffix=state.get(K.KEY_SUFFIX),
                reset_frequency_code=state.get(K.KEY_RESET_FREQUENCY_CODE),
            )
            seq = svc.update_document_sequence(company_id, sid, cmd_u)
        state[K.KEY_SEQUENCE_ID] = seq.id
        try:
            preview = svc.preview_document_number(company_id, seq.id)
            state[K.KEY_PREVIEW_NUMBER] = preview.preview_number
        except Exception:  # noqa: BLE001
            # Preview is informational; never fail the commit on preview error.
            state[K.KEY_PREVIEW_NUMBER] = None

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        sid = state.get(K.KEY_SEQUENCE_ID)
        if sid:
            return f"Sequence #{sid} \u2014 next: {state.get(K.KEY_PREVIEW_NUMBER) or '(saved)'}"
        return "Ready to save."
