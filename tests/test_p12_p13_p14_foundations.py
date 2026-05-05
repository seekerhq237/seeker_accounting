from __future__ import annotations

import importlib.util
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.navigation.navigation_service import NavigationService
from seeker_accounting.db.model_registry import load_model_registry
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.audit.services.audit_coverage import build_audit_coverage_report
from seeker_accounting.modules.dashboard.services.dashboard_service import DashboardService
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.platform.validation import (
    PredicateRule,
    RequiredFieldRule,
    ValidationEngine,
    require_code,
    require_non_negative_decimal,
    require_text,
)
from seeker_accounting.shared.services.telemetry_service import TelemetryService
from seeker_accounting.shared.services.ui_preferences_service import UiPreferencesService
from seeker_accounting.shared.ui.empty_states import audit_empty_state_coverage
from seeker_accounting.shared.ui.help_content import audit_help_content
from seeker_accounting.shared.ui.layout_constraints import WINDOW_SIZE_TOKENS


def test_dashboard_setup_checklist_builds_progress() -> None:
    checklist = DashboardService._build_setup_checklist_from_counts(
        {
            "fiscal_periods": 12,
            "accounts": 120,
            "document_sequences": 4,
            "customers": 1,
            "suppliers": 0,
            "items": 0,
            "employees": 5,
        }
    )

    assert checklist.total_count == 6
    assert checklist.complete_count == 5
    assert not checklist.is_complete
    assert [item.key for item in checklist.items if not item.is_complete] == ["items"]


def test_empty_state_and_help_audits_are_covered() -> None:
    assert audit_empty_state_coverage(
        {
            "dashboard.no_company",
            "dashboard.recent_activity",
            "dashboard.attention",
            "dashboard.setup_complete",
            "customers.no_company",
            "suppliers.empty",
            "suppliers.no_company",
            "treasury.transactions.empty",
            "treasury.financial_accounts.empty",
            "treasury.no_company",
            "projects.empty",
            "projects.no_company",
            "inventory.items.empty",
            "inventory.no_company",
            "management_reporting.no_selection",
            "management_reporting.no_company",
            "management_reporting.contract_summary.no_selection",
            "management_reporting.project_variance.no_selection",
        }
    ) == ()
    assert audit_help_content() == ()


def test_validation_engine_raises_structured_validation_error() -> None:
    engine = ValidationEngine()
    with pytest.raises(ValidationError) as exc_info:
        engine.validate_or_raise(
            {"name": "", "amount": -1},
            (
                RequiredFieldRule("name", "Name"),
                PredicateRule("amount.positive", "Amount must be positive.", lambda target: target["amount"] > 0, field="amount"),
            ),
        )

    issues = exc_info.value.context["issues"]
    assert [issue["field"] for issue in issues] == ["name", "amount"]


def test_service_validation_helpers_preserve_service_messages() -> None:
    assert require_text("  Acme  ", "Display name") == "Acme"
    assert require_code(" c us 1 ", "Customer code", remove_spaces=True) == "CUS1"
    assert require_non_negative_decimal(Decimal("12.34"), "Credit limit amount") == Decimal("12.34")

    with pytest.raises(ValidationError) as exc_info:
        require_non_negative_decimal(
            Decimal("-1"),
            "Credit limit amount",
            message="Credit limit amount cannot be negative.",
        )

    assert str(exc_info.value) == "Credit limit amount cannot be negative."


def test_ui_preferences_persist_table_density(tmp_path: Path) -> None:
    path = tmp_path / "ui_prefs.json"
    service = UiPreferencesService(path)

    assert service.get_table_density() == "comfortable"
    service.set_table_density("dense")

    assert UiPreferencesService(path).get_table_density() == "dense"


def test_ui_preferences_persist_telemetry_opt_in(tmp_path: Path) -> None:
    path = tmp_path / "ui_prefs.json"
    service = UiPreferencesService(path)

    assert not service.get_telemetry_opted_in()
    service.set_telemetry_opted_in(True)

    assert UiPreferencesService(path).get_telemetry_opted_in()


def test_telemetry_is_opt_in_and_sanitizes_context(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.jsonl"
    service = TelemetryService(opted_in=False, path=path)

    assert not service.record_funnel_step(funnel="setup", step="started")
    assert not path.exists()

    service.set_opted_in(True)
    assert service.record_funnel_step(
        funnel="setup",
        step="completed",
        context={"screen": "dashboard", "email": "hidden@example.com", "count": 3},
    )
    content = path.read_text(encoding="utf-8")
    assert "dashboard" in content
    assert "hidden@example.com" not in content


def test_telemetry_can_read_opt_in_from_preferences(tmp_path: Path) -> None:
    prefs = UiPreferencesService(tmp_path / "ui_prefs.json")
    path = tmp_path / "telemetry.jsonl"
    service = TelemetryService(opted_in=None, path=path, preferences=prefs)

    assert not service.record_funnel_step(funnel="setup", step="displayed")
    prefs.set_telemetry_opted_in(True)

    assert service.record_funnel_step(funnel="setup", step="displayed")


def test_navigation_records_opt_in_telemetry(tmp_path: Path) -> None:
    telemetry_path = tmp_path / "telemetry.jsonl"
    telemetry = TelemetryService(opted_in=True, path=telemetry_path)
    navigation = NavigationService(telemetry_service=telemetry)

    navigation.navigate(nav_ids.CUSTOMERS, context={"customer_id": 42})

    event = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert event["funnel"] == "navigation"
    assert event["step"] == "navigate"
    assert event["context"]["nav_id"] == nav_ids.CUSTOMERS
    assert event["context"]["has_context"]


def test_audit_coverage_reports_missing_events() -> None:
    report = build_audit_coverage_report({"STATE_TRANSITION", "OVERRIDE_APPLIED"})

    assert not report.is_complete
    assert "BUSINESS_PROCESS_STEP" in report.missing_event_type_codes


def test_audit_service_state_transition_helper_builds_structured_event() -> None:
    load_model_registry()
    saved = []

    class _Uow:
        session = object()

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *_args):  # noqa: ANN002, ANN204
            return None

        def commit(self) -> None:
            return None

    class _Repo:
        def save(self, event):  # noqa: ANN001, ANN201
            saved.append(event)

    service = AuditService(
        unit_of_work_factory=lambda: _Uow(),
        app_context=AppContext(
            current_user_id=7,
            current_user_display_name="Tester",
            active_company_id=None,
            active_company_name=None,
            theme_name="light",
        ),
        audit_event_repository_factory=lambda _session: _Repo(),
    )

    service.record_state_transition_in_session(
        object(),  # type: ignore[arg-type]
        1,
        module_code="budgeting",
        entity_type="ProjectBudgetVersion",
        entity_id=9,
        from_state="submitted",
        to_state="approved",
        description="Approved budget version.",
        context={"project_id": 3},
    )

    assert saved[0].event_type_code == "STATE_TRANSITION"
    payload = json.loads(saved[0].detail_json)
    assert payload["from_state"] == "submitted"
    assert payload["to_state"] == "approved"
    assert payload["context"] == {"project_id": 3}

    service.record_override_applied(
        1,
        module_code="inventory",
        entity_type="ItemAccountOverride",
        entity_id=11,
        override_code="ITEM_ACCOUNT_MAPPING",
        reason="Configured for location-specific stock accounting.",
    )

    override_payload = json.loads(saved[1].detail_json)
    assert saved[1].event_type_code == "OVERRIDE_APPLIED"
    assert override_payload["override_code"] == "ITEM_ACCOUNT_MAPPING"
    assert override_payload["reason"] == "Configured for location-specific stock accounting."


def test_layout_resize_literals_are_centralized() -> None:
    assert WINDOW_SIZE_TOKENS
    source_root = Path(__file__).resolve().parents[1] / "src" / "seeker_accounting"
    pattern = re.compile(r"\.resize\(\s*\d+\s*,\s*\d+\s*\)")
    offenders = [
        path.as_posix()
        for path in source_root.rglob("*.py")
        if path.name != "layout_constraints.py" and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_reproducible_e2e_fixture_matrix_shape() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "reproducible_e2e_fixture_matrix.py"
    spec = importlib.util.spec_from_file_location("reproducible_e2e_fixture_matrix", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    matrix = module.build_fixture_matrix()
    codes = [step.code for step in matrix]

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

    results = module.run_fixture_matrix(module.build_dry_run_handlers(), dry_run=True)
    assert [result.code for result in results if result.executed] == codes

    committed_sessions = []

    class _FixtureUow:
        def __init__(self):
            self.session = []

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *_args):  # noqa: ANN002, ANN204
            return None

        def commit(self) -> None:
            committed_sessions.append(tuple(self.session))

    def _db_handler(step, session):  # noqa: ANN001, ANN202
        session.append(step.code)
        return f"stored {step.code}"

    db_results = module.run_database_fixture_matrix(
        {step.code: _db_handler for step in matrix},
        _FixtureUow,
    )
    assert [result.code for result in db_results if result.executed] == codes
    assert db_results[0].message == "stored setup_company"
    assert committed_sessions[0] == ("setup_company",)

    with pytest.raises(KeyError):
        module.run_fixture_matrix({})

    with pytest.raises(KeyError):
        module.run_database_fixture_matrix({}, _FixtureUow)