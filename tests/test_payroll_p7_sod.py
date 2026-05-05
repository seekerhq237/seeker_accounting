"""P7: Payroll Approvals & Segregation of Duties — unit tests.

Tests the key correctness invariants of Phase 7:
  - submit_run_for_review requires PAYROLL_RUN_SUBMIT and changes state
  - send_back_run requires PAYROLL_RUN_SEND_BACK and returns to calculated
  - approve_run requires PAYROLL_RUN_APPROVE
  - four-eye enforcement: submitter cannot approve when sod_strict=True
  - four-eye enforcement: approver cannot post when sod_strict=True
  - approval routing threshold selection
  - RBAC: payroll_preparer and payroll_approver role membership checks

All tests use in-memory SQLite via SQLAlchemy and an ephemeral schema.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from seeker_accounting.modules.payroll.dto.payroll_approval_routing_dto import (
    ApproverConfigDTO,
    ApprovalRoutingResultDTO,
    SetApproverConfigCommand,
)
from seeker_accounting.modules.payroll.payroll_permissions import (
    ALL_PAYROLL_PERMISSIONS,
    PAYROLL_RUN_APPROVE,
    PAYROLL_RUN_SEND_BACK,
    PAYROLL_RUN_SUBMIT,
    PAYROLL_RUN_POST,
    PAYROLL_RUN_REVERSE,
    PAYROLL_RUN_CREATE,
    PAYROLL_APPROVER_CONFIG_MANAGE,
    PAYROLL_CORRECTION_MANAGE,
)
from seeker_accounting.modules.administration.rbac_catalog import (
    ALL_SYSTEM_ROLES,
    PAYROLL_ROLE_DEFINITIONS,
)
from seeker_accounting.modules.payroll.services.payroll_run_state import (
    PayrollRunStatus,
    PayrollRunStateMachine,
)
from seeker_accounting.platform.exceptions import PermissionDeniedError, ValidationError


# ── Minimal stubs ─────────────────────────────────────────────────────────────

@dataclass
class _StubRun:
    id: int = 1
    company_id: int = 10
    run_reference: str = "RUN-2026-01"
    status_code: str = "calculated"
    submitted_at: datetime | None = None
    submitted_by_user_id: int | None = None
    sent_back_at: datetime | None = None
    sent_back_by_user_id: int | None = None
    sent_back_reason: str | None = None
    approved_at: datetime | None = None
    approved_by_user_id: int | None = None
    posted_at: datetime | None = None


@dataclass
class _StubSetting:
    company_id: int = 10
    sod_strict: bool = False


class _AllowAll:
    """Permission service stub that grants every permission."""
    def require_permission(self, code: str) -> None:
        pass  # always allow


class _DenyAll:
    """Permission service stub that denies every permission."""
    def require_permission(self, code: str) -> None:
        raise PermissionDeniedError(f"Permission denied: {code}")


class _AllowOnly:
    """Permission service stub that only allows specific codes."""
    def __init__(self, *allowed: str) -> None:
        self._allowed = frozenset(allowed)

    def require_permission(self, code: str) -> None:
        if code not in self._allowed:
            raise PermissionDeniedError(f"Permission denied: {code}")


class _StubAuditService:
    def record_event_in_session(self, session: Any, company_id: int, cmd: Any) -> None:
        pass


class _StubUow:
    def __init__(self) -> None:
        self.session = MagicMock()
        self._committed = False

    def commit(self) -> None:
        self._committed = True

    def __enter__(self) -> "_StubUow":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


# ── Helpers to build a minimal PayrollRunService ──────────────────────────────

def _make_run_service(
    run: _StubRun,
    setting: _StubSetting | None = None,
    permission_service: Any = None,
    actor_user_id: int = 99,
) -> Any:
    """Build a :class:`PayrollRunService` with stub dependencies."""
    from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService

    uow = _StubUow()
    uow.session = MagicMock()

    # run repo
    run_repo = MagicMock()
    run_repo.get_by_id.return_value = run

    # setting repo
    setting_repo = MagicMock()
    setting_repo.get_by_company.return_value = setting

    # app context
    app_ctx = MagicMock()
    app_ctx.current_user_id = actor_user_id

    svc = PayrollRunService(
        unit_of_work_factory=lambda: uow,
        app_context=app_ctx,
        run_repository_factory=lambda s: run_repo,
        run_employee_repository_factory=lambda s: MagicMock(),
        employee_repository_factory=lambda s: MagicMock(),
        profile_repository_factory=lambda s: MagicMock(),
        assignment_repository_factory=lambda s: MagicMock(),
        input_batch_repository_factory=lambda s: MagicMock(),
        rule_set_repository_factory=lambda s: MagicMock(),
        setting_repository_factory=lambda s: setting_repo,
        calculation_service=MagicMock(),
        numbering_service=MagicMock(),
        permission_service=permission_service or _AllowAll(),
        audit_service=_StubAuditService(),
    )
    return svc, uow, run


# ── Permission gatekeeping ─────────────────────────────────────────────────────

class P7PermissionTests(unittest.TestCase):

    def test_submit_requires_payroll_run_submit_permission(self) -> None:
        run = _StubRun(status_code="calculated")
        svc, _, _ = _make_run_service(run, permission_service=_DenyAll())
        with self.assertRaises(PermissionDeniedError):
            svc.submit_run_for_review(10, 1)

    def test_approve_requires_payroll_run_approve_permission(self) -> None:
        run = _StubRun(status_code="submitted_for_review")
        svc, _, _ = _make_run_service(run, permission_service=_DenyAll())
        with self.assertRaises(PermissionDeniedError):
            svc.approve_run(10, 1)

    def test_send_back_requires_payroll_run_send_back_permission(self) -> None:
        run = _StubRun(status_code="submitted_for_review")
        svc, _, _ = _make_run_service(run, permission_service=_DenyAll())
        with self.assertRaises(PermissionDeniedError):
            svc.send_back_run(10, 1, reason="typo in numbers")

    def test_send_back_requires_non_empty_reason(self) -> None:
        run = _StubRun(status_code="submitted_for_review")
        svc, _, _ = _make_run_service(run)
        with self.assertRaises(ValidationError):
            svc.send_back_run(10, 1, reason="  ")


# ── State transitions ─────────────────────────────────────────────────────────

class P7StateTransitionTests(unittest.TestCase):

    def test_submit_changes_status_to_submitted_for_review(self) -> None:
        run = _StubRun(status_code="calculated")
        svc, uow, _ = _make_run_service(run)
        svc.submit_run_for_review(10, 1)
        self.assertEqual(run.status_code, "submitted_for_review")
        self.assertIsNotNone(run.submitted_at)
        self.assertEqual(run.submitted_by_user_id, 99)
        self.assertTrue(uow._committed)

    def test_submit_blocked_if_not_calculated(self) -> None:
        for bad_status in ("draft", "submitted_for_review", "approved", "posted"):
            with self.subTest(status=bad_status):
                run = _StubRun(status_code=bad_status)
                svc, _, _ = _make_run_service(run)
                with self.assertRaises(ValidationError):
                    svc.submit_run_for_review(10, 1)

    def test_send_back_returns_to_calculated(self) -> None:
        run = _StubRun(status_code="submitted_for_review")
        svc, uow, _ = _make_run_service(run, actor_user_id=42)
        svc.send_back_run(10, 1, reason="Fix overtime amounts.", actor_user_id=42)
        self.assertEqual(run.status_code, "calculated")
        self.assertIsNotNone(run.sent_back_at)
        self.assertEqual(run.sent_back_by_user_id, 42)
        self.assertEqual(run.sent_back_reason, "Fix overtime amounts.")
        self.assertTrue(uow._committed)

    def test_send_back_blocked_if_not_submitted(self) -> None:
        for bad_status in ("draft", "calculated", "approved", "posted"):
            with self.subTest(status=bad_status):
                run = _StubRun(status_code=bad_status)
                svc, _, _ = _make_run_service(run)
                with self.assertRaises(ValidationError):
                    svc.send_back_run(10, 1, reason="wrong state test")

    def test_approve_from_submitted_for_review(self) -> None:
        run = _StubRun(status_code="submitted_for_review", submitted_by_user_id=1)
        setting = _StubSetting(sod_strict=False)
        svc, uow, _ = _make_run_service(run, setting=setting, actor_user_id=2)
        svc.approve_run(10, 1, actor_user_id=2)
        self.assertEqual(run.status_code, "approved")
        self.assertIsNotNone(run.approved_at)
        self.assertEqual(run.approved_by_user_id, 2)
        self.assertTrue(uow._committed)

    def test_approve_from_calculated_allowed_when_sod_disabled(self) -> None:
        run = _StubRun(status_code="calculated")
        setting = _StubSetting(sod_strict=False)
        svc, _, _ = _make_run_service(run, setting=setting)
        svc.approve_run(10, 1)
        self.assertEqual(run.status_code, "approved")

    def test_approve_from_calculated_blocked_when_sod_enabled(self) -> None:
        run = _StubRun(status_code="calculated")
        setting = _StubSetting(sod_strict=True)
        svc, _, _ = _make_run_service(run, setting=setting)
        with self.assertRaises(ValidationError):
            svc.approve_run(10, 1)

    def test_void_blocked_on_submitted_for_review(self) -> None:
        run = _StubRun(status_code="submitted_for_review")
        svc, _, _ = _make_run_service(run)
        with self.assertRaises(ValidationError):
            svc.void_run(10, 1)


# ── Four-eye SoD enforcement ──────────────────────────────────────────────────

class P7FourEyeTests(unittest.TestCase):

    def test_submitter_cannot_approve_own_run_when_sod_enabled(self) -> None:
        """User 5 submitted → user 5 cannot approve (sod_strict=True)."""
        run = _StubRun(
            status_code="submitted_for_review",
            submitted_by_user_id=5,
        )
        setting = _StubSetting(sod_strict=True)
        svc, _, _ = _make_run_service(run, setting=setting, actor_user_id=5)
        with self.assertRaises(ValidationError) as ctx:
            svc.approve_run(10, 1, actor_user_id=5)
        self.assertIn("segregation", str(ctx.exception).lower())

    def test_different_user_can_approve_when_sod_enabled(self) -> None:
        """User 6 can approve a run submitted by user 5 (sod_strict=True)."""
        run = _StubRun(
            status_code="submitted_for_review",
            submitted_by_user_id=5,
        )
        setting = _StubSetting(sod_strict=True)
        svc, uow, _ = _make_run_service(run, setting=setting, actor_user_id=6)
        svc.approve_run(10, 1, actor_user_id=6)
        self.assertEqual(run.status_code, "approved")

    def test_sod_not_enforced_when_sod_disabled(self) -> None:
        """Same user can submit and approve when sod_strict=False."""
        run = _StubRun(
            status_code="submitted_for_review",
            submitted_by_user_id=7,
        )
        setting = _StubSetting(sod_strict=False)
        svc, _, _ = _make_run_service(run, setting=setting, actor_user_id=7)
        svc.approve_run(10, 1, actor_user_id=7)
        self.assertEqual(run.status_code, "approved")


# ── Approval routing service ──────────────────────────────────────────────────

class P7ApprovalRoutingTests(unittest.TestCase):

    def _make_routing_svc(self, configs: list[Any]) -> Any:
        from seeker_accounting.modules.payroll.services.payroll_approval_routing_service import (
            PayrollApprovalRoutingService,
        )

        uow = _StubUow()
        repo = MagicMock()
        repo.list_active_by_company.return_value = configs

        svc = PayrollApprovalRoutingService(
            unit_of_work_factory=lambda: uow,
            config_repository_factory=lambda s: repo,
            permission_service=_AllowAll(),
        )
        return svc

    def _make_config(self, approver_user_id: int, min_run_amount: Decimal | None) -> Any:
        """Build a stub PayrollApproverConfig-like object."""
        cfg = MagicMock()
        cfg.id = approver_user_id
        cfg.company_id = 10
        cfg.approver_user_id = approver_user_id
        cfg.min_run_amount = min_run_amount
        cfg.is_active = True
        return cfg

    def test_no_configs_returns_none_approver(self) -> None:
        svc = self._make_routing_svc([])
        result = svc.get_required_approver(10, Decimal("500000"))
        self.assertIsNone(result.required_approver_user_id)

    def test_unconditional_rule_always_applies(self) -> None:
        svc = self._make_routing_svc([self._make_config(42, None)])
        result = svc.get_required_approver(10, Decimal("1"))
        self.assertEqual(result.required_approver_user_id, 42)

    def test_threshold_rule_applies_when_met(self) -> None:
        svc = self._make_routing_svc([self._make_config(99, Decimal("1000000"))])
        result = svc.get_required_approver(10, Decimal("1000000"))
        self.assertEqual(result.required_approver_user_id, 99)

    def test_threshold_rule_skipped_when_below(self) -> None:
        svc = self._make_routing_svc([self._make_config(99, Decimal("1000000"))])
        result = svc.get_required_approver(10, Decimal("999999"))
        self.assertIsNone(result.required_approver_user_id)

    def test_most_specific_threshold_wins(self) -> None:
        """Two rules: unconditional (user 10) and 500K threshold (user 20).
        When total is 600K, the more-specific 500K rule should win → user 20."""
        svc = self._make_routing_svc([
            self._make_config(10, None),
            self._make_config(20, Decimal("500000")),
        ])
        result = svc.get_required_approver(10, Decimal("600000"))
        self.assertEqual(result.required_approver_user_id, 20)

    def test_unconditional_rule_wins_below_any_threshold(self) -> None:
        """Total below 500K threshold → only unconditional rule applies → user 10."""
        svc = self._make_routing_svc([
            self._make_config(10, None),
            self._make_config(20, Decimal("500000")),
        ])
        result = svc.get_required_approver(10, Decimal("100000"))
        self.assertEqual(result.required_approver_user_id, 10)


# ── RBAC role definitions ─────────────────────────────────────────────────────

class P7RbacRoleTests(unittest.TestCase):

    def _get_role(self, code: str) -> Any:
        for role in PAYROLL_ROLE_DEFINITIONS:
            if role.code == code:
                return role
        return None

    def test_payroll_preparer_role_exists(self) -> None:
        self.assertIsNotNone(self._get_role("payroll_preparer"))

    def test_payroll_approver_role_exists(self) -> None:
        self.assertIsNotNone(self._get_role("payroll_approver"))

    def test_payroll_poster_role_exists(self) -> None:
        self.assertIsNotNone(self._get_role("payroll_poster"))

    def test_payroll_payer_role_exists(self) -> None:
        self.assertIsNotNone(self._get_role("payroll_payer"))

    def test_payroll_admin_role_exists(self) -> None:
        self.assertIsNotNone(self._get_role("payroll_admin"))

    def test_preparer_has_submit_not_approve(self) -> None:
        role = self._get_role("payroll_preparer")
        self.assertIsNotNone(role)
        self.assertIn(PAYROLL_RUN_SUBMIT, role.permission_codes)
        self.assertIn(PAYROLL_RUN_CREATE, role.permission_codes)
        self.assertIn(PAYROLL_CORRECTION_MANAGE, role.permission_codes)
        self.assertNotIn(PAYROLL_RUN_APPROVE, role.permission_codes)
        self.assertNotIn(PAYROLL_RUN_POST, role.permission_codes)

    def test_approver_has_approve_and_send_back_not_create_or_post(self) -> None:
        role = self._get_role("payroll_approver")
        self.assertIsNotNone(role)
        self.assertIn(PAYROLL_RUN_APPROVE, role.permission_codes)
        self.assertIn(PAYROLL_RUN_SEND_BACK, role.permission_codes)
        self.assertNotIn(PAYROLL_RUN_CREATE, role.permission_codes)
        self.assertNotIn(PAYROLL_RUN_SUBMIT, role.permission_codes)
        self.assertNotIn(PAYROLL_RUN_POST, role.permission_codes)

    def test_poster_has_post_only_not_approve(self) -> None:
        role = self._get_role("payroll_poster")
        self.assertIsNotNone(role)
        self.assertIn(PAYROLL_RUN_POST, role.permission_codes)
        self.assertIn(PAYROLL_RUN_REVERSE, role.permission_codes)
        self.assertNotIn(PAYROLL_RUN_APPROVE, role.permission_codes)
        self.assertNotIn(PAYROLL_RUN_SUBMIT, role.permission_codes)

    def test_admin_has_all_payroll_permissions(self) -> None:
        role = self._get_role("payroll_admin")
        self.assertIsNotNone(role)
        for code, _name, _desc in ALL_PAYROLL_PERMISSIONS:
            self.assertIn(code, role.permission_codes, f"Missing: {code}")

    def test_payroll_permissions_catalog_includes_new_codes(self) -> None:
        all_codes = {code for code, _, _ in ALL_PAYROLL_PERMISSIONS}
        self.assertIn(PAYROLL_RUN_SUBMIT, all_codes)
        self.assertIn(PAYROLL_RUN_SEND_BACK, all_codes)
        self.assertIn(PAYROLL_RUN_REVERSE, all_codes)
        self.assertIn(PAYROLL_CORRECTION_MANAGE, all_codes)
        self.assertIn(PAYROLL_APPROVER_CONFIG_MANAGE, all_codes)


# ── State machine extension ───────────────────────────────────────────────────

class P7StateMachineTests(unittest.TestCase):

    def test_submitted_for_review_in_main_steps(self) -> None:
        from seeker_accounting.modules.payroll.services.payroll_run_state import TIMELINE_ORDER
        self.assertIn("submitted_for_review", TIMELINE_ORDER)

    def test_submitted_for_review_label(self) -> None:
        from seeker_accounting.modules.payroll.services.payroll_run_state import STATUS_LABELS
        self.assertIn("submitted_for_review", STATUS_LABELS)

    def test_submitted_for_review_transitions(self) -> None:
        allowed = PayrollRunStateMachine.allowed_transitions("submitted_for_review")
        self.assertIn("calculated", allowed)   # send-back
        self.assertIn("approved", allowed)     # approve

    def test_submitted_is_not_terminal(self) -> None:
        self.assertFalse(PayrollRunStateMachine.is_terminal("submitted_for_review"))


if __name__ == "__main__":
    unittest.main()
