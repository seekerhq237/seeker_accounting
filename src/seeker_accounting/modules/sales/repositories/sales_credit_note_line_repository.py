from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from seeker_accounting.modules.sales.models.sales_credit_note import SalesCreditNote
from seeker_accounting.modules.sales.models.sales_credit_note_line import SalesCreditNoteLine
from seeker_accounting.modules.sales.dto.sales_credit_note_dto import SalesCreditNoteLineDTO


class SalesCreditNoteLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_credit_note(
        self,
        company_id: int,
        credit_note_id: int,
    ) -> list[SalesCreditNoteLine]:
        stmt = (
            select(SalesCreditNoteLine)
            .join(SalesCreditNote, SalesCreditNoteLine.sales_credit_note_id == SalesCreditNote.id)
            .where(
                SalesCreditNote.company_id == company_id,
                SalesCreditNoteLine.sales_credit_note_id == credit_note_id,
            )
            .options(
                joinedload(SalesCreditNoteLine.tax_code),
                joinedload(SalesCreditNoteLine.revenue_account),
            )
            .order_by(SalesCreditNoteLine.line_number)
        )
        return list(self._session.execute(stmt).unique().scalars().all())

    def replace_lines(
        self,
        company_id: int,
        credit_note_id: int,
        lines: list[SalesCreditNoteLine],
    ) -> None:
        existing_stmt = (
            select(SalesCreditNoteLine)
            .join(SalesCreditNote, SalesCreditNoteLine.sales_credit_note_id == SalesCreditNote.id)
            .where(
                SalesCreditNote.company_id == company_id,
                SalesCreditNoteLine.sales_credit_note_id == credit_note_id,
            )
        )
        for line in self._session.execute(existing_stmt).scalars().all():
            self._session.delete(line)
        self._session.flush()
        for line in lines:
            self._session.add(line)
        self._session.flush()

    def add(self, line: SalesCreditNoteLine) -> None:
        self._session.add(line)
        self._session.flush()

    def save(self, line: SalesCreditNoteLine) -> None:
        self._session.flush()

    @staticmethod
    def _to_line_dto(ln: SalesCreditNoteLine) -> SalesCreditNoteLineDTO:
        return SalesCreditNoteLineDTO(
            id=ln.id,
            line_number=ln.line_number,
            description=ln.description,
            quantity=ln.quantity,
            unit_price=ln.unit_price,
            discount_percent=ln.discount_percent,
            discount_amount=ln.discount_amount,
            tax_code_id=ln.tax_code_id,
            tax_code_name=ln.tax_code.code if ln.tax_code else None,
            revenue_account_id=ln.revenue_account_id,
            revenue_account_name=ln.revenue_account.account_name if ln.revenue_account else "",
            line_subtotal_amount=ln.line_subtotal_amount,
            line_tax_amount=ln.line_tax_amount,
            line_total_amount=ln.line_total_amount,
            contract_id=ln.contract_id,
            project_id=ln.project_id,
            project_job_id=ln.project_job_id,
            project_cost_code_id=ln.project_cost_code_id,
        )
