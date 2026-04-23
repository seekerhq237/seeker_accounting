from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QRadioButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import (
    AccountListItemDTO,
)
from seeker_accounting.modules.accounting.chart_of_accounts.dto.chart_import_dto import (
    ChartImportPreviewDTO,
    ChartImportResultDTO,
    ImportChartTemplateCommand,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_profile import (
    BUILT_IN_TEMPLATE_CODE_OHADA,
)
from seeker_accounting.modules.accounting.chart_of_accounts.ui.account_form_dialog import (
    AccountFormDialog,
)
from seeker_accounting.modules.accounting.chart_of_accounts.ui.chart_import_dialog import (
    ChartImportDialog,
)
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    AccountRoleMappingDTO,
    AccountRoleOptionDTO,
    SetAccountRoleMappingCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog, check_write_or_raise
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


@dataclass(frozen=True, slots=True)
class ChartCustomizationWizardResult:
    baseline_applied: bool
    imported_count: int
    mappings_updated: int
    mappings_cleared: int
    summary: str


@dataclass(frozen=True, slots=True)
class _RoleAdvisorSpec:
    role_code: str
    area_label: str
    workflow: str
    requirement_default: str
    prefixes: tuple[str, ...]
    keywords: tuple[str, ...]
    preferred_codes: tuple[str, ...] = ()
    prefer_control: bool = False
    prefer_postable: bool = True
    expected_balance: str | None = None


@dataclass(frozen=True, slots=True)
class _AreaDefinition:
    key: str
    label: str
    prefixes: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TemplateAccount:
    account_code: str
    account_name: str
    parent_account_code: str | None
    account_class_code: str
    account_type_code: str
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool


@dataclass(frozen=True, slots=True)
class _AccountSignal:
    account_id: int | None
    account_code: str
    account_name: str
    account_class_code: str
    account_type_code: str
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    is_active: bool
    source: str


@dataclass(frozen=True, slots=True)
class _RoleCandidate:
    key: str
    account_id: int | None
    account_code: str
    account_name: str
    source: str
    is_active: bool
    allow_manual_posting: bool
    is_control_account: bool
    score: int
    reason: str


@dataclass(frozen=True, slots=True)
class _RolePlan:
    role_code: str
    role_label: str
    requirement: str
    workflow: str
    explanation: str
    current_mapping_account_id: int | None
    current_mapping_key: str | None
    suggested_key: str | None
    selected_key: str | None
    candidates: tuple[_RoleCandidate, ...]


@dataclass(frozen=True, slots=True)
class _WizardFinding:
    severity: str
    workflow: str
    message: str
    action_label: str


@dataclass(frozen=True, slots=True)
class _StructureRow:
    area_key: str
    account_code: str
    account_name: str
    source_label: str
    status_label: str
    note: str
    account_id: int | None


_ROLE_SPECS: dict[str, _RoleAdvisorSpec] = {
    "ar_control": _RoleAdvisorSpec(
        role_code="ar_control",
        area_label="Sales and receivables",
        workflow="Sales posting",
        requirement_default="blocker",
        prefixes=("41",),
        keywords=("receivable", "receivables", "debtor", "debtors", "customer", "customers", "client", "clients"),
        prefer_control=True,
        expected_balance="debit",
    ),
    "ap_control": _RoleAdvisorSpec(
        role_code="ap_control",
        area_label="Purchases and payables",
        workflow="Purchase posting",
        requirement_default="blocker",
        prefixes=("40",),
        keywords=("payable", "payables", "supplier", "suppliers", "vendor", "vendors", "creditor", "creditors"),
        prefer_control=True,
        expected_balance="credit",
    ),
    "inventory_control": _RoleAdvisorSpec(
        role_code="inventory_control",
        area_label="Inventory",
        workflow="Inventory valuation",
        requirement_default="recommended",
        prefixes=("31", "32", "33", "34", "35", "36", "37", "38"),
        keywords=("inventory", "stock", "stores", "materials", "goods"),
        expected_balance="debit",
    ),
    "cash_on_hand": _RoleAdvisorSpec(
        role_code="cash_on_hand",
        area_label="Treasury and cash",
        workflow="Cash payments",
        requirement_default="recommended",
        prefixes=("57", "53"),
        keywords=("cash", "caisse", "till", "hand"),
        expected_balance="debit",
    ),
    "petty_cash": _RoleAdvisorSpec(
        role_code="petty_cash",
        area_label="Treasury and cash",
        workflow="Small disbursements",
        requirement_default="optional",
        prefixes=("57", "58"),
        keywords=("petty", "imprest", "cash"),
        expected_balance="debit",
    ),
    "bank_main": _RoleAdvisorSpec(
        role_code="bank_main",
        area_label="Treasury and cash",
        workflow="Treasury settlement",
        requirement_default="blocker",
        prefixes=("52", "51"),
        keywords=("bank", "checking", "current", "settlement"),
        expected_balance="debit",
    ),
    "bank_clearing": _RoleAdvisorSpec(
        role_code="bank_clearing",
        area_label="Treasury and cash",
        workflow="Bank clearing",
        requirement_default="recommended",
        prefixes=("58",),
        keywords=("clearing", "transit", "transfer", "suspense"),
        expected_balance="debit",
    ),
    "sales_revenue_default": _RoleAdvisorSpec(
        role_code="sales_revenue_default",
        area_label="Sales and receivables",
        workflow="Sales posting",
        requirement_default="blocker",
        prefixes=("70", "71", "72"),
        keywords=("sales", "revenue", "turnover", "service"),
        expected_balance="credit",
    ),
    "purchases_expense_default": _RoleAdvisorSpec(
        role_code="purchases_expense_default",
        area_label="Purchases and payables",
        workflow="Purchase posting",
        requirement_default="blocker",
        prefixes=("60", "61", "62"),
        keywords=("purchase", "purchases", "expense", "consumable", "materials"),
        expected_balance="debit",
    ),
    "payroll_payable": _RoleAdvisorSpec(
        role_code="payroll_payable",
        area_label="Payroll",
        workflow="Payroll posting",
        requirement_default="recommended",
        prefixes=("42", "43"),
        keywords=("payroll", "salary", "salaries", "wages", "staff", "personnel"),
        expected_balance="credit",
    ),
    "vat_input": _RoleAdvisorSpec(
        role_code="vat_input",
        area_label="VAT and taxes",
        workflow="Purchase VAT posting",
        requirement_default="recommended",
        prefixes=("4456", "445", "44"),
        keywords=("vat", "tva", "input", "deductible", "recoverable"),
        expected_balance="debit",
    ),
    "vat_output": _RoleAdvisorSpec(
        role_code="vat_output",
        area_label="VAT and taxes",
        workflow="Sales VAT posting",
        requirement_default="recommended",
        prefixes=("4457", "445", "44"),
        keywords=("vat", "tva", "output", "collected", "payable"),
        expected_balance="credit",
    ),
    "retained_earnings": _RoleAdvisorSpec(
        role_code="retained_earnings",
        area_label="Equity and year-end",
        workflow="Year-end close",
        requirement_default="recommended",
        prefixes=("11", "12", "13"),
        keywords=("reserve", "reserves", "retained", "earnings", "brought", "forward", "income"),
        expected_balance="credit",
    ),
    "rounding_gain": _RoleAdvisorSpec(
        role_code="rounding_gain",
        area_label="Miscellaneous adjustments",
        workflow="Settlement rounding",
        requirement_default="optional",
        prefixes=("758", "778", "75", "77"),
        keywords=("rounding", "gain", "difference"),
        expected_balance="credit",
    ),
    "rounding_loss": _RoleAdvisorSpec(
        role_code="rounding_loss",
        area_label="Miscellaneous adjustments",
        workflow="Settlement rounding",
        requirement_default="optional",
        prefixes=("658", "678", "65", "67"),
        keywords=("rounding", "loss", "difference"),
        expected_balance="debit",
    ),
    "contract_revenue_default": _RoleAdvisorSpec(
        role_code="contract_revenue_default",
        area_label="Projects and contracts",
        workflow="Contract billing",
        requirement_default="optional",
        prefixes=("70", "71"),
        keywords=("contract", "project", "revenue"),
        expected_balance="credit",
    ),
    "project_cost_default": _RoleAdvisorSpec(
        role_code="project_cost_default",
        area_label="Projects and contracts",
        workflow="Project costing",
        requirement_default="optional",
        prefixes=("60", "61", "62"),
        keywords=("project", "cost", "job"),
        expected_balance="debit",
    ),
    "project_wip_asset": _RoleAdvisorSpec(
        role_code="project_wip_asset",
        area_label="Projects and contracts",
        workflow="Project WIP",
        requirement_default="optional",
        prefixes=("34", "35"),
        keywords=("project", "wip", "work in progress"),
        expected_balance="debit",
    ),
    "project_billed_not_earned": _RoleAdvisorSpec(
        role_code="project_billed_not_earned",
        area_label="Projects and contracts",
        workflow="Project revenue deferral",
        requirement_default="optional",
        prefixes=("47", "48"),
        keywords=("billed", "unearned", "not earned", "deferred"),
        expected_balance="credit",
    ),
    "project_retention_receivable": _RoleAdvisorSpec(
        role_code="project_retention_receivable",
        area_label="Projects and contracts",
        workflow="Project billing retention",
        requirement_default="optional",
        prefixes=("41",),
        keywords=("retention", "receivable"),
        expected_balance="debit",
    ),
    "project_deferred_revenue": _RoleAdvisorSpec(
        role_code="project_deferred_revenue",
        area_label="Projects and contracts",
        workflow="Project revenue deferral",
        requirement_default="optional",
        prefixes=("47", "48"),
        keywords=("deferred", "revenue"),
        expected_balance="credit",
    ),
    "project_overhead_recovery": _RoleAdvisorSpec(
        role_code="project_overhead_recovery",
        area_label="Projects and contracts",
        workflow="Project overhead recovery",
        requirement_default="optional",
        prefixes=("75",),
        keywords=("project", "overhead", "recovery"),
        expected_balance="credit",
    ),
}

_AREA_DEFINITIONS: tuple[_AreaDefinition, ...] = (
    _AreaDefinition("equity", "Equity and year-end", ("1",), ("equity", "reserve", "retained", "income")),
    _AreaDefinition("sales", "Sales and receivables", ("41", "70", "71", "72"), ("sales", "customer", "receivable", "revenue")),
    _AreaDefinition("purchases", "Purchases and payables", ("40", "60", "61", "62"), ("purchase", "supplier", "payable", "expense")),
    _AreaDefinition("tax", "VAT and taxes", ("44", "45"), ("vat", "tva", "tax")),
    _AreaDefinition("treasury", "Treasury and cash", ("5", "51", "52", "53", "57", "58"), ("bank", "cash", "till", "clearing")),
    _AreaDefinition("inventory", "Inventory", ("3",), ("inventory", "stock", "materials", "goods")),
    _AreaDefinition("payroll", "Payroll", ("42", "43", "64", "66"), ("payroll", "salary", "wage", "staff", "personnel")),
    _AreaDefinition("projects", "Projects and contracts", ("34", "35", "47", "48"), ("project", "contract", "retention", "wip")),
)

_SEVERITY_ORDER = {"blocker": 0, "warning": 1, "suggestion": 2}
_REQUIREMENT_ORDER = {"blocker": 0, "recommended": 1, "optional": 2}


class ChartCustomizationWizardDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._analysis_error: str | None = None
        self._preview_result: ChartImportPreviewDTO | None = None
        self._current_accounts: list[AccountListItemDTO] = []
        self._current_mappings: list[AccountRoleMappingDTO] = []
        self._role_options: list[AccountRoleOptionDTO] = []
        self._template_rows: list[_TemplateAccount] = self._load_template_rows()
        self._findings: list[_WizardFinding] = []
        self._role_plans: list[_RolePlan] = []
        self._structure_rows: list[_StructureRow] = []
        self._mapping_combos: dict[str, SearchableComboBox] = {}
        self._mapping_combo_keys: dict[str, set[str | None]] = {}
        self._structure_selection_rows: list[_StructureRow] = []
        self._recommended_baseline = "keep_current"
        self._baseline_user_override = False
        self._result: ChartCustomizationWizardResult | None = None

        super().__init__("Customize Chart of Accounts", parent)
        self.setObjectName("ChartCustomizationWizardDialog")
        self.resize(1180, 820)

        intro = QLabel(
            "Study the current chart, apply the safest OHADA baseline strategy, then finish the control-account and tax mapping work before posting gaps show up later.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)
        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_step_header())
        self.body_layout.addWidget(self._build_stack(), 1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)
        self._cancel_button = self.button_box.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        self._back_button = self.button_box.addButton("Back", QDialogButtonBox.ButtonRole.ActionRole)
        self._next_button = self.button_box.addButton("Next", QDialogButtonBox.ButtonRole.ActionRole)
        self._finish_button = self.button_box.addButton("Apply Setup", QDialogButtonBox.ButtonRole.AcceptRole)
        self._cancel_button.setProperty("variant", "secondary")
        self._back_button.setProperty("variant", "secondary")
        self._next_button.setProperty("variant", "secondary")
        self._finish_button.setProperty("variant", "primary")
        self._cancel_button.clicked.connect(self.reject)
        self._back_button.clicked.connect(self._go_back)
        self._next_button.clicked.connect(self._go_next)
        self._finish_button.clicked.connect(self._apply_changes)
        self._apply_license_guard(self._service_registry.license_service)

        self._current_step_index = 0
        self._load_analysis()
        self._sync_step_state()

    @property
    def result_payload(self) -> ChartCustomizationWizardResult | None:
        return self._result

    @classmethod
    def customize_chart(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> ChartCustomizationWizardResult | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result_payload
        return None

    def _build_step_header(self) -> QWidget:
        header = QWidget(self)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._step_labels: list[QLabel] = []
        for text in (
            "1. Scan",
            "2. Baseline",
            "3. Structure",
            "4. Mapping",
            "5. Readiness",
        ):
            pill = QLabel(text, header)
            pill.setObjectName("WizardStepPill")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(pill)
            self._step_labels.append(pill)
        layout.addStretch(1)
        return header

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_scan_page())
        self._stack.addWidget(self._build_baseline_page())
        self._stack.addWidget(self._build_structure_page())
        self._stack.addWidget(self._build_mapping_page())
        self._stack.addWidget(self._build_readiness_page())
        return self._stack

    def _build_scan_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        summary_card = QFrame(page)
        summary_card.setObjectName("DialogSectionCard")
        summary_card.setProperty("card", True)
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(18, 16, 18, 18)
        summary_layout.setSpacing(12)

        title = QLabel("Chart Scan", summary_card)
        title.setObjectName("DialogSectionTitle")
        summary_layout.addWidget(title)

        self._scan_recommendation_label = QLabel(summary_card)
        self._scan_recommendation_label.setObjectName("DialogSectionSummary")
        self._scan_recommendation_label.setWordWrap(True)
        summary_layout.addWidget(self._scan_recommendation_label)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._metric_labels: dict[str, QLabel] = {}
        metric_specs = (
            ("current_accounts", "Accounts in chart"),
            ("active_accounts", "Active accounts"),
            ("mapped_roles", "Mapped roles"),
            ("ohada_overlap", "OHADA overlap"),
            ("ohada_missing", "Missing OHADA rows"),
            ("blockers", "Current blockers"),
        )
        for index, (key, label_text) in enumerate(metric_specs):
            label = QLabel("0", summary_card)
            label.setObjectName("ToolbarValue")
            self._metric_labels[key] = label
            grid.addWidget(create_field_block(label_text, label), index // 3, index % 3)

        summary_layout.addLayout(grid)
        layout.addWidget(summary_card)

        findings_card = QFrame(page)
        findings_card.setObjectName("DialogSectionCard")
        findings_card.setProperty("card", True)
        findings_layout = QVBoxLayout(findings_card)
        findings_layout.setContentsMargins(18, 16, 18, 18)
        findings_layout.setSpacing(12)

        findings_title = QLabel("Advisor Findings", findings_card)
        findings_title.setObjectName("DialogSectionTitle")
        findings_layout.addWidget(findings_title)

        self._findings_table = QTableWidget(findings_card)
        self._findings_table.setColumnCount(4)
        self._findings_table.setHorizontalHeaderLabels(("Severity", "Workflow", "Finding", "Suggested Action"))
        configure_compact_table(self._findings_table)
        self._findings_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._findings_table.verticalHeader().setVisible(False)
        header = self._findings_table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.Stretch)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        findings_layout.addWidget(self._findings_table)
        layout.addWidget(findings_card, 1)
        return page

    def _build_baseline_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame(page)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(12)

        title = QLabel("Baseline Strategy", card)
        title.setObjectName("DialogSectionTitle")
        card_layout.addWidget(title)

        self._baseline_summary_label = QLabel(card)
        self._baseline_summary_label.setObjectName("DialogSectionSummary")
        self._baseline_summary_label.setWordWrap(True)
        card_layout.addWidget(self._baseline_summary_label)

        self._baseline_group = QButtonGroup(card)
        self._baseline_seed_radio = QRadioButton("Add only missing OHADA accounts to this chart", card)
        self._baseline_keep_radio = QRadioButton("Keep the current chart structure and only finish mappings", card)
        self._baseline_group.addButton(self._baseline_seed_radio)
        self._baseline_group.addButton(self._baseline_keep_radio)
        self._baseline_seed_radio.toggled.connect(lambda checked: self._handle_baseline_toggle("add_missing", checked))
        self._baseline_keep_radio.toggled.connect(lambda checked: self._handle_baseline_toggle("keep_current", checked))
        card_layout.addWidget(self._baseline_seed_radio)
        card_layout.addWidget(self._baseline_keep_radio)

        preview_grid = QGridLayout()
        preview_grid.setContentsMargins(0, 8, 0, 0)
        preview_grid.setHorizontalSpacing(12)
        preview_grid.setVerticalSpacing(12)

        self._baseline_preview_labels: dict[str, QLabel] = {}
        preview_specs = (
            ("source_rows", "Template rows"),
            ("importable", "Rows to add"),
            ("skipped", "Already covered"),
            ("conflicts", "Conflicts"),
        )
        for index, (key, label_text) in enumerate(preview_specs):
            label = QLabel("-", card)
            label.setObjectName("ValueLabel")
            self._baseline_preview_labels[key] = label
            preview_grid.addWidget(create_field_block(label_text, label), 0, index)

        card_layout.addLayout(preview_grid)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        self._open_import_button = QPushButton("Open Import Template...", actions)
        self._open_import_button.setProperty("variant", "secondary")
        self._open_import_button.clicked.connect(self._open_import_dialog)
        actions_layout.addWidget(self._open_import_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)
        card_layout.addWidget(actions)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_structure_page(self) -> QWidget:
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        left_card = QFrame(page)
        left_card.setObjectName("DialogSectionCard")
        left_card.setProperty("card", True)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(10)

        title = QLabel("Business Areas", left_card)
        title.setObjectName("DialogSectionTitle")
        left_layout.addWidget(title)

        summary = QLabel(
            "Review the chart one operating area at a time. Missing template rows show up here too when the OHADA baseline is selected.",
            left_card,
        )
        summary.setObjectName("DialogSectionSummary")
        summary.setWordWrap(True)
        left_layout.addWidget(summary)

        self._area_list = QListWidget(left_card)
        self._area_list.currentRowChanged.connect(lambda _row: self._populate_structure_table())
        left_layout.addWidget(self._area_list, 1)
        left_card.setFixedWidth(260)
        layout.addWidget(left_card)

        right_card = QFrame(page)
        right_card.setObjectName("DialogSectionCard")
        right_card.setProperty("card", True)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(18, 16, 18, 18)
        right_layout.setSpacing(12)

        self._structure_area_title = QLabel("Area review", right_card)
        self._structure_area_title.setObjectName("DialogSectionTitle")
        right_layout.addWidget(self._structure_area_title)

        self._structure_area_summary = QLabel(right_card)
        self._structure_area_summary.setObjectName("DialogSectionSummary")
        self._structure_area_summary.setWordWrap(True)
        right_layout.addWidget(self._structure_area_summary)

        self._structure_table = QTableWidget(right_card)
        self._structure_table.setColumnCount(5)
        self._structure_table.setHorizontalHeaderLabels(("Code", "Account", "Source", "Status", "Note"))
        configure_compact_table(self._structure_table)
        self._structure_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._structure_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._structure_table.itemSelectionChanged.connect(self._sync_structure_action_state)
        header = self._structure_table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.Stretch)
        right_layout.addWidget(self._structure_table, 1)

        actions = QWidget(right_card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        self._create_account_button = QPushButton("Create Account", actions)
        self._create_account_button.setProperty("variant", "secondary")
        self._create_account_button.clicked.connect(self._open_create_account)
        actions_layout.addWidget(self._create_account_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._edit_account_button = QPushButton("Edit Selected", actions)
        self._edit_account_button.setProperty("variant", "secondary")
        self._edit_account_button.clicked.connect(self._open_edit_selected_account)
        actions_layout.addWidget(self._edit_account_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._deactivate_account_button = QPushButton("Deactivate Selected", actions)
        self._deactivate_account_button.setProperty("variant", "secondary")
        self._deactivate_account_button.clicked.connect(self._deactivate_selected_account)
        actions_layout.addWidget(self._deactivate_account_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)
        right_layout.addWidget(actions)

        layout.addWidget(right_card, 1)
        return page

    def _build_mapping_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame(page)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(12)

        title = QLabel("Mapping Wizard", card)
        title.setObjectName("DialogSectionTitle")
        card_layout.addWidget(title)

        self._mapping_summary_label = QLabel(card)
        self._mapping_summary_label.setObjectName("DialogSectionSummary")
        self._mapping_summary_label.setWordWrap(True)
        card_layout.addWidget(self._mapping_summary_label)

        self._mapping_table = QTableWidget(card)
        self._mapping_table.setColumnCount(5)
        self._mapping_table.setHorizontalHeaderLabels(("Role", "Level", "Suggested", "Selected Mapping", "Advisor Note"))
        configure_compact_table(self._mapping_table)
        self._mapping_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        mapping_header = self._mapping_table.horizontalHeader()
        mapping_header.setSectionResizeMode(0, mapping_header.ResizeMode.ResizeToContents)
        mapping_header.setSectionResizeMode(1, mapping_header.ResizeMode.ResizeToContents)
        mapping_header.setSectionResizeMode(2, mapping_header.ResizeMode.Stretch)
        mapping_header.setSectionResizeMode(3, mapping_header.ResizeMode.Stretch)
        mapping_header.setSectionResizeMode(4, mapping_header.ResizeMode.Stretch)
        card_layout.addWidget(self._mapping_table, 1)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        self._apply_recommendations_button = QPushButton("Apply Recommended Selections", actions)
        self._apply_recommendations_button.setProperty("variant", "secondary")
        self._apply_recommendations_button.clicked.connect(self._apply_recommended_mappings)
        actions_layout.addWidget(self._apply_recommendations_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._refresh_mapping_button = QPushButton("Refresh Suggestions", actions)
        self._refresh_mapping_button.setProperty("variant", "ghost")
        self._refresh_mapping_button.clicked.connect(lambda: self._refresh_dynamic_views(preserve_mapping_choices=True))
        actions_layout.addWidget(self._refresh_mapping_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)
        card_layout.addWidget(actions)

        layout.addWidget(card, 1)
        return page

    def _build_readiness_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame(page)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(12)

        title = QLabel("Readiness And Commit", card)
        title.setObjectName("DialogSectionTitle")
        card_layout.addWidget(title)

        self._readiness_label = QLabel(card)
        self._readiness_label.setObjectName("DialogSectionSummary")
        self._readiness_label.setWordWrap(True)
        card_layout.addWidget(self._readiness_label)

        self._readiness_text = QPlainTextEdit(card)
        self._readiness_text.setReadOnly(True)
        self._readiness_text.setMinimumHeight(360)
        card_layout.addWidget(self._readiness_text, 1)

        layout.addWidget(card, 1)
        return page

    def _load_analysis(self) -> None:
        self._set_error(None)
        previous_area = self._selected_area_key()
        previous_mapping_choices = self._selected_mapping_keys()

        try:
            self._current_accounts = self._service_registry.chart_of_accounts_service.list_accounts(
                self._company_id,
                active_only=False,
            )
            self._current_mappings = self._service_registry.account_role_mapping_service.list_role_mappings(
                self._company_id
            )
            self._role_options = self._service_registry.account_role_mapping_service.list_role_options()
            self._preview_result = self._service_registry.chart_template_import_service.preview_import(
                self._company_id,
                ImportChartTemplateCommand(
                    source_kind="built_in",
                    template_code=BUILT_IN_TEMPLATE_CODE_OHADA,
                    add_missing_only=True,
                ),
            )
            self._analysis_error = None
        except Exception as exc:
            self._analysis_error = str(exc)
            self._preview_result = None
            self._current_accounts = []
            self._current_mappings = []
            self._role_options = self._service_registry.account_role_mapping_service.list_role_options()

        self._recommended_baseline = self._recommend_baseline_strategy()
        if not self._baseline_user_override:
            self._set_baseline_strategy(self._recommended_baseline, user_override=False)

        self._findings = self._build_findings()
        self._refresh_scan_view()
        self._refresh_baseline_view()
        self._refresh_dynamic_views(
            preserve_mapping_choices=bool(previous_mapping_choices),
            previous_mapping_choices=previous_mapping_choices,
            previous_area=previous_area,
        )

        if self._analysis_error:
            self._set_error(f"Chart analysis could not be completed cleanly.\n\n{self._analysis_error}")

    def _refresh_dynamic_views(
        self,
        *,
        preserve_mapping_choices: bool,
        previous_mapping_choices: dict[str, str | None] | None = None,
        previous_area: str | None = None,
    ) -> None:
        self._role_plans = self._build_role_plans(previous_mapping_choices if preserve_mapping_choices else None)
        self._structure_rows = self._build_structure_rows()
        self._refresh_structure_view(previous_area)
        self._refresh_mapping_view()
        self._refresh_readiness_view()
        self._sync_step_state()

    def _refresh_scan_view(self) -> None:
        active_accounts = [account for account in self._current_accounts if account.is_active]
        overlap_percent = self._ohada_overlap_percent()
        blocker_count = sum(1 for finding in self._findings if finding.severity == "blocker")

        self._scan_recommendation_label.setText(
            self._recommended_baseline_text(self._recommended_baseline)
        )
        self._metric_labels["current_accounts"].setText(str(len(self._current_accounts)))
        self._metric_labels["active_accounts"].setText(str(len(active_accounts)))
        self._metric_labels["mapped_roles"].setText(
            str(sum(1 for mapping in self._current_mappings if mapping.account_id is not None))
        )
        self._metric_labels["ohada_overlap"].setText(f"{overlap_percent}%")
        self._metric_labels["ohada_missing"].setText(str(self._preview_result.importable_count if self._preview_result else 0))
        self._metric_labels["blockers"].setText(str(blocker_count))

        self._findings_table.setRowCount(0)
        sorted_findings = sorted(
            self._findings,
            key=lambda finding: (_SEVERITY_ORDER[finding.severity], finding.workflow, finding.message),
        )
        for finding in sorted_findings:
            row_index = self._findings_table.rowCount()
            self._findings_table.insertRow(row_index)
            for column_index, value in enumerate(
                (
                    finding.severity.title(),
                    finding.workflow,
                    finding.message,
                    finding.action_label,
                )
            ):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._findings_table.setItem(row_index, column_index, item)

    def _refresh_baseline_view(self) -> None:
        baseline = self._baseline_strategy()
        baseline_label = "add missing OHADA rows" if baseline == "add_missing" else "keep the current chart only"
        self._baseline_summary_label.setText(
            f"The advisor recommends {self._recommended_baseline_text(self._recommended_baseline).lower()} "
            f"Right now the wizard is configured to {baseline_label}."
        )
        self._baseline_preview_labels["source_rows"].setText(
            str(self._preview_result.normalized_row_count if self._preview_result else 0)
        )
        self._baseline_preview_labels["importable"].setText(
            str(self._preview_result.importable_count if self._preview_result else 0)
        )
        self._baseline_preview_labels["skipped"].setText(
            str(self._preview_result.skipped_existing_count if self._preview_result else 0)
        )
        self._baseline_preview_labels["conflicts"].setText(
            str(self._preview_result.conflict_count if self._preview_result else 0)
        )

    def _refresh_structure_view(self, previous_area: str | None) -> None:
        counts_by_area: dict[str, int] = {}
        for row in self._structure_rows:
            counts_by_area[row.area_key] = counts_by_area.get(row.area_key, 0) + 1

        self._area_list.blockSignals(True)
        self._area_list.clear()
        selected_row = 0
        for index, area in enumerate(_AREA_DEFINITIONS):
            count = counts_by_area.get(area.key, 0)
            item = QListWidgetItem(f"{area.label} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, area.key)
            self._area_list.addItem(item)
            if previous_area == area.key:
                selected_row = index
        if self._area_list.count():
            self._area_list.setCurrentRow(selected_row)
        self._area_list.blockSignals(False)
        self._populate_structure_table()

    def _refresh_mapping_view(self) -> None:
        self._mapping_summary_label.setText(
            "Recommended accounts float to the top. If OHADA add-missing is selected, template-only candidates show up as [Will add] so you can map them before the import runs."
        )
        self._mapping_table.setRowCount(0)
        self._mapping_combos.clear()
        self._mapping_combo_keys.clear()

        plans = sorted(
            self._role_plans,
            key=lambda plan: (_REQUIREMENT_ORDER[plan.requirement], plan.role_label),
        )
        for plan in plans:
            row_index = self._mapping_table.rowCount()
            self._mapping_table.insertRow(row_index)

            combo = SearchableComboBox(self._mapping_table)
            items = []
            search_texts = []
            seen_keys: set[str | None] = {None}
            for candidate in plan.candidates:
                if candidate.key in seen_keys:
                    continue
                seen_keys.add(candidate.key)
                prefix = "[Will add] " if candidate.source == "template" else ""
                items.append((f"{prefix}{candidate.account_code}  {candidate.account_name}", candidate.key))
                search_texts.append(
                    f"{candidate.account_code} {candidate.account_name} {candidate.reason} {plan.role_label}"
                )
            combo.set_items(items, placeholder="Leave unmapped", search_texts=search_texts)
            combo.set_current_value(plan.selected_key)
            combo.value_changed.connect(lambda _value, role_code=plan.role_code: self._handle_mapping_changed(role_code))
            self._mapping_combos[plan.role_code] = combo
            self._mapping_combo_keys[plan.role_code] = seen_keys

            recommendation = self._candidate_by_key(plan.candidates, plan.suggested_key)
            recommendation_text = (
                f"{recommendation.account_code}  {recommendation.account_name}"
                if recommendation is not None
                else "No strong candidate yet"
            )
            advisor_note = recommendation.reason if recommendation is not None else plan.explanation

            role_item = QTableWidgetItem(plan.role_label)
            level_item = QTableWidgetItem(plan.requirement.title())
            level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            suggested_item = QTableWidgetItem(recommendation_text)
            note_item = QTableWidgetItem(advisor_note)
            self._mapping_table.setItem(row_index, 0, role_item)
            self._mapping_table.setItem(row_index, 1, level_item)
            self._mapping_table.setItem(row_index, 2, suggested_item)
            self._mapping_table.setCellWidget(row_index, 3, combo)
            self._mapping_table.setItem(row_index, 4, note_item)

    def _refresh_readiness_view(self) -> None:
        baseline_will_apply = self._baseline_strategy() == "add_missing" and self._preview_result is not None and self._preview_result.importable_count > 0
        mapping_changes = self._calculate_mapping_changes()
        blockers = self._collect_readiness_blockers()
        self._readiness_label.setText(
            "The wizard only enables Apply when the remaining blockers are either solved or explicitly out of scope for the selected setup path."
        )

        lines = ["Planned actions:"]
        if baseline_will_apply:
            lines.append(f"- Add {self._preview_result.importable_count} missing OHADA rows.")
        else:
            lines.append("- No OHADA baseline rows will be added.")

        if mapping_changes["set"] or mapping_changes["clear"]:
            lines.append(f"- Set {mapping_changes['set']} role mappings.")
            if mapping_changes["clear"]:
                lines.append(f"- Clear {mapping_changes['clear']} role mappings.")
        else:
            lines.append("- No role-mapping changes are queued.")

        lines.append("")
        if blockers:
            lines.append("Remaining blockers:")
            lines.extend(f"- {blocker}" for blocker in blockers)
        else:
            lines.append("Remaining blockers:")
            lines.append("- None. The chart is ready for this setup pass.")

        self._readiness_text.setPlainText("\n".join(lines))
        write_permitted = True
        try:
            write_permitted = bool(self._service_registry.license_service.is_write_permitted())
        except Exception:
            write_permitted = True
        self._finish_button.setEnabled(not blockers and write_permitted)

    def _handle_baseline_toggle(self, strategy: str, checked: bool) -> None:
        if not checked:
            return
        self._baseline_user_override = True
        previous_area = self._selected_area_key()
        previous_mapping_choices = self._selected_mapping_keys()
        self._set_baseline_strategy(strategy, user_override=True)
        self._refresh_baseline_view()
        self._refresh_dynamic_views(
            preserve_mapping_choices=True,
            previous_mapping_choices=previous_mapping_choices,
            previous_area=previous_area,
        )

    def _handle_mapping_changed(self, _role_code: str) -> None:
        self._refresh_readiness_view()

    def _apply_recommended_mappings(self) -> None:
        for plan in self._role_plans:
            combo = self._mapping_combos.get(plan.role_code)
            if combo is None:
                continue
            combo.set_current_value(plan.suggested_key)
        self._refresh_readiness_view()

    def _go_back(self) -> None:
        if self._current_step_index <= 0:
            return
        self._current_step_index -= 1
        self._sync_step_state()

    def _go_next(self) -> None:
        if self._current_step_index >= self._stack.count() - 1:
            return
        self._current_step_index += 1
        self._sync_step_state()

    def _sync_step_state(self) -> None:
        self._stack.setCurrentIndex(self._current_step_index)
        for index, label in enumerate(self._step_labels):
            label.setProperty("current", index == self._current_step_index)
            label.setProperty("completed", index < self._current_step_index)
            label.style().unpolish(label)
            label.style().polish(label)

        self._back_button.setVisible(self._current_step_index > 0)
        self._next_button.setVisible(self._current_step_index < self._stack.count() - 1)
        self._finish_button.setVisible(self._current_step_index == self._stack.count() - 1)

    def _open_import_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("chart.import"):
            self._set_error("You do not have permission to import chart templates.")
            return
        result = ChartImportDialog.import_chart_template(
            self._service_registry,
            company_id=self._company_id,
            company_name=self._company_name,
            parent=self,
        )
        if result is None:
            return
        show_info(self, "Chart Import", self._format_import_result(result))
        self._baseline_user_override = False
        self._load_analysis()

    def _open_create_account(self) -> None:
        if not self._service_registry.permission_service.has_permission("chart.accounts.create"):
            self._set_error("You do not have permission to create accounts from the wizard.")
            return
        account = AccountFormDialog.create_account(
            self._service_registry,
            company_id=self._company_id,
            company_name=self._company_name,
            parent=self,
        )
        if account is not None:
            self._load_analysis()

    def _open_edit_selected_account(self) -> None:
        selected = self._selected_structure_row()
        if selected is None or selected.account_id is None:
            show_info(self, "Customize Chart", "Select an existing account row to edit.")
            return
        if not self._service_registry.permission_service.has_permission("chart.accounts.edit"):
            self._set_error("You do not have permission to edit accounts from the wizard.")
            return
        account = AccountFormDialog.edit_account(
            self._service_registry,
            company_id=self._company_id,
            company_name=self._company_name,
            account_id=selected.account_id,
            parent=self,
        )
        if account is not None:
            self._load_analysis()

    def _deactivate_selected_account(self) -> None:
        selected = self._selected_structure_row()
        if selected is None or selected.account_id is None:
            show_info(self, "Customize Chart", "Select an existing account row to deactivate.")
            return
        if not self._service_registry.permission_service.has_permission("chart.accounts.deactivate"):
            self._set_error("You do not have permission to deactivate accounts from the wizard.")
            return

        current_account = next((account for account in self._current_accounts if account.id == selected.account_id), None)
        if current_account is None:
            show_info(self, "Customize Chart", "The selected account could not be resolved.")
            return
        if not current_account.is_active:
            show_info(self, "Customize Chart", "The selected account is already inactive.")
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Account",
            f"Deactivate account '{current_account.account_name}' ({current_account.account_code})?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.chart_of_accounts_service.deactivate_account(
                self._company_id,
                current_account.id,
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Customize Chart", str(exc))
            return

        self._load_analysis()

    def _apply_changes(self) -> None:
        blockers = self._collect_readiness_blockers()
        if blockers:
            self._set_error("Resolve the remaining blockers before applying the wizard plan.")
            return

        try:
            check_write_or_raise(self._service_registry.license_service)
        except Exception as exc:
            show_error(self, "Customize Chart", str(exc))
            return

        baseline_applied = False
        imported_count = 0
        mappings_updated = 0
        mappings_cleared = 0

        if self._baseline_strategy() == "add_missing" and self._preview_result is not None and self._preview_result.importable_count > 0:
            if not self._service_registry.permission_service.has_permission("chart.seed"):
                self._set_error("You do not have permission to seed the OHADA chart baseline.")
                return
            try:
                seed_result = self._service_registry.chart_seed_service.seed_built_in_chart(self._company_id)
            except (ValidationError, ConflictError, NotFoundError) as exc:
                show_error(self, "Customize Chart", str(exc))
                return
            baseline_applied = True
            imported_count = seed_result.imported_count

        pending_changes = self._collect_mapping_commands()
        if pending_changes and not self._service_registry.permission_service.has_any_permission(
            ("reference.account_role_mappings.manage", "chart.role_mappings.manage")
        ):
            self._set_error("You do not have permission to save account role mappings.")
            return

        if baseline_applied or pending_changes:
            self._load_analysis()

        for role_code, target_key in pending_changes.items():
            current_mapping = next((mapping for mapping in self._current_mappings if mapping.role_code == role_code), None)
            resolved_account_id = self._resolve_mapping_target_account_id(target_key)

            try:
                if resolved_account_id is None:
                    if current_mapping is not None and current_mapping.account_id is not None:
                        self._service_registry.account_role_mapping_service.clear_role_mapping(self._company_id, role_code)
                        mappings_cleared += 1
                else:
                    self._service_registry.account_role_mapping_service.set_role_mapping(
                        self._company_id,
                        SetAccountRoleMappingCommand(role_code=role_code, account_id=resolved_account_id),
                    )
                    mappings_updated += 1
            except (ValidationError, ConflictError, NotFoundError) as exc:
                show_error(self, "Customize Chart", str(exc))
                return

        self._load_analysis()

        lines = []
        if baseline_applied:
            lines.append(f"Added {imported_count} missing OHADA rows.")
        else:
            lines.append("No OHADA rows were added.")
        if mappings_updated:
            lines.append(f"Updated {mappings_updated} role mappings.")
        if mappings_cleared:
            lines.append(f"Cleared {mappings_cleared} role mappings.")
        if not mappings_updated and not mappings_cleared:
            lines.append("No role-mapping changes were required.")

        self._result = ChartCustomizationWizardResult(
            baseline_applied=baseline_applied,
            imported_count=imported_count,
            mappings_updated=mappings_updated,
            mappings_cleared=mappings_cleared,
            summary="\n".join(lines),
        )
        self.accept()

    def _populate_structure_table(self) -> None:
        area_key = self._selected_area_key()
        self._structure_selection_rows = []
        self._structure_table.setRowCount(0)
        if area_key is None:
            self._sync_structure_action_state()
            return

        area = next((item for item in _AREA_DEFINITIONS if item.key == area_key), None)
        if area is None:
            self._sync_structure_action_state()
            return

        rows = [row for row in self._structure_rows if row.area_key == area_key]
        rows.sort(key=lambda row: (row.account_code, row.account_name, row.source_label))
        self._structure_area_title.setText(area.label)
        self._structure_area_summary.setText(
            "Use the wizard for targeted review, then drop into the full account dialog only when a direct edit is needed."
        )

        for row in rows:
            row_index = self._structure_table.rowCount()
            self._structure_table.insertRow(row_index)
            values = (row.account_code, row.account_name, row.source_label, row.status_label, row.note)
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row_index)
                self._structure_table.setItem(row_index, column_index, item)
            self._structure_selection_rows.append(row)

        if self._structure_table.rowCount():
            self._structure_table.selectRow(0)
        self._sync_structure_action_state()

    def _sync_structure_action_state(self) -> None:
        selected = self._selected_structure_row()
        has_current_account = selected is not None and selected.account_id is not None
        self._edit_account_button.setEnabled(has_current_account)
        self._deactivate_account_button.setEnabled(has_current_account)

    def _selected_structure_row(self) -> _StructureRow | None:
        row_index = self._structure_table.currentRow()
        if row_index < 0 or row_index >= len(self._structure_selection_rows):
            return None
        return self._structure_selection_rows[row_index]

    def _selected_area_key(self) -> str | None:
        item = self._area_list.currentItem() if hasattr(self, "_area_list") else None
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return value if isinstance(value, str) else None

    def _selected_mapping_keys(self) -> dict[str, str | None]:
        return {
            role_code: combo.current_value()
            for role_code, combo in self._mapping_combos.items()
        }

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def _baseline_strategy(self) -> str:
        return "add_missing" if self._baseline_seed_radio.isChecked() else "keep_current"

    def _set_baseline_strategy(self, strategy: str, *, user_override: bool) -> None:
        self._baseline_user_override = user_override
        self._baseline_seed_radio.blockSignals(True)
        self._baseline_keep_radio.blockSignals(True)
        self._baseline_seed_radio.setChecked(strategy == "add_missing")
        self._baseline_keep_radio.setChecked(strategy != "add_missing")
        self._baseline_seed_radio.blockSignals(False)
        self._baseline_keep_radio.blockSignals(False)

    def _recommend_baseline_strategy(self) -> str:
        active_accounts = [account for account in self._current_accounts if account.is_active]
        if not active_accounts:
            return "add_missing"
        if self._preview_result is None:
            return "keep_current"
        if self._preview_result.importable_count >= 20:
            return "add_missing"
        if self._ohada_overlap_percent() < 60:
            return "add_missing"
        blocker_roles = self._missing_blocker_roles_current_state()
        if blocker_roles and self._preview_result.importable_count > 0:
            return "add_missing"
        return "keep_current"

    def _recommended_baseline_text(self, strategy: str) -> str:
        if strategy == "add_missing":
            return "adding the missing OHADA baseline first"
        return "keeping the current chart and focusing on mappings"

    def _ohada_overlap_percent(self) -> int:
        if self._preview_result is None or self._preview_result.normalized_row_count == 0:
            return 0
        return int(round((self._preview_result.skipped_existing_count / self._preview_result.normalized_row_count) * 100))

    def _build_findings(self) -> list[_WizardFinding]:
        findings: list[_WizardFinding] = []
        active_accounts = [account for account in self._current_accounts if account.is_active]
        if not active_accounts:
            findings.append(
                _WizardFinding(
                    severity="blocker",
                    workflow="Chart setup",
                    message="The company has no active chart accounts yet.",
                    action_label="Add OHADA baseline",
                )
            )

        if self._preview_result is not None and self._preview_result.importable_count > 0:
            findings.append(
                _WizardFinding(
                    severity="suggestion" if active_accounts else "warning",
                    workflow="Chart coverage",
                    message=f"{self._preview_result.importable_count} OHADA rows are still missing from the company chart.",
                    action_label="Review baseline step",
                )
            )

        for role_code in self._missing_blocker_roles_current_state():
            spec = _ROLE_SPECS.get(role_code)
            if spec is None:
                continue
            findings.append(
                _WizardFinding(
                    severity="blocker",
                    workflow=spec.workflow,
                    message=f"{spec.area_label}: {self._role_label(role_code)} is not mapped yet.",
                    action_label="Fix in mapping step",
                )
            )

        duplicate_names = self._duplicate_name_groups()
        if duplicate_names:
            findings.append(
                _WizardFinding(
                    severity="warning",
                    workflow="Chart hygiene",
                    message=f"{len(duplicate_names)} account name group(s) look duplicated and may confuse mapping later.",
                    action_label="Review structure step",
                )
            )

        if not findings:
            findings.append(
                _WizardFinding(
                    severity="suggestion",
                    workflow="Readiness",
                    message="The chart foundation already looks stable. The wizard can mostly confirm mappings and guardrails.",
                    action_label="Review readiness",
                )
            )
        return findings

    def _build_structure_rows(self) -> list[_StructureRow]:
        rows: list[_StructureRow] = []
        current_codes = {account.account_code for account in self._current_accounts}

        for account in self._current_accounts:
            rows.append(
                _StructureRow(
                    area_key=self._classify_area(account.account_code, account.account_name),
                    account_code=account.account_code,
                    account_name=account.account_name,
                    source_label="Current",
                    status_label="Active" if account.is_active else "Inactive",
                    note="Posted history may exist. Deactivate rather than delete when replacing structure.",
                    account_id=account.id,
                )
            )

        if self._baseline_strategy() == "add_missing":
            for template in self._template_rows:
                if template.account_code in current_codes:
                    continue
                rows.append(
                    _StructureRow(
                        area_key=self._classify_area(template.account_code, template.account_name),
                        account_code=template.account_code,
                        account_name=template.account_name,
                        source_label="OHADA",
                        status_label="Will add",
                        note="Recommended baseline row that will be inserted on Apply.",
                        account_id=None,
                    )
                )
        return rows

    def _build_role_plans(self, previous_mapping_choices: dict[str, str | None] | None) -> list[_RolePlan]:
        plans: list[_RolePlan] = []
        current_accounts_by_id = {account.id: account for account in self._current_accounts}
        active_signals = [self._account_to_signal(account) for account in self._current_accounts if account.is_active]
        template_signals = [self._template_to_signal(row) for row in self._template_rows if self._template_row_available(row)]
        current_mappings_by_role = {mapping.role_code: mapping for mapping in self._current_mappings}

        for option in self._role_options:
            spec = _ROLE_SPECS.get(
                option.role_code,
                _RoleAdvisorSpec(
                    role_code=option.role_code,
                    area_label="General",
                    workflow="Posting",
                    requirement_default="optional",
                    prefixes=(),
                    keywords=tuple(token for token in option.label.lower().replace("/", " ").split() if len(token) > 2),
                ),
            )
            requirement = self._resolve_requirement(spec.role_code)
            mapping = current_mappings_by_role.get(option.role_code)

            candidates: list[_RoleCandidate] = []
            if mapping is not None and mapping.account_id is not None:
                mapped_account = current_accounts_by_id.get(mapping.account_id)
                if mapped_account is not None:
                    candidates.append(
                        self._candidate_from_signal(
                            self._account_to_signal(mapped_account),
                            spec,
                            mapped=True,
                        )
                    )

            for signal in active_signals:
                candidates.append(self._candidate_from_signal(signal, spec))
            for signal in template_signals:
                candidates.append(self._candidate_from_signal(signal, spec))

            unique_candidates: dict[str, _RoleCandidate] = {}
            for candidate in candidates:
                existing = unique_candidates.get(candidate.key)
                if existing is None or candidate.score > existing.score:
                    unique_candidates[candidate.key] = candidate

            ordered_candidates = tuple(
                sorted(
                    unique_candidates.values(),
                    key=lambda candidate: (-candidate.score, candidate.account_code, candidate.account_name),
                )
            )

            current_key = None
            if mapping is not None and mapping.account_id is not None:
                current_key = f"a:{mapping.account_id}"
            suggested_key = ordered_candidates[0].key if ordered_candidates and ordered_candidates[0].score > 0 else None
            selected_key = suggested_key
            if previous_mapping_choices and option.role_code in previous_mapping_choices:
                candidate_key = previous_mapping_choices[option.role_code]
                if candidate_key is None or candidate_key in unique_candidates:
                    selected_key = candidate_key
            elif current_key is not None:
                selected_key = current_key

            plans.append(
                _RolePlan(
                    role_code=option.role_code,
                    role_label=option.label,
                    requirement=requirement,
                    workflow=spec.workflow,
                    explanation=spec.area_label,
                    current_mapping_account_id=mapping.account_id if mapping is not None else None,
                    current_mapping_key=current_key,
                    suggested_key=suggested_key,
                    selected_key=selected_key,
                    candidates=ordered_candidates,
                )
            )
        return plans

    def _candidate_from_signal(self, signal: _AccountSignal, spec: _RoleAdvisorSpec, *, mapped: bool = False) -> _RoleCandidate:
        text = f"{signal.account_code} {signal.account_name}".lower()
        score = 0
        reasons: list[str] = []

        if mapped:
            score += 200
            reasons.append("currently mapped")

        for preferred_code in spec.preferred_codes:
            if signal.account_code == preferred_code:
                score += 60
                reasons.append(f"exact code {preferred_code}")

        longest_prefix = 0
        for prefix in spec.prefixes:
            if signal.account_code.startswith(prefix):
                longest_prefix = max(longest_prefix, len(prefix))
        if longest_prefix:
            score += 24 + longest_prefix * 2
            reasons.append(f"matches OHADA prefix {signal.account_code[:longest_prefix]}")

        keyword_hits = [keyword for keyword in spec.keywords if keyword in text]
        if keyword_hits:
            score += min(36, len(keyword_hits) * 8)
            reasons.append(f"keyword match: {', '.join(keyword_hits[:2])}")

        if spec.expected_balance and signal.normal_balance.lower() == spec.expected_balance:
            score += 10
            reasons.append(f"{spec.expected_balance} balance")
        if spec.prefer_control and signal.is_control_account:
            score += 14
            reasons.append("control account")
        if spec.prefer_postable and signal.allow_manual_posting:
            score += 10
            reasons.append("postable leaf")
        elif spec.prefer_postable and not signal.allow_manual_posting:
            score -= 8

        if not signal.is_active:
            score -= 80
            reasons.append("inactive")
        if signal.source == "template":
            score -= 2

        if not reasons:
            reasons.append("manual override candidate")

        if signal.source == "template":
            reasons.append("available after OHADA add-missing")

        key = f"a:{signal.account_id}" if signal.account_id is not None else f"t:{signal.account_code}"
        return _RoleCandidate(
            key=key,
            account_id=signal.account_id,
            account_code=signal.account_code,
            account_name=signal.account_name,
            source=signal.source,
            is_active=signal.is_active,
            allow_manual_posting=signal.allow_manual_posting,
            is_control_account=signal.is_control_account,
            score=score,
            reason=", ".join(reasons),
        )

    def _collect_readiness_blockers(self) -> list[str]:
        blockers: list[str] = []
        baseline_selected = self._baseline_strategy() == "add_missing"
        if baseline_selected and not self._service_registry.permission_service.has_permission("chart.seed"):
            blockers.append("The selected baseline path needs the 'chart.seed' permission.")

        mapping_manage_allowed = self._service_registry.permission_service.has_any_permission(
            ("reference.account_role_mappings.manage", "chart.role_mappings.manage")
        )
        if self._collect_mapping_commands() and not mapping_manage_allowed:
            blockers.append("Saving role mappings from the wizard requires role-mapping management permission.")

        for plan in self._role_plans:
            selected_key = self._selected_mapping_key(plan.role_code)
            if plan.requirement != "blocker":
                continue
            if selected_key is None:
                blockers.append(f"{plan.role_label} is still unmapped.")
                continue
            if selected_key.startswith("t:") and not baseline_selected:
                blockers.append(f"{plan.role_label} points to a template-only account but OHADA add-missing is not selected.")
                continue
            selected_candidate = self._candidate_by_key(plan.candidates, selected_key)
            if selected_candidate is None:
                blockers.append(f"{plan.role_label} selection could not be resolved.")
                continue
            if not selected_candidate.is_active:
                blockers.append(f"{plan.role_label} points to an inactive account.")
                continue
            spec = _ROLE_SPECS.get(plan.role_code)
            if spec is not None and spec.prefer_postable and not selected_candidate.allow_manual_posting:
                blockers.append(f"{plan.role_label} should point to a postable leaf account.")

        return blockers

    def _calculate_mapping_changes(self) -> dict[str, int]:
        changes = {"set": 0, "clear": 0}
        for plan in self._role_plans:
            selected_key = self._selected_mapping_key(plan.role_code)
            if selected_key == plan.current_mapping_key:
                continue
            if selected_key is None:
                if plan.current_mapping_key is not None:
                    changes["clear"] += 1
            else:
                changes["set"] += 1
        return changes

    def _collect_mapping_commands(self) -> dict[str, str | None]:
        commands: dict[str, str | None] = {}
        for plan in self._role_plans:
            selected_key = self._selected_mapping_key(plan.role_code)
            if selected_key != plan.current_mapping_key:
                commands[plan.role_code] = selected_key
        return commands

    def _resolve_mapping_target_account_id(self, target_key: str | None) -> int | None:
        if target_key is None:
            return None
        if target_key.startswith("a:"):
            return int(target_key.split(":", 1)[1])
        if target_key.startswith("t:"):
            target_code = target_key.split(":", 1)[1]
            match = next((account for account in self._current_accounts if account.account_code == target_code and account.is_active), None)
            if match is None:
                raise ValidationError(
                    f"Template account {target_code} could not be resolved after the OHADA add-missing step."
                )
            return match.id
        raise ValidationError("Unknown mapping target.")

    def _selected_mapping_key(self, role_code: str) -> str | None:
        combo = self._mapping_combos.get(role_code)
        if combo is None:
            return next((plan.selected_key for plan in self._role_plans if plan.role_code == role_code), None)
        value = combo.current_value()
        return value if value is None or isinstance(value, str) else None

    def _candidate_by_key(
        self,
        candidates: tuple[_RoleCandidate, ...],
        key: str | None,
    ) -> _RoleCandidate | None:
        if key is None:
            return None
        return next((candidate for candidate in candidates if candidate.key == key), None)

    def _resolve_requirement(self, role_code: str) -> str:
        spec = _ROLE_SPECS.get(role_code)
        if spec is None:
            return "optional"
        signals = {
            "sales": self._has_signal(("41", "70", "71", "72"), ("sales", "customer", "receivable", "revenue")),
            "purchases": self._has_signal(("40", "60", "61", "62"), ("purchase", "supplier", "payable", "expense")),
            "tax": self._has_signal(("44", "45"), ("vat", "tva", "tax")),
            "treasury": self._has_signal(("5", "51", "52", "57", "58"), ("bank", "cash", "treasury")),
            "inventory": self._has_signal(("3",), ("inventory", "stock")),
            "payroll": self._has_signal(("42", "43", "64", "66"), ("payroll", "salary", "wage")),
            "projects": self._has_signal(("34", "35", "47", "48"), ("project", "contract", "retention", "wip")),
        }

        if role_code in {"ar_control", "sales_revenue_default"}:
            return "blocker" if signals["sales"] else "recommended"
        if role_code in {"ap_control", "purchases_expense_default"}:
            return "blocker" if signals["purchases"] else "recommended"
        if role_code in {"vat_input", "vat_output"}:
            return "blocker" if signals["tax"] else "recommended"
        if role_code == "bank_main":
            return "blocker" if signals["treasury"] else "recommended"
        if role_code in {"cash_on_hand", "bank_clearing", "inventory_control", "payroll_payable", "retained_earnings"}:
            if role_code == "inventory_control":
                return "blocker" if signals["inventory"] else "recommended"
            if role_code == "payroll_payable":
                return "blocker" if signals["payroll"] else "recommended"
            if role_code == "retained_earnings":
                return "blocker" if self._current_accounts else "recommended"
            return "recommended"
        if role_code.startswith("project_") or role_code == "contract_revenue_default":
            return "recommended" if signals["projects"] else "optional"
        return spec.requirement_default

    def _has_signal(self, prefixes: tuple[str, ...], keywords: tuple[str, ...]) -> bool:
        for account in self._current_accounts:
            text = f"{account.account_code} {account.account_name}".lower()
            if any(account.account_code.startswith(prefix) for prefix in prefixes):
                return True
            if any(keyword in text for keyword in keywords):
                return True
        return False

    def _missing_blocker_roles_current_state(self) -> list[str]:
        current_mappings = {mapping.role_code: mapping for mapping in self._current_mappings}
        missing_roles: list[str] = []
        for role_code, spec in _ROLE_SPECS.items():
            if self._resolve_requirement(role_code) != "blocker":
                continue
            mapping = current_mappings.get(role_code)
            if mapping is None or mapping.account_id is None:
                missing_roles.append(role_code)
                continue
            account = next((row for row in self._current_accounts if row.id == mapping.account_id), None)
            if account is None or not account.is_active:
                missing_roles.append(role_code)
                continue
            if spec.prefer_postable and not account.allow_manual_posting:
                missing_roles.append(role_code)
        return missing_roles

    def _duplicate_name_groups(self) -> list[list[AccountListItemDTO]]:
        groups: dict[str, list[AccountListItemDTO]] = {}
        for account in self._current_accounts:
            normalized = "".join(character for character in account.account_name.lower() if character.isalnum())
            groups.setdefault(normalized, []).append(account)
        return [group for group in groups.values() if len(group) > 1]

    def _classify_area(self, account_code: str, account_name: str) -> str:
        text = f"{account_code} {account_name}".lower()
        for area in _AREA_DEFINITIONS:
            if any(account_code.startswith(prefix) for prefix in area.prefixes):
                return area.key
            if any(keyword in text for keyword in area.keywords):
                return area.key
        if any(token in text for token in ("project", "contract", "retention", "wip")):
            return "projects"
        if account_code.startswith("5"):
            return "treasury"
        if account_code.startswith("7"):
            return "sales"
        if account_code.startswith("6"):
            return "purchases"
        if account_code.startswith("3"):
            return "inventory"
        return "equity"

    def _account_to_signal(self, account: AccountListItemDTO) -> _AccountSignal:
        return _AccountSignal(
            account_id=account.id,
            account_code=account.account_code,
            account_name=account.account_name,
            account_class_code=account.account_class_code,
            account_type_code=account.account_type_code,
            normal_balance=account.normal_balance.lower(),
            allow_manual_posting=account.allow_manual_posting,
            is_control_account=account.is_control_account,
            is_active=account.is_active,
            source="current",
        )

    def _template_to_signal(self, row: _TemplateAccount) -> _AccountSignal:
        return _AccountSignal(
            account_id=None,
            account_code=row.account_code,
            account_name=row.account_name,
            account_class_code=row.account_class_code,
            account_type_code=row.account_type_code,
            normal_balance=row.normal_balance.lower(),
            allow_manual_posting=row.allow_manual_posting,
            is_control_account=row.is_control_account,
            is_active=True,
            source="template",
        )

    def _template_row_available(self, row: _TemplateAccount) -> bool:
        if self._baseline_strategy() != "add_missing":
            return False
        return not any(account.account_code == row.account_code for account in self._current_accounts)

    def _load_template_rows(self) -> list[_TemplateAccount]:
        template_path = Path(__file__).resolve().parents[4] / "resources" / "chart_templates" / f"{BUILT_IN_TEMPLATE_CODE_OHADA}.csv"
        rows: list[_TemplateAccount] = []
        if not template_path.exists():
            return rows

        with template_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw_row in reader:
                rows.append(
                    _TemplateAccount(
                        account_code=(raw_row.get("account_code") or "").strip(),
                        account_name=(raw_row.get("account_name") or "").strip(),
                        parent_account_code=(raw_row.get("parent_account_code") or "").strip() or None,
                        account_class_code=(raw_row.get("class_code") or "").strip(),
                        account_type_code=(raw_row.get("account_type_code") or "").strip(),
                        normal_balance=(raw_row.get("normal_balance") or "").strip(),
                        allow_manual_posting=str(raw_row.get("allow_manual_posting") or "").strip().lower() == "true",
                        is_control_account=str(raw_row.get("is_control_account_default") or "").strip().lower() == "true",
                    )
                )
        return rows

    def _role_label(self, role_code: str) -> str:
        option = next((role for role in self._role_options if role.role_code == role_code), None)
        return option.label if option is not None else role_code.replace("_", " ").title()

    def _format_import_result(self, result: ChartImportResultDTO) -> str:
        lines = [
            f"Imported: {result.imported_count}",
            f"Skipped existing: {result.skipped_existing_count}",
            f"Conflicts: {result.conflict_count}",
        ]
        if result.warnings:
            lines.append("")
            lines.extend(f"- {warning}" for warning in result.warnings)
        return "\n".join(lines)
