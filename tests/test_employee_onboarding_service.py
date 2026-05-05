"""P4.S1 — EmployeeOnboardingService unit tests.

Exercise the Hire-to-Pay BP state machine end-to-end against a real
in-memory SQLite session via SqlAlchemyUnitOfWork. Permission and
audit services are stubbed (the BP must not depend on either to
mutate state).
"""
from __future__ import annotations

import unittest
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db.base import Base
from seeker_accounting.db.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work_factory,
)
import seeker_accounting.db.model_registry  # noqa: F401  (register all mappers)

from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.payroll.dto.employee_onboarding_dto import (
    EmployeeOnboardingStartCommand,
    EmployeeOnboardingState,
    EmployeeOnboardingStepUpdate,
    EmployeeOnboardingTransition,
)
from seeker_accounting.modules.payroll.repositories.employee_onboarding_draft_repository import (
    EmployeeOnboardingDraftRepository,
)
from seeker_accounting.modules.payroll.repositories.employee_repository import (
    EmployeeRepository,
)
from seeker_accounting.modules.payroll.services.employee_onboarding_service import (
    EmployeeOnboardingService,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


# ── Stubs ────────────────────────────────────────────────────────────────


class _GrantAllPermissions:
    def require_permission(self, code: str) -> None:  # pragma: no cover - trivial
        return None

    def has_permission(self, code: str) -> bool:  # pragma: no cover - trivial
        return True


class _NoopAudit:
    def __init__(self) -> None:
        self.events: list[tuple[int, str]] = []

    def record_event_in_session(self, session, company_id, command):  # type: ignore[no-untyped-def]
        self.events.append((company_id, command.event_type_code))


# ── Fixture ──────────────────────────────────────────────────────────────


def _seed_company(session: Session) -> int:
    company = Company(
        legal_name="Test Co",
        display_name="Test Co",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()
    return company.id


def _build_service() -> tuple[EmployeeOnboardingService, sessionmaker, int]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF: sessionmaker = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    setup_session = SF()
    try:
        company_id = _seed_company(setup_session)
        setup_session.commit()
    finally:
        setup_session.close()

    uow_factory = create_unit_of_work_factory(SF)
    service = EmployeeOnboardingService(
        unit_of_work_factory=uow_factory,
        draft_repository_factory=EmployeeOnboardingDraftRepository,
        employee_repository_factory=EmployeeRepository,
        permission_service=_GrantAllPermissions(),
        audit_service=_NoopAudit(),
    )
    return service, SF, company_id


def _full_payload() -> dict[str, dict]:
    return {
        "identity": {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
        "employment": {"employee_number": "EMP-001", "hire_date": "2024-01-15"},
        "compensation": {"base_currency_code": "XAF"},
        "payment": {"payment_method_code": "cash"},
        "statutory": {"tax_identifier": "TID-1", "cnps_number": "CNPS-1"},
        "components": {},
    }


# ── Tests ────────────────────────────────────────────────────────────────


class EmployeeOnboardingServiceTests(unittest.TestCase):
    def test_start_draft_initial_state_is_draft_identity(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        self.assertEqual(dto.status_code, EmployeeOnboardingState.DRAFT_IDENTITY.value)
        self.assertEqual(dto.current_step, EmployeeOnboardingState.DRAFT_IDENTITY.value)
        self.assertEqual(set(dto.payload.keys()), {
            "identity", "employment", "compensation", "payment", "statutory", "components",
        })

    def test_start_draft_rejects_zero_company(self) -> None:
        service, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.start_draft(EmployeeOnboardingStartCommand(company_id=0))

    def test_update_step_persists_payload(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        updated = service.update_step(
            company_id,
            EmployeeOnboardingStepUpdate(
                draft_id=dto.id,
                step_code="identity",
                patch={"first_name": "Ada", "last_name": "Lovelace"},
            ),
        )
        self.assertEqual(updated.payload["identity"]["first_name"], "Ada")

    def test_update_step_unknown_raises(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        with self.assertRaises(ValidationError):
            service.update_step(
                company_id,
                EmployeeOnboardingStepUpdate(
                    draft_id=dto.id, step_code="bogus", patch={}
                ),
            )

    def test_forward_transition_blocked_when_step_incomplete(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        # identity is empty → cannot advance
        with self.assertRaises(ValidationError):
            service.transition_state(
                company_id,
                EmployeeOnboardingTransition(
                    draft_id=dto.id,
                    target_state=EmployeeOnboardingState.DRAFT_EMPLOYMENT.value,
                ),
            )

    def test_forward_transition_one_step_when_complete(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        service.update_step(
            company_id,
            EmployeeOnboardingStepUpdate(
                draft_id=dto.id,
                step_code="identity",
                patch={"first_name": "Ada", "last_name": "Lovelace"},
            ),
        )
        moved = service.transition_state(
            company_id,
            EmployeeOnboardingTransition(
                draft_id=dto.id,
                target_state=EmployeeOnboardingState.DRAFT_EMPLOYMENT.value,
            ),
        )
        self.assertEqual(moved.status_code, EmployeeOnboardingState.DRAFT_EMPLOYMENT.value)

    def test_forward_skipping_steps_blocked(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        service.update_step(
            company_id,
            EmployeeOnboardingStepUpdate(
                draft_id=dto.id,
                step_code="identity",
                patch={"first_name": "Ada", "last_name": "Lovelace"},
            ),
        )
        with self.assertRaises(ValidationError):
            service.transition_state(
                company_id,
                EmployeeOnboardingTransition(
                    draft_id=dto.id,
                    target_state=EmployeeOnboardingState.DRAFT_PAYMENT.value,
                ),
            )

    def test_back_transition_skips_validation(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        service.update_step(
            company_id,
            EmployeeOnboardingStepUpdate(
                draft_id=dto.id,
                step_code="identity",
                patch={"first_name": "Ada", "last_name": "Lovelace"},
            ),
        )
        moved = service.transition_state(
            company_id,
            EmployeeOnboardingTransition(
                draft_id=dto.id,
                target_state=EmployeeOnboardingState.DRAFT_EMPLOYMENT.value,
            ),
        )
        # Now go back without filling employment.
        back = service.transition_state(
            company_id,
            EmployeeOnboardingTransition(
                draft_id=moved.id,
                target_state=EmployeeOnboardingState.DRAFT_IDENTITY.value,
            ),
        )
        self.assertEqual(back.status_code, EmployeeOnboardingState.DRAFT_IDENTITY.value)

    def test_abandon_then_edit_blocked(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        service.transition_state(
            company_id,
            EmployeeOnboardingTransition(
                draft_id=dto.id,
                target_state=EmployeeOnboardingState.ABANDONED.value,
                abandon_reason="testing",
            ),
        )
        with self.assertRaises(ConflictError):
            service.update_step(
                company_id,
                EmployeeOnboardingStepUpdate(
                    draft_id=dto.id, step_code="identity", patch={"first_name": "X"}
                ),
            )

    def test_complete_requires_review_state(self) -> None:
        service, _, company_id = _build_service()
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        with self.assertRaises(ConflictError):
            service.complete(company_id, dto.id)

    def _drive_to_review(self, service: EmployeeOnboardingService, company_id: int) -> int:
        dto = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        payload = _full_payload()
        steps = ("identity", "employment", "compensation", "payment", "statutory", "components")
        states = (
            EmployeeOnboardingState.DRAFT_EMPLOYMENT,
            EmployeeOnboardingState.DRAFT_COMPENSATION,
            EmployeeOnboardingState.DRAFT_PAYMENT,
            EmployeeOnboardingState.DRAFT_STATUTORY,
            EmployeeOnboardingState.DRAFT_COMPONENTS,
            EmployeeOnboardingState.DRAFT_REVIEW,
        )
        for step, target in zip(steps, states):
            service.update_step(
                company_id,
                EmployeeOnboardingStepUpdate(
                    draft_id=dto.id, step_code=step, patch=payload[step]
                ),
            )
            service.transition_state(
                company_id,
                EmployeeOnboardingTransition(
                    draft_id=dto.id, target_state=target.value
                ),
            )
        return dto.id

    def test_complete_materialises_employee(self) -> None:
        service, SF, company_id = _build_service()
        draft_id = self._drive_to_review(service, company_id)
        finalised = service.complete(company_id, draft_id)
        self.assertEqual(finalised.status_code, EmployeeOnboardingState.COMPLETED.value)
        self.assertIsNotNone(finalised.produced_employee_id)
        # Verify the Employee row exists.
        with SF() as s:
            from seeker_accounting.modules.payroll.models.employee import Employee
            emp = s.query(Employee).filter_by(employee_number="EMP-001").one()
            self.assertEqual(emp.first_name, "Ada")
            self.assertEqual(emp.hire_date, date(2024, 1, 15))
            self.assertEqual(emp.cnps_number, "CNPS-1")

    def test_complete_idempotent(self) -> None:
        service, _, company_id = _build_service()
        draft_id = self._drive_to_review(service, company_id)
        first = service.complete(company_id, draft_id)
        second = service.complete(company_id, draft_id)
        self.assertEqual(first.produced_employee_id, second.produced_employee_id)

    def test_complete_rejects_duplicate_employee_number(self) -> None:
        service, SF, company_id = _build_service()
        # Pre-seed an Employee with the same number.
        with SF() as s:
            from seeker_accounting.modules.payroll.models.employee import Employee
            s.add(
                Employee(
                    company_id=company_id,
                    employee_number="EMP-001",
                    display_name="Existing",
                    first_name="Existing",
                    last_name="Person",
                    hire_date=date(2023, 1, 1),
                    base_currency_code="XAF",
                    is_active=True,
                )
            )
            s.commit()
        draft_id = self._drive_to_review(service, company_id)
        with self.assertRaises(ConflictError):
            service.complete(company_id, draft_id)

    def test_get_draft_not_found(self) -> None:
        service, _, company_id = _build_service()
        with self.assertRaises(NotFoundError):
            service.get_draft(company_id, 9999)

    def test_list_active_drafts_excludes_terminal(self) -> None:
        service, _, company_id = _build_service()
        a = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        b = service.start_draft(EmployeeOnboardingStartCommand(company_id=company_id))
        service.transition_state(
            company_id,
            EmployeeOnboardingTransition(
                draft_id=a.id,
                target_state=EmployeeOnboardingState.ABANDONED.value,
            ),
        )
        active = service.list_active_drafts(company_id)
        ids = {d.id for d in active}
        self.assertIn(b.id, ids)
        self.assertNotIn(a.id, ids)


if __name__ == "__main__":
    unittest.main()
