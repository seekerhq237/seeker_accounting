"""Step 4 — Confirm & post the stock count adjustment."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CreateInventoryDocumentCommand,
    InventoryDocumentLineCommand,
)
from seeker_accounting.modules.wizards.stock_count import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Create the inventory adjustment document and post it."

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
        self._result.setWordWrap(True)
        self._result.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        variance_lines = self._collect_variance_lines(state)
        if self._summary is not None:
            self._summary.setText(
                f"<b>Count date:</b> {state.get(K.KEY_COUNT_DATE)}<br>"
                f"<b>Variance lines:</b> {len(variance_lines)}<br>"
                f"<b>Reference:</b> {state.get(K.KEY_REFERENCE) or '(auto)'}<br><br>"
                "Clicking Finish creates a draft adjustment document and posts it."
            )
        if self._result is not None and state.get(K.KEY_POSTED):
            self._result.setText(
                f"<b>Adjustment posted.</b><br>"
                f"Document: {state.get(K.KEY_RESULT_DOCUMENT_NUMBER)}<br>"
                f"Variance lines posted: {state.get(K.KEY_RESULT_VARIANCE_LINES)}"
            )

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_POSTED):
            return
        company_id = context.require_company_id()
        variance_lines = self._collect_variance_lines(state)
        if not variance_lines:
            return
        line_cmds = [
            InventoryDocumentLineCommand(
                item_id=ln["item_id"],
                quantity=ln["variance"],
                unit_cost=ln["avg_cost"] if ln["variance"] > 0 else None,
                counterparty_account_id=int(state[K.KEY_ADJUSTMENT_ACCOUNT_ID]),
                line_description=f"Stock count variance: {ln['item_code']}",
            )
            for ln in variance_lines
        ]
        command = CreateInventoryDocumentCommand(
            document_type_code="adjustment",
            document_date=state[K.KEY_COUNT_DATE],
            location_id=state.get(K.KEY_LOCATION_ID),
            reference_number=state.get(K.KEY_REFERENCE),
            notes=state.get(K.KEY_NOTES),
            lines=tuple(line_cmds),
        )
        doc = context.service_registry.inventory_document_service.create_draft_document(
            company_id, command
        )
        result = context.service_registry.inventory_posting_service.post_inventory_document(
            company_id, doc.id, actor_user_id=context.user_id
        )
        state[K.KEY_RESULT_DOCUMENT_ID] = int(doc.id)
        state[K.KEY_RESULT_DOCUMENT_NUMBER] = getattr(result, "document_number", None) or doc.document_number
        state[K.KEY_RESULT_VARIANCE_LINES] = len(variance_lines)
        state[K.KEY_RESULT_JOURNAL_ENTRY_ID] = getattr(result, "journal_entry_id", None)
        state[K.KEY_POSTED] = True

    def _collect_variance_lines(self, state: WizardState) -> list[dict]:
        rows = state.get(K.KEY_COUNTS) or ()
        variance_lines: list[dict] = []
        for entry in rows:
            text = (entry.get("counted_qty") or "").strip()
            if not text:
                continue
            try:
                counted = Decimal(text)
                system = Decimal(str(entry.get("system_qty") or "0"))
            except Exception:
                continue
            variance = counted - system
            if variance == 0:
                continue
            variance_lines.append(
                {
                    "item_id": int(entry["item_id"]),
                    "item_code": entry.get("item_code") or "",
                    "variance": variance,
                    "avg_cost": Decimal(str(entry.get("avg_cost") or "0")),
                }
            )
        return variance_lines
