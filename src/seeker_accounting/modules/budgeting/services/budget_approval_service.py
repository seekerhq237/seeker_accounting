from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.budgeting.dto.project_budget_commands import (
    ApproveProjectBudgetVersionCommand,
    BudgetLineDraftDTO,
    CancelProjectBudgetVersionCommand,
    CloneProjectBudgetVersionCommand,
    SubmitProjectBudgetVersionCommand,
)
from seeker_accounting.modules.budgeting.dto.project_budget_dto import (
    CurrentApprovedBudgetDTO,
    ProjectBudgetVersionDetailDTO,
)
from seeker_accounting.modules.budgeting.models.project_budget_line import ProjectBudgetLine
from seeker_accounting.modules.budgeting.models.project_budget_version import ProjectBudgetVersion
from seeker_accounting.modules.budgeting.repositories.project_budget_line_repository import (
    ProjectBudgetLineRepository,
)
from seeker_accounting.modules.budgeting.repositories.project_budget_version_repository import (
    ProjectBudgetVersionRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

ProjectBudgetVersionRepositoryFactory = Callable[[Session], ProjectBudgetVersionRepository]
ProjectBudgetLineRepositoryFactory = Callable[[Session], ProjectBudgetLineRepository]

_ALLOWED_SUBMIT_FROM = frozenset({"draft"})
_ALLOWED_APPROVE_FROM = frozenset({"submitted"})
_ALLOWED_CANCEL_FROM = frozenset({"draft", "submitted"})


class BudgetApprovalService:
    """Workflow transitions for project budget versions: submit, approve, cancel, clone."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        version_repository_factory: ProjectBudgetVersionRepositoryFactory,
        line_repository_factory: ProjectBudgetLineRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._version_repository_factory = version_repository_factory
        self._line_repository_factory = line_repository_factory
        self._audit_service = audit_service

    # ── Submit ────────────────────────────────────────────────────────

    def submit_version(
        self, command: SubmitProjectBudgetVersionCommand
    ) -> ProjectBudgetVersionDetailDTO:
        with self._unit_of_work_factory() as uow:
            version = self._load_version(uow.session, command.version_id, command.company_id)

            if version.status_code not in _ALLOWED_SUBMIT_FROM:
                raise ValidationError(
                    f"Cannot submit a budget version with status '{version.status_code}'. "
                    "Only draft versions can be submitted."
                )

            line_repo = self._line_repository_factory(uow.session)
            lines = line_repo.list_by_version(version.id)
            if not lines:
                raise ValidationError(
                    "Cannot submit a budget version with no lines. Add at least one budget line first."
                )

            version.status_code = "submitted"
            version_repo = self._version_repository_factory(uow.session)
            version_repo.save(version)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget version could not be submitted.") from exc

            return self._to_detail_dto(version)

    # ── Approve ───────────────────────────────────────────────────────

    def approve_version(
        self, command: ApproveProjectBudgetVersionCommand
    ) -> ProjectBudgetVersionDetailDTO:
        with self._unit_of_work_factory() as uow:
            version = self._load_version(uow.session, command.version_id, command.company_id)

            if version.status_code not in _ALLOWED_APPROVE_FROM:
                raise ValidationError(
                    f"Cannot approve a budget version with status '{version.status_code}'. "
                    "Only submitted versions can be approved."
                )

            version_repo = self._version_repository_factory(uow.session)

            # Supersede the currently approved version for this project, if any
            current_approved = version_repo.get_current_approved(version.project_id)
            if current_approved is not None and current_approved.id != version.id:
                current_approved.status_code = "superseded"
                version_repo.save(current_approved)

            version.status_code = "approved"
            version.approved_at = datetime.now()
            version.approved_by_user_id = command.approved_by_user_id
            version_repo.save(version)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget version could not be approved.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import BUDGET_VERSION_APPROVED
            self._record_audit(
                command.company_id,
                BUDGET_VERSION_APPROVED,
                "ProjectBudgetVersion",
                version.id,
                "Approved budget version",
            )
            return self._to_detail_dto(version)

    # ── Cancel ────────────────────────────────────────────────────────

    def cancel_version(
        self, command: CancelProjectBudgetVersionCommand
    ) -> ProjectBudgetVersionDetailDTO:
        with self._unit_of_work_factory() as uow:
            version = self._load_version(uow.session, command.version_id, command.company_id)

            if version.status_code not in _ALLOWED_CANCEL_FROM:
                raise ValidationError(
                    f"Cannot cancel a budget version with status '{version.status_code}'. "
                    "Only draft or submitted versions can be cancelled."
                )

            version.status_code = "cancelled"
            version_repo = self._version_repository_factory(uow.session)
            version_repo.save(version)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget version could not be cancelled.") from exc

            return self._to_detail_dto(version)

    # ── Clone ─────────────────────────────────────────────────────────

    def clone_version(
        self, command: CloneProjectBudgetVersionCommand
    ) -> ProjectBudgetVersionDetailDTO:
        if not command.version_name or not command.version_name.strip():
            raise ValidationError("Version name is required.")

        with self._unit_of_work_factory() as uow:
            version_repo = self._version_repository_factory(uow.session)
            source = version_repo.get_by_company_and_id(command.company_id, command.source_version_id)
            if source is None:
                raise NotFoundError(f"Source budget version {command.source_version_id} not found.")
            if source.project_id != command.project_id:
                raise ValidationError("Source version does not belong to the specified project.")

            next_number = version_repo.get_max_version_number(command.project_id) + 1

            new_version = ProjectBudgetVersion(
                company_id=command.company_id,
                project_id=command.project_id,
                version_number=next_number,
                version_name=command.version_name.strip(),
                version_type_code=command.version_type_code,
                status_code="draft",
                base_version_id=command.source_version_id,
                budget_date=command.budget_date,
                revision_reason=command.revision_reason,
                total_budget_amount=Decimal("0"),
            )
            version_repo.add(new_version)
            uow.session.flush()  # get new_version.id

            # Copy lines from source
            line_repo = self._line_repository_factory(uow.session)
            source_lines = line_repo.list_by_version(source.id)
            total = Decimal("0")
            for src_line in source_lines:
                cloned = ProjectBudgetLine(
                    project_budget_version_id=new_version.id,
                    line_number=src_line.line_number,
                    project_job_id=src_line.project_job_id,
                    project_cost_code_id=src_line.project_cost_code_id,
                    description=src_line.description,
                    quantity=src_line.quantity,
                    unit_rate=src_line.unit_rate,
                    line_amount=src_line.line_amount,
                    start_date=src_line.start_date,
                    end_date=src_line.end_date,
                    notes=src_line.notes,
                )
                line_repo.add(cloned)
                total += src_line.line_amount

            new_version.total_budget_amount = total

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Budget version could not be cloned.") from exc

            return self._to_detail_dto(new_version)

    # ── Current approved budget ───────────────────────────────────────

    def get_current_approved_budget(self, project_id: int) -> CurrentApprovedBudgetDTO | None:
        with self._unit_of_work_factory() as uow:
            version_repo = self._version_repository_factory(uow.session)
            version = version_repo.get_current_approved(project_id)
            if version is None:
                return None
            return CurrentApprovedBudgetDTO(
                project_id=version.project_id,
                version_id=version.id,
                version_number=version.version_number,
                version_name=version.version_name,
                total_budget_amount=version.total_budget_amount,
                budget_date=version.budget_date,
                approved_at=version.approved_at,
            )

    # ── Revision seed (no persistence) ────────────────────────────────

    def prepare_revision_draft(
        self, project_id: int
    ) -> tuple[int, str, int | None, tuple[BudgetLineDraftDTO, ...]] | None:
        """Return a seed for a new revision draft based on the current approved version.

        Returns a tuple ``(next_version_number, default_name, base_version_id, line_drafts)``
        that the UI can pass to ``ProjectBudgetService.create_version_with_lines``.
        Returns ``None`` if no approved version exists (nothing to revise from).

        The returned drafts carry fresh line numbers (sequential from 1) and
        reference the same jobs/cost codes/amounts as the approved version.
        """
        with self._unit_of_work_factory() as uow:
            version_repo = self._version_repository_factory(uow.session)
            approved = version_repo.get_current_approved(project_id)
            if approved is None:
                return None

            next_number = version_repo.get_max_version_number(project_id) + 1
            default_name = f"Revision {next_number}"

            line_repo = self._line_repository_factory(uow.session)
            source_lines = line_repo.list_by_version(approved.id)
            drafts = tuple(
                BudgetLineDraftDTO(
                    line_number=idx,
                    project_cost_code_id=src.project_cost_code_id,
                    line_amount=src.line_amount,
                    project_job_id=src.project_job_id,
                    description=src.description,
                    quantity=src.quantity,
                    unit_rate=src.unit_rate,
                    start_date=src.start_date,
                    end_date=src.end_date,
                    notes=src.notes,
                )
                for idx, src in enumerate(source_lines, start=1)
            )
            return (next_number, default_name, approved.id, drafts)

    # ── Internal helpers ──────────────────────────────────────────────

    def _load_version(
        self, session: Session, version_id: int, company_id: int
    ) -> ProjectBudgetVersion:
        version_repo = self._version_repository_factory(session)
        version = version_repo.get_by_company_and_id(company_id, version_id)
        if version is None:
            raise NotFoundError(f"Budget version {version_id} not found.")
        return version

    def _to_detail_dto(self, version: ProjectBudgetVersion) -> ProjectBudgetVersionDetailDTO:
        base_version_name: str | None = None
        if version.base_version is not None:
            base_version_name = version.base_version.version_name

        return ProjectBudgetVersionDetailDTO(
            id=version.id,
            company_id=version.company_id,
            project_id=version.project_id,
            version_number=version.version_number,
            version_name=version.version_name,
            version_type_code=version.version_type_code,
            status_code=version.status_code,
            base_version_id=version.base_version_id,
            base_version_name=base_version_name,
            budget_date=version.budget_date,
            revision_reason=version.revision_reason,
            total_budget_amount=version.total_budget_amount,
            approved_at=version.approved_at,
            approved_by_user_id=version.approved_by_user_id,
            created_at=version.created_at,
            updated_at=version.updated_at,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_BUDGETING
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_BUDGETING,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
