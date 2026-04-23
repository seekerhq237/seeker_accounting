from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
from seeker_accounting.modules.purchases.models.supplier_payment_allocation import SupplierPaymentAllocation
from seeker_accounting.modules.suppliers.models.supplier import Supplier


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

    # ------------------------------------------------------------------
    # Paginated + searchable listing (server-side)
    # ------------------------------------------------------------------

    def _build_filter_conditions(
        self,
        company_id: int,
        status_code: str | None,
        payment_status_code: str | None,
        query: str | None,
    ) -> list:
        conditions: list = [PurchaseBill.company_id == company_id]
        if status_code is not None:
            conditions.append(PurchaseBill.status_code == status_code)
        if payment_status_code is not None:
            conditions.append(PurchaseBill.payment_status_code == payment_status_code)
        if query:
            like = f"%{query.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(PurchaseBill.bill_number).like(like),
                    func.lower(PurchaseBill.supplier_bill_reference).like(like),
                    func.lower(Supplier.display_name).like(like),
                    func.lower(Supplier.supplier_code).like(like),
                )
            )
        return conditions

    def count_filtered(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
        query: str | None = None,
    ) -> int:
        stmt = (
            select(func.count(PurchaseBill.id))
            .join(Supplier, Supplier.id == PurchaseBill.supplier_id)
            .where(*self._build_filter_conditions(company_id, status_code, payment_status_code, query))
        )
        return int(self._session.scalar(stmt) or 0)

    def list_filtered_page(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PurchaseBill]:
        stmt = (
            select(PurchaseBill)
            .join(Supplier, Supplier.id == PurchaseBill.supplier_id)
            .where(*self._build_filter_conditions(company_id, status_code, payment_status_code, query))
            .options(selectinload(PurchaseBill.supplier))
            .order_by(
                PurchaseBill.bill_date.desc(),
                PurchaseBill.bill_number.desc(),
                PurchaseBill.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt))

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
