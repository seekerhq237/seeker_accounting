from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.dto.payroll_component_dto import (
    CreatePayrollComponentCommand,
    PayrollComponentDetailDTO,
    PayrollComponentListItemDTO,
    UpdatePayrollComponentCommand,
)
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

PayrollComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]

_VALID_COMPONENT_TYPES = frozenset({
    "earning", "deduction", "employer_contribution", "tax", "informational",
})

_VALID_CALCULATION_METHODS = frozenset({
    "fixed_amount", "percentage", "rule_based", "manual_input", "hourly",
})


class PayrollComponentService:
    """Manage payroll component definitions (earnings, deductions, contributions)."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        component_repository_factory: PayrollComponentRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._component_repository_factory = component_repository_factory
        self._company_repository_factory = company_repository_factory
        self._account_repository_factory = account_repository_factory
        self._audit_service = audit_service

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_components(
        self,
        company_id: int,
        active_only: bool = False,
        component_type_code: str | None = None,
    ) -> list[PayrollComponentListItemDTO]:
        with self._unit_of_work_factory() as uow:
            rows = self._component_repository_factory(uow.session).list_by_company(
                company_id, active_only=active_only, component_type_code=component_type_code
            )
            return [self._to_list_dto(r) for r in rows]

    def get_component(self, company_id: int, component_id: int) -> PayrollComponentDetailDTO:
        with self._unit_of_work_factory() as uow:
            row = self._component_repository_factory(uow.session).get_by_id(
                company_id, component_id
            )
            if row is None:
                raise NotFoundError(f"Payroll component {component_id} not found.")
            return self._to_detail_dto(row)

    # ── Commands ──────────────────────────────────────────────────────────────

    def create_component(
        self, company_id: int, command: CreatePayrollComponentCommand
    ) -> PayrollComponentDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_fields(command.component_code, command.component_name,
                                  command.component_type_code, command.calculation_method_code)
            self._validate_accounts(uow.session, company_id,
                                    command.expense_account_id, command.liability_account_id)
            repo = self._component_repository_factory(uow.session)
            if repo.get_by_code(company_id, command.component_code.strip().upper()) is not None:
                raise ConflictError(
                    f"Component code '{command.component_code}' already exists."
                )
            now = datetime.utcnow()
            comp = PayrollComponent(
                company_id=company_id,
                component_code=command.component_code.strip().upper(),
                component_name=command.component_name.strip(),
                component_type_code=command.component_type_code,
                calculation_method_code=command.calculation_method_code,
                is_taxable=command.is_taxable,
                is_pensionable=command.is_pensionable,
                expense_account_id=command.expense_account_id,
                liability_account_id=command.liability_account_id,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            repo.save(comp)
            uow.commit()
            row = self._component_repository_factory(uow.session).get_by_id(company_id, comp.id)
            from seeker_accounting.modules.audit.event_type_catalog import PAYROLL_COMPONENT_CREATED
            self._record_audit(company_id, PAYROLL_COMPONENT_CREATED, "PayrollComponent", comp.id, f"Created payroll component '{command.component_code}'")
            return self._to_detail_dto(row)  # type: ignore[arg-type]

    def update_component(
        self, company_id: int, component_id: int, command: UpdatePayrollComponentCommand
    ) -> PayrollComponentDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._component_repository_factory(uow.session)
            comp = repo.get_by_id(company_id, component_id)
            if comp is None:
                raise NotFoundError(f"Payroll component {component_id} not found.")
            self._validate_fields(command.component_code, command.component_name,
                                  command.component_type_code, command.calculation_method_code)
            self._validate_accounts(uow.session, company_id,
                                    command.expense_account_id, command.liability_account_id)
            existing = repo.get_by_code(company_id, command.component_code.strip().upper())
            if existing is not None and existing.id != component_id:
                raise ConflictError(
                    f"Component code '{command.component_code}' already exists."
                )
            comp.component_code = command.component_code.strip().upper()
            comp.component_name = command.component_name.strip()
            comp.component_type_code = command.component_type_code
            comp.calculation_method_code = command.calculation_method_code
            comp.is_taxable = command.is_taxable
            comp.is_pensionable = command.is_pensionable
            comp.expense_account_id = command.expense_account_id
            comp.liability_account_id = command.liability_account_id
            comp.is_active = command.is_active
            comp.updated_at = datetime.utcnow()
            repo.save(comp)
            uow.commit()
            row = self._component_repository_factory(uow.session).get_by_id(company_id, component_id)
            from seeker_accounting.modules.audit.event_type_catalog import PAYROLL_COMPONENT_UPDATED
            self._record_audit(company_id, PAYROLL_COMPONENT_UPDATED, "PayrollComponent", comp.id, f"Updated payroll component id={component_id}")
            return self._to_detail_dto(row)  # type: ignore[arg-type]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _validate_fields(
        self,
        component_code: str,
        component_name: str,
        component_type_code: str,
        calculation_method_code: str,
    ) -> None:
        if not component_code or not component_code.strip():
            raise ValidationError("Component code is required.")
        if not component_name or not component_name.strip():
            raise ValidationError("Component name is required.")
        if component_type_code not in _VALID_COMPONENT_TYPES:
            raise ValidationError(
                f"Component type '{component_type_code}' is not valid. "
                f"Valid: {', '.join(sorted(_VALID_COMPONENT_TYPES))}."
            )
        if calculation_method_code not in _VALID_CALCULATION_METHODS:
            raise ValidationError(
                f"Calculation method '{calculation_method_code}' is not valid. "
                f"Valid: {', '.join(sorted(_VALID_CALCULATION_METHODS))}."
            )

    def _validate_accounts(
        self,
        session: Session,
        company_id: int,
        expense_account_id: int | None,
        liability_account_id: int | None,
    ) -> None:
        account_repo = self._account_repository_factory(session)
        if expense_account_id is not None:
            if account_repo.get_by_id(company_id, expense_account_id) is None:
                raise ValidationError(
                    f"Expense account {expense_account_id} not found in this company."
                )
        if liability_account_id is not None:
            if account_repo.get_by_id(company_id, liability_account_id) is None:
                raise ValidationError(
                    f"Liability account {liability_account_id} not found in this company."
                )

    def _to_list_dto(self, comp: PayrollComponent) -> PayrollComponentListItemDTO:
        return PayrollComponentListItemDTO(
            id=comp.id,
            company_id=comp.company_id,
            component_code=comp.component_code,
            component_name=comp.component_name,
            component_type_code=comp.component_type_code,
            calculation_method_code=comp.calculation_method_code,
            is_taxable=comp.is_taxable,
            is_pensionable=comp.is_pensionable,
            expense_account_id=comp.expense_account_id,
            expense_account_code=(
                comp.expense_account.account_code if comp.expense_account else None
            ),
            liability_account_id=comp.liability_account_id,
            liability_account_code=(
                comp.liability_account.account_code if comp.liability_account else None
            ),
            is_active=comp.is_active,
        )

    def _to_detail_dto(self, comp: PayrollComponent) -> PayrollComponentDetailDTO:
        return PayrollComponentDetailDTO(
            id=comp.id,
            company_id=comp.company_id,
            component_code=comp.component_code,
            component_name=comp.component_name,
            component_type_code=comp.component_type_code,
            calculation_method_code=comp.calculation_method_code,
            is_taxable=comp.is_taxable,
            is_pensionable=comp.is_pensionable,
            expense_account_id=comp.expense_account_id,
            expense_account_code=(
                comp.expense_account.account_code if comp.expense_account else None
            ),
            expense_account_name=(
                comp.expense_account.account_name if comp.expense_account else None
            ),
            liability_account_id=comp.liability_account_id,
            liability_account_code=(
                comp.liability_account.account_code if comp.liability_account else None
            ),
            liability_account_name=(
                comp.liability_account.account_name if comp.liability_account else None
            ),
            is_active=comp.is_active,
            created_at=comp.created_at,
            updated_at=comp.updated_at,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_PAYROLL
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_PAYROLL,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
