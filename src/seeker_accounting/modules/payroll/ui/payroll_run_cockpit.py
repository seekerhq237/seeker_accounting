"""Payroll Run Cockpit (Phase 3 / P3.S1+P3.S4, Phase 6 / P6.S1–P6.S4).

Single-page replacement for the legacy 7-step ``PayrollRunWizardDialog``.
The cockpit shows one payroll run end-to-end:

* timeline   — horizontal state-machine strip (P6.S1)
* header     — period, currency, status chip, primary action
* employee   — sortable / filterable / expandable employee grid (P3.S4)
* right rail — Summary / Inputs / Variance / Issues / Posting / Payments /
               Remit / Audit tabs (Posting live P6.S2; Payments P6.S3;
               Remit P6.S4; Issues/Audit arrive with P14)

Architecture: UI surface only. Every state-changing action goes through
:class:`PayrollRunService`. The local :class:`PayrollRunStateMachine` is
consulted to derive button gating and the primary-action label.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from datetime import date as _date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    PayrollRunDetailDTO,
    PayrollRunEmployeeDetailDTO,
    PayrollRunEmployeeListItemDTO,
)
from seeker_accounting.modules.payroll.services.payroll_exclusion_reasons import (
    reason_label,
)
from seeker_accounting.modules.payroll.services.payroll_run_state import (
    PayrollRunStateMachine,
    PayrollRunStatus,
)
from seeker_accounting.modules.payroll.ui.payroll_run_timeline import RunTimelineWidget
from seeker_accounting.platform.exceptions import AppError
from seeker_accounting.shared.ui.components.status_chip import StatusChip
from seeker_accounting.shared.ui.components.workbench_primitives import (
    EmptyState,
    KpiTile,
    KpiTileData,
    WorkbenchHeader,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.background_task import run_with_progress
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS
from seeker_accounting.shared.ui.styles.palette import LIGHT_PALETTE as _P

if TYPE_CHECKING:
    from seeker_accounting.modules.payroll.services.payroll_dry_run import PayrollDryRunEstimate

# Rail tab indices (kept in one place to avoid brittle magic numbers).
_TAB_SUMMARY = 0
_TAB_INPUTS = 1
_TAB_VARIANCE = 2
_TAB_ISSUES = 3
_TAB_POSTING = 4
_TAB_PAYMENTS = 5
_TAB_REMIT = 6
_TAB_AUDIT = 7

_log = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

_MONTHS: Final[dict[int, str]] = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

_EMP_STATUS_LABELS: Final[dict[str, str]] = {
    "included": "Included",
    "excluded": "Excluded",
    "error": "Error",
}

_FILTER_ALL: Final[str] = "__all__"

# Tree columns for the employee grid.
_COL_EMPLOYEE = 0
_COL_GROSS = 1
_COL_EARNINGS = 2
_COL_DEDUCTIONS = 3
_COL_STATUTORY = 4
_COL_NET = 5
_COL_EMPLOYER = 6
_COL_STATUS = 7
_COL_COUNT = 8

_NUMERIC_COLS: Final[tuple[int, ...]] = (
    _COL_GROSS, _COL_EARNINGS, _COL_DEDUCTIONS,
    _COL_STATUTORY, _COL_NET, _COL_EMPLOYER,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _fmt_money(value: Decimal | float | int | None) -> str:
    if value is None:
        return ""
    try:
        return f"{Decimal(value):,.2f}"
    except Exception:  # noqa: BLE001
        return str(value)


def _emp_status_label(code: str | None) -> str:
    if not code:
        return ""
    return _EMP_STATUS_LABELS.get(code, code.replace("_", " ").title())


# ── Numeric tree item with proper sorting ───────────────────────────────────

class _NumericTreeItem(QTreeWidgetItem):
    """QTreeWidgetItem that sorts numeric columns by stored Decimal."""

    def __lt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, QTreeWidgetItem):
            return NotImplemented
        col = 0
        tw = self.treeWidget()
        if tw is not None:
            col = tw.sortColumn()
        if col in _NUMERIC_COLS:
            try:
                a = Decimal(self.data(col, Qt.ItemDataRole.UserRole + 1) or 0)
                b = Decimal(other.data(col, Qt.ItemDataRole.UserRole + 1) or 0)
                return a < b
            except Exception:  # noqa: BLE001
                pass
        return self.text(col) < other.text(col)


# ── Cockpit widget ──────────────────────────────────────────────────────────

class PayrollRunCockpit(QWidget):
    """Single-page run cockpit for one :class:`PayrollRun`.

    Replaces the seven-step :class:`PayrollRunWizardDialog`.
    """

    state_changed = Signal(int, str)  # (run_id, new_status_code)
    employee_open_requested = Signal(int)  # run_employee_id
    selection_changed = Signal()
    closed = Signal()

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        run_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._run_id = run_id

        self._run: PayrollRunDetailDTO | None = None
        self._employees: list[PayrollRunEmployeeListItemDTO] = []
        self._employee_detail_cache: dict[int, PayrollRunEmployeeDetailDTO] = {}
        # P6.S2: track whether the posting pane has loaded its validation
        # results at least once (avoid repeat network calls on tab switch).
        self._posting_validated: bool = False

        self._build_ui()
        self.refresh()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        spacing = DEFAULT_TOKENS.spacing

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header --------------------------------------------------------
        self._header = WorkbenchHeader(self)
        self._status_chip = StatusChip("draft")
        self._currency_label = QLabel("")
        self._currency_label.setObjectName("PayrollRunCockpitCurrency")
        self._primary_btn = QPushButton("")
        self._primary_btn.setObjectName("PayrollRunCockpitPrimary")
        self._primary_btn.setDefault(True)
        self._primary_btn.clicked.connect(self._on_primary)

        # Submit-for-review (P7.S1): visible only for calculated runs.
        # P7 ships the full state change.
        self._submit_review_btn = QPushButton("Submit for review")
        self._submit_review_btn.setObjectName("PayrollRunCockpitSubmitReview")
        self._submit_review_btn.clicked.connect(self._on_submit_for_review)
        self._submit_review_btn.setVisible(False)

        # P7: Approve / Send Back — visible for approvers on submitted runs.
        self._approve_btn = QPushButton("Approve")
        self._approve_btn.setObjectName("PayrollRunCockpitApprove")
        self._approve_btn.clicked.connect(self._on_approve)
        self._approve_btn.setVisible(False)

        self._send_back_btn = QPushButton("Send back…")
        self._send_back_btn.setObjectName("PayrollRunCockpitSendBack")
        self._send_back_btn.clicked.connect(self._on_send_back)
        self._send_back_btn.setVisible(False)

        ctx = QFrame(self._header)
        ctx_lay = QHBoxLayout(ctx)
        ctx_lay.setContentsMargins(0, 0, 0, 0)
        ctx_lay.setSpacing(spacing.compact_gap)
        ctx_lay.addWidget(self._currency_label)
        ctx_lay.addWidget(self._status_chip)
        ctx_lay.addWidget(self._submit_review_btn)
        ctx_lay.addWidget(self._approve_btn)
        ctx_lay.addWidget(self._send_back_btn)
        ctx_lay.addWidget(self._primary_btn)
        self._header.set_context_widget(ctx)
        root.addWidget(self._header)

        # KPI strip -----------------------------------------------------
        kpi_row = QFrame(self)
        kpi_row.setObjectName("PayrollRunCockpitKpis")
        kpi_lay = QHBoxLayout(kpi_row)
        kpi_lay.setContentsMargins(
            spacing.page_padding, spacing.compact_gap,
            spacing.page_padding, spacing.compact_gap,
        )
        kpi_lay.setSpacing(spacing.compact_gap)
        self._kpi_employees = KpiTile(KpiTileData(label="Employees", value="—"))
        self._kpi_gross = KpiTile(KpiTileData(label="Gross", value="—"))
        self._kpi_deductions = KpiTile(KpiTileData(label="Deductions", value="—"))
        self._kpi_net = KpiTile(KpiTileData(label="Net Payable", value="—"))
        for tile in (
            self._kpi_employees, self._kpi_gross,
            self._kpi_deductions, self._kpi_net,
        ):
            kpi_lay.addWidget(tile, 1)
        root.addWidget(kpi_row)

        # Timeline strip (P6.S1) ----------------------------------------
        self._timeline = RunTimelineWidget(self)
        self._timeline.setObjectName("PayrollRunCockpitTimeline")
        tl_frame = QFrame(self)
        tl_frame.setObjectName("PayrollRunCockpitTimelineFrame")
        tl_lay = QHBoxLayout(tl_frame)
        tl_lay.setContentsMargins(
            spacing.page_padding, 4, spacing.page_padding, 4,
        )
        tl_lay.addWidget(self._timeline)
        root.addWidget(tl_frame)

        # Body splitter -------------------------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("PayrollRunCockpitSplitter")
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        splitter.addWidget(self._build_centre())
        splitter.addWidget(self._build_right_rail())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([800, 320])

    def _build_centre(self) -> QWidget:
        spacing = DEFAULT_TOKENS.spacing
        host = QFrame(self)
        host.setObjectName("PayrollRunCockpitCentre")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(
            spacing.page_padding, spacing.compact_gap,
            spacing.compact_gap, spacing.page_padding,
        )
        lay.setSpacing(spacing.compact_gap)

        # Filter bar
        bar = QHBoxLayout()
        bar.setSpacing(spacing.compact_gap)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search employee…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filters)
        bar.addWidget(self._search, 2)

        self._status_filter = QComboBox()
        self._status_filter.addItem("All statuses", _FILTER_ALL)
        for code, label in _EMP_STATUS_LABELS.items():
            self._status_filter.addItem(label, code)
        self._status_filter.currentIndexChanged.connect(self._apply_filters)
        bar.addWidget(self._status_filter, 1)

        self._density_btn = QToolButton()
        self._density_btn.setText("Compact")
        self._density_btn.setCheckable(True)
        self._density_btn.toggled.connect(self._on_density_toggled)
        bar.addWidget(self._density_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self._refresh_btn)

        bar.addStretch(1)

        self._toggle_btn = QPushButton("Exclude…")
        self._toggle_btn.clicked.connect(self._on_toggle_inclusion)
        self._toggle_btn.setEnabled(False)
        bar.addWidget(self._toggle_btn)

        self._open_btn = QPushButton("Open Employee…")
        self._open_btn.clicked.connect(self._on_open_employee)
        self._open_btn.setEnabled(False)
        bar.addWidget(self._open_btn)

        self._correction_btn = QPushButton("Correction…")
        self._correction_btn.clicked.connect(self._on_queue_correction)
        self._correction_btn.setEnabled(False)
        bar.addWidget(self._correction_btn)

        lay.addLayout(bar)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setObjectName("PayrollRunCockpitTree")
        self._tree.setColumnCount(_COL_COUNT)
        self._tree.setHeaderLabels([
            "Employee", "Gross", "Earnings", "Deductions",
            "Statutory", "Net", "Employer Cost", "Status",
        ])
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSortingEnabled(True)
        self._tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(_COL_EMPLOYEE, QHeaderView.ResizeMode.Stretch)
        for col in _NUMERIC_COLS:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.itemSelectionChanged.connect(self._on_tree_selection)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        lay.addWidget(self._tree, 1)

        # Totals strip
        self._totals_strip = QLabel("")
        self._totals_strip.setObjectName("PayrollRunCockpitTotals")
        self._totals_strip.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        font = self._totals_strip.font()
        font.setWeight(QFont.Weight.DemiBold)
        self._totals_strip.setFont(font)
        lay.addWidget(self._totals_strip)

        return host

    def _build_right_rail(self) -> QWidget:
        host = QFrame(self)
        host.setObjectName("PayrollRunCockpitRail")
        host.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._rail_tabs = QTabWidget(host)
        self._rail_tabs.setDocumentMode(True)

        self._rail_tabs.addTab(self._build_summary_pane(), "Summary")     # 0
        self._rail_tabs.addTab(self._build_inputs_pane(), "Inputs")       # 1
        self._rail_tabs.addTab(self._build_variance_pane(), "Variance")   # 2
        self._rail_tabs.addTab(self._build_issues_pane(), "Issues")       # 3
        self._rail_tabs.addTab(self._build_posting_pane(), "Posting")     # 4
        self._rail_tabs.addTab(self._build_payments_pane(), "Payments")   # 5
        self._rail_tabs.addTab(self._build_remit_pane(), "Remittances")   # 6
        self._rail_tabs.addTab(self._build_audit_pane(), "Audit")         # 7

        # Refresh posting/payments/remittance when those tabs are activated so
        # the user always sees current data.
        self._rail_tabs.currentChanged.connect(self._on_rail_tab_changed)

        lay.addWidget(self._rail_tabs)
        return host

    def _build_summary_pane(self) -> QWidget:
        host = QFrame()
        spacing = DEFAULT_TOKENS.spacing
        lay = QVBoxLayout(host)
        lay.setContentsMargins(
            spacing.dialog_padding, spacing.dialog_padding,
            spacing.dialog_padding, spacing.dialog_padding,
        )
        lay.setSpacing(spacing.dialog_field_gap)
        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._summary_label)
        lay.addStretch(1)
        return host

    def _build_variance_pane(self) -> QWidget:
        host = QFrame()
        spacing = DEFAULT_TOKENS.spacing
        lay = QVBoxLayout(host)
        lay.setContentsMargins(
            spacing.dialog_padding, spacing.dialog_padding,
            spacing.dialog_padding, spacing.dialog_padding,
        )
        lay.setSpacing(spacing.dialog_field_gap)

        heading = QLabel("Variance vs. prior run")
        f = QFont(heading.font())
        f.setBold(True)
        heading.setFont(f)
        lay.addWidget(heading)

        self._variance_label = QLabel(
            "Calculate the run to see deltas vs. the most recent prior run."
        )
        self._variance_label.setWordWrap(True)
        self._variance_label.setObjectName("PayrollRunCockpitVariance")
        lay.addWidget(self._variance_label)

        self._variance_table = QTreeWidget()
        self._variance_table.setObjectName("PayrollRunCockpitVarianceTable")
        self._variance_table.setColumnCount(4)
        self._variance_table.setHeaderLabels([
            "Metric", "Prior", "Current", "Delta",
        ])
        self._variance_table.setRootIsDecorated(False)
        self._variance_table.setUniformRowHeights(True)
        self._variance_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for col in (1, 2, 3):
            self._variance_table.headerItem().setTextAlignment(
                col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
        lay.addWidget(self._variance_table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._dry_run_report_btn = QPushButton("Export Dry-Run Report…")
        self._dry_run_report_btn.clicked.connect(self._on_export_dry_run_report)
        btn_row.addWidget(self._dry_run_report_btn)
        lay.addLayout(btn_row)

        note = QLabel(
            "Variance uses persisted calculation output and company threshold settings."
        )
        note.setWordWrap(True)
        note.setObjectName("PayrollRunCockpitVarianceNote")
        lay.addWidget(note)
        return host

    def _build_inputs_pane(self) -> QWidget:
        host = QFrame()
        spacing = DEFAULT_TOKENS.spacing
        lay = QVBoxLayout(host)
        lay.setContentsMargins(
            spacing.dialog_padding, spacing.dialog_padding,
            spacing.dialog_padding, spacing.dialog_padding,
        )
        lay.setSpacing(spacing.dialog_field_gap)

        heading = QLabel("Variable inputs for this period")
        f = QFont(heading.font())
        f.setBold(True)
        heading.setFont(f)
        lay.addWidget(heading)

        self._inputs_summary = QLabel("")
        self._inputs_summary.setWordWrap(True)
        lay.addWidget(self._inputs_summary)

        self._inputs_table = QTreeWidget()
        self._inputs_table.setObjectName("PayrollRunCockpitInputsTable")
        self._inputs_table.setColumnCount(4)
        self._inputs_table.setHeaderLabels([
            "Reference", "Status", "Lines", "Submitted",
        ])
        self._inputs_table.setRootIsDecorated(False)
        self._inputs_table.setUniformRowHeights(True)
        self._inputs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._inputs_table.itemDoubleClicked.connect(
            lambda *_: self._on_open_input_batch()
        )
        lay.addWidget(self._inputs_table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._open_inputs_btn = QPushButton("Open Inputs Workspace")
        self._open_inputs_btn.clicked.connect(self._on_open_inputs_workspace)
        btn_row.addWidget(self._open_inputs_btn)
        lay.addLayout(btn_row)

        note = QLabel(
            "Inline edit of variable-input lines arrives with Phase 3 "
            "deeper integration. Today, double-click a batch to open it "
            "in the inputs workspace."
        )
        note.setWordWrap(True)
        note.setObjectName("PayrollRunCockpitInputsNote")
        lay.addWidget(note)
        return host

    def _build_issues_pane(self) -> QWidget:
        return EmptyState(
            headline="Validation issues",
            body=(
                "Run-level validation issues will appear here. Wire-up arrives "
                "with Phase 14 (validation hardening)."
            ),
        )

    def _build_posting_pane(self) -> QWidget:
        """Inline post-to-GL panel (P6.S2).

        Layout:
            • Posting date selector + narration field.
            • "Validate" button → shows issue list below inline.
            • "Post to GL" button → calls posting service.
            • After posting: shows journal entry summary.
        """
        spacing = DEFAULT_TOKENS.spacing
        host = QFrame()
        host.setObjectName("PayrollRunCockpitPostingPane")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(
            spacing.dialog_padding, spacing.dialog_padding,
            spacing.dialog_padding, spacing.dialog_padding,
        )
        lay.setSpacing(spacing.dialog_field_gap)

        heading = QLabel("Post to GL")
        hf = QFont(heading.font())
        hf.setBold(True)
        heading.setFont(hf)
        lay.addWidget(heading)

        # ── Posting date ────────────────────────────────────────────────
        date_row = QHBoxLayout()
        date_row.setSpacing(spacing.compact_gap)
        date_row.addWidget(QLabel("Posting date:"))
        self._posting_date = QDateEdit()
        self._posting_date.setCalendarPopup(True)
        self._posting_date.setDisplayFormat("yyyy-MM-dd")
        today = _date.today()
        self._posting_date.setDate(QDate(today.year, today.month, today.day))
        date_row.addWidget(self._posting_date)
        date_row.addStretch(1)
        lay.addLayout(date_row)

        # ── Narration ────────────────────────────────────────────────────
        lay.addWidget(QLabel("Narration (optional):"))
        self._posting_narration = QPlainTextEdit()
        self._posting_narration.setMaximumHeight(52)
        self._posting_narration.setPlaceholderText("Leave blank for auto narration")
        lay.addWidget(self._posting_narration)

        # ── Validation issues ────────────────────────────────────────────
        self._posting_issues_label = QLabel("")
        self._posting_issues_label.setObjectName("PayrollRunCockpitPostingIssues")
        self._posting_issues_label.setWordWrap(True)
        self._posting_issues_label.setTextFormat(Qt.TextFormat.RichText)
        self._posting_issues_label.setVisible(False)
        lay.addWidget(self._posting_issues_label)

        # ── Action buttons ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(spacing.compact_gap)
        self._posting_validate_btn = QPushButton("Validate…")
        self._posting_validate_btn.clicked.connect(self._on_posting_validate)
        btn_row.addWidget(self._posting_validate_btn)
        self._posting_post_btn = QPushButton("Post to GL")
        self._posting_post_btn.setObjectName("PayrollRunCockpitPostBtn")
        self._posting_post_btn.clicked.connect(self._on_posting_post)
        self._posting_post_btn.setEnabled(False)
        btn_row.addWidget(self._posting_post_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        # ── Posted result summary ────────────────────────────────────────
        self._posting_result_label = QLabel("")
        self._posting_result_label.setObjectName("PayrollRunCockpitPostingResult")
        self._posting_result_label.setWordWrap(True)
        self._posting_result_label.setTextFormat(Qt.TextFormat.RichText)
        self._posting_result_label.setVisible(False)
        lay.addWidget(self._posting_result_label)

        # Journal lines table (shown after successful post)
        self._posting_journal_table = QTreeWidget()
        self._posting_journal_table.setObjectName("PayrollRunCockpitJournalTable")
        self._posting_journal_table.setColumnCount(3)
        self._posting_journal_table.setHeaderLabels(["Account", "Dr", "Cr"])
        self._posting_journal_table.setRootIsDecorated(False)
        self._posting_journal_table.setUniformRowHeights(True)
        self._posting_journal_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._posting_journal_table.setVisible(False)
        hdr = self._posting_journal_table.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._posting_journal_table, 1)

        lay.addStretch(1)
        return host

    def _build_payments_pane(self) -> QWidget:
        """Per-employee payment settlement pane (P6.S3)."""
        spacing = DEFAULT_TOKENS.spacing
        host = QFrame()
        host.setObjectName("PayrollRunCockpitPaymentsPane")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(
            spacing.dialog_padding, spacing.dialog_padding,
            spacing.dialog_padding, spacing.dialog_padding,
        )
        lay.setSpacing(spacing.dialog_field_gap)

        heading = QLabel("Employee Payments")
        hf = QFont(heading.font())
        hf.setBold(True)
        heading.setFont(hf)
        lay.addWidget(heading)

        self._payments_status_label = QLabel(
            "Payments are tracked once the run is posted."
        )
        self._payments_status_label.setWordWrap(True)
        lay.addWidget(self._payments_status_label)

        # Per-employee payment table
        self._payments_model = QStandardItemModel(0, 5)
        self._payments_table = DataTable(
            columns=(
                DataTableColumn(key="employee", title="Employee"),
                DataTableColumn(key="net_payable", title="Net Payable", is_numeric=True),
                DataTableColumn(key="paid", title="Paid", is_numeric=True),
                DataTableColumn(key="outstanding", title="Outstanding", is_numeric=True),
                DataTableColumn(key="status", title="Status"),
            ),
            show_search=False,
            selection_mode="single",
            parent=host,
        )
        self._payments_table.set_model(self._payments_model)
        lay.addWidget(self._payments_table, 1)

        # Record payment button
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._payments_record_btn = QPushButton("Record Payment…")
        self._payments_record_btn.setEnabled(False)
        self._payments_record_btn.clicked.connect(self._on_record_payment)
        btn_row.addWidget(self._payments_record_btn)
        lay.addLayout(btn_row)

        self._payments_table.selection_changed.connect(
            lambda _rows: self._payments_record_btn.setEnabled(
                bool(_rows)
                and self._run is not None
                and self._run.status_code == "posted"
            )
        )
        return host

    def _build_remit_pane(self) -> QWidget:
        """Remittance hand-off pane (P6.S4)."""
        spacing = DEFAULT_TOKENS.spacing
        host = QFrame()
        host.setObjectName("PayrollRunCockpitRemitPane")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(
            spacing.dialog_padding, spacing.dialog_padding,
            spacing.dialog_padding, spacing.dialog_padding,
        )
        lay.setSpacing(spacing.dialog_field_gap)

        heading = QLabel("Remittances due")
        hf = QFont(heading.font())
        hf.setBold(True)
        heading.setFont(hf)
        lay.addWidget(heading)

        self._remit_status_label = QLabel(
            "Statutory authority remittances for this period are computed here once the "
            "run is approved and the payroll component-to-authority map is applied."
        )
        self._remit_status_label.setWordWrap(True)
        lay.addWidget(self._remit_status_label)

        # Authorities table
        self._remit_model = QStandardItemModel(0, 3)
        self._remit_table = DataTable(
            columns=(
                DataTableColumn(key="authority", title="Statutory authority"),
                DataTableColumn(key="amount_due", title="Amount Due", is_numeric=True),
                DataTableColumn(key="deadline", title="Deadline"),
            ),
            show_search=False,
            selection_mode="single",
            parent=host,
        )
        self._remit_table.set_model(self._remit_model)
        lay.addWidget(self._remit_table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._remit_open_btn = QPushButton("Open remittance editor...")
        self._remit_open_btn.setEnabled(False)
        self._remit_open_btn.clicked.connect(self._on_open_remittance_editor)
        btn_row.addWidget(self._remit_open_btn)
        lay.addLayout(btn_row)

        self._remit_table.selection_changed.connect(
            lambda _rows: self._remit_open_btn.setEnabled(bool(_rows))
        )
        return host

    def _build_audit_pane(self) -> QWidget:
        return EmptyState(
            headline="Audit trail",
            body=(
                "Every state transition for this run is recorded in the audit "
                "log. A scoped feed lands with Phase 14."
            ),
        )

    # ── Public API ────────────────────────────────────────────────────

    @property
    def run_id(self) -> int:
        return self._run_id

    def get_ambient_context(self) -> dict[str, object]:
        """Expose current run state for the ambient thought overlay."""
        run = self._run
        if run is None:
            return {}
        return {
            "run_id": self._run_id,
            "run_status": getattr(run, "status_code", None),
            "run_period_label": getattr(run, "period_label", None),
            "run_currency": getattr(run, "currency_code", None),
        }

    def refresh(self) -> None:
        """Re-load run + employees from the service layer."""
        company_id = self._company_id
        run_id = self._run_id
        task = run_with_progress(
            parent=self,
            title="Payroll run",
            message="Loading run data…",
            worker=lambda: (
                self._registry.payroll_run_service.get_run(company_id, run_id),
                list(self._registry.payroll_run_service.list_run_employees(company_id, run_id)),
            ),
        )
        if task.cancelled:
            return
        if task.error is not None:
            _log.warning("Failed to load payroll run %s: %s", run_id, task.error)
            show_error(
                self, "Payroll run",
                f"Failed to load the run.\n\n{task.error}",
            )
            return

        run, employees = task.value
        self._run = run
        self._employees = employees
        self._employee_detail_cache.clear()
        self._posting_validated = False  # P6.S2: reset validation state on reload

        self._render_header()
        self._render_kpis()
        self._render_tree()
        self._render_summary()
        self._render_inputs_pane()
        self._render_variance_pane()
        self._render_posting_pane()
        self._render_payments_pane()
        self._render_remit_pane()
        self._update_action_state()

    # ── Header / KPIs / summary ───────────────────────────────────────

    def _render_header(self) -> None:
        run = self._run
        if run is None:
            return
        period = f"{_MONTHS.get(run.period_month, str(run.period_month))} {run.period_year}"
        self._header.set_breadcrumb("Payroll · Run cockpit")
        self._header.set_title(f"{run.run_reference} — {period}")
        label = run.run_label or ""
        if label and label != f"{period} Payroll":
            self._header.set_subtitle(label)
        else:
            self._header.set_subtitle("")

        self._currency_label.setText(run.currency_code or "")
        self._status_chip.set_status(run.status_code)
        self._status_chip.setToolTip(
            PayrollRunStateMachine.status_label(run.status_code)
        )
        # P6.S1 — keep the timeline in sync.
        self._timeline.set_status(run.status_code)

    def _render_kpis(self) -> None:
        included = [e for e in self._employees if e.status_code != "excluded"]
        n = len(included)
        gross = sum((e.gross_earnings or Decimal(0)) for e in included)
        deductions = sum(
            ((e.total_employee_deductions or Decimal(0)) + (e.total_taxes or Decimal(0)))
            for e in included
        )
        net = sum((e.net_payable or Decimal(0)) for e in included)
        currency = self._run.currency_code if self._run else ""
        suffix = f" {currency}" if currency else ""
        self._kpi_employees.update_data(KpiTileData(
            label="Employees included", value=str(n),
        ))
        self._kpi_gross.update_data(KpiTileData(
            label="Gross", value=f"{_fmt_money(gross)}{suffix}",
        ))
        self._kpi_deductions.update_data(KpiTileData(
            label="Deductions + taxes", value=f"{_fmt_money(deductions)}{suffix}",
        ))
        self._kpi_net.update_data(KpiTileData(
            label="Net payable", value=f"{_fmt_money(net)}{suffix}",
        ))

    def _render_summary(self) -> None:
        run = self._run
        if run is None:
            self._summary_label.setText("")
            return
        period = f"{_MONTHS.get(run.period_month, str(run.period_month))} {run.period_year}"
        lines: list[str] = []
        lines.append(f"<b>Reference:</b> {run.run_reference}")
        lines.append(f"<b>Period:</b> {period}")
        lines.append(f"<b>Status:</b> {PayrollRunStateMachine.status_label(run.status_code)}")
        lines.append(f"<b>Currency:</b> {run.currency_code or '—'}")
        if run.run_date:
            lines.append(f"<b>Run date:</b> {run.run_date}")
        if run.payment_date:
            lines.append(f"<b>Payment date:</b> {run.payment_date}")
        if run.calculated_at:
            lines.append(f"<b>Calculated at:</b> {run.calculated_at:%Y-%m-%d %H:%M}")
        if run.approved_at:
            lines.append(f"<b>Approved at:</b> {run.approved_at:%Y-%m-%d %H:%M}")
        if run.posted_at:
            lines.append(f"<b>Posted at:</b> {run.posted_at:%Y-%m-%d %H:%M}")
        # P7: show send-back annotation to preparer
        sent_back_reason = getattr(run, "sent_back_reason", None)
        if sent_back_reason:
            lines.append("")
            lines.append(
                f"<b style='color:{_P.status_danger_fg}'>Sent back for revision:</b> {sent_back_reason}"
            )
        if run.notes:
            lines.append("")
            lines.append(f"<i>{run.notes}</i>")
        self._summary_label.setText("<br>".join(lines))

    # ── Inputs pane (P3.S2) ──────────────────────────────────────────

    def _render_inputs_pane(self) -> None:
        self._inputs_table.clear()
        run = self._run
        if run is None:
            self._inputs_summary.setText("")
            return
        try:
            batches = self._registry.payroll_input_service.list_batches(
                self._company_id,
                period_year=run.period_year,
                period_month=run.period_month,
            )
        except Exception:  # noqa: BLE001
            _log.debug("Inputs lookup failed", exc_info=True)
            batches = []

        approved = sum(1 for b in batches if b.status_code == "approved")
        draft = sum(1 for b in batches if b.status_code == "draft")
        voided = sum(1 for b in batches if b.status_code == "voided")
        if not batches:
            self._inputs_summary.setText(
                "No variable inputs for this period."
            )
        else:
            parts = []
            if approved:
                parts.append(f"{approved} approved")
            if draft:
                parts.append(f"{draft} draft")
            if voided:
                parts.append(f"{voided} voided")
            self._inputs_summary.setText(
                f"{len(batches)} batch(es) — " + ", ".join(parts)
            )

        for b in batches:
            item = QTreeWidgetItem()
            item.setData(0, Qt.ItemDataRole.UserRole, b.id)
            item.setText(0, getattr(b, "reference", "") or f"Batch #{b.id}")
            item.setText(1, (b.status_code or "").title())
            line_count = getattr(b, "line_count", None)
            if line_count is None:
                line_count = len(getattr(b, "lines", []) or [])
            item.setText(2, str(line_count))
            submitted = getattr(b, "submitted_at", None)
            if submitted:
                item.setText(3, f"{submitted:%Y-%m-%d}")
            self._inputs_table.addTopLevelItem(item)

    def _on_open_input_batch(self) -> None:
        items = self._inputs_table.selectedItems()
        if not items:
            return
        batch_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(batch_id, int):
            return
        manager = getattr(self._registry, "child_window_manager", None)
        try:
            from seeker_accounting.modules.payroll.ui.payroll_input_batch_window import (
                PayrollInputBatchWindow,
            )
        except Exception:  # noqa: BLE001
            _log.debug("PayrollInputBatchWindow unavailable", exc_info=True)
            return
        if manager is not None:
            manager.open_document(
                getattr(PayrollInputBatchWindow, "DOC_TYPE", "payroll_input_batch"),
                batch_id,
                lambda: PayrollInputBatchWindow(
                    self._registry,
                    company_id=self._company_id,
                    batch_id=batch_id,
                ),
            )
        else:
            window = PayrollInputBatchWindow(
                self._registry,
                company_id=self._company_id,
                batch_id=batch_id,
            )
            window.show()

    def _on_open_inputs_workspace(self) -> None:
        # Bounce to the calculation workspace's Inputs tab if accessible;
        # otherwise this is a no-op (we already show the list inline).
        nav = getattr(self._registry, "navigation_service", None)
        if nav is None or not hasattr(nav, "navigate_to"):
            return
        try:
            nav.navigate_to("payroll.calculation", context={"tab": "inputs"})
        except Exception:  # noqa: BLE001
            _log.debug("Navigate to inputs workspace failed", exc_info=True)

    # ── Variance pane (P9) ───────────────────────────────────────────

    def _render_variance_pane(self) -> None:
        run = self._run
        self._variance_table.clear()
        if run is None:
            self._variance_label.setText("")
            return

        if run.status_code in ("draft",):
            self._variance_label.setText(
                "Calculate the run to see deltas vs. the most recent prior run."
            )
            return

        svc = getattr(self._registry, "payroll_variance_analysis_service", None)
        if svc is None:
            self._variance_label.setText("Variance analysis service unavailable.")
            return
        try:
            analysis = svc.analyze_run(self._company_id, run.id)
        except Exception as exc:  # noqa: BLE001
            _log.debug("Variance analysis failed", exc_info=True)
            self._variance_label.setText(f"Variance analysis failed: {exc}")
            return

        if analysis.prior_run_reference:
            self._variance_label.setText(
                f"Comparing to <b>{analysis.prior_run_reference}</b>. "
                f"Threshold: {analysis.threshold_percent}%."
            )
        else:
            self._variance_label.setText(
                "No prior comparable run found; current amounts are shown as new values."
            )

        for line in analysis.lines:
            pct = "" if line.delta_percent is None else f" ({line.delta_percent:+.1f}%)"
            item = QTreeWidgetItem([
                line.subject_label,
                _fmt_money(line.prior_amount),
                _fmt_money(line.current_amount),
                f"{_fmt_money(line.delta_amount)}{pct}",
            ])
            item.setToolTip(0, line.explanation)
            for col in (1, 2, 3):
                item.setTextAlignment(
                    col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                )
            self._variance_table.addTopLevelItem(item)

    def _on_export_dry_run_report(self) -> None:
        run = self._run
        if run is None:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Dry-Run Report",
            f"payroll_dry_run_{run.run_reference}.csv",
            "CSV files (*.csv);;HTML files (*.html);;PDF files (*.pdf)",
        )
        if not path:
            return
        fmt = "csv"
        lower = path.lower()
        if lower.endswith(".html"):
            fmt = "html"
        elif lower.endswith(".pdf"):
            fmt = "pdf"
        elif "HTML" in selected_filter:
            fmt = "html"
        elif "PDF" in selected_filter:
            fmt = "pdf"
        try:
            self._registry.payroll_dry_run_report_service.export_report(
                self._company_id, run.id, path, fmt=fmt
            )
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Dry-Run Report", str(exc))
            return
        show_info(self, "Dry-run report exported.")

    # ── Tree rendering ───────────────────────────────────────────────

    def _render_tree(self) -> None:
        self._tree.setSortingEnabled(False)
        self._tree.clear()
        rail_currency = self._run.currency_code if self._run else ""
        for emp in self._employees:
            item = _NumericTreeItem()
            item.setData(_COL_EMPLOYEE, Qt.ItemDataRole.UserRole, emp.id)
            item.setText(_COL_EMPLOYEE, emp.employee_display_name or f"#{emp.employee_id}")
            statutory = (emp.total_taxes or Decimal(0))
            earnings = (emp.gross_earnings or Decimal(0))
            for col, value in (
                (_COL_GROSS, emp.gross_earnings),
                (_COL_EARNINGS, earnings),
                (_COL_DEDUCTIONS, emp.total_employee_deductions),
                (_COL_STATUTORY, statutory),
                (_COL_NET, emp.net_payable),
                (_COL_EMPLOYER, emp.employer_cost_base),
            ):
                self._set_numeric(item, col, value)
            status_text = _emp_status_label(emp.status_code)
            if emp.status_code == "excluded" and emp.exclusion_reason:
                item.setToolTip(_COL_STATUS, reason_label(emp.exclusion_reason))
            item.setText(_COL_STATUS, status_text)
            # Lazy expansion sentinel:
            placeholder = QTreeWidgetItem(item)
            placeholder.setText(_COL_EMPLOYEE, "Loading…")
            placeholder.setDisabled(True)
            placeholder.setData(_COL_EMPLOYEE, Qt.ItemDataRole.UserRole + 2, "placeholder")
            self._tree.addTopLevelItem(item)
        self._tree.setSortingEnabled(True)
        self._tree.sortItems(_COL_EMPLOYEE, Qt.SortOrder.AscendingOrder)
        self._apply_filters()
        self._render_totals()
        _ = rail_currency  # currently unused, reserved for future column

    @staticmethod
    def _set_numeric(item: QTreeWidgetItem, col: int, value: Decimal | None) -> None:
        item.setText(col, _fmt_money(value))
        item.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setData(col, Qt.ItemDataRole.UserRole + 1, str(value or 0))

    def _render_totals(self) -> None:
        if not self._employees:
            self._totals_strip.setText("")
            return
        included = [e for e in self._employees if e.status_code != "excluded"]
        gross = sum((e.gross_earnings or Decimal(0)) for e in included)
        deductions = sum((e.total_employee_deductions or Decimal(0)) for e in included)
        statutory = sum((e.total_taxes or Decimal(0)) for e in included)
        net = sum((e.net_payable or Decimal(0)) for e in included)
        currency = self._run.currency_code if self._run else ""
        self._totals_strip.setText(
            f"Totals ({len(included)} included) · "
            f"Gross {_fmt_money(gross)} · "
            f"Deductions {_fmt_money(deductions)} · "
            f"Statutory {_fmt_money(statutory)} · "
            f"Net {_fmt_money(net)} {currency}".strip()
        )

    def _apply_filters(self) -> None:
        text = (self._search.text() or "").strip().lower()
        status = self._status_filter.currentData()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item is None:
                continue
            emp_id = item.data(_COL_EMPLOYEE, Qt.ItemDataRole.UserRole)
            emp = next((e for e in self._employees if e.id == emp_id), None)
            visible = True
            if emp is None:
                visible = False
            else:
                if text and text not in (emp.employee_display_name or "").lower() \
                        and text not in (emp.employee_number or "").lower():
                    visible = False
                if status and status != _FILTER_ALL and emp.status_code != status:
                    visible = False
            item.setHidden(not visible)

    # ── Posting pane rendering (P6.S2) ───────────────────────────────

    def _render_posting_pane(self) -> None:
        run = self._run
        if run is None:
            return

        already_posted = run.status_code in ("posted", "paid", "closed", "reversed")

        if already_posted and run.posted_at:
            # Show summary of the completed posting.
            posted_at = run.posted_at.strftime("%Y-%m-%d %H:%M")
            html = (
                f"<b>Posted</b> {posted_at}<br>"
                "<i>The posting is complete. See journal entry for details.</i>"
            )
            self._posting_result_label.setText(html)
            self._posting_result_label.setVisible(True)
            self._posting_validate_btn.setEnabled(False)
            self._posting_post_btn.setEnabled(False)
            self._posting_date.setEnabled(False)
            self._posting_narration.setEnabled(False)
        else:
            # Enable / disable based on run readiness.
            can_post = run.status_code == "approved"
            self._posting_validate_btn.setEnabled(can_post)
            self._posting_post_btn.setEnabled(False)  # enabled after validate
            self._posting_date.setEnabled(can_post)
            self._posting_narration.setEnabled(can_post)
            self._posting_result_label.setVisible(False)
            self._posting_journal_table.setVisible(False)
            if not can_post:
                self._posting_issues_label.setText(
                    f"<i>Posting is available when the run is approved. "
                    f"Current status: <b>{PayrollRunStateMachine.status_label(run.status_code)}</b>.</i>"
                )
                self._posting_issues_label.setVisible(True)
            else:
                self._posting_issues_label.setVisible(False)

    def _on_rail_tab_changed(self, index: int) -> None:
        if index == _TAB_POSTING:
            self._render_posting_pane()
        elif index == _TAB_PAYMENTS:
            self._render_payments_pane()
        elif index == _TAB_REMIT:
            self._render_remit_pane()

    def _on_posting_validate(self) -> None:
        run = self._run
        if run is None:
            return
        posting_svc = getattr(self._registry, "payroll_posting_service", None)
        if posting_svc is None:
            self._posting_issues_label.setText(
                f"<span style='color:{_P.status_danger_fg}'>Posting service unavailable.</span>"
            )
            self._posting_issues_label.setVisible(True)
            return

        # Build a lightweight validation: call validate_posting if it
        # exists, otherwise use post_run in dry-run mode or just check
        # basic preconditions here.
        validate = getattr(posting_svc, "validate_posting", None)
        if validate is not None:
            try:
                from seeker_accounting.modules.payroll.dto.payroll_posting_dto import (
                    PostPayrollRunCommand,
                )
                qd = self._posting_date.date()
                cmd = PostPayrollRunCommand(
                    run_id=self._run_id,
                    posting_date=_date(qd.year(), qd.month(), qd.day()),
                    narration=self._posting_narration.toPlainText().strip() or None,
                )
                result = validate(self._company_id, cmd)
            except Exception as exc:  # noqa: BLE001
                _log.debug("validate_posting failed", exc_info=True)
                self._posting_issues_label.setText(
                    f"<span style='color:{_P.status_danger_fg}'>Validation error: {exc}</span>"
                )
                self._posting_issues_label.setVisible(True)
                return
        else:
            # Service has no dedicated validate method; the only check
            # we can do here is that the run is approved.
            result = None  # type: ignore[assignment]

        if result is not None and result.has_errors:
            lines = []
            for issue in result.issues:
                icon = "✖" if issue.severity == "error" else "⚠"
                color = _P.danger if issue.severity == "error" else _P.warning
                lines.append(
                    f"<span style='color:{color}'>{icon} {issue.message}</span>"
                )
            self._posting_issues_label.setText("<br>".join(lines))
            self._posting_issues_label.setVisible(True)
            self._posting_post_btn.setEnabled(False)
        else:
            if result is not None and result.warning_count:
                lines = []
                for issue in result.issues:
                    lines.append(f"⚠ {issue.message}")
                self._posting_issues_label.setText(
                    "<br>".join(f"<span style='color:{_P.status_warning_fg}'>{l}</span>" for l in lines)
                )
                self._posting_issues_label.setVisible(True)
            else:
                self._posting_issues_label.setText(
                    f"<span style='color:{_P.status_success_fg}'>✔ Ready to post — no issues found.</span>"
                )
                self._posting_issues_label.setVisible(True)
            self._posting_post_btn.setEnabled(True)
            self._posting_validated = True

    def _on_posting_post(self) -> None:
        run = self._run
        if run is None:
            return
        posting_svc = getattr(self._registry, "payroll_posting_service", None)
        if posting_svc is None:
            show_error(self, "Posting", "Posting service unavailable in this build.")
            return
        qd = self._posting_date.date()
        posting_date = _date(qd.year(), qd.month(), qd.day())
        narration = self._posting_narration.toPlainText().strip() or None
        try:
            from seeker_accounting.modules.payroll.dto.payroll_posting_dto import (
                PostPayrollRunCommand,
            )
            cmd = PostPayrollRunCommand(
                run_id=self._run_id,
                posting_date=posting_date,
                narration=narration,
            )
            result = posting_svc.post_run(self._company_id, cmd)
        except Exception as exc:  # noqa: BLE001
            _log.exception("post_run failed")
            show_error(self, "Posting", str(exc))
            return

        # Show journal entry summary.
        self._posting_result_label.setText(
            f"<b>Posted</b> — Journal entry <b>{result.entry_number}</b> "
            f"({result.posting_date}) · "
            f"Dr {_fmt_money(result.total_debit)} "
            f"Cr {_fmt_money(result.total_credit)} "
            f"{run.currency_code}"
        )
        self._posting_result_label.setVisible(True)
        self._posting_post_btn.setEnabled(False)
        self._posting_validate_btn.setEnabled(False)

        # Populate journal lines table.
        self._posting_journal_table.clear()
        self._posting_journal_table.setColumnCount(3)
        self._posting_journal_table.setHeaderLabels(["Account", "Dr", "Cr"])
        for jl in result.journal_lines:
            it = QTreeWidgetItem([
                f"[{jl.account_code}] {jl.account_name}",
                _fmt_money(jl.debit_amount) if jl.debit_amount else "",
                _fmt_money(jl.credit_amount) if jl.credit_amount else "",
            ])
            for col in (1, 2):
                it.setTextAlignment(
                    col,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                )
            self._posting_journal_table.addTopLevelItem(it)
        self._posting_journal_table.setVisible(True)

        self.refresh()
        if self._run is not None:
            self.state_changed.emit(self._run_id, self._run.status_code)

    # ── Payments pane rendering (P6.S3) ──────────────────────────────

    def _render_payments_pane(self) -> None:
        run = self._run
        self._payments_model.removeRows(0, self._payments_model.rowCount())

        if run is None:
            return
        if run.status_code not in ("posted", "paid", "closed"):
            self._payments_status_label.setText(
                "Payment tracking is available after the run is posted."
            )
            self._payments_record_btn.setEnabled(False)
            return

        self._payments_status_label.setText("")
        payment_svc = getattr(self._registry, "payroll_payment_tracking_service", None)
        if payment_svc is None:
            self._payments_status_label.setText(
                "Payment tracking service unavailable."
            )
            return

        try:
            summaries = payment_svc.list_run_payment_summaries(
                self._company_id, run_id=self._run_id,
            )
        except Exception:  # noqa: BLE001
            _log.debug("list_run_payment_summaries failed", exc_info=True)
            summaries = []

        _STATUS_LABEL = {
            "unpaid": "Unpaid",
            "partial": "Partial",
            "paid": "Paid",
        }

        for s in summaries:
            name_item = self._make_item(s.employee_display_name or f"#{s.employee_id}")
            name_item.setData(s.run_employee_id, Qt.ItemDataRole.UserRole)
            name_item.setData(s.net_payable, Qt.ItemDataRole.UserRole + 1)
            self._payments_model.appendRow([
                name_item,
                self._make_item(_fmt_money(s.net_payable)),
                self._make_item(_fmt_money(s.total_paid)),
                self._make_item(_fmt_money(s.outstanding)),
                self._make_item(_STATUS_LABEL.get(s.payment_status_code, s.payment_status_code)),
            ])

    def _on_record_payment(self) -> None:
        run = self._run
        if run is None:
            return
        rows = self._payments_table.selected_rows()
        if not rows:
            return
        name_item = self._payments_model.item(rows[0], 0)
        if name_item is None:
            return
        run_employee_id = name_item.data(Qt.ItemDataRole.UserRole)
        net_payable = name_item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(run_employee_id, int):
            return
        from seeker_accounting.modules.payroll.ui.dialogs.payroll_payment_record_dialog import (
            PayrollPaymentRecordDialog,
        )
        from PySide6.QtWidgets import QDialog
        dlg = PayrollPaymentRecordDialog(
            self._registry,
            self._company_id,
            run_employee_id,
            net_payable or Decimal(0),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._render_payments_pane()

    # ── Remit pane rendering (P6.S4) ─────────────────────────────────

    def _render_remit_pane(self) -> None:
        run = self._run
        self._remit_model.removeRows(0, self._remit_model.rowCount())

        if run is None:
            return
        if run.status_code not in ("approved", "posted", "paid", "closed"):
            self._remit_status_label.setText(
                "Remittance estimates are available once the run is approved."
            )
            self._remit_open_btn.setEnabled(False)
            return

        engine = getattr(self._registry, "payroll_remittance_engine", None)
        auth_svc = getattr(self._registry, "payroll_authority_service", None)
        if engine is None or auth_svc is None:
            self._remit_status_label.setText(
                "Remittance engine or authority service unavailable."
            )
            return

        try:
            authorities = auth_svc.list_authorities(
                self._company_id, active_only=True,
            )
        except Exception:  # noqa: BLE001
            _log.debug("list_authorities failed", exc_info=True)
            self._remit_status_label.setText("Could not load authority list.")
            return

        if not authorities:
            self._remit_status_label.setText(
                "No authorities configured for this company. Apply a statutory "
                "pack or add authorities under Payroll → Setup → Statutory."
            )
            return

        self._remit_status_label.setText("")

        deadline_svc = getattr(
            self._registry, "payroll_remittance_deadline_service", None,
        )

        for auth in authorities:
            try:
                estimate = engine.estimate_for_period(
                    self._company_id,
                    authority_id=auth.id,
                    period_year=run.period_year,
                    period_month=run.period_month,
                )
                amount = estimate.total_amount
            except Exception:  # noqa: BLE001
                _log.debug(
                    "estimate_for_period failed for authority %s", auth.code,
                    exc_info=True,
                )
                amount = Decimal("0")

            deadline_str = ""
            if deadline_svc is not None:
                try:
                    from datetime import date as _d
                    period_end = _d(
                        run.period_year,
                        run.period_month,
                        __import__("calendar").monthrange(
                            run.period_year, run.period_month,
                        )[1],
                    )
                    dl = deadline_svc.compute_filing_deadline(auth.code, period_end)
                    if dl is not None:
                        deadline_str = str(dl)
                except Exception:  # noqa: BLE001
                    pass

            auth_item = self._make_item(f"{auth.code} — {auth.name}")
            auth_item.setData(auth.id, Qt.ItemDataRole.UserRole)
            auth_item.setData(auth.code, Qt.ItemDataRole.UserRole + 1)
            self._remit_model.appendRow([
                auth_item,
                self._make_item(_fmt_money(amount)),
                self._make_item(deadline_str),
            ])

    def _on_density_toggled(self, checked: bool) -> None:
        sizes = DEFAULT_TOKENS.sizes
        # Compact = base row_height; comfortable adds 8px padding via
        # uniform row hint. Qt does not expose a per-tree padding token,
        # so we toggle indentation + uniformRowHeights for a visible
        # density swap.
        self._density_btn.setText("Compact" if checked else "Comfortable")
        # Adjust indentation slightly to communicate the change.
        self._tree.setIndentation(12 if checked else 18)
        _ = sizes  # tokens reserved for future row-height tuning

    # ── Lazy line expansion (S4: row-level breakdown) ────────────────

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        if item.parent() is not None:
            return
        # Detect placeholder
        if item.childCount() != 1:
            return
        first_child = item.child(0)
        if first_child is None:
            return
        if first_child.data(_COL_EMPLOYEE, Qt.ItemDataRole.UserRole + 2) != "placeholder":
            return
        emp_id = item.data(_COL_EMPLOYEE, Qt.ItemDataRole.UserRole)
        if not isinstance(emp_id, int):
            return
        try:
            detail = self._employee_detail_cache.get(emp_id)
            if detail is None:
                detail = self._registry.payroll_run_service.get_run_employee_detail(
                    self._company_id, emp_id
                )
                self._employee_detail_cache[emp_id] = detail
        except AppError as exc:
            show_error(self, "Payroll run", str(exc))
            return
        except Exception:  # noqa: BLE001
            _log.exception("Failed to load employee detail %s", emp_id)
            return

        # Replace placeholder with line rows.
        item.takeChild(0)
        self._populate_lines(item, detail)

    def _populate_lines(
        self, parent: QTreeWidgetItem, detail: PayrollRunEmployeeDetailDTO,
    ) -> None:
        if not detail.lines:
            empty = QTreeWidgetItem(parent)
            empty.setText(_COL_EMPLOYEE, "No component lines.")
            empty.setDisabled(True)
            return
        for line in detail.lines:
            child = _NumericTreeItem(parent)
            type_label = (line.component_type_code or "").replace("_", " ").title()
            label = f"  {line.component_name}"
            if line.component_code:
                label = f"  [{line.component_code}] {line.component_name}"
            child.setText(_COL_EMPLOYEE, label)
            child.setText(_COL_STATUS, type_label)
            # Component amount goes into either earnings or deductions
            # depending on type, but we keep it simple: amount appears
            # in the Net column for any component.
            self._set_numeric(child, _COL_NET, line.component_amount)

        svc = getattr(self._registry, "payroll_variance_analysis_service", None)
        if svc is None:
            return
        try:
            steps = svc.list_calc_steps(self._company_id, detail.id)
        except Exception:  # noqa: BLE001
            _log.debug("Calculation trace lookup failed", exc_info=True)
            return
        if not steps:
            return
        header = QTreeWidgetItem(parent)
        header.setText(_COL_EMPLOYEE, "Calculation trace")
        header.setDisabled(True)
        for step in steps:
            child = _NumericTreeItem(parent)
            label = f"  #{step.sequence_number} {step.stage_code}"
            if step.component_code:
                label = f"{label} [{step.component_code}]"
            child.setText(_COL_EMPLOYEE, label)
            child.setText(_COL_STATUS, step.formula_code)
            child.setToolTip(_COL_EMPLOYEE, step.input_json or "")
            child.setToolTip(_COL_STATUS, step.output_json or "")
            self._set_numeric(child, _COL_NET, step.amount)

    # ── Actions ───────────────────────────────────────────────────────

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _selected_employee(self) -> PayrollRunEmployeeListItemDTO | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        item = items[0]
        # If a child line is selected, walk up to its top-level employee row.
        while item.parent() is not None:
            item = item.parent()
        emp_id = item.data(_COL_EMPLOYEE, Qt.ItemDataRole.UserRole)
        if not isinstance(emp_id, int):
            return None
        return next((e for e in self._employees if e.id == emp_id), None)

    def _on_tree_selection(self) -> None:
        self._update_action_state()
        self.selection_changed.emit()

    def _update_action_state(self) -> None:
        run = self._run
        emp = self._selected_employee()
        emp_selected = emp is not None
        run_status = run.status_code if run else PayrollRunStatus.DRAFT.value
        can_edit = PayrollRunStateMachine.can_edit_inclusion(run_status)
        # Toggle button label + enablement
        if emp is not None and emp.status_code == "excluded":
            self._toggle_btn.setText("Include…")
        else:
            self._toggle_btn.setText("Exclude…")
        self._toggle_btn.setEnabled(emp_selected and can_edit)
        self._open_btn.setEnabled(emp_selected)
        self._correction_btn.setEnabled(
            emp_selected
            and run is not None
            and run.status_code in (
                PayrollRunStatus.CALCULATED.value,
                PayrollRunStatus.SUBMITTED_FOR_REVIEW.value,
            )
        )

        # Submit-for-review affordance: only meaningful while the run
        # is calculated and not yet submitted.
        self._submit_review_btn.setVisible(
            run_status == PayrollRunStatus.CALCULATED.value
        )
        # Approve / Send Back: visible for submitted_for_review runs.
        is_in_review = run_status == PayrollRunStatus.SUBMITTED_FOR_REVIEW.value
        self._approve_btn.setVisible(is_in_review)
        self._send_back_btn.setVisible(is_in_review)

        # Primary action
        action = PayrollRunStateMachine.primary_action(run_status)
        if action is None:
            self._primary_btn.setText("—")
            self._primary_btn.setEnabled(False)
            self._primary_btn.setToolTip("This run is in a terminal state.")
        else:
            self._primary_btn.setText(action.label)
            self._primary_btn.setEnabled(True)
            self._primary_btn.setProperty(
                "danger", "true" if action.is_destructive else "false"
            )
            self._primary_btn.setToolTip(
                f"Move run to “{PayrollRunStateMachine.status_label(action.target_state)}”."
            )

    def _on_primary(self) -> None:
        if self._run is None:
            return
        action = PayrollRunStateMachine.primary_action(self._run.status_code)
        if action is None:
            return
        target = action.target_state
        if target == PayrollRunStatus.CALCULATED.value:
            self._do_calculate()
        elif target == PayrollRunStatus.APPROVED.value:
            self._do_approve()
        elif target == PayrollRunStatus.POSTED.value:
            self._do_post()
        elif target == PayrollRunStatus.REVERSED.value:
            self._do_reverse()

    def _build_dry_run_estimate(self) -> "PayrollDryRunEstimate":
        """Cheap pre-flight summary used by the calculate-confirm dialog."""
        from seeker_accounting.modules.payroll.services.payroll_dry_run import (
            PayrollDryRunEstimate,
        )

        run = self._run
        assert run is not None  # only called inside _do_calculate

        # Employee count: prefer the loaded list (run already calculated /
        # has employees attached); else fall back to active employees in
        # the period via employee_service.
        employee_count = len(self._employees)
        if employee_count == 0:
            try:
                employees = self._registry.employee_service.list_employees(
                    self._company_id, status_code="active",
                )
                employee_count = len(employees)
            except Exception:  # noqa: BLE001
                employee_count = 0

        # Prior run anchor: most recent posted/approved run with same
        # currency, excluding self.
        prior_gross: Decimal | None = None
        prior_net: Decimal | None = None
        prior_ref: str | None = None
        prior_period: str | None = None
        try:
            runs = self._registry.payroll_run_service.list_runs(self._company_id)
            for r in runs:
                if r.id == run.id:
                    continue
                if r.currency_code != run.currency_code:
                    continue
                if r.status_code not in ("calculated", "approved", "posted"):
                    continue
                prior_gross = r.total_gross_earnings
                prior_net = r.total_net_payable
                prior_ref = r.run_reference
                prior_period = (
                    f"{_MONTHS.get(r.period_month, r.period_month)} {r.period_year}"
                )
                break
        except Exception:  # noqa: BLE001
            _log.debug("Prior-run anchor lookup failed", exc_info=True)

        # Input batch counts.
        approved_batches = 0
        draft_batches = 0
        try:
            batches = self._registry.payroll_input_service.list_batches(
                self._company_id,
                period_year=run.period_year,
                period_month=run.period_month,
            )
            approved_batches = sum(1 for b in batches if b.status_code == "approved")
            draft_batches = sum(1 for b in batches if b.status_code == "draft")
        except Exception:  # noqa: BLE001
            _log.debug("Input batch lookup failed", exc_info=True)

        warnings: list[str] = []
        if employee_count == 0:
            warnings.append(
                "No active employees found for this period — "
                "the run will produce zero rows.",
            )
        if draft_batches:
            warnings.append(
                f"{draft_batches} variable input set(s) are still in draft and "
                "will not be picked up. Submit them first if needed.",
            )

        return PayrollDryRunEstimate(
            run_reference=run.run_reference,
            period_year=run.period_year,
            period_month=run.period_month,
            currency_code=run.currency_code,
            employee_count=employee_count,
            prior_total_gross=prior_gross,
            prior_total_net=prior_net,
            prior_run_reference=prior_ref,
            prior_period_label=prior_period,
            approved_input_batches=approved_batches,
            draft_input_batches=draft_batches,
            warnings=tuple(warnings),
        )

    def _do_calculate(self) -> None:
        run = self._run
        if run is None:
            return
        is_recalc = run.status_code == PayrollRunStatus.CALCULATED.value
        # Lazy import the dialog to keep cockpit module load light.
        from seeker_accounting.modules.payroll.ui.dialogs.calculate_run_confirm_dialog import (
            CalculateRunConfirmDialog,
        )
        from PySide6.QtWidgets import QDialog

        estimate = self._build_dry_run_estimate()
        dlg = CalculateRunConfirmDialog(
            estimate, is_recalc=is_recalc, parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        company_id = self._company_id
        run_id = self._run_id
        task = run_with_progress(
            parent=self,
            title="Payroll Calculation",
            message="Calculating payroll run…",
            worker=lambda: self._registry.payroll_run_service.calculate_run(
                company_id, run_id
            ),
        )
        if task.cancelled:
            return
        if task.error is not None:
            if isinstance(task.error, AppError):
                show_error(self, "Payroll Calculation", str(task.error))
            else:
                _log.warning("Calculate run failed: %s", task.error, exc_info=task.error)
                show_error(
                    self, "Payroll Calculation",
                    "An unexpected error occurred. See application log.",
                )
            return
        show_info(self, "Payroll calculation complete.")
        self.refresh()
        if self._run is not None:
            self.state_changed.emit(self._run_id, self._run.status_code)

    def _do_approve(self) -> None:
        run = self._run
        if run is None:
            return
        from seeker_accounting.modules.payroll.ui.dialogs.run_review_dialogs import (
            ApproveRunDialog,
        )
        from PySide6.QtWidgets import QDialog

        dlg = ApproveRunDialog(run.run_reference, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._registry.payroll_run_service.approve_run(
                self._company_id, self._run_id,
                reviewer_note=dlg.note,
            )
        except AppError as exc:
            show_error(self, "Payroll run", str(exc))
            return
        except Exception:  # noqa: BLE001
            _log.exception("Approve run failed")
            show_error(
                self, "Payroll run",
                "An unexpected error occurred. See application log.",
            )
            return
        self.refresh()
        if self._run is not None:
            self.state_changed.emit(self._run_id, self._run.status_code)

    def _on_submit_for_review(self) -> None:
        run = self._run
        if run is None or run.status_code != PayrollRunStatus.CALCULATED.value:
            return
        from seeker_accounting.modules.payroll.ui.dialogs.run_review_dialogs import (
            SubmitForReviewDialog,
        )
        from PySide6.QtWidgets import QDialog

        dlg = SubmitForReviewDialog(run.run_reference, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        service = self._registry.payroll_run_service
        try:
            service.submit_run_for_review(
                self._company_id, self._run_id,
                preparer_note=dlg.note,
            )
        except AppError as exc:
            show_error(self, "Payroll run", str(exc))
            return
        except Exception:  # noqa: BLE001
            _log.exception("Submit for review failed")
            show_error(
                self, "Payroll run",
                "An unexpected error occurred. See application log.",
            )
            return
        show_info(
            self,
            "Run submitted for review. The approver can now approve or send it back.",
        )
        self.refresh()

    def _on_approve(self) -> None:
        """Approve a run that is in 'submitted_for_review' state."""
        run = self._run
        if run is None or run.status_code != PayrollRunStatus.SUBMITTED_FOR_REVIEW.value:
            return
        reply = QMessageBox.question(
            self,
            "Approve payroll run",
            f"Approve run '{run.run_reference}'?\n\n"
            "Once approved the run cannot be recalculated.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        service = self._registry.payroll_run_service
        try:
            service.approve_run(self._company_id, self._run_id)
        except AppError as exc:
            show_error(self, "Approve payroll run", str(exc))
            return
        except Exception:  # noqa: BLE001
            _log.exception("Approve run failed")
            show_error(self, "Approve payroll run", "An unexpected error occurred. See application log.")
            return
        show_info(self, "Payroll run approved.")
        self.refresh()

    def _on_send_back(self) -> None:
        """Send a submitted run back to the preparer with a reason."""
        run = self._run
        if run is None or run.status_code != PayrollRunStatus.SUBMITTED_FOR_REVIEW.value:
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextEdit

        class _SendBackDialog(QDialog):
            def __init__(self, run_ref: str, parent: QWidget | None = None) -> None:
                super().__init__(parent)
                self.setWindowTitle("Send Back for Revision")
                self.setMinimumWidth(DEFAULT_TOKENS.sizes.dialog_min_w_medium)
                lay = QVBoxLayout(self)
                lay.addWidget(QLabel(f"Send back run '{run_ref}' to the preparer?\n\nReason (required):"))
                self._reason = QPlainTextEdit()
                self._reason.setFixedHeight(DEFAULT_TOKENS.sizes.form_textarea_h_medium)
                lay.addWidget(self._reason)
                btns = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                )
                btns.accepted.connect(self._check_accept)
                btns.rejected.connect(self.reject)
                lay.addWidget(btns)

            def _check_accept(self) -> None:
                if not self._reason.toPlainText().strip():
                    show_error(self, "Send Back", "A reason is required.")
                    return
                self.accept()

            @property
            def reason(self) -> str:
                return self._reason.toPlainText().strip()

        dlg = _SendBackDialog(run.run_reference, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        service = self._registry.payroll_run_service
        try:
            service.send_back_run(
                self._company_id, self._run_id,
                reason=dlg.reason,
            )
        except AppError as exc:
            show_error(self, "Send Back", str(exc))
            return
        except Exception:  # noqa: BLE001
            _log.exception("Send back run failed")
            show_error(self, "Send Back", "An unexpected error occurred. See application log.")
            return
        show_info(self, "Run sent back to preparer.")
        self.refresh()

    def _on_open_remittance_editor(self) -> None:
        run = self._run
        if run is None:
            return
        rows = self._remit_table.selected_rows()
        if not rows:
            return
        auth_item = self._remit_model.item(rows[0], 0)
        if auth_item is None:
            return
        authority_id = auth_item.data(Qt.ItemDataRole.UserRole)
        authority_code = auth_item.data(Qt.ItemDataRole.UserRole + 1)
        try:
            from seeker_accounting.modules.payroll.ui.dialogs.remittance_editor_dialog import (
                RemittanceEditorDialog,
            )
            RemittanceEditorDialog.run(
                self._registry,
                company_id=self._company_id,
                authority_id=authority_id,
                authority_code=authority_code,
                period_year=run.period_year,
                period_month=run.period_month,
                parent=self,
            )
        except Exception:  # noqa: BLE001
            _log.exception("Failed to open remittance editor")
            show_error(self, "Remittance", "Could not open the remittance editor.")

    def _do_post(self) -> None:
        # P6.S2: switch to the posting rail tab and enable the validate
        # flow instead of launching a separate modal.
        self._rail_tabs.setCurrentIndex(_TAB_POSTING)
        self._render_posting_pane()
        # Trigger validation automatically when switching so the user
        # gets immediate feedback.
        if self._run is not None and self._run.status_code == "approved":
            self._on_posting_validate()

    def _do_reverse(self) -> None:
        run = self._run
        if run is None:
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        from seeker_accounting.modules.payroll.dto.payroll_posting_dto import (
            ReversePayrollRunCommand,
        )

        class _ReverseDialog(QDialog):
            def __init__(self, run_ref: str, parent: QWidget | None = None) -> None:
                super().__init__(parent)
                self.setWindowTitle("Reverse payroll run")
                self.setMinimumWidth(DEFAULT_TOKENS.sizes.dialog_min_w_medium)
                layout = QVBoxLayout(self)
                layout.addWidget(QLabel(f"Reverse posted run '{run_ref}' with a counter-journal?"))
                row = QHBoxLayout()
                row.addWidget(QLabel("Reversal date:"))
                self.date_edit = QDateEdit()
                self.date_edit.setCalendarPopup(True)
                self.date_edit.setDisplayFormat("yyyy-MM-dd")
                today = _date.today()
                self.date_edit.setDate(QDate(today.year, today.month, today.day))
                row.addWidget(self.date_edit)
                row.addStretch(1)
                layout.addLayout(row)
                layout.addWidget(QLabel("Reason (required):"))
                self.reason = QPlainTextEdit()
                self.reason.setMaximumHeight(DEFAULT_TOKENS.sizes.form_textarea_h_medium)
                layout.addWidget(self.reason)
                buttons = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok
                    | QDialogButtonBox.StandardButton.Cancel
                )
                buttons.accepted.connect(self._accept_if_valid)
                buttons.rejected.connect(self.reject)
                layout.addWidget(buttons)

            def _accept_if_valid(self) -> None:
                if not self.reason.toPlainText().strip():
                    show_error(self, "Reverse Run", "A reason is required.")
                    return
                self.accept()

        dlg = _ReverseDialog(run.run_reference, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        qd = dlg.date_edit.date()
        try:
            self._registry.payroll_posting_service.reverse_run(
                self._company_id,
                ReversePayrollRunCommand(
                    run_id=run.id,
                    reversal_date=_date(qd.year(), qd.month(), qd.day()),
                    reason=dlg.reason.toPlainText().strip(),
                ),
            )
        except AppError as exc:
            show_error(self, "Reverse Run", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            _log.exception("Reverse run failed")
            show_error(self, "Reverse Run", str(exc))
            return
        show_info(self, "Payroll run reversed.")
        self.refresh()
        if self._run is not None:
            self.state_changed.emit(self._run_id, self._run.status_code)

    def _on_queue_correction(self) -> None:
        run = self._run
        emp = self._selected_employee()
        if run is None or emp is None:
            return
        from PySide6.QtWidgets import QDialog
        from seeker_accounting.modules.payroll.ui.dialogs.payroll_correction_dialog import (
            PayrollCorrectionDialog,
        )

        dlg = PayrollCorrectionDialog(
            self._registry,
            self._company_id,
            employee_id=emp.employee_id,
            employee_label=emp.employee_display_name or f"Employee #{emp.employee_id}",
            period_year=run.period_year,
            period_month=run.period_month,
            source_run_id=run.id,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            show_info(self, "Correction queued for the next eligible calculation.")

    def _on_void(self) -> None:
        run = self._run
        if run is None:
            return
        if not PayrollRunStateMachine.can_void(run.status_code):
            return
        if QMessageBox.question(
            self, "Void Run",
            f"Void run {run.run_reference}?\n\nThis cannot be undone.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_run_service.void_run(
                self._company_id, self._run_id
            )
        except AppError as exc:
            show_error(self, "Payroll run", str(exc))
            return
        except Exception:  # noqa: BLE001
            _log.exception("Void run failed")
            show_error(
                self, "Payroll run",
                "An unexpected error occurred. See application log.",
            )
            return
        self.refresh()
        if self._run is not None:
            self.state_changed.emit(self._run_id, self._run.status_code)

    def _on_toggle_inclusion(self) -> None:
        emp = self._selected_employee()
        if emp is None or self._run is None:
            return
        if not PayrollRunStateMachine.can_edit_inclusion(self._run.status_code):
            return
        is_excluding = emp.status_code != "excluded"
        reason: str | None = None
        if is_excluding:
            # Lazy import to keep module load time small for non-toggling
            # sessions.
            from seeker_accounting.modules.payroll.ui.dialogs.exclude_employee_dialog import (
                ExcludeEmployeeDialog,
            )
            from PySide6.QtWidgets import QDialog

            dlg = ExcludeEmployeeDialog(
                emp.employee_display_name or f"Employee #{emp.employee_id}",
                existing_reason=emp.exclusion_reason,
                parent=self,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            reason = dlg.stored_reason
            if not reason:
                return
        try:
            self._registry.payroll_run_service.set_run_employee_inclusion(
                self._company_id,
                emp.id,
                is_included=not is_excluding,
                exclusion_reason=reason,
            )
        except AppError as exc:
            show_error(self, "Payroll run", str(exc))
            return
        except Exception:  # noqa: BLE001
            _log.exception("Toggle inclusion failed")
            show_error(
                self, "Payroll run",
                "An unexpected error occurred. See application log.",
            )
            return
        self.refresh()

    def _on_open_employee(self) -> None:
        emp = self._selected_employee()
        if emp is None:
            return
        self.employee_open_requested.emit(emp.id)

    def _on_item_double_clicked(
        self, item: QTreeWidgetItem, _column: int,
    ) -> None:
        if item.parent() is not None:
            return
        emp_id = item.data(_COL_EMPLOYEE, Qt.ItemDataRole.UserRole)
        if isinstance(emp_id, int):
            self.employee_open_requested.emit(emp_id)

    # ── Public state for ribbon hosts (used by the child window) ──────

    def can_calculate(self) -> bool:
        return bool(self._run) and PayrollRunStateMachine.can_calculate(self._run.status_code)

    def can_approve(self) -> bool:
        return bool(self._run) and PayrollRunStateMachine.can_approve(self._run.status_code)

    def can_void(self) -> bool:
        return bool(self._run) and PayrollRunStateMachine.can_void(self._run.status_code)

    def selected_run_employee_id(self) -> int | None:
        emp = self._selected_employee()
        return emp.id if emp else None

    def trigger_calculate(self) -> None:
        self._do_calculate()

    def trigger_approve(self) -> None:
        self._do_approve()

    def trigger_void(self) -> None:
        self._on_void()


__all__ = ["PayrollRunCockpit"]
