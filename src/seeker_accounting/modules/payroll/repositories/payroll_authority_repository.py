"""Repositories for the Phase 5 payroll authority registry & component map."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.payroll_authority import PayrollAuthority
from seeker_accounting.modules.payroll.models.payroll_component_authority_map import (
    PayrollComponentAuthorityMap,
)


class PayrollAuthorityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self, company_id: int, *, active_only: bool = False,
    ) -> list[PayrollAuthority]:
        stmt = (
            select(PayrollAuthority)
            .where(PayrollAuthority.company_id == company_id)
            .options(selectinload(PayrollAuthority.gl_liability_account))
            .order_by(PayrollAuthority.code)
        )
        if active_only:
            stmt = stmt.where(PayrollAuthority.is_active == True)  # noqa: E712
        return list(self._session.scalars(stmt).all())

    def get_by_id(
        self, company_id: int, authority_id: int,
    ) -> PayrollAuthority | None:
        stmt = (
            select(PayrollAuthority)
            .where(PayrollAuthority.id == authority_id)
            .where(PayrollAuthority.company_id == company_id)
            .options(selectinload(PayrollAuthority.gl_liability_account))
        )
        return self._session.scalar(stmt)

    def get_by_code(
        self, company_id: int, code: str,
    ) -> PayrollAuthority | None:
        stmt = (
            select(PayrollAuthority)
            .where(PayrollAuthority.company_id == company_id)
            .where(PayrollAuthority.code == code)
        )
        return self._session.scalar(stmt)

    def save(self, authority: PayrollAuthority) -> PayrollAuthority:
        self._session.add(authority)
        return authority


class PayrollComponentAuthorityMapRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        *,
        component_id: int | None = None,
        authority_id: int | None = None,
    ) -> list[PayrollComponentAuthorityMap]:
        stmt = (
            select(PayrollComponentAuthorityMap)
            .where(PayrollComponentAuthorityMap.company_id == company_id)
            .options(
                selectinload(PayrollComponentAuthorityMap.component),
                selectinload(PayrollComponentAuthorityMap.authority),
            )
            .order_by(
                PayrollComponentAuthorityMap.authority_id,
                PayrollComponentAuthorityMap.component_id,
            )
        )
        if component_id is not None:
            stmt = stmt.where(PayrollComponentAuthorityMap.component_id == component_id)
        if authority_id is not None:
            stmt = stmt.where(PayrollComponentAuthorityMap.authority_id == authority_id)
        return list(self._session.scalars(stmt).all())

    def list_for_authority(
        self, company_id: int, authority_id: int,
    ) -> list[PayrollComponentAuthorityMap]:
        return self.list_by_company(company_id, authority_id=authority_id)

    def get_by_id(
        self, company_id: int, mapping_id: int,
    ) -> PayrollComponentAuthorityMap | None:
        stmt = (
            select(PayrollComponentAuthorityMap)
            .where(PayrollComponentAuthorityMap.id == mapping_id)
            .where(PayrollComponentAuthorityMap.company_id == company_id)
            .options(
                selectinload(PayrollComponentAuthorityMap.component),
                selectinload(PayrollComponentAuthorityMap.authority),
            )
        )
        return self._session.scalar(stmt)

    def find(
        self,
        company_id: int,
        *,
        component_id: int,
        authority_id: int,
        side: str,
    ) -> PayrollComponentAuthorityMap | None:
        stmt = (
            select(PayrollComponentAuthorityMap)
            .where(PayrollComponentAuthorityMap.company_id == company_id)
            .where(PayrollComponentAuthorityMap.component_id == component_id)
            .where(PayrollComponentAuthorityMap.authority_id == authority_id)
            .where(PayrollComponentAuthorityMap.side == side)
        )
        return self._session.scalar(stmt)

    def save(self, mapping: PayrollComponentAuthorityMap) -> PayrollComponentAuthorityMap:
        self._session.add(mapping)
        return mapping

    def delete(self, mapping: PayrollComponentAuthorityMap) -> None:
        self._session.delete(mapping)
