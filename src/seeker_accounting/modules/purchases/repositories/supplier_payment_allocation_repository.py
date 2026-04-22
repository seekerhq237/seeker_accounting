from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.purchases.models.supplier_payment import SupplierPayment
from seeker_accounting.modules.purchases.models.supplier_payment_allocation import SupplierPaymentAllocation
from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill


class SupplierPaymentAllocationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_payment(self, company_id: int, payment_id: int) -> list[SupplierPaymentAllocation]:
        statement = (
            select(SupplierPaymentAllocation)
            .join(SupplierPayment, SupplierPayment.id == SupplierPaymentAllocation.supplier_payment_id)
            .where(
                SupplierPaymentAllocation.company_id == company_id,
                SupplierPaymentAllocation.supplier_payment_id == payment_id,
            )
            .options(selectinload(SupplierPaymentAllocation.purchase_bill))
            .order_by(SupplierPaymentAllocation.id.asc())
        )
        return list(self._session.scalars(statement))

    def list_for_bill(self, company_id: int, bill_id: int) -> list[SupplierPaymentAllocation]:
        statement = (
            select(SupplierPaymentAllocation)
            .join(PurchaseBill, PurchaseBill.id == SupplierPaymentAllocation.purchase_bill_id)
            .where(
                SupplierPaymentAllocation.company_id == company_id,
                SupplierPaymentAllocation.purchase_bill_id == bill_id,
            )
            .options(
                selectinload(SupplierPaymentAllocation.supplier_payment)
                .selectinload(SupplierPayment.financial_account),
                selectinload(SupplierPaymentAllocation.purchase_bill),
            )
            .order_by(SupplierPaymentAllocation.allocation_date.asc(), SupplierPaymentAllocation.id.asc())
        )
        return list(self._session.scalars(statement))

    def get_total_allocated_for_payment(self, company_id: int, payment_id: int) -> Decimal:
        statement = (
            select(func.coalesce(func.sum(SupplierPaymentAllocation.allocated_amount), 0))
            .where(
                SupplierPaymentAllocation.company_id == company_id,
                SupplierPaymentAllocation.supplier_payment_id == payment_id,
            )
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def get_allocated_totals_for_bill_ids(
        self,
        company_id: int,
        bill_ids: list[int] | tuple[int, ...],
        posted_only: bool = True,
    ) -> dict[int, Decimal]:
        if not bill_ids:
            return {}

        statement = (
            select(
                SupplierPaymentAllocation.purchase_bill_id,
                func.coalesce(func.sum(SupplierPaymentAllocation.allocated_amount), 0),
            )
            .join(SupplierPayment, SupplierPayment.id == SupplierPaymentAllocation.supplier_payment_id)
            .where(
                SupplierPaymentAllocation.company_id == company_id,
                SupplierPaymentAllocation.purchase_bill_id.in_(bill_ids),
            )
            .group_by(SupplierPaymentAllocation.purchase_bill_id)
        )
        if posted_only:
            statement = statement.where(SupplierPayment.status_code == "posted")

        results: dict[int, Decimal] = {}
        for bill_id, amount in self._session.execute(statement):
            results[int(bill_id)] = Decimal(str(amount or 0)).quantize(Decimal("0.00"))
        return results

    def replace_allocations_for_payment(
        self,
        company_id: int,
        payment_id: int,
        allocations: list[SupplierPaymentAllocation],
    ) -> list[SupplierPaymentAllocation]:
        for existing_allocation in self.list_for_payment(company_id, payment_id):
            self._session.delete(existing_allocation)
        self._session.flush()
        for allocation in allocations:
            allocation.supplier_payment_id = payment_id
            self._session.add(allocation)
        return allocations

    def add(self, allocation: SupplierPaymentAllocation) -> SupplierPaymentAllocation:
        self._session.add(allocation)
        return allocation

    def save(self, allocation: SupplierPaymentAllocation) -> SupplierPaymentAllocation:
        self._session.add(allocation)
        return allocation
