from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.event_type_catalog import (
    ACCOUNT_CREATED,
    ACCOUNT_DEACTIVATED,
    ACCOUNT_UPDATED,
    MODULE_CHART,
)
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import (
    CreateAccountCommand,
    UpdateAccountCommand,
)
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import (
    AccountDetailDTO,
    AccountListItemDTO,
    AccountLookupDTO,
    AccountTreeNodeDTO,
)
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.accounting.reference_data.repositories.account_class_repository import (
    AccountClassRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_type_repository import (
    AccountTypeRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AccountRepositoryFactory = Callable[[Session], AccountRepository]
AccountClassRepositoryFactory = Callable[[Session], AccountClassRepository]
AccountTypeRepositoryFactory = Callable[[Session], AccountTypeRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class ChartOfAccountsService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        account_repository_factory: AccountRepositoryFactory,
        account_class_repository_factory: AccountClassRepositoryFactory,
        account_type_repository_factory: AccountTypeRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._account_repository_factory = account_repository_factory
        self._account_class_repository_factory = account_class_repository_factory
        self._account_type_repository_factory = account_type_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_accounts(self, company_id: int, active_only: bool = False) -> list[AccountListItemDTO]:
        self._permission_service.require_permission("chart.accounts.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            account_class_repository = self._require_account_class_repository(uow.session)
            account_type_repository = self._require_account_type_repository(uow.session)

            accounts = account_repository.list_by_company(company_id, active_only=active_only)
            account_classes = account_class_repository.list_all(active_only=False)
            account_types = account_type_repository.list_all(active_only=False)
            return self._to_account_list_dtos(accounts, account_classes, account_types)

    def get_account(self, company_id: int, account_id: int) -> AccountDetailDTO:
        self._permission_service.require_permission("chart.accounts.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            account_class_repository = self._require_account_class_repository(uow.session)
            account_type_repository = self._require_account_type_repository(uow.session)

            account = account_repository.get_by_id(company_id, account_id)
            if account is None:
                raise NotFoundError(f"Account with id {account_id} was not found.")

            account_classes = {row.id: row for row in account_class_repository.list_all(active_only=False)}
            account_types = {row.id: row for row in account_type_repository.list_all(active_only=False)}
            accounts = {row.id: row for row in account_repository.list_by_company(company_id, active_only=False)}
            return self._to_account_detail_dto(account, account_classes, account_types, accounts)

    def list_account_tree(self, company_id: int, active_only: bool = False) -> list[AccountTreeNodeDTO]:
        self._permission_service.require_permission("chart.accounts.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            account_class_repository = self._require_account_class_repository(uow.session)
            account_type_repository = self._require_account_type_repository(uow.session)

            accounts = account_repository.list_by_company(company_id, active_only=active_only)
            account_classes = {row.id: row for row in account_class_repository.list_all(active_only=False)}
            account_types = {row.id: row for row in account_type_repository.list_all(active_only=False)}

            children_by_parent_id: dict[int | None, list[Account]] = defaultdict(list)
            for account in accounts:
                children_by_parent_id[account.parent_account_id].append(account)

            for children in children_by_parent_id.values():
                children.sort(key=lambda row: (row.account_code, row.id))

            def build_node(account: Account) -> AccountTreeNodeDTO:
                account_class = account_classes[account.account_class_id]
                account_type = account_types[account.account_type_id]
                return AccountTreeNodeDTO(
                    id=account.id,
                    company_id=account.company_id,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    account_class_code=account_class.code,
                    account_class_name=account_class.name,
                    account_type_code=account_type.code,
                    account_type_name=account_type.name,
                    parent_account_id=account.parent_account_id,
                    normal_balance=account.normal_balance,
                    allow_manual_posting=account.allow_manual_posting,
                    is_control_account=account.is_control_account,
                    is_active=account.is_active,
                    children=tuple(build_node(child) for child in children_by_parent_id.get(account.id, [])),
                )

            return [build_node(account) for account in children_by_parent_id.get(None, [])]

    def list_account_lookup_options(
        self,
        company_id: int,
        active_only: bool = False,
        exclude_account_id: int | None = None,
    ) -> list[AccountLookupDTO]:
        self._permission_service.require_permission("chart.accounts.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            accounts = account_repository.list_tree_candidates(company_id, exclude_account_id=exclude_account_id)
            if active_only:
                accounts = [account for account in accounts if account.is_active]
            return [
                AccountLookupDTO(
                    id=account.id,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    is_active=account.is_active,
                    is_control_account=account.is_control_account,
                    allow_manual_posting=account.allow_manual_posting,
                )
                for account in accounts
            ]

    def create_account(self, company_id: int, command: CreateAccountCommand) -> AccountDetailDTO:
        self._permission_service.require_permission("chart.accounts.create")
        normalized_command = self._normalize_create_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            account_class_repository = self._require_account_class_repository(uow.session)
            account_type_repository = self._require_account_type_repository(uow.session)

            if account_repository.account_code_exists(company_id, normalized_command.account_code):
                raise ConflictError("An account with this code already exists for the company.")

            self._require_account_class(account_class_repository, normalized_command.account_class_id)
            self._require_account_type(account_type_repository, normalized_command.account_type_id)
            self._validate_parent_account(
                account_repository=account_repository,
                company_id=company_id,
                parent_account_id=normalized_command.parent_account_id,
                account_id=None,
            )

            account = Account(
                company_id=company_id,
                account_code=normalized_command.account_code,
                account_name=normalized_command.account_name,
                account_class_id=normalized_command.account_class_id,
                account_type_id=normalized_command.account_type_id,
                parent_account_id=normalized_command.parent_account_id,
                normal_balance=normalized_command.normal_balance,
                allow_manual_posting=normalized_command.allow_manual_posting,
                is_control_account=normalized_command.is_control_account,
                notes=normalized_command.notes,
            )
            account_repository.add(account)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_account_integrity_error(exc) from exc

            self._record_audit(
                company_id, ACCOUNT_CREATED, "Account", account.id,
                f"Created account {account.account_code} — {account.account_name}",
            )

            return self._to_account_detail_dto(
                account,
                {row.id: row for row in account_class_repository.list_all(active_only=False)},
                {row.id: row for row in account_type_repository.list_all(active_only=False)},
                {row.id: row for row in account_repository.list_by_company(company_id, active_only=False)},
            )

    def update_account(self, company_id: int, account_id: int, command: UpdateAccountCommand) -> AccountDetailDTO:
        self._permission_service.require_permission("chart.accounts.edit")
        normalized_command = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            account_class_repository = self._require_account_class_repository(uow.session)
            account_type_repository = self._require_account_type_repository(uow.session)

            account = account_repository.get_by_id(company_id, account_id)
            if account is None:
                raise NotFoundError(f"Account with id {account_id} was not found.")

            if account_repository.account_code_exists(
                company_id,
                normalized_command.account_code,
                exclude_account_id=account_id,
            ):
                raise ConflictError("An account with this code already exists for the company.")

            self._require_account_class(account_class_repository, normalized_command.account_class_id)
            self._require_account_type(account_type_repository, normalized_command.account_type_id)
            self._validate_parent_account(
                account_repository=account_repository,
                company_id=company_id,
                parent_account_id=normalized_command.parent_account_id,
                account_id=account_id,
            )

            account.account_code = normalized_command.account_code
            account.account_name = normalized_command.account_name
            account.account_class_id = normalized_command.account_class_id
            account.account_type_id = normalized_command.account_type_id
            account.parent_account_id = normalized_command.parent_account_id
            account.normal_balance = normalized_command.normal_balance
            account.allow_manual_posting = normalized_command.allow_manual_posting
            account.is_control_account = normalized_command.is_control_account
            account.is_active = normalized_command.is_active
            account.notes = normalized_command.notes
            account_repository.save(account)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_account_integrity_error(exc) from exc

            self._record_audit(
                company_id, ACCOUNT_UPDATED, "Account", account.id,
                f"Updated account {account.account_code} — {account.account_name}",
            )

            return self._to_account_detail_dto(
                account,
                {row.id: row for row in account_class_repository.list_all(active_only=False)},
                {row.id: row for row in account_type_repository.list_all(active_only=False)},
                {row.id: row for row in account_repository.list_by_company(company_id, active_only=False)},
            )

    def deactivate_account(self, company_id: int, account_id: int) -> None:
        self._permission_service.require_permission("chart.accounts.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            account = account_repository.get_by_id(company_id, account_id)
            if account is None:
                raise NotFoundError(f"Account with id {account_id} was not found.")

            active_children = [
                child
                for child in account_repository.list_children(company_id, account_id)
                if child.is_active
            ]
            if active_children:
                raise ValidationError("Deactivate child accounts before deactivating this account.")

            account.is_active = False
            account_repository.save(account)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Account could not be deactivated.") from exc

            self._record_audit(
                company_id, ACCOUNT_DEACTIVATED, "Account", account_id,
                f"Deactivated account {account.account_code} — {account.account_name}",
            )

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_account_class_repository(self, session: Session | None) -> AccountClassRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_class_repository_factory(session)

    def _require_account_type_repository(self, session: Session | None) -> AccountTypeRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_type_repository_factory(session)

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_account_class(
        self,
        account_class_repository: AccountClassRepository,
        account_class_id: int,
    ) -> AccountClass:
        account_class = account_class_repository.get_by_id(account_class_id)
        if account_class is None:
            raise ValidationError("Account class must reference an existing chart class.")
        return account_class

    def _require_account_type(
        self,
        account_type_repository: AccountTypeRepository,
        account_type_id: int,
    ) -> AccountType:
        account_type = account_type_repository.get_by_id(account_type_id)
        if account_type is None:
            raise ValidationError("Account type must reference an existing chart type.")
        return account_type

    def _validate_parent_account(
        self,
        *,
        account_repository: AccountRepository,
        company_id: int,
        parent_account_id: int | None,
        account_id: int | None,
    ) -> None:
        if parent_account_id is None:
            return

        if account_id is not None and parent_account_id == account_id:
            raise ValidationError("Parent account cannot be the same as the account.")

        parent_account = account_repository.get_by_id(company_id, parent_account_id)
        if parent_account is None:
            raise ValidationError("Parent account must reference an existing account in the same company.")

        visited_ids: set[int] = set()
        current_account = parent_account
        while current_account is not None:
            if current_account.id in visited_ids:
                raise ValidationError("Account hierarchy contains a circular parent chain.")
            visited_ids.add(current_account.id)

            if account_id is not None and current_account.id == account_id:
                raise ValidationError("Parent account cannot create a hierarchy cycle.")

            if current_account.parent_account_id is None:
                return
            current_account = account_repository.get_by_id(company_id, current_account.parent_account_id)

    def _normalize_create_command(self, command: CreateAccountCommand) -> CreateAccountCommand:
        return CreateAccountCommand(
            account_code=self._require_account_code(command.account_code),
            account_name=self._require_text(command.account_name, "Account name"),
            account_class_id=self._require_positive_id(command.account_class_id, "Account class"),
            account_type_id=self._require_positive_id(command.account_type_id, "Account type"),
            normal_balance=self._require_normal_balance(command.normal_balance),
            allow_manual_posting=bool(command.allow_manual_posting),
            is_control_account=bool(command.is_control_account),
            parent_account_id=self._normalize_optional_id(command.parent_account_id),
            notes=self._normalize_optional_text(command.notes),
        )

    def _normalize_update_command(self, command: UpdateAccountCommand) -> UpdateAccountCommand:
        return UpdateAccountCommand(
            account_code=self._require_account_code(command.account_code),
            account_name=self._require_text(command.account_name, "Account name"),
            account_class_id=self._require_positive_id(command.account_class_id, "Account class"),
            account_type_id=self._require_positive_id(command.account_type_id, "Account type"),
            normal_balance=self._require_normal_balance(command.normal_balance),
            allow_manual_posting=bool(command.allow_manual_posting),
            is_control_account=bool(command.is_control_account),
            is_active=bool(command.is_active),
            parent_account_id=self._normalize_optional_id(command.parent_account_id),
            notes=self._normalize_optional_text(command.notes),
        )

    def _require_account_code(self, value: str) -> str:
        normalized = "".join(character for character in value.strip().upper() if character not in {" ", "\t"})
        if not normalized:
            raise ValidationError("Account code is required.")
        return normalized

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _require_positive_id(self, value: int, label: str) -> int:
        if value <= 0:
            raise ValidationError(f"{label} is required.")
        return value

    def _normalize_optional_id(self, value: int | None) -> int | None:
        if value is None or value <= 0:
            return None
        return value

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _require_normal_balance(self, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBIT", "CREDIT"}:
            raise ValidationError("Normal balance must be DEBIT or CREDIT.")
        return normalized

    def _translate_account_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_accounts" in message or "account_code" in message:
            return ConflictError("An account with this code already exists for the company.")
        return ValidationError("Account data could not be saved.")

    def _to_account_list_dtos(
        self,
        accounts: list[Account],
        account_classes: list[AccountClass],
        account_types: list[AccountType],
    ) -> list[AccountListItemDTO]:
        account_class_by_id = {row.id: row for row in account_classes}
        account_type_by_id = {row.id: row for row in account_types}
        account_by_id = {row.id: row for row in accounts}
        return [
            self._to_account_list_item_dto(account, account_class_by_id, account_type_by_id, account_by_id)
            for account in accounts
        ]

    def _to_account_list_item_dto(
        self,
        account: Account,
        account_class_by_id: dict[int, AccountClass],
        account_type_by_id: dict[int, AccountType],
        account_by_id: dict[int, Account],
    ) -> AccountListItemDTO:
        account_class = account_class_by_id[account.account_class_id]
        account_type = account_type_by_id[account.account_type_id]
        parent_account = account_by_id.get(account.parent_account_id)
        return AccountListItemDTO(
            id=account.id,
            company_id=account.company_id,
            account_code=account.account_code,
            account_name=account.account_name,
            account_class_id=account.account_class_id,
            account_class_code=account_class.code,
            account_class_name=account_class.name,
            account_type_id=account.account_type_id,
            account_type_code=account_type.code,
            account_type_name=account_type.name,
            parent_account_id=account.parent_account_id,
            parent_account_code=parent_account.account_code if parent_account is not None else None,
            parent_account_name=parent_account.account_name if parent_account is not None else None,
            normal_balance=account.normal_balance,
            allow_manual_posting=account.allow_manual_posting,
            is_control_account=account.is_control_account,
            is_active=account.is_active,
            updated_at=account.updated_at,
        )

    def _to_account_detail_dto(
        self,
        account: Account,
        account_class_by_id: dict[int, AccountClass],
        account_type_by_id: dict[int, AccountType],
        account_by_id: dict[int, Account],
    ) -> AccountDetailDTO:
        list_item = self._to_account_list_item_dto(
            account,
            account_class_by_id,
            account_type_by_id,
            account_by_id,
        )
        return AccountDetailDTO(
            id=list_item.id,
            company_id=list_item.company_id,
            account_code=list_item.account_code,
            account_name=list_item.account_name,
            account_class_id=list_item.account_class_id,
            account_class_code=list_item.account_class_code,
            account_class_name=list_item.account_class_name,
            account_type_id=list_item.account_type_id,
            account_type_code=list_item.account_type_code,
            account_type_name=list_item.account_type_name,
            parent_account_id=list_item.parent_account_id,
            parent_account_code=list_item.parent_account_code,
            parent_account_name=list_item.parent_account_name,
            normal_balance=list_item.normal_balance,
            allow_manual_posting=list_item.allow_manual_posting,
            is_control_account=list_item.is_control_account,
            is_active=list_item.is_active,
            notes=account.notes,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
        detail_json: str | None = None,
    ) -> None:
        if self._audit_service is None:
            return
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_CHART,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                    detail_json=detail_json,
                ),
            )
        except Exception:  # noqa: BLE001 — audit must never break chart of accounts flow
            pass
