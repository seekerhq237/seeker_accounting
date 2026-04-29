"""Step 4 — Default document sequences."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.wizards.company_setup import state_keys as K
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


# (document_type_code, default_prefix, default_padding)
_DEFAULTS: tuple[tuple[str, str, int], ...] = (
    ("sales_invoice", "INV-", 5),
    ("customer_receipt", "REC-", 5),
    ("purchase_bill", "BILL-", 5),
    ("supplier_payment", "PAY-", 5),
    ("journal_entry", "JE-", 5),
)


class DocumentSequencesStep(WizardStep):
    key = "document_sequences"
    title = "Document Numbers"
    subtitle = "Pick the default numbering sequences to seed for this company."

    def __init__(self) -> None:
        super().__init__()
        self._checkboxes: dict[str, QCheckBox] = {}

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        intro = QLabel(
            "Selected sequences will be created with sensible defaults. "
            "You can edit prefixes, padding, and reset frequency later in "
            "Reference Data \u203a Numbering.",
            root,
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #4E5866; font-size: 11px;")
        layout.addWidget(intro)

        for code, prefix, padding in _DEFAULTS:
            cb = QCheckBox(
                f"{self._format_label(code)}  ·  prefix \u201c{prefix}\u201d  ·  {padding} digits",
                root,
            )
            cb.setChecked(True)
            self._checkboxes[code] = cb
            layout.addWidget(cb)

        layout.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        selected = state.get(K.KEY_DOC_SEQ_TYPES_TO_CREATE)
        if isinstance(selected, list):
            for code, cb in self._checkboxes.items():
                cb.setChecked(code in selected)

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_DOC_SEQ_TYPES_TO_CREATE] = [
            code for code, cb in self._checkboxes.items() if cb.isChecked()
        ]

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_DOC_SEQ_CREATED) is not None:
            return
        company_id = context.require_company_id()
        service = context.service_registry.numbering_setup_service
        wanted = set(state.get(K.KEY_DOC_SEQ_TYPES_TO_CREATE, []))
        existing = {seq.document_type_code for seq in service.list_document_sequences(company_id)}
        created = 0
        for code, prefix, padding in _DEFAULTS:
            if code not in wanted or code in existing:
                continue
            try:
                service.create_document_sequence(
                    company_id,
                    CreateDocumentSequenceCommand(
                        document_type_code=code,
                        next_number=1,
                        padding_width=padding,
                        prefix=prefix,
                        reset_frequency_code=None,
                    ),
                )
            except (ValidationError, ConflictError):
                # Duplicate or invalid input — skip silently to keep the
                # wizard's best-effort seed behaviour.
                continue
            created += 1
        state[K.KEY_DOC_SEQ_CREATED] = created

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        chosen = state.get(K.KEY_DOC_SEQ_TYPES_TO_CREATE) or []
        if not chosen:
            return "No document sequences will be created."
        return f"Create default document sequences: {', '.join(self._format_label(c) for c in chosen)}."

    @staticmethod
    def _format_label(code: str) -> str:
        return code.replace("_", " ").title()
