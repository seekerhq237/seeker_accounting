from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.inventory.dto.inventory_valuation_dto import (
    InventoryStockPositionDTO,
    InventoryValuationSummaryDTO,
)
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error


STOCK_POSITION_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="item_code", title="Item Code"),
    DataTableColumn(key="item_name", title="Item Name"),
    DataTableColumn(key="uom", title="UoM"),
    DataTableColumn(key="qty_on_hand", title="Qty on Hand"),
    DataTableColumn(key="avg_cost", title="Avg Cost"),
    DataTableColumn(key="total_value", title="Total Value"),
    DataTableColumn(key="reorder_level", title="Reorder Lvl"),
    DataTableColumn(key="low_stock", title="Low Stock"),
)


class InventoryStockView(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._positions: list[InventoryStockPositionDTO] = []
        self._summary: InventoryValuationSummaryDTO | None = None

        self.setObjectName("InventoryStockView")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_summary_panel())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_stock()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_stock(self) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._positions = []
            self._summary = None
            self._model.removeRows(0, self._model.rowCount())
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_summary_display()
            return

        low_only = self._low_stock_checkbox.isChecked()

        try:
            self._positions = self._service_registry.inventory_valuation_service.list_stock_positions(
                active_company.company_id, low_stock_only=low_only
            )
            self._summary = self._service_registry.inventory_valuation_service.get_inventory_valuation_summary(
                active_company.company_id
            )
        except Exception as exc:
            self._positions = []
            self._summary = None
            self._model.removeRows(0, self._model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_summary_display()
            show_error(self, "Stock Position", f"Stock data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._update_summary_display()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel('Stock Positions', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)
        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search items...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self._search_input)

        self._low_stock_checkbox = QCheckBox("Low stock only", card)
        self._low_stock_checkbox.stateChanged.connect(lambda _state: self.reload_stock())
        layout.addWidget(self._low_stock_checkbox)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_stock())
        layout.addWidget(self._refresh_button)
        return card

    def _build_summary_panel(self) -> QWidget:
        self._summary_panel = QFrame(self)
        self._summary_panel.setObjectName("InfoCard")

        layout = QHBoxLayout(self._summary_panel)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(24)

        self._total_items_label = QLabel("Items with stock: -", self._summary_panel)
        self._total_items_label.setObjectName("ToolbarValue")
        layout.addWidget(self._total_items_label)

        self._total_qty_label = QLabel("Total quantity: -", self._summary_panel)
        self._total_qty_label.setObjectName("ToolbarValue")
        layout.addWidget(self._total_qty_label)

        self._total_value_label = QLabel("Total value: -", self._summary_panel)
        self._total_value_label.setObjectName("ToolbarValue")
        layout.addWidget(self._total_value_label)

        self._low_stock_label = QLabel("Low stock: -", self._summary_panel)
        self._low_stock_label.setObjectName("ToolbarValue")
        layout.addWidget(self._low_stock_label)

        layout.addStretch(1)
        return self._summary_panel

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_active_company_state = self._build_no_active_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_active_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = QStandardItemModel(0, len(STOCK_POSITION_COLUMNS), self)
        self._model.setHorizontalHeaderLabels([c.title for c in STOCK_POSITION_COLUMNS])

        self._table = DataTable(
            columns=STOCK_POSITION_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No stock positions to display.",
            parent=card,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 7)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No stock positions", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Stock positions appear after posting inventory receipt or adjustment documents. "
            "Create stock items and post receipts to see valuation data here.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addStretch(1)
        return card

    def _build_no_active_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Stock positions are company-scoped. Choose the active company to view inventory valuation.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._positions:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _update_summary_display(self) -> None:
        if self._summary is None:
            self._total_items_label.setText("Items with stock: -")
            self._total_qty_label.setText("Total quantity: -")
            self._total_value_label.setText("Total value: -")
            self._low_stock_label.setText("Low stock: -")
            return
        self._total_items_label.setText(f"Items with stock: {self._summary.total_items_with_stock}")
        self._total_qty_label.setText(f"Total quantity: {self._format_qty(self._summary.total_quantity_on_hand)}")
        self._total_value_label.setText(f"Total value: {self._format_amount(self._summary.total_inventory_value)}")
        self._low_stock_label.setText(f"Low stock: {self._summary.low_stock_item_count}")

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())

        for pos in self._positions:
            row_items = [
                self._make_item(pos.item_code, user_data=pos.item_id),
                self._make_item(pos.item_name),
                self._make_item(pos.unit_of_measure_code),
                self._make_numeric(pos.quantity_on_hand),
                self._make_numeric(pos.weighted_average_cost),
                self._make_numeric(pos.total_value),
                self._make_numeric(pos.reorder_level_quantity),
                self._make_item("low_stock" if pos.is_low_stock else "in_stock"),
            ]
            self._model.appendRow(row_items)

        count = len(self._positions)
        self._record_count_label.setText(f"{count} item" if count == 1 else f"{count} items")

    def _on_search_text_changed(self, text: str) -> None:
        self._table.set_search_text(text)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_qty(self, value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.4f}".rstrip("0").rstrip(".")

    def _format_cost(self, value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.4f}"

    def _format_amount(self, value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.2f}"

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_stock()
