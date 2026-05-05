from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
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
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.purchases.dto.purchase_order_dto import PurchaseOrderListItemDTO
from seeker_accounting.modules.purchases.ui.purchase_order_dialog import (
    ConvertOrderDialog,
    PurchaseOrderDialog,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.register import RegisterPage


_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft",
    "sent": "Sent",
    "acknowledged": "Acknowledged",
    "cancelled": "Cancelled",
    "converted": "Converted",
}


ORDER_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="order_number", title="Order #"),
    DataTableColumn(key="order_date", title="Date"),
    DataTableColumn(key="expected_delivery_date", title="Expected Delivery"),
    DataTableColumn(key="supplier_name", title="Supplier"),
    DataTableColumn(key="currency_code", title="Currency"),
    DataTableColumn(key="subtotal_amount", title="Subtotal", is_numeric=True),
    DataTableColumn(key="tax_amount", title="Tax", is_numeric=True),
    DataTableColumn(key="total_amount", title="Total", is_numeric=True),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="bill", title="Bill"),
)
_STATUS_COLUMN_INDEX = 8


_CMD_NEW = "purchase_orders.new"
_CMD_EDIT = "purchase_orders.edit"
_CMD_CANCEL = "purchase_orders.cancel"
_CMD_SEND = "purchase_orders.send"
_CMD_ACKNOWLEDGE = "purchase_orders.acknowledge"
_CMD_CONVERT = "purchase_orders.convert"
_CMD_REFRESH = "purchase_orders.refresh"
_CMD_PRINT = "purchase_orders.print"
_CMD_EXPORT_LIST = "purchase_orders.export_list"


class PurchaseOrdersPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._orders: list[PurchaseOrderListItemDTO] = []
        self._command_enabled: dict[str, bool] = {
            _CMD_NEW: False,
            _CMD_EDIT: False,
            _CMD_CANCEL: False,
            _CMD_SEND: False,
            _CMD_ACKNOWLEDGE: False,
            _CMD_CONVERT: False,
            _CMD_REFRESH: True,
            _CMD_PRINT: False,
            _CMD_EXPORT_LIST: False,
        }

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(self._apply_search_filter)

        self.setObjectName("PurchaseOrdersPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        # Action band is owned by the ribbon now; the visible toolbar above
        # carries the legacy buttons. ActionBand stays hidden for visual
        # consistency with other migrated registers.
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_orders()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_orders(self, selected_order_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._orders = []
            self._orders_model.removeRows(0, self._orders_model.rowCount())
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._orders = self._service_registry.purchase_order_service.list_orders(
                active_company.company_id,
                status_code=self._status_filter_value(),
            )
        except Exception as exc:
            self._orders = []
            self._orders_model.removeRows(0, self._orders_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Purchase Orders", f"Order data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._apply_search_filter()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_order_id)
        self._update_action_state()

    def _handle_search_text_changed(self, _text: str) -> None:
        self._search_debounce.start()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        title = QLabel("Purchase Order Register", register.toolbar_strip)
        title.setObjectName("ToolbarTitle")
        strip_layout.addWidget(title)

        self._search_input = QLineEdit(register.toolbar_strip)
        self._search_input.setPlaceholderText("Search orders…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        strip_layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Sent", "sent")
        self._status_filter_combo.addItem("Acknowledged", "acknowledged")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.addItem("Converted", "converted")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_orders())
        strip_layout.addWidget(self._status_filter_combo)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._new_button = QPushButton("New Order", register.toolbar_strip)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        strip_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", register.toolbar_strip)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        strip_layout.addWidget(self._edit_button)

        self._send_button = QPushButton("Send Order", register.toolbar_strip)
        self._send_button.setProperty("variant", "secondary")
        self._send_button.clicked.connect(self._send_selected_order)
        strip_layout.addWidget(self._send_button)

        self._acknowledge_button = QPushButton("Acknowledge", register.toolbar_strip)
        self._acknowledge_button.setProperty("variant", "secondary")
        self._acknowledge_button.clicked.connect(self._acknowledge_selected_order)
        strip_layout.addWidget(self._acknowledge_button)

        self._convert_button = QPushButton("Convert to Bill", register.toolbar_strip)
        self._convert_button.setProperty("variant", "secondary")
        self._convert_button.clicked.connect(self._convert_selected_order)
        strip_layout.addWidget(self._convert_button)

        self._cancel_button = QPushButton("Cancel Order", register.toolbar_strip)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_order)
        strip_layout.addWidget(self._cancel_button)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_orders())
        strip_layout.addWidget(self._refresh_button)

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
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._orders_model = QStandardItemModel(0, len(ORDER_COLUMNS), self)
        self._orders_model.setHorizontalHeaderLabels([c.title for c in ORDER_COLUMNS])

        self._table = DataTable(
            columns=ORDER_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No orders match the current filters.",
            parent=container,
        )
        self._table.set_model(self._orders_model)
        self._orders_status_delegate = apply_status_chip_to_column(
            self._table.view(), _STATUS_COLUMN_INDEX
        )
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        layout.addWidget(self._table, 1)
        return container

    @staticmethod
    def _make_item(text: str, *, user_data=None) -> QStandardItem:
        item = QStandardItem(text or "")
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

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No purchase orders yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create a draft order, add line items, then send it to the supplier. "
            "Once acknowledged, convert it to a purchase bill with a single action.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Order", actions)
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
            "Purchase orders are company-scoped. Choose the active company before creating or sending orders.",
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

    def _status_filter_value(self) -> str | None:
        value = self._status_filter_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._orders:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._orders_model.removeRows(0, self._orders_model.rowCount())
        for order in self._orders:
            row_items = [
                self._make_item(order.order_number, user_data=order.id),
                self._make_item(self._format_date(order.order_date)),
                self._make_item(
                    self._format_date(order.expected_delivery_date)
                    if order.expected_delivery_date
                    else "—"
                ),
                self._make_item(order.supplier_name),
                self._make_item(order.currency_code),
                self._make_numeric(order.subtotal_amount),
                self._make_numeric(order.tax_amount),
                self._make_numeric(order.total_amount),
                self._make_item(order.status_code or ""),
                self._make_item("✓" if order.converted_to_bill_id else ""),
            ]
            self._orders_model.appendRow(row_items)

        count = len(self._orders)
        self._record_count_label.setText(f"{count} order" if count == 1 else f"{count} orders")

    def _apply_search_filter(self) -> None:
        proxy = self._table.view().model()
        if proxy is None:
            return
        query = self._search_input.text().strip()
        setter = getattr(proxy, "set_search_text", None)
        if callable(setter):
            setter(query)

    def _restore_selection(self, selected_order_id: int | None) -> None:
        if not self._orders:
            return
        if selected_order_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, o in enumerate(self._orders) if o.id == selected_order_id),
                -1,
            )
        if target_idx < 0:
            target_idx = 0
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._orders_model.index(target_idx, 0)
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

    def _selected_order(self) -> PurchaseOrderListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._orders):
            return self._orders[idx]
        return None

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        selected = self._selected_order()
        if selected is None:
            return
        if selected.status_code == "draft":
            self._open_edit_dialog()

    def _set_command_enabled(self, command_id: str, enabled: bool) -> None:
        self._command_enabled[command_id] = bool(enabled)

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_order()
        has_company = active_company is not None
        perm = self._service_registry.permission_service

        status = selected.status_code if selected else ""

        new_enabled = has_company and perm.has_permission("purchases.orders.create")
        edit_enabled = (
            has_company and selected is not None and status == "draft"
            and perm.has_permission("purchases.orders.edit")
        )
        send_enabled = (
            has_company and selected is not None and status == "draft"
            and perm.has_permission("purchases.orders.send")
        )
        acknowledge_enabled = (
            has_company and selected is not None and status == "sent"
            and perm.has_permission("purchases.orders.acknowledge")
        )
        convert_enabled = (
            has_company and selected is not None and status == "acknowledged"
            and perm.has_permission("purchases.orders.convert")
            and perm.has_permission("purchases.bills.create")
        )
        cancel_enabled = (
            has_company and selected is not None and status in {"draft", "sent"}
            and perm.has_permission("purchases.orders.cancel")
        )
        print_enabled = has_company and selected is not None
        export_enabled = has_company and bool(self._orders)

        self._new_button.setEnabled(new_enabled)
        self._edit_button.setEnabled(edit_enabled)
        self._send_button.setEnabled(send_enabled)
        self._acknowledge_button.setEnabled(acknowledge_enabled)
        self._convert_button.setEnabled(convert_enabled)
        self._cancel_button.setEnabled(cancel_enabled)

        self._set_command_enabled(_CMD_NEW, new_enabled)
        self._set_command_enabled(_CMD_EDIT, edit_enabled)
        self._set_command_enabled(_CMD_CANCEL, cancel_enabled)
        self._set_command_enabled(_CMD_SEND, send_enabled)
        self._set_command_enabled(_CMD_ACKNOWLEDGE, acknowledge_enabled)
        self._set_command_enabled(_CMD_CONVERT, convert_enabled)
        self._set_command_enabled(_CMD_REFRESH, True)
        self._set_command_enabled(_CMD_PRINT, print_enabled)
        self._set_command_enabled(_CMD_EXPORT_LIST, export_enabled)
        self._notify_ribbon_state_changed()

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Purchase Orders",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self):
        return {
            _CMD_NEW: self._open_create_dialog,
            _CMD_EDIT: self._open_edit_dialog,
            _CMD_CANCEL: self._cancel_selected_order,
            _CMD_SEND: self._send_selected_order,
            _CMD_ACKNOWLEDGE: self._acknowledge_selected_order,
            _CMD_CONVERT: self._convert_selected_order,
            _CMD_REFRESH: self.reload_orders,
        }

    def ribbon_state(self):
        return dict(self._command_enabled)

    # ------------------------------------------------------------------
    # Event dispatchers
    # ------------------------------------------------------------------

    def _handle_active_company_changed(self) -> None:
        self.reload_orders()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.orders.create"):
            self._show_permission_denied("purchases.orders.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Purchase Orders", "Select an active company before creating orders.")
            return

        result = PurchaseOrderDialog.create_order(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_orders(selected_order_id=result.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.orders.edit"):
            self._show_permission_denied("purchases.orders.edit")
            return
        active_company = self._active_company()
        selected = self._selected_order()
        if active_company is None or selected is None:
            show_info(self, "Purchase Orders", "Select a draft order to edit.")
            return
        if selected.status_code != "draft":
            show_info(self, "Purchase Orders", "Only draft orders can be edited.")
            return

        result = PurchaseOrderDialog.edit_order(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            order_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_orders(selected_order_id=result.id)

    def _send_selected_order(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.orders.send"):
            self._show_permission_denied("purchases.orders.send")
            return
        active_company = self._active_company()
        selected = self._selected_order()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Send Order",
            f"Send order {selected.order_number} to the supplier?\n\n"
            "The order will be finalised and can no longer be edited.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.purchase_order_service.send_order(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Purchase Orders", str(exc))
        self.reload_orders(selected_order_id=selected.id)

    def _acknowledge_selected_order(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.orders.acknowledge"):
            self._show_permission_denied("purchases.orders.acknowledge")
            return
        active_company = self._active_company()
        selected = self._selected_order()
        if active_company is None or selected is None:
            return

        try:
            self._service_registry.purchase_order_service.acknowledge_order(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Purchase Orders", str(exc))
        self.reload_orders(selected_order_id=selected.id)

    def _convert_selected_order(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.orders.convert"):
            self._show_permission_denied("purchases.orders.convert")
            return
        if not self._service_registry.permission_service.has_permission("purchases.bills.create"):
            self._show_permission_denied("purchases.bills.create")
            return
        active_company = self._active_company()
        selected = self._selected_order()
        if active_company is None or selected is None:
            return

        cmd = ConvertOrderDialog.run_conversion(
            order_number=selected.order_number,
            parent=self,
        )
        if cmd is None:
            return

        try:
            result = self._service_registry.purchase_order_service.convert_to_bill(
                active_company.company_id, selected.id, cmd
            )
            show_info(
                self,
                "Order Converted",
                f"Order {result.order_number} was converted to bill {result.purchase_bill_id}.\n\n"
                "The new bill is in draft state. Navigate to Purchase Bills to post it.",
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            show_error(self, "Purchase Orders", str(exc))
        self.reload_orders(selected_order_id=selected.id)

    def _cancel_selected_order(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.orders.cancel"):
            self._show_permission_denied("purchases.orders.cancel")
            return
        active_company = self._active_company()
        selected = self._selected_order()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Cancel Order",
            f"Cancel order {selected.order_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.purchase_order_service.cancel_order(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Purchase Orders", str(exc))
        self.reload_orders()

    def _open_companies_workspace(self) -> None:
        try:
            self._service_registry.navigation_service.navigate(nav_ids.ORGANISATION_SETTINGS)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    @staticmethod
    def _format_date(value: date | None) -> str:
        if value is None:
            return ""
        return value.strftime("%d/%m/%Y")

    @staticmethod
    def _format_amount(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.2f}"
