from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox
from PySide6.QtGui import QIcon

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import (
    CreateAccountCommand,
    UpdateAccountCommand,
)
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import (
    AccountDetailDTO,
    AccountListItemDTO,
    AccountLookupDTO,
)
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import (
    AccountClassDTO,
    AccountTypeDTO,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error


class AccountFormDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        account_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._account_id = account_id
        self._saved_account: AccountDetailDTO | None = None
        self._loaded_account: AccountDetailDTO | None = None
        self._account_classes: list[AccountClassDTO] = []
        self._account_types: list[AccountTypeDTO] = []
        self._account_lookup_options: list[AccountLookupDTO] = []
        self._excluded_parent_account_ids: set[int] = set()

        title = "New Account" if account_id is None else "Edit Account"
        super().__init__(title, parent, help_key="dialog.account_form")
        self.setObjectName("AccountFormDialog")
        self.resize(680, 490)

        # Remove intro label and company row, add compact company label
        company_label = QLabel(company_name, self)
        company_label.setObjectName("DialogSectionSummary")
        self.body_layout.addWidget(company_label)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_structure_section())
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("ProfileMenuSeparator")
        self.body_layout.addWidget(sep)
        self.body_layout.addWidget(self._build_classification_section())
        self.body_layout.addStretch(1)

        # --- Wiring: buttons, data loading ---
        self._balance_dirty = False

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        self._save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if self._save_button is not None:
            self._save_button.setText("Create Account" if account_id is None else "Save Changes")
            self._save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._load_reference_data()
        if self._account_id is not None:
            self._load_account()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def saved_account(self) -> AccountDetailDTO | None:
        return self._saved_account

    @classmethod
    def create_account(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> AccountDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_account
        return None

    @classmethod
    def edit_account(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        account_id: int,
        parent: QWidget | None = None,
    ) -> AccountDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, account_id=account_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_account
        return None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _build_structure_section(self) -> QWidget:
        card = QWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = QLabel("Structure", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._account_code_edit = QLineEdit(card)
        self._account_code_edit.setPlaceholderText("401")
        grid.addWidget(create_field_block("Account Code", self._account_code_edit), 0, 0)

        self._account_name_edit = QLineEdit(card)
        self._account_name_edit.setPlaceholderText("Suppliers")
        grid.addWidget(create_field_block("Account Name", self._account_name_edit), 0, 1)

        self._parent_account_combo = SearchableComboBox(card)
        grid.addWidget(
            create_field_block(
                "Parent Account",
                self._parent_account_combo,
                None,
            ),
            1,
            0,
            1,
            2,
        )

        layout.addLayout(grid)
        return card

    def _build_classification_section(self) -> QWidget:
        card = QWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = QLabel("Classification And Controls", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._account_class_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Account Class", self._account_class_combo), 0, 0)

        self._account_type_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Account Type", self._account_type_combo), 0, 1)

        self._normal_balance_combo = QComboBox(card)
        self._normal_balance_combo.addItem("DEBIT", "DEBIT")
        self._normal_balance_combo.addItem("CREDIT", "CREDIT")
        grid.addWidget(create_field_block("Normal Balance", self._normal_balance_combo), 1, 0)

        self._allow_manual_posting_checkbox = QCheckBox("Allow manual posting", card)
        self._allow_manual_posting_checkbox.setChecked(True)
        grid.addWidget(self._allow_manual_posting_checkbox, 1, 1)

        self._control_account_checkbox = QCheckBox("Control account", card)
        grid.addWidget(self._control_account_checkbox, 2, 0)

        self._active_checkbox = QCheckBox("Account is active", card)
        self._active_checkbox.setChecked(True)
        self._active_checkbox.setVisible(self._account_id is not None)
        grid.addWidget(self._active_checkbox, 2, 1)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setPlaceholderText("Optional note for chart reviewers")
        self._notes_edit.setFixedHeight(56)
        grid.addWidget(create_field_block("Notes", self._notes_edit), 3, 0, 1, 2)

        layout.addLayout(grid)
        return card

    def _load_reference_data(self) -> None:
        try:
            self._service_registry.chart_seed_service.ensure_global_chart_reference_seed()
            self._account_classes = self._service_registry.reference_data_service.list_account_classes()
            self._account_types = self._service_registry.reference_data_service.list_account_types()
            if self._account_id is not None:
                self._excluded_parent_account_ids = self._collect_descendant_ids(
                    self._service_registry.chart_of_accounts_service.list_accounts(
                        self._company_id,
                        active_only=False,
                    ),
                    self._account_id,
                )
            self._account_lookup_options = self._service_registry.chart_of_accounts_service.list_account_lookup_options(
                self._company_id,
                active_only=False,
                exclude_account_id=self._account_id,
            )
            if self._excluded_parent_account_ids:
                self._account_lookup_options = [
                    account
                    for account in self._account_lookup_options
                    if account.id not in self._excluded_parent_account_ids
                ]
        except Exception as exc:
            self._set_error(f"Chart references could not be loaded.\n\n{exc}")
            return

        self._populate_account_class_combo()
        self._populate_account_type_combo()
        self._populate_parent_account_combo()
        self._sync_normal_balance_from_account_type()

    def _load_account(self) -> None:
        try:
            account = self._service_registry.chart_of_accounts_service.get_account(
                self._company_id,
                self._account_id or 0,
            )
        except NotFoundError as exc:
            show_error(self, "Account Not Found", str(exc))
            self.reject()
            return

        self._loaded_account = account
        self._account_code_edit.setText(account.account_code)
        self._account_name_edit.setText(account.account_name)
        self._parent_account_combo.set_current_value(account.parent_account_id)
        self._account_class_combo.set_current_value(account.account_class_id)
        self._account_type_combo.set_current_value(account.account_type_id)
        self._select_combo_data(self._normal_balance_combo, account.normal_balance)
        self._allow_manual_posting_checkbox.setChecked(account.allow_manual_posting)
        self._control_account_checkbox.setChecked(account.is_control_account)
        self._active_checkbox.setChecked(account.is_active)
        self._notes_edit.setPlainText(account.notes or "")
        self._balance_dirty = False

    def _populate_account_class_combo(self) -> None:
        self._account_class_combo.set_items(
            [(f"{ac.code}  {ac.name}", ac.id) for ac in self._account_classes],
            placeholder="Select account class",
        )

    def _populate_account_type_combo(self) -> None:
        self._account_type_combo.set_items(
            [(f"{at.code}  {at.name}", at.id) for at in self._account_types],
            placeholder="Select account type",
        )

    def _populate_parent_account_combo(self) -> None:
        items = []
        for account in self._account_lookup_options:
            label = f"{account.account_code}  {account.account_name}"
            if not account.is_active:
                label = f"{label}  (inactive)"
            items.append((label, account.id))
        self._parent_account_combo.set_items(items, placeholder="Top-level account")

    def _collect_descendant_ids(
        self,
        accounts: list[AccountListItemDTO],
        root_account_id: int,
    ) -> set[int]:
        children_by_parent_id: dict[int | None, list[int]] = {}
        for account in accounts:
            children_by_parent_id.setdefault(account.parent_account_id, []).append(account.id)

        descendant_ids: set[int] = set()
        pending_ids = list(children_by_parent_id.get(root_account_id, ()))
        while pending_ids:
            account_id = pending_ids.pop()
            if account_id in descendant_ids:
                continue
            descendant_ids.add(account_id)
            pending_ids.extend(children_by_parent_id.get(account_id, ()))
        return descendant_ids

    def _select_combo_data(self, combo_box: QComboBox, value: object) -> None:
        index = combo_box.findData(value)
        combo_box.setCurrentIndex(index if index >= 0 else 0)

    def _selected_text(self, combo_box: QComboBox) -> str:
        value = combo_box.currentData()
        return value if isinstance(value, str) else combo_box.currentText().strip()

    def _selected_account_type(self) -> AccountTypeDTO | None:
        account_type_id = self._account_type_combo.current_value()
        if account_type_id is None:
            return None
        for account_type in self._account_types:
            if account_type.id == account_type_id:
                return account_type
        return None

    def _sync_normal_balance_from_account_type(self) -> None:
        if self._balance_dirty and self._loaded_account is not None:
            return
        account_type = self._selected_account_type()
        if account_type is None:
            return
        self._select_combo_data(self._normal_balance_combo, account_type.normal_balance)

    def _mark_balance_dirty(self, _value: str) -> None:
        self._balance_dirty = True

    def _sync_save_state(self) -> None:
        if self._save_button is None:
            return
        self._save_button.setEnabled(bool(self._account_classes) and bool(self._account_types))

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return

        self._error_label.setText(message)
        self._error_label.show()

    def _handle_submit(self) -> None:
        self._set_error(None)

        account_code = self._account_code_edit.text().strip()
        account_name = self._account_name_edit.text().strip()
        account_class_id = self._account_class_combo.current_value()
        account_type_id = self._account_type_combo.current_value()
        normal_balance = self._selected_text(self._normal_balance_combo).strip().upper()

        if not account_code:
            self._set_error("Account code is required.")
            self._account_code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not account_name:
            self._set_error("Account name is required.")
            self._account_name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if account_class_id is None:
            self._set_error("Account class is required.")
            self._account_class_combo.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if account_type_id is None:
            self._set_error("Account type is required.")
            self._account_type_combo.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if normal_balance not in {"DEBIT", "CREDIT"}:
            self._set_error("Normal balance must be DEBIT or CREDIT.")
            self._normal_balance_combo.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        if self._account_id is None:
            command = CreateAccountCommand(
                account_code=account_code,
                account_name=account_name,
                account_class_id=account_class_id,
                account_type_id=account_type_id,
                normal_balance=normal_balance,
                allow_manual_posting=self._allow_manual_posting_checkbox.isChecked(),
                is_control_account=self._control_account_checkbox.isChecked(),
                parent_account_id=self._parent_account_combo.current_value(),
                notes=self._notes_edit.toPlainText().strip() or None,
            )
            save_operation = lambda: self._service_registry.chart_of_accounts_service.create_account(
                self._company_id,
                command,
            )
        else:
            command = UpdateAccountCommand(
                account_code=account_code,
                account_name=account_name,
                account_class_id=account_class_id,
                account_type_id=account_type_id,
                normal_balance=normal_balance,
                allow_manual_posting=self._allow_manual_posting_checkbox.isChecked(),
                is_control_account=self._control_account_checkbox.isChecked(),
                is_active=self._active_checkbox.isChecked(),
                parent_account_id=self._parent_account_combo.current_value(),
                notes=self._notes_edit.toPlainText().strip() or None,
            )
            save_operation = lambda: self._service_registry.chart_of_accounts_service.update_account(
                self._company_id,
                self._account_id,
                command,
            )

        try:
            self._saved_account = save_operation()
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Account Not Found", str(exc))
            return

        self.accept()
