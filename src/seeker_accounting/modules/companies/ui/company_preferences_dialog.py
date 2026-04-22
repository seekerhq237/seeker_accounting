from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_commands import (
    UpdateCompanyPreferencesCommand,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error

_log = logging.getLogger(__name__)

_DATE_FORMATS = [
    ("DMY_SLASH", "DD/MM/YYYY"),
    ("MDY_SLASH", "MM/DD/YYYY"),
    ("YMD_DASH", "YYYY-MM-DD"),
    ("DMY_DOT", "DD.MM.YYYY"),
]

_NUMBER_FORMATS = [
    ("SPACE_COMMA", "1 234,56"),
    ("COMMA_DOT", "1,234.56"),
    ("DOT_COMMA", "1.234,56"),
    ("SPACE_DOT", "1 234.56"),
]

_COST_METHODS = [
    ("", "— Not specified —"),
    ("FIFO", "FIFO (First In, First Out)"),
    ("WEIGHTED_AVERAGE", "Weighted Average"),
]


class CompanyPreferencesDialog(QDialog):
    """Modal dialog for editing company operational preferences."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._company_id = company_id

        self.setWindowTitle(f"Company Preferences — {company_name}")
        self.setModal(True)
        self.resize(480, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Formatting card ───────────────────────────────────────────────
        fmt_card = QFrame(self)
        fmt_card.setObjectName("PageCard")
        fmt_form = QFormLayout(fmt_card)
        fmt_form.setContentsMargins(18, 16, 18, 16)
        fmt_form.setSpacing(10)
        fmt_hdr = QLabel("Formatting", fmt_card)
        fmt_hdr.setObjectName("CardTitle")
        fmt_form.addRow(fmt_hdr)

        self._date_format_combo = QComboBox(fmt_card)
        for code, label in _DATE_FORMATS:
            self._date_format_combo.addItem(label, code)
        fmt_form.addRow("Date Format *", self._date_format_combo)

        self._number_format_combo = QComboBox(fmt_card)
        for code, label in _NUMBER_FORMATS:
            self._number_format_combo.addItem(label, code)
        fmt_form.addRow("Number Format *", self._number_format_combo)

        self._decimal_spin = QSpinBox(fmt_card)
        self._decimal_spin.setMinimum(0)
        self._decimal_spin.setMaximum(6)
        self._decimal_spin.setValue(2)
        fmt_form.addRow("Decimal Places *", self._decimal_spin)

        self._tax_inclusive_check = QCheckBox("Tax inclusive by default", fmt_card)
        fmt_form.addRow(self._tax_inclusive_check)

        layout.addWidget(fmt_card)

        # ── Inventory card ────────────────────────────────────────────────
        inv_card = QFrame(self)
        inv_card.setObjectName("PageCard")
        inv_form = QFormLayout(inv_card)
        inv_form.setContentsMargins(18, 16, 18, 16)
        inv_form.setSpacing(10)
        inv_hdr = QLabel("Inventory", inv_card)
        inv_hdr.setObjectName("CardTitle")
        inv_form.addRow(inv_hdr)

        self._negative_stock_check = QCheckBox("Allow negative stock", inv_card)
        inv_form.addRow(self._negative_stock_check)

        self._cost_method_combo = QComboBox(inv_card)
        for code, label in _COST_METHODS:
            self._cost_method_combo.addItem(label, code)
        inv_form.addRow("Default Cost Method", self._cost_method_combo)

        layout.addWidget(inv_card)

        # ── Session security card ─────────────────────────────────────────
        sec_card = QFrame(self)
        sec_card.setObjectName("PageCard")
        sec_form = QFormLayout(sec_card)
        sec_form.setContentsMargins(18, 16, 18, 16)
        sec_form.setSpacing(10)
        sec_hdr = QLabel("Session Security", sec_card)
        sec_hdr.setObjectName("CardTitle")
        sec_form.addRow(sec_hdr)

        self._idle_timeout_spin = QSpinBox(sec_card)
        self._idle_timeout_spin.setMinimum(1)
        self._idle_timeout_spin.setMaximum(480)
        self._idle_timeout_spin.setValue(2)
        self._idle_timeout_spin.setSuffix(" minutes")
        sec_form.addRow("Idle logout after *", self._idle_timeout_spin)

        idle_note = QLabel(
            "Users will see a 30-second warning before automatic logout.",
            sec_card,
        )
        idle_note.setObjectName("FieldHint")
        idle_note.setWordWrap(True)
        sec_form.addRow(idle_note)

        self._password_expiry_spin = QSpinBox(sec_card)
        self._password_expiry_spin.setMinimum(0)
        self._password_expiry_spin.setMaximum(365)
        self._password_expiry_spin.setValue(30)
        self._password_expiry_spin.setSuffix(" days")
        sec_form.addRow("Password expiry *", self._password_expiry_spin)

        expiry_note = QLabel(
            "Set to 0 to disable password expiry. Users with expired passwords will be prompted to change on login.",
            sec_card,
        )
        expiry_note.setObjectName("FieldHint")
        expiry_note.setWordWrap(True)
        sec_form.addRow(expiry_note)

        layout.addWidget(sec_card)

        # ── Error + buttons ───────────────────────────────────────────────
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

        self._load_existing()
        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.company_preferences")
    # ── Data loading ──────────────────────────────────────────────────

    def _load_existing(self) -> None:
        try:
            prefs = self._sr.company_service.get_company_preferences(self._company_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._set_combo_value(self._date_format_combo, prefs.date_format_code)
        self._set_combo_value(self._number_format_combo, prefs.number_format_code)
        self._decimal_spin.setValue(prefs.decimal_places)
        self._tax_inclusive_check.setChecked(prefs.tax_inclusive_default)
        self._negative_stock_check.setChecked(prefs.allow_negative_stock)
        self._set_combo_value(self._cost_method_combo, prefs.default_inventory_cost_method or "")
        self._idle_timeout_spin.setValue(prefs.idle_timeout_minutes)
        self._password_expiry_spin.setValue(prefs.password_expiry_days)

    def _set_combo_value(self, combo: QComboBox, value: str | None) -> None:
        if value is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    # ── Submit ────────────────────────────────────────────────────────

    def _submit(self) -> None:
        self._error_label.hide()

        date_format = self._date_format_combo.currentData()
        number_format = self._number_format_combo.currentData()
        cost_method = self._cost_method_combo.currentData() or None

        if not date_format:
            self._show_error("Date format is required.")
            return
        if not number_format:
            self._show_error("Number format is required.")
            return

        try:
            self._sr.company_service.update_company_preferences(
                self._company_id,
                UpdateCompanyPreferencesCommand(
                    date_format_code=date_format,
                    number_format_code=number_format,
                    decimal_places=self._decimal_spin.value(),
                    tax_inclusive_default=self._tax_inclusive_check.isChecked(),
                    allow_negative_stock=self._negative_stock_check.isChecked(),
                    default_inventory_cost_method=cost_method,
                    idle_timeout_minutes=self._idle_timeout_spin.value(),
                    password_expiry_days=self._password_expiry_spin.value(),
                ),
            )
            # If saved idle timeout applies to the currently active company, update the watcher
            active_cid = self._sr.active_company_context.company_id
            if active_cid == self._company_id:
                self._sr.session_idle_watcher_service.update_timeout(
                    self._idle_timeout_spin.value()
                )
            self.accept()
        except ValidationError as exc:
            self._show_error(str(exc))
        except Exception as exc:
            show_error(self, "Company Preferences", f"Could not save preferences.\n\n{exc}")

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
