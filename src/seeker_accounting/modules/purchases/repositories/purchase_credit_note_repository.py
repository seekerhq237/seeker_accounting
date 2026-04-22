from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from seeker_accounting.modules.purchases.models.purchase_credit_note import PurchaseCreditNote
from seeker_accounting.modules.purchases.dto.purchase_credit_note_dto import (
    PurchaseCreditNoteDetailDTO,
    PurchaseCreditNoteLineDTO,
    PurchaseCreditNoteListItemDTO,
)


class PurchaseCreditNoteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        *,
        status_code: str | None = None,
        supplier_id: int | None = None,
    ) -> list[PurchaseCreditNoteListItemDTO]:
        stmt = (
            select(PurchaseCreditNote)
            .where(PurchaseCreditNote.company_id == company_id)
            .options(
                joinedload(PurchaseCreditNote.supplier),
                joinedload(PurchaseCreditNote.source_bill),
            )
            .order_by(PurchaseCreditNote.credit_date.desc(), PurchaseCreditNote.id.desc())
        )
        if status_code:
            stmt = stmt.where(PurchaseCreditNote.status_code == status_code)
        if supplier_id:
            stmt = stmt.where(PurchaseCreditNote.supplier_id == supplier_id)

        rows = self._session.execute(stmt).unique().scalars().all()
        return [self._to_list_dto(r) for r in rows]

    def get_by_id(self, company_id: int, credit_note_id: int) -> PurchaseCreditNote | None:
        return self._session.execute(
            select(PurchaseCreditNote)
            .where(
                PurchaseCreditNote.company_id == company_id,
                PurchaseCreditNote.id == credit_note_id,
            )
        ).scalar_one_or_none()

    def get_detail(self, company_id: int, credit_note_id: int) -> PurchaseCreditNote | None:
        return self._session.execute(
            select(PurchaseCreditNote)
            .where(
                PurchaseCreditNote.company_id == company_id,
                PurchaseCreditNote.id == credit_note_id,
            )
            .options(
                joinedload(PurchaseCreditNote.supplier),
                joinedload(PurchaseCreditNote.currency),
                joinedload(PurchaseCreditNote.source_bill),
                joinedload(PurchaseCreditNote.lines),
            )
        ).unique().scalar_one_or_none()

    def get_by_number(self, company_id: int, credit_number: str) -> PurchaseCreditNote | None:
        return self._session.execute(
            select(PurchaseCreditNote)
            .where(
                PurchaseCreditNote.company_id == company_id,
                PurchaseCreditNote.credit_number == credit_number,
            )
        ).scalar_one_or_none()

    def add(self, credit_note: PurchaseCreditNote) -> None:
        self._session.add(credit_note)
        self._session.flush()

    def save(self, credit_note: PurchaseCreditNote) -> None:
        self._session.flush()

    @staticmethod
    def _to_list_dto(r: PurchaseCreditNote) -> PurchaseCreditNoteListItemDTO:
        return PurchaseCreditNoteListItemDTO(
            id=r.id,
            credit_number=r.credit_number,
            supplier_id=r.supplier_id,
            supplier_name=r.supplier.display_name if r.supplier else "",
            supplier_credit_reference=r.supplier_credit_reference,
            credit_date=r.credit_date,
            currency_code=r.currency_code,
            status_code=r.status_code,
            total_amount=r.total_amount,
            source_bill_id=r.source_bill_id,
            source_bill_number=r.source_bill.bill_number if r.source_bill else None,
        )

    @staticmethod
    def _to_detail_dto(r: PurchaseCreditNote) -> PurchaseCreditNoteDetailDTO:
        from seeker_accounting.modules.purchases.repositories.purchase_credit_note_line_repository import (
            PurchaseCreditNoteLineRepository,
        )

        line_dtos = [PurchaseCreditNoteLineRepository._to_line_dto(ln) for ln in r.lines]
        return PurchaseCreditNoteDetailDTO(
            id=r.id,
            company_id=r.company_id,
            credit_number=r.credit_number,
            supplier_id=r.supplier_id,
            supplier_name=r.supplier.display_name if r.supplier else "",
            supplier_credit_reference=r.supplier_credit_reference,
            credit_date=r.credit_date,
            currency_code=r.currency_code,
            exchange_rate=r.exchange_rate,
            status_code=r.status_code,
            reason_text=r.reason_text,
            subtotal_amount=r.subtotal_amount,
            tax_amount=r.tax_amount,
            total_amount=r.total_amount,
            source_bill_id=r.source_bill_id,
            source_bill_number=r.source_bill.bill_number if r.source_bill else None,
            posted_journal_entry_id=r.posted_journal_entry_id,
            posted_at=r.posted_at,
            posted_by_user_id=r.posted_by_user_id,
            contract_id=r.contract_id,
            project_id=r.project_id,
            lines=line_dtos,
        )
