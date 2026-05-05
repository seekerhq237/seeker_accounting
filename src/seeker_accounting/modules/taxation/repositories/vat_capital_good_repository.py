"""Repository for the VAT Capital-Goods Register."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.vat_capital_good import VatCapitalGood


class VatCapitalGoodRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, asset: VatCapitalGood) -> None:
        self._session.add(asset)

    def get(self, asset_id: int, company_id: int) -> VatCapitalGood | None:
        return self._session.execute(
            select(VatCapitalGood).where(
                VatCapitalGood.id == asset_id,
                VatCapitalGood.company_id == company_id,
            )
        ).scalar_one_or_none()

    def list_active(self, company_id: int) -> list[VatCapitalGood]:
        rows = self._session.execute(
            select(VatCapitalGood)
            .where(
                VatCapitalGood.company_id == company_id,
                VatCapitalGood.status_code == "ACTIVE",
            )
            .order_by(VatCapitalGood.acquisition_date)
        ).scalars().all()
        return list(rows)

    def list_all(self, company_id: int) -> list[VatCapitalGood]:
        rows = self._session.execute(
            select(VatCapitalGood)
            .where(VatCapitalGood.company_id == company_id)
            .order_by(VatCapitalGood.acquisition_date)
        ).scalars().all()
        return list(rows)
