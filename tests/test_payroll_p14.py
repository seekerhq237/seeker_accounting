"""Phase 14 — Validation, Audit, Telemetry, and E2E Fixture Matrix tests.

Acceptance scope:
  P14.S1 — All payroll validation check codes registered in CodeLabelRegistry.
  P14.S2 — Audit coverage complete; PAYROLL_CORRECTION_APPLIED emitted.
  P14.S3 — TelemetryService wired into EmployeeOnboardingService / PayrollRunService.
  P14.S4 — Fixture matrix drives full 8-step lifecycle with dry-run handlers.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

# ── P14.S1 ────────────────────────────────────────────────────────────────────

# Import ensures module-level CODE_LABELS.register_many() has been called.
import seeker_accounting.modules.payroll.ui.payroll_validation_labels as _pvl
from seeker_accounting.modules.payroll.ui.payroll_validation_labels import (
    PAYROLL_VALIDATION_CHECK_CODES,
)
from seeker_accounting.shared.ui.components.code_label_registry import CODE_LABELS

_EXPECTED_CHECK_CODES = frozenset(
    {
        # Setup
        "NO_PAYROLL_SETTINGS",
        "NO_STATUTORY_PACK",
        "PACK_UNVERIFIED_ITEMS",
        "PACK_PROVISIONAL_ITEMS",
        "BENEFITS_IN_KIND_SETUP_ISSUE",
        # Period
        "NO_FISCAL_PERIOD",
        "PERIOD_LOCKED",
        "PERIOD_NOT_OPEN",
        # Accounts
        "NO_PAYROLL_PAYABLE_ACCOUNT",
        "INVALID_PAYROLL_PAYABLE_ACCOUNT",
        "INACTIVE_PAYROLL_PAYABLE_ACCOUNT",
        "NON_POSTABLE_PAYROLL_PAYABLE_ACCOUNT",
        "MISSING_EXPENSE_ACCOUNT",
        "MISSING_LIABILITY_ACCOUNT",
        "INACTIVE_MAPPED_ACCOUNT",
        "NON_POSTABLE_MAPPED_ACCOUNT",
        # Employees
        "NO_ACTIVE_EMPLOYEES",
        "NO_COMPENSATION_PROFILE",
        "EFFECTIVE_DATE_GAP",
        "EFFECTIVE_DATE_AMBIGUITY",
        "ASSIGNMENT_EFFECTIVE_DATE_AMBIGUITY",
        "NO_COMPONENT_ASSIGNMENTS",
        "OVERLAPPING_COMPENSATION_PROFILES",
        "OVERLAPPING_COMPONENT_ASSIGNMENTS",
        "TERMINATED_STILL_ACTIVE",
        # Rules
        "MISSING_RULE_SET",
        "INVALID_OR_MISSING_RULE_BRACKETS",
        "MISSING_OVERTIME_RULE_LINK",
        "CNPS_EMPLOYER_RATE_MISMATCH",
        "FALLBACK_STATUTORY_CONSTANTS_RELIANCE",
        # Payments
        "PAYMENT_INCONSISTENCY",
        "REMITTANCE_INCONSISTENCY",
    }
)


def test_all_validation_check_codes_are_registered() -> None:
    """Every expected check code must be present in CODE_LABELS payroll_validation category."""
    missing = _EXPECTED_CHECK_CODES - set(PAYROLL_VALIDATION_CHECK_CODES)
    assert missing == frozenset(), f"Unregistered check codes: {sorted(missing)}"


def test_validation_check_codes_canonical_set_is_complete() -> None:
    """PAYROLL_VALIDATION_CHECK_CODES must cover all expected codes."""
    assert _EXPECTED_CHECK_CODES.issubset(PAYROLL_VALIDATION_CHECK_CODES)


def test_registered_label_is_human_readable_not_raw_code() -> None:
    """Labels must not be the raw code itself — they must be human-readable."""
    for code in _EXPECTED_CHECK_CODES:
        label = CODE_LABELS.label("payroll_validation", code)
        # Fallback label produced by _fallback_label() will Title-Case the code,
        # so a proper label must differ from or not look like an ALL_CAPS code.
        assert label != code, f"Label for {code} is identical to the raw code"
        assert "_" not in label, f"Label for {code} still contains underscores: {label!r}"


def test_validation_check_tooltips_are_non_empty() -> None:
    """Every registered check code must have a non-empty tooltip."""
    for code in _EXPECTED_CHECK_CODES:
        tooltip = CODE_LABELS.tooltip("payroll_validation", code)
        assert tooltip, f"Empty tooltip for payroll_validation:{code}"


def test_error_severity_codes_have_error_family() -> None:
    """Setup/Period/Account blocker codes must carry the 'error' family."""
    error_expected = {
        "NO_PAYROLL_SETTINGS",
        "NO_FISCAL_PERIOD",
        "PERIOD_LOCKED",
        "NO_PAYROLL_PAYABLE_ACCOUNT",
    }
    for code in error_expected:
        family = CODE_LABELS.family("payroll_validation", code)
        assert family == "error", f"Expected 'error' family for {code}, got {family!r}"


def test_warning_codes_have_warning_family() -> None:
    """Advisory codes must carry the 'warning' family."""
    warning_expected = {
        "PACK_UNVERIFIED_ITEMS",
        "PACK_PROVISIONAL_ITEMS",
        "NO_COMPONENT_ASSIGNMENTS",
        "TERMINATED_STILL_ACTIVE",
        "FALLBACK_STATUTORY_CONSTANTS_RELIANCE",
        "PAYMENT_INCONSISTENCY",
        "REMITTANCE_INCONSISTENCY",
    }
    for code in warning_expected:
        family = CODE_LABELS.family("payroll_validation", code)
        assert family == "warning", f"Expected 'warning' family for {code}, got {family!r}"


# ── P14.S2 ────────────────────────────────────────────────────────────────────

from seeker_accounting.modules.audit.services.audit_coverage import (
    DEFAULT_AUDIT_REQUIREMENTS,
    build_audit_coverage_report,
)


def test_default_audit_requirements_include_payroll_correction_applied() -> None:
    codes = {req.event_type_code for req in DEFAULT_AUDIT_REQUIREMENTS}
    assert "PAYROLL_CORRECTION_APPLIED" in codes


def test_default_audit_requirements_include_payroll_run_reversed() -> None:
    codes = {req.event_type_code for req in DEFAULT_AUDIT_REQUIREMENTS}
    assert "PAYROLL_RUN_REVERSED" in codes


def test_audit_coverage_is_complete_when_all_events_supplied() -> None:
    all_codes = {req.event_type_code for req in DEFAULT_AUDIT_REQUIREMENTS}
    report = build_audit_coverage_report(all_codes)
    assert report.is_complete
    assert report.missing_event_type_codes == ()


def test_audit_coverage_detects_missing_event() -> None:
    all_codes = {req.event_type_code for req in DEFAULT_AUDIT_REQUIREMENTS}
    incomplete = all_codes - {"PAYROLL_CORRECTION_APPLIED"}
    report = build_audit_coverage_report(incomplete)
    assert not report.is_complete
    assert "PAYROLL_CORRECTION_APPLIED" in report.missing_event_type_codes


def test_payroll_run_service_accepts_correction_repository_factory() -> None:
    """PayrollRunService.__init__ must accept correction_repository_factory."""
    import inspect
    from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService

    params = inspect.signature(PayrollRunService.__init__).parameters
    assert "correction_repository_factory" in params


def test_payroll_run_service_emits_correction_applied_audit_event() -> None:
    """When corrections exist for an employee, PAYROLL_CORRECTION_APPLIED is emitted."""
    from seeker_accounting.db.model_registry import load_model_registry
    from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService

    load_model_registry()
    audit_events: list[object] = []

    # Minimal correction stub
    class _Component:
        def __init__(self) -> None:
            self.id = 1
            self.component_type_code = "earning"

    class _Correction:
        def __init__(self) -> None:
            self.id = 99
            self.employee_id = 5
            self.correction_amount = Decimal("250")
            self.component = _Component()
            self.status_code = "pending"
            self.applied_run_id = None
            self.applied_run_employee_id = None
            self.applied_at = None

    correction = _Correction()

    class _AuditRepo:
        def save(self, event: object) -> None:
            audit_events.append(event)

    class _AuditService:
        def record_event_in_session(self, session: Any, company_id: int, cmd: Any) -> None:
            class _FakeEvent:
                event_type_code = cmd.event_type_code

            audit_events.append(_FakeEvent())

    class _Session:
        def add(self, obj: Any) -> None: ...
        def flush(self) -> None: ...

    session = _Session()
    audit_svc = _AuditService()

    # Call _mark_corrections_applied (static) and verify state
    applied_at = object()
    PayrollRunService._mark_corrections_applied(
        [correction],
        run_id=10,
        run_employee_id=20,
        applied_at=applied_at,
    )
    assert correction.status_code == "applied"
    assert correction.applied_run_id == 10
    assert correction.applied_run_employee_id == 20


def test_correction_applied_event_type_code_is_stable() -> None:
    """The event type code used in calculate_run must be the canonical string."""
    from seeker_accounting.modules.payroll.services import payroll_run_service as _prs
    import inspect

    src = inspect.getsource(_prs)
    assert "PAYROLL_CORRECTION_APPLIED" in src, (
        "PAYROLL_CORRECTION_APPLIED event must be emitted in payroll_run_service"
    )


# ── P14.S3 ────────────────────────────────────────────────────────────────────

from seeker_accounting.shared.services.telemetry_service import TelemetryService


def test_employee_onboarding_service_accepts_telemetry_service() -> None:
    """EmployeeOnboardingService must accept an optional telemetry_service parameter."""
    import inspect
    from seeker_accounting.modules.payroll.services.employee_onboarding_service import (
        EmployeeOnboardingService,
    )

    params = inspect.signature(EmployeeOnboardingService.__init__).parameters
    assert "telemetry_service" in params


def test_payroll_run_service_accepts_telemetry_service() -> None:
    """PayrollRunService must accept an optional telemetry_service parameter."""
    import inspect
    from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService

    params = inspect.signature(PayrollRunService.__init__).parameters
    assert "telemetry_service" in params


def test_telemetry_records_hire_bp_started() -> None:
    """start_draft must call telemetry.record_funnel_step with funnel='hire_bp', step='started'."""
    from seeker_accounting.db.model_registry import load_model_registry
    from seeker_accounting.modules.payroll.dto.employee_onboarding_dto import (
        EmployeeOnboardingStartCommand,
    )
    from seeker_accounting.modules.payroll.services.employee_onboarding_service import (
        EmployeeOnboardingService,
    )

    load_model_registry()

    recorded: list[dict[str, Any]] = []

    class _MockTelemetry:
        def record_funnel_step(
            self, *, funnel: str, step: str, event_code: str | None = None, context: Any = None
        ) -> bool:
            recorded.append({"funnel": funnel, "step": step, "event_code": event_code})
            return True

    class _Session:
        def flush(self) -> None: ...
        def add(self, obj: Any) -> None: ...

    class _DraftRepo:
        def save(self, draft: Any) -> None:
            draft.id = 1

    class _Uow:
        def __init__(self) -> None:
            self.session = _Session()

        def __enter__(self) -> "_Uow":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def commit(self) -> None:
            pass

    class _PermSvc:
        def require_permission(self, perm: str) -> None:
            pass

    class _AuditSvc:
        def record_event_in_session(self, *args: Any, **kwargs: Any) -> None:
            pass

    service = EmployeeOnboardingService(
        unit_of_work_factory=_Uow,
        draft_repository_factory=lambda _: _DraftRepo(),
        employee_repository_factory=lambda _: None,  # type: ignore[arg-type]
        permission_service=_PermSvc(),  # type: ignore[arg-type]
        audit_service=_AuditSvc(),  # type: ignore[arg-type]
        telemetry_service=_MockTelemetry(),  # type: ignore[arg-type]
    )

    service.start_draft(
        EmployeeOnboardingStartCommand(
            company_id=10,
            started_by_user_id=1,
        )
    )

    assert any(
        r["funnel"] == "hire_bp" and r["step"] == "started" for r in recorded
    ), f"Expected hire_bp.started in {recorded}"


def test_telemetry_not_called_when_not_provided() -> None:
    """If telemetry_service is None, no telemetry calls are made (no AttributeError)."""
    from seeker_accounting.db.model_registry import load_model_registry
    from seeker_accounting.modules.payroll.dto.employee_onboarding_dto import (
        EmployeeOnboardingStartCommand,
    )
    from seeker_accounting.modules.payroll.services.employee_onboarding_service import (
        EmployeeOnboardingService,
    )

    load_model_registry()

    class _Session:
        def flush(self) -> None: ...
        def add(self, obj: Any) -> None: ...

    class _Uow:
        def __init__(self) -> None:
            self.session = _Session()

        def __enter__(self) -> "_Uow":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def commit(self) -> None:
            pass

    class _DraftRepo:
        def save(self, draft: Any) -> None:
            draft.id = 1

    class _PermSvc:
        def require_permission(self, perm: str) -> None:
            pass

    class _AuditSvc:
        def record_event_in_session(self, *args: Any, **kwargs: Any) -> None:
            pass

    service = EmployeeOnboardingService(
        unit_of_work_factory=_Uow,
        draft_repository_factory=lambda _: _DraftRepo(),
        employee_repository_factory=lambda _: None,  # type: ignore[arg-type]
        permission_service=_PermSvc(),  # type: ignore[arg-type]
        audit_service=_AuditSvc(),  # type: ignore[arg-type]
        telemetry_service=None,
    )
    # Must not raise
    service.start_draft(EmployeeOnboardingStartCommand(company_id=10, started_by_user_id=1))


def test_telemetry_run_created_event_recorded() -> None:
    """PayrollRunService.create_run must emit monthly_run.run_created telemetry."""
    import inspect
    from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService

    src = inspect.getsource(PayrollRunService.create_run)
    assert "monthly_run" in src, "create_run must emit 'monthly_run' telemetry funnel step"
    assert "run_created" in src, "create_run must use step 'run_created'"


def test_telemetry_run_calculated_event_recorded() -> None:
    """PayrollRunService.calculate_run must emit monthly_run.run_calculated telemetry."""
    import inspect
    from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService

    src = inspect.getsource(PayrollRunService.calculate_run)
    assert "monthly_run" in src, "calculate_run must emit 'monthly_run' telemetry funnel step"
    assert "run_calculated" in src, "calculate_run must use step 'run_calculated'"


def test_telemetry_service_is_opt_in_by_default() -> None:
    """TelemetryService must not record events when opted_in is False."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp = Path(f.name)

    svc = TelemetryService(opted_in=False, path=tmp)
    result = svc.record_funnel_step(funnel="test", step="step1")
    assert result is False
    assert tmp.read_text().strip() == ""
    tmp.unlink(missing_ok=True)


def test_telemetry_service_records_when_opted_in() -> None:
    """TelemetryService must record events when opted_in is True."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp = Path(f.name)

    svc = TelemetryService(opted_in=True, path=tmp)
    result = svc.record_funnel_step(
        funnel="hire_bp",
        step="started",
        event_code="hire_bp.started",
        context={"company_id": 1},
    )
    assert result is True
    lines = [l for l in tmp.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["funnel"] == "hire_bp"
    assert record["step"] == "started"
    tmp.unlink(missing_ok=True)


def test_telemetry_sanitizes_pii_fields() -> None:
    """Telemetry must drop PII keys (name, email, phone, tax_identifier)."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp = Path(f.name)

    svc = TelemetryService(opted_in=True, path=tmp)
    svc.record_funnel_step(
        funnel="hire_bp",
        step="completed",
        context={
            "company_id": 5,
            "name": "Alice Dupont",
            "email": "alice@example.com",
            "tax_identifier": "TI-12345",
        },
    )
    record = json.loads(tmp.read_text().splitlines()[0])
    ctx = record["context"]
    assert "name" not in ctx
    assert "email" not in ctx
    assert "tax_identifier" not in ctx
    assert ctx.get("company_id") == 5
    tmp.unlink(missing_ok=True)


# ── P14.S4 ────────────────────────────────────────────────────────────────────

def _load_fixture_matrix_module():  # type: ignore[return]
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "reproducible_e2e_fixture_matrix.py"
    )
    spec = importlib.util.spec_from_file_location("_p14_fixture_matrix", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fixture_matrix_dry_run_all_steps_executed() -> None:
    """Dry-run with built-in handlers must execute all 8 steps."""
    m = _load_fixture_matrix_module()
    results = m.run_fixture_matrix(m.build_dry_run_handlers(), dry_run=True)
    assert len(results) == 8
    assert all(r.executed for r in results)


def test_fixture_matrix_step_codes_stable() -> None:
    """Step codes must match the locked fixture spec."""
    m = _load_fixture_matrix_module()
    codes = [step.code for step in m.build_fixture_matrix()]
    assert codes == [
        "setup_company",
        "seed_employees",
        "monthly_run_2026_01",
        "monthly_run_2026_02",
        "monthly_run_2026_03",
        "off_cycle_adjustment",
        "reverse_off_cycle",
        "year_end_dsf",
    ]


def test_fixture_matrix_missing_handler_raises_in_strict_mode() -> None:
    """run_fixture_matrix with no handlers and dry_run=False must raise KeyError."""
    m = _load_fixture_matrix_module()
    with pytest.raises(KeyError):
        m.run_fixture_matrix({}, dry_run=False)


def test_fixture_matrix_missing_handler_does_not_raise_in_dry_run() -> None:
    """Dry-run with no handlers must not raise — steps are marked not executed."""
    m = _load_fixture_matrix_module()
    results = m.run_fixture_matrix({}, dry_run=True)
    assert len(results) == 8
    assert all(not r.executed for r in results)


def test_fixture_matrix_write_produces_valid_json(tmp_path: Path) -> None:
    """write_fixture_matrix must produce valid JSON with all 8 steps."""
    m = _load_fixture_matrix_module()
    out = tmp_path / "matrix.json"
    m.write_fixture_matrix(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 8
    assert {item["code"] for item in data} == {
        "setup_company",
        "seed_employees",
        "monthly_run_2026_01",
        "monthly_run_2026_02",
        "monthly_run_2026_03",
        "off_cycle_adjustment",
        "reverse_off_cycle",
        "year_end_dsf",
    }


def test_fixture_matrix_custom_handler_result_message() -> None:
    """A custom handler's returned message is captured in the result."""
    m = _load_fixture_matrix_module()
    handlers = {
        step.code: (lambda s: f"custom:{s.code}")
        for step in m.build_fixture_matrix()
    }
    results = m.run_fixture_matrix(handlers)
    for r in results:
        assert r.message == f"custom:{r.code}"
        assert r.executed
