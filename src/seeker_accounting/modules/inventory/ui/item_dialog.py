from __future__ import annotations

import logging

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand, UpdateItemCommand
from seeker_accounting.modules.inventory.dto.item_dto import ItemDetailDTO
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class ItemDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        item_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._item_id = item_id
        self._saved_item: ItemDetailDTO | None = None

        is_edit = item_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Item — {company_name}")
        self.setModal(True)
        self.resize(580, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_form())

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._button_box.accepted.connect(self._handle_submit)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._load_reference_data()
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed()

        if is_edit:
            self._load_item()
        else:
            self._suggest_code()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.item")

    @property
    def saved_item(self) -> ItemDetailDTO | None:
        return self._saved_item

    @classmethod
    def create_item(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> ItemDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_item
        return None

    @classmethod
    def edit_item(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        item_id: int,
        parent: QWidget | None = None,
    ) -> ItemDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, item_id=item_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_item
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_form(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self._code_input = QLineEdit(card)
        self._code_input.setPlaceholderText("Unique item code")
        form.addRow("Item Code", self._code_input)

        self._name_input = QLineEdit(card)
        self._name_input.setPlaceholderText("Item name")
        form.addRow("Item Name", self._name_input)

        self._type_combo = QComboBox(card)
        self._type_combo.addItem("Stock", "stock")
        self._type_combo.addItem("Non-stock", "non_stock")
        self._type_combo.addItem("Service", "service")
        form.addRow("Item Type", self._type_combo)

        self._uom_combo = SearchableComboBox(card)
        form.addRow("Unit of Measure", self._uom_combo)

        self._category_combo = SearchableComboBox(card)
        form.addRow("Category", self._category_combo)

        self._cost_method_combo = QComboBox(card)
        self._cost_method_combo.addItem("Weighted Average", "weighted_average")
        form.addRow("Cost Method", self._cost_method_combo)

        self._inventory_account_combo = SearchableComboBox(card)
        form.addRow("Inventory Account", self._inventory_account_combo)

        self._cogs_account_combo = SearchableComboBox(card)
        form.addRow("COGS Account", self._cogs_account_combo)

        self._expense_account_combo = SearchableComboBox(card)
        form.addRow("Expense Account", self._expense_account_combo)

        self._revenue_account_combo = SearchableComboBox(card)
        form.addRow("Revenue Account", self._revenue_account_combo)

        self._reorder_level_input = QLineEdit(card)
        self._reorder_level_input.setPlaceholderText("Optional reorder level quantity")
        form.addRow("Reorder Level", self._reorder_level_input)

        self._description_input = QPlainTextEdit(card)
        self._description_input.setMaximumHeight(60)
        self._description_input.setPlaceholderText("Optional description")
        form.addRow("Description", self._description_input)

        self._active_checkbox = QCheckBox("Active", card)
        self._active_checkbox.setChecked(True)
        form.addRow("", self._active_checkbox)

        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("item", self._company_id)
            self._code_input.setText(code)
        except Exception:
            pass

    def _load_reference_data(self) -> None:
        # Units of measure
        try:
            uoms = self._service_registry.unit_of_measure_service.list_units_of_measure(
                self._company_id, active_only=True
            )
        except Exception:
            uoms = []
        if not uoms:
            self._uom_combo.set_items([], placeholder="(No units of measure defined)")
        else:
            self._uom_combo.set_items(
                [(f"{uom.code} — {uom.name}", uom.id) for uom in uoms],
                placeholder="Select unit of measure",
            )

        # Item categories
        try:
            cats = self._service_registry.item_category_service.list_item_categories(
                self._company_id, active_only=True
            )
        except Exception:
            cats = []
        self._category_combo.set_items(
            [(f"{cat.code} — {cat.name}", cat.id) for cat in cats],
            placeholder="(None)",
        )

        # Accounts
        try:
            accounts = self._service_registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
        except Exception:
            accounts = []

        account_items = [(f"{acc.account_code} — {acc.account_name}", acc.id) for acc in accounts]
        for combo in (
            self._inventory_account_combo,
            self._cogs_account_combo,
            self._expense_account_combo,
            self._revenue_account_combo,
        ):
            combo.set_items(account_items, placeholder="(None)")

    def _load_item(self) -> None:
        if self._item_id is None:
            return
        try:
            item = self._service_registry.item_service.get_item(self._company_id, self._item_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._code_input.setText(item.item_code)
        self._name_input.setText(item.item_name)
        self._set_combo_by_data(self._type_combo, item.item_type_code)
        self._uom_combo.set_current_value(item.unit_of_measure_id)
        self._category_combo.set_current_value(item.item_category_id)
        if item.inventory_cost_method_code:
            self._set_combo_by_data(self._cost_method_combo, item.inventory_cost_method_code)
        self._inventory_account_combo.set_current_value(item.inventory_account_id)
        self._cogs_account_combo.set_current_value(item.cogs_account_id)
        self._expense_account_combo.set_current_value(item.expense_account_id)
        self._revenue_account_combo.set_current_value(item.revenue_account_id)
        if item.reorder_level_quantity is not None:
            self._reorder_level_input.setText(str(item.reorder_level_quantity))
        if item.description:
            self._description_input.setPlainText(item.description)
        self._active_checkbox.setChecked(item.is_active)
        self._on_type_changed()

    def _on_type_changed(self) -> None:
        is_stock = self._type_combo.currentData() == "stock"
        self._cost_method_combo.setEnabled(is_stock)
        self._inventory_account_combo.setEnabled(is_stock)
        self._cogs_account_combo.setEnabled(is_stock)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        item_code = self._code_input.text().strip()
        item_name = self._name_input.text().strip()
        item_type_code = self._type_combo.currentData()
        uom_id = self._uom_combo.current_value()
        category_id = self._category_combo.current_value()
        cost_method = self._cost_method_combo.currentData() if item_type_code == "stock" else None
        inv_acct = self._inventory_account_combo.current_value() if item_type_code == "stock" else None
        cogs_acct = self._cogs_account_combo.current_value() if item_type_code == "stock" else None
        expense_acct = self._expense_account_combo.current_value()
        revenue_acct = self._revenue_account_combo.current_value()

        if uom_id is None:
            self._show_error("Select a unit of measure. Create one in Inventory → Units of Measure first.")
            return

        reorder_level: Decimal | None = None
        reorder_text = self._reorder_level_input.text().strip()
        if reorder_text:
            try:
                reorder_level = Decimal(reorder_text)
            except InvalidOperation:
                self._show_error("Reorder level must be a valid number.")
                return

        description = self._description_input.toPlainText().strip() or None

        try:
            if self._item_id is None:
                result = self._service_registry.item_service.create_item(
                    self._company_id,
                    CreateItemCommand(
                        item_code=item_code,
                        item_name=item_name,
                        item_type_code=item_type_code,
                        unit_of_measure_id=uom_id,
                        item_category_id=category_id,
                        inventory_cost_method_code=cost_method,
                        inventory_account_id=inv_acct,
                        cogs_account_id=cogs_acct,
                        expense_account_id=expense_acct,
                        revenue_account_id=revenue_acct,
                        purchase_tax_code_id=None,
                        sales_tax_code_id=None,
                        reorder_level_quantity=reorder_level,
                        description=description,
                    ),
                )
            else:
                result = self._service_registry.item_service.update_item(
                    self._company_id,
                    self._item_id,
                    UpdateItemCommand(
                        item_code=item_code,
                        item_name=item_name,
                        item_type_code=item_type_code,
                        unit_of_measure_id=uom_id,
                        item_category_id=category_id,
                        inventory_cost_method_code=cost_method,
                        inventory_account_id=inv_acct,
                        cogs_account_id=cogs_acct,
                        expense_account_id=expense_acct,
                        revenue_account_id=revenue_acct,
                        purchase_tax_code_id=None,
                        sales_tax_code_id=None,
                        reorder_level_quantity=reorder_level,
                        description=description,
                        is_active=self._active_checkbox.isChecked(),
                    ),
                )
            self._saved_item = result
            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _set_combo_by_data(self, combo: QComboBox, value: object) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
