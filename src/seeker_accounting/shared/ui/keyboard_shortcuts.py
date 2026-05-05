"""Keyboard shortcut registry and installer helpers for workbench panes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True, slots=True)
class ShortcutSpec:
    scope: str
    action_id: str
    sequence: str
    label: str
    description: str = ""


WORKBENCH_SHORTCUTS: tuple[ShortcutSpec, ...] = (
    ShortcutSpec("common", "refresh", "F5", "Refresh", "Reload the current workbench pane."),
    ShortcutSpec("common", "search", "Ctrl+F", "Search", "Move focus to the local search field."),
    ShortcutSpec("table", "toggle_density", "Ctrl+Shift+D", "Toggle Density", "Switch tables between comfortable and compact density."),
    ShortcutSpec("table", "clear_selection", "Esc", "Clear Selection", "Clear the current table selection."),
    ShortcutSpec("dashboard", "open_overview", "Alt+1", "Overview", "Show the dashboard overview pane."),
    ShortcutSpec("dashboard", "open_cash", "Alt+2", "Cash & Liquidity", "Show the cash and liquidity pane."),
    # Payroll workbench — global scope (active anywhere in the payroll workbench)
    ShortcutSpec("payroll", "new_run", "Ctrl+Shift+P", "New Payroll Run", "Create a new payroll run from anywhere in the payroll workbench."),
    ShortcutSpec("payroll", "hire_employee", "Ctrl+Shift+E", "Hire Employee", "Open the Hire Employee wizard from anywhere in the payroll workbench."),
    # Payroll run pane
    ShortcutSpec("payroll.run", "new_run", "Ctrl+N", "New Payroll Run", "Create a new payroll run."),
    ShortcutSpec("payroll.run", "open_run", "Ctrl+E", "Open Run", "Open the selected payroll run."),
    ShortcutSpec("payroll.run", "delete_run", "Delete", "Delete Run", "Delete the selected payroll run after confirmation."),
    # Payroll people pane
    ShortcutSpec("payroll.people", "hire", "Ctrl+N", "Hire Employee", "Open the Hire Employee wizard."),
    ShortcutSpec("payroll.people", "edit", "Ctrl+E", "Edit Employee", "Edit the selected employee."),
    ShortcutSpec("payroll.people", "delete", "Delete", "Terminate Employee", "Initiate employee termination after confirmation."),
    # Payroll compensation pane
    ShortcutSpec("payroll.compensation", "new_comp", "Ctrl+N", "New Compensation", "Add a compensation record."),
    ShortcutSpec("payroll.compensation", "edit_comp", "Ctrl+E", "Edit Compensation", "Edit the selected compensation record."),
    # Payroll setup pane
    ShortcutSpec("payroll.setup", "new_item", "Ctrl+N", "New Item", "Add a new item in the active setup tab."),
    ShortcutSpec("payroll.setup", "edit_item", "Ctrl+E", "Edit Item", "Edit the selected item in the active setup tab."),
    # Payroll statutory pane
    ShortcutSpec("payroll.statutory", "open_remittance", "Ctrl+E", "Open Remittance", "Open the remittance editor for the selected authority."),
    # Payroll dialog — submit confirmation
    ShortcutSpec("payroll.dialog", "submit", "Ctrl+Return", "Submit", "Confirm and submit the current form."),
)


def shortcuts_for_scope(scope: str) -> tuple[ShortcutSpec, ...]:
    return tuple(spec for spec in WORKBENCH_SHORTCUTS if spec.scope in ("common", scope))


def shortcut_map(scope: str) -> dict[str, ShortcutSpec]:
    return {spec.action_id: spec for spec in shortcuts_for_scope(scope)}


def install_shortcut(
    parent: QWidget,
    spec: ShortcutSpec,
    callback: Callable[[], None],
) -> QAction:
    action = QAction(spec.label, parent)
    action.setObjectName(f"ShortcutAction_{spec.scope}_{spec.action_id}")
    action.setShortcut(QKeySequence(spec.sequence))
    action.setToolTip(spec.description or spec.label)
    action.triggered.connect(callback)
    parent.addAction(action)
    return action