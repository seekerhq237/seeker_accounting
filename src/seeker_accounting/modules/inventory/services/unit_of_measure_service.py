from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_reference_commands import (
    CreateUnitOfMeasureCommand,
    UpdateUnitOfMeasureCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_dto import UnitOfMeasureDTO
from seeker_accounting.modules.inventory.models.unit_of_measure import UnitOfMeasure
from seeker_accounting.modules.inventory.repositories.uom_category_repository import UomCategoryRepository
from seeker_accounting.modules.inventory.repositories.unit_of_measure_repository import UnitOfMeasureRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
UnitOfMeasureRepositoryFactory = Callable[[Session], UnitOfMeasureRepository]
UomCategoryRepositoryFactory = Callable[[Session], UomCategoryRepository]


class UnitOfMeasureService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        unit_of_measure_repository_factory: UnitOfMeasureRepositoryFactory,
        uom_category_repository_factory: UomCategoryRepositoryFactory | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._uom_repository_factory = unit_of_measure_repository_factory
        self._category_repository_factory = uom_category_repository_factory
        self._audit_service = audit_service

    def list_units_of_measure(self, company_id: int, active_only: bool = False) -> list[UnitOfMeasureDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._uom_repository_factory(uow.session)
            return [self._to_dto(r) for r in repo.list_by_company(company_id, active_only=active_only)]

    def get_unit_of_measure(self, company_id: int, uom_id: int) -> UnitOfMeasureDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._uom_repository_factory(uow.session)
            uom = repo.get_by_id(company_id, uom_id)
            if uom is None:
                raise NotFoundError(f"Unit of measure with id {uom_id} was not found.")
            return self._to_dto(uom)

    def create_unit_of_measure(self, company_id: int, command: CreateUnitOfMeasureCommand) -> UnitOfMeasureDTO:
        self._validate_fields(command.code, command.name)
        self._validate_ratio(command.ratio_to_base)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._uom_repository_factory(uow.session)
            if repo.code_exists(company_id, command.code.strip().upper()):
                raise ConflictError(f"Unit of measure code '{command.code}' already exists for this company.")
            self._validate_category(uow.session, company_id, command.category_id)
            uom = UnitOfMeasure(
                company_id=company_id,
                code=command.code.strip().upper(),
                name=command.name.strip(),
                description=command.description,
                category_id=command.category_id,
                ratio_to_base=command.ratio_to_base,
            )
            repo.add(uom)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Unit of measure could not be saved.") from exc
            from seeker_accounting.modules.audit.event_type_catalog import UNIT_OF_MEASURE_CREATED
            self._record_audit(company_id, UNIT_OF_MEASURE_CREATED, "UnitOfMeasure", uom.id, "Created unit of measure")
            return self._to_dto(uom)

    def update_unit_of_measure(
        self, company_id: int, uom_id: int, command: UpdateUnitOfMeasureCommand
    ) -> UnitOfMeasureDTO:
        self._validate_fields(command.code, command.name)
        self._validate_ratio(command.ratio_to_base)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._uom_repository_factory(uow.session)
            uom = repo.get_by_id(company_id, uom_id)
            if uom is None:
                raise NotFoundError(f"Unit of measure with id {uom_id} was not found.")
            new_code = command.code.strip().upper()
            if new_code != uom.code and repo.code_exists(company_id, new_code, exclude_id=uom_id):
                raise ConflictError(f"Unit of measure code '{command.code}' already exists for this company.")
            self._validate_category(uow.session, company_id, command.category_id)
            uom.code = new_code
            uom.name = command.name.strip()
            uom.description = command.description
            uom.is_active = command.is_active
            uom.category_id = command.category_id
            uom.ratio_to_base = command.ratio_to_base
            repo.save(uom)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Unit of measure could not be saved.") from exc
            from seeker_accounting.modules.audit.event_type_catalog import UNIT_OF_MEASURE_UPDATED
            self._record_audit(company_id, UNIT_OF_MEASURE_UPDATED, "UnitOfMeasure", uom.id, "Updated unit of measure")
            return self._to_dto(uom)

    def deactivate_unit_of_measure(self, company_id: int, uom_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._uom_repository_factory(uow.session)
            uom = repo.get_by_id(company_id, uom_id)
            if uom is None:
                raise NotFoundError(f"Unit of measure with id {uom_id} was not found.")
            uom.is_active = False
            repo.save(uom)
            uow.commit()

    def _validate_fields(self, code: str, name: str) -> None:
        if not code or not code.strip():
            raise ValidationError("Code is required.")
        if not name or not name.strip():
            raise ValidationError("Name is required.")

    def _validate_ratio(self, ratio: Decimal) -> None:
        if ratio <= 0:
            raise ValidationError("Ratio to base must be greater than zero.")

    def _validate_category(self, session: Session, company_id: int, category_id: int | None) -> None:
        if category_id is None:
            return
        if self._category_repository_factory is None:
            return
        cat_repo = self._category_repository_factory(session)
        cat = cat_repo.get_by_id(company_id, category_id)
        if cat is None:
            raise ValidationError("Selected UoM category does not exist.")
        if not cat.is_active:
            raise ValidationError("Selected UoM category is not active.")

    def convert_quantity(
        self,
        company_id: int,
        from_uom_id: int,
        to_uom_id: int,
        quantity: Decimal,
    ) -> Decimal:
        """Convert quantity between two UoMs in the same category."""
        if from_uom_id == to_uom_id:
            return quantity
        with self._unit_of_work_factory() as uow:
            repo = self._uom_repository_factory(uow.session)
            from_uom = repo.get_by_id(company_id, from_uom_id)
            to_uom = repo.get_by_id(company_id, to_uom_id)
            if from_uom is None or to_uom is None:
                raise NotFoundError("One or both units of measure were not found.")
            if from_uom.category_id is None or to_uom.category_id is None:
                raise ValidationError("Both units must belong to a category for conversion.")
            if from_uom.category_id != to_uom.category_id:
                raise ValidationError("Units must belong to the same category for conversion.")
            if to_uom.ratio_to_base == 0:
                raise ValidationError("Target unit ratio to base must not be zero.")
            return (quantity * from_uom.ratio_to_base / to_uom.ratio_to_base).quantize(
                Decimal("0.0001")
            )

    def _require_company(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _to_dto(self, uom: UnitOfMeasure) -> UnitOfMeasureDTO:
        cat = uom.category
        return UnitOfMeasureDTO(
            id=uom.id,
            company_id=uom.company_id,
            code=uom.code,
            name=uom.name,
            description=uom.description,
            is_active=uom.is_active,
            created_at=uom.created_at,
            updated_at=uom.updated_at,
            category_id=uom.category_id,
            category_code=cat.code if cat else None,
            category_name=cat.name if cat else None,
            ratio_to_base=uom.ratio_to_base,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_INVENTORY
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_INVENTORY,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
