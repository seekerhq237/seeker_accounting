"""Payroll first-run setup checklist service (P12.S2).

Evaluates which of the seven canonical setup steps have been completed
for a company and returns a lightweight ``SetupChecklistResult``.

Steps (in recommended order):
  1. payroll_settings — company payroll settings configured
  2. statutory_pack   — at least one statutory pack applied
  3. departments      — at least one department created
  4. positions        — at least one position created
  5. components       — at least one payroll component defined
  6. employees        — at least one active employee hired
  7. first_run        — at least one posted payroll run exists

Once all seven are complete the checklist is "done" and should no
longer be shown.

Callers (dashboard pane) supply the ``ServiceRegistry`` and call
``evaluate(company_id)``.  Every probe is wrapped in try/except so
missing or misbehaving services never surface as errors in the UI.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── DTO ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SetupChecklistItem:
    """One step in the setup checklist."""

    key: str
    label: str
    description: str
    done: bool
    action_label: str | None = None
    action_key: str | None = None  # correlates to a workbench pane or wizard key


@dataclass(frozen=True, slots=True)
class SetupChecklistResult:
    """Evaluated checklist for one company."""

    items: tuple[SetupChecklistItem, ...]
    all_done: bool

    @property
    def done_count(self) -> int:
        return sum(1 for i in self.items if i.done)

    @property
    def total_count(self) -> int:
        return len(self.items)


# ── Ordered step definitions ──────────────────────────────────────────────────

_STEP_META: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    # (key, label, description, action_label, action_key)
    (
        "payroll_settings",
        "Configure payroll settings",
        "Set the pay frequency, currency, and statutory registration numbers.",
        "Open settings",
        "setup",
    ),
    (
        "statutory_pack",
        "Apply a statutory pack",
        "Apply the correct statutory pack to enable automatic CNPS and tax calculations.",
        "Apply pack",
        "statutory",
    ),
    (
        "departments",
        "Add departments",
        "Create at least one department to group employees for cost reporting.",
        "Add department",
        "setup",
    ),
    (
        "positions",
        "Add positions",
        "Create job positions to pre-fill salary defaults when hiring.",
        "Add position",
        "setup",
    ),
    (
        "components",
        "Define payroll components",
        "Define the earnings, deductions, and statutory components that make up payslips.",
        "Add component",
        "setup",
    ),
    (
        "employees",
        "Hire the first employee",
        "Use the Hire employee wizard to onboard the first person and assign their compensation.",
        "Hire employee",
        "people",
    ),
    (
        "first_run",
        "Run first payroll",
        "Create and calculate the first payroll run. Post it to complete the setup journey.",
        "New payroll run",
        "run",
    ),
)


# ── Service ───────────────────────────────────────────────────────────────────


class PayrollSetupChecklistService:
    """Evaluates the first-run setup checklist for a given company.

    Designed to be instantiated once per workbench session and called on
    every company switch.  All probes are defensively guarded.
    """

    def evaluate(self, company_id: int, service_registry: Any) -> SetupChecklistResult:
        probes = {
            "payroll_settings": self._probe_settings(company_id, service_registry),
            "statutory_pack": self._probe_statutory_pack(company_id, service_registry),
            "departments": self._probe_departments(company_id, service_registry),
            "positions": self._probe_positions(company_id, service_registry),
            "components": self._probe_components(company_id, service_registry),
            "employees": self._probe_employees(company_id, service_registry),
            "first_run": self._probe_first_run(company_id, service_registry),
        }

        items = tuple(
            SetupChecklistItem(
                key=key,
                label=label,
                description=desc,
                done=probes.get(key, False),
                action_label=action_label,
                action_key=action_key,
            )
            for key, label, desc, action_label, action_key in _STEP_META
        )
        return SetupChecklistResult(items=items, all_done=all(i.done for i in items))

    # ── Probes ────────────────────────────────────────────────────────────────

    def _probe_settings(self, company_id: int, sr: Any) -> bool:
        svc = getattr(sr, "payroll_setup_service", None)
        if svc is None:
            return False
        try:
            settings = svc.get_company_payroll_settings(company_id)
            return settings is not None
        except Exception:
            logger.debug("probe_settings failed", exc_info=True)
            return False

    def _probe_statutory_pack(self, company_id: int, sr: Any) -> bool:
        svc = getattr(sr, "payroll_statutory_pack_service", None)
        if svc is None:
            return False
        try:
            packs = svc.list_applied_packs(company_id)
            return bool(packs)
        except Exception:
            logger.debug("probe_statutory_pack failed", exc_info=True)
            return False

    def _probe_departments(self, company_id: int, sr: Any) -> bool:
        svc = getattr(sr, "payroll_setup_service", None)
        if svc is None:
            return False
        try:
            depts = svc.list_departments(company_id)
            return bool(depts)
        except Exception:
            logger.debug("probe_departments failed", exc_info=True)
            return False

    def _probe_positions(self, company_id: int, sr: Any) -> bool:
        svc = getattr(sr, "payroll_setup_service", None)
        if svc is None:
            return False
        try:
            positions = svc.list_positions(company_id)
            return bool(positions)
        except Exception:
            logger.debug("probe_positions failed", exc_info=True)
            return False

    def _probe_components(self, company_id: int, sr: Any) -> bool:
        svc = getattr(sr, "payroll_component_service", None)
        if svc is None:
            return False
        try:
            components = svc.list_components(company_id)
            return bool(components)
        except Exception:
            logger.debug("probe_components failed", exc_info=True)
            return False

    def _probe_employees(self, company_id: int, sr: Any) -> bool:
        svc = getattr(sr, "employee_service", None)
        if svc is None:
            return False
        try:
            employees = svc.list_employees(company_id, active_only=True)
            return bool(employees)
        except Exception:
            logger.debug("probe_employees failed", exc_info=True)
            return False

    def _probe_first_run(self, company_id: int, sr: Any) -> bool:
        svc = getattr(sr, "payroll_run_service", None)
        if svc is None:
            return False
        try:
            runs = svc.list_runs(company_id)
            posted = [
                r for r in (runs or [])
                if getattr(r, "status_code", "") == "posted"
            ]
            return bool(posted)
        except Exception:
            logger.debug("probe_first_run failed", exc_info=True)
            return False
