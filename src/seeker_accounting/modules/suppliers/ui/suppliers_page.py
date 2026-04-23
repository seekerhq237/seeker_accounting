from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.accounting.reference_data.ui.account_role_mapping_dialog import (
    AccountRoleMappingDialog,
)
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.parties.dto.control_account_foundation_dto import (
    ControlAccountFoundationStatusDTO,
)
from seeker_accounting.modules.suppliers.dto.supplier_dto import SupplierListItemDTO
from seeker_accounting.modules.suppliers.ui.supplier_dialog import SupplierDialog
from seeker_accounting.modules.suppliers.ui.supplier_group_dialog import SupplierGroupDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.pager import Pager
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.table_helpers import configure_dense_table
from seeker_accounting.shared.ui.register import RegisterPage


class SuppliersPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._suppliers: list[SupplierListItemDTO] = []
        self._total_count: int = 0
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(lambda: self.reload_suppliers(reset_page=True))

        self.setObjectName("SuppliersPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_readiness_card())

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        self._populate_action_band(self._register)
        # Ribbon hosts the primary commands; hide the ActionBand band.
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._search_edit.textChanged.connect(self._handle_search_text_changed)

        self.reload_suppliers()

    def _handle_search_text_changed(self, _text: str) -> None:
        self._search_debounce.start()

    def reload_suppliers(
        self,
        selected_supplier_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        active_company = self._active_company()
        self._sync_readiness(active_company)

        if active_company is None:
            self._suppliers = []
            self._total_count = 0
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._pager.reset()
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        if reset_page:
            self._pager.reset()

        search_text = self._search_edit.text().strip() or None
        try:
            page_result = self._service_registry.supplier_service.list_suppliers_page(
                active_company.company_id,
                active_only=False,
                query=search_text,
                page=self._pager.page,
                page_size=self._pager.page_size,
            )
        except Exception as exc:
            self._suppliers = []
            self._total_count = 0
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._pager.reset()
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Suppliers", f"Supplier data could not be loaded.\n\n{exc}")
            return

        self._suppliers = list(page_result.items)
        self._total_count = page_result.total_count
        self._pager.apply_result(page_result)
        self._populate_table()
        self._sync_surface_state(active_company)
        self._update_record_count_label(search_text)
        self._restore_selection(selected_supplier_id)
        self._update_action_state()

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._search_edit = QLineEdit(register.toolbar_strip)
        self._search_edit.setPlaceholderText("Search supplier code or name…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(260)
        strip_layout.addWidget(self._search_edit)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_suppliers())
        strip_layout.addWidget(self._refresh_button)

    def _populate_action_band(self, register: RegisterPage) -> None:
        band_layout = register.action_band_layout

        self._new_button = QPushButton("New Supplier", register.action_band)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        band_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Supplier", register.action_band)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        band_layout.addWidget(self._edit_button)

        self._deactivate_button = QPushButton("Deactivate", register.action_band)
        self._deactivate_button.setProperty("variant", "secondary")
        self._deactivate_button.clicked.connect(self._deactivate_selected_supplier)
        band_layout.addWidget(self._deactivate_button)

        self._groups_button = QPushButton("Manage Groups", register.action_band)
        self._groups_button.setProperty("variant", "secondary")
        self._groups_button.clicked.connect(self._open_group_dialog)
        band_layout.addWidget(self._groups_button)

        band_layout.addStretch(1)

        self._export_list_button = QPushButton("Export List", register.action_band)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._print_supplier_list)
        band_layout.addWidget(self._export_list_button)

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

        title = QLabel("AP Control-Account Foundation", text_container)
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

        self._table = QTableWidget(container)
        self._table.setObjectName("SuppliersTable")
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ("Supplier Code", "Display Name", "Group", "Payment Term", "Status")
        )
        configure_dense_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._table, 1)

        self._pager = Pager(container, default_page_size=100)
        self._pager.page_changed.connect(lambda _p: self.reload_suppliers())
        self._pager.page_size_changed.connect(lambda _s: self.reload_suppliers(reset_page=True))
        layout.addWidget(self._pager)
        return container

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No suppliers yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first supplier for the active company once its master-data and AP control-account foundation are in place.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Supplier", actions)
        create_button.setProperty("variant", "primary")
        create_button.clicked.connect(self._open_create_dialog)
        actions_layout.addWidget(create_button, 0, Qt.AlignmentFlag.AlignLeft)

        groups_button = QPushButton("Manage Groups", actions)
        groups_button.setProperty("variant", "secondary")
        groups_button.clicked.connect(self._open_group_dialog)
        actions_layout.addWidget(groups_button, 0, Qt.AlignmentFlag.AlignLeft)
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
            "Suppliers are company-scoped. Choose the active company from the shell, or return to Companies if setup still needs to happen first.",
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
            status = self._service_registry.control_account_foundation_service.get_supplier_ap_foundation_status(
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
        if self._suppliers:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        # Bulk populate with paint updates and sorting suspended for speed.
        self._table.setUpdatesEnabled(False)
        self._table.setSortingEnabled(False)
        try:
            self._table.setRowCount(len(self._suppliers))
            for row_index, supplier in enumerate(self._suppliers):
                values = (
                    supplier.supplier_code,
                    supplier.display_name,
                    supplier.supplier_group_name or "",
                    supplier.payment_term_name or "",
                    "Active" if supplier.is_active else "Inactive",
                )
                for column_index, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column_index == 0:
                        item.setData(Qt.ItemDataRole.UserRole, supplier.id)
                    if column_index == 4:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._table.setItem(row_index, column_index, item)

            self._table.resizeColumnsToContents()
            header = self._table.horizontalHeader()
            header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, header.ResizeMode.Stretch)
            header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        finally:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)

    def _update_record_count_label(self, search_text: str | None) -> None:
        total = self._total_count
        shown = len(self._suppliers)
        if search_text:
            self._record_count_label.setText(f"{shown} shown of {total} matches")
        else:
            self._record_count_label.setText(
                f"{total} supplier" if total == 1 else f"{total} suppliers"
            )

    def _restore_selection(self, selected_supplier_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_supplier_id is None:
            self._select_first_visible_row()
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_supplier_id:
                if not self._table.isRowHidden(row_index):
                    self._table.selectRow(row_index)
                    return
        self._select_first_visible_row()

    def _select_first_visible_row(self) -> None:
        for row_index in range(self._table.rowCount()):
            if not self._table.isRowHidden(row_index):
                self._table.selectRow(row_index)
                return
        self._table.clearSelection()

    def _selected_supplier(self) -> SupplierListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0 or self._table.isRowHidden(current_row):
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        supplier_id = item.data(Qt.ItemDataRole.UserRole)
        for supplier in self._suppliers:
            if supplier.id == supplier_id:
                return supplier
        return None

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Suppliers",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected_supplier = self._selected_supplier()
        has_active_company = active_company is not None
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_active_company and permission_service.has_permission("suppliers.create")
        )
        self._edit_button.setEnabled(
            selected_supplier is not None
            and has_active_company
            and permission_service.has_permission("suppliers.edit")
        )
        self._deactivate_button.setEnabled(
            selected_supplier is not None
            and has_active_company
            and selected_supplier.is_active
            and permission_service.has_permission("suppliers.deactivate")
        )
        self._groups_button.setEnabled(
            has_active_company
            and permission_service.has_any_permission(
                (
                    "suppliers.groups.view",
                    "suppliers.groups.create",
                    "suppliers.groups.edit",
                    "suppliers.groups.deactivate",
                )
            )
        )
        self._export_list_button.setEnabled(has_active_company and bool(self._suppliers))
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self):
        return {
            "suppliers.new": self._open_create_dialog,
            "suppliers.edit": self._open_edit_dialog,
            "suppliers.deactivate": self._deactivate_selected_supplier,
            "suppliers.refresh": self.reload_suppliers,
            "suppliers.export_list": self._print_supplier_list,
        }

    def ribbon_state(self):
        return {
            "suppliers.new": self._new_button.isEnabled(),
            "suppliers.edit": self._edit_button.isEnabled(),
            "suppliers.deactivate": self._deactivate_button.isEnabled(),
            "suppliers.refresh": True,
            "suppliers.export_list": self._export_list_button.isEnabled(),
        }

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("suppliers.create"):
            self._show_permission_denied("suppliers.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Suppliers", "Select an active company before creating suppliers.")
            return

        supplier = SupplierDialog.create_supplier(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if supplier is None:
            return
        self.reload_suppliers(selected_supplier_id=supplier.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("suppliers.edit"):
            self._show_permission_denied("suppliers.edit")
            return
        active_company = self._active_company()
        supplier = self._selected_supplier()
        if active_company is None or supplier is None:
            show_info(self, "Suppliers", "Select a supplier to edit.")
            return

        updated_supplier = SupplierDialog.edit_supplier(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            supplier_id=supplier.id,
            parent=self,
        )
        if updated_supplier is None:
            return
        self.reload_suppliers(selected_supplier_id=updated_supplier.id)

    def _deactivate_selected_supplier(self) -> None:
        if not self._service_registry.permission_service.has_permission("suppliers.deactivate"):
            self._show_permission_denied("suppliers.deactivate")
            return
        active_company = self._active_company()
        supplier = self._selected_supplier()
        if active_company is None or supplier is None:
            show_info(self, "Suppliers", "Select a supplier to deactivate.")
            return
        if not supplier.is_active:
            show_info(self, "Suppliers", "The selected supplier is already inactive.")
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Supplier",
            f"Deactivate supplier '{supplier.display_name}' ({supplier.supplier_code}) for {active_company.company_name}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.supplier_service.deactivate_supplier(active_company.company_id, supplier.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Suppliers", str(exc))
            self.reload_suppliers()
            return

        self.reload_suppliers(selected_supplier_id=supplier.id)

    def _open_group_dialog(self) -> None:
        if not self._service_registry.permission_service.has_any_permission(
            (
                "suppliers.groups.view",
                "suppliers.groups.create",
                "suppliers.groups.edit",
                "suppliers.groups.deactivate",
            )
        ):
            self._show_permission_denied("suppliers.groups.view")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Suppliers", "Select an active company before managing supplier groups.")
            return
        SupplierGroupDialog.manage_groups(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        self.reload_suppliers()

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

    def _handle_item_double_clicked(self, *_args: object) -> None:
        supplier = self._selected_supplier()
        if supplier is None:
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.SUPPLIER_DETAIL,
            context={"supplier_id": supplier.id},
        )

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_suppliers()

    def set_navigation_context(self, context: dict) -> None:
        self.reload_suppliers()

    # ------------------------------------------------------------------
    # Print / export
    # ------------------------------------------------------------------

    def _print_supplier_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._suppliers:
            return
        result = PrintExportDialog.show_dialog(self, "Supplier Register")
        if result is None:
            return
        try:
            self._service_registry.supplier_print_service.print_supplier_list(
                active_company.company_id, self._suppliers, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Suppliers", f"Export failed.\n\n{exc}")
