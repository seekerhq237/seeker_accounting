from __future__ import annotations

from seeker_accounting.modules.accounting.chart_of_accounts.dto.chart_import_dto import (
    ChartSeedResultDTO,
)
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_seed_service import (
    ChartSeedService,
)


class CompanySeedService:
    def __init__(self, chart_seed_service: ChartSeedService) -> None:
        self._chart_seed_service = chart_seed_service

    def initialize_new_company(
        self,
        company_id: int,
        *,
        seed_built_in_chart: bool = False,
        template_code: str = "ohada_syscohada_v1",
    ) -> ChartSeedResultDTO | None:
        if not seed_built_in_chart:
            return None
        return self._chart_seed_service.seed_built_in_chart(company_id, template_code=template_code)

    def seed_built_in_chart(
        self,
        company_id: int,
        template_code: str = "ohada_syscohada_v1",
    ) -> ChartSeedResultDTO:
        return self._chart_seed_service.seed_built_in_chart(company_id, template_code=template_code)
