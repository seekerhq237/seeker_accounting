"""EmployeeHubWindow — compact full-window workbench for a payroll employee.

Serves as the single place to inspect and manage everything about an
employee from a payroll point of view:

* Identity & contact (name, employee number, department/position, tax /
  CNPS / payment account).
* Payroll readiness strip (Tax & CNPS, Payment, Compensation, Components)
  driven by the same gap scan used by
  :class:`EmployeePayrollSetupWizardDialog`.
* Compensation profiles (compact table).
* Recurring component assignments (compact table).
* Recent payroll runs touching this employee (compact table).

Ribbon actions: Edit Employee · Payroll Setup Wizard · Compensation
Change · Assign Component · Deactivate/Reactivate · Refresh · Close.

Registered under the child-window key ``child:payroll_employee_hub``.
"""

from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.child_windows.child_window_base import ChildWindowBase
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.modules.payroll.dto.employee_dto import (
    EmployeeDetailDTO,
    UpdateEmployeeCommand,
)
from seeker_accounting.modules.payroll.ui.dialogs.component_assignment_dialog import (
    ComponentAssignmentDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.employee_form_dialog import (
    EmployeeFormDialog,
)
from seeker_accounting.modules.payroll.ui.wizards.compensation_change_wizard import (
    CompensationChangeWizardDialog,
)
from seeker_accounting.modules.payroll.ui.wizards.employee_payroll_setup_wizard import (
    EmployeePayrollSetupWizardDialog,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


_log = logging.getLogger(__name__)


_RUN_STATUS_LABELS = {
    "draft": "Draft",
    "calculated": "Calculated",
    "approved": "Approved",
    "posted": "Posted",
    "voided": "Voided",
}

_MONTHS = (
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


class EmployeeHubWindow(ChildWindowBase):
    """Full-window hub for managing a single employee's payroll profile."""

    DOC_TYPE = "payroll_employee_hub"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        employee_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title="Employee Hub",
            surface_key=RibbonRegistry.child_window_key(self.DOC_TYPE),
            window_key=(self.DOC_TYPE, employee_id),
            registry=service_registry.ribbon_registry or RibbonRegistry(),
            icon_provider=IconProvider(service_registry.theme_manager),
            parent=parent,
        )
        self._registry = service_registry
        self._company_id = company_id
        self._employee_id = employee_id
        self._company_name = self._lookup_company_name(company_id)

        self._employee: EmployeeDetailDTO | None = None
        self._gaps: dict[str, bool] = {}
        self._profiles: list = []
        self._assignments: list = []
        self._recent_runs: list[tuple] = []

        self.set_body(self._build_body())
        self._reload()

    # ── Helpers ───────────────────────────────────────────────────────

    def _lookup_company_name(self, company_id: int) -> str:
        try:
            company = self._registry.company_service.get_company(company_id)
            return getattr(company, "company_name", "") or getattr(company, "name", "")
        except Exception:  # noqa: BLE001
            return ""

    # ── Body layout ───────────────────────────────────────────────────

    def _build_body(self) -> QWidget:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(self._build_hero())
        root.addWidget(self._build_readiness_strip())

        grid_host = QFrame(body)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        grid.addWidget(self._build_identity_card(), 0, 0)
        grid.addWidget(self._build_profiles_card(), 0, 1)
        grid.addWidget(self._build_assignments_card(), 0, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        root.addWidget(grid_host, 1)

        root.addWidget(self._build_recent_runs_card())

        return body

    def _build_hero(self) -> QWidget:
        hero = QFrame(self)
        hero.setObjectName("DialogSectionCard")
        hero.setProperty("card", True)
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._name_label = QLabel("Employee", hero)
        f = self._name_label.font()
        f.setPointSize(max(f.pointSize() + 4, 14))
        f.setBold(True)
        self._name_label.setFont(f)
        row.addWidget(self._name_label)

        self._number_chip = QLabel("", hero)
        self._number_chip.setObjectName("ChipNeutral")
        self._number_chip.setStyleSheet(
            "padding: 2px 8px; border-radius: 8px; background: #eef1f5; "
            "color: #374151; font-weight: 500;"
        )
        row.addWidget(self._number_chip)

        self._status_chip = QLabel("", hero)
        self._status_chip.setObjectName("ChipStatus")
        row.addWidget(self._status_chip)
        row.addStretch(1)
        layout.addLayout(row)

        self._subtitle_label = QLabel("", hero)
        self._subtitle_label.setObjectName("DialogSectionSummary")
        layout.addWidget(self._subtitle_label)
        return hero

    def _build_readiness_strip(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("DialogSectionCard")
        frame.setProperty("card", True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        self._readiness_pills: dict[str, QLabel] = {}
        for label_text, key in (
            ("Tax & CNPS",  "tax_cnps"),
            ("Payment",     "payment"),
            ("Compensation","comp"),
            ("Components",  "components"),
        ):
            pill = QLabel(label_text, frame)
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setMinimumWidth(140)
            self._readiness_pills[key] = pill
            layout.addWidget(pill)
        layout.addStretch(1)

        self._readiness_summary = QLabel("", frame)
        self._readiness_summary.setObjectName("DialogSectionSummary")
        layout.addWidget(self._readiness_summary)
        return frame

    def _build_identity_card(self) -> QWidget:
        card = self._card("Identity & Contact")
        self._identity_grid_host = QFrame(card)
        card.layout().addWidget(self._identity_grid_host)
        return card

    def _build_profiles_card(self) -> QWidget:
        card = self._card("Compensation Profiles")
        self._profiles_table = QTableWidget(card)
        configure_compact_table(self._profiles_table)
        self._profiles_table.setColumnCount(4)
        self._profiles_table.setHorizontalHeaderLabels(
            ("From", "Salary", "Currency", "Status")
        )
        self._profiles_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._profiles_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        card.layout().addWidget(self._profiles_table, 1)
        return card

    def _build_assignments_card(self) -> QWidget:
        card = self._card("Component Assignments")
        self._assignments_table = QTableWidget(card)
        configure_compact_table(self._assignments_table)
        self._assignments_table.setColumnCount(4)
        self._assignments_table.setHorizontalHeaderLabels(
            ("Component", "Type", "From", "Status")
        )
        self._assignments_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._assignments_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        card.layout().addWidget(self._assignments_table, 1)
        return card

    def _build_recent_runs_card(self) -> QWidget:
        card = self._card("Recent Payroll Runs")
        self._runs_table = QTableWidget(card)
        configure_compact_table(self._runs_table)
        self._runs_table.setColumnCount(5)
        self._runs_table.setHorizontalHeaderLabels(
            ("Run", "Period", "Gross", "Net", "Status")
        )
        self._runs_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._runs_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._runs_table.setMaximumHeight(180)
        card.layout().addWidget(self._runs_table)
        return card

    def _card(self, title: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(8)
        tlabel = QLabel(title, card)
        tlabel.setObjectName("DialogSectionTitle")
        layout.addWidget(tlabel)
        return card

    # ── Data ──────────────────────────────────────────────────────────

    def _reload(self) -> None:
        try:
            emp = self._registry.employee_service.get_employee(
                self._company_id, self._employee_id,
            )
        except NotFoundError:
            show_error(self, "Employee Hub", "This employee no longer exists.")
            self.close()
            return
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Employee Hub", str(exc))
            return
        self._employee = emp
        self.setWindowTitle(f"Employee Hub — {emp.display_name}")
        self._name_label.setText(emp.display_name)
        self._number_chip.setText(emp.employee_number)

        active = emp.is_active
        self._status_chip.setText("Active" if active else "Inactive")
        self._status_chip.setStyleSheet(
            "padding: 2px 10px; border-radius: 8px; font-weight: 600;"
            + (" background: #e6f4ea; color: #1a7a2e;" if active
               else " background: #fde8e8; color: #9b1c1c;")
        )
        dept = emp.department_name or "—"
        pos = emp.position_name or "—"
        self._subtitle_label.setText(
            f"{dept}  ·  {pos}  ·  Hired {emp.hire_date.isoformat()}"
            + (f"  ·  Terminated {emp.termination_date.isoformat()}"
               if emp.termination_date else "")
        )

        self._refresh_identity_grid()
        self._load_profiles_and_assignments()
        self._scan_gaps()
        self._refresh_readiness()
        self._load_recent_runs()
        self.refresh_ribbon_state()

    def _refresh_identity_grid(self) -> None:
        # Clear the host and rebuild a tight grid.
        old = self._identity_grid_host.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget() if item else None
                if w is not None:
                    w.setParent(None)
            QWidget().setLayout(old)

        grid = QGridLayout(self._identity_grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        emp = self._employee
        assert emp is not None

        acct_label = "—"
        if emp.default_payment_account_id is not None:
            try:
                accts = (
                    self._registry.financial_account_service
                    .list_financial_accounts(self._company_id, active_only=False)
                )
                match = next(
                    (a for a in accts if a.id == emp.default_payment_account_id), None,
                )
                if match is not None:
                    acct_label = match.name
            except Exception:  # noqa: BLE001
                acct_label = f"#{emp.default_payment_account_id}"

        rows = [
            ("Email",           emp.email or "—"),
            ("Phone",           emp.phone or "—"),
            ("Tax ID",          emp.tax_identifier or "—"),
            ("CNPS",            emp.cnps_number or "—"),
            ("Currency",        emp.base_currency_code),
            ("Payment account", acct_label),
        ]
        for i, (label, value) in enumerate(rows):
            lab = QLabel(label, self._identity_grid_host)
            lab.setStyleSheet("color: #6b7280;")
            val = QLabel(value, self._identity_grid_host)
            val.setWordWrap(True)
            grid.addWidget(lab, i, 0)
            grid.addWidget(val, i, 1)
        grid.setColumnStretch(1, 1)

    def _load_profiles_and_assignments(self) -> None:
        try:
            self._profiles = (
                self._registry.compensation_profile_service.list_profiles(
                    self._company_id, employee_id=self._employee_id, active_only=False,
                )
            )
        except Exception:  # noqa: BLE001
            self._profiles = []
        try:
            self._assignments = (
                self._registry.component_assignment_service.list_assignments(
                    self._company_id, employee_id=self._employee_id, active_only=False,
                )
            )
        except Exception:  # noqa: BLE001
            self._assignments = []

        self._profiles_table.setRowCount(0)
        for p in sorted(self._profiles, key=lambda x: x.effective_from, reverse=True):
            row = self._profiles_table.rowCount()
            self._profiles_table.insertRow(row)
            self._profiles_table.setItem(
                row, 0, QTableWidgetItem(p.effective_from.isoformat())
            )
            amt = QTableWidgetItem(f"{p.basic_salary:,.2f}")
            amt.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._profiles_table.setItem(row, 1, amt)
            self._profiles_table.setItem(row, 2, QTableWidgetItem(p.currency_code))
            self._profiles_table.setItem(
                row, 3, QTableWidgetItem("Active" if p.is_active else "Inactive")
            )
        self._profiles_table.resizeColumnsToContents()

        self._assignments_table.setRowCount(0)
        for a in sorted(self._assignments, key=lambda x: x.effective_from, reverse=True):
            row = self._assignments_table.rowCount()
            self._assignments_table.insertRow(row)
            self._assignments_table.setItem(
                row, 0, QTableWidgetItem(a.component_name)
            )
            self._assignments_table.setItem(
                row, 1, QTableWidgetItem(a.component_type_code)
            )
            self._assignments_table.setItem(
                row, 2, QTableWidgetItem(a.effective_from.isoformat())
            )
            self._assignments_table.setItem(
                row, 3, QTableWidgetItem("Active" if a.is_active else "Inactive")
            )
        self._assignments_table.resizeColumnsToContents()

    def _scan_gaps(self) -> None:
        emp = self._employee
        assert emp is not None
        today = date.today()

        tax_missing = not (emp.tax_identifier and emp.cnps_number)
        payment_missing = emp.default_payment_account_id is None

        has_comp = any(
            p.effective_from <= today
            and (p.effective_to is None or p.effective_to >= today)
            and p.is_active
            for p in self._profiles
        )
        has_assignments = any(a.is_active for a in self._assignments)

        self._gaps = {
            "tax_cnps":   tax_missing,
            "payment":    payment_missing,
            "comp":       not has_comp,
            "components": not has_assignments,
        }

    def _refresh_readiness(self) -> None:
        for key, pill in self._readiness_pills.items():
            missing = self._gaps.get(key, False)
            if missing:
                pill.setText(f"⚠ {pill.text().replace('⚠ ', '').replace('✓ ', '')}")
                pill.setStyleSheet(
                    "padding: 4px 10px; border-radius: 8px;"
                    " background: #fff7e6; color: #b25503; font-weight: 600;"
                )
                # Normalize text back to label without badge repeat.
            else:
                pill.setStyleSheet(
                    "padding: 4px 10px; border-radius: 8px;"
                    " background: #e6f4ea; color: #1a7a2e; font-weight: 600;"
                )

        # Reset pill text so repeat calls don't stack badges.
        labels_map = {
            "tax_cnps":   "Tax & CNPS",
            "payment":    "Payment",
            "comp":       "Compensation",
            "components": "Components",
        }
        for key, pill in self._readiness_pills.items():
            base = labels_map[key]
            badge = "⚠ " if self._gaps.get(key) else "✓ "
            pill.setText(badge + base)

        gap_count = sum(1 for v in self._gaps.values() if v)
        self._readiness_summary.setText(
            "Payroll-ready"
            if gap_count == 0
            else f"{gap_count} gap(s) — run Payroll Setup to fill them in."
        )

    def _load_recent_runs(self) -> None:
        self._recent_runs = []
        try:
            runs = self._registry.payroll_run_service.list_runs(self._company_id)
        except Exception:  # noqa: BLE001
            runs = []
        runs = sorted(runs, key=lambda r: (r.period_year, r.period_month), reverse=True)
        for run in runs:
            try:
                emps = self._registry.payroll_run_service.list_run_employees(
                    self._company_id, run.id,
                )
            except Exception:  # noqa: BLE001
                continue
            hit = next((e for e in emps if e.employee_id == self._employee_id), None)
            if hit is None:
                continue
            self._recent_runs.append((run, hit))
            if len(self._recent_runs) >= 8:
                break

        self._runs_table.setRowCount(0)
        for run, hit in self._recent_runs:
            row = self._runs_table.rowCount()
            self._runs_table.insertRow(row)
            self._runs_table.setItem(row, 0, QTableWidgetItem(run.run_reference))
            period_name = (
                _MONTHS[run.period_month] if 1 <= run.period_month <= 12 else ""
            )
            self._runs_table.setItem(
                row, 1, QTableWidgetItem(f"{period_name} {run.period_year}")
            )
            gross = QTableWidgetItem(f"{hit.gross_earnings:,.2f}")
            gross.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._runs_table.setItem(row, 2, gross)
            net = QTableWidgetItem(f"{hit.net_payable:,.2f}")
            net.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._runs_table.setItem(row, 3, net)
            self._runs_table.setItem(
                row, 4,
                QTableWidgetItem(
                    _RUN_STATUS_LABELS.get(run.status_code, run.status_code)
                ),
            )
        self._runs_table.resizeColumnsToContents()

    # ── Ribbon host ───────────────────────────────────────────────────

    def handle_ribbon_command(self, command_id: str) -> None:  # type: ignore[override]
        dispatch = {
            "payroll_employee_hub.edit":                 self._on_edit,
            "payroll_employee_hub.payroll_setup_wizard": self._on_payroll_setup,
            "payroll_employee_hub.compensation_change":  self._on_compensation_change,
            "payroll_employee_hub.new_assignment":       self._on_new_assignment,
            "payroll_employee_hub.deactivate":           self._on_deactivate,
            "payroll_employee_hub.reactivate":           self._on_reactivate,
            "payroll_employee_hub.refresh":              self._reload,
            "payroll_employee_hub.close":                self.close,
        }
        handler = dispatch.get(command_id)
        if handler is not None:
            handler()

    def ribbon_state(self) -> dict[str, bool]:  # type: ignore[override]
        loaded = self._employee is not None
        active = bool(self._employee and self._employee.is_active)
        return {
            "payroll_employee_hub.edit":                 loaded,
            "payroll_employee_hub.payroll_setup_wizard": loaded and active,
            "payroll_employee_hub.compensation_change":  loaded and active,
            "payroll_employee_hub.new_assignment":       loaded and active,
            "payroll_employee_hub.deactivate":           loaded and active,
            "payroll_employee_hub.reactivate":           loaded and not active,
            "payroll_employee_hub.refresh":              True,
            "payroll_employee_hub.close":                True,
        }

    # ── Command handlers ──────────────────────────────────────────────

    def _on_edit(self) -> None:
        dlg = EmployeeFormDialog(
            self._registry,
            self._company_id,
            self._company_name,
            employee_id=self._employee_id,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_payroll_setup(self) -> None:
        result = EmployeePayrollSetupWizardDialog.run(
            self._registry,
            self._company_id,
            self._company_name,
            employee_id=self._employee_id,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _on_compensation_change(self) -> None:
        result = CompensationChangeWizardDialog.run(
            self._registry,
            self._company_id,
            self._company_name,
            employee_id=self._employee_id,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _on_new_assignment(self) -> None:
        dlg = ComponentAssignmentDialog(
            self._registry,
            self._company_id,
            self._employee_id,
            existing=None,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_deactivate(self) -> None:
        emp = self._employee
        if emp is None or not emp.is_active:
            return
        if QMessageBox.question(
            self,
            "Deactivate Employee",
            f"Deactivate {emp.display_name}? They will be excluded from "
            "future payroll runs.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.employee_service.update_employee(
                self._company_id, emp.id,
                UpdateEmployeeCommand(
                    employee_number=emp.employee_number,
                    display_name=emp.display_name,
                    first_name=emp.first_name,
                    last_name=emp.last_name,
                    hire_date=emp.hire_date,
                    base_currency_code=emp.base_currency_code,
                    is_active=False,
                    department_id=emp.department_id,
                    position_id=emp.position_id,
                    termination_date=emp.termination_date or date.today(),
                    phone=emp.phone,
                    email=emp.email,
                    tax_identifier=emp.tax_identifier,
                    cnps_number=emp.cnps_number,
                    default_payment_account_id=emp.default_payment_account_id,
                ),
            )
        except (ValidationError, ConflictError, NotFoundError,
                PermissionDeniedError) as exc:
            show_error(self, "Employee Hub", str(exc))
            return
        self._reload()

    def _on_reactivate(self) -> None:
        emp = self._employee
        if emp is None or emp.is_active:
            return
        try:
            self._registry.employee_service.update_employee(
                self._company_id, emp.id,
                UpdateEmployeeCommand(
                    employee_number=emp.employee_number,
                    display_name=emp.display_name,
                    first_name=emp.first_name,
                    last_name=emp.last_name,
                    hire_date=emp.hire_date,
                    base_currency_code=emp.base_currency_code,
                    is_active=True,
                    department_id=emp.department_id,
                    position_id=emp.position_id,
                    termination_date=None,
                    phone=emp.phone,
                    email=emp.email,
                    tax_identifier=emp.tax_identifier,
                    cnps_number=emp.cnps_number,
                    default_payment_account_id=emp.default_payment_account_id,
                ),
            )
        except (ValidationError, ConflictError, NotFoundError,
                PermissionDeniedError) as exc:
            show_error(self, "Employee Hub", str(exc))
            return
        self._reload()
