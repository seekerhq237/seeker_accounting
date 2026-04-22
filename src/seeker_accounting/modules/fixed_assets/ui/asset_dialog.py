from __future__ import annotations

import logging

from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.fixed_assets.dto.asset_commands import CreateAssetCommand, UpdateAssetCommand
from seeker_accounting.modules.fixed_assets.dto.asset_depreciation_settings_commands import (
    UpsertAssetDepreciationSettingsCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_dto import AssetDetailDTO
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)

_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("active", "Active"),
    ("fully_depreciated", "Fully Depreciated"),
    ("disposed", "Disposed"),
]

# Settings panel page indices
_PAGE_NONE = 0
_PAGE_DB = 1       # declining-balance family
_PAGE_UOP = 2      # units of production / depletion
_PAGE_INTEREST = 3  # annuity / sinking fund
_PAGE_MACRS = 4

_DB_METHODS = frozenset({
    "declining_balance", "double_declining_balance",
    "declining_balance_150", "reducing_balance",
})
_UOP_METHODS = frozenset({"units_of_production", "depletion"})
_INTEREST_METHODS = frozenset({"annuity", "sinking_fund"})

_DB_DEFAULT_FACTORS = {
    "declining_balance": 1.0,
    "double_declining_balance": 2.0,
    "declining_balance_150": 1.5,
    "reducing_balance": 2.0,
}


class AssetDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        asset_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._asset_id = asset_id
        self._saved: AssetDetailDTO | None = None

        is_edit = asset_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Asset — {company_name}")
        self.setModal(True)
        self.resize(560, 0)  # width hint; height will size-to-content via adjustSize

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # ── Identity ──────────────────────────────────────────────────
        id_card = QFrame(self)
        id_card.setObjectName("PageCard")
        id_form = QFormLayout(id_card)
        id_form.setContentsMargins(14, 10, 14, 10)
        id_form.setSpacing(6)

        self._number_input = QLineEdit(id_card)
        self._number_input.setPlaceholderText("Unique asset number")
        id_form.addRow("Asset Number *", self._number_input)

        self._name_input = QLineEdit(id_card)
        self._name_input.setPlaceholderText("Asset description")
        id_form.addRow("Asset Name *", self._name_input)

        self._category_combo = SearchableComboBox(id_card)
        id_form.addRow("Category *", self._category_combo)

        if is_edit:
            self._status_combo = QComboBox(id_card)
            for code, label in _STATUS_CHOICES:
                self._status_combo.addItem(label, code)
            id_form.addRow("Status", self._status_combo)

        layout.addWidget(id_card)

        # ── Acquisition & Depreciation (2-column) ─────────────────────
        acq_depr_card = QFrame(self)
        acq_depr_card.setObjectName("PageCard")
        acq_depr_grid = QGridLayout(acq_depr_card)
        acq_depr_grid.setContentsMargins(14, 10, 14, 10)
        acq_depr_grid.setHorizontalSpacing(14)
        acq_depr_grid.setVerticalSpacing(3)
        acq_depr_grid.setColumnStretch(0, 1)
        acq_depr_grid.setColumnStretch(1, 1)

        # Row 0: Acquisition header
        acq_hdr = QLabel("Acquisition", acq_depr_card)
        acq_hdr.setObjectName("CardTitle")
        acq_depr_grid.addWidget(acq_hdr, 0, 0, 1, 2)

        # Row 1: Acquisition Date | Capitalization Date
        acq_date_lbl = QLabel("Acquisition Date *", acq_depr_card)
        acq_date_lbl.setProperty("role", "caption")
        acq_depr_grid.addWidget(acq_date_lbl, 1, 0)
        self._acq_date_input = QDateEdit(acq_depr_card)
        self._acq_date_input.setCalendarPopup(True)
        self._acq_date_input.setDate(QDate.currentDate())
        acq_depr_grid.addWidget(self._acq_date_input, 2, 0)

        cap_date_lbl = QLabel("Capitalization Date *", acq_depr_card)
        cap_date_lbl.setProperty("role", "caption")
        acq_depr_grid.addWidget(cap_date_lbl, 1, 1)
        self._cap_date_input = QDateEdit(acq_depr_card)
        self._cap_date_input.setCalendarPopup(True)
        self._cap_date_input.setDate(QDate.currentDate())
        acq_depr_grid.addWidget(self._cap_date_input, 2, 1)

        # Row 3: Acquisition Cost | Salvage Value
        cost_lbl = QLabel("Acquisition Cost *", acq_depr_card)
        cost_lbl.setProperty("role", "caption")
        acq_depr_grid.addWidget(cost_lbl, 3, 0)
        self._cost_input = QDoubleSpinBox(acq_depr_card)
        self._cost_input.setMinimum(0.01)
        self._cost_input.setMaximum(9_999_999_999.99)
        self._cost_input.setDecimals(2)
        self._cost_input.setGroupSeparatorShown(True)
        acq_depr_grid.addWidget(self._cost_input, 4, 0)

        salvage_lbl = QLabel("Salvage Value", acq_depr_card)
        salvage_lbl.setProperty("role", "caption")
        acq_depr_grid.addWidget(salvage_lbl, 3, 1)
        self._salvage_input = QDoubleSpinBox(acq_depr_card)
        self._salvage_input.setMinimum(0.0)
        self._salvage_input.setMaximum(9_999_999_999.99)
        self._salvage_input.setDecimals(2)
        self._salvage_input.setGroupSeparatorShown(True)
        acq_depr_grid.addWidget(self._salvage_input, 4, 1)

        # Row 5: Depreciation header
        depr_hdr = QLabel("Depreciation", acq_depr_card)
        depr_hdr.setObjectName("CardTitle")
        acq_depr_grid.addWidget(depr_hdr, 5, 0, 1, 2)

        # Row 6: Useful Life | Method
        life_lbl = QLabel("Useful Life *", acq_depr_card)
        life_lbl.setProperty("role", "caption")
        acq_depr_grid.addWidget(life_lbl, 6, 0)
        method_lbl = QLabel("Method *", acq_depr_card)
        method_lbl.setProperty("role", "caption")
        acq_depr_grid.addWidget(method_lbl, 6, 1)

        life_row = QWidget(acq_depr_card)
        life_layout = QHBoxLayout(life_row)
        life_layout.setContentsMargins(0, 0, 0, 0)
        life_layout.setSpacing(6)
        self._life_years = QSpinBox(life_row)
        self._life_years.setMinimum(0)
        self._life_years.setMaximum(99)
        self._life_years.setSuffix(" yr")
        self._life_years.setFixedWidth(76)
        self._life_extra_months = QSpinBox(life_row)
        self._life_extra_months.setMinimum(0)
        self._life_extra_months.setMaximum(11)
        self._life_extra_months.setSuffix(" mo")
        self._life_extra_months.setFixedWidth(76)
        life_layout.addWidget(self._life_years)
        life_layout.addWidget(self._life_extra_months)
        life_layout.addStretch(1)
        acq_depr_grid.addWidget(life_row, 7, 0)

        self._method_combo = QComboBox(acq_depr_card)
        acq_depr_grid.addWidget(self._method_combo, 7, 1)

        layout.addWidget(acq_depr_card)

        # ── Method-specific settings ──────────────────────────────────
        self._settings_card = QFrame(self)
        self._settings_card.setObjectName("PageCard")
        settings_outer = QVBoxLayout(self._settings_card)
        settings_outer.setContentsMargins(14, 10, 14, 10)
        settings_outer.setSpacing(6)
        settings_hdr = QLabel("Method Settings", self._settings_card)
        settings_hdr.setObjectName("CardTitle")
        settings_outer.addWidget(settings_hdr)

        self._settings_stack = QStackedWidget(self._settings_card)
        settings_outer.addWidget(self._settings_stack)

        # Page 0: no settings
        page_none = QWidget()
        none_form = QFormLayout(page_none)
        none_form.setContentsMargins(0, 0, 0, 0)
        none_lbl = QLabel("No additional settings required for this method.")
        none_lbl.setProperty("role", "caption")
        none_form.addRow(none_lbl)
        self._settings_stack.addWidget(page_none)  # index 0

        # Page 1: declining balance
        page_db = QWidget()
        db_form = QFormLayout(page_db)
        db_form.setContentsMargins(0, 0, 0, 0)
        db_form.setSpacing(8)
        self._db_factor = QDoubleSpinBox(page_db)
        self._db_factor.setMinimum(0.01)
        self._db_factor.setMaximum(4.0)
        self._db_factor.setDecimals(2)
        self._db_factor.setSingleStep(0.1)
        self._db_factor.setToolTip("1.0 = DB  |  1.5 = 150% DB  |  2.0 = DDB")
        db_form.addRow("Declining Factor", self._db_factor)
        self._db_switch_sl = QCheckBox("Switch to straight-line when SL charge exceeds DB", page_db)
        db_form.addRow("", self._db_switch_sl)
        self._settings_stack.addWidget(page_db)  # index 1

        # Page 2: units of production / depletion
        page_uop = QWidget()
        uop_form = QFormLayout(page_uop)
        uop_form.setContentsMargins(0, 0, 0, 0)
        uop_form.setSpacing(8)
        self._uop_total_units = QDoubleSpinBox(page_uop)
        self._uop_total_units.setMinimum(1.0)
        self._uop_total_units.setMaximum(999_999_999.0)
        self._uop_total_units.setDecimals(2)
        self._uop_total_units.setGroupSeparatorShown(True)
        self._uop_total_units.setToolTip("Total expected production / resource units over asset life")
        uop_form.addRow("Expected Total Units *", self._uop_total_units)
        self._settings_stack.addWidget(page_uop)  # index 2

        # Page 3: annuity / sinking fund
        page_interest = QWidget()
        interest_form = QFormLayout(page_interest)
        interest_form.setContentsMargins(0, 0, 0, 0)
        interest_form.setSpacing(8)
        self._interest_rate_pct = QDoubleSpinBox(page_interest)
        self._interest_rate_pct.setMinimum(0.001)
        self._interest_rate_pct.setMaximum(99.999)
        self._interest_rate_pct.setDecimals(3)
        self._interest_rate_pct.setSingleStep(0.1)
        self._interest_rate_pct.setSuffix(" % / month")
        self._interest_rate_pct.setToolTip("e.g. 0.5 = 0.5% per month (6% p.a.)")
        interest_form.addRow("Monthly Interest Rate *", self._interest_rate_pct)
        self._settings_stack.addWidget(page_interest)  # index 3

        # Page 4: MACRS
        page_macrs = QWidget()
        macrs_form = QFormLayout(page_macrs)
        macrs_form.setContentsMargins(0, 0, 0, 0)
        macrs_form.setSpacing(8)
        self._macrs_profile_combo = SearchableComboBox(page_macrs)
        macrs_form.addRow("GDS Recovery Profile *", self._macrs_profile_combo)
        self._settings_stack.addWidget(page_macrs)  # index 4

        self._settings_card.hide()
        layout.addWidget(self._settings_card)

        # ── Notes (no card wrapper) ───────────────────────────────────
        notes_row = QHBoxLayout()
        notes_row.setContentsMargins(4, 0, 4, 0)
        notes_row.setSpacing(8)
        notes_lbl = QLabel("Notes", self)
        notes_lbl.setProperty("role", "caption")
        notes_row.addWidget(notes_lbl)
        self._notes_input = QPlainTextEdit(self)
        self._notes_input.setMaximumHeight(40)
        self._notes_input.setPlaceholderText("Optional notes…")
        notes_row.addWidget(self._notes_input, 1)
        layout.addLayout(notes_row)

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

        # ── Load dynamic data ─────────────────────────────────────────
        self._load_methods()
        self._load_macrs_profiles()
        self._load_categories()
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        if is_edit:
            self._load_existing()
        else:
            self._suggest_code()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.asset")

        self.adjustSize()  # shrink-wrap to actual content height

    @property
    def saved(self) -> AssetDetailDTO | None:
        return self._saved

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("asset", self._company_id)
            self._number_input.setText(code)
        except Exception:
            pass

    def _load_methods(self) -> None:
        """Populate method combo from seeded catalog; exclude INTANGIBLE-family methods."""
        try:
            methods = self._service_registry.depreciation_method_service.list_methods(active_only=True)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._method_combo.clear()
        for m in methods:
            if m.asset_family_code == "INTANGIBLE":
                continue
            self._method_combo.addItem(m.name, m.code)

    def _load_macrs_profiles(self) -> None:
        try:
            profiles = self._service_registry.depreciation_method_service.list_macrs_profiles()
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._macrs_profile_combo.set_items(
            [
                (f"{p.class_name}  ({p.convention_code.replace('_', ' ').title()})", p.id)
                for p in profiles
            ],
            placeholder="— Select MACRS profile —",
        )

    def _load_categories(self) -> None:
        try:
            cats = self._service_registry.asset_category_service.list_asset_categories(
                self._company_id, active_only=True
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._category_combo.set_items(
            [(f"{cat.code} — {cat.name}", cat.id) for cat in cats],
            placeholder="— Select category —",
        )
        self._category_combo.value_changed.connect(self._on_category_changed)

    def _load_existing(self) -> None:
        if self._asset_id is None:
            return
        try:
            asset = self._service_registry.asset_service.get_asset(self._company_id, self._asset_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._number_input.setText(asset.asset_number)
        self._name_input.setText(asset.asset_name)

        self._category_combo.blockSignals(True)
        self._category_combo.set_current_value(asset.asset_category_id)
        self._category_combo.blockSignals(False)

        if hasattr(self, "_status_combo"):
            sidx = self._status_combo.findData(asset.status_code)
            if sidx >= 0:
                self._status_combo.setCurrentIndex(sidx)

        self._acq_date_input.setDate(
            QDate(asset.acquisition_date.year, asset.acquisition_date.month, asset.acquisition_date.day)
        )
        self._cap_date_input.setDate(
            QDate(asset.capitalization_date.year, asset.capitalization_date.month, asset.capitalization_date.day)
        )
        self._cost_input.setValue(float(asset.acquisition_cost))
        if asset.salvage_value is not None:
            self._salvage_input.setValue(float(asset.salvage_value))
        self._set_life_from_months(asset.useful_life_months)

        midx = self._method_combo.findData(asset.depreciation_method_code)
        if midx >= 0:
            self._method_combo.blockSignals(True)
            self._method_combo.setCurrentIndex(midx)
            self._method_combo.blockSignals(False)

        self._notes_input.setPlainText(asset.notes or "")
        self._load_method_settings(asset.depreciation_method_code)

    def _load_method_settings(self, method_code: str) -> None:
        page = self._settings_page_for(method_code)
        if page == _PAGE_NONE:
            self._settings_card.hide()
            return
        self._settings_stack.setCurrentIndex(page)
        self._settings_card.show()

        if page == _PAGE_DB and method_code in _DB_DEFAULT_FACTORS:
            self._db_factor.setValue(_DB_DEFAULT_FACTORS[method_code])

        if self._asset_id is None:
            return
        try:
            settings = self._service_registry.asset_depreciation_settings_service.get_settings(
                self._company_id, self._asset_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        if settings is None:
            return

        if page == _PAGE_DB:
            if settings.declining_factor is not None:
                self._db_factor.setValue(float(settings.declining_factor))
            self._db_switch_sl.setChecked(settings.switch_to_straight_line or False)
        elif page == _PAGE_UOP:
            if settings.expected_total_units is not None:
                self._uop_total_units.setValue(float(settings.expected_total_units))
        elif page == _PAGE_INTEREST:
            if settings.interest_rate is not None:
                self._interest_rate_pct.setValue(float(settings.interest_rate) * 100.0)
        elif page == _PAGE_MACRS:
            if settings.macrs_profile_id is not None:
                self._macrs_profile_combo.set_current_value(settings.macrs_profile_id)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _on_category_changed(self, _value: object) -> None:
        cat_id = self._category_combo.current_value()
        if cat_id is None:
            return
        try:
            cat = self._service_registry.asset_category_service.get_asset_category(
                self._company_id, cat_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._set_life_from_months(cat.default_useful_life_months)
        idx = self._method_combo.findData(cat.default_depreciation_method_code)
        if idx >= 0:
            self._method_combo.setCurrentIndex(idx)

    def _on_method_changed(self, index: int) -> None:
        method_code = self._method_combo.currentData()
        if method_code is None:
            self._settings_card.hide()
            return
        page = self._settings_page_for(method_code)
        if page == _PAGE_NONE:
            self._settings_card.hide()
        else:
            self._settings_stack.setCurrentIndex(page)
            if page == _PAGE_DB and method_code in _DB_DEFAULT_FACTORS:
                self._db_factor.setValue(_DB_DEFAULT_FACTORS[method_code])
            self._settings_card.show()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _settings_page_for(self, method_code: str) -> int:
        if method_code in _DB_METHODS:
            return _PAGE_DB
        if method_code in _UOP_METHODS:
            return _PAGE_UOP
        if method_code in _INTEREST_METHODS:
            return _PAGE_INTEREST
        if method_code == "macrs":
            return _PAGE_MACRS
        return _PAGE_NONE

    def _get_total_months(self) -> int:
        return self._life_years.value() * 12 + self._life_extra_months.value()

    def _set_life_from_months(self, months: int) -> None:
        self._life_years.blockSignals(True)
        self._life_extra_months.blockSignals(True)
        self._life_years.setValue(months // 12)
        self._life_extra_months.setValue(months % 12)
        self._life_years.blockSignals(False)
        self._life_extra_months.blockSignals(False)

    def _build_settings_command(self, method_code: str) -> UpsertAssetDepreciationSettingsCommand | None:
        page = self._settings_page_for(method_code)
        if page == _PAGE_NONE:
            return None
        if page == _PAGE_DB:
            return UpsertAssetDepreciationSettingsCommand(
                declining_factor=Decimal(str(round(self._db_factor.value(), 2))),
                switch_to_straight_line=self._db_switch_sl.isChecked(),
            )
        if page == _PAGE_UOP:
            return UpsertAssetDepreciationSettingsCommand(
                expected_total_units=Decimal(str(round(self._uop_total_units.value(), 2))),
            )
        if page == _PAGE_INTEREST:
            rate = Decimal(str(round(self._interest_rate_pct.value() / 100.0, 6)))
            return UpsertAssetDepreciationSettingsCommand(interest_rate=rate)
        if page == _PAGE_MACRS:
            profile_id = self._macrs_profile_combo.current_value()
            if profile_id is None:
                raise ValidationError("Please select a MACRS recovery profile.")
            return UpsertAssetDepreciationSettingsCommand(macrs_profile_id=profile_id)
        return None

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        self._error_label.hide()
        asset_number = self._number_input.text().strip()
        asset_name = self._name_input.text().strip()
        cat_id = self._category_combo.current_value()
        acq_d = self._acq_date_input.date().toPython()
        cap_d = self._cap_date_input.date().toPython()
        cost = Decimal(str(self._cost_input.value()))
        salvage = Decimal(str(self._salvage_input.value()))
        salvage_val = None if salvage == Decimal("0") else salvage
        life = self._get_total_months()
        method = self._method_combo.currentData()
        notes = self._notes_input.toPlainText().strip() or None

        if cat_id is None:
            self._show_error("Asset category is required.")
            return
        if life <= 0:
            self._show_error("Useful life must be at least 1 month.")
            return

        try:
            settings_cmd = self._build_settings_command(method)
        except ValidationError as exc:
            self._show_error(str(exc))
            return

        try:
            svc = self._service_registry.asset_service
            settings_svc = self._service_registry.asset_depreciation_settings_service

            if self._asset_id is None:
                self._saved = svc.create_asset(
                    self._company_id,
                    CreateAssetCommand(
                        asset_number=asset_number,
                        asset_name=asset_name,
                        asset_category_id=cat_id,
                        acquisition_date=acq_d,
                        capitalization_date=cap_d,
                        acquisition_cost=cost,
                        salvage_value=salvage_val,
                        useful_life_months=life,
                        depreciation_method_code=method,
                        notes=notes,
                    ),
                )
                if settings_cmd is not None and self._saved is not None:
                    settings_svc.upsert_settings(self._company_id, self._saved.id, settings_cmd)
            else:
                status_code = self._status_combo.currentData() if hasattr(self, "_status_combo") else "active"
                self._saved = svc.update_asset(
                    self._company_id,
                    self._asset_id,
                    UpdateAssetCommand(
                        asset_number=asset_number,
                        asset_name=asset_name,
                        asset_category_id=cat_id,
                        acquisition_date=acq_d,
                        capitalization_date=cap_d,
                        acquisition_cost=cost,
                        salvage_value=salvage_val,
                        useful_life_months=life,
                        depreciation_method_code=method,
                        status_code=status_code,
                        notes=notes,
                    ),
                )
                if settings_cmd is not None:
                    settings_svc.upsert_settings(self._company_id, self._asset_id, settings_cmd)
                else:
                    # Method changed to one that needs no settings — clear any stored settings
                    settings_svc.delete_settings(self._company_id, self._asset_id)

            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
