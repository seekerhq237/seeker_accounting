from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.dto.chart_import_dto import (
    ChartSeedResultDTO,
    ImportChartTemplateCommand,
)
from seeker_accounting.modules.accounting.chart_of_accounts.seeds.global_chart_reference_seed import (
    ensure_global_chart_reference_seed,
)
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_template_import_service import (
    ChartTemplateImportService,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_profile import (
    BUILT_IN_TEMPLATE_CODE_OHADA,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_class_repository import (
    AccountClassRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_type_repository import (
    AccountTypeRepository,
)

AccountClassRepositoryFactory = Callable[[Session], AccountClassRepository]
AccountTypeRepositoryFactory = Callable[[Session], AccountTypeRepository]


class ChartSeedService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        account_class_repository_factory: AccountClassRepositoryFactory,
        account_type_repository_factory: AccountTypeRepositoryFactory,
        chart_template_import_service: ChartTemplateImportService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._account_class_repository_factory = account_class_repository_factory
        self._account_type_repository_factory = account_type_repository_factory
        self._chart_template_import_service = chart_template_import_service

    def ensure_global_chart_reference_seed(self) -> tuple[int, int]:
        with self._unit_of_work_factory() as uow:
            session = uow.session
            if session is None:
                raise RuntimeError("Unit of work has no active session.")

            inserted_account_classes, inserted_account_types = ensure_global_chart_reference_seed(
                self._account_class_repository_factory(session),
                self._account_type_repository_factory(session),
            )
            if inserted_account_classes or inserted_account_types:
                uow.commit()
            return inserted_account_classes, inserted_account_types

    def seed_built_in_chart(
        self,
        company_id: int,
        template_code: str = BUILT_IN_TEMPLATE_CODE_OHADA,
    ) -> ChartSeedResultDTO:
        inserted_account_classes, inserted_account_types = self.ensure_global_chart_reference_seed()
        import_result = self._chart_template_import_service.import_add_missing(
            company_id,
            ImportChartTemplateCommand(
                source_kind="built_in",
                template_code=template_code,
                add_missing_only=True,
            ),
        )

        messages: list[str] = []
        if inserted_account_classes or inserted_account_types:
            messages.append("Global chart references were initialized before company chart seeding.")
        if import_result.imported_count == 0 and import_result.skipped_existing_count > 0:
            messages.append(
                "The target company already had matching chart rows for this template, so only missing rows were considered."
            )
        messages.extend(import_result.warnings)

        return ChartSeedResultDTO(
            company_id=company_id,
            template_code=template_code,
            total_template_rows=import_result.normalized_row_count,
            imported_count=import_result.imported_count,
            skipped_existing_count=import_result.skipped_existing_count,
            duplicate_source_count=import_result.duplicate_source_count,
            invalid_row_count=import_result.invalid_row_count,
            conflict_count=import_result.conflict_count,
            messages=tuple(messages),
        )
