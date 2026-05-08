from __future__ import annotations

import logging

from PySide6.QtCore import Qt
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
from seeker_accounting.modules.parties.dto.control_account_foundation_dto import (
    ControlAccountFoundationStatusDTO,
)
from seeker_accounting.modules.suppliers.dto.supplier_dto import SupplierListItemDTO
from seeker_accounting.modules.suppliers.ui.supplier_dialog import SupplierDialog
from seeker_accounting.modules.suppliers.ui.supplier_group_dialog import SupplierGroupDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.background_task import run_with_progress
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.register import RegisterPage


_log = logging.getLogger(__name__)


SUPPLIER_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="supplier_code", title="Supplier Code"),
    DataTableColumn(key="display_name", title="Display Name"),
    DataTableColumn(key="group", title="Group"),
    DataTableColumn(key="payment_term", title="Payment Term"),
    DataTableColumn(key="status", title="Status"),
)

_STATUS_COLUMN_INDEX = 4


# Ribbon command ids surfaced from this page.
_CMD_NEW = "suppliers.new"
_CMD_EDIT = "suppliers.edit"
_CMD_DEACTIVATE = "suppliers.deactivate"
_CMD_REFRESH = "suppliers.refresh"
_CMD_EXPORT = "suppliers.export_list"


class SuppliersPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._suppliers: list[SupplierListItemDTO] = []

        # Per-command ribbon enablement. Mirrors the shell ribbon state.
        self._command_enabled: dict[str, bool] = {
            _CMD_NEW: False,
            _CMD_EDIT: False,
            _CMD_DEACTIVATE: False,
            _CMD_REFRESH: True,
            _CMD_EXPORT: False,
        }

        self.setObjectName("SuppliersPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_readiness_card())

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        # Ribbon hosts the primary commands; hide the ActionBand band.
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._search_edit.textChanged.connect(self._table.set_search_text)
        self._search_edit.textChanged.connect(self._update_record_count_label)

        self.reload_suppliers()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_suppliers(
        self,
        selected_supplier_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        _ = reset_page  # retained for backward compatibility
        active_company = self._active_company()
        self._sync_readiness(active_company)

        if active_company is None:
            self._suppliers = []
            self._populate_table()
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        company_id = active_company.company_id
        task = run_with_progress(
            parent=self,
            title="Suppliers",
            message="Loading suppliers…",
            worker=lambda: list(
                self._service_registry.supplier_service.list_suppliers(
                    company_id,
                    active_only=False,
                )
            ),
        )
        if task.cancelled:
            return
        if task.error is not None:
            self._suppliers = []
            self._populate_table()
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Suppliers", f"Supplier data could not be loaded.\n\n{task.error}")
            return

        self._suppliers = task.value
        self._populate_table()
        self._sync_surface_state(active_company)
        self._update_record_count_label()
        self._restore_selection(selected_supplier_id)
        self._update_action_state()

    # ------------------------------------------------------------------
    # Toolbar strip
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Readiness card
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Content stack
    # ------------------------------------------------------------------

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
        layout.setSpacing(0)

        self._suppliers_model = QStandardItemModel(0, len(SUPPLIER_COLUMNS), self)
        self._suppliers_model.setHorizontalHeaderLabels([c.title for c in SUPPLIER_COLUMNS])

        self._table = DataTable(
            columns=SUPPLIER_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text=(
                "No suppliers yet. Use the ribbon's New Supplier to add one."
            ),
            parent=container,
        )
        self._table.set_model(self._suppliers_model)
        self._suppliers_status_delegate = apply_status_chip_to_column(
            self._table.view(), _STATUS_COLUMN_INDEX
        )
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)

        layout.addWidget(self._table, 1)
        return container

    def _build_empty_state(self) -> QWidget:
        state = build_empty_state("suppliers.empty", parent=self)
        state.primary_clicked.connect(self._open_create_dialog)
        state.secondary_clicked.connect(self._open_group_dialog)
        return state

    def _build_no_active_company_state(self) -> QWidget:
        state = build_empty_state("suppliers.no_company", parent=self)
        state.primary_clicked.connect(self._open_companies_workspace)
        return state

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Table population and search
    # ------------------------------------------------------------------

    @staticmethod
    def _make_item(text: str, *, user_data: object | None = None) -> QStandardItem:
        item = QStandardItem(text or "")
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self) -> None:
        self._suppliers_model.removeRows(0, self._suppliers_model.rowCount())
        for supplier in self._suppliers:
            status_code = "active" if supplier.is_active else "inactive"
            items = [
                self._make_item(supplier.supplier_code, user_data=supplier.id),
                self._make_item(supplier.display_name),
                self._make_item(supplier.supplier_group_name or ""),
                self._make_item(supplier.payment_term_name or ""),
                self._make_item(status_code),
            ]
            self._suppliers_model.appendRow(items)

    def _update_record_count_label(self, *_args: object) -> None:
        total = len(self._suppliers)
        query = self._search_edit.text().strip()
        if query:
            proxy_model = self._table.view().model()
            visible = proxy_model.rowCount() if proxy_model is not None else total
            self._record_count_label.setText(f"{visible} shown of {total} suppliers")
        else:
            self._record_count_label.setText(
                f"{total} supplier" if total == 1 else f"{total} suppliers"
            )

    def _restore_selection(self, selected_supplier_id: int | None) -> None:
        if not self._suppliers:
            return
        if selected_supplier_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, s in enumerate(self._suppliers) if s.id == selected_supplier_id),
                0,
            )

        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._suppliers_model.index(target_idx, 0)
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

    def _selected_supplier(self) -> SupplierListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._suppliers):
            return self._suppliers[idx]
        return None

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        supplier = self._selected_supplier()
        if supplier is None:
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.SUPPLIER_DETAIL,
            context={"supplier_id": supplier.id},
        )

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Suppliers",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _set_command_enabled(self, command_id: str, enabled: bool) -> None:
        self._command_enabled[command_id] = bool(enabled)

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected_supplier = self._selected_supplier()
        has_active_company = active_company is not None
        has_selection = selected_supplier is not None and has_active_company
        permission_service = self._service_registry.permission_service

        self._set_command_enabled(
            _CMD_NEW,
            has_active_company and permission_service.has_permission("suppliers.create"),
        )
        self._set_command_enabled(
            _CMD_EDIT,
            has_selection and permission_service.has_permission("suppliers.edit"),
        )
        self._set_command_enabled(
            _CMD_DEACTIVATE,
            has_selection
            and selected_supplier.is_active
            and permission_service.has_permission("suppliers.deactivate"),
        )
        self._set_command_enabled(_CMD_REFRESH, True)
        self._set_command_enabled(
            _CMD_EXPORT,
            has_active_company and bool(self._suppliers),
        )

        self._notify_ribbon_state_changed()

    # ------------------------------------------------------------------
    # IRibbonHost
    # ------------------------------------------------------------------

    def _ribbon_commands(self):
        return {
            _CMD_NEW: self._open_create_dialog,
            _CMD_EDIT: self._open_edit_dialog,
            _CMD_DEACTIVATE: self._deactivate_selected_supplier,
            _CMD_REFRESH: self.reload_suppliers,
            _CMD_EXPORT: self._print_supplier_list,
        }

    def ribbon_state(self):
        return dict(self._command_enabled)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

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
        except Exception:
            _log.exception("Suppliers")
            show_error(self, "Suppliers", "An unexpected error occurred. See application log for details.")
