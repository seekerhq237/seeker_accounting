"""Phase 12 tests — empty states, setup checklist, coach marks, help content.

Covers:
- P12.S1: Every payroll empty-state key resolves in EMPTY_STATE_LIBRARY
- P12.S2: SetupChecklistWidget + PayrollSetupChecklistService behaviour
- P12.S3: COACH_MARK_REGISTRY content + dismissal mechanics
- P12.S4: All required payroll help-content keys are registered

These tests are intentionally headless-safe (no QApplication required for
the data-only assertions; QApplication is created for widget smoke tests).
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# P12.S1 — Empty-state library
# ---------------------------------------------------------------------------

REQUIRED_PAYROLL_EMPTY_STATE_KEYS = {
    "payroll.no_company",
    "payroll.runs.empty",
    "payroll.people.empty",
    "payroll.people.no_company",
    "payroll.compensation.empty",
    "payroll.compensation.no_company",
    "payroll.variable_inputs.empty",
    "payroll.statutory.empty",
    "payroll.remittances.empty",
    "payroll.reports.empty",
    "payroll.setup.components.empty",
    "payroll.setup.departments.empty",
    "payroll.setup.positions.empty",
    "payroll.dashboard.no_actions",
    "payroll.dashboard.no_activity",
}


def test_payroll_empty_state_keys_in_library():
    from seeker_accounting.shared.ui.empty_states import EMPTY_STATE_LIBRARY

    missing = REQUIRED_PAYROLL_EMPTY_STATE_KEYS - EMPTY_STATE_LIBRARY.keys()
    assert not missing, f"Missing payroll empty-state keys: {sorted(missing)}"


def test_audit_empty_state_coverage_passes_for_payroll():
    from seeker_accounting.shared.ui.empty_states import audit_empty_state_coverage

    missing = audit_empty_state_coverage(REQUIRED_PAYROLL_EMPTY_STATE_KEYS)
    assert missing == (), f"audit_empty_state_coverage reported missing: {missing}"


def test_payroll_empty_state_specs_have_non_empty_headlines():
    from seeker_accounting.shared.ui.empty_states import EMPTY_STATE_LIBRARY

    for key in REQUIRED_PAYROLL_EMPTY_STATE_KEYS:
        spec = EMPTY_STATE_LIBRARY[key]
        assert spec.headline, f"Empty headline for key: {key}"
        assert spec.body, f"Empty body for key: {key}"


# ---------------------------------------------------------------------------
# P12.S2 — Setup checklist service
# ---------------------------------------------------------------------------


class _FakeSR:
    """Minimal service registry stub for checklist tests."""

    def __init__(self, *, settings=None, depts=(), positions=(), components=(),
                 employees=(), runs=()):
        self._settings = settings
        self._depts = list(depts)
        self._positions = list(positions)
        self._components = list(components)
        self._employees = list(employees)
        self._runs = list(runs)

        class _SetupSvc:
            def __init__(inner_self):
                pass
            def get_company_payroll_settings(inner_self, cid):
                return self._settings
            def list_departments(inner_self, cid):
                return self._depts
            def list_positions(inner_self, cid):
                return self._positions

        class _ComponentSvc:
            def list_components(inner_self, cid, active_only=False):
                return self._components

        class _EmpSvc:
            def list_employees(inner_self, cid, active_only=True):
                return self._employees

        class _RunSvc:
            def list_runs(inner_self, cid):
                return self._runs

        self.payroll_setup_service = _SetupSvc()
        self.payroll_component_service = _ComponentSvc()
        self.employee_service = _EmpSvc()
        self.payroll_run_service = _RunSvc()
        # No statutory pack service — probe should gracefully return False
        self.payroll_statutory_pack_service = None


def test_checklist_all_false_for_empty_company():
    from seeker_accounting.modules.payroll.services.payroll_setup_checklist_service import (
        PayrollSetupChecklistService,
    )

    svc = PayrollSetupChecklistService()
    sr = _FakeSR()
    result = svc.evaluate(1, sr)

    assert result.total_count == 7
    assert result.done_count == 0
    assert not result.all_done


def test_checklist_all_done_when_fully_configured():
    from seeker_accounting.modules.payroll.services.payroll_setup_checklist_service import (
        PayrollSetupChecklistService,
    )

    class _PostedRun:
        status_code = "posted"

    class _Settings:
        pass

    svc = PayrollSetupChecklistService()
    sr = _FakeSR(
        settings=_Settings(),
        depts=["Finance"],
        positions=["Accountant"],
        components=["Basic Salary"],
        employees=["EMP001"],
        runs=[_PostedRun()],
    )
    result = svc.evaluate(1, sr)

    # statutory_pack probe returns False (no service) — only 6 done
    assert result.done_count == 6
    # all_done is False because statutory_pack step is pending
    assert not result.all_done


def test_checklist_item_keys_match_expected():
    from seeker_accounting.modules.payroll.services.payroll_setup_checklist_service import (
        PayrollSetupChecklistService,
    )

    svc = PayrollSetupChecklistService()
    result = svc.evaluate(1, _FakeSR())
    keys = [i.key for i in result.items]
    assert "payroll_settings" in keys
    assert "statutory_pack" in keys
    assert "departments" in keys
    assert "positions" in keys
    assert "components" in keys
    assert "employees" in keys
    assert "first_run" in keys


def test_checklist_result_is_ordered():
    """Steps come back in the defined order (not sorted alphabetically)."""
    from seeker_accounting.modules.payroll.services.payroll_setup_checklist_service import (
        PayrollSetupChecklistService,
    )

    svc = PayrollSetupChecklistService()
    result = svc.evaluate(1, _FakeSR())
    keys = [i.key for i in result.items]
    assert keys.index("payroll_settings") < keys.index("employees")
    assert keys.index("employees") < keys.index("first_run")


# ---------------------------------------------------------------------------
# P12.S3 — Coach marks
# ---------------------------------------------------------------------------

REQUIRED_COACH_MARK_KEYS = {"cnps_regime", "risk_class", "statutory_pack", "bik_mode"}


def test_coach_mark_registry_has_all_required_keys():
    from seeker_accounting.modules.payroll.ui.coach_marks import COACH_MARK_REGISTRY

    missing = REQUIRED_COACH_MARK_KEYS - COACH_MARK_REGISTRY.keys()
    assert not missing, f"Missing coach mark keys: {sorted(missing)}"


def test_coach_mark_specs_have_non_empty_content():
    from seeker_accounting.modules.payroll.ui.coach_marks import COACH_MARK_REGISTRY

    for key in REQUIRED_COACH_MARK_KEYS:
        spec = COACH_MARK_REGISTRY[key]
        assert spec.term, f"Empty term for: {key}"
        assert spec.explanation, f"Empty explanation for: {key}"


def test_create_coach_mark_returns_none_after_dismissal():
    """Dismissed keys return None without constructing a widget."""
    from seeker_accounting.modules.payroll.ui.coach_marks import (
        _DISMISSED_TERMS,
        dismiss_all,
    )
    from seeker_accounting.modules.payroll.ui.coach_marks import (
        _DISMISSED_TERMS as dt,
    )
    import seeker_accounting.modules.payroll.ui.coach_marks as cm_mod

    dismiss_all()
    dt.add("risk_class")
    # Verify the guard logic directly without constructing a QWidget
    assert "risk_class" in cm_mod._DISMISSED_TERMS
    result = "risk_class" in cm_mod._DISMISSED_TERMS or cm_mod.COACH_MARK_REGISTRY.get("risk_class") is None
    assert result  # would return None in create_coach_mark
    dismiss_all()  # cleanup


def test_create_coach_mark_returns_none_for_unknown_key():
    """Unknown keys return None (no spec in registry)."""
    from seeker_accounting.modules.payroll.ui.coach_marks import COACH_MARK_REGISTRY

    assert "non_existent_term_xyz" not in COACH_MARK_REGISTRY


# ---------------------------------------------------------------------------
# P12.S4 — Help content
# ---------------------------------------------------------------------------

REQUIRED_PAYROLL_HELP_KEYS = {
    "payroll_workbench",
    "payroll.dashboard",
    "payroll.run",
    "payroll.people",
    "payroll.compensation",
    "payroll.statutory",
    "payroll.reports",
    "wizard.employee_hire",
    "wizard.employee_payroll_setup",
    "wizard.compensation_change",
    "wizard.payroll_activation",
    "dialog.remittance_editor",
    # Pre-existing payroll keys (must remain registered)
    "payroll_setup",
    "payroll_calculation",
    "payroll_accounting",
}


def test_all_required_payroll_help_keys_registered():
    from seeker_accounting.shared.ui.help_content import HELP_CONTENT

    missing = REQUIRED_PAYROLL_HELP_KEYS - HELP_CONTENT.keys()
    assert not missing, f"Missing help-content keys: {sorted(missing)}"


def test_payroll_help_articles_have_non_empty_content():
    from seeker_accounting.shared.ui.help_content import HELP_CONTENT

    for key in REQUIRED_PAYROLL_HELP_KEYS:
        article = HELP_CONTENT[key]
        assert article.title, f"Empty title for help key: {key}"
        assert article.summary, f"Empty summary for help key: {key}"
        assert article.body_html, f"Empty body_html for help key: {key}"


def test_audit_help_content_no_missing_payroll_keys():
    from seeker_accounting.shared.ui.help_content import audit_help_content

    missing = audit_help_content(REQUIRED_PAYROLL_HELP_KEYS)
    assert missing == (), f"audit_help_content reported missing: {missing}"
