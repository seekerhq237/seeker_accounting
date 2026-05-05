from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.contracts_projects.models.contract_progress_claim import ContractProgressClaim

_BILLING_STATUSES = ("certified", "invoiced")


class ContractProgressClaimRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, claim_id: int) -> ContractProgressClaim | None:
        return self._session.get(ContractProgressClaim, claim_id)

    def get_by_company_and_id(self, company_id: int, claim_id: int) -> ContractProgressClaim | None:
        statement = (
            select(ContractProgressClaim)
            .where(
                ContractProgressClaim.company_id == company_id,
                ContractProgressClaim.id == claim_id,
            )
            .options(selectinload(ContractProgressClaim.lines))
        )
        return self._session.scalar(statement)

    def get_by_claim_number(self, company_id: int, claim_number: str) -> ContractProgressClaim | None:
        return self._session.scalar(
            select(ContractProgressClaim).where(
                ContractProgressClaim.company_id == company_id,
                ContractProgressClaim.claim_number == claim_number,
            )
        )

    def list_by_contract(self, company_id: int, contract_id: int) -> list[ContractProgressClaim]:
        statement = (
            select(ContractProgressClaim)
            .where(
                ContractProgressClaim.company_id == company_id,
                ContractProgressClaim.contract_id == contract_id,
            )
            .options(selectinload(ContractProgressClaim.lines))
            .order_by(ContractProgressClaim.claim_date.asc(), ContractProgressClaim.id.asc())
        )
        return list(self._session.scalars(statement))

    def sum_certified_amount(self, company_id: int, contract_id: int, *, exclude_claim_id: int | None = None) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractProgressClaim.current_claim_amount), 0)).where(
            ContractProgressClaim.company_id == company_id,
            ContractProgressClaim.contract_id == contract_id,
            ContractProgressClaim.status_code.in_(_BILLING_STATUSES),
        )
        if exclude_claim_id is not None:
            statement = statement.where(ContractProgressClaim.id != exclude_claim_id)
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def sum_billed_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractProgressClaim.current_claim_amount), 0)).where(
            ContractProgressClaim.company_id == company_id,
            ContractProgressClaim.contract_id == contract_id,
            ContractProgressClaim.sales_invoice_id.is_not(None),
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def sum_earned_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractProgressClaim.earned_amount), 0)).where(
            ContractProgressClaim.company_id == company_id,
            ContractProgressClaim.contract_id == contract_id,
            ContractProgressClaim.status_code.in_(_BILLING_STATUSES),
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def sum_advance_recovery_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractProgressClaim.advance_recovery_amount), 0)).where(
            ContractProgressClaim.company_id == company_id,
            ContractProgressClaim.contract_id == contract_id,
            ContractProgressClaim.status_code.in_(_BILLING_STATUSES),
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def sum_retention_withheld_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractProgressClaim.retention_amount), 0)).where(
            ContractProgressClaim.company_id == company_id,
            ContractProgressClaim.contract_id == contract_id,
            ContractProgressClaim.status_code.in_(_BILLING_STATUSES),
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def add(self, claim: ContractProgressClaim) -> ContractProgressClaim:
        self._session.add(claim)
        return claim

    def save(self, claim: ContractProgressClaim) -> ContractProgressClaim:
        self._session.add(claim)
        return claim
