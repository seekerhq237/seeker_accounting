from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
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
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import TaxCodeListItemDTO
from seeker_accounting.modules.accounting.reference_data.ui.tax_code_account_mapping_dialog import (
    TaxCodeAccountMappingDialog,
)
from seeker_accounting.modules.accounting.reference_data.ui.tax_code_dialog import TaxCodeDialog
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class TaxCodesPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._tax_codes: list[TaxCodeListItemDTO] = []

        self.setObjectName("TaxCodesPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._action_bar = self._build_action_bar()
        root_layout.addWidget(self._action_bar)
        self._action_bar.hide()
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )

        self.reload_tax_codes()

    def reload_tax_codes(self, selected_tax_code_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._tax_codes = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._tax_codes = self._service_registry.tax_setup_service.list_tax_codes(active_company.company_id)
        except Exception as exc:
            self._tax_codes = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Tax Codes", f"Tax codes could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_tax_code_id)
        self._update_action_state()

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Tax Code Register", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)

        self._new_button = QPushButton("New Tax Code", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Tax Code", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._deactivate_button = QPushButton("Deactivate", card)
        self._deactivate_button.setProperty("variant", "secondary")
        self._deactivate_button.clicked.connect(self._deactivate_selected_tax_code)
        layout.addWidget(self._deactivate_button)

        self._mapping_button = QPushButton("Account Mappings", card)
        self._mapping_button.setProperty("variant", "secondary")
        self._mapping_button.clicked.connect(self._open_tax_account_mappings)
        layout.addWidget(self._mapping_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_tax_codes())
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

        self._table = QTableWidget(card)
        self._table.setObjectName("TaxCodesTable")
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ("Code", "Name", "Tax Type", "Method", "Rate", "Effective From", "Effective To", "Status")
        )
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

        title = QLabel("No tax codes yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first tax definition for the active company so invoicing and later postings have an explicit starting point.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Tax Code", actions)
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
            "Tax codes are company-scoped. Choose the active company from the shell, or return to Companies if setup still needs to happen first.",
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

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._tax_codes:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for tax_code in self._tax_codes:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)

            values = (
                tax_code.code,
                tax_code.name,
                tax_code.tax_type_code,
                tax_code.calculation_method_code,
                self._format_rate(tax_code.rate_percent),
                self._format_date(tax_code.effective_from),
                self._format_date(tax_code.effective_to),
                "Active" if tax_code.is_active else "Inactive",
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, tax_code.id)
                if column_index in {4, 5, 6, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, column_index, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._tax_codes)
        self._record_count_label.setText(f"{count} tax code" if count == 1 else f"{count} tax codes")

    def _restore_selection(self, selected_tax_code_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return

        if selected_tax_code_id is None:
            self._table.selectRow(0)
            return

        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_tax_code_id:
                self._table.selectRow(row_index)
                return

        self._table.selectRow(0)

    def _selected_tax_code(self) -> TaxCodeListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None

        item = self._table.item(current_row, 0)
        if item is None:
            return None

        tax_code_id = item.data(Qt.ItemDataRole.UserRole)
        for tax_code in self._tax_codes:
            if tax_code.id == tax_code_id:
                return tax_code
        return None

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Tax Codes",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected_tax_code = self._selected_tax_code()
        has_active_company = active_company is not None
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_active_company and permission_service.has_permission("reference.tax_codes.create")
        )
        self._edit_button.setEnabled(
            selected_tax_code is not None
            and has_active_company
            and permission_service.has_permission("reference.tax_codes.edit")
        )
        self._deactivate_button.setEnabled(
            selected_tax_code is not None
            and has_active_company
            and selected_tax_code.is_active
            and permission_service.has_permission("reference.tax_codes.deactivate")
        )
        self._mapping_button.setEnabled(
            has_active_company
            and permission_service.has_any_permission(
                ("reference.tax_mappings.view", "reference.tax_mappings.manage")
            )
        )
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ────────────────────────────────────────────────────

    def _ribbon_commands(self) -> dict:
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_handlers
        return {
            "tax_codes.new": self._open_create_dialog,
            "tax_codes.edit": self._open_edit_dialog,
            "tax_codes.deactivate": self._deactivate_selected_tax_code,
            "tax_codes.account_mappings": self._open_tax_account_mappings,
            "tax_codes.refresh": self.reload_tax_codes,
            **related_goto_handlers(self._service_registry, "tax_codes"),
        }

    def ribbon_state(self) -> dict:
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_state
        return {
            "tax_codes.new": self._new_button.isEnabled(),
            "tax_codes.edit": self._edit_button.isEnabled(),
            "tax_codes.deactivate": self._deactivate_button.isEnabled(),
            "tax_codes.account_mappings": self._mapping_button.isEnabled(),
            "tax_codes.refresh": True,
            **related_goto_state("tax_codes"),
        }

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.tax_codes.create"):
            self._show_permission_denied("reference.tax_codes.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Tax Codes", "Select an active company before creating tax codes.")
            return

        tax_code = TaxCodeDialog.create_tax_code(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if tax_code is None:
            return
        self.reload_tax_codes(selected_tax_code_id=tax_code.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.tax_codes.edit"):
            self._show_permission_denied("reference.tax_codes.edit")
            return
        active_company = self._active_company()
        tax_code = self._selected_tax_code()
        if active_company is None or tax_code is None:
            show_info(self, "Tax Codes", "Select a tax code to edit.")
            return

        updated_tax_code = TaxCodeDialog.edit_tax_code(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            tax_code_id=tax_code.id,
            parent=self,
        )
        if updated_tax_code is None:
            return
        self.reload_tax_codes(selected_tax_code_id=updated_tax_code.id)

    def _deactivate_selected_tax_code(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.tax_codes.deactivate"):
            self._show_permission_denied("reference.tax_codes.deactivate")
            return
        active_company = self._active_company()
        tax_code = self._selected_tax_code()
        if active_company is None or tax_code is None:
            show_info(self, "Tax Codes", "Select a tax code to deactivate.")
            return
        if not tax_code.is_active:
            show_info(self, "Tax Codes", "The selected tax code is already inactive.")
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Tax Code",
            (
                f"Deactivate tax code '{tax_code.name}' ({tax_code.code}) "
                f"for {active_company.company_name}?"
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.tax_setup_service.deactivate_tax_code(
                active_company.company_id,
                tax_code.id,
            )
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Tax Codes", str(exc))
            self.reload_tax_codes()
            return

        self.reload_tax_codes(selected_tax_code_id=tax_code.id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _open_tax_account_mappings(self) -> None:
        if not self._service_registry.permission_service.has_any_permission(
            ("reference.tax_mappings.view", "reference.tax_mappings.manage")
        ):
            self._show_permission_denied("reference.tax_mappings.view")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Tax Codes", "Select an active company before managing tax account mappings.")
            return
        TaxCodeAccountMappingDialog.manage_mappings(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )

    def _format_rate(self, rate_percent: Decimal | None) -> str:
        return "" if rate_percent is None else f"{rate_percent}%"

    def _format_date(self, value: date | None) -> str:
        return value.strftime("%Y-%m-%d") if value is not None else ""

    def _handle_item_double_clicked(self, *_args: object) -> None:
        self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_tax_codes()
