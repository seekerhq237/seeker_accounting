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

from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountLookupDTO
from seeker_accounting.modules.accounting.reference_data.dto.tax_code_account_mapping_dto import (
    SetTaxCodeAccountMappingCommand,
    TaxCodeAccountMappingDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_info
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


class TaxCodeAccountMappingDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._mappings: list[TaxCodeAccountMappingDTO] = []
        self._account_lookup_options: list[AccountLookupDTO] = []

        super().__init__("Tax Code Account Mappings", parent, help_key="dialog.tax_code_account_mapping")
        self.setObjectName("TaxCodeAccountMappingDialog")
        apply_window_size(self, "modules.accounting.reference.data.ui.tax.code.account.mapping.dialog.0")

        intro_label = QLabel(
            "Bind tax codes to real chart accounts so later sales, purchases, and tax settlement workflows have disciplined account references.",
            self,
        )
        intro_label.setObjectName("PageSummary")
        intro_label.setWordWrap(True)
        self.body_layout.addWidget(intro_label)

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

        title = QLabel("Current Tax Mappings", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._model = QStandardItemModel(0, 6, card)
        self._model.setHorizontalHeaderLabels(
            ["Code", "Name", "Sales", "Purchase", "Tax Liability", "Tax Asset"]
        )
        self._table = DataTable(
            columns=(
                DataTableColumn(key="code", title="Code"),
                DataTableColumn(key="name", title="Name"),
                DataTableColumn(key="sales", title="Sales"),
                DataTableColumn(key="purchase", title="Purchase"),
                DataTableColumn(key="liability", title="Tax Liability"),
                DataTableColumn(key="asset", title="Tax Asset"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._table.set_model(self._model)
        self._table.view().doubleClicked.connect(lambda *_: self._sales_account_combo.setFocus())
        layout.addWidget(self._table)
        return card

    def _build_editor_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Selected Tax Code", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._tax_code_value = QLabel("Select a tax code mapping", card)
        self._tax_code_value.setObjectName("ValueLabel")
        grid.addWidget(create_field_block("Tax Code", self._tax_code_value), 0, 0)

        self._tax_name_value = QLabel("", card)
        self._tax_name_value.setObjectName("ToolbarMeta")
        self._tax_name_value.setWordWrap(True)
        grid.addWidget(create_field_block("Name", self._tax_name_value), 0, 1)

        self._sales_account_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Sales Account", self._sales_account_combo), 1, 0)

        self._purchase_account_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Purchase Account", self._purchase_account_combo), 1, 1)

        self._tax_liability_account_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Tax Liability Account", self._tax_liability_account_combo), 2, 0)

        self._tax_asset_account_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Tax Asset Account", self._tax_asset_account_combo), 2, 1)

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

        account_items = [
            (f"{account.account_code}  {account.account_name}", account.id)
            for account in self._account_lookup_options
        ]
        combo_boxes = (
            self._sales_account_combo,
            self._purchase_account_combo,
            self._tax_liability_account_combo,
            self._tax_asset_account_combo,
        )
        for combo_box in combo_boxes:
            combo_box.set_items(account_items, placeholder="Unmapped")

    def reload_mappings(self, selected_tax_code_id: int | None = None) -> None:
        try:
            self._mappings = self._service_registry.tax_setup_service.list_tax_code_account_mappings(
                self._company_id
            )
        except Exception as exc:
            self._mappings = []
            self._model.removeRows(0, self._model.rowCount())
            self._set_error(f"Tax code account mappings could not be loaded.\n\n{exc}")
            self._sync_editor_state()
            return

        self._set_error(None)
        self._populate_table()
        self._restore_selection(selected_tax_code_id)
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
        for mapping in self._mappings:
            self._model.appendRow([
                self._make_item(mapping.tax_code_code, user_data=mapping.tax_code_id),
                self._make_item(mapping.tax_code_name),
                self._make_item(self._account_label(mapping.sales_account_code, mapping.sales_account_name)),
                self._make_item(self._account_label(mapping.purchase_account_code, mapping.purchase_account_name)),
                self._make_item(self._account_label(mapping.tax_liability_account_code, mapping.tax_liability_account_name)),
                self._make_item(self._account_label(mapping.tax_asset_account_code, mapping.tax_asset_account_name)),
            ])

    def _restore_selection(self, selected_tax_code_id: int | None) -> None:
        if not self._mappings:
            return
        if selected_tax_code_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, m in enumerate(self._mappings) if m.tax_code_id == selected_tax_code_id),
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

    def _selected_mapping(self) -> TaxCodeAccountMappingDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        row = rows[0]
        if row < 0 or row >= len(self._mappings):
            return None
        return self._mappings[row]

    def _sync_editor_state(self) -> None:
        mapping = self._selected_mapping()
        if mapping is None:
            self._tax_code_value.setText("Select a tax code mapping")
            self._tax_name_value.setText("")
            self._select_account(self._sales_account_combo, None)
            self._select_account(self._purchase_account_combo, None)
            self._select_account(self._tax_liability_account_combo, None)
            self._select_account(self._tax_asset_account_combo, None)
            self._save_button.setEnabled(False)
            self._clear_button.setEnabled(False)
            return

        self._tax_code_value.setText(mapping.tax_code_code)
        self._tax_name_value.setText(mapping.tax_code_name)
        self._select_account(self._sales_account_combo, mapping.sales_account_id)
        self._select_account(self._purchase_account_combo, mapping.purchase_account_id)
        self._select_account(self._tax_liability_account_combo, mapping.tax_liability_account_id)
        self._select_account(self._tax_asset_account_combo, mapping.tax_asset_account_id)
        self._save_button.setEnabled(True)
        self._clear_button.setEnabled(
            any(
                account_id is not None
                for account_id in (
                    mapping.sales_account_id,
                    mapping.purchase_account_id,
                    mapping.tax_liability_account_id,
                    mapping.tax_asset_account_id,
                )
            )
        )

    def _select_account(self, combo_box: SearchableComboBox, account_id: int | None) -> None:
        combo_box.set_current_value(account_id)

    def _selected_account_id(self, combo_box: SearchableComboBox) -> int | None:
        value = combo_box.current_value()
        return value if isinstance(value, int) and value > 0 else None

    def _account_label(self, account_code: str | None, account_name: str | None) -> str:
        if account_code is None or account_name is None:
            return "Unmapped"
        return f"{account_code}  {account_name}"

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def _save_mapping(self) -> None:
        mapping = self._selected_mapping()
        if mapping is None:
            show_info(self, "Tax Code Account Mappings", "Select a tax code to map.")
            return

        try:
            updated_mapping = self._service_registry.tax_setup_service.set_tax_code_account_mapping(
                self._company_id,
                SetTaxCodeAccountMappingCommand(
                    tax_code_id=mapping.tax_code_id,
                    sales_account_id=self._selected_account_id(self._sales_account_combo),
                    purchase_account_id=self._selected_account_id(self._purchase_account_combo),
                    tax_liability_account_id=self._selected_account_id(self._tax_liability_account_combo),
                    tax_asset_account_id=self._selected_account_id(self._tax_asset_account_combo),
                ),
            )
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))
            return

        self.reload_mappings(selected_tax_code_id=updated_mapping.tax_code_id)

    def _clear_mapping(self) -> None:
        mapping = self._selected_mapping()
        if mapping is None:
            return

        try:
            self._service_registry.tax_setup_service.clear_tax_code_account_mapping(
                self._company_id,
                mapping.tax_code_id,
            )
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))
            return

        self.reload_mappings(selected_tax_code_id=mapping.tax_code_id)
