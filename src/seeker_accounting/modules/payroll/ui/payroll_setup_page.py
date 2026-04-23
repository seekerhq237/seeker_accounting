from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.payroll.ui.dialogs.company_payroll_settings_dialog import (
    CompanyPayrollSettingsDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.employee_form_dialog import EmployeeFormDialog
from seeker_accounting.modules.payroll.ui.dialogs.payroll_component_form_dialog import (
    PayrollComponentFormDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.apply_statutory_pack_dialog import (
    ApplyStatutoryPackDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.department_dialog import DepartmentManagementDialog
from seeker_accounting.modules.payroll.ui.dialogs.payroll_rule_brackets_dialog import (
    PayrollRuleBracketsDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_rule_set_form_dialog import (
    PayrollRuleSetFormDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.position_dialog import PositionManagementDialog
from seeker_accounting.modules.payroll.ui.employee_hub_window import EmployeeHubWindow
from seeker_accounting.modules.payroll.ui.wizards.compensation_change_wizard import (
    CompensationChangeWizardDialog,
)
from seeker_accounting.modules.payroll.ui.wizards.employee_hire_wizard import (
    EmployeeHireWizardDialog,
)
from seeker_accounting.modules.payroll.ui.wizards.employee_payroll_setup_wizard import (
    EmployeePayrollSetupWizardDialog,
)
from seeker_accounting.modules.payroll.ui.wizards.payroll_activation_wizard import (
    PayrollActivationWizardDialog,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_PAY_FREQ_LABELS = {
    "monthly":   "Monthly",
    "bi_monthly": "Bi-Monthly",
    "bi_weekly": "Bi-Weekly",
    "weekly":    "Weekly",
    "daily":     "Daily",
}

_COMP_TYPE_LABELS = {
    "earning":              "Earning",
    "deduction":            "Deduction",
    "employer_contribution":"Employer Contribution",
    "tax":                  "Tax",
    "informational":        "Informational",
}

_CALC_METHOD_LABELS = {
    "fixed_amount": "Fixed Amount",
    "percentage":   "Percentage",
    "rule_based":   "Rule Based",
    "manual_input": "Manual Input",
    "hourly":       "Hourly",
}

_RULE_TYPE_LABELS = {
    "pit":               "PIT (IRPP)",
    "pension_employee":  "Pension — Employee",
    "pension_employer":  "Pension — Employer",
    "accident_risk":     "Accident Risk",
    "overtime":          "Overtime",
    "levy":              "Levy",
    "other":             "Other",
}


class PayrollSetupPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = service_registry

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_tabs(), 1)

        self._sr.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        layout.addStretch(1)

        self._configure_btn = QPushButton("Configure Settings", card)
        self._configure_btn.setProperty("variant", "primary")
        self._configure_btn.clicked.connect(self._on_configure_settings)
        layout.addWidget(self._configure_btn)

        self._seed_btn = QPushButton("Apply Statutory Pack…", card)
        self._seed_btn.setProperty("variant", "secondary")
        self._seed_btn.clicked.connect(self._on_seed_cameroon)
        layout.addWidget(self._seed_btn)

        refresh_btn = QPushButton("Refresh", card)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(self.reload)
        layout.addWidget(refresh_btn)
        return card

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self) -> QWidget:
        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.currentChanged.connect(lambda *_: self._notify_ribbon_context_changed())

        self._tabs.addTab(self._build_settings_tab(), "Company Settings")
        self._tabs.addTab(self._build_employees_tab(), "Employees")
        self._tabs.addTab(self._build_components_tab(), "Payroll Components")
        self._tabs.addTab(self._build_rules_tab(), "Payroll Rules")
        return self._tabs

    # ── Settings tab ──────────────────────────────────────────────────────────

    def _build_settings_tab(self) -> QWidget:
        self._settings_stack = QStackedWidget()
        self._settings_view = self._build_settings_view()
        self._settings_empty = self._build_settings_empty()
        self._settings_no_company = self._build_no_company_state(
            "Select an active company to view payroll configuration."
        )
        self._settings_stack.addWidget(self._settings_view)
        self._settings_stack.addWidget(self._settings_empty)
        self._settings_stack.addWidget(self._settings_no_company)
        return self._settings_stack

    def _build_settings_view(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        top = QWidget(card)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        title = QLabel("Payroll Configuration", top)
        title.setObjectName("CardTitle")
        tl.addWidget(title, 1)
        edit_btn = QPushButton("Edit", top)
        edit_btn.setProperty("variant", "secondary")
        edit_btn.clicked.connect(self._on_configure_settings)
        tl.addWidget(edit_btn)
        layout.addWidget(top)

        self._settings_fields: dict[str, QLabel] = {}
        field_defs = [
            ("pay_frequency",    "Default Pay Frequency"),
            ("currency",         "Default Currency"),
            ("statutory_pack",   "Statutory Pack Version"),
            ("cnps_regime",      "CNPS Regime"),
            ("accident_class",   "Accident Risk Class"),
            ("overtime_mode",    "Overtime Policy Mode"),
            ("bik_mode",         "Benefits in Kind Policy"),
            ("number_prefix",    "Payroll Number Prefix"),
            ("number_padding",   "Number Padding Width"),
        ]
        for key, label_text in field_defs:
            row = QWidget(card)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)
            lbl = QLabel(label_text, row)
            lbl.setProperty("role", "caption")
            lbl.setFixedWidth(200)
            val = QLabel("—", row)
            self._settings_fields[key] = val
            row_layout.addWidget(lbl)
            row_layout.addWidget(val, 1)
            layout.addWidget(row)

        layout.addStretch(1)
        return card

    def _build_settings_empty(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("Payroll not yet configured", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        msg = QLabel(
            "Run the guided activation wizard to set up payroll for this company "
            "in one pass — settings, statutory pack, departments, and positions. "
            "Prefer the hands-on route? Use Configure Settings for the standalone "
            "settings form.", card
        )
        msg.setObjectName("PageSummary")
        msg.setWordWrap(True)
        layout.addWidget(msg)
        act = QWidget(card)
        al = QHBoxLayout(act)
        al.setContentsMargins(0, 6, 0, 0)
        al.setSpacing(8)
        wizard_btn = QPushButton("Run Activation Wizard", act)
        wizard_btn.setProperty("variant", "primary")
        wizard_btn.clicked.connect(self._on_activation_wizard)
        al.addWidget(wizard_btn, 0, Qt.AlignmentFlag.AlignLeft)
        btn = QPushButton("Configure Settings", act)
        btn.setProperty("variant", "secondary")
        btn.clicked.connect(self._on_configure_settings)
        al.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
        al.addStretch(1)
        layout.addWidget(act)
        layout.addStretch(1)
        return card

    # ── Employees tab ─────────────────────────────────────────────────────────

    def _build_employees_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        # Filter bar
        filter_bar = QWidget(container)
        fl = QHBoxLayout(filter_bar)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(8)
        self._emp_search = QLineEdit(filter_bar)
        self._emp_search.setPlaceholderText("Search by number or name...")
        self._emp_search.textChanged.connect(self._reload_employees)
        fl.addWidget(self._emp_search, 1)
        self._emp_inactive_cb = QCheckBox("Show inactive", filter_bar)
        self._emp_inactive_cb.stateChanged.connect(self._reload_employees)
        fl.addWidget(self._emp_inactive_cb)
        emp_new_btn = QPushButton("New Employee", filter_bar)
        emp_new_btn.setProperty("variant", "primary")
        emp_new_btn.clicked.connect(self._on_new_employee)
        fl.addWidget(emp_new_btn)
        self._emp_edit_btn = QPushButton("Edit", filter_bar)
        self._emp_edit_btn.setProperty("variant", "secondary")
        self._emp_edit_btn.clicked.connect(self._on_edit_employee)
        fl.addWidget(self._emp_edit_btn)
        self._emp_deactivate_btn = QPushButton("Deactivate", filter_bar)
        self._emp_deactivate_btn.setProperty("variant", "secondary")
        self._emp_deactivate_btn.clicked.connect(self._on_deactivate_employee)
        fl.addWidget(self._emp_deactivate_btn)
        dept_btn = QPushButton("Departments…", filter_bar)
        dept_btn.setProperty("variant", "ghost")
        dept_btn.clicked.connect(self._on_manage_departments)
        fl.addWidget(dept_btn)
        pos_btn = QPushButton("Positions…", filter_bar)
        pos_btn.setProperty("variant", "ghost")
        pos_btn.clicked.connect(self._on_manage_positions)
        fl.addWidget(pos_btn)
        layout.addWidget(filter_bar)

        self._emp_stack = QStackedWidget(container)
        self._emp_table_surface = self._build_employee_table()
        self._emp_empty = self._build_list_empty("No employees yet", "Create the first employee record.")
        self._emp_no_company = self._build_no_company_state("Employees are company-scoped.")
        self._emp_stack.addWidget(self._emp_table_surface)
        self._emp_stack.addWidget(self._emp_empty)
        self._emp_stack.addWidget(self._emp_no_company)
        layout.addWidget(self._emp_stack, 1)
        return container

    def _build_employee_table(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        self._emp_table = QTableWidget(card)
        self._emp_table.setColumnCount(7)
        self._emp_table.setHorizontalHeaderLabels(
            ("Employee No.", "Name", "Department", "Position", "Hire Date", "Currency", "Status")
        )
        configure_compact_table(self._emp_table)
        self._emp_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._emp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._emp_table.doubleClicked.connect(lambda _: self._on_open_employee_hub())
        self._emp_table.selectionModel().selectionChanged.connect(
            lambda *_: self._notify_ribbon_context_changed()
        )
        layout.addWidget(self._emp_table)
        return card

    # ── Components tab ────────────────────────────────────────────────────────

    def _build_components_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        comp_bar = QWidget(container)
        cl = QHBoxLayout(comp_bar)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        self._comp_inactive_cb = QCheckBox("Show inactive", comp_bar)
        self._comp_inactive_cb.stateChanged.connect(self._reload_components)
        cl.addWidget(self._comp_inactive_cb)
        cl.addStretch(1)
        comp_new_btn = QPushButton("New Component", comp_bar)
        comp_new_btn.setProperty("variant", "primary")
        comp_new_btn.clicked.connect(self._on_new_component)
        cl.addWidget(comp_new_btn)
        self._comp_edit_btn = QPushButton("Edit", comp_bar)
        self._comp_edit_btn.setProperty("variant", "secondary")
        self._comp_edit_btn.clicked.connect(self._on_edit_component)
        cl.addWidget(self._comp_edit_btn)
        self._comp_deact_btn = QPushButton("Deactivate", comp_bar)
        self._comp_deact_btn.setProperty("variant", "secondary")
        self._comp_deact_btn.clicked.connect(self._on_deactivate_component)
        cl.addWidget(self._comp_deact_btn)
        layout.addWidget(comp_bar)

        self._comp_stack = QStackedWidget(container)
        self._comp_table_surface = self._build_component_table()
        self._comp_empty = self._build_list_empty(
            "No payroll components yet",
            "Seed Cameroon defaults or create components manually."
        )
        self._comp_no_company = self._build_no_company_state("Payroll components are company-scoped.")
        self._comp_stack.addWidget(self._comp_table_surface)
        self._comp_stack.addWidget(self._comp_empty)
        self._comp_stack.addWidget(self._comp_no_company)
        layout.addWidget(self._comp_stack, 1)
        return container

    def _build_component_table(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        self._comp_table = QTableWidget(card)
        self._comp_table.setColumnCount(8)
        self._comp_table.setHorizontalHeaderLabels(
            ("Code", "Name", "Type", "Method", "Taxable", "Pensionable",
             "Expense Account", "Status")
        )
        configure_compact_table(self._comp_table)
        self._comp_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._comp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._comp_table.doubleClicked.connect(lambda _: self._on_edit_component())
        self._comp_table.selectionModel().selectionChanged.connect(
            lambda *_: self._notify_ribbon_context_changed()
        )
        layout.addWidget(self._comp_table)
        return card

    # ── Rules tab ─────────────────────────────────────────────────────────────

    def _build_rules_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        rule_bar = QWidget(container)
        rl = QHBoxLayout(rule_bar)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self._rule_inactive_cb = QCheckBox("Show inactive", rule_bar)
        self._rule_inactive_cb.stateChanged.connect(self._reload_rules)
        rl.addWidget(self._rule_inactive_cb)
        rl.addStretch(1)
        rule_new_btn = QPushButton("New Rule Set", rule_bar)
        rule_new_btn.setProperty("variant", "primary")
        rule_new_btn.clicked.connect(self._on_new_rule_set)
        rl.addWidget(rule_new_btn)
        self._rule_edit_btn = QPushButton("Edit", rule_bar)
        self._rule_edit_btn.setProperty("variant", "secondary")
        self._rule_edit_btn.clicked.connect(self._on_edit_rule_set)
        rl.addWidget(self._rule_edit_btn)
        self._rule_brackets_btn = QPushButton("Edit Brackets", rule_bar)
        self._rule_brackets_btn.setProperty("variant", "secondary")
        self._rule_brackets_btn.clicked.connect(self._on_edit_brackets)
        rl.addWidget(self._rule_brackets_btn)
        self._rule_deact_btn = QPushButton("Deactivate", rule_bar)
        self._rule_deact_btn.setProperty("variant", "secondary")
        self._rule_deact_btn.clicked.connect(self._on_deactivate_rule_set)
        rl.addWidget(self._rule_deact_btn)
        layout.addWidget(rule_bar)

        self._rule_stack = QStackedWidget(container)
        self._rule_table_surface = self._build_rule_table()
        self._rule_empty = self._build_list_empty(
            "No payroll rule sets yet",
            "Seed Cameroon defaults or create rule sets manually."
        )
        self._rule_no_company = self._build_no_company_state("Payroll rule sets are company-scoped.")
        self._rule_stack.addWidget(self._rule_table_surface)
        self._rule_stack.addWidget(self._rule_empty)
        self._rule_stack.addWidget(self._rule_no_company)
        layout.addWidget(self._rule_stack, 1)
        return container

    def _build_rule_table(self) -> QWidget:
        card = QFrame()
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        self._rule_table = QTableWidget(card)
        self._rule_table.setColumnCount(7)
        self._rule_table.setHorizontalHeaderLabels(
            ("Code", "Name", "Type", "Effective From", "Effective To", "Brackets", "Status")
        )
        configure_compact_table(self._rule_table)
        self._rule_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._rule_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._rule_table.doubleClicked.connect(lambda _: self._on_edit_brackets())
        self._rule_table.selectionModel().selectionChanged.connect(
            lambda *_: self._notify_ribbon_context_changed()
        )
        layout.addWidget(self._rule_table)
        return card

    # ── Shared state builders ─────────────────────────────────────────────────

    def _build_no_company_state(self, msg: str) -> QWidget:
        card = QFrame()
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        sub = QLabel(msg, card)
        sub.setObjectName("PageSummary")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addStretch(1)
        return card

    def _build_list_empty(self, title_text: str, body_text: str) -> QWidget:
        card = QFrame()
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel(title_text, card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        msg = QLabel(body_text, card)
        msg.setObjectName("PageSummary")
        msg.setWordWrap(True)
        layout.addWidget(msg)
        layout.addStretch(1)
        return card

    # ── Reload orchestration ──────────────────────────────────────────────────

    def reload(self) -> None:
        company = self._active_company()
        self._reload_settings(company)
        self._reload_employees()
        self._reload_components()
        self._reload_rules()
        self._notify_ribbon_context_changed()

    def _reload_settings(self, company: ActiveCompanyDTO | None) -> None:
        if company is None:
            self._settings_stack.setCurrentWidget(self._settings_no_company)
            return
        try:
            ws = self._sr.payroll_setup_service.get_payroll_setup_workspace(company.company_id)
        except Exception as exc:
            show_error(self, "Payroll Setup", f"Could not load payroll settings.\n\n{exc}")
            self._settings_stack.setCurrentWidget(self._settings_empty)
            return
        if ws.settings is None:
            self._settings_stack.setCurrentWidget(self._settings_empty)
            return
        s = ws.settings
        self._settings_fields["pay_frequency"].setText(
            _PAY_FREQ_LABELS.get(s.default_pay_frequency_code, s.default_pay_frequency_code)
        )
        self._settings_fields["currency"].setText(s.default_payroll_currency_code)
        self._settings_fields["statutory_pack"].setText(s.statutory_pack_version_code or "—")
        self._settings_fields["cnps_regime"].setText(s.cnps_regime_code or "—")
        self._settings_fields["accident_class"].setText(s.accident_risk_class_code or "—")
        self._settings_fields["overtime_mode"].setText(s.overtime_policy_mode_code or "—")
        self._settings_fields["bik_mode"].setText(s.benefit_in_kind_policy_mode_code or "—")
        self._settings_fields["number_prefix"].setText(s.payroll_number_prefix or "—")
        self._settings_fields["number_padding"].setText(
            str(s.payroll_number_padding_width) if s.payroll_number_padding_width else "—"
        )
        self._settings_stack.setCurrentWidget(self._settings_view)

    def _reload_employees(self) -> None:
        company = self._active_company()
        if company is None:
            self._emp_table.setRowCount(0)
            self._emp_stack.setCurrentWidget(self._emp_no_company)
            return
        query = self._emp_search.text().strip() or None
        active_only = not self._emp_inactive_cb.isChecked()
        try:
            rows = self._sr.employee_service.list_employees(
                company.company_id, active_only=active_only, query=query
            )
        except Exception as exc:
            show_error(self, "Employees", f"Could not load employees.\n\n{exc}")
            self._emp_table.setRowCount(0)
            self._emp_stack.setCurrentWidget(self._emp_empty)
            return
        self._populate_employees(rows)
        self._emp_stack.setCurrentWidget(
            self._emp_table_surface if rows else self._emp_empty
        )

    def _reload_components(self) -> None:
        company = self._active_company()
        if company is None:
            self._comp_table.setRowCount(0)
            self._comp_stack.setCurrentWidget(self._comp_no_company)
            return
        active_only = not self._comp_inactive_cb.isChecked()
        try:
            rows = self._sr.payroll_component_service.list_components(
                company.company_id, active_only=active_only
            )
        except Exception as exc:
            show_error(self, "Payroll Components", f"Could not load components.\n\n{exc}")
            self._comp_table.setRowCount(0)
            self._comp_stack.setCurrentWidget(self._comp_empty)
            return
        self._populate_components(rows)
        self._comp_stack.setCurrentWidget(
            self._comp_table_surface if rows else self._comp_empty
        )

    def _reload_rules(self) -> None:
        company = self._active_company()
        if company is None:
            self._rule_table.setRowCount(0)
            self._rule_stack.setCurrentWidget(self._rule_no_company)
            return
        active_only = not self._rule_inactive_cb.isChecked()
        try:
            rows = self._sr.payroll_rule_service.list_rule_sets(
                company.company_id, active_only=active_only
            )
        except Exception as exc:
            show_error(self, "Payroll Rules", f"Could not load rule sets.\n\n{exc}")
            self._rule_table.setRowCount(0)
            self._rule_stack.setCurrentWidget(self._rule_empty)
            return
        self._populate_rules(rows)
        self._rule_stack.setCurrentWidget(
            self._rule_table_surface if rows else self._rule_empty
        )

    # ── Populate helpers ──────────────────────────────────────────────────────

    def _populate_employees(self, rows: list) -> None:
        self._emp_table.setSortingEnabled(False)
        self._emp_table.setRowCount(0)
        for row in rows:
            ri = self._emp_table.rowCount()
            self._emp_table.insertRow(ri)
            num_item = QTableWidgetItem(row.employee_number)
            num_item.setData(Qt.ItemDataRole.UserRole, row.id)
            self._emp_table.setItem(ri, 0, num_item)
            self._emp_table.setItem(ri, 1, QTableWidgetItem(row.display_name))
            self._emp_table.setItem(ri, 2, QTableWidgetItem(row.department_name or "—"))
            self._emp_table.setItem(ri, 3, QTableWidgetItem(row.position_name or "—"))
            self._emp_table.setItem(ri, 4, QTableWidgetItem(str(row.hire_date)))
            self._emp_table.setItem(ri, 5, QTableWidgetItem(row.base_currency_code))
            self._emp_table.setItem(ri, 6, QTableWidgetItem("Active" if row.is_active else "Inactive"))
        self._emp_table.resizeColumnsToContents()
        hdr = self._emp_table.horizontalHeader()
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)
        self._emp_table.setSortingEnabled(True)

    def _populate_components(self, rows: list) -> None:
        self._comp_table.setSortingEnabled(False)
        self._comp_table.setRowCount(0)
        for row in rows:
            ri = self._comp_table.rowCount()
            self._comp_table.insertRow(ri)
            code_item = QTableWidgetItem(row.component_code)
            code_item.setData(Qt.ItemDataRole.UserRole, row.id)
            self._comp_table.setItem(ri, 0, code_item)
            self._comp_table.setItem(ri, 1, QTableWidgetItem(row.component_name))
            self._comp_table.setItem(ri, 2, QTableWidgetItem(
                _COMP_TYPE_LABELS.get(row.component_type_code, row.component_type_code)
            ))
            self._comp_table.setItem(ri, 3, QTableWidgetItem(
                _CALC_METHOD_LABELS.get(row.calculation_method_code, row.calculation_method_code)
            ))
            self._comp_table.setItem(ri, 4, QTableWidgetItem("Yes" if row.is_taxable else "No"))
            self._comp_table.setItem(ri, 5, QTableWidgetItem("Yes" if row.is_pensionable else "No"))
            self._comp_table.setItem(ri, 6, QTableWidgetItem(
                row.expense_account_code or "—"
            ))
            self._comp_table.setItem(ri, 7, QTableWidgetItem(
                "Active" if row.is_active else "Inactive"
            ))
        self._comp_table.resizeColumnsToContents()
        hdr = self._comp_table.horizontalHeader()
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)
        self._comp_table.setSortingEnabled(True)

    def _populate_rules(self, rows: list) -> None:
        self._rule_table.setSortingEnabled(False)
        self._rule_table.setRowCount(0)
        for row in rows:
            ri = self._rule_table.rowCount()
            self._rule_table.insertRow(ri)
            code_item = QTableWidgetItem(row.rule_code)
            code_item.setData(Qt.ItemDataRole.UserRole, row.id)
            self._rule_table.setItem(ri, 0, code_item)
            self._rule_table.setItem(ri, 1, QTableWidgetItem(row.rule_name))
            self._rule_table.setItem(ri, 2, QTableWidgetItem(
                _RULE_TYPE_LABELS.get(row.rule_type_code, row.rule_type_code)
            ))
            self._rule_table.setItem(ri, 3, QTableWidgetItem(str(row.effective_from)))
            self._rule_table.setItem(ri, 4, QTableWidgetItem(
                str(row.effective_to) if row.effective_to else "Open-ended"
            ))
            self._rule_table.setItem(ri, 5, QTableWidgetItem(str(row.bracket_count)))
            self._rule_table.setItem(ri, 6, QTableWidgetItem(
                "Active" if row.is_active else "Inactive"
            ))
        self._rule_table.resizeColumnsToContents()
        hdr = self._rule_table.horizontalHeader()
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)
        self._rule_table.setSortingEnabled(True)

    # ── Actions — Settings ────────────────────────────────────────────────────

    def _on_activation_wizard(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Setup", "Select an active company first.")
            return
        result = PayrollActivationWizardDialog.run(
            self._sr, company.company_id, company.company_name, parent=self
        )
        if result is not None:
            self._reload_settings(company)
            self._tabs.setCurrentIndex(0)
            self._notify_ribbon_context_changed()
            show_info(self, "Payroll Activation", result.summary)

    def _on_hire_employee_wizard(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Setup", "Select an active company first.")
            return
        result = EmployeeHireWizardDialog.run(
            self._sr, company.company_id, company.company_name, parent=self
        )
        if result is not None:
            self._reload_employees()
            self._tabs.setCurrentIndex(1)
            self._notify_ribbon_context_changed()
            show_info(self, "Hire Employee", result.summary)

    def _on_open_employee_hub(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Setup", "Select an active company first.")
            return
        employee_id = self._selected_id(self._emp_table)
        if employee_id is None:
            show_error(self, "Employee Hub", "Select an employee first.")
            return
        manager = getattr(self._sr, "child_window_manager", None)
        cid = company.company_id

        def factory() -> EmployeeHubWindow:
            return EmployeeHubWindow(
                self._sr, company_id=cid, employee_id=employee_id,
            )
        if manager is not None:
            manager.open_document(EmployeeHubWindow.DOC_TYPE, employee_id, factory)
        else:
            win = factory()
            win.show()

    def _on_employee_payroll_setup_wizard(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Setup", "Select an active company first.")
            return
        employee_id = self._selected_id(self._emp_table)
        if employee_id is None:
            show_error(self, "Payroll Setup", "Select an employee first.")
            return
        result = EmployeePayrollSetupWizardDialog.run(
            self._sr, company.company_id, company.company_name,
            employee_id=employee_id, parent=self,
        )
        if result is not None:
            self._reload_employees()
            self._tabs.setCurrentIndex(1)
            self._notify_ribbon_context_changed()
            show_info(self, "Payroll Setup", result.summary)

    def _on_compensation_change_wizard(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Setup", "Select an active company first.")
            return
        employee_id = self._selected_id(self._emp_table)
        if employee_id is None:
            show_error(
                self, "Compensation Change",
                "Select an employee first.",
            )
            return
        result = CompensationChangeWizardDialog.run(
            self._sr, company.company_id, company.company_name,
            employee_id=employee_id, parent=self,
        )
        if result is not None:
            self._reload_employees()
            self._tabs.setCurrentIndex(1)
            self._notify_ribbon_context_changed()
            show_info(self, "Compensation Change", result.summary)

    def _on_configure_settings(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Setup", "Select an active company first.")
            return
        dialog = CompanyPayrollSettingsDialog(
            self._sr, company.company_id, company.company_name, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_settings(company)
            self._tabs.setCurrentIndex(0)
            self._notify_ribbon_context_changed()

    def _on_seed_cameroon(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Setup", "Select an active company first.")
            return
        settings = None
        try:
            settings = self._sr.payroll_setup_service.get_company_payroll_settings(
                company.company_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
        current_pack = settings.statutory_pack_version_code if settings else None
        dialog = ApplyStatutoryPackDialog(
            self._sr,
            company.company_id,
            company.company_name,
            current_pack_version=current_pack,
            parent=self,
        )
        dialog.exec()
        if dialog.applied_result is not None:
            self.reload()

    # ── Actions — Departments / Positions ────────────────────────────────────

    def _on_manage_departments(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Departments", "Select an active company first.")
            return
        dialog = DepartmentManagementDialog(
            self._sr, company.company_id, company.company_name, parent=self
        )
        dialog.exec()
        self._notify_ribbon_state_changed()

    def _on_manage_positions(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Positions", "Select an active company first.")
            return
        dialog = PositionManagementDialog(
            self._sr, company.company_id, company.company_name, parent=self
        )
        dialog.exec()
        self._notify_ribbon_state_changed()

    # ── Actions — Employees ───────────────────────────────────────────────────

    def _on_new_employee(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Employees", "Select an active company first.")
            return
        dialog = EmployeeFormDialog(
            self._sr, company.company_id, company.company_name, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_employees()

    def _on_edit_employee(self) -> None:
        company = self._active_company()
        if company is None:
            return
        emp_id = self._selected_id(self._emp_table)
        if emp_id is None:
            return
        dialog = EmployeeFormDialog(
            self._sr, company.company_id, company.company_name,
            employee_id=emp_id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_employees()

    def _on_deactivate_employee(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._emp_table.currentRow()
        if row < 0:
            return
        item = self._emp_table.item(row, 0)
        if item is None:
            return
        emp_id = item.data(Qt.ItemDataRole.UserRole)
        emp_name = self._emp_table.item(row, 1).text() if self._emp_table.item(row, 1) else ""
        reply = QMessageBox.question(
            self, "Deactivate Employee",
            f"Deactivate employee '{emp_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            detail = self._sr.employee_service.get_employee(company.company_id, emp_id)
            from seeker_accounting.modules.payroll.dto.employee_dto import UpdateEmployeeCommand
            cmd = UpdateEmployeeCommand(
                employee_number=detail.employee_number,
                display_name=detail.display_name,
                first_name=detail.first_name,
                last_name=detail.last_name,
                hire_date=detail.hire_date,
                base_currency_code=detail.base_currency_code,
                is_active=False,
                department_id=detail.department_id,
                position_id=detail.position_id,
                termination_date=detail.termination_date,
                phone=detail.phone,
                email=detail.email,
                tax_identifier=detail.tax_identifier,
            )
            self._sr.employee_service.update_employee(company.company_id, emp_id, cmd)
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Employees", str(exc))
            return
        self._reload_employees()

    # ── Actions — Components ──────────────────────────────────────────────────

    def _on_new_component(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Components", "Select an active company first.")
            return
        dialog = PayrollComponentFormDialog(
            self._sr, company.company_id, company.company_name, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_components()

    def _on_edit_component(self) -> None:
        company = self._active_company()
        if company is None:
            return
        comp_id = self._selected_id(self._comp_table)
        if comp_id is None:
            return
        dialog = PayrollComponentFormDialog(
            self._sr, company.company_id, company.company_name,
            component_id=comp_id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_components()

    def _on_deactivate_component(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._comp_table.currentRow()
        if row < 0:
            return
        item = self._comp_table.item(row, 0)
        if item is None:
            return
        comp_id = item.data(Qt.ItemDataRole.UserRole)
        comp_code = item.text()
        reply = QMessageBox.question(
            self, "Deactivate Component",
            f"Deactivate payroll component '{comp_code}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            detail = self._sr.payroll_component_service.get_component(company.company_id, comp_id)
            from seeker_accounting.modules.payroll.dto.payroll_component_dto import UpdatePayrollComponentCommand
            cmd = UpdatePayrollComponentCommand(
                component_code=detail.component_code,
                component_name=detail.component_name,
                component_type_code=detail.component_type_code,
                calculation_method_code=detail.calculation_method_code,
                is_taxable=detail.is_taxable,
                is_pensionable=detail.is_pensionable,
                is_active=False,
                expense_account_id=detail.expense_account_id,
                liability_account_id=detail.liability_account_id,
            )
            self._sr.payroll_component_service.update_component(company.company_id, comp_id, cmd)
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Payroll Components", str(exc))
            return
        self._reload_components()

    # ── Actions — Rules ───────────────────────────────────────────────────────

    def _on_new_rule_set(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Payroll Rules", "Select an active company first.")
            return
        dialog = PayrollRuleSetFormDialog(
            self._sr, company.company_id, company.company_name, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_rules()

    def _on_edit_rule_set(self) -> None:
        company = self._active_company()
        if company is None:
            return
        rule_id = self._selected_id(self._rule_table)
        if rule_id is None:
            return
        dialog = PayrollRuleSetFormDialog(
            self._sr, company.company_id, company.company_name,
            rule_set_id=rule_id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_rules()

    def _on_edit_brackets(self) -> None:
        company = self._active_company()
        if company is None:
            return
        rule_id = self._selected_id(self._rule_table)
        if rule_id is None:
            return
        row = self._rule_table.currentRow()
        rule_code = self._rule_table.item(row, 0).text() if self._rule_table.item(row, 0) else ""
        dialog = PayrollRuleBracketsDialog(
            self._sr, company.company_id, rule_id, rule_code, parent=self
        )
        dialog.exec()
        self._reload_rules()

    def _on_deactivate_rule_set(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._rule_table.currentRow()
        if row < 0:
            return
        item = self._rule_table.item(row, 0)
        if item is None:
            return
        rule_id = item.data(Qt.ItemDataRole.UserRole)
        rule_code = item.text()
        reply = QMessageBox.question(
            self, "Deactivate Rule Set",
            f"Deactivate rule set '{rule_code}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            detail = self._sr.payroll_rule_service.get_rule_set(company.company_id, rule_id)
            from seeker_accounting.modules.payroll.dto.payroll_rule_dto import UpdatePayrollRuleSetCommand
            cmd = UpdatePayrollRuleSetCommand(
                rule_code=detail.rule_code,
                rule_name=detail.rule_name,
                rule_type_code=detail.rule_type_code,
                effective_from=detail.effective_from,
                calculation_basis_code=detail.calculation_basis_code,
                is_active=False,
                effective_to=detail.effective_to,
            )
            self._sr.payroll_rule_service.update_rule_set(company.company_id, rule_id, cmd)
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Payroll Rules", str(exc))
            return
        self._reload_rules()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def current_ribbon_surface_key(self) -> str | None:
        tab_key = self._current_tab_key()
        if tab_key == "settings":
            return "payroll_setup.settings"
        if tab_key == "employees":
            if not self._has_employee_selected():
                return "payroll_setup.employees.none"
            if self._selected_employee_is_active():
                return "payroll_setup.employees.active"
            return "payroll_setup.employees.inactive"
        if tab_key == "components":
            if self._has_component_selected():
                return "payroll_setup.components.selected"
            return "payroll_setup.components.none"
        if tab_key == "rules":
            if self._has_rule_selected():
                return "payroll_setup.rules.selected"
            return "payroll_setup.rules.none"
        return "payroll_setup.settings"

    def _ribbon_commands(self):
        return {
            "payroll_setup.activation_wizard": self._on_activation_wizard,
            "payroll_setup.hire_employee_wizard": self._on_hire_employee_wizard,
            "payroll_setup.open_employee_hub": self._on_open_employee_hub,
            "payroll_setup.employee_payroll_setup_wizard": self._on_employee_payroll_setup_wizard,
            "payroll_setup.compensation_change_wizard": self._on_compensation_change_wizard,
            "payroll_setup.configure_settings": self._on_configure_settings,
            "payroll_setup.apply_pack": self._on_seed_cameroon,
            "payroll_setup.open_validation": self._open_validation_workspace,
            "payroll_setup.open_calculation": self._open_calculation_workspace,
            "payroll_setup.new_employee": self._on_new_employee,
            "payroll_setup.edit_employee": self._on_edit_employee,
            "payroll_setup.deactivate_employee": self._on_deactivate_employee,
            "payroll_setup.manage_departments": self._on_manage_departments,
            "payroll_setup.manage_positions": self._on_manage_positions,
            "payroll_setup.new_component": self._on_new_component,
            "payroll_setup.edit_component": self._on_edit_component,
            "payroll_setup.deactivate_component": self._on_deactivate_component,
            "payroll_setup.new_rule_set": self._on_new_rule_set,
            "payroll_setup.edit_rule_set": self._on_edit_rule_set,
            "payroll_setup.edit_brackets": self._on_edit_brackets,
            "payroll_setup.deactivate_rule_set": self._on_deactivate_rule_set,
            "payroll_setup.refresh": self.reload,
        }

    def ribbon_state(self):
        has_company = self._active_company() is not None
        has_employee = self._has_employee_selected()
        employee_active = self._selected_employee_is_active()
        has_component = self._has_component_selected()
        component_active = self._selected_component_is_active()
        has_rule = self._has_rule_selected()
        rule_active = self._selected_rule_is_active()
        return {
            "payroll_setup.activation_wizard": has_company,
            "payroll_setup.hire_employee_wizard": has_company,
            "payroll_setup.open_employee_hub": has_company and has_employee,
            "payroll_setup.employee_payroll_setup_wizard": has_company and has_employee and employee_active,
            "payroll_setup.compensation_change_wizard": has_company and has_employee and employee_active,
            "payroll_setup.configure_settings": has_company,
            "payroll_setup.apply_pack": has_company,
            "payroll_setup.open_validation": has_company,
            "payroll_setup.open_calculation": has_company,
            "payroll_setup.new_employee": has_company,
            "payroll_setup.edit_employee": has_company and has_employee,
            "payroll_setup.deactivate_employee": has_company and has_employee and employee_active,
            "payroll_setup.manage_departments": has_company,
            "payroll_setup.manage_positions": has_company,
            "payroll_setup.new_component": has_company,
            "payroll_setup.edit_component": has_company and has_component,
            "payroll_setup.deactivate_component": has_company and has_component and component_active,
            "payroll_setup.new_rule_set": has_company,
            "payroll_setup.edit_rule_set": has_company and has_rule,
            "payroll_setup.edit_brackets": has_company and has_rule,
            "payroll_setup.deactivate_rule_set": has_company and has_rule and rule_active,
            "payroll_setup.refresh": True,
        }

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._sr.company_context_service.get_active_company()

    def _current_tab_key(self) -> str:
        index = self._tabs.currentIndex()
        if index == 1:
            return "employees"
        if index == 2:
            return "components"
        if index == 3:
            return "rules"
        return "settings"

    def _has_employee_selected(self) -> bool:
        return self._selected_id(self._emp_table) is not None

    def _selected_employee_is_active(self) -> bool:
        row = self._emp_table.currentRow()
        if row < 0:
            return False
        item = self._emp_table.item(row, 6)
        return (item.text().strip().lower() if item is not None else "") == "active"

    def _has_component_selected(self) -> bool:
        return self._selected_id(self._comp_table) is not None

    def _selected_component_is_active(self) -> bool:
        row = self._comp_table.currentRow()
        if row < 0:
            return False
        item = self._comp_table.item(row, 7)
        return (item.text().strip().lower() if item is not None else "") == "active"

    def _has_rule_selected(self) -> bool:
        return self._selected_id(self._rule_table) is not None

    def _selected_rule_is_active(self) -> bool:
        row = self._rule_table.currentRow()
        if row < 0:
            return False
        item = self._rule_table.item(row, 6)
        return (item.text().strip().lower() if item is not None else "") == "active"

    def _open_validation_workspace(self) -> None:
        self._sr.navigation_service.navigate(
            nav_ids.PAYROLL_OPERATIONS,
            context={"payroll_tab": "validation"},
        )

    def _open_calculation_workspace(self) -> None:
        self._sr.navigation_service.navigate(
            nav_ids.PAYROLL_CALCULATION,
            context={"payroll_tab": "profiles"},
        )

    def _selected_id(self, table: QTableWidget) -> int | None:
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None
