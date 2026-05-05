"""Phase 13 — Tokenised sizing, keyboard shortcuts, accessible names, density.

Tests cover:
    P13.S1  — sizing tokens present in DEFAULT_TOKENS.sizes; no bare resize() in dialogs.
    P13.S2  — payroll keyboard shortcut specs present in WORKBENCH_SHORTCUTS.
    P13.S3  — accessible-name helpers wired (data-only checks; no QApplication required).
    P13.S4  — DataTable density infrastructure wired (shortcut in place).
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import re

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────

ROOT = pathlib.Path(__file__).parent.parent / "src" / "seeker_accounting"
PAYROLL_UI = ROOT / "modules" / "payroll" / "ui"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ── P13.S1: sizing tokens ──────────────────────────────────────────────────────

class TestSizingTokens:
    """Every new token added in P13.S1 must be present."""

    def _sizes(self):
        from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS
        return DEFAULT_TOKENS.sizes

    def test_dialog_small(self):
        s = self._sizes()
        assert s.dialog_min_w_small == 380
        assert s.dialog_min_h_small == 220

    def test_dialog_medium(self):
        s = self._sizes()
        assert s.dialog_min_w_medium == 480
        assert s.dialog_min_h_medium == 320

    def test_dialog_large(self):
        s = self._sizes()
        assert s.dialog_min_w_large == 580
        assert s.dialog_min_h_large == 440

    def test_dialog_xlarge(self):
        s = self._sizes()
        assert s.dialog_min_w_xlarge == 760
        assert s.dialog_min_h_xlarge == 480

    def test_dialog_document(self):
        s = self._sizes()
        assert s.dialog_min_w_document == 860
        assert s.dialog_min_h_document == 680

    def test_dialog_validation(self):
        s = self._sizes()
        assert s.dialog_min_w_validation == 560
        assert s.dialog_min_h_validation == 480

    def test_form_labels(self):
        s = self._sizes()
        assert s.form_label_w == 160
        assert s.form_label_w_small == 120
        assert s.form_label_w_medium == 200

    def test_form_combos(self):
        s = self._sizes()
        assert s.form_combo_min_w == 260
        assert s.form_combo_large_min_w == 300

    def test_form_textareas(self):
        s = self._sizes()
        assert s.form_textarea_h_small == 60
        assert s.form_textarea_h_medium == 80
        assert s.form_textarea_h_large == 96

    def test_glyph_col(self):
        assert self._sizes().glyph_col_w == 18

    def test_toolbar_filter(self):
        assert self._sizes().toolbar_filter_min_w == 220

    def test_workbench_pane(self):
        s = self._sizes()
        assert s.workbench_pane_min_w == 360
        assert s.workbench_pane_min_w_wide == 420

    def test_report_tile(self):
        assert self._sizes().report_tile_h == 64

    def test_nav_pill(self):
        assert self._sizes().nav_pill_min_w == 140


# ── P13.S1: no bare resize() literals in payroll dialog files ─────────────────

# Files that used to contain bare resize() calls.
_DIALOG_FILES = [
    PAYROLL_UI / "dialogs" / "department_dialog.py",
    PAYROLL_UI / "dialogs" / "position_dialog.py",
    PAYROLL_UI / "dialogs" / "payroll_rule_brackets_dialog.py",
    PAYROLL_UI / "dialogs" / "payslip_preview_dialog.py",
    PAYROLL_UI / "dialogs" / "validation_check_detail_dialog.py",
]

_RESIZE_LITERAL_RE = re.compile(r"\bself\.resize\(\s*\d+\s*,\s*\d+\s*\)")


@pytest.mark.parametrize("path", _DIALOG_FILES, ids=[p.name for p in _DIALOG_FILES])
def test_no_bare_resize_literal(path: pathlib.Path):
    """No dialog should use self.resize(W, H) with numeric literals."""
    src = _read(path)
    matches = _RESIZE_LITERAL_RE.findall(src)
    # payslip_preview_dialog retains one resize() for the initial preferred height,
    # but must use a token for the width — allowed if the first arg is NOT a bare literal.
    # We allow at most one and only when it uses a token reference.
    assert not matches, (
        f"{path.name} still contains bare resize() literals: {matches}"
    )


# ── P13.S2: keyboard shortcut specs ───────────────────────────────────────────

class TestKeyboardShortcuts:
    def _shortcuts(self):
        from seeker_accounting.shared.ui.keyboard_shortcuts import WORKBENCH_SHORTCUTS
        return WORKBENCH_SHORTCUTS

    def _scopes(self):
        return {spec.scope for spec in self._shortcuts()}

    def _by_scope_action(self):
        return {(spec.scope, spec.action_id): spec for spec in self._shortcuts()}

    def test_payroll_global_scopes_present(self):
        assert "payroll" in self._scopes()

    def test_payroll_run_scope_present(self):
        assert "payroll.run" in self._scopes()

    def test_payroll_people_scope_present(self):
        assert "payroll.people" in self._scopes()

    def test_payroll_compensation_scope_present(self):
        assert "payroll.compensation" in self._scopes()

    def test_payroll_run_new_run_shortcut(self):
        spec = self._by_scope_action().get(("payroll.run", "new_run"))
        assert spec is not None, "payroll.run/new_run shortcut missing"
        assert spec.sequence == "Ctrl+N"

    def test_payroll_run_open_run_shortcut(self):
        spec = self._by_scope_action().get(("payroll.run", "open_run"))
        assert spec is not None, "payroll.run/open_run shortcut missing"
        assert spec.sequence == "Ctrl+E"

    def test_payroll_people_hire_shortcut(self):
        spec = self._by_scope_action().get(("payroll.people", "hire"))
        assert spec is not None, "payroll.people/hire shortcut missing"
        assert spec.sequence == "Ctrl+N"

    def test_payroll_people_edit_shortcut(self):
        spec = self._by_scope_action().get(("payroll.people", "edit"))
        assert spec is not None, "payroll.people/edit shortcut missing"
        assert spec.sequence == "Ctrl+E"

    def test_payroll_compensation_new_shortcut(self):
        spec = self._by_scope_action().get(("payroll.compensation", "new_comp"))
        assert spec is not None, "payroll.compensation/new_comp shortcut missing"
        assert spec.sequence == "Ctrl+N"

    def test_payroll_global_new_run(self):
        spec = self._by_scope_action().get(("payroll", "new_run"))
        assert spec is not None, "payroll/new_run global shortcut missing"
        assert spec.sequence == "Ctrl+Shift+P"

    def test_payroll_global_hire_employee(self):
        spec = self._by_scope_action().get(("payroll", "hire_employee"))
        assert spec is not None, "payroll/hire_employee global shortcut missing"
        assert spec.sequence == "Ctrl+Shift+E"

    def test_shortcuts_for_scope_includes_common(self):
        from seeker_accounting.shared.ui.keyboard_shortcuts import shortcuts_for_scope
        specs = shortcuts_for_scope("payroll.run")
        scopes = {s.scope for s in specs}
        assert "common" in scopes, "shortcuts_for_scope should always include 'common'"
        assert "payroll.run" in scopes

    def test_shortcut_map_keys(self):
        from seeker_accounting.shared.ui.keyboard_shortcuts import shortcut_map
        m = shortcut_map("payroll.run")
        assert "new_run" in m
        assert "open_run" in m


# ── P13.S3: accessible names wired in pane source ─────────────────────────────

_PANE_A11Y = [
    (PAYROLL_UI / "workbench" / "panes" / "run_pane.py",
     ["New payroll run", "Open selected payroll run", "Payroll runs list"]),
    (PAYROLL_UI / "workbench" / "panes" / "people_pane.py",
     ["Hire new employee", "Edit selected employee"]),
    (PAYROLL_UI / "workbench" / "panes" / "compensation_pane.py",
     ["New compensation", "Edit selected compensation"]),
]


@pytest.mark.parametrize("path,names", _PANE_A11Y, ids=[p.name for p, _ in _PANE_A11Y])
def test_accessible_names_present(path: pathlib.Path, names: list[str]):
    src = _read(path)
    for name in names:
        assert name in src, (
            f"{path.name}: accessible name {name!r} not found in source"
        )


# ── P13.S4: density toggle shortcut wired in panes ────────────────────────────

_DENSITY_PANES = [
    PAYROLL_UI / "workbench" / "panes" / "run_pane.py",
    PAYROLL_UI / "workbench" / "panes" / "people_pane.py",
    PAYROLL_UI / "workbench" / "panes" / "compensation_pane.py",
]


@pytest.mark.parametrize("path", _DENSITY_PANES, ids=[p.name for p in _DENSITY_PANES])
def test_density_toggle_shortcut_wired(path: pathlib.Path):
    src = _read(path)
    assert "toggle_density" in src, (
        f"{path.name}: density toggle shortcut not wired (missing 'toggle_density' reference)"
    )
    assert "set_density" in src, (
        f"{path.name}: set_density call missing from density shortcut handler"
    )


# ── P13.S4: DataTable default show_density_toggle=True ───────────────────────

def test_data_table_density_default():
    """DataTable constructor default show_density_toggle=True so all payroll tables get it."""
    from seeker_accounting.shared.ui.components.data_table import DataTable
    import inspect
    sig = inspect.signature(DataTable.__init__)
    param = sig.parameters.get("show_density_toggle")
    assert param is not None, "DataTable missing show_density_toggle parameter"
    assert param.default is True, (
        f"show_density_toggle default should be True, got {param.default!r}"
    )
