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
from seeker_accounting.modules.sales.dto.sales_order_dto import SalesOrderListItemDTO
from seeker_accounting.modules.sales.ui.sales_order_dialog import (
    ConvertSalesOrderDialog,
    SalesOrderDialog,
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
    "confirmed": "Confirmed",
    "invoiced": "Invoiced",
    "cancelled": "Cancelled",
}


ORDER_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="order_number", title="Order #"),
    DataTableColumn(key="order_date", title="Date"),
    DataTableColumn(key="requested_delivery_date", title="Req. Delivery"),
    DataTableColumn(key="customer_name", title="Customer"),
    DataTableColumn(key="currency_code", title="Currency"),
    DataTableColumn(key="subtotal_amount", title="Subtotal", is_numeric=True),
    DataTableColumn(key="tax_amount", title="Tax", is_numeric=True),
    DataTableColumn(key="total_amount", title="Total", is_numeric=True),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="invoice", title="Invoice"),
)
_STATUS_COLUMN_INDEX = 8

_CMD_NEW = "sales_orders.new"
_CMD_EDIT = "sales_orders.edit"
_CMD_CANCEL = "sales_orders.cancel"
_CMD_POST = "sales_orders.post"  # ribbon "post" surface = Confirm Order
_CMD_REFRESH = "sales_orders.refresh"


class SalesOrdersPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._orders: list[SalesOrderListItemDTO] = []
        self._command_enabled: dict[str, bool] = {
            _CMD_NEW: False,
            _CMD_EDIT: False,
            _CMD_CANCEL: False,
            _CMD_POST: False,
            _CMD_REFRESH: True,
        }
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(self._apply_search_filter)

        self.setObjectName("SalesOrdersPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        # Action band is owned by the ribbon now; legacy hidden buttons removed.
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
            self._orders = self._service_registry.sales_order_service.list_orders(
                active_company.company_id,
                status_code=self._status_filter_value(),
            )
        except Exception as exc:
            self._orders = []
            self._orders_model.removeRows(0, self._orders_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Sales Orders", f"Order data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
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

        self._search_input = QLineEdit(register.toolbar_strip)
        self._search_input.setPlaceholderText("Search orders…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        strip_layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Confirmed", "confirmed")
        self._status_filter_combo.addItem("Invoiced", "invoiced")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_orders())
        strip_layout.addWidget(self._status_filter_combo)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_orders())
        strip_layout.addWidget(self._refresh_button)

    def _populate_action_band(self, register: RegisterPage) -> None:
        # Legacy action-band buttons removed; ribbon owns these commands now.
        return

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

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No sales orders yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create a draft order, add line items, then confirm it for the customer. "
            "Once confirmed, convert it to a sales invoice with a single action.",
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
            "Sales orders are company-scoped. Choose the active company before creating or confirming orders.",
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
        query = self._search_input.text().strip().lower()

        shown = 0
        for order in self._orders:
            if query and not self._order_matches_query(order, query):
                continue
            row_items = [
                self._make_item(order.order_number, user_data=order.id),
                self._make_item(self._format_date(order.order_date)),
                self._make_item(
                    self._format_date(order.requested_delivery_date)
                    if order.requested_delivery_date
                    else "—"
                ),
                self._make_item(order.customer_name or ""),
                self._make_item(order.currency_code or ""),
                self._make_numeric(order.subtotal_amount),
                self._make_numeric(order.tax_amount),
                self._make_numeric(order.total_amount),
                self._make_item(order.status_code or ""),
                self._make_item("✓" if order.converted_to_invoice_id else ""),
            ]
            self._orders_model.appendRow(row_items)
            shown += 1

        total = len(self._orders)
        if query:
            self._record_count_label.setText(f"{shown} shown of {total} matches")
        else:
            self._record_count_label.setText(
                f"{total} order" if total == 1 else f"{total} orders"
            )

    @staticmethod
    def _order_matches_query(order: SalesOrderListItemDTO, query: str) -> bool:
        haystack = " ".join(
            [
                order.order_number or "",
                order.customer_name or "",
                order.currency_code or "",
                _STATUS_LABELS.get(order.status_code, order.status_code or "").lower(),
                order.status_code or "",
            ]
        ).lower()
        return query in haystack

    def _apply_search_filter(self) -> None:
        # Re-render the model from the current in-memory list, applying the
        # search filter client-side. Server-side filter is by status only.
        self._populate_table()
        self._update_action_state()

    def _restore_selection(self, selected_order_id: int | None) -> None:
        if self._orders_model.rowCount() == 0:
            return
        if selected_order_id is None:
            target_idx = 0
        else:
            target_idx = -1
            for row in range(self._orders_model.rowCount()):
                index = self._orders_model.index(row, 0)
                if index.data(Qt.ItemDataRole.UserRole) == selected_order_id:
                    target_idx = row
                    break
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

    def _selected_order(self) -> SalesOrderListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if idx < 0 or idx >= self._orders_model.rowCount():
            return None
        order_id = self._orders_model.index(idx, 0).data(Qt.ItemDataRole.UserRole)
        for order in self._orders:
            if order.id == order_id:
                return order
        return None

    @staticmethod
    def _make_item(text: str, *, user_data: object | None = None) -> QStandardItem:
        item = QStandardItem(text or "")
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value: Decimal | None) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _set_command_enabled(self, command_id: str, enabled: bool) -> None:
        self._command_enabled[command_id] = bool(enabled)

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_order()
        has_company = active_company is not None
        perm = self._service_registry.permission_service

        status = selected.status_code if selected else ""
        is_draft = has_company and selected is not None and status == "draft"

        self._set_command_enabled(
            _CMD_NEW,
            has_company and perm.has_permission("sales.orders.create"),
        )
        self._set_command_enabled(
            _CMD_EDIT,
            is_draft and perm.has_permission("sales.orders.edit"),
        )
        self._set_command_enabled(
            _CMD_CANCEL,
            has_company
            and selected is not None
            and status in {"draft", "confirmed"}
            and perm.has_permission("sales.orders.cancel"),
        )
        self._set_command_enabled(
            _CMD_POST,
            is_draft and perm.has_permission("sales.orders.confirm"),
        )
        self._set_command_enabled(_CMD_REFRESH, True)
        self._notify_ribbon_state_changed()

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Sales Orders",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    # ------------------------------------------------------------------
    # IRibbonHost
    # ------------------------------------------------------------------

    def _ribbon_commands(self):
        return {
            _CMD_NEW: self._open_create_dialog,
            _CMD_EDIT: self._open_edit_dialog,
            _CMD_CANCEL: self._cancel_selected_order,
            _CMD_POST: self._confirm_selected_order,
            _CMD_REFRESH: self.reload_orders,
        }

    def ribbon_state(self):
        return dict(self._command_enabled)

    # ------------------------------------------------------------------
    # Event dispatchers
    # ------------------------------------------------------------------

    def _handle_active_company_changed(self, *_args: object) -> None:
        self.reload_orders()

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        # Preserve legacy double-click behaviour: edit when draft is selected.
        selected = self._selected_order()
        if selected is None:
            return
        if selected.status_code == "draft":
            self._open_edit_dialog()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.orders.create"):
            self._show_permission_denied("sales.orders.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Sales Orders", "Select an active company before creating orders.")
            return

        result = SalesOrderDialog.create_order(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_orders(selected_order_id=result.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.orders.edit"):
            self._show_permission_denied("sales.orders.edit")
            return
        active_company = self._active_company()
        selected = self._selected_order()
        if active_company is None or selected is None:
            show_info(self, "Sales Orders", "Select a draft order to edit.")
            return
        if selected.status_code != "draft":
            show_info(self, "Sales Orders", "Only draft orders can be edited.")
            return

        result = SalesOrderDialog.edit_order(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            order_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_orders(selected_order_id=result.id)

    def _confirm_selected_order(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.orders.confirm"):
            self._show_permission_denied("sales.orders.confirm")
            return
        active_company = self._active_company()
        selected = self._selected_order()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Confirm Order",
            f"Confirm order {selected.order_number} for the customer?\n\n"
            "The order will be finalised and can no longer be edited.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.sales_order_service.confirm_order(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Sales Orders", str(exc))
        self.reload_orders(selected_order_id=selected.id)

    def _convert_selected_order(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.orders.convert"):
            self._show_permission_denied("sales.orders.convert")
            return
        if not self._service_registry.permission_service.has_permission("sales.invoices.create"):
            self._show_permission_denied("sales.invoices.create")
            return
        active_company = self._active_company()
        selected = self._selected_order()
        if active_company is None or selected is None:
            return

        cmd = ConvertSalesOrderDialog.run_conversion(
            order_number=selected.order_number,
            parent=self,
        )
        if cmd is None:
            return

        try:
            result = self._service_registry.sales_order_service.convert_to_invoice(
                active_company.company_id, selected.id, cmd
            )
            show_info(
                self,
                "Order Converted",
                f"Order {result.order_number} was converted to invoice {result.invoice_id}.\n\n"
                "The new invoice is in draft state. Navigate to Sales Invoices to post it.",
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            show_error(self, "Sales Orders", str(exc))
        self.reload_orders(selected_order_id=selected.id)

    def _cancel_selected_order(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.orders.cancel"):
            self._show_permission_denied("sales.orders.cancel")
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
            self._service_registry.sales_order_service.cancel_order(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Sales Orders", str(exc))
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
