from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.ias_income_statement_mapping_dto import (
    IasIncomeStatementAccountOptionDTO,
    IasIncomeStatementMappingDTO,
    IasIncomeStatementMappingEditorDTO,
    IasIncomeStatementSectionDTO,
    IasIncomeStatementValidationIssueDTO,
    ToggleIasIncomeStatementMappingStateCommand,
    UpsertIasIncomeStatementMappingCommand,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_mapping_repository import (
    IasIncomeStatementMappingRepository,
    IasMappingRow,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_repository import (
    IasAccountActivityRow,
    IasCompanyAccountRow,
    IasIncomeStatementRepository,
)
from seeker_accounting.modules.reporting.services.ias_income_statement_template_service import (
    IasIncomeStatementTemplateService,
)
from seeker_accounting.modules.reporting.specs.ias_income_statement_spec import (
    IAS_INCOME_STATEMENT_PROFILE_CODE,
    IAS_SIGN_BEHAVIOR_INVERTED,
    IAS_SIGN_BEHAVIOR_NORMAL,
    is_relevant_income_statement_account,
    normalize_sign_behavior_code,
    suggest_default_sign_behavior,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

IasIncomeStatementRepositoryFactory = Callable[[Session], IasIncomeStatementRepository]
IasIncomeStatementMappingRepositoryFactory = Callable[[Session], IasIncomeStatementMappingRepository]

class IasIncomeStatementMappingService:
    """Company-scoped IAS mapping persistence and validation."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        ias_income_statement_repository_factory: IasIncomeStatementRepositoryFactory,
        ias_income_statement_mapping_repository_factory: IasIncomeStatementMappingRepositoryFactory,
        ias_income_statement_template_service: IasIncomeStatementTemplateService,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._ias_income_statement_repository_factory = ias_income_statement_repository_factory
        self._ias_income_statement_mapping_repository_factory = ias_income_statement_mapping_repository_factory
        self._ias_income_statement_template_service = ias_income_statement_template_service
        self._permission_service = permission_service

    def get_editor_snapshot(self, company_id: int) -> IasIncomeStatementMappingEditorDTO:
        self._permission_service.require_permission("reports.ias_mappings.view")
        with self._unit_of_work_factory() as uow:
            repo = self._ias_income_statement_repository_factory(uow.session)
            mapping_repo = self._ias_income_statement_mapping_repository_factory(uow.session)
            sections = self._ias_income_statement_template_service.list_sections()
            account_rows = repo.list_company_accounts(company_id, active_only=False)
            mapping_rows = mapping_repo.list_by_company(
                company_id,
                IAS_INCOME_STATEMENT_PROFILE_CODE,
                active_only=False,
            )

        section_map = {section.section_code: section for section in sections}
        mappings = tuple(self._to_mapping_dto(row, section_map) for row in mapping_rows)
        account_options = self._build_account_options(account_rows, mappings, mapping_rows)
        issues = self._validate_snapshot(
            company_id=company_id,
            sections=sections,
            account_options=account_options,
            mapping_rows=mapping_rows,
        )
        unmapped_relevant_accounts = tuple(
            option
            for option in account_options
            if option.is_active
            and is_relevant_income_statement_account(
                account_class_code=option.account_class_code,
                account_type_section_code=option.account_type_section_code,
                account_code=option.account_code,
            )
            and (option.mapped_mapping_id is None or option.mapped_is_active is False)
        )

        return IasIncomeStatementMappingEditorDTO(
            company_id=company_id,
            statement_profile_code=IAS_INCOME_STATEMENT_PROFILE_CODE,
            sections=sections,
            account_options=tuple(account_options),
            mappings=mappings,
            issues=issues,
            unmapped_relevant_accounts=unmapped_relevant_accounts,
            has_mappings=any(mapping.is_active for mapping in mappings),
            has_issues=bool(issues),
        )

    def upsert_mappings(
        self,
        company_id: int,
        command: UpsertIasIncomeStatementMappingCommand,
    ) -> IasIncomeStatementMappingEditorDTO:
        self._permission_service.require_permission("reports.ias_mappings.manage")
        section_code = self._require_code(command.section_code, "Section")
        subsection_code = self._normalize_optional_code(command.subsection_code)
        sign_behavior_code = normalize_sign_behavior_code(command.sign_behavior_code)
        display_order = self._normalize_display_order(command.display_order)
        account_ids = self._normalize_account_ids(command.account_ids)

        with self._unit_of_work_factory() as uow:
            repo = self._ias_income_statement_repository_factory(uow.session)
            mapping_repo = self._ias_income_statement_mapping_repository_factory(uow.session)
            sections = self._ias_income_statement_template_service.list_sections()
            account_rows = repo.list_company_accounts(company_id, active_only=False)
            section_map = {section.section_code: section for section in sections}

            self._validate_section_target(section_map, section_code, subsection_code)

            accounts_by_id = {row.account_id: row for row in account_rows}
            for account_id in account_ids:
                account_row = accounts_by_id.get(account_id)
                if account_row is None:
                    raise NotFoundError(f"Account with id {account_id} was not found.")
                self._validate_account_row(account_row)

            next_display_order = display_order
            for account_id in account_ids:
                existing = mapping_repo.get_by_account(
                    company_id,
                    IAS_INCOME_STATEMENT_PROFILE_CODE,
                    account_id,
                )
                if existing is None:
                    mapping = self._new_mapping(
                        company_id=company_id,
                        account_id=account_id,
                        section_code=section_code,
                        subsection_code=subsection_code,
                        sign_behavior_code=sign_behavior_code,
                        display_order=next_display_order,
                        is_active=command.is_active,
                    )
                    mapping.created_by_user_id = self._app_context.current_user_id
                    mapping.updated_by_user_id = self._app_context.current_user_id
                    mapping_repo.add(mapping)
                else:
                    existing.statement_profile_code = IAS_INCOME_STATEMENT_PROFILE_CODE
                    existing.section_code = section_code
                    existing.subsection_code = subsection_code
                    existing.sign_behavior_code = sign_behavior_code
                    existing.display_order = next_display_order
                    existing.is_active = command.is_active
                    existing.updated_by_user_id = self._app_context.current_user_id
                    mapping_repo.save(existing)
                next_display_order += 10

            uow.commit()

        return self.get_editor_snapshot(company_id)

    def toggle_mapping_state(
        self,
        company_id: int,
        command: ToggleIasIncomeStatementMappingStateCommand,
    ) -> IasIncomeStatementMappingEditorDTO:
        with self._unit_of_work_factory() as uow:
            mapping_repo = self._ias_income_statement_mapping_repository_factory(uow.session)
            mapping = mapping_repo.get_by_id(
                company_id,
                IAS_INCOME_STATEMENT_PROFILE_CODE,
                command.mapping_id,
            )
            if mapping is None:
                raise NotFoundError(f"Mapping with id {command.mapping_id} was not found.")
            mapping.is_active = command.is_active
            mapping.updated_by_user_id = self._app_context.current_user_id
            mapping_repo.save(mapping)
            uow.commit()
        return self.get_editor_snapshot(company_id)

    def list_unmapped_relevant_accounts(self, company_id: int) -> tuple[IasIncomeStatementAccountOptionDTO, ...]:
        return self.get_editor_snapshot(company_id).unmapped_relevant_accounts

    def get_active_mappings(
        self,
        company_id: int,
    ) -> tuple[IasIncomeStatementMappingDTO, ...]:
        snapshot = self.get_editor_snapshot(company_id)
        return tuple(mapping for mapping in snapshot.mappings if mapping.is_active)

    def _build_account_options(
        self,
        account_rows: list[IasCompanyAccountRow],
        mappings: tuple[IasIncomeStatementMappingDTO, ...],
        mapping_rows: list[IasMappingRow],
    ) -> list[IasIncomeStatementAccountOptionDTO]:
        mapping_lookup = self._mapping_lookup_by_account_id(mapping_rows)
        options: list[IasIncomeStatementAccountOptionDTO] = []
        for account_row in account_rows:
            mapped_row = mapping_lookup.get(account_row.account_id)
            default_sign = suggest_default_sign_behavior(
                normal_balance=account_row.normal_balance,
                account_type_section_code=account_row.account_type_section_code,
            )
            options.append(
                IasIncomeStatementAccountOptionDTO(
                    account_id=account_row.account_id,
                    account_code=account_row.account_code,
                    account_name=account_row.account_name,
                    account_class_code=account_row.account_class_code,
                    account_type_code=account_row.account_type_code,
                    account_type_section_code=account_row.account_type_section_code,
                    normal_balance=account_row.normal_balance,
                    allow_manual_posting=account_row.allow_manual_posting,
                    is_control_account=account_row.is_control_account,
                    is_active=account_row.is_active,
                    default_sign_behavior_code=default_sign,
                    mapped_mapping_id=mapped_row.mapping_id if mapped_row is not None else None,
                    mapped_section_code=mapped_row.section_code if mapped_row is not None else None,
                    mapped_subsection_code=mapped_row.subsection_code if mapped_row is not None else None,
                    mapped_sign_behavior_code=mapped_row.sign_behavior_code if mapped_row is not None else None,
                    mapped_display_order=mapped_row.display_order if mapped_row is not None else None,
                    mapped_is_active=mapped_row.is_active if mapped_row is not None else None,
                )
            )
        return options

    def _validate_snapshot(
        self,
        *,
        company_id: int,
        sections: tuple[IasIncomeStatementSectionDTO, ...],
        account_options: list[IasIncomeStatementAccountOptionDTO],
        mapping_rows: list[IasMappingRow],
    ) -> tuple[IasIncomeStatementValidationIssueDTO, ...]:
        issues: list[IasIncomeStatementValidationIssueDTO] = []
        section_map = {section.section_code: section for section in sections}
        account_map = {account.account_id: account for account in account_options}

        seen_account_ids: set[int] = set()
        for row in mapping_rows:
            account = account_map.get(row.account_id)
            if row.account_code is None or row.account_name is None:
                issues.append(
                    IasIncomeStatementValidationIssueDTO(
                        issue_code="missing_account",
                        severity_code="error",
                        title="Missing account reference",
                        message=(
                            f"Mapping {row.mapping_id} references account {row.account_id}, which no longer exists."
                        ),
                        account_id=row.account_id,
                        mapping_id=row.mapping_id,
                    )
                )
                continue
            if row.account_id in seen_account_ids:
                issues.append(
                    IasIncomeStatementValidationIssueDTO(
                        issue_code="duplicate_mapping",
                        severity_code="error",
                        title="Duplicate account mapping",
                        message=(
                            f"Account {row.account_code or row.account_id} is mapped more than once. "
                            "Only one active mapping per account is allowed."
                        ),
                        account_id=row.account_id,
                        account_code=row.account_code,
                        mapping_id=row.mapping_id,
                    )
                )
            else:
                seen_account_ids.add(row.account_id)

            if not row.is_active:
                issues.append(
                    IasIncomeStatementValidationIssueDTO(
                        issue_code="inactive_mapping",
                        severity_code="warning",
                        title="Inactive mapping",
                        message=(
                            f"Mapping {row.mapping_id} for account {row.account_code} is inactive and will not appear on the statement."
                        ),
                        account_id=row.account_id,
                        account_code=row.account_code,
                        mapping_id=row.mapping_id,
                    )
                )

            section = section_map.get(row.section_code)
            if section is None:
                issues.append(
                    IasIncomeStatementValidationIssueDTO(
                        issue_code="missing_section",
                        severity_code="error",
                        title="Missing IAS section",
                        message=f"Mapping {row.mapping_id} references section {row.section_code}, which is not defined.",
                        account_id=row.account_id,
                        account_code=row.account_code,
                        section_code=row.section_code,
                        mapping_id=row.mapping_id,
                    )
                )
                continue

            if section.row_kind_code == "formula" or not section.is_mapping_target and section.row_kind_code != "group":
                issues.append(
                    IasIncomeStatementValidationIssueDTO(
                        issue_code="invalid_section_target",
                        severity_code="error",
                        title="Invalid mapping target",
                        message=(
                            f"Section {section.section_label} cannot receive account mappings."
                        ),
                        account_id=row.account_id,
                        account_code=row.account_code,
                        section_code=row.section_code,
                        mapping_id=row.mapping_id,
                    )
                )

            if row.section_code == "OPERATING_EXPENSES" and not row.subsection_code:
                issues.append(
                    IasIncomeStatementValidationIssueDTO(
                        issue_code="missing_subsection",
                        severity_code="error",
                        title="Subsection required",
                        message=(
                            "Operating Expenses mappings must target a subsection such as "
                            "Selling and Distribution Expenses or Administrative Expenses."
                        ),
                        account_id=row.account_id,
                        account_code=row.account_code,
                        section_code=row.section_code,
                        mapping_id=row.mapping_id,
                    )
                )

            if row.subsection_code:
                subsection = section_map.get(row.subsection_code)
                if subsection is None:
                    issues.append(
                        IasIncomeStatementValidationIssueDTO(
                            issue_code="missing_subsection",
                            severity_code="error",
                            title="Missing subsection",
                            message=(
                                f"Mapping {row.mapping_id} references subsection {row.subsection_code}, "
                                "which is not defined."
                            ),
                            account_id=row.account_id,
                            account_code=row.account_code,
                            subsection_code=row.subsection_code,
                            mapping_id=row.mapping_id,
                        )
                    )
                else:
                    if subsection.parent_section_code != row.section_code:
                        issues.append(
                            IasIncomeStatementValidationIssueDTO(
                                issue_code="invalid_subsection_parent",
                                severity_code="error",
                                title="Invalid subsection",
                                message=(
                                    f"Subsection {subsection.section_label} does not belong under "
                                    f"section {section.section_label}."
                                ),
                                account_id=row.account_id,
                                account_code=row.account_code,
                                section_code=row.section_code,
                                subsection_code=row.subsection_code,
                                mapping_id=row.mapping_id,
                            )
                        )
                    if subsection.row_kind_code == "formula" or not subsection.is_mapping_target:
                        issues.append(
                            IasIncomeStatementValidationIssueDTO(
                                issue_code="invalid_subsection_target",
                                severity_code="error",
                                title="Invalid subsection target",
                                message=(
                                    f"Subsection {subsection.section_label} cannot receive account mappings."
                                ),
                                account_id=row.account_id,
                                account_code=row.account_code,
                                subsection_code=row.subsection_code,
                                mapping_id=row.mapping_id,
                            )
                        )
            elif section.row_kind_code == "group":
                issues.append(
                    IasIncomeStatementValidationIssueDTO(
                        issue_code="missing_subsection",
                        severity_code="error",
                        title="Subsection required",
                        message=(
                            f"Section {section.section_label} requires a subsection selection."
                        ),
                        account_id=row.account_id,
                        account_code=row.account_code,
                        section_code=row.section_code,
                        mapping_id=row.mapping_id,
                    )
                )

            if normalize_sign_behavior_code(row.sign_behavior_code) not in {IAS_SIGN_BEHAVIOR_NORMAL, IAS_SIGN_BEHAVIOR_INVERTED}:
                issues.append(
                    IasIncomeStatementValidationIssueDTO(
                        issue_code="invalid_sign_behavior",
                        severity_code="error",
                        title="Invalid sign behavior",
                        message=(
                            f"Mapping {row.mapping_id} has an unsupported sign behavior value."
                        ),
                        account_id=row.account_id,
                        account_code=row.account_code,
                        mapping_id=row.mapping_id,
                    )
                )

            if account is None or account.mapped_mapping_id is None:
                continue

            if account.mapped_mapping_id == row.mapping_id and row.is_active:
                if not account.is_active:
                    issues.append(
                        IasIncomeStatementValidationIssueDTO(
                            issue_code="inactive_account",
                            severity_code="warning",
                            title="Inactive account mapped",
                            message=(
                                f"Account {account.account_code} is inactive but remains mapped."
                            ),
                            account_id=row.account_id,
                            account_code=row.account_code,
                            mapping_id=row.mapping_id,
                        )
                    )
                if not account.allow_manual_posting:
                    issues.append(
                        IasIncomeStatementValidationIssueDTO(
                            issue_code="control_account_mapped",
                            severity_code="warning",
                            title="Control-only account mapped",
                            message=(
                                f"Account {account.account_code} is control-only and should not "
                                "usually be mapped into active IAS reporting."
                            ),
                            account_id=row.account_id,
                            account_code=row.account_code,
                            mapping_id=row.mapping_id,
                        )
                    )

        for account in account_options:
            if not account.is_active:
                continue
            if not is_relevant_income_statement_account(
                account_class_code=account.account_class_code,
                account_type_section_code=account.account_type_section_code,
                account_code=account.account_code,
            ):
                continue
            if account.mapped_mapping_id is not None and account.mapped_is_active is True:
                continue
            issues.append(
                IasIncomeStatementValidationIssueDTO(
                    issue_code="unmapped_relevant_account",
                    severity_code="warning",
                    title="Unmapped relevant account",
                    message=(
                        f"Account {account.account_code} is relevant to IAS reporting but is not mapped."
                    ),
                    account_id=account.account_id,
                    account_code=account.account_code,
                )
            )

        return tuple(issues)

    def _validate_section_target(
        self,
        section_map: dict[str, IasIncomeStatementSectionDTO],
        section_code: str,
        subsection_code: str | None,
    ) -> None:
        section = section_map.get(section_code)
        if section is None:
            raise ValidationError(f"Section {section_code} is not defined.")
        if section.row_kind_code == "formula":
            raise ValidationError("Formula rows cannot receive account mappings.")
        if section.row_kind_code == "group" and not subsection_code:
            raise ValidationError("A subsection is required for Operating Expenses mappings.")
        if subsection_code is not None:
            subsection = section_map.get(subsection_code)
            if subsection is None:
                raise ValidationError(f"Subsection {subsection_code} is not defined.")
            if subsection.parent_section_code != section_code:
                raise ValidationError(
                    f"Subsection {subsection.section_label} does not belong under {section.section_label}."
                )
            if subsection.row_kind_code == "formula":
                raise ValidationError("Formula rows cannot receive account mappings.")
            if not subsection.is_mapping_target:
                raise ValidationError("Selected subsection cannot receive account mappings.")

    def _validate_account_row(self, account_row: IasCompanyAccountRow) -> None:
        if not account_row.is_active:
            raise ValidationError(
                f"Account {account_row.account_code} is inactive and cannot be mapped through the active statement editor."
            )
        if not account_row.allow_manual_posting:
            raise ValidationError(
                f"Account {account_row.account_code} is control-only and cannot be mapped through the active statement editor."
            )

    def _mapping_lookup_by_account_id(self, mapping_rows: list[IasMappingRow]) -> dict[int, IasMappingRow]:
        mapping_lookup: dict[int, IasMappingRow] = {}
        for row in sorted(
            mapping_rows,
            key=lambda value: (not value.is_active, value.display_order, value.mapping_id),
        ):
            if row.account_id in mapping_lookup:
                continue
            mapping_lookup[row.account_id] = row
        return mapping_lookup

    def _to_mapping_dto(
        self,
        row: IasMappingRow,
        section_map: dict[str, IasIncomeStatementSectionDTO],
    ) -> IasIncomeStatementMappingDTO:
        section = section_map.get(row.section_code)
        subsection = section_map.get(row.subsection_code) if row.subsection_code else None
        normal_balance = row.normal_balance or "DEBIT"
        return IasIncomeStatementMappingDTO(
            id=row.mapping_id,
            company_id=row.company_id,
            statement_profile_code=row.statement_profile_code,
            section_code=row.section_code,
            section_label=section.section_label if section else row.section_label or row.section_code,
            subsection_code=row.subsection_code,
            subsection_label=subsection.section_label if subsection else row.subsection_label,
            account_id=row.account_id,
            account_code=row.account_code or "",
            account_name=row.account_name or "",
            account_class_code=row.account_class_code,
            account_type_code=row.account_type_code,
            account_type_section_code=row.account_type_section_code,
            normal_balance=normal_balance,
            allow_manual_posting=bool(row.allow_manual_posting) if row.allow_manual_posting is not None else False,
            is_control_account=bool(row.is_control_account) if row.is_control_account is not None else False,
            account_is_active=bool(row.account_is_active) if row.account_is_active is not None else False,
            sign_behavior_code=normalize_sign_behavior_code(row.sign_behavior_code),
            default_sign_behavior_code=suggest_default_sign_behavior(
                normal_balance=normal_balance,
                account_type_section_code=row.account_type_section_code,
            ),
            display_order=row.display_order,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
            created_by_user_id=row.created_by_user_id,
            updated_by_user_id=row.updated_by_user_id,
        )

    def _new_mapping(
        self,
        *,
        company_id: int,
        account_id: int,
        section_code: str,
        subsection_code: str | None,
        sign_behavior_code: str,
        display_order: int,
        is_active: bool,
    ) -> object:
        from seeker_accounting.modules.reporting.models.ias_income_statement_mapping import (
            IasIncomeStatementMapping,
        )

        return IasIncomeStatementMapping(
            company_id=company_id,
            statement_profile_code=IAS_INCOME_STATEMENT_PROFILE_CODE,
            section_code=section_code,
            subsection_code=subsection_code,
            account_id=account_id,
            sign_behavior_code=sign_behavior_code,
            display_order=display_order,
            is_active=is_active,
            created_by_user_id=self._app_context.current_user_id,
            updated_by_user_id=self._app_context.current_user_id,
        )

    def _normalize_account_ids(self, account_ids: tuple[int, ...]) -> tuple[int, ...]:
        normalized: list[int] = []
        seen: set[int] = set()
        for account_id in account_ids:
            if not isinstance(account_id, int) or account_id <= 0:
                raise ValidationError("Account identifiers must be positive integers.")
            if account_id in seen:
                raise ValidationError("Duplicate account selections were provided.")
            seen.add(account_id)
            normalized.append(account_id)
        if not normalized:
            raise ValidationError("Select at least one account.")
        return tuple(normalized)

    def _normalize_optional_code(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    def _require_code(self, value: str, label: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _normalize_display_order(self, value: int) -> int:
        if not isinstance(value, int) or value <= 0:
            raise ValidationError("Display order must be a positive integer.")
        return value
