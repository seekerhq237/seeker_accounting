from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent


class PayrollComponentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        active_only: bool = False,
        component_type_code: str | None = None,
    ) -> list[PayrollComponent]:
        stmt = (
            select(PayrollComponent)
            .where(PayrollComponent.company_id == company_id)
            .options(
                selectinload(PayrollComponent.expense_account),
                selectinload(PayrollComponent.liability_account),
            )
            .order_by(PayrollComponent.component_code)
        )
        if active_only:
            stmt = stmt.where(PayrollComponent.is_active == True)  # noqa: E712
        if component_type_code is not None:
            stmt = stmt.where(PayrollComponent.component_type_code == component_type_code)
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, component_id: int) -> PayrollComponent | None:
        stmt = (
            select(PayrollComponent)
            .where(PayrollComponent.id == component_id)
            .where(PayrollComponent.company_id == company_id)
            .options(
                selectinload(PayrollComponent.expense_account),
                selectinload(PayrollComponent.liability_account),
            )
        )
        return self._session.scalar(stmt)

    def get_by_code(self, company_id: int, component_code: str) -> PayrollComponent | None:
        stmt = (
            select(PayrollComponent)
            .where(PayrollComponent.company_id == company_id)
            .where(PayrollComponent.component_code == component_code)
        )
        return self._session.scalar(stmt)

    def save(self, component: PayrollComponent) -> PayrollComponent:
        self._session.add(component)
        return component
