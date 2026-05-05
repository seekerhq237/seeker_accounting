"""PayrollApproverConfigRepository — P7 approval routing data access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.payroll.models.payroll_approver_config import (
    PayrollApproverConfig,
)


class PayrollApproverConfigRepository:
    """Read and persist :class:`PayrollApproverConfig` records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Queries ───────────────────────────────────────────────────────────

    def list_active_by_company(self, company_id: int) -> list[PayrollApproverConfig]:
        """Return all active routing rules for a company, ordered by id."""
        stmt = (
            select(PayrollApproverConfig)
            .where(
                PayrollApproverConfig.company_id == company_id,
                PayrollApproverConfig.is_active.is_(True),
            )
            .order_by(PayrollApproverConfig.id)
        )
        return list(self._session.scalars(stmt))

    def list_by_company(self, company_id: int) -> list[PayrollApproverConfig]:
        """Return all routing rules (active and inactive) for a company."""
        stmt = (
            select(PayrollApproverConfig)
            .where(PayrollApproverConfig.company_id == company_id)
            .order_by(PayrollApproverConfig.id)
        )
        return list(self._session.scalars(stmt))

    def get_by_id(
        self, company_id: int, config_id: int
    ) -> PayrollApproverConfig | None:
        """Load a single config by id, scoped to the company."""
        return self._session.get(PayrollApproverConfig, config_id) if (
            rec := self._session.get(PayrollApproverConfig, config_id)
        ) and rec.company_id == company_id else None

    # ── Mutations ─────────────────────────────────────────────────────────

    def save(self, config: PayrollApproverConfig) -> None:
        """Persist (add or update) a config record in the current session."""
        self._session.add(config)

    def delete(self, config: PayrollApproverConfig) -> None:
        """Delete a config record from the current session."""
        self._session.delete(config)
