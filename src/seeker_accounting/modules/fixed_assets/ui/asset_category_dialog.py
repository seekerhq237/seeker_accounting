from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.fixed_assets.dto.asset_category_commands import (
    CreateAssetCategoryCommand,
    UpdateAssetCategoryCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_category_dto import AssetCategoryDetailDTO
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)

_METHODS = [
    ("straight_line", "Straight Line"),
    ("reducing_balance", "Reducing Balance (DDB)"),
    ("sum_of_years_digits", "Sum of Years Digits"),
]


class AssetCategoryDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        category_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._category_id = category_id
        self._saved: AssetCategoryDetailDTO | None = None

        is_edit = category_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Asset Category — {company_name}")
        self.setModal(True)
        self.resize(460, 460)
        self.setMinimumWidth(440)
        self.setMaximumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Basic details
        details_card = QFrame(self)
        details_card.setObjectName("PageCard")
        form = QFormLayout(details_card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self._code_input = QLineEdit(details_card)
        self._code_input.setPlaceholderText("Category code (e.g. EQUIP)")
        form.addRow("Code *", self._code_input)

        self._name_input = QLineEdit(details_card)
        self._name_input.setPlaceholderText("Category name")
        form.addRow("Name *", self._name_input)

        layout.addWidget(details_card)

        # Account mapping section
        acct_card = QFrame(self)
        acct_card.setObjectName("PageCard")
        acct_form = QFormLayout(acct_card)
        acct_form.setContentsMargins(18, 16, 18, 16)
        acct_form.setSpacing(10)

        acct_hdr = QLabel("Account Mapping", acct_card)
        acct_hdr.setObjectName("CardTitle")
        acct_form.addRow(acct_hdr)

        self._asset_account_combo = SearchableComboBox(acct_card)
        self._asset_account_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._asset_account_combo.setMinimumContentsLength(24)
        acct_form.addRow("Asset Account *", self._asset_account_combo)

        self._accum_depr_account_combo = SearchableComboBox(acct_card)
        self._accum_depr_account_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._accum_depr_account_combo.setMinimumContentsLength(24)
        acct_form.addRow("Accum. Depreciation Acct *", self._accum_depr_account_combo)

        self._depr_expense_account_combo = SearchableComboBox(acct_card)
        self._depr_expense_account_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._depr_expense_account_combo.setMinimumContentsLength(24)
        acct_form.addRow("Depreciation Expense Acct *", self._depr_expense_account_combo)

        layout.addWidget(acct_card)

        # Depreciation defaults section
        depr_card = QFrame(self)
        depr_card.setObjectName("PageCard")
        depr_form = QFormLayout(depr_card)
        depr_form.setContentsMargins(18, 16, 18, 16)
        depr_form.setSpacing(10)

        depr_hdr = QLabel("Depreciation Defaults", depr_card)
        depr_hdr.setObjectName("CardTitle")
        depr_form.addRow(depr_hdr)

        self._life_input = QSpinBox(depr_card)
        self._life_input.setMinimum(1)
        self._life_input.setMaximum(999)
        self._life_input.setSuffix(" months")
        self._life_input.setValue(60)
        depr_form.addRow("Default Useful Life *", self._life_input)

        self._method_combo = QComboBox(depr_card)
        for code, label in _METHODS:
            self._method_combo.addItem(label, code)
        depr_form.addRow("Default Method *", self._method_combo)

        if is_edit:
            self._active_checkbox = QCheckBox("Active", depr_card)
            self._active_checkbox.setChecked(True)
            depr_form.addRow("Status", self._active_checkbox)

        layout.addWidget(depr_card)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_accounts()
        if is_edit:
            self._load_existing()
        else:
            self._suggest_code()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.asset_category")

    @property
    def saved(self) -> AssetCategoryDetailDTO | None:
        return self._saved

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("asset_category", self._company_id)
            self._code_input.setText(code)
        except Exception:
            pass

    def _load_accounts(self) -> None:
        try:
            accounts = self._service_registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        account_items = [(f"{acct.account_code} — {acct.account_name}", acct.id) for acct in accounts]
        for combo in (self._asset_account_combo, self._accum_depr_account_combo, self._depr_expense_account_combo):
            combo.set_items(account_items, placeholder="— Select account —")

    def _load_existing(self) -> None:
        if self._category_id is None:
            return
        try:
            cat = self._service_registry.asset_category_service.get_asset_category(
                self._company_id, self._category_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._code_input.setText(cat.code)
        self._name_input.setText(cat.name)
        self._asset_account_combo.set_current_value(cat.asset_account_id)
        self._accum_depr_account_combo.set_current_value(cat.accumulated_depreciation_account_id)
        self._depr_expense_account_combo.set_current_value(cat.depreciation_expense_account_id)
        self._life_input.setValue(cat.default_useful_life_months)
        idx = self._method_combo.findData(cat.default_depreciation_method_code)
        if idx >= 0:
            self._method_combo.setCurrentIndex(idx)
        if hasattr(self, "_active_checkbox"):
            self._active_checkbox.setChecked(cat.is_active)

    def _submit(self) -> None:
        self._error_label.hide()
        code = self._code_input.text().strip()
        name = self._name_input.text().strip()
        asset_acct = self._asset_account_combo.current_value()
        accum_acct = self._accum_depr_account_combo.current_value()
        depr_acct = self._depr_expense_account_combo.current_value()
        life = self._life_input.value()
        method = self._method_combo.currentData()
        is_active = self._active_checkbox.isChecked() if hasattr(self, "_active_checkbox") else True

        if asset_acct is None or accum_acct is None or depr_acct is None:
            self._show_error("All three account mappings are required.")
            return

        try:
            svc = self._service_registry.asset_category_service
            if self._category_id is None:
                self._saved = svc.create_asset_category(
                    self._company_id,
                    CreateAssetCategoryCommand(
                        code=code,
                        name=name,
                        asset_account_id=asset_acct,
                        accumulated_depreciation_account_id=accum_acct,
                        depreciation_expense_account_id=depr_acct,
                        default_useful_life_months=life,
                        default_depreciation_method_code=method,
                    ),
                )
            else:
                self._saved = svc.update_asset_category(
                    self._company_id,
                    self._category_id,
                    UpdateAssetCategoryCommand(
                        code=code,
                        name=name,
                        asset_account_id=asset_acct,
                        accumulated_depreciation_account_id=accum_acct,
                        depreciation_expense_account_id=depr_acct,
                        default_useful_life_months=life,
                        default_depreciation_method_code=method,
                        is_active=is_active,
                    ),
                )
            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
