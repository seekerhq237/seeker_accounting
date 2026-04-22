from __future__ import annotations

from datetime import date
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
from seeker_accounting.modules.sales.dto.sales_order_dto import SalesOrderListItemDTO
from seeker_accounting.modules.sales.ui.sales_order_dialog import (
    ConvertSalesOrderDialog,
    SalesOrderDialog,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft",
    "confirmed": "Confirmed",
    "invoiced": "Invoiced",
    "cancelled": "Cancelled",
}


class SalesOrdersPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._orders: list[SalesOrderListItemDTO] = []

        self.setObjectName("SalesOrdersPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

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
            self._table.setRowCount(0)
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
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Sales Orders", f"Order data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._apply_search_filter()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_order_id)
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

        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search orders...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(lambda _text: self._apply_search_filter())
        layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(card)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Confirmed", "confirmed")
        self._status_filter_combo.addItem("Invoiced", "invoiced")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_orders())
        layout.addWidget(self._status_filter_combo)

        self._new_button = QPushButton("New Order", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._confirm_button = QPushButton("Confirm", card)
        self._confirm_button.setProperty("variant", "secondary")
        self._confirm_button.clicked.connect(self._confirm_selected_order)
        layout.addWidget(self._confirm_button)

        self._convert_button = QPushButton("Convert to Invoice", card)
        self._convert_button.setProperty("variant", "secondary")
        self._convert_button.clicked.connect(self._convert_selected_order)
        layout.addWidget(self._convert_button)

        self._cancel_button = QPushButton("Cancel Order", card)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_order)
        layout.addWidget(self._cancel_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_orders())
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

        title = QLabel("Sales Order Register", top_row)
        title.setObjectName("CardTitle")
        top_row_layout.addWidget(title)
        top_row_layout.addStretch(1)

        self._record_count_label = QLabel(top_row)
        self._record_count_label.setObjectName("ToolbarMeta")
        top_row_layout.addWidget(self._record_count_label)

        layout.addWidget(top_row)

        self._table = QTableWidget(card)
        self._table.setObjectName("SalesOrdersTable")
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels((
            "Order #",
            "Date",
            "Req. Delivery",
            "Customer",
            "Currency",
            "Subtotal",
            "Tax",
            "Total",
            "Status",
            "Invoice",
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
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for order in self._orders:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (
                order.order_number,
                self._format_date(order.order_date),
                self._format_date(order.requested_delivery_date) if order.requested_delivery_date else "—",
                order.customer_name,
                order.currency_code,
                self._format_amount(order.subtotal_amount),
                self._format_amount(order.tax_amount),
                self._format_amount(order.total_amount),
                _STATUS_LABELS.get(order.status_code, order.status_code.title()),
                "✓" if order.converted_to_invoice_id else "",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, order.id)
                if col in {1, 2, 4, 5, 6, 7, 8, 9}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, col, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.Stretch)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._orders)
        self._record_count_label.setText(f"{count} order" if count == 1 else f"{count} orders")

    def _apply_search_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        for row in range(self._table.rowCount()):
            if not query:
                self._table.setRowHidden(row, False)
                continue
            match = False
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None and query in item.text().lower():
                    match = True
                    break
            self._table.setRowHidden(row, not match)

    def _restore_selection(self, selected_order_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_order_id is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_order_id:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    def _selected_order(self) -> SalesOrderListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        order_id = item.data(Qt.ItemDataRole.UserRole)
        for order in self._orders:
            if order.id == order_id:
                return order
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_order()
        has_company = active_company is not None
        perm = self._service_registry.permission_service

        status = selected.status_code if selected else ""

        self._new_button.setEnabled(has_company and perm.has_permission("sales.orders.create"))
        self._edit_button.setEnabled(
            has_company and selected is not None and status == "draft"
            and perm.has_permission("sales.orders.edit")
        )
        self._confirm_button.setEnabled(
            has_company and selected is not None and status == "draft"
            and perm.has_permission("sales.orders.confirm")
        )
        self._convert_button.setEnabled(
            has_company and selected is not None and status == "confirmed"
            and perm.has_permission("sales.orders.convert")
            and perm.has_permission("sales.invoices.create")
        )
        self._cancel_button.setEnabled(
            has_company and selected is not None and status in {"draft", "confirmed"}
            and perm.has_permission("sales.orders.cancel")
        )

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Sales Orders",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    # ------------------------------------------------------------------
    # Event dispatchers
    # ------------------------------------------------------------------

    def _handle_active_company_changed(self) -> None:
        self.reload_orders()

    def _handle_item_double_clicked(self) -> None:
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
