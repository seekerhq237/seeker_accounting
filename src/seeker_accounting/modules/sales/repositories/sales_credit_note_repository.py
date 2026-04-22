from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from seeker_accounting.modules.sales.models.sales_credit_note import SalesCreditNote
from seeker_accounting.modules.sales.dto.sales_credit_note_dto import (
    SalesCreditNoteDetailDTO,
    SalesCreditNoteLineDTO,
    SalesCreditNoteListItemDTO,
)


class SalesCreditNoteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        *,
        status_code: str | None = None,
        customer_id: int | None = None,
    ) -> list[SalesCreditNoteListItemDTO]:
        stmt = (
            select(SalesCreditNote)
            .where(SalesCreditNote.company_id == company_id)
            .options(
                joinedload(SalesCreditNote.customer),
                joinedload(SalesCreditNote.source_invoice),
            )
            .order_by(SalesCreditNote.credit_date.desc(), SalesCreditNote.id.desc())
        )
        if status_code:
            stmt = stmt.where(SalesCreditNote.status_code == status_code)
        if customer_id:
            stmt = stmt.where(SalesCreditNote.customer_id == customer_id)

        rows = self._session.execute(stmt).unique().scalars().all()
        return [self._to_list_dto(r) for r in rows]

    def get_by_id(self, company_id: int, credit_note_id: int) -> SalesCreditNote | None:
        return self._session.execute(
            select(SalesCreditNote)
            .where(
                SalesCreditNote.company_id == company_id,
                SalesCreditNote.id == credit_note_id,
            )
        ).scalar_one_or_none()

    def get_detail(self, company_id: int, credit_note_id: int) -> SalesCreditNote | None:
        return self._session.execute(
            select(SalesCreditNote)
            .where(
                SalesCreditNote.company_id == company_id,
                SalesCreditNote.id == credit_note_id,
            )
            .options(
                joinedload(SalesCreditNote.customer),
                joinedload(SalesCreditNote.currency),
                joinedload(SalesCreditNote.source_invoice),
                joinedload(SalesCreditNote.lines),
            )
        ).unique().scalar_one_or_none()

    def get_by_number(self, company_id: int, credit_number: str) -> SalesCreditNote | None:
        return self._session.execute(
            select(SalesCreditNote)
            .where(
                SalesCreditNote.company_id == company_id,
                SalesCreditNote.credit_number == credit_number,
            )
        ).scalar_one_or_none()

    def add(self, credit_note: SalesCreditNote) -> None:
        self._session.add(credit_note)
        self._session.flush()

    def save(self, credit_note: SalesCreditNote) -> None:
        self._session.flush()

    # --- DTO mapping ---

    @staticmethod
    def _to_list_dto(r: SalesCreditNote) -> SalesCreditNoteListItemDTO:
        return SalesCreditNoteListItemDTO(
            id=r.id,
            credit_number=r.credit_number,
            customer_id=r.customer_id,
            customer_name=r.customer.display_name if r.customer else "",
            credit_date=r.credit_date,
            currency_code=r.currency_code,
            status_code=r.status_code,
            total_amount=r.total_amount,
            source_invoice_id=r.source_invoice_id,
            source_invoice_number=r.source_invoice.invoice_number if r.source_invoice else None,
        )

    @staticmethod
    def _to_detail_dto(r: SalesCreditNote) -> SalesCreditNoteDetailDTO:
        from seeker_accounting.modules.sales.repositories.sales_credit_note_line_repository import (
            SalesCreditNoteLineRepository,
        )

        line_dtos = [SalesCreditNoteLineRepository._to_line_dto(ln) for ln in r.lines]
        return SalesCreditNoteDetailDTO(
            id=r.id,
            company_id=r.company_id,
            credit_number=r.credit_number,
            customer_id=r.customer_id,
            customer_name=r.customer.display_name if r.customer else "",
            credit_date=r.credit_date,
            currency_code=r.currency_code,
            exchange_rate=r.exchange_rate,
            status_code=r.status_code,
            reason_text=r.reason_text,
            reference_number=r.reference_number,
            subtotal_amount=r.subtotal_amount,
            tax_amount=r.tax_amount,
            total_amount=r.total_amount,
            source_invoice_id=r.source_invoice_id,
            source_invoice_number=r.source_invoice.invoice_number if r.source_invoice else None,
            posted_journal_entry_id=r.posted_journal_entry_id,
            posted_at=r.posted_at,
            posted_by_user_id=r.posted_by_user_id,
            contract_id=r.contract_id,
            project_id=r.project_id,
            lines=line_dtos,
        )
