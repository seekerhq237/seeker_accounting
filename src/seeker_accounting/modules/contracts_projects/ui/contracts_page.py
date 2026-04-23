from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
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
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.contracts_projects.dto.contract_dto import ContractListItemDTO
from seeker_accounting.modules.contracts_projects.ui.contract_change_order_dialog import ContractChangeOrdersDialog
from seeker_accounting.modules.contracts_projects.ui.contract_form_dialog import ContractFormDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class ContractsPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._contracts: list[ContractListItemDTO] = []

        self.setObjectName("ContractsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._search_edit.textChanged.connect(self._apply_search_filter)

        self.reload_contracts()

    def reload_contracts(self, selected_contract_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._contracts = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._contracts = self._service_registry.contract_service.list_contracts(
                active_company.company_id,
            )
        except Exception as exc:
            self._contracts = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Contracts", f"Contract data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._apply_search_filter()
        self._restore_selection(selected_contract_id)
        self._update_action_state()

    # ------------------------------------------------------------------
    # Header and action bar
    # ------------------------------------------------------------------

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Contract Directory", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        self._search_edit = QLineEdit(card)
        self._search_edit.setPlaceholderText("Search contract number or title")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(220)
        layout.addWidget(self._search_edit)

        layout.addStretch(1)

        self._new_button = QPushButton("New Contract", card)
        self._new_button.hide()
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)

        self._edit_button = QPushButton("Edit Contract", card)
        self._edit_button.hide()
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)

        self._activate_button = QPushButton("Activate", card)
        self._activate_button.hide()
        self._activate_button.setProperty("variant", "secondary")
        self._activate_button.clicked.connect(self._activate_selected_contract)

        self._hold_button = QPushButton("Put On Hold", card)
        self._hold_button.hide()
        self._hold_button.setProperty("variant", "secondary")
        self._hold_button.clicked.connect(self._hold_selected_contract)

        self._complete_button = QPushButton("Complete", card)
        self._complete_button.hide()
        self._complete_button.setProperty("variant", "secondary")
        self._complete_button.clicked.connect(self._complete_selected_contract)

        self._close_button = QPushButton("Close Contract", card)
        self._close_button.hide()
        self._close_button.setProperty("variant", "secondary")
        self._close_button.clicked.connect(self._close_selected_contract)

        self._cancel_button = QPushButton("Cancel", card)
        self._cancel_button.hide()
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_contract)

        self._change_orders_button = QPushButton("Change Orders", card)
        self._change_orders_button.hide()
        self._change_orders_button.setProperty("variant", "secondary")
        self._change_orders_button.clicked.connect(self._open_change_orders)

        self._open_workspace_button = QPushButton("Open Workspace", card)
        self._open_workspace_button.hide()
        self._open_workspace_button.setProperty("variant", "secondary")
        self._open_workspace_button.clicked.connect(self._open_workspace)

        self._summary_button = QPushButton("Contract Summary", card)
        self._summary_button.hide()
        self._summary_button.setProperty("variant", "secondary")
        self._summary_button.clicked.connect(self._open_contract_summary)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.hide()
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_contracts())
        return card

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
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(card)
        self._table.setObjectName("ContractsTable")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ("Contract #", "Title", "Customer", "Type", "Amount", "Currency", "Status")
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

        title = QLabel("No contracts yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first contract for the active company.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Contract", actions)
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
            "Contracts are company-scoped. Choose the active company from the shell, "
            "or return to Companies if setup still needs to happen first.",
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
    # Context helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._contracts:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    # ------------------------------------------------------------------
    # Table population and search
    # ------------------------------------------------------------------

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for contract in self._contracts:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (
                contract.contract_number,
                contract.contract_title,
                contract.customer_display_name,
                contract.contract_type_code,
                self._format_amount(contract.base_contract_amount),
                contract.currency_code,
                contract.status_code,
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, contract.id)
                if column_index in {4}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column_index in {5, 6}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, column_index, item)

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

    def _apply_search_filter(self) -> None:
        query = self._search_edit.text().strip().lower()
        visible_count = 0
        for row_index in range(self._table.rowCount()):
            matches = not query or any(
                query in (self._table.item(row_index, col).text().lower() if self._table.item(row_index, col) else "")
                for col in range(self._table.columnCount())
            )
            self._table.setRowHidden(row_index, not matches)
            if matches:
                visible_count += 1

        total_count = len(self._contracts)
        if query:
            self._record_count_label.setText(f"{visible_count} shown of {total_count} contracts")
        else:
            self._record_count_label.setText(
                f"{total_count} contract" if total_count == 1 else f"{total_count} contracts"
            )
        self._update_action_state()

    def _restore_selection(self, selected_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_id is None:
            self._select_first_visible_row()
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_id:
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

    def _selected_contract(self) -> ContractListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0 or self._table.isRowHidden(current_row):
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        contract_id = item.data(Qt.ItemDataRole.UserRole)
        for contract in self._contracts:
            if contract.id == contract_id:
                return contract
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_contract()
        has_active_company = active_company is not None

        self._new_button.setEnabled(has_active_company)
        self._edit_button.setEnabled(selected is not None and has_active_company)
        self._activate_button.setEnabled(
            selected is not None and has_active_company and selected.status_code == "draft"
        )
        self._cancel_button.setEnabled(
            selected is not None
            and has_active_company
            and selected.status_code in {"draft", "active", "on_hold"}
        )
        self._hold_button.setEnabled(
            selected is not None and has_active_company and selected.status_code == "active"
        )
        self._complete_button.setEnabled(
            selected is not None
            and has_active_company
            and selected.status_code in {"active", "on_hold"}
        )
        self._close_button.setEnabled(
            selected is not None and has_active_company and selected.status_code == "completed"
        )
        self._change_orders_button.setEnabled(selected is not None and has_active_company)
        self._open_workspace_button.setEnabled(selected is not None and has_active_company)
        self._summary_button.setEnabled(selected is not None and has_active_company)
        self._notify_ribbon_state_changed()

    # ------------------------------------------------------------------
    # Ribbon host
    # ------------------------------------------------------------------

    def _ribbon_commands(self) -> dict[str, object]:
        return {
            "contracts.new": self._open_create_dialog,
            "contracts.open_workspace": self._open_workspace,
            "contracts.edit": self._open_edit_dialog,
            "contracts.activate": self._activate_selected_contract,
            "contracts.hold": self._hold_selected_contract,
            "contracts.complete": self._complete_selected_contract,
            "contracts.close_record": self._close_selected_contract,
            "contracts.cancel": self._cancel_selected_contract,
            "contracts.change_orders": self._open_change_orders,
            "contracts.summary": self._open_contract_summary,
            "contracts.refresh": lambda: self.reload_contracts(),
        }

    def ribbon_state(self) -> dict[str, bool]:
        return {
            "contracts.new": self._new_button.isEnabled(),
            "contracts.open_workspace": self._open_workspace_button.isEnabled(),
            "contracts.edit": self._edit_button.isEnabled(),
            "contracts.activate": self._activate_button.isEnabled(),
            "contracts.hold": self._hold_button.isEnabled(),
            "contracts.complete": self._complete_button.isEnabled(),
            "contracts.close_record": self._close_button.isEnabled(),
            "contracts.cancel": self._cancel_button.isEnabled(),
            "contracts.change_orders": self._change_orders_button.isEnabled(),
            "contracts.summary": self._summary_button.isEnabled(),
            "contracts.refresh": True,
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Contracts", "Select an active company before creating contracts.")
            return
        contract = ContractFormDialog.create_contract(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if contract is None:
            return
        self.reload_contracts(selected_contract_id=contract.id)

    def _open_edit_dialog(self) -> None:
        active_company = self._active_company()
        selected = self._selected_contract()
        if active_company is None or selected is None:
            show_info(self, "Contracts", "Select a contract to edit.")
            return
        updated = ContractFormDialog.edit_contract(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            contract_id=selected.id,
            parent=self,
        )
        if updated is None:
            return
        self.reload_contracts(selected_contract_id=updated.id)

    def _activate_selected_contract(self) -> None:
        self._change_selected_status(
            title="Activate Contract",
            prompt="Activate contract '{code}'?",
            service_call=self._service_registry.contract_service.activate_contract,
        )

    def _hold_selected_contract(self) -> None:
        self._change_selected_status(
            title="Put Contract On Hold",
            prompt="Put contract '{code}' on hold?",
            service_call=self._service_registry.contract_service.put_contract_on_hold,
        )

    def _complete_selected_contract(self) -> None:
        self._change_selected_status(
            title="Complete Contract",
            prompt="Mark contract '{code}' as completed?",
            service_call=self._service_registry.contract_service.complete_contract,
        )

    def _close_selected_contract(self) -> None:
        self._change_selected_status(
            title="Close Contract",
            prompt="Close contract '{code}'?",
            service_call=self._service_registry.contract_service.close_contract,
        )

    def _cancel_selected_contract(self) -> None:
        self._change_selected_status(
            title="Cancel Contract",
            prompt="Cancel contract '{code}'? This cannot be undone.",
            service_call=self._service_registry.contract_service.cancel_contract,
        )

    def _change_selected_status(self, *, title: str, prompt: str, service_call) -> None:
        selected = self._selected_contract()
        if selected is None:
            return
        choice = QMessageBox.question(
            self,
            title,
            prompt.format(code=selected.contract_number),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            service_call(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Contracts", str(exc))
        self.reload_contracts(selected_contract_id=selected.id)

    def _open_change_orders(self) -> None:
        active_company = self._active_company()
        selected = self._selected_contract()
        if active_company is None or selected is None:
            show_info(self, "Contracts", "Select a contract to manage change orders.")
            return
        ContractChangeOrdersDialog.manage_change_orders(
            self._service_registry,
            company_id=active_company.company_id,
            contract_id=selected.id,
            contract_number=selected.contract_number,
            parent=self,
        )
        self.reload_contracts(selected_contract_id=selected.id)

    def _open_workspace(self) -> None:
        active_company = self._active_company()
        selected = self._selected_contract()
        if active_company is None or selected is None:
            show_info(self, "Contracts", "Select a contract to open its workspace.")
            return

        manager = getattr(self._service_registry, "child_window_manager", None)
        if manager is None:
            self._open_edit_dialog()
            return

        from seeker_accounting.modules.contracts_projects.ui.contract_workspace_window import (
            ContractWorkspaceWindow,
        )

        manager.open_document(
            ContractWorkspaceWindow.DOC_TYPE,
            selected.id,
            lambda: ContractWorkspaceWindow(
                self._service_registry,
                company_id=active_company.company_id,
                company_name=active_company.company_name,
                contract_id=selected.id,
            ),
        )

    def _open_contract_summary(self) -> None:
        selected = self._selected_contract()
        if selected is None:
            show_info(self, "Contracts", "Select a contract first.")
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.CONTRACT_SUMMARY,
            context={"contract_id": selected.id},
        )

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _format_amount(self, value: Decimal | None) -> str:
        return "" if value is None else f"{value:,.2f}"

    def _handle_item_double_clicked(self, *_args: object) -> None:
        self._open_workspace()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_contracts()
