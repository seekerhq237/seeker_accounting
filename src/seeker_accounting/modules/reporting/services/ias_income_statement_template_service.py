from __future__ import annotations

from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.ias_income_statement_mapping_dto import (
    IasIncomeStatementSectionDTO,
)
from seeker_accounting.modules.reporting.dto.ias_income_statement_template_dto import (
    IasIncomeStatementTemplateDTO,
)
from seeker_accounting.modules.reporting.models.ias_income_statement_preference import (
    IasIncomeStatementPreference,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_preference_repository import (
    IasIncomeStatementPreferenceRepository,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_repository import (
    IasIncomeStatementRepository,
    IasSectionRow,
    IasTemplateRow,
)
from seeker_accounting.modules.reporting.specs.ias_income_statement_spec import (
    IAS_INCOME_STATEMENT_PROFILE_CODE,
    IAS_SECTION_SPEC_BY_CODE,
    IAS_SECTION_SPECS,
    IAS_TEMPLATE_SPECS,
)
from seeker_accounting.platform.exceptions import ValidationError

IasIncomeStatementRepositoryFactory = Callable[[Session], IasIncomeStatementRepository]
IasIncomeStatementPreferenceRepositoryFactory = Callable[[Session], IasIncomeStatementPreferenceRepository]


class IasIncomeStatementTemplateService:
    """Presentation metadata and locked IAS section metadata."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ias_income_statement_repository_factory: IasIncomeStatementRepositoryFactory,
        ias_income_statement_preference_repository_factory: IasIncomeStatementPreferenceRepositoryFactory,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._ias_income_statement_repository_factory = ias_income_statement_repository_factory
        self._ias_income_statement_preference_repository_factory = ias_income_statement_preference_repository_factory
        self._permission_service = permission_service

    def list_templates(self) -> tuple[IasIncomeStatementTemplateDTO, ...]:
        with self._unit_of_work_factory() as uow:
            repo = self._ias_income_statement_repository_factory(uow.session)
            rows = repo.list_templates(IAS_INCOME_STATEMENT_PROFILE_CODE, active_only=True)
        if rows and {row.template_code for row in rows} == {spec.template_code for spec in IAS_TEMPLATE_SPECS}:
            return tuple(self._to_template_dto(row) for row in rows)
        return tuple(self._to_template_dto_from_spec(spec, template_id=index + 1) for index, spec in enumerate(IAS_TEMPLATE_SPECS))

    def get_template(self, template_code: str | None) -> IasIncomeStatementTemplateDTO:
        normalized = (template_code or "").strip().lower()
        templates = self.list_templates()
        for template in templates:
            if template.template_code == normalized:
                return template
        if templates:
            return templates[0]
        raise RuntimeError("No IAS income statement templates are available.")

    def list_sections(self) -> tuple[IasIncomeStatementSectionDTO, ...]:
        with self._unit_of_work_factory() as uow:
            repo = self._ias_income_statement_repository_factory(uow.session)
            rows = repo.list_sections(IAS_INCOME_STATEMENT_PROFILE_CODE, active_only=True)
        if rows and {row.section_code for row in rows} == {spec.section_code for spec in IAS_SECTION_SPECS}:
            return self._to_section_dtos(rows)

        return self._to_section_dtos_from_specs()

    def get_section(self, section_code: str) -> IasIncomeStatementSectionDTO:
        normalized = (section_code or "").strip().upper()
        for section in self.list_sections():
            if section.section_code == normalized:
                return section
        raise RuntimeError(f"IAS section {normalized} is not defined.")

    def get_section_map(self) -> dict[str, IasIncomeStatementSectionDTO]:
        return {section.section_code: section for section in self.list_sections()}

    def get_company_template_code(self, company_id: int) -> str:
        default_code = self._default_template_code()
        available_codes = self._available_template_codes()

        with self._unit_of_work_factory() as uow:
            repo = self._ias_income_statement_preference_repository_factory(uow.session)
            preference = repo.get_by_company_id(company_id)
            if preference is None:
                preference = IasIncomeStatementPreference(
                    company_id=company_id,
                    template_code=default_code,
                )
                repo.add(preference)
                self._commit_preference(uow)
                return default_code

            normalized = self._normalize_template_code(preference.template_code) or default_code
            if normalized not in available_codes:
                normalized = default_code
            if normalized != preference.template_code:
                preference.template_code = normalized
                repo.save(preference)
                self._commit_preference(uow)
            return normalized

    def set_company_template_code(self, company_id: int, template_code: str) -> str:
        if self._permission_service is not None:
            self._permission_service.require_permission("reports.ias_templates.manage")
        normalized = self._normalize_template_code(template_code)
        available_codes = self._available_template_codes()
        if normalized not in available_codes:
            raise ValidationError(f"IAS template {normalized} is not available.")

        with self._unit_of_work_factory() as uow:
            repo = self._ias_income_statement_preference_repository_factory(uow.session)
            preference = repo.get_by_company_id(company_id)
            if preference is None:
                preference = IasIncomeStatementPreference(
                    company_id=company_id,
                    template_code=normalized,
                )
                repo.add(preference)
            else:
                preference.template_code = normalized
                repo.save(preference)
            self._commit_preference(uow)
        return normalized

    def _to_template_dto(self, row: IasTemplateRow) -> IasIncomeStatementTemplateDTO:
        return IasIncomeStatementTemplateDTO(
            id=row.id,
            statement_profile_code=row.statement_profile_code,
            template_code=row.template_code,
            template_title=row.template_title,
            description=row.description,
            standard_note=row.standard_note,
            display_order=row.display_order,
            row_height=row.row_height,
            section_background=row.section_background,
            subtotal_background=row.subtotal_background,
            statement_background=row.statement_background,
            amount_font_size=row.amount_font_size,
            label_font_size=row.label_font_size,
            is_active=row.is_active,
        )

    def _to_template_dto_from_spec(
        self,
        spec,
        *,
        template_id: int,
    ) -> IasIncomeStatementTemplateDTO:
        return IasIncomeStatementTemplateDTO(
            id=template_id,
            statement_profile_code=IAS_INCOME_STATEMENT_PROFILE_CODE,
            template_code=spec.template_code,
            template_title=spec.template_title,
            description=spec.description,
            standard_note=spec.standard_note,
            display_order=spec.display_order,
            row_height=spec.row_height,
            section_background=spec.section_background,
            subtotal_background=spec.subtotal_background,
            statement_background=spec.statement_background,
            amount_font_size=spec.amount_font_size,
            label_font_size=spec.label_font_size,
            is_active=True,
        )

    def _to_section_dtos(self, rows: list[IasSectionRow]) -> tuple[IasIncomeStatementSectionDTO, ...]:
        row_lookup = {row.section_code: row for row in rows}

        def build_path(section_code: str) -> tuple[str, int]:
            row = row_lookup[section_code]
            parent_code = row.parent_section_code
            if parent_code and parent_code in row_lookup:
                parent_path, parent_depth = build_path(parent_code)
                return f"{parent_path} / {row.section_label}", parent_depth + 1
            return row.section_label, 0

        dtos: list[IasIncomeStatementSectionDTO] = []
        for row in sorted(rows, key=lambda value: (value.display_order, value.section_code, value.id)):
            display_path, indent_level = build_path(row.section_code)
            spec = IAS_SECTION_SPEC_BY_CODE.get(row.section_code)
            dtos.append(
                IasIncomeStatementSectionDTO(
                    statement_profile_code=row.statement_profile_code,
                    section_code=row.section_code,
                    section_label=row.section_label,
                    parent_section_code=row.parent_section_code,
                    display_order=row.display_order,
                    row_kind_code=row.row_kind_code,
                    is_mapping_target=row.is_mapping_target,
                    is_formula=False if row.row_kind_code != "formula" else True,
                    display_path=display_path,
                    indent_level=indent_level,
                    aggregation_components=spec.aggregation_components if spec else (),
                    formula_components=spec.formula_components if spec else (),
                )
            )
        return tuple(dtos)

    def _to_section_dtos_from_specs(self) -> tuple[IasIncomeStatementSectionDTO, ...]:
        spec_lookup = {spec.section_code: spec for spec in IAS_SECTION_SPECS}

        def build_path(section_code: str) -> tuple[str, int]:
            spec = spec_lookup[section_code]
            parent_code = spec.parent_section_code
            if parent_code and parent_code in spec_lookup:
                parent_path, parent_depth = build_path(parent_code)
                return f"{parent_path} / {spec.section_label}", parent_depth + 1
            return spec.section_label, 0

        dtos: list[IasIncomeStatementSectionDTO] = []
        for spec in IAS_SECTION_SPECS:
            display_path, indent_level = build_path(spec.section_code)
            dtos.append(
                IasIncomeStatementSectionDTO(
                    statement_profile_code=IAS_INCOME_STATEMENT_PROFILE_CODE,
                    section_code=spec.section_code,
                    section_label=spec.section_label,
                    parent_section_code=spec.parent_section_code,
                    display_order=spec.display_order,
                    row_kind_code=spec.row_kind_code,
                    is_mapping_target=spec.is_mapping_target,
                    is_formula=spec.is_formula,
                    display_path=display_path,
                    indent_level=indent_level,
                    aggregation_components=spec.aggregation_components,
                    formula_components=spec.formula_components,
                )
            )
        return tuple(sorted(dtos, key=lambda value: (value.display_order, value.section_code)))

    def _available_template_codes(self) -> set[str]:
        return {template.template_code for template in self.list_templates()}

    def _default_template_code(self) -> str:
        templates = self.list_templates()
        if not templates:
            raise RuntimeError("No IAS income statement templates are available.")
        return templates[0].template_code

    @staticmethod
    def _normalize_template_code(template_code: str | None) -> str:
        return (template_code or "").strip().lower()

    @staticmethod
    def _commit_preference(uow) -> None:
        try:
            uow.commit()
        except IntegrityError as exc:  # pragma: no cover - defensive
            raise ValidationError("IAS template preference could not be saved.") from exc
