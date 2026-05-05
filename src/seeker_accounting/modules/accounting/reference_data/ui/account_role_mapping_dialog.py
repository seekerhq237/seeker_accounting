from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


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
        apply_window_size(self, "modules.accounting.reference.data.ui.account.role.mapping.dialog.0")

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
        self._table.selection_changed.connect(lambda _rows: self._sync_editor_state())

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

        self._model = QStandardItemModel(0, 3, card)
        self._model.setHorizontalHeaderLabels(["Role", "Description", "Mapped Account"])
        self._table = DataTable(
            columns=(
                DataTableColumn(key="role", title="Role"),
                DataTableColumn(key="description", title="Description"),
                DataTableColumn(key="account", title="Mapped Account"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._table.set_model(self._model)
        self._table.view().doubleClicked.connect(lambda *_: self._account_combo.setFocus())
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
            self._model.removeRows(0, self._model.rowCount())
            self._set_error(f"Account role mappings could not be loaded.\n\n{exc}")
            return

        self._set_error(None)
        self._populate_table()
        self._restore_selection(selected_role_code)
        self._sync_editor_state()

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        role_options_by_code = {
            option.role_code: option
            for option in self._role_options
        }
        for mapping in self._mappings:
            role_option = role_options_by_code[mapping.role_code]
            account_text = (
                f"{mapping.account_code}  {mapping.account_name}"
                if mapping.account_id is not None
                else "Unmapped"
            )
            self._model.appendRow([
                self._make_item(mapping.role_label, user_data=mapping.role_code),
                self._make_item(role_option.description),
                self._make_item(account_text),
            ])

    def _restore_selection(self, selected_role_code: str | None) -> None:
        if not self._mappings:
            return
        if selected_role_code is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, m in enumerate(self._mappings) if m.role_code == selected_role_code),
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
        sm.select(proxy_index, sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows)
        self._table.view().scrollTo(proxy_index)

    def _selected_mapping(self) -> AccountRoleMappingDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        row = rows[0]
        if row < 0 or row >= len(self._mappings):
            return None
        return self._mappings[row]

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
