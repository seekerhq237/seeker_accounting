from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.inventory.dto.item_dto import ItemListItemDTO
from seeker_accounting.modules.inventory.ui.item_dialog import ItemDialog
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


ITEM_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="item_code", title="Item Code"),
    DataTableColumn(key="item_name", title="Item Name"),
    DataTableColumn(key="type", title="Type"),
    DataTableColumn(key="uom", title="UoM"),
    DataTableColumn(key="cost_method", title="Cost Method"),
    DataTableColumn(key="tracking", title="Tracking"),
    DataTableColumn(key="variant", title="Variant"),
    DataTableColumn(key="reorder_level", title="Reorder Lvl"),
    DataTableColumn(key="active", title="Active"),
)


class ItemsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._items: list[ItemListItemDTO] = []

        self.setObjectName("ItemsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

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
            self._model.removeRows(0, self._model.rowCount())
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
            self._model.removeRows(0, self._model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Items", f"Item data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
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
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel('Item Register', card)
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = QStandardItemModel(0, len(ITEM_COLUMNS), self)
        self._model.setHorizontalHeaderLabels([c.title for c in ITEM_COLUMNS])

        self._table = DataTable(
            columns=ITEM_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No items to display.",
            parent=card,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 8)
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        state = build_empty_state("inventory.items.empty", parent=self)
        state.primary_clicked.connect(self._open_create_dialog)
        return state

    def _build_no_active_company_state(self) -> QWidget:
        state = build_empty_state("inventory.no_company", parent=self)
        state.primary_clicked.connect(self._open_companies_workspace)
        return state

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

        for item in self._items:
            type_label = item.item_type_code.replace("_", " ").title()
            cost_label = (item.inventory_cost_method_code or "").replace("_", " ").title()
            row_items = [
                self._make_item(item.item_code, user_data=item.id),
                self._make_item(item.item_name),
                self._make_item(type_label),
                self._make_item(item.unit_of_measure_code),
                self._make_item(cost_label),
                self._make_item((item.tracking_mode_code or "none").replace("_", " ").title()),
                self._make_item("Variant" if item.is_variant else "Parent" if item.parent_item_id is None else "Child"),
                self._make_numeric(item.reorder_level_quantity),
                self._make_item("active" if item.is_active else "inactive"),
            ]
            self._model.appendRow(row_items)

        count = len(self._items)
        self._record_count_label.setText(f"{count} item" if count == 1 else f"{count} items")

    def _on_search_text_changed(self, text: str) -> None:
        self._table.set_search_text(text)

    def _restore_selection(self, selected_item_id: int | None) -> None:
        if not self._items:
            return
        if selected_item_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, it in enumerate(self._items) if it.id == selected_item_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._table.view().selectionModel()
        if sm is None:
            return
        sm.select(
            proxy_index,
            sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows,
        )
        self._table.view().scrollTo(proxy_index)

    def _selected_item(self) -> ItemListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._items):
            return self._items[idx]
        return None

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        self._handle_item_double_clicked()

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Items",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_item()
        has_company = active_company is not None
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_company and permission_service.has_permission("inventory.items.create")
        )
        self._edit_button.setEnabled(
            has_company
            and selected is not None
            and permission_service.has_permission("inventory.items.edit")
        )
        self._deactivate_button.setEnabled(
            has_company
            and selected is not None
            and selected.is_active
            and permission_service.has_permission("inventory.items.deactivate")
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Items", "Select an active company before creating items.")
            return
        if not self._service_registry.permission_service.has_permission("inventory.items.create"):
            self._show_permission_denied("inventory.items.create")
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
        if not self._service_registry.permission_service.has_permission("inventory.items.edit"):
            self._show_permission_denied("inventory.items.edit")
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
        if not self._service_registry.permission_service.has_permission("inventory.items.deactivate"):
            self._show_permission_denied("inventory.items.deactivate")
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
        except PermissionDeniedError:
            self._show_permission_denied("inventory.items.deactivate")
            return
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
