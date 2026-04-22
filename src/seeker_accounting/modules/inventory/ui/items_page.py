from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.inventory.dto.item_dto import ItemListItemDTO
from seeker_accounting.modules.inventory.ui.item_dialog import ItemDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class ItemsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._items: list[ItemListItemDTO] = []

        self.setObjectName("ItemsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_items()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_items(self, selected_item_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._items = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            type_filter = self._type_filter_value()
            self._items = self._service_registry.item_service.list_items(
                active_company.company_id,
                active_only=self._active_only_filter(),
                item_type_code=type_filter,
            )
        except Exception as exc:
            self._items = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Items", f"Item data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._apply_search_filter()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_item_id)
        self._update_action_state()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        layout.addStretch(1)

        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search items...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(lambda _text: self._apply_search_filter())
        layout.addWidget(self._search_input)

        self._type_filter_combo = QComboBox(card)
        self._type_filter_combo.addItem("All types", None)
        self._type_filter_combo.addItem("Stock", "stock")
        self._type_filter_combo.addItem("Non-stock", "non_stock")
        self._type_filter_combo.addItem("Service", "service")
        self._type_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_items())
        layout.addWidget(self._type_filter_combo)

        self._active_filter_combo = QComboBox(card)
        self._active_filter_combo.addItem("Active only", True)
        self._active_filter_combo.addItem("All items", False)
        self._active_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_items())
        layout.addWidget(self._active_filter_combo)

        self._new_button = QPushButton("New Item", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Item", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._deactivate_button = QPushButton("Deactivate", card)
        self._deactivate_button.setProperty("variant", "secondary")
        self._deactivate_button.clicked.connect(self._deactivate_selected_item)
        layout.addWidget(self._deactivate_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_items())
        layout.addWidget(self._refresh_button)
        return card

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
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        top_row = QWidget(card)
        top_row_layout = QHBoxLayout(top_row)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(12)

        title = QLabel("Item Register", top_row)
        title.setObjectName("CardTitle")
        top_row_layout.addWidget(title)
        top_row_layout.addStretch(1)

        self._record_count_label = QLabel(top_row)
        self._record_count_label.setObjectName("ToolbarMeta")
        top_row_layout.addWidget(self._record_count_label)

        layout.addWidget(top_row)

        self._table = QTableWidget(card)
        self._table.setObjectName("ItemsTable")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels((
            "Item Code",
            "Item Name",
            "Type",
            "UoM",
            "Cost Method",
            "Reorder Lvl",
            "Active",
        ))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No items yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create items to use in inventory documents. Stock items track inventory "
            "on hand and require costing configuration.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Item", actions)
        create_button.setProperty("variant", "primary")
        create_button.clicked.connect(self._open_create_dialog)
        actions_layout.addWidget(create_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
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
            "Items are company-scoped. Choose the active company before managing items.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        companies_button = QPushButton("Open Companies", actions)
        companies_button.setProperty("variant", "secondary")
        companies_button.clicked.connect(self._open_companies_workspace)
        actions_layout.addWidget(companies_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _type_filter_value(self) -> str | None:
        value = self._type_filter_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _active_only_filter(self) -> bool:
        value = self._active_filter_combo.currentData()
        return bool(value) if value is not None else True

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._items:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for item in self._items:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (
                item.item_code,
                item.item_name,
                item.item_type_code.replace("_", " ").title(),
                item.unit_of_measure_code,
                (item.inventory_cost_method_code or "").replace("_", " ").title(),
                self._format_qty(item.reorder_level_quantity),
                "Yes" if item.is_active else "No",
            )
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item.id)
                if col in {2, 3, 4, 5, 6}:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, col, cell)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._items)
        self._record_count_label.setText(f"{count} item" if count == 1 else f"{count} items")

    def _apply_search_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        for row in range(self._table.rowCount()):
            if not query:
                self._table.setRowHidden(row, False)
                continue
            match = False
            for col in range(self._table.columnCount()):
                cell = self._table.item(row, col)
                if cell is not None and query in cell.text().lower():
                    match = True
                    break
            self._table.setRowHidden(row, not match)

    def _restore_selection(self, selected_item_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_item_id is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, 0)
            if cell is not None and cell.data(Qt.ItemDataRole.UserRole) == selected_item_id:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    def _selected_item(self) -> ItemListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        cell = self._table.item(current_row, 0)
        if cell is None:
            return None
        item_id = cell.data(Qt.ItemDataRole.UserRole)
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_item()
        has_company = active_company is not None

        self._new_button.setEnabled(has_company)
        self._edit_button.setEnabled(has_company and selected is not None)
        self._deactivate_button.setEnabled(
            has_company and selected is not None and selected.is_active
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Items", "Select an active company before creating items.")
            return
        result = ItemDialog.create_item(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_items(selected_item_id=result.id)

    def _open_edit_dialog(self) -> None:
        active_company = self._active_company()
        selected = self._selected_item()
        if active_company is None or selected is None:
            show_info(self, "Items", "Select an item to edit.")
            return
        result = ItemDialog.edit_item(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            item_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_items(selected_item_id=result.id)

    def _deactivate_selected_item(self) -> None:
        active_company = self._active_company()
        selected = self._selected_item()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Item",
            f"Deactivate item '{selected.item_code}'?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.item_service.deactivate_item(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Items", str(exc))
            self.reload_items(selected_item_id=selected.id)
            return
        self.reload_items()

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_qty(self, value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.4f}".rstrip("0").rstrip(".")

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _handle_item_double_clicked(self, *_args: object) -> None:
        item = self._selected_item()
        if item is None:
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.ITEM_DETAIL,
            context={"item_id": item.id},
        )

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_items()
