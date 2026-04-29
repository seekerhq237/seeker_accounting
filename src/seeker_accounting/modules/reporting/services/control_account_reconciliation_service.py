"""Control Account Reconciliation service.

Read-only reconciliation between AR/AP control GL balances and their
subledger aging totals. No posting, no audit; pure diagnostic surface
consumed by the Control Account Reconciliation wizard and (optionally)
month-end close advisors.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.reporting.dto.control_account_reconciliation_dto import (
    ControlAccountReconciliationDTO,
    ControlAccountReconciliationReportDTO,
)
from seeker_accounting.modules.reporting.repositories.ap_aging_report_repository import (
    APAgingReportRepository,
)
from seeker_accounting.modules.reporting.repositories.ar_aging_report_repository import (
    ARAgingReportRepository,
)
from seeker_accounting.platform.exceptions import ValidationError

ARAgingReportRepositoryFactory = Callable[[Session], ARAgingReportRepository]
APAgingReportRepositoryFactory = Callable[[Session], APAgingReportRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]

_AR_CONTROL = "ar_control"
_AP_CONTROL = "ap_control"
_SUPPORTED_ROLES = frozenset({_AR_CONTROL, _AP_CONTROL})
_ROLE_LABELS: dict[str, str] = {
    _AR_CONTROL: "AR Control",
    _AP_CONTROL: "AP Control",
}
_RECONCILED_TOLERANCE = Decimal("0.01")
_ZERO = Decimal("0.00")


class ControlAccountReconciliationService:
    """Reconciles a control account GL balance against its subledger total."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ar_aging_report_repository_factory: ARAgingReportRepositoryFactory,
        ap_aging_report_repository_factory: APAgingReportRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._ar_aging_report_repository_factory = ar_aging_report_repository_factory
        self._ap_aging_report_repository_factory = ap_aging_report_repository_factory
        self._account_repository_factory = account_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory

    def reconcile(
        self,
        company_id: int,
        role_code: str,
        as_of_date: date,
    ) -> ControlAccountReconciliationDTO:
        normalized = (role_code or "").strip().lower()
        if normalized not in _SUPPORTED_ROLES:
            raise ValidationError(
                f"Unsupported control role '{role_code}'. Expected one of: "
                f"{', '.join(sorted(_SUPPORTED_ROLES))}."
            )

        with self._unit_of_work_factory() as uow:
            mapping_repo = self._account_role_mapping_repository_factory(uow.session)
            mapping = mapping_repo.get_by_role_code(company_id, normalized)
            if mapping is None or not isinstance(mapping.account_id, int):
                return ControlAccountReconciliationDTO(
                    role_code=normalized,
                    role_label=_ROLE_LABELS[normalized],
                    as_of_date=as_of_date,
                    account_mapped=False,
                )

            account_repo = self._account_repository_factory(uow.session)
            account = account_repo.get_by_id(company_id, int(mapping.account_id))
            account_code = account.account_code if account is not None else None
            account_name = account.account_name if account is not None else None

            if normalized == _AR_CONTROL:
                aging_repo = self._ar_aging_report_repository_factory(uow.session)
                gl_balance = aging_repo.sum_control_balance(company_id, as_of_date)
                rows = aging_repo.list_open_documents(company_id, as_of_date)
                party_ids = {row.customer_id for row in rows}
                subledger_total = sum(
                    (abs(row.open_amount) for row in rows), _ZERO
                ).quantize(Decimal("0.01"))
            else:
                ap_repo = self._ap_aging_report_repository_factory(uow.session)
                gl_balance = ap_repo.sum_control_balance(company_id, as_of_date)
                rows = ap_repo.list_open_documents(company_id, as_of_date)
                party_ids = {row.supplier_id for row in rows}
                subledger_total = sum(
                    (abs(row.open_amount) for row in rows), _ZERO
                ).quantize(Decimal("0.01"))

        # Sign convention: AR control is naturally a debit balance, AP control
        # a credit balance. The subledger total is unsigned. To compare, we
        # take absolute value of GL balance for the delta calculation.
        delta: Decimal | None
        is_reconciled = False
        if gl_balance is None:
            delta = None
        else:
            delta = (abs(gl_balance) - subledger_total).quantize(Decimal("0.01"))
            is_reconciled = abs(delta) < _RECONCILED_TOLERANCE

        return ControlAccountReconciliationDTO(
            role_code=normalized,
            role_label=_ROLE_LABELS[normalized],
            as_of_date=as_of_date,
            account_mapped=True,
            account_id=int(mapping.account_id),
            account_code=account_code,
            account_name=account_name,
            gl_balance=gl_balance,
            subledger_total=subledger_total,
            party_count=len(party_ids),
            document_count=len(rows),
            delta=delta,
            is_reconciled=is_reconciled,
        )

    def reconcile_all(
        self,
        company_id: int,
        as_of_date: date,
        role_codes: tuple[str, ...] = (_AR_CONTROL, _AP_CONTROL),
    ) -> ControlAccountReconciliationReportDTO:
        sections = tuple(
            self.reconcile(company_id, code, as_of_date) for code in role_codes
        )
        return ControlAccountReconciliationReportDTO(
            company_id=company_id,
            as_of_date=as_of_date,
            sections=sections,
        )
