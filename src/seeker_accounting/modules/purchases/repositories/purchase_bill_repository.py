from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
from seeker_accounting.modules.purchases.models.supplier_payment_allocation import SupplierPaymentAllocation


class PurchaseBillRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
    ) -> list[PurchaseBill]:
        statement = select(PurchaseBill).where(PurchaseBill.company_id == company_id)
        if status_code is not None:
            statement = statement.where(PurchaseBill.status_code == status_code)
        if payment_status_code is not None:
            statement = statement.where(PurchaseBill.payment_status_code == payment_status_code)
        statement = statement.options(selectinload(PurchaseBill.supplier))
        statement = statement.order_by(
            PurchaseBill.bill_date.desc(),
            PurchaseBill.bill_number.desc(),
            PurchaseBill.id.desc(),
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, bill_id: int) -> PurchaseBill | None:
        statement = select(PurchaseBill).where(
            PurchaseBill.company_id == company_id,
            PurchaseBill.id == bill_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, bill_id: int) -> PurchaseBill | None:
        statement = select(PurchaseBill).where(
            PurchaseBill.company_id == company_id,
            PurchaseBill.id == bill_id,
        )
        statement = statement.options(
            selectinload(PurchaseBill.supplier),
            selectinload(PurchaseBill.currency),
            selectinload(PurchaseBill.posted_journal_entry),
            selectinload(PurchaseBill.posted_by_user),
            selectinload(PurchaseBill.lines)
            .selectinload(PurchaseBillLine.tax_code),
            selectinload(PurchaseBill.lines)
            .selectinload(PurchaseBillLine.expense_account),
            selectinload(PurchaseBill.allocations).selectinload(SupplierPaymentAllocation.supplier_payment),
        )
        return self._session.scalar(statement)

    def get_by_number(self, company_id: int, bill_number: str) -> PurchaseBill | None:
        statement = select(PurchaseBill).where(
            PurchaseBill.company_id == company_id,
            PurchaseBill.bill_number == bill_number,
        )
        return self._session.scalar(statement)

    def add(self, bill: PurchaseBill) -> PurchaseBill:
        self._session.add(bill)
        return bill

    def save(self, bill: PurchaseBill) -> PurchaseBill:
        self._session.add(bill)
        return bill
