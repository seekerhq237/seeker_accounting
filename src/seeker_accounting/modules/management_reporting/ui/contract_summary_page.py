"""Contract Summary page.

A read-only reporting surface that shows a selected contract's financial
summary, optional cost trend sparkline, and a project rollup table.
Consumes ContractReportingService and BudgetReportingService.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.management_reporting.dto.contract_summary_dto import (
    ContractProjectRollupItemDTO,
    ContractSummaryDTO,
)
from seeker_accounting.modules.management_reporting.ui.variance_chart_widgets import (
    MiniSparkline,
    TrendLineChart,
    TrendPoint,
)
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.message_boxes import show_error

_ZERO = Decimal(0)


def _fmt(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}"


def _fmt_pct(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.1f}%"


# ======================================================================
# Contract Summary Page
# ======================================================================


class ContractSummaryPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._summary: ContractSummaryDTO | None = None

        self.setObjectName("ContractSummaryPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._on_company_changed
        )
        self._service_registry.navigation_service.navigation_context_changed.connect(
            self._on_navigation_context_changed
        )

        self._load_contracts()

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel('Linked Project Rollup', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._rollup_count = QLabel(card)
        self._rollup_count.setObjectName("ToolbarMeta")
        layout.addWidget(self._rollup_count)

        layout.addStretch(1)
        # Contract selector
        ct_block = QWidget(card)
        ct_layout = QVBoxLayout(ct_block)
        ct_layout.setContentsMargins(0, 0, 0, 0)
        ct_layout.setSpacing(2)

        ct_caption = QLabel("Contract", ct_block)
        ct_caption.setProperty("role", "caption")
        ct_layout.addWidget(ct_caption)

        self._contract_combo = QComboBox(ct_block)
        self._contract_combo.setMinimumWidth(280)
        self._contract_combo.currentIndexChanged.connect(self._on_contract_changed)
        ct_layout.addWidget(self._contract_combo)

        layout.addWidget(ct_block)
        layout.addStretch(1)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self._reload)
        layout.addWidget(self._refresh_button)

        return card

    # ------------------------------------------------------------------
    # Content stack
    # ------------------------------------------------------------------

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._detail_surface = self._build_detail_surface()
        self._empty_state = build_empty_state("management_reporting.contract_summary.no_selection", parent=self)
        self._no_company_state = build_empty_state("management_reporting.no_company", parent=self)
        self._stack.addWidget(self._detail_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_company_state)
        return self._stack

    # ------------------------------------------------------------------
    # Detail surface (scrollable)
    # ------------------------------------------------------------------

    def _build_detail_surface(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_contract_header_card(content))
        layout.addWidget(self._build_rollup_table(content))

        scroll.setWidget(content)
        return scroll

    # ------------------------------------------------------------------
    # Contract header card
    # ------------------------------------------------------------------

    def _build_contract_header_card(self, parent: QWidget) -> QWidget:
        card = QFrame(parent)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        t = QLabel("Contract Financial Summary", card)
        t.setObjectName("CardTitle")
        layout.addWidget(t)

        self._header_labels: dict[str, QLabel] = {}

        # Row 1: contract identity
        row1 = QWidget(card)
        r1_layout = QHBoxLayout(row1)
        r1_layout.setContentsMargins(0, 0, 0, 0)
        r1_layout.setSpacing(16)

        for label_text, key in [
            ("Contract #", "number"),
            ("Title", "title"),
            ("Status", "status"),
            ("Type", "type"),
            ("Currency", "currency"),
        ]:
            block = self._metric_block(row1, label_text, key)
            r1_layout.addWidget(block, 1)
        layout.addWidget(row1)

        # Row 2: amounts
        row2 = QWidget(card)
        r2_layout = QHBoxLayout(row2)
        r2_layout.setContentsMargins(0, 0, 0, 0)
        r2_layout.setSpacing(16)

        for label_text, key in [
            ("Base Amount", "base_amount"),
            ("Change Orders", "change_orders"),
            ("Current Amount", "current_amount"),
        ]:
            block = self._metric_block(row2, label_text, key)
            r2_layout.addWidget(block, 1)
        layout.addWidget(row2)

        # Row 3: cross-project totals
        row3 = QWidget(card)
        r3_layout = QHBoxLayout(row3)
        r3_layout.setContentsMargins(0, 0, 0, 0)
        r3_layout.setSpacing(16)

        for label_text, key in [
            ("Revenue", "total_revenue"),
            ("Actual Cost", "total_cost"),
            ("Commitments", "total_commit"),
            ("Budget", "total_budget"),
            ("Margin", "total_margin"),
            ("Margin %", "total_margin_pct"),
        ]:
            block = self._metric_block(row3, label_text, key)
            r3_layout.addWidget(block, 1)
        layout.addWidget(row3)

        return card

    def _metric_block(self, parent: QWidget, label_text: str, key: str) -> QWidget:
        block = QWidget(parent)
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.setSpacing(1)

        caption = QLabel(label_text, block)
        caption.setProperty("role", "caption")
        block_layout.addWidget(caption)

        value = QLabel("—", block)
        value.setObjectName("ToolbarValue")
        block_layout.addWidget(value)

        self._header_labels[key] = value
        return block

    # ------------------------------------------------------------------
    # Rollup table
    # ------------------------------------------------------------------

    def _build_rollup_table(self, parent: QWidget) -> QWidget:
        card = QFrame(parent)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self._rollup_model = QStandardItemModel(0, 9, card)
        self._rollup_model.setHorizontalHeaderLabels([
            "Project", "Revenue", "Actual Cost", "Commitments",
            "Budget", "Exposure", "Remaining", "Margin", "Margin %",
        ])
        self._rollup_table = DataTable(
            columns=(
                DataTableColumn(key="project", title="Project"),
                DataTableColumn(key="revenue", title="Revenue"),
                DataTableColumn(key="actual_cost", title="Actual Cost"),
                DataTableColumn(key="commitments", title="Commitments"),
                DataTableColumn(key="budget", title="Budget"),
                DataTableColumn(key="exposure", title="Exposure"),
                DataTableColumn(key="remaining", title="Remaining"),
                DataTableColumn(key="margin", title="Margin"),
                DataTableColumn(key="margin_pct", title="Margin %"),
            ),
            show_search=False,
            parent=card,
        )
        self._rollup_table.set_model(self._rollup_model)
        layout.addWidget(self._rollup_table)
        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _load_contracts(self) -> None:
        self._contract_combo.blockSignals(True)
        self._contract_combo.clear()

        active = self._active_company()
        if active is None:
            self._contract_combo.blockSignals(False)
            self._stack.setCurrentWidget(self._no_company_state)
            return

        try:
            contracts = self._service_registry.contract_service.list_contracts(active.company_id)
        except Exception as exc:
            self._contract_combo.blockSignals(False)
            self._stack.setCurrentWidget(self._empty_state)
            show_error(self, "Contracts", f"Could not load contracts.\n\n{exc}")
            return

        if not contracts:
            self._contract_combo.addItem("No contracts available", None)
            self._contract_combo.blockSignals(False)
            self._stack.setCurrentWidget(self._empty_state)
            return

        for c in contracts:
            self._contract_combo.addItem(
                f"{c.contract_number} — {c.contract_title}",
                c.id,
            )

        self._contract_combo.blockSignals(False)
        self._apply_navigation_context()
        self._on_contract_changed()

    def _reload(self) -> None:
        self._on_contract_changed()

    def _on_company_changed(self) -> None:
        self._load_contracts()

    def _on_navigation_context_changed(self, nav_id: str, context: object) -> None:
        _ = context
        if nav_id != nav_ids.CONTRACT_SUMMARY:
            return
        self._apply_navigation_context()

    def _apply_navigation_context(self) -> None:
        context = self._service_registry.navigation_service.current_navigation_context
        contract_id = context.get("contract_id")
        if not isinstance(contract_id, int):
            return
        for index in range(self._contract_combo.count()):
            if self._contract_combo.itemData(index) == contract_id:
                self._contract_combo.setCurrentIndex(index)
                return

    def _on_contract_changed(self) -> None:
        contract_id = self._contract_combo.currentData()
        if contract_id is None:
            self._clear()
            self._stack.setCurrentWidget(self._empty_state)
            return

        active = self._active_company()
        if active is None:
            return

        try:
            self._summary = self._service_registry.contract_reporting_service.get_contract_summary(
                active.company_id, contract_id
            )
        except NotFoundError:
            self._clear()
            self._stack.setCurrentWidget(self._empty_state)
            return
        except Exception as exc:
            self._clear()
            show_error(self, "Contract Summary", f"Could not load summary.\n\n{exc}")
            return

        self._populate_header()
        self._populate_rollup()
        self._stack.setCurrentWidget(self._detail_surface)

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------

    def _populate_header(self) -> None:
        s = self._summary
        if s is None:
            return

        palette = self._service_registry.theme_manager.current_palette
        h = self._header_labels

        h["number"].setText(s.contract_number)
        h["title"].setText(s.contract_title)
        h["status"].setText(s.status_code.replace("_", " ").title())
        h["type"].setText(s.contract_type_code.replace("_", " ").title())
        h["currency"].setText(s.currency_code)

        h["base_amount"].setText(_fmt(s.base_contract_amount))
        h["change_orders"].setText(_fmt(s.approved_change_order_delta_total))
        h["current_amount"].setText(_fmt(s.current_contract_amount))

        h["total_revenue"].setText(_fmt(s.total_billed_revenue_amount))
        h["total_cost"].setText(_fmt(s.total_actual_cost_amount))
        h["total_commit"].setText(_fmt(s.total_approved_commitment_amount))
        h["total_budget"].setText(_fmt(s.total_current_budget_amount))

        margin_label = h["total_margin"]
        margin_label.setText(_fmt(s.total_margin_amount))
        if s.total_margin_amount >= 0:
            margin_label.setStyleSheet(f"color: {palette.success};")
        else:
            margin_label.setStyleSheet(f"color: {palette.danger};")

        h["total_margin_pct"].setText(_fmt_pct(s.total_margin_percent))

    @staticmethod
    def _make_item(text: str, *, right_align: bool = False, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if right_align:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_rollup(self) -> None:
        s = self._summary
        if s is None:
            return

        palette = self._service_registry.theme_manager.current_palette
        items = s.project_rollup_items

        self._rollup_model.removeRows(0, self._rollup_model.rowCount())

        for item in items:
            margin_item = self._make_item(_fmt(item.margin_amount), right_align=True)
            if item.margin_amount >= 0:
                margin_item.setForeground(QBrush(QColor(palette.success)))
            else:
                margin_item.setForeground(QBrush(QColor(palette.danger)))

            pct_item = self._make_item(_fmt_pct(item.margin_percent))
            pct_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self._rollup_model.appendRow([
                self._make_item(f"{item.project_code} — {item.project_name}", user_data=item.project_id),
                self._make_item(_fmt(item.billed_revenue_amount), right_align=True),
                self._make_item(_fmt(item.actual_cost_amount), right_align=True),
                self._make_item(_fmt(item.approved_commitment_amount), right_align=True),
                self._make_item(_fmt(item.current_budget_amount), right_align=True),
                self._make_item(_fmt(item.total_exposure_amount), right_align=True),
                self._make_item(_fmt(item.remaining_budget_after_commitments_amount), right_align=True),
                margin_item,
                pct_item,
            ])

        n = len(items)
        self._rollup_count.setText(f"{n} project{'s' if n != 1 else ''}")

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def _clear(self) -> None:
        self._summary = None
        for lbl in self._header_labels.values():
            lbl.setText("—")
            lbl.setStyleSheet("")
        self._rollup_model.removeRows(0, self._rollup_model.rowCount())
        self._rollup_count.setText("")
