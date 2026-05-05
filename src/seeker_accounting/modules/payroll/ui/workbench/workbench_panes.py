"""Workbench pane registry: the eight task-oriented panes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from seeker_accounting.modules.payroll.ui.i18n import tr


@dataclass(frozen=True, slots=True)
class WorkbenchPane:
    """Static descriptor for one left-rail entry inside the workbench."""

    key: str
    label: str
    description: str


PANE_DASHBOARD: Final = "dashboard"
PANE_RUN: Final = "run"
PANE_PEOPLE: Final = "people"
PANE_COMPENSATION: Final = "compensation"
PANE_SETUP: Final = "setup"
PANE_STATUTORY: Final = "statutory"
PANE_REPORTS: Final = "reports"
PANE_AUDIT: Final = "audit"


def build_workbench_panes() -> tuple[WorkbenchPane, ...]:
    """Build translated pane descriptors for the active payroll locale."""
    return (
        WorkbenchPane(
            key=PANE_DASHBOARD,
            label=tr("Dashboard"),
            description=tr("Period status, next actions, recent payroll activity."),
        ),
        WorkbenchPane(
            key=PANE_RUN,
            label=tr("Payroll runs"),
            description=tr("Open and recent payroll runs."),
        ),
        WorkbenchPane(
            key=PANE_PEOPLE,
            label=tr("People"),
            description=tr("Employees, readiness, hire / terminate / compensation actions."),
        ),
        WorkbenchPane(
            key=PANE_COMPENSATION,
            label=tr("Compensation"),
            description=tr("Compensation records and recurring component assignments."),
        ),
        WorkbenchPane(
            key=PANE_SETUP,
            label=tr("Setup"),
            description=tr("Company payroll, payroll components, rules, departments, positions."),
        ),
        WorkbenchPane(
            key=PANE_STATUTORY,
            label=tr("Statutory"),
            description=tr("Statutory packs, remittances, and filing deadlines."),
        ),
        WorkbenchPane(
            key=PANE_REPORTS,
            label=tr("Reports"),
            description=tr("Payslips, summaries, exports."),
        ),
        WorkbenchPane(
            key=PANE_AUDIT,
            label=tr("Audit"),
            description=tr("Audit trail and validation history."),
        ),
    )


WORKBENCH_PANES: Final[tuple[WorkbenchPane, ...]] = build_workbench_panes()


PANE_KEYS: Final[tuple[str, ...]] = tuple(p.key for p in WORKBENCH_PANES)
