from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.dto.chart_import_dto import (
    ChartImportPreviewDTO,
    ChartImportResultDTO,
    ChartTemplateProfileDTO,
    ImportChartTemplateCommand,
)
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.chart_of_accounts.seeds.global_chart_reference_seed import (
    ACCOUNT_CLASS_SEEDS,
    ACCOUNT_TYPE_SEEDS,
    ensure_global_chart_reference_seed,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_loader import (
    ChartTemplateLoader,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_profile import (
    BUILT_IN_TEMPLATE_CODE_OHADA,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_row import (
    ChartTemplateRow,
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
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

AccountRepositoryFactory = Callable[[Session], AccountRepository]
AccountClassRepositoryFactory = Callable[[Session], AccountClassRepository]
AccountTypeRepositoryFactory = Callable[[Session], AccountTypeRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


@dataclass(frozen=True, slots=True)
class _ResolvedChartSource:
    source_label: str
    template_code: str | None
    total_source_rows: int
    normalized_rows: tuple[ChartTemplateRow, ...]
    duplicate_source_count: int
    invalid_row_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class _ImportEvaluation:
    importable_rows: tuple[ChartTemplateRow, ...]
    existing_accounts_by_code: dict[str, Account]
    skipped_existing_count: int
    invalid_row_count: int
    conflict_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ChartTemplateImportService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        account_class_repository_factory: AccountClassRepositoryFactory,
        account_type_repository_factory: AccountTypeRepositoryFactory,
        template_loader: ChartTemplateLoader | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._account_repository_factory = account_repository_factory
        self._account_class_repository_factory = account_class_repository_factory
        self._account_type_repository_factory = account_type_repository_factory
        self._template_loader = template_loader or ChartTemplateLoader()

    def list_built_in_templates(self) -> list[ChartTemplateProfileDTO]:
        return [
            ChartTemplateProfileDTO(
                template_code=profile.template_code,
                display_name=profile.display_name,
                version=profile.version,
                description=profile.description,
                source_name=profile.source_name,
                source_format=profile.source_format,
                row_count=profile.row_count,
                notes=profile.notes,
            )
            for profile in self._template_loader.list_built_in_profiles()
        ]

    def preview_import(self, company_id: int, command: ImportChartTemplateCommand) -> ChartImportPreviewDTO:
        self._require_add_missing_only(command)
        resolved_source = self._resolve_chart_source(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            evaluation = self._evaluate_import(
                session=uow.session,
                company_id=company_id,
                normalized_rows=resolved_source.normalized_rows,
            )

        return ChartImportPreviewDTO(
            source_label=resolved_source.source_label,
            template_code=resolved_source.template_code,
            add_missing_only=True,
            total_source_rows=resolved_source.total_source_rows,
            normalized_row_count=len(resolved_source.normalized_rows),
            importable_count=len(evaluation.importable_rows),
            skipped_existing_count=evaluation.skipped_existing_count,
            duplicate_source_count=resolved_source.duplicate_source_count,
            invalid_row_count=resolved_source.invalid_row_count + evaluation.invalid_row_count,
            conflict_count=evaluation.conflict_count,
            warnings=resolved_source.warnings + evaluation.warnings,
        )

    def import_add_missing(self, company_id: int, command: ImportChartTemplateCommand) -> ChartImportResultDTO:
        self._require_add_missing_only(command)
        resolved_source = self._resolve_chart_source(command)

        with self._unit_of_work_factory() as uow:
            session = uow.session
            self._require_company_exists(session, company_id)

            account_class_repository = self._require_account_class_repository(session)
            account_type_repository = self._require_account_type_repository(session)
            ensure_global_chart_reference_seed(account_class_repository, account_type_repository)
            session.flush()

            evaluation = self._evaluate_import(
                session=session,
                company_id=company_id,
                normalized_rows=resolved_source.normalized_rows,
            )
            imported_count = self._import_rows(
                session=session,
                company_id=company_id,
                rows=evaluation.importable_rows,
                existing_accounts_by_code=dict(evaluation.existing_accounts_by_code),
            )

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Chart template data could not be imported.") from exc

        return ChartImportResultDTO(
            source_label=resolved_source.source_label,
            template_code=resolved_source.template_code,
            add_missing_only=True,
            total_source_rows=resolved_source.total_source_rows,
            normalized_row_count=len(resolved_source.normalized_rows),
            imported_count=imported_count,
            skipped_existing_count=evaluation.skipped_existing_count,
            duplicate_source_count=resolved_source.duplicate_source_count,
            invalid_row_count=resolved_source.invalid_row_count + evaluation.invalid_row_count,
            conflict_count=evaluation.conflict_count,
            warnings=resolved_source.warnings + evaluation.warnings,
        )

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

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

    def _require_add_missing_only(self, command: ImportChartTemplateCommand) -> None:
        if not command.add_missing_only:
            raise ValidationError("Only add-missing-only chart import mode is supported in this slice.")

    def _resolve_chart_source(self, command: ImportChartTemplateCommand) -> _ResolvedChartSource:
        source_kind = command.source_kind.strip().lower()
        if source_kind == "built_in":
            template_code = (command.template_code or BUILT_IN_TEMPLATE_CODE_OHADA).strip() or BUILT_IN_TEMPLATE_CODE_OHADA
            profile = self._template_loader.load_built_in_profile(template_code)
            rows = self._template_loader.load_built_in_rows(template_code)
            return _ResolvedChartSource(
                source_label=profile.display_name,
                template_code=profile.template_code,
                total_source_rows=profile.row_count,
                normalized_rows=tuple(rows),
                duplicate_source_count=0,
                invalid_row_count=0,
                warnings=profile.notes,
            )

        if source_kind not in {"csv", "xlsx"}:
            raise ValidationError("Chart import source must be built_in, csv, or xlsx.")

        file_path = self._require_file_path(command.file_path)
        normalization_result = self._template_loader.load_and_normalize_file(
            file_path,
            template_code=self._derive_external_template_code(file_path),
        )
        return _ResolvedChartSource(
            source_label=Path(file_path).name,
            template_code=normalization_result.template_code,
            total_source_rows=normalization_result.total_source_rows,
            normalized_rows=normalization_result.normalized_rows,
            duplicate_source_count=normalization_result.duplicate_source_count,
            invalid_row_count=normalization_result.invalid_row_count,
            warnings=normalization_result.warnings,
        )

    def _require_file_path(self, file_path: str | None) -> str:
        normalized_path = (file_path or "").strip()
        if not normalized_path:
            raise ValidationError("A chart template file path is required.")
        path = Path(normalized_path)
        if not path.exists():
            raise ValidationError(f"Chart template file was not found: {normalized_path}")
        return str(path)

    def _derive_external_template_code(self, file_path: str) -> str:
        file_stem = Path(file_path).stem.strip().lower().replace(" ", "_")
        return file_stem or "external_import"

    def _evaluate_import(
        self,
        *,
        session: Session | None,
        company_id: int,
        normalized_rows: tuple[ChartTemplateRow, ...],
    ) -> _ImportEvaluation:
        account_repository = self._require_account_repository(session)
        account_class_repository = self._require_account_class_repository(session)
        account_type_repository = self._require_account_type_repository(session)

        existing_accounts = account_repository.list_by_company(company_id, active_only=False)
        existing_accounts_by_code = {account.account_code: account for account in existing_accounts}
        existing_accounts_by_id = {account.id: account for account in existing_accounts}
        existing_parent_code_by_account_id = {
            account.id: (
                existing_accounts_by_id[account.parent_account_id].account_code
                if account.parent_account_id in existing_accounts_by_id
                else None
            )
            for account in existing_accounts
        }

        valid_account_class_codes = {
            row.code
            for row in account_class_repository.list_all(active_only=False)
        } | {seed.code for seed in ACCOUNT_CLASS_SEEDS}
        valid_account_type_codes = {
            row.code
            for row in account_type_repository.list_all(active_only=False)
        } | {seed.code for seed in ACCOUNT_TYPE_SEEDS}

        source_rows_by_code = {row.account_code: row for row in normalized_rows}
        candidate_rows: list[ChartTemplateRow] = []
        warnings: list[str] = []
        skipped_existing_count = 0
        invalid_row_count = 0
        conflict_count = 0

        for row in normalized_rows:
            row_error = self._validate_template_row(
                row=row,
                source_rows_by_code=source_rows_by_code,
                existing_accounts_by_code=existing_accounts_by_code,
                valid_account_class_codes=valid_account_class_codes,
                valid_account_type_codes=valid_account_type_codes,
            )
            if row_error is not None:
                invalid_row_count += 1
                warnings.append(row_error)
                continue

            existing_account = existing_accounts_by_code.get(row.account_code)
            if existing_account is None:
                candidate_rows.append(row)
                continue

            if self._existing_account_matches_template(
                account=existing_account,
                row=row,
                account_class_repository=account_class_repository,
                account_type_repository=account_type_repository,
                existing_parent_code_by_account_id=existing_parent_code_by_account_id,
            ):
                skipped_existing_count += 1
            else:
                conflict_count += 1
                warnings.append(
                    f"Skipped existing account {row.account_code}: the current company chart uses a different definition."
                )

        importable_rows: list[ChartTemplateRow] = []
        available_parent_codes = set(existing_accounts_by_code)
        for row in sorted(candidate_rows, key=lambda item: (item.level_no, item.account_code)):
            if row.parent_account_code is not None and row.parent_account_code not in available_parent_codes:
                invalid_row_count += 1
                warnings.append(
                    f"Skipped source account {row.account_code}: parent account {row.parent_account_code} is not available in the target chart."
                )
                continue
            importable_rows.append(row)
            available_parent_codes.add(row.account_code)

        return _ImportEvaluation(
            importable_rows=tuple(importable_rows),
            existing_accounts_by_code=existing_accounts_by_code,
            skipped_existing_count=skipped_existing_count,
            invalid_row_count=invalid_row_count,
            conflict_count=conflict_count,
            warnings=tuple(warnings),
        )

    def _validate_template_row(
        self,
        *,
        row: ChartTemplateRow,
        source_rows_by_code: dict[str, ChartTemplateRow],
        existing_accounts_by_code: dict[str, Account],
        valid_account_class_codes: set[str],
        valid_account_type_codes: set[str],
    ) -> str | None:
        if not row.account_code:
            return "Skipped source row with a blank account code."
        if not row.account_name:
            return f"Skipped source account {row.account_code}: account name is blank."
        if row.class_code not in valid_account_class_codes:
            return f"Skipped source account {row.account_code}: account class {row.class_code} is not recognized."
        if row.account_type_code not in valid_account_type_codes:
            return (
                f"Skipped source account {row.account_code}: account type {row.account_type_code} is not recognized."
            )
        if row.normal_balance not in {"DEBIT", "CREDIT"}:
            return f"Skipped source account {row.account_code}: normal balance must be DEBIT or CREDIT."
        if row.parent_account_code == row.account_code:
            return f"Skipped source account {row.account_code}: parent account cannot equal the account code."
        if row.parent_account_code is not None:
            parent_exists = (
                row.parent_account_code in source_rows_by_code
                or row.parent_account_code in existing_accounts_by_code
            )
            if not parent_exists:
                return (
                    f"Skipped source account {row.account_code}: parent account {row.parent_account_code} "
                    "does not exist in the source or target chart."
                )
        return None

    def _existing_account_matches_template(
        self,
        *,
        account: Account,
        row: ChartTemplateRow,
        account_class_repository: AccountClassRepository,
        account_type_repository: AccountTypeRepository,
        existing_parent_code_by_account_id: dict[int, str | None],
    ) -> bool:
        account_class = account_class_repository.get_by_id(account.account_class_id)
        account_type = account_type_repository.get_by_id(account.account_type_id)
        if account_class is None or account_type is None:
            return False

        return (
            account.account_name == row.account_name
            and account_class.code == row.class_code
            and account_type.code == row.account_type_code
            and existing_parent_code_by_account_id.get(account.id) == row.parent_account_code
            and account.normal_balance == row.normal_balance
            and account.allow_manual_posting == row.allow_manual_posting
            and account.is_control_account == row.is_control_account_default
            and account.is_active == row.is_active_default
        )

    def _import_rows(
        self,
        *,
        session: Session | None,
        company_id: int,
        rows: tuple[ChartTemplateRow, ...],
        existing_accounts_by_code: dict[str, Account],
    ) -> int:
        account_repository = self._require_account_repository(session)
        account_class_repository = self._require_account_class_repository(session)
        account_type_repository = self._require_account_type_repository(session)

        account_classes_by_code = {
            row.code: row
            for row in account_class_repository.list_all(active_only=False)
        }
        account_types_by_code = {
            row.code: row
            for row in account_type_repository.list_all(active_only=False)
        }

        imported_count = 0
        for row in sorted(rows, key=lambda item: (item.level_no, item.account_code)):
            if row.account_code in existing_accounts_by_code:
                continue

            parent_account_id: int | None = None
            if row.parent_account_code is not None:
                parent_account = existing_accounts_by_code.get(row.parent_account_code)
                if parent_account is None:
                    raise ValidationError(
                        f"Chart template import could not resolve parent account {row.parent_account_code}."
                    )
                parent_account_id = parent_account.id

            account_class = account_classes_by_code.get(row.class_code)
            account_type = account_types_by_code.get(row.account_type_code)
            if account_class is None or account_type is None:
                raise ValidationError(
                    f"Chart template import could not resolve global references for account {row.account_code}."
                )

            account = Account(
                company_id=company_id,
                account_code=row.account_code,
                account_name=row.account_name,
                account_class_id=account_class.id,
                account_type_id=account_type.id,
                parent_account_id=parent_account_id,
                normal_balance=row.normal_balance,
                allow_manual_posting=row.allow_manual_posting,
                is_control_account=row.is_control_account_default,
                notes=row.notes,
                is_active=row.is_active_default,
            )
            account_repository.add(account)
            session.flush()
            existing_accounts_by_code[account.account_code] = account
            imported_count += 1

        return imported_count
