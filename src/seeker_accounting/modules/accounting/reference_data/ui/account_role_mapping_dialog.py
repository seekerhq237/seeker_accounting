from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountLookupDTO
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    AccountRoleMappingDTO,
    SetAccountRoleMappingCommand,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class AccountRoleMappingDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._mappings: list[AccountRoleMappingDTO] = []
        self._account_lookup_options: list[AccountLookupDTO] = []
        self._can_manage = self._service_registry.permission_service.has_any_permission(
            ("reference.account_role_mappings.manage", "chart.role_mappings.manage")
        )
        self._role_options = self._service_registry.account_role_mapping_service.list_role_options()

        super().__init__("Account Role Mappings", parent, help_key="dialog.account_role_mapping")
        self.setObjectName("AccountRoleMappingDialog")
        self.resize(760, 560)

        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_mapping_table())
        self.body_layout.addWidget(self._build_editor_section())
        self.body_layout.addStretch(1)

        close_button = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setProperty("variant", "secondary")

        self._save_button.clicked.connect(self._save_mapping)
        self._clear_button.clicked.connect(self._clear_mapping)
        self._refresh_button.clicked.connect(self.reload_mappings)
        self._table.itemSelectionChanged.connect(self._sync_editor_state)

        self._load_reference_data()
        self.reload_mappings()

    @classmethod
    def manage_mappings(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog.exec()

    def _build_mapping_table(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        self._table = QTableWidget(card)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(("Role", "Description", "Mapped Account"))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemDoubleClicked.connect(lambda *_args: self._account_combo.setFocus())
        layout.addWidget(self._table)
        return card

    def _build_editor_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Selected Role", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._role_value = QLabel("Select a role mapping", card)
        self._role_value.setObjectName("ValueLabel")
        grid.addWidget(create_field_block("Role", self._role_value), 0, 0)

        self._description_value = QLabel("", card)
        self._description_value.setObjectName("ToolbarMeta")
        self._description_value.setWordWrap(True)
        grid.addWidget(create_field_block("Description", self._description_value), 0, 1)

        self._account_combo = SearchableComboBox(card)
        grid.addWidget(
            create_field_block(
                "Mapped Account",
                self._account_combo,
            ),
            1,
            0,
            1,
            2,
        )

        layout.addLayout(grid)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        self._save_button = QPushButton("Save Mapping", actions)
        self._save_button.setProperty("variant", "primary")
        actions_layout.addWidget(self._save_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._clear_button = QPushButton("Clear Mapping", actions)
        self._clear_button.setProperty("variant", "secondary")
        actions_layout.addWidget(self._clear_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._refresh_button = QPushButton("Refresh", actions)
        self._refresh_button.setProperty("variant", "ghost")
        actions_layout.addWidget(self._refresh_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        return card

    def _load_reference_data(self) -> None:
        try:
            self._account_lookup_options = self._service_registry.chart_of_accounts_service.list_account_lookup_options(
                self._company_id,
                active_only=True,
            )
        except Exception as exc:
            self._set_error(f"Accounts could not be loaded.\n\n{exc}")
            return

        self._account_combo.set_items(
            [(f"{account.account_code}  {account.account_name}", account.id) for account in self._account_lookup_options],
            placeholder="No mapped account",
        )

    def reload_mappings(self, selected_role_code: str | None = None) -> None:
        try:
            self._mappings = self._service_registry.account_role_mapping_service.list_role_mappings(self._company_id)
        except Exception as exc:
            self._mappings = []
            self._table.setRowCount(0)
            self._set_error(f"Account role mappings could not be loaded.\n\n{exc}")
            return

        self._set_error(None)
        self._populate_table()
        self._restore_selection(selected_role_code)
        self._sync_editor_state()

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        role_options_by_code = {
            option.role_code: option
            for option in self._role_options
        }

        for mapping in self._mappings:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            role_option = role_options_by_code[mapping.role_code]

            values = (
                mapping.role_label,
                role_option.description,
                f"{mapping.account_code}  {mapping.account_name}"
                if mapping.account_id is not None
                else "Unmapped",
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, mapping.role_code)
                self._table.setItem(row_index, column_index, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Stretch)
        self._table.setSortingEnabled(True)

    def _restore_selection(self, selected_role_code: str | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_role_code is None:
            self._table.selectRow(0)
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_role_code:
                self._table.selectRow(row_index)
                return
        self._table.selectRow(0)

    def _selected_mapping(self) -> AccountRoleMappingDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        role_item = self._table.item(current_row, 0)
        if role_item is None:
            return None
        role_code = role_item.data(Qt.ItemDataRole.UserRole)
        for mapping in self._mappings:
            if mapping.role_code == role_code:
                return mapping
        return None

    def _sync_editor_state(self) -> None:
        mapping = self._selected_mapping()
        has_selection = mapping is not None

        if mapping is None:
            self._role_value.setText("Select a role mapping")
            self._description_value.setText("")
            self._account_combo.clear_selection()
            self._save_button.setEnabled(False)
            self._clear_button.setEnabled(False)
            return

        role_option = next(
            option
            for option in self._role_options
            if option.role_code == mapping.role_code
        )
        self._role_value.setText(role_option.label)
        self._description_value.setText(role_option.description)
        self._select_account(mapping.account_id)
        self._save_button.setEnabled(has_selection and self._can_manage)
        self._clear_button.setEnabled(mapping.account_id is not None and self._can_manage)

    def _select_account(self, account_id: int | None) -> None:
        self._account_combo.set_current_value(account_id)

    def _selected_account_id(self) -> int | None:
        value = self._account_combo.current_value()
        return value if isinstance(value, int) and value > 0 else None

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def _save_mapping(self) -> None:
        if not self._can_manage:
            self._set_error(
                self._service_registry.permission_service.build_denied_message(
                    "reference.account_role_mappings.manage"
                )
            )
            return
        mapping = self._selected_mapping()
        if mapping is None:
            show_info(self, "Account Role Mappings", "Select a role to map.")
            return
        account_id = self._selected_account_id()
        if account_id is None:
            self._set_error("Select an account before saving, or use Clear Mapping.")
            return

        try:
            updated_mapping = self._service_registry.account_role_mapping_service.set_role_mapping(
                self._company_id,
                SetAccountRoleMappingCommand(role_code=mapping.role_code, account_id=account_id),
            )
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))
            return

        self.reload_mappings(selected_role_code=updated_mapping.role_code)

    def _clear_mapping(self) -> None:
        if not self._can_manage:
            self._set_error(
                self._service_registry.permission_service.build_denied_message(
                    "reference.account_role_mappings.manage"
                )
            )
            return
        mapping = self._selected_mapping()
        if mapping is None:
            return

        try:
            self._service_registry.account_role_mapping_service.clear_role_mapping(
                self._company_id,
                mapping.role_code,
            )
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))
            return

        self.reload_mappings(selected_role_code=mapping.role_code)
