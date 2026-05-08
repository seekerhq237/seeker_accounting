from __future__ import annotations

import logging

from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
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
from seeker_accounting.modules.accounting.reference_data.ui.account_role_mapping_dialog import (
    AccountRoleMappingDialog,
)
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.customers.dto.customer_dto import CustomerListItemDTO
from seeker_accounting.modules.customers.ui.customer_dialog import CustomerDialog
from seeker_accounting.modules.customers.ui.customer_group_dialog import CustomerGroupDialog
from seeker_accounting.modules.parties.dto.control_account_foundation_dto import (
    ControlAccountFoundationStatusDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.background_task import run_with_progress
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.pager import Pager
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.register import RegisterPage


_log = logging.getLogger(__name__)


CUSTOMER_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="customer_code", title="Customer Code"),
    DataTableColumn(key="display_name", title="Display Name"),
    DataTableColumn(key="customer_group_name", title="Group"),
    DataTableColumn(key="payment_term_name", title="Payment Term"),
    DataTableColumn(key="credit_limit_amount", title="Credit Limit"),
    DataTableColumn(key="status", title="Status"),
)


# Ribbon command ids surfaced from this page.
_CMD_NEW = "customers.new"
_CMD_EDIT = "customers.edit"
_CMD_DEACTIVATE = "customers.deactivate"
_CMD_REFRESH = "customers.refresh"
_CMD_EXPORT_LIST = "customers.export_list"


class CustomersPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._customers: list[CustomerListItemDTO] = []
        self._total_count: int = 0
        # Debounce for the search box so typing doesn't fire a query per keystroke.
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(lambda: self.reload_customers(reset_page=True))

        # Per-command ribbon enablement. Mirrors the shell ribbon state.
        self._command_enabled: dict[str, bool] = {
            _CMD_NEW: False,
            _CMD_EDIT: False,
            _CMD_DEACTIVATE: False,
            _CMD_REFRESH: True,
            _CMD_EXPORT_LIST: False,
        }

        self.setObjectName("CustomersPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_readiness_card())

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        # Ribbon hosts the primary commands; the ActionBand stays empty and hidden.
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._search_edit.textChanged.connect(self._handle_search_text_changed)
        self._search_edit.textChanged.connect(self._table.set_search_text)
        self._search_edit.textChanged.connect(self._update_record_count_label)

        self.reload_customers()

    def _handle_search_text_changed(self, _text: str) -> None:
        # Debounced — triggers a server-side reload with page reset.
        self._search_debounce.start()

    def reload_customers(
        self,
        selected_customer_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        active_company = self._active_company()
        self._sync_readiness(active_company)

        if active_company is None:
            self._customers = []
            self._total_count = 0
            self._customers_model.removeRows(0, self._customers_model.rowCount())
            self._record_count_label.setText("Select a company")
            self._pager.reset()
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        if reset_page:
            self._pager.reset()

        # Capture all parameters before handing off to the worker thread.
        company_id = active_company.company_id
        search_text = self._search_edit.text().strip() or None
        page = self._pager.page
        page_size = self._pager.page_size

        task = run_with_progress(
            parent=self,
            title="Customers",
            message="Loading customers…",
            worker=lambda: self._service_registry.customer_service.list_customers_page(
                company_id,
                active_only=False,
                query=search_text,
                page=page,
                page_size=page_size,
            ),
        )
        if task.cancelled:
            return
        if task.error is not None:
            self._customers = []
            self._total_count = 0
            self._customers_model.removeRows(0, self._customers_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._pager.reset()
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Customers", f"Customer data could not be loaded.\n\n{task.error}")
            return

        page_result = task.value
        self._customers = list(page_result.items)
        self._total_count = page_result.total_count
        self._pager.apply_result(page_result)
        self._populate_table()
        self._sync_surface_state(active_company)
        self._update_record_count_label()
        self._restore_selection(selected_customer_id)
        self._update_action_state()

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._search_edit = QLineEdit(register.toolbar_strip)
        self._search_edit.setPlaceholderText("Search customer code or name…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(260)
        strip_layout.addWidget(self._search_edit)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_customers())
        strip_layout.addWidget(self._refresh_button)

    def _build_readiness_card(self) -> QWidget:
        self._readiness_card = QFrame(self)
        self._readiness_card.setObjectName("PageCard")

        layout = QHBoxLayout(self._readiness_card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        text_container = QWidget(self._readiness_card)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        title = QLabel("AR Control-Account Foundation", text_container)
        title.setObjectName("CardTitle")
        text_layout.addWidget(title)

        self._readiness_value = QLabel(text_container)
        self._readiness_value.setObjectName("ToolbarValue")
        text_layout.addWidget(self._readiness_value)

        self._readiness_meta = QLabel(text_container)
        self._readiness_meta.setObjectName("ToolbarMeta")
        self._readiness_meta.setWordWrap(True)
        text_layout.addWidget(self._readiness_meta)

        layout.addWidget(text_container, 1)

        self._fix_mapping_button = QPushButton("Fix Mapping", self._readiness_card)
        self._fix_mapping_button.setProperty("variant", "secondary")
        self._fix_mapping_button.clicked.connect(self._open_mapping_dialog)
        layout.addWidget(self._fix_mapping_button)
        return self._readiness_card

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

        self._customers_model = QStandardItemModel(0, len(CUSTOMER_COLUMNS), self)
        self._customers_model.setHorizontalHeaderLabels([c.title for c in CUSTOMER_COLUMNS])

        self._table = DataTable(
            columns=CUSTOMER_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text=(
                "No customers yet. Use the ribbon's New Customer to add one."
            ),
            parent=container,
        )
        self._table.set_model(self._customers_model)
        self._customers_status_delegate = apply_status_chip_to_column(self._table.view(), 5)
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        layout.addWidget(self._table, 1)

        self._pager = Pager(container, default_page_size=100)
        self._pager.page_changed.connect(lambda _p: self.reload_customers())
        self._pager.page_size_changed.connect(lambda _s: self.reload_customers(reset_page=True))
        layout.addWidget(self._pager)
        return container

    def _build_empty_state(self) -> QWidget:
        state = build_empty_state("customers.empty", parent=self)
        state.primary_clicked.connect(self._open_create_dialog)
        state.secondary_clicked.connect(self._open_group_dialog)
        return state

    def _build_no_active_company_state(self) -> QWidget:
        state = build_empty_state("customers.no_company", parent=self)
        state.primary_clicked.connect(self._open_companies_workspace)
        return state

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_readiness(self, active_company: ActiveCompanyDTO | None) -> None:
        has_active_company = active_company is not None
        self._readiness_card.setVisible(has_active_company)
        self._fix_mapping_button.setEnabled(
            has_active_company
            and self._service_registry.permission_service.has_any_permission(
                ("reference.account_role_mappings.manage", "chart.role_mappings.manage")
            )
        )
        if active_company is None:
            return

        try:
            status = self._service_registry.control_account_foundation_service.get_customer_ar_foundation_status(
                active_company.company_id
            )
        except Exception as exc:
            self._readiness_value.setText("Readiness unavailable")
            self._readiness_meta.setText(str(exc))
            return

        self._apply_readiness_status(status)

    def _apply_readiness_status(self, status: ControlAccountFoundationStatusDTO) -> None:
        if status.is_ready:
            self._readiness_value.setText("Ready")
            if status.mapped_account_code and status.mapped_account_name:
                self._readiness_meta.setText(
                    f"{status.role_label} mapped to {status.mapped_account_code}  {status.mapped_account_name}."
                )
            else:
                self._readiness_meta.setText(f"{status.role_label} mapping is in place.")
            return

        self._readiness_value.setText("Needs attention")
        self._readiness_meta.setText(" ".join(status.issues))

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._customers:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    @staticmethod
    def _make_item(text: str, *, user_data: object | None = None) -> QStandardItem:
        item = QStandardItem(text or "")
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self) -> None:
        self._customers_model.removeRows(0, self._customers_model.rowCount())
        for customer in self._customers:
            items = [
                self._make_item(customer.customer_code, user_data=customer.id),
                self._make_item(customer.display_name),
                self._make_item(customer.customer_group_name or ""),
                self._make_item(customer.payment_term_name or ""),
                self._make_item(self._format_amount(customer.credit_limit_amount)),
                self._make_item("active" if customer.is_active else "inactive"),
            ]
            self._customers_model.appendRow(items)

    def _update_record_count_label(self, *_args: object) -> None:
        total = len(self._customers)
        query = self._search_edit.text().strip()
        if query:
            proxy = self._table.view().model()
            visible = proxy.rowCount() if proxy is not None else total
            self._record_count_label.setText(
                f"{visible} shown of {total} customers"
            )
        else:
            self._record_count_label.setText(
                f"{total} customer" if total == 1 else f"{total} customers"
            )

    def _restore_selection(self, selected_customer_id: int | None) -> None:
        if not self._customers:
            return
        if selected_customer_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, c in enumerate(self._customers) if c.id == selected_customer_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._customers_model.index(target_idx, 0)
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

    def _selected_customer(self) -> CustomerListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._customers):
            return self._customers[idx]
        return None

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        customer = self._selected_customer()
        if customer is None:
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.CUSTOMER_DETAIL,
            context={"customer_id": customer.id},
        )

    def _set_command_enabled(self, command_id: str, enabled: bool) -> None:
        self._command_enabled[command_id] = bool(enabled)

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Customers",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected_customer = self._selected_customer()
        has_active_company = active_company is not None
        permission_service = self._service_registry.permission_service

        self._set_command_enabled(
            _CMD_NEW,
            has_active_company and permission_service.has_permission("customers.create"),
        )
        self._set_command_enabled(
            _CMD_EDIT,
            selected_customer is not None
            and has_active_company
            and permission_service.has_permission("customers.edit"),
        )
        self._set_command_enabled(
            _CMD_DEACTIVATE,
            selected_customer is not None
            and has_active_company
            and selected_customer.is_active
            and permission_service.has_permission("customers.deactivate"),
        )
        self._set_command_enabled(
            _CMD_EXPORT_LIST,
            has_active_company and bool(self._customers),
        )
        self._set_command_enabled(_CMD_REFRESH, True)
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self):
        return {
            _CMD_NEW: self._open_create_dialog,
            _CMD_EDIT: self._open_edit_dialog,
            _CMD_DEACTIVATE: self._deactivate_selected_customer,
            _CMD_REFRESH: self.reload_customers,
            _CMD_EXPORT_LIST: self._print_customer_list,
        }

    def ribbon_state(self):
        return dict(self._command_enabled)

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("customers.create"):
            self._show_permission_denied("customers.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Customers", "Select an active company before creating customers.")
            return

        customer = CustomerDialog.create_customer(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if customer is None:
            return
        self.reload_customers(selected_customer_id=customer.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("customers.edit"):
            self._show_permission_denied("customers.edit")
            return
        active_company = self._active_company()
        customer = self._selected_customer()
        if active_company is None or customer is None:
            show_info(self, "Customers", "Select a customer to edit.")
            return

        updated_customer = CustomerDialog.edit_customer(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            customer_id=customer.id,
            parent=self,
        )
        if updated_customer is None:
            return
        self.reload_customers(selected_customer_id=updated_customer.id)

    def _deactivate_selected_customer(self) -> None:
        if not self._service_registry.permission_service.has_permission("customers.deactivate"):
            self._show_permission_denied("customers.deactivate")
            return
        active_company = self._active_company()
        customer = self._selected_customer()
        if active_company is None or customer is None:
            show_info(self, "Customers", "Select a customer to deactivate.")
            return
        if not customer.is_active:
            show_info(self, "Customers", "The selected customer is already inactive.")
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Customer",
            f"Deactivate customer '{customer.display_name}' ({customer.customer_code}) for {active_company.company_name}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.customer_service.deactivate_customer(active_company.company_id, customer.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Customers", str(exc))
            self.reload_customers()
            return

        self.reload_customers(selected_customer_id=customer.id)

    def _open_group_dialog(self) -> None:
        if not self._service_registry.permission_service.has_any_permission(
            (
                "customers.groups.view",
                "customers.groups.create",
                "customers.groups.edit",
                "customers.groups.deactivate",
            )
        ):
            self._show_permission_denied("customers.groups.view")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Customers", "Select an active company before managing customer groups.")
            return
        CustomerGroupDialog.manage_groups(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        self.reload_customers()

    def _open_mapping_dialog(self) -> None:
        if not self._service_registry.permission_service.has_any_permission(
            ("reference.account_role_mappings.manage", "chart.role_mappings.manage")
        ):
            self._show_permission_denied("reference.account_role_mappings.manage")
            return
        active_company = self._active_company()
        if active_company is None:
            return
        AccountRoleMappingDialog.manage_mappings(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        self._sync_readiness(active_company)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _format_amount(self, value: Decimal | None) -> str:
        return "" if value is None else f"{value:,.2f}"

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_customers()

    def set_navigation_context(self, context: dict) -> None:
        self.reload_customers()

    # ------------------------------------------------------------------
    # Print / export
    # ------------------------------------------------------------------

    def _print_customer_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._customers:
            return
        result = PrintExportDialog.show_dialog(self, "Customer Register")
        if result is None:
            return
        try:
            self._service_registry.customer_print_service.print_customer_list(
                active_company.company_id, self._customers, result,
            )
            result.open_file()
        except AppError as exc:
            show_error(self, "Customers", f"Export failed.\n\n{exc}")

        except Exception:
            _log.exception("Customers")
            show_error(self, "Customers", "An unexpected error occurred. See application log for details.")
