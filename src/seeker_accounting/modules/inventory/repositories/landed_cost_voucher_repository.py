"""Repository for LandedCostVoucher (P5 / Slice 6.2)."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.landed_cost_voucher import (
    LandedCostVoucher,
    LandedCostVoucherReceipt,
)


class LandedCostVoucherRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, voucher_id: int) -> LandedCostVoucher | None:
        return self._session.get(LandedCostVoucher, voucher_id)

    def get_by_number(self, company_id: int, voucher_number: str) -> LandedCostVoucher | None:
        stmt = select(LandedCostVoucher).where(
            LandedCostVoucher.company_id == company_id,
            LandedCostVoucher.voucher_number == voucher_number,
        )
        return self._session.scalars(stmt).first()

    def list_by_company(
        self, company_id: int, status_code: str | None = None
    ) -> Sequence[LandedCostVoucher]:
        stmt = select(LandedCostVoucher).where(
            LandedCostVoucher.company_id == company_id
        )
        if status_code:
            stmt = stmt.where(LandedCostVoucher.status_code == status_code)
        stmt = stmt.order_by(LandedCostVoucher.voucher_date.desc())
        return self._session.scalars(stmt).all()

    def add(self, voucher: LandedCostVoucher) -> None:
        self._session.add(voucher)

    def list_receipts(self, voucher_id: int) -> Sequence[LandedCostVoucherReceipt]:
        stmt = select(LandedCostVoucherReceipt).where(
            LandedCostVoucherReceipt.voucher_id == voucher_id
        )
        return self._session.scalars(stmt).all()

    def add_receipt(self, receipt: LandedCostVoucherReceipt) -> None:
        self._session.add(receipt)

    def delete_receipt(self, receipt: LandedCostVoucherReceipt) -> None:
        self._session.delete(receipt)
