"""PayrollApprovalRoutingService — P7 approval routing management.

Manages the per-company table of approval routing rules
(:class:`PayrollApproverConfig`).  The routing logic selects the first
active config whose min_run_amount threshold is met (or None) when
determining who must approve a given run total.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.payroll.dto.payroll_approval_routing_dto import (
    ApprovalRoutingResultDTO,
    ApproverConfigDTO,
    SetApproverConfigCommand,
)
from seeker_accounting.modules.payroll.models.payroll_approver_config import PayrollApproverConfig
from seeker_accounting.modules.payroll.payroll_permissions import (
    PAYROLL_APPROVER_CONFIG_MANAGE,
    PAYROLL_SETUP_MANAGE,
)
from seeker_accounting.modules.payroll.repositories.payroll_approver_config_repository import (
    PayrollApproverConfigRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError


class PayrollApprovalRoutingService:
    """Manage per-company approval routing rules for payroll runs."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        config_repository_factory: Callable[[Session], PayrollApproverConfigRepository],
        permission_service: PermissionService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._config_repo_factory = config_repository_factory
        self._permission_service = permission_service

    # ── Queries ───────────────────────────────────────────────────────────

    def list_approver_configs(self, company_id: int) -> list[ApproverConfigDTO]:
        """Return all active approval routing rules for *company_id*."""
        with self._uow_factory() as uow:
            repo = self._config_repo_factory(uow.session)
            configs = repo.list_active_by_company(company_id)
            return [self._to_dto(c) for c in configs]

    def get_required_approver(
        self,
        company_id: int,
        run_total_net_payable: Decimal,
    ) -> ApprovalRoutingResultDTO:
        """Return the required approver for a run of the given total.

        Selection logic:
          1. Find all active configs for the company.
          2. Filter to configs where ``min_run_amount`` is None or ≤ total.
          3. Sort by ``min_run_amount`` descending (most-specific threshold wins).
          4. Return the first match, or ``ApprovalRoutingResultDTO`` with
             ``required_approver_user_id=None`` if no rule applies.
        """
        with self._uow_factory() as uow:
            repo = self._config_repo_factory(uow.session)
            configs = repo.list_active_by_company(company_id)

        applicable = [
            c for c in configs
            if c.min_run_amount is None or c.min_run_amount <= run_total_net_payable
        ]
        if not applicable:
            return ApprovalRoutingResultDTO(
                required_approver_user_id=None,
                routing_reason="No approval routing rule configured for this company.",
            )

        # Prefer the most-specific threshold (highest min_run_amount).
        applicable.sort(
            key=lambda c: (c.min_run_amount is None, -(c.min_run_amount or Decimal(0)))
        )
        best = applicable[0]
        threshold_note = (
            f"threshold ≥ {best.min_run_amount}"
            if best.min_run_amount is not None
            else "unconditional rule"
        )
        return ApprovalRoutingResultDTO(
            required_approver_user_id=best.approver_user_id,
            routing_reason=f"Routed to user {best.approver_user_id} via {threshold_note}.",
        )

    # ── Mutations ─────────────────────────────────────────────────────────

    def add_approver_config(
        self,
        company_id: int,
        cmd: SetApproverConfigCommand,
    ) -> ApproverConfigDTO:
        """Add a new approval routing rule.  Requires PAYROLL_APPROVER_CONFIG_MANAGE."""
        self._permission_service.require_permission(PAYROLL_APPROVER_CONFIG_MANAGE)
        if cmd.min_run_amount is not None and cmd.min_run_amount < Decimal(0):
            raise ValidationError("Minimum run amount cannot be negative.")
        with self._uow_factory() as uow:
            config = PayrollApproverConfig(
                company_id=company_id,
                approver_user_id=cmd.approver_user_id,
                min_run_amount=cmd.min_run_amount,
                is_active=True,
            )
            repo = self._config_repo_factory(uow.session)
            repo.save(config)
            uow.commit()
            return self._to_dto(config)

    def remove_approver_config(self, company_id: int, config_id: int) -> None:
        """Delete an approval routing rule.  Requires PAYROLL_APPROVER_CONFIG_MANAGE."""
        self._permission_service.require_permission(PAYROLL_APPROVER_CONFIG_MANAGE)
        with self._uow_factory() as uow:
            repo = self._config_repo_factory(uow.session)
            config = repo.get_by_id(company_id, config_id)
            if config is None:
                raise NotFoundError("Approver config not found.")
            repo.delete(config)
            uow.commit()

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(config: PayrollApproverConfig) -> ApproverConfigDTO:
        return ApproverConfigDTO(
            id=config.id,
            company_id=config.company_id,
            approver_user_id=config.approver_user_id,
            min_run_amount=config.min_run_amount,
            is_active=config.is_active,
        )
