from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.contracts_projects.repositories.project_cost_code_repository import (
    ProjectCostCodeRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.project_job_repository import ProjectJobRepository
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.modules.job_costing.dto.project_commitment_commands import (
    AddProjectCommitmentLineCommand,
    ApproveProjectCommitmentCommand,
    CancelProjectCommitmentCommand,
    CloseProjectCommitmentCommand,
    CreateProjectCommitmentCommand,
    UpdateProjectCommitmentCommand,
    UpdateProjectCommitmentLineCommand,
)
from seeker_accounting.modules.job_costing.dto.project_commitment_dto import (
    ProjectCommitmentDetailDTO,
    ProjectCommitmentLineDTO,
    ProjectCommitmentListItemDTO,
)
from seeker_accounting.modules.job_costing.models.project_commitment import ProjectCommitment
from seeker_accounting.modules.job_costing.models.project_commitment_line import ProjectCommitmentLine
from seeker_accounting.modules.job_costing.repositories.project_commitment_line_repository import (
    ProjectCommitmentLineRepository,
)
from seeker_accounting.modules.job_costing.repositories.project_commitment_repository import (
    ProjectCommitmentRepository,
)
from seeker_accounting.modules.suppliers.repositories.supplier_repository import SupplierRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

ProjectCommitmentRepositoryFactory = Callable[[Session], ProjectCommitmentRepository]
ProjectCommitmentLineRepositoryFactory = Callable[[Session], ProjectCommitmentLineRepository]
ProjectRepositoryFactory = Callable[[Session], ProjectRepository]
SupplierRepositoryFactory = Callable[[Session], SupplierRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
ProjectJobRepositoryFactory = Callable[[Session], ProjectJobRepository]
ProjectCostCodeRepositoryFactory = Callable[[Session], ProjectCostCodeRepository]

_VALID_COMMITMENT_TYPES = frozenset({
    "manual_reservation",
    "subcontract",
    "materials",
    "labor",
    "expense",
    "other",
})


class ProjectCommitmentService:
    """Manage project commitments and their lines."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        commitment_repository_factory: ProjectCommitmentRepositoryFactory,
        commitment_line_repository_factory: ProjectCommitmentLineRepositoryFactory,
        project_repository_factory: ProjectRepositoryFactory,
        supplier_repository_factory: SupplierRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        project_job_repository_factory: ProjectJobRepositoryFactory,
        project_cost_code_repository_factory: ProjectCostCodeRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._commitment_repo_factory = commitment_repository_factory
        self._commitment_line_repo_factory = commitment_line_repository_factory
        self._project_repo_factory = project_repository_factory
        self._supplier_repo_factory = supplier_repository_factory
        self._currency_repo_factory = currency_repository_factory
        self._job_repo_factory = project_job_repository_factory
        self._cost_code_repo_factory = project_cost_code_repository_factory
        self._audit_service = audit_service

    # ── CRUD ──────────────────────────────────────────────────────────

    def create_commitment(self, command: CreateProjectCommitmentCommand) -> ProjectCommitmentDetailDTO:
        self._validate_commitment_type(command.commitment_type_code)
        if not command.commitment_number or not command.commitment_number.strip():
            raise ValidationError("Commitment number is required.")

        with self._unit_of_work_factory() as uow:
            self._validate_project(uow.session, command.company_id, command.project_id)
            self._validate_currency(uow.session, command.currency_code)
            if command.supplier_id is not None:
                self._validate_supplier(uow.session, command.company_id, command.supplier_id)

            repo = self._commitment_repo_factory(uow.session)
            existing = repo.get_by_company_and_number(command.company_id, command.commitment_number.strip())
            if existing is not None:
                raise ConflictError(f"Commitment number '{command.commitment_number}' already exists.")

            commitment = ProjectCommitment(
                company_id=command.company_id,
                project_id=command.project_id,
                commitment_number=command.commitment_number.strip(),
                commitment_type_code=command.commitment_type_code,
                commitment_date=command.commitment_date,
                currency_code=command.currency_code,
                supplier_id=command.supplier_id,
                required_date=command.required_date,
                exchange_rate=command.exchange_rate,
                reference_number=command.reference_number,
                notes=command.notes,
                status_code="draft",
                total_amount=Decimal("0.00"),
            )
            repo.add(commitment)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Commitment could not be created.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMMITMENT_CREATED
            self._record_audit(command.company_id, COMMITMENT_CREATED, "ProjectCommitment", commitment.id, f"Created commitment '{command.commitment_number}'")
            return self._to_detail_dto(commitment, uow.session)

    def update_commitment(self, commitment_id: int, company_id: int, command: UpdateProjectCommitmentCommand) -> ProjectCommitmentDetailDTO:
        self._validate_commitment_type(command.commitment_type_code)

        with self._unit_of_work_factory() as uow:
            repo = self._commitment_repo_factory(uow.session)
            commitment = repo.get_by_company_and_id(company_id, commitment_id)
            if commitment is None:
                raise NotFoundError(f"Commitment {commitment_id} not found.")
            if commitment.status_code != "draft":
                raise ValidationError("Only draft commitments can be edited.")

            self._validate_currency(uow.session, command.currency_code)
            if command.supplier_id is not None:
                self._validate_supplier(uow.session, company_id, command.supplier_id)

            commitment.commitment_type_code = command.commitment_type_code
            commitment.commitment_date = command.commitment_date
            commitment.currency_code = command.currency_code
            commitment.supplier_id = command.supplier_id
            commitment.required_date = command.required_date
            commitment.exchange_rate = command.exchange_rate
            commitment.reference_number = command.reference_number
            commitment.notes = command.notes
            repo.save(commitment)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Commitment could not be updated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMMITMENT_UPDATED
            self._record_audit(company_id, COMMITMENT_UPDATED, "ProjectCommitment", commitment.id, f"Updated commitment id={commitment_id}")
            return self._to_detail_dto(commitment, uow.session)

    def get_commitment_detail(self, commitment_id: int, company_id: int) -> ProjectCommitmentDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._commitment_repo_factory(uow.session)
            commitment = repo.get_by_company_and_id(company_id, commitment_id)
            if commitment is None:
                raise NotFoundError(f"Commitment {commitment_id} not found.")
            return self._to_detail_dto(commitment, uow.session)

    def list_commitments(self, project_id: int) -> list[ProjectCommitmentListItemDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._commitment_repo_factory(uow.session)
            commitments = repo.list_by_project(project_id)
            return [self._to_list_item_dto(c, uow.session) for c in commitments]

    # ── Lines ─────────────────────────────────────────────────────────

    def add_line(self, command: AddProjectCommitmentLineCommand) -> ProjectCommitmentDetailDTO:
        with self._unit_of_work_factory() as uow:
            commitment = self._get_editable_commitment(uow.session, command.project_commitment_id)
            self._validate_line_fields(uow.session, commitment, command)

            line_repo = self._commitment_line_repo_factory(uow.session)

            # Check line number uniqueness
            existing_lines = line_repo.list_by_commitment(command.project_commitment_id)
            for el in existing_lines:
                if el.line_number == command.line_number:
                    raise ConflictError(f"Line number {command.line_number} already exists.")

            line = ProjectCommitmentLine(
                project_commitment_id=command.project_commitment_id,
                line_number=command.line_number,
                project_cost_code_id=command.project_cost_code_id,
                line_amount=command.line_amount,
                project_job_id=command.project_job_id,
                description=command.description,
                quantity=command.quantity,
                unit_rate=command.unit_rate,
                notes=command.notes,
            )
            line_repo.add(line)

            self._recalculate_total(commitment, uow.session, extra_line_amount=command.line_amount)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Line could not be added.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMMITMENT_LINE_ADDED
            self._record_audit(commitment.company_id, COMMITMENT_LINE_ADDED, "ProjectCommitmentLine", line.id, f"Added line to commitment id={command.project_commitment_id}")
            return self._to_detail_dto(commitment, uow.session)

    def update_line(self, line_id: int, command: UpdateProjectCommitmentLineCommand) -> ProjectCommitmentDetailDTO:
        with self._unit_of_work_factory() as uow:
            line_repo = self._commitment_line_repo_factory(uow.session)
            line = line_repo.get_by_id(line_id)
            if line is None:
                raise NotFoundError(f"Commitment line {line_id} not found.")

            commitment = self._get_editable_commitment(uow.session, line.project_commitment_id)
            self._validate_line_fields(uow.session, commitment, command)

            line.line_number = command.line_number
            line.project_cost_code_id = command.project_cost_code_id
            line.line_amount = command.line_amount
            line.project_job_id = command.project_job_id
            line.description = command.description
            line.quantity = command.quantity
            line.unit_rate = command.unit_rate
            line.notes = command.notes
            line_repo.save(line)

            self._recalculate_total(commitment, uow.session)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Line could not be updated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMMITMENT_LINE_UPDATED
            self._record_audit(commitment.company_id, COMMITMENT_LINE_UPDATED, "ProjectCommitmentLine", line.id, f"Updated line id={line_id} on commitment")
            return self._to_detail_dto(commitment, uow.session)

    def remove_line(self, line_id: int) -> ProjectCommitmentDetailDTO:
        with self._unit_of_work_factory() as uow:
            line_repo = self._commitment_line_repo_factory(uow.session)
            line = line_repo.get_by_id(line_id)
            if line is None:
                raise NotFoundError(f"Commitment line {line_id} not found.")

            commitment = self._get_editable_commitment(uow.session, line.project_commitment_id)
            line_repo.delete(line)

            self._recalculate_total(commitment, uow.session)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Line could not be removed.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMMITMENT_LINE_REMOVED
            self._record_audit(commitment.company_id, COMMITMENT_LINE_REMOVED, "ProjectCommitmentLine", line_id, f"Removed line id={line_id} from commitment")
            return self._to_detail_dto(commitment, uow.session)

    # ── Workflow ──────────────────────────────────────────────────────

    def approve_commitment(self, command: ApproveProjectCommitmentCommand) -> ProjectCommitmentDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._commitment_repo_factory(uow.session)
            commitment = repo.get_by_company_and_id(command.company_id, command.commitment_id)
            if commitment is None:
                raise NotFoundError(f"Commitment {command.commitment_id} not found.")
            if commitment.status_code != "draft":
                raise ValidationError("Only draft commitments can be approved.")

            # Must have at least one line
            line_repo = self._commitment_line_repo_factory(uow.session)
            lines = line_repo.list_by_commitment(commitment.id)
            if not lines:
                raise ValidationError("Cannot approve a commitment with no lines.")

            commitment.status_code = "approved"
            commitment.approved_at = datetime.now(timezone.utc)
            commitment.approved_by_user_id = command.approved_by_user_id
            repo.save(commitment)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Commitment could not be approved.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMMITMENT_APPROVED
            self._record_audit(command.company_id, COMMITMENT_APPROVED, "ProjectCommitment", commitment.id, f"Approved commitment id={command.commitment_id}")
            return self._to_detail_dto(commitment, uow.session)

    def close_commitment(self, command: CloseProjectCommitmentCommand) -> ProjectCommitmentDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._commitment_repo_factory(uow.session)
            commitment = repo.get_by_company_and_id(command.company_id, command.commitment_id)
            if commitment is None:
                raise NotFoundError(f"Commitment {command.commitment_id} not found.")
            if commitment.status_code != "approved":
                raise ValidationError("Only approved commitments can be closed.")

            commitment.status_code = "closed"
            repo.save(commitment)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Commitment could not be closed.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMMITMENT_CLOSED
            self._record_audit(command.company_id, COMMITMENT_CLOSED, "ProjectCommitment", commitment.id, f"Closed commitment id={command.commitment_id}")
            return self._to_detail_dto(commitment, uow.session)

    def cancel_commitment(self, command: CancelProjectCommitmentCommand) -> ProjectCommitmentDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._commitment_repo_factory(uow.session)
            commitment = repo.get_by_company_and_id(command.company_id, command.commitment_id)
            if commitment is None:
                raise NotFoundError(f"Commitment {command.commitment_id} not found.")
            if commitment.status_code != "draft":
                raise ValidationError("Only draft commitments can be cancelled.")

            commitment.status_code = "cancelled"
            repo.save(commitment)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Commitment could not be cancelled.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import COMMITMENT_CANCELLED
            self._record_audit(command.company_id, COMMITMENT_CANCELLED, "ProjectCommitment", commitment.id, f"Cancelled commitment id={command.commitment_id}")
            return self._to_detail_dto(commitment, uow.session)

    # ── Private helpers ───────────────────────────────────────────────

    def _get_editable_commitment(self, session: Session, commitment_id: int) -> ProjectCommitment:
        repo = self._commitment_repo_factory(session)
        commitment = repo.get_by_id(commitment_id)
        if commitment is None:
            raise NotFoundError(f"Commitment {commitment_id} not found.")
        if commitment.status_code != "draft":
            raise ValidationError("Only draft commitments can be edited.")
        return commitment

    def _validate_commitment_type(self, type_code: str) -> None:
        if type_code not in _VALID_COMMITMENT_TYPES:
            raise ValidationError(
                f"Invalid commitment type: {type_code}. "
                f"Valid: {', '.join(sorted(_VALID_COMMITMENT_TYPES))}."
            )

    def _validate_project(self, session: Session, company_id: int, project_id: int) -> None:
        project = self._project_repo_factory(session).get_by_id(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found.")
        if project.company_id != company_id:
            raise ValidationError("Project does not belong to the specified company.")

    def _validate_supplier(self, session: Session, company_id: int, supplier_id: int) -> None:
        supplier = self._supplier_repo_factory(session).get_by_id(company_id, supplier_id)
        if supplier is None:
            raise NotFoundError(f"Supplier {supplier_id} not found.")

    def _validate_currency(self, session: Session, currency_code: str) -> None:
        if not self._currency_repo_factory(session).exists_active(currency_code):
            raise ValidationError(f"Currency code '{currency_code}' is not found or not active.")

    def _validate_line_fields(
        self,
        session: Session,
        commitment: ProjectCommitment,
        command: AddProjectCommitmentLineCommand | UpdateProjectCommitmentLineCommand,
    ) -> None:
        if command.line_amount < Decimal("0"):
            raise ValidationError("Line amount cannot be negative.")

        cost_code = self._cost_code_repo_factory(session).get_by_id(command.project_cost_code_id)
        if cost_code is None:
            raise NotFoundError(f"Cost code {command.project_cost_code_id} not found.")
        if cost_code.company_id != commitment.company_id:
            raise ValidationError("Cost code does not belong to the commitment's company.")

        if command.project_job_id is not None:
            job = self._job_repo_factory(session).get_by_id(command.project_job_id)
            if job is None:
                raise NotFoundError(f"Job {command.project_job_id} not found.")
            if job.project_id != commitment.project_id:
                raise ValidationError("Job does not belong to the commitment's project.")

    def _recalculate_total(
        self,
        commitment: ProjectCommitment,
        session: Session,
        extra_line_amount: Decimal | None = None,
    ) -> None:
        """Recalculate total_amount from all persisted lines.

        For newly added lines not yet flushed, `extra_line_amount` can be provided
        to include the new line in the sum.
        """
        line_repo = self._commitment_line_repo_factory(session)
        lines = line_repo.list_by_commitment(commitment.id)
        total = sum((ln.line_amount for ln in lines), Decimal("0.00"))
        if extra_line_amount is not None:
            total += extra_line_amount
        commitment.total_amount = total

    # ── DTO mapping ───────────────────────────────────────────────────

    def _to_list_item_dto(self, commitment: ProjectCommitment, session: Session) -> ProjectCommitmentListItemDTO:
        project = self._project_repo_factory(session).get_by_id(commitment.project_id)
        project_name = project.project_name if project else ""

        supplier_name: str | None = None
        if commitment.supplier_id is not None:
            supplier = self._supplier_repo_factory(session).get_by_id(commitment.company_id, commitment.supplier_id)
            supplier_name = supplier.display_name if supplier else None

        return ProjectCommitmentListItemDTO(
            id=commitment.id,
            commitment_number=commitment.commitment_number,
            project_id=commitment.project_id,
            project_name=project_name,
            commitment_type_code=commitment.commitment_type_code,
            commitment_date=commitment.commitment_date,
            currency_code=commitment.currency_code,
            status_code=commitment.status_code,
            total_amount=commitment.total_amount,
            supplier_name=supplier_name,
            reference_number=commitment.reference_number,
        )

    def _to_detail_dto(self, commitment: ProjectCommitment, session: Session) -> ProjectCommitmentDetailDTO:
        project = self._project_repo_factory(session).get_by_id(commitment.project_id)
        project_name = project.project_name if project else ""

        supplier_name: str | None = None
        if commitment.supplier_id is not None:
            supplier = self._supplier_repo_factory(session).get_by_id(commitment.company_id, commitment.supplier_id)
            supplier_name = supplier.display_name if supplier else None

        line_repo = self._commitment_line_repo_factory(session)
        lines = line_repo.list_by_commitment(commitment.id)
        line_dtos = [self._to_line_dto(ln, session) for ln in lines]

        return ProjectCommitmentDetailDTO(
            id=commitment.id,
            commitment_number=commitment.commitment_number,
            company_id=commitment.company_id,
            project_id=commitment.project_id,
            project_name=project_name,
            commitment_type_code=commitment.commitment_type_code,
            commitment_date=commitment.commitment_date,
            currency_code=commitment.currency_code,
            status_code=commitment.status_code,
            total_amount=commitment.total_amount,
            supplier_id=commitment.supplier_id,
            supplier_name=supplier_name,
            required_date=commitment.required_date,
            exchange_rate=commitment.exchange_rate,
            reference_number=commitment.reference_number,
            notes=commitment.notes,
            approved_at=commitment.approved_at,
            approved_by_user_id=commitment.approved_by_user_id,
            lines=line_dtos,
            created_at=commitment.created_at,
            updated_at=commitment.updated_at,
        )

    def _to_line_dto(self, line: ProjectCommitmentLine, session: Session) -> ProjectCommitmentLineDTO:
        cost_code = self._cost_code_repo_factory(session).get_by_id(line.project_cost_code_id)
        cost_code_name = cost_code.name if cost_code else ""

        job_name: str | None = None
        if line.project_job_id is not None:
            job = self._job_repo_factory(session).get_by_id(line.project_job_id)
            job_name = job.job_name if job else None

        return ProjectCommitmentLineDTO(
            id=line.id,
            line_number=line.line_number,
            project_cost_code_id=line.project_cost_code_id,
            cost_code_name=cost_code_name,
            line_amount=line.line_amount,
            project_job_id=line.project_job_id,
            job_name=job_name,
            description=line.description,
            quantity=line.quantity,
            unit_rate=line.unit_rate,
            notes=line.notes,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_JOB_COSTING
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_JOB_COSTING,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
