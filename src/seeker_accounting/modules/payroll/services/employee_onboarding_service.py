"""Phase 4 Hire-to-Pay business-process service.

Owns the entire lifecycle of an :class:`EmployeeOnboardingDraft`:

* ``start_draft`` — create a fresh draft for a company.
* ``update_step`` — patch the payload for one of the six drafting steps.
* ``transition_state`` — move the draft along the state machine
  (forward, back, or abandon).
* ``complete`` — finalise from ``draft_review``, materialise the
  ``Employee`` row, and mark the draft completed.
* ``get_draft`` / ``list_active_drafts`` — read access.

State transitions and step validation live here, **never** in the UI.
Each state-changing call records an audit event so the full hire BP
can be replayed.

Per Phase 4 plan: required statutory IDs and a payment account become
*structurally* required at completion time. Light edits to existing
employees go through the legacy form dialog.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.employee_onboarding_dto import (
    DRAFTING_STEP_CODES,
    DRAFTING_STEP_ORDER,
    STATE_TO_PAYLOAD_KEY,
    STEP_PAYLOAD_KEYS,
    EmployeeOnboardingDraftDTO,
    EmployeeOnboardingStartCommand,
    EmployeeOnboardingState,
    EmployeeOnboardingStepUpdate,
    EmployeeOnboardingTransition,
    is_terminal,
)
from seeker_accounting.modules.payroll.models.employee import Employee
from seeker_accounting.modules.payroll.models.employee_compensation_profile import (
    EmployeeCompensationProfile,
)
from seeker_accounting.modules.payroll.models.employee_component_assignment import (
    EmployeeComponentAssignment,
)
from seeker_accounting.modules.payroll.models.employee_onboarding_draft import (
    EmployeeOnboardingDraft,
)
from seeker_accounting.modules.payroll.payroll_permissions import (
    PAYROLL_EMPLOYEE_MANAGE,
)
from seeker_accounting.modules.payroll.repositories.compensation_profile_repository import (
    CompensationProfileRepository,
)
from seeker_accounting.modules.payroll.repositories.component_assignment_repository import (
    ComponentAssignmentRepository,
)
from seeker_accounting.modules.payroll.repositories.employee_onboarding_draft_repository import (
    EmployeeOnboardingDraftRepository,
)
from seeker_accounting.modules.payroll.repositories.employee_repository import (
    EmployeeRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from seeker_accounting.shared.services.telemetry_service import TelemetryService


DraftRepositoryFactory = Callable[[Session], EmployeeOnboardingDraftRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
CompensationProfileRepositoryFactory = Callable[[Session], CompensationProfileRepository]
ComponentAssignmentRepositoryFactory = Callable[[Session], ComponentAssignmentRepository]


# ── Step validation ──────────────────────────────────────────────────────


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _validate_step_payload(step_code: str, payload: Mapping[str, Any]) -> list[str]:
    """Return a list of human-readable issues for a given step.

    Empty list means the step is structurally complete. The full
    field-level validation (uniqueness, references, format) lives in
    the P1.S5 validator pipeline at the UI/service boundary.
    """
    issues: list[str] = []
    if step_code == "identity":
        if _is_blank(payload.get("first_name")):
            issues.append("First name is required.")
        if _is_blank(payload.get("last_name")):
            issues.append("Last name is required.")
    elif step_code == "employment":
        if _is_blank(payload.get("employee_number")):
            issues.append("Employee number is required.")
        if _is_blank(payload.get("hire_date")):
            issues.append("Hire date is required.")
    elif step_code == "compensation":
        if _is_blank(payload.get("base_currency_code")):
            issues.append("Base currency is required.")
        # Note: actual compensation profile rows are written in P4.S3.
    elif step_code == "payment":
        method = payload.get("payment_method_code")
        if _is_blank(method):
            issues.append("Payment method is required.")
        # If method is bank, account is mandatory.
        if method == "bank" and payload.get("default_payment_account_id") in (None, 0):
            issues.append("A bank account is required for bank-paid employees.")
    elif step_code == "statutory":
        if _is_blank(payload.get("tax_identifier")):
            issues.append("Tax identifier is required.")
        if _is_blank(payload.get("cnps_number")):
            issues.append("CNPS number is required.")
    elif step_code == "components":
        # The components grid arrives in P4.S4; at minimum the slot
        # must exist (even an empty list is OK).
        pass
    else:
        issues.append(f"Unknown step '{step_code}'.")
    return issues


def _is_step_complete(step_code: str, payload: Mapping[str, Any]) -> bool:
    return not _validate_step_payload(step_code, payload)


# ── Service ──────────────────────────────────────────────────────────────


class EmployeeOnboardingService:
    """Phase 4 Hire-to-Pay BP service."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        draft_repository_factory: DraftRepositoryFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService,
        compensation_profile_repository_factory: CompensationProfileRepositoryFactory | None = None,
        component_assignment_repository_factory: ComponentAssignmentRepositoryFactory | None = None,
        telemetry_service: TelemetryService | None = None,
    ) -> None:
        self._uow = unit_of_work_factory
        self._draft_repo_factory = draft_repository_factory
        self._employee_repo_factory = employee_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service
        self._comp_profile_repo_factory = compensation_profile_repository_factory
        self._comp_assignment_repo_factory = component_assignment_repository_factory
        self._telemetry = telemetry_service

    # ── Public API: reads ────────────────────────────────────────────

    def get_draft(self, company_id: int, draft_id: int) -> EmployeeOnboardingDraftDTO:
        self._permission_service.require_permission(PAYROLL_EMPLOYEE_MANAGE)
        with self._uow() as uow:
            draft = self._draft_repo_factory(uow.session).get_for_company(
                draft_id, company_id
            )
            if draft is None:
                raise NotFoundError(
                    f"Employee onboarding draft {draft_id} not found for company {company_id}."
                )
            return self._to_dto(draft)

    def list_active_drafts(
        self, company_id: int
    ) -> list[EmployeeOnboardingDraftDTO]:
        self._permission_service.require_permission(PAYROLL_EMPLOYEE_MANAGE)
        with self._uow() as uow:
            rows = self._draft_repo_factory(uow.session).list_active_for_company(
                company_id
            )
            return [self._to_dto(r) for r in rows]

    def is_step_complete(self, payload: Mapping[str, Any], step_code: str) -> bool:
        return _is_step_complete(step_code, payload or {})

    def step_issues(self, payload: Mapping[str, Any], step_code: str) -> list[str]:
        return _validate_step_payload(step_code, payload or {})

    # ── Public API: writes ───────────────────────────────────────────

    def start_draft(
        self, command: EmployeeOnboardingStartCommand
    ) -> EmployeeOnboardingDraftDTO:
        self._permission_service.require_permission(PAYROLL_EMPLOYEE_MANAGE)
        if command.company_id <= 0:
            raise ValidationError("A company is required to start an onboarding draft.")

        initial_payload: dict[str, Any] = {key: {} for key in STEP_PAYLOAD_KEYS}
        if command.initial_payload:
            for key in STEP_PAYLOAD_KEYS:
                slot = command.initial_payload.get(key)
                if isinstance(slot, Mapping):
                    initial_payload[key] = dict(slot)

        with self._uow() as uow:
            draft = EmployeeOnboardingDraft(
                company_id=command.company_id,
                status_code=EmployeeOnboardingState.DRAFT_IDENTITY.value,
                current_step=EmployeeOnboardingState.DRAFT_IDENTITY.value,
                payload_json=json.dumps(initial_payload),
                started_by_user_id=command.started_by_user_id,
                last_modified_by_user_id=command.started_by_user_id,
            )
            self._draft_repo_factory(uow.session).save(draft)
            uow.session.flush()

            self._record_audit(
                uow.session,
                draft,
                event_type="EMPLOYEE_ONBOARDING_STARTED",
                description="Started employee onboarding draft.",
                detail={"company_id": command.company_id},
            )
            uow.commit()
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="hire_bp",
                    step="started",
                    event_code="hire_bp.started",
                    context={"company_id": command.company_id},
                )
            return self._to_dto(draft)

    def update_step(
        self, company_id: int, command: EmployeeOnboardingStepUpdate
    ) -> EmployeeOnboardingDraftDTO:
        self._permission_service.require_permission(PAYROLL_EMPLOYEE_MANAGE)
        if command.step_code not in STEP_PAYLOAD_KEYS:
            raise ValidationError(f"Unknown onboarding step '{command.step_code}'.")

        with self._uow() as uow:
            repo = self._draft_repo_factory(uow.session)
            draft = repo.get_for_company(command.draft_id, company_id)
            if draft is None:
                raise NotFoundError(
                    f"Employee onboarding draft {command.draft_id} not found."
                )
            if is_terminal(draft.status_code):
                raise ConflictError(
                    "This onboarding draft is closed and cannot be edited."
                )

            payload = self._load_payload(draft)
            payload[command.step_code] = dict(command.patch or {})
            draft.payload_json = json.dumps(payload)
            draft.last_modified_by_user_id = command.actor_user_id

            self._record_audit(
                uow.session,
                draft,
                event_type="EMPLOYEE_ONBOARDING_STEP_UPDATED",
                description=f"Updated onboarding step '{command.step_code}'.",
                detail={"step_code": command.step_code},
            )
            uow.commit()
            return self._to_dto(draft)

    def transition_state(
        self, company_id: int, command: EmployeeOnboardingTransition
    ) -> EmployeeOnboardingDraftDTO:
        """Move a draft between states.

        Allowed transitions:

        * Forward: ``draft_X`` → next drafting state, only if the
          *current* step's payload is structurally complete.
        * Back: any drafting state → any earlier drafting state (no
          payload validation; the user can revisit earlier steps).
        * ``draft_review`` → ``completed`` is **not** handled here;
          callers must use :meth:`complete`.
        * Any drafting state → ``abandoned`` with optional reason.
        """
        self._permission_service.require_permission(PAYROLL_EMPLOYEE_MANAGE)

        with self._uow() as uow:
            repo = self._draft_repo_factory(uow.session)
            draft = repo.get_for_company(command.draft_id, company_id)
            if draft is None:
                raise NotFoundError(
                    f"Employee onboarding draft {command.draft_id} not found."
                )
            if is_terminal(draft.status_code):
                raise ConflictError("Onboarding draft is already closed.")

            target = command.target_state
            if target == EmployeeOnboardingState.COMPLETED.value:
                raise ValidationError(
                    "Use complete() to finalise an onboarding draft."
                )
            if target == EmployeeOnboardingState.ABANDONED.value:
                draft.status_code = EmployeeOnboardingState.ABANDONED.value
                draft.abandoned_at = datetime.utcnow()
                draft.abandon_reason = command.abandon_reason
                draft.last_modified_by_user_id = command.actor_user_id
                self._record_audit(
                    uow.session,
                    draft,
                    event_type="EMPLOYEE_ONBOARDING_ABANDONED",
                    description="Abandoned employee onboarding draft.",
                    detail={"reason": command.abandon_reason},
                )
                uow.commit()
                if self._telemetry is not None:
                    self._telemetry.record_funnel_step(
                        funnel="hire_bp",
                        step="abandoned",
                        event_code="hire_bp.abandoned",
                        context={"from_step": draft.status_code},
                    )
                return self._to_dto(draft)

            if target not in DRAFTING_STEP_CODES:
                raise ValidationError(
                    f"Unknown onboarding target state '{target}'."
                )

            current = draft.status_code
            current_idx = self._drafting_index(current)
            target_idx = self._drafting_index(target)

            if current_idx is None or target_idx is None:
                raise ValidationError(
                    f"Cannot transition from {current} to {target}."
                )

            # Forward step gate: current step's payload must be complete.
            if target_idx > current_idx:
                payload_key = STATE_TO_PAYLOAD_KEY[current]
                payload = self._load_payload(draft)
                issues = _validate_step_payload(
                    payload_key, payload.get(payload_key, {})
                )
                if issues:
                    raise ValidationError(
                        "Cannot advance: " + " ".join(issues)
                    )
                # Forward jumps may only advance one step at a time so
                # the user cannot skip mandatory data collection.
                if target_idx != current_idx + 1:
                    raise ValidationError(
                        "Forward navigation must advance one step at a time."
                    )

            draft.status_code = target
            draft.current_step = target
            draft.last_modified_by_user_id = command.actor_user_id
            self._record_audit(
                uow.session,
                draft,
                event_type="EMPLOYEE_ONBOARDING_TRANSITIONED",
                description=f"Onboarding transitioned: {current} → {target}.",
                detail={"from": current, "to": target},
            )
            uow.commit()
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="hire_bp",
                    step=target,
                    event_code=f"hire_bp.{target}",
                    context={"from_step": current, "to_step": target},
                )
            return self._to_dto(draft)

    def complete(
        self,
        company_id: int,
        draft_id: int,
        actor_user_id: int | None = None,
    ) -> EmployeeOnboardingDraftDTO:
        """Finalise the BP from ``draft_review``.

        All six step payloads must validate, and a corresponding
        ``Employee`` row is materialised. Idempotency: re-completing a
        completed draft is a no-op (returns the same DTO).
        """
        self._permission_service.require_permission(PAYROLL_EMPLOYEE_MANAGE)
        with self._uow() as uow:
            repo = self._draft_repo_factory(uow.session)
            draft = repo.get_for_company(draft_id, company_id)
            if draft is None:
                raise NotFoundError(
                    f"Employee onboarding draft {draft_id} not found."
                )
            if draft.status_code == EmployeeOnboardingState.COMPLETED.value:
                return self._to_dto(draft)
            if draft.status_code == EmployeeOnboardingState.ABANDONED.value:
                raise ConflictError("Onboarding draft was abandoned.")
            if draft.status_code != EmployeeOnboardingState.DRAFT_REVIEW.value:
                raise ConflictError(
                    "Onboarding draft must be at the review step before completion."
                )

            payload = self._load_payload(draft)
            blocking: list[str] = []
            for key in STEP_PAYLOAD_KEYS:
                blocking.extend(_validate_step_payload(key, payload.get(key, {})))
            if blocking:
                raise ValidationError(
                    "Cannot complete onboarding: " + " ".join(blocking)
                )

            # Materialise the Employee row.
            employee = self._materialise_employee(
                uow.session,
                company_id=company_id,
                payload=payload,
            )
            uow.session.flush()

            draft.status_code = EmployeeOnboardingState.COMPLETED.value
            draft.completed_at = datetime.utcnow()
            draft.last_modified_by_user_id = actor_user_id
            draft.produced_employee_id = employee.id

            self._record_audit(
                uow.session,
                draft,
                event_type="EMPLOYEE_ONBOARDING_COMPLETED",
                description="Completed employee onboarding draft.",
                detail={"employee_id": employee.id},
            )
            uow.commit()
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="hire_bp",
                    step="completed",
                    event_code="hire_bp.completed",
                    context={"company_id": company_id},
                )
            return self._to_dto(draft)

    # ── Internal helpers ─────────────────────────────────────────────

    @staticmethod
    def _drafting_index(state_code: str) -> int | None:
        try:
            return [s.value for s in DRAFTING_STEP_ORDER].index(state_code)
        except ValueError:
            return None

    @staticmethod
    def _load_payload(draft: EmployeeOnboardingDraft) -> dict[str, Any]:
        try:
            data = json.loads(draft.payload_json or "{}")
        except (ValueError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        # Ensure every step slot exists.
        for key in STEP_PAYLOAD_KEYS:
            data.setdefault(key, {})
        return data

    def _record_audit(
        self,
        session: Session,
        draft: EmployeeOnboardingDraft,
        *,
        event_type: str,
        description: str,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            self._audit_service.record_event_in_session(
                session,
                draft.company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type,
                    module_code="payroll",
                    entity_type="employee_onboarding_draft",
                    entity_id=draft.id or 0,
                    description=description,
                    detail_json=json.dumps(dict(detail or {})),
                ),
            )
        except Exception:  # pragma: no cover — audit must never block BP
            # Audit failures are logged by the audit service itself; we
            # do not let them tear down the business transaction.
            pass

    def _materialise_employee(
        self,
        session: Session,
        *,
        company_id: int,
        payload: Mapping[str, Any],
    ) -> Employee:
        identity = payload.get("identity") or {}
        employment = payload.get("employment") or {}
        compensation = payload.get("compensation") or {}
        payment = payload.get("payment") or {}
        statutory = payload.get("statutory") or {}

        employee_number = str(employment.get("employee_number") or "").strip()
        first_name = str(identity.get("first_name") or "").strip()
        last_name = str(identity.get("last_name") or "").strip()
        display_name = (
            str(identity.get("display_name") or "").strip()
            or f"{first_name} {last_name}".strip()
        )

        # Uniqueness check — fail fast with a typed exception.
        repo = self._employee_repo_factory(session)
        if repo.get_by_number(company_id, employee_number) is not None:
            raise ConflictError(
                f"Employee number '{employee_number}' is already in use."
            )

        hire_date = employment.get("hire_date")
        # Caller is responsible for sending a date object or ISO string;
        # store as-is. Strict parsing is done in the UI command layer.
        if isinstance(hire_date, str):
            from datetime import date as _date

            try:
                hire_date = _date.fromisoformat(hire_date)
            except ValueError as exc:
                raise ValidationError(
                    f"Invalid hire_date: {hire_date}"
                ) from exc

        employee = Employee(
            company_id=company_id,
            employee_number=employee_number,
            display_name=display_name,
            first_name=first_name,
            last_name=last_name,
            department_id=employment.get("department_id"),
            position_id=employment.get("position_id"),
            hire_date=hire_date,
            phone=identity.get("phone"),
            email=identity.get("email"),
            tax_identifier=str(statutory.get("tax_identifier") or "").strip() or None,
            cnps_number=str(statutory.get("cnps_number") or "").strip() or None,
            default_payment_account_id=payment.get("default_payment_account_id"),
            base_currency_code=str(
                compensation.get("base_currency_code")
                or payment.get("base_currency_code")
                or "XAF"
            ),
            is_active=True,
        )
        repo.save(employee)

        # ── Compensation profile (P4.S3) ─────────────────────────────
        # Created only when the wizard step sends a basic_salary value
        # and the repository factory is wired. Backward-compatible with
        # old payloads that only carry base_currency_code.
        basic_salary_str = str(compensation.get("basic_salary") or "").strip()
        if basic_salary_str and self._comp_profile_repo_factory is not None:
            from datetime import date as _date2
            from decimal import Decimal, InvalidOperation

            try:
                basic_salary = Decimal(basic_salary_str)
            except InvalidOperation:
                basic_salary = None

            if basic_salary is not None and basic_salary > 0:
                eff_from_str = str(compensation.get("effective_from") or "").strip()
                eff_from: Any = None
                if eff_from_str:
                    try:
                        eff_from = _date2.fromisoformat(eff_from_str)
                    except ValueError:
                        eff_from = None
                if eff_from is None:
                    eff_from = employee.hire_date or _date2.today()

                profile_name = (
                    str(compensation.get("profile_name") or "").strip()
                    or "Initial salary"
                )
                currency_code = str(
                    compensation.get("base_currency_code")
                    or employee.base_currency_code
                    or "XAF"
                ).strip()

                try:
                    number_of_parts = Decimal(
                        str(compensation.get("number_of_parts") or "1.0")
                    )
                except Exception:
                    number_of_parts = Decimal("1.0")

                comp_profile = EmployeeCompensationProfile(
                    company_id=company_id,
                    employee_id=employee.id,
                    profile_name=profile_name,
                    basic_salary=basic_salary,
                    currency_code=currency_code,
                    effective_from=eff_from,
                    effective_to=None,
                    number_of_parts=number_of_parts,
                    notes=str(compensation.get("notes") or "").strip() or None,
                    is_active=True,
                )
                self._comp_profile_repo_factory(session).save(comp_profile)

        # ── Component assignments (P4.S4) ────────────────────────────
        # Created only when the wizard step sends an assignments list
        # and the repository factory is wired.
        comp_assignments = (payload.get("components") or {}).get("assignments") or []
        if comp_assignments and self._comp_assignment_repo_factory is not None:
            from datetime import date as _date3
            from decimal import Decimal, InvalidOperation as _IE

            hire_eff: Any = employee.hire_date or _date3.today()
            assignment_repo = self._comp_assignment_repo_factory(session)
            for item in comp_assignments:
                if not isinstance(item, dict) or "component_id" not in item:
                    continue
                try:
                    component_id = int(item["component_id"])
                except (ValueError, TypeError):
                    continue
                override_amount = None
                ovr_str = str(item.get("override_amount") or "").strip()
                if ovr_str:
                    try:
                        override_amount = Decimal(ovr_str)
                    except _IE:
                        override_amount = None
                assignment = EmployeeComponentAssignment(
                    company_id=company_id,
                    employee_id=employee.id,
                    component_id=component_id,
                    override_amount=override_amount,
                    override_rate=None,
                    effective_from=hire_eff,
                    effective_to=None,
                    is_active=True,
                )
                assignment_repo.save(assignment)

        return employee

    @staticmethod
    def _to_dto(draft: EmployeeOnboardingDraft) -> EmployeeOnboardingDraftDTO:
        try:
            payload = json.loads(draft.payload_json or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except (ValueError, TypeError):
            payload = {}
        return EmployeeOnboardingDraftDTO(
            id=draft.id,
            company_id=draft.company_id,
            status_code=draft.status_code,
            current_step=draft.current_step,
            payload=payload,
            started_by_user_id=draft.started_by_user_id,
            last_modified_by_user_id=draft.last_modified_by_user_id,
            completed_at=draft.completed_at,
            abandoned_at=draft.abandoned_at,
            abandon_reason=draft.abandon_reason,
            produced_employee_id=draft.produced_employee_id,
            created_at=getattr(draft, "created_at", None),
            updated_at=getattr(draft, "updated_at", None),
        )
