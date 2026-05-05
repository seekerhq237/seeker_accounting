"""ChildWindowBase wrapper for the Payroll Run Cockpit (Phase 3 / P3.S1).

Hosts :class:`PayrollRunCockpit` inside the application's child-window
shell so it can be opened from the calculation workspace, the command
palette, and the navigation router.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.child_windows.child_window_base import ChildWindowBase
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.modules.payroll.ui.payroll_run_cockpit import PayrollRunCockpit
from seeker_accounting.modules.payroll.ui.payroll_run_employee_window import (
    PayrollRunEmployeeWindow,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_run_employee_detail_dialog import (
    PayrollRunEmployeeDetailDialog,
)
from seeker_accounting.shared.ui.icon_provider import IconProvider

_log = logging.getLogger(__name__)


class PayrollRunCockpitWindow(ChildWindowBase):
    """Child-window host for the run cockpit."""

    DOC_TYPE = "payroll_run_cockpit"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        run_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title="Payroll run",
            surface_key=RibbonRegistry.child_window_key(self.DOC_TYPE),
            window_key=(self.DOC_TYPE, run_id),
            registry=service_registry.ribbon_registry or RibbonRegistry(),
            icon_provider=IconProvider(service_registry.theme_manager),
            parent=parent,
        )
        self._registry = service_registry
        self._company_id = company_id
        self._run_id = run_id

        self._cockpit = PayrollRunCockpit(
            service_registry,
            company_id=company_id,
            run_id=run_id,
            parent=self,
        )
        self._cockpit.employee_open_requested.connect(self._on_open_employee)
        self._cockpit.state_changed.connect(self._on_state_changed)
        self._cockpit.selection_changed.connect(self.refresh_ribbon_state)
        self.set_body(self._cockpit)

        # Refresh the window title with the run reference once loaded.
        self._sync_title()

    # ── Public ribbon-friendly handles ────────────────────────────────

    @property
    def cockpit(self) -> PayrollRunCockpit:
        return self._cockpit

    def refresh(self) -> None:
        self._cockpit.refresh()
        self._sync_title()

    # ── Ribbon host implementation ────────────────────────────────────

    def handle_ribbon_command(self, command_id: str) -> None:  # type: ignore[override]
        dispatch = {
            "payroll_run_cockpit.calculate":        self._cockpit.trigger_calculate,
            "payroll_run_cockpit.approve":          self._cockpit.trigger_approve,
            "payroll_run_cockpit.void":             self._cockpit.trigger_void,
            "payroll_run_cockpit.employee_detail":  self._on_open_selected_employee,
            "payroll_run_cockpit.refresh":          self.refresh,
            "payroll_run_cockpit.close":            self.close,
        }
        handler = dispatch.get(command_id)
        if handler is not None:
            handler()

    def ribbon_state(self) -> dict[str, bool]:  # type: ignore[override]
        emp_selected = self._cockpit.selected_run_employee_id() is not None
        return {
            "payroll_run_cockpit.calculate":       self._cockpit.can_calculate(),
            "payroll_run_cockpit.approve":         self._cockpit.can_approve(),
            "payroll_run_cockpit.void":            self._cockpit.can_void(),
            "payroll_run_cockpit.employee_detail": emp_selected,
            "payroll_run_cockpit.refresh":         True,
            "payroll_run_cockpit.close":           True,
        }

    # ── Internal ──────────────────────────────────────────────────────

    def _sync_title(self) -> None:
        run = self._cockpit._run  # noqa: SLF001 — internal contract
        if run is None:
            return
        self.setWindowTitle(f"Payroll run - {run.run_reference}")

    def _on_state_changed(self, _run_id: Any, _status: Any) -> None:
        self._sync_title()
        self.refresh_ribbon_state()

    def _on_open_selected_employee(self) -> None:
        emp_id = self._cockpit.selected_run_employee_id()
        if emp_id is None:
            return
        self._on_open_employee(emp_id)

    def _on_open_employee(self, run_employee_id: int) -> None:
        manager = getattr(self._registry, "child_window_manager", None)
        if manager is None:
            dlg = PayrollRunEmployeeDetailDialog(
                self._registry, self._company_id, run_employee_id, self
            )
            dlg.exec()
            return

        def _factory() -> PayrollRunEmployeeWindow:
            return PayrollRunEmployeeWindow(
                self._registry,
                company_id=self._company_id,
                run_employee_id=run_employee_id,
            )

        manager.open_document(
            PayrollRunEmployeeWindow.DOC_TYPE,
            run_employee_id,
            _factory,
        )


__all__ = ["PayrollRunCockpitWindow"]
