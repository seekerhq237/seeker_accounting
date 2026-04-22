from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from seeker_accounting.modules.purchases.models.purchase_credit_note import PurchaseCreditNote
from seeker_accounting.modules.purchases.models.purchase_credit_note_line import PurchaseCreditNoteLine
from seeker_accounting.modules.purchases.dto.purchase_credit_note_dto import PurchaseCreditNoteLineDTO


class PurchaseCreditNoteLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_credit_note(
        self,
        company_id: int,
        credit_note_id: int,
    ) -> list[PurchaseCreditNoteLine]:
        stmt = (
            select(PurchaseCreditNoteLine)
            .join(PurchaseCreditNote, PurchaseCreditNoteLine.purchase_credit_note_id == PurchaseCreditNote.id)
            .where(
                PurchaseCreditNote.company_id == company_id,
                PurchaseCreditNoteLine.purchase_credit_note_id == credit_note_id,
            )
            .options(
                joinedload(PurchaseCreditNoteLine.tax_code),
                joinedload(PurchaseCreditNoteLine.expense_account),
            )
            .order_by(PurchaseCreditNoteLine.line_number)
        )
        return list(self._session.execute(stmt).unique().scalars().all())

    def replace_lines(
        self,
        company_id: int,
        credit_note_id: int,
        lines: list[PurchaseCreditNoteLine],
    ) -> None:
        existing_stmt = (
            select(PurchaseCreditNoteLine)
            .join(PurchaseCreditNote, PurchaseCreditNoteLine.purchase_credit_note_id == PurchaseCreditNote.id)
            .where(
                PurchaseCreditNote.company_id == company_id,
                PurchaseCreditNoteLine.purchase_credit_note_id == credit_note_id,
            )
        )
        for line in self._session.execute(existing_stmt).scalars().all():
            self._session.delete(line)
        self._session.flush()
        for line in lines:
            self._session.add(line)
        self._session.flush()

    def add(self, line: PurchaseCreditNoteLine) -> None:
        self._session.add(line)
        self._session.flush()

    def save(self, line: PurchaseCreditNoteLine) -> None:
        self._session.flush()

    @staticmethod
    def _to_line_dto(ln: PurchaseCreditNoteLine) -> PurchaseCreditNoteLineDTO:
        return PurchaseCreditNoteLineDTO(
            id=ln.id,
            line_number=ln.line_number,
            description=ln.description,
            quantity=ln.quantity,
            unit_cost=ln.unit_cost,
            expense_account_id=ln.expense_account_id,
            expense_account_name=ln.expense_account.account_name if ln.expense_account else None,
            tax_code_id=ln.tax_code_id,
            tax_code_name=ln.tax_code.code if ln.tax_code else None,
            line_subtotal_amount=ln.line_subtotal_amount,
            line_tax_amount=ln.line_tax_amount,
            line_total_amount=ln.line_total_amount,
            contract_id=ln.contract_id,
            project_id=ln.project_id,
            project_job_id=ln.project_job_id,
            project_cost_code_id=ln.project_cost_code_id,
        )
