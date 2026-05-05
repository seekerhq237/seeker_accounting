"""Deferral dialog — create a new deferral schedule."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.deferrals.dto.deferral_dto import (
    CreateDeferralScheduleCommand,
)
from seeker_accounting.modules.accounting.deferrals.models.deferral_schedule import (
    DEFERRAL_TYPE_EXPENSE,
    DEFERRAL_TYPE_REVENUE,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error


class _AccountCombo(QComboBox):
    """A combo that holds (display_text, account_id) pairs."""

    def current_account_id(self) -> int | None:
        idx = self.currentIndex()
        if idx < 0:
            return None
        return self.itemData(idx)


class DeferralDialog(QDialog):
    """Create a new deferral schedule.

    On acceptance, the caller should read ``new_schedule_id``.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self.new_schedule_id: int | None = None

        self.setWindowTitle("New Deferral Schedule")
        self.setMinimumWidth(440)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(16)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(form)

        # Type
        self._type_combo = QComboBox(self)
        self._type_combo.addItem("Prepaid Expense (Charges constatées d'avance)", DEFERRAL_TYPE_EXPENSE)
        self._type_combo.addItem("Unearned Revenue (Produits constatés d'avance)", DEFERRAL_TYPE_REVENUE)
        self._type_combo.currentIndexChanged.connect(self._refresh_account_hints)
        form.addRow("Type:", self._type_combo)

        # Description
        self._description_edit = QLineEdit(self)
        self._description_edit.setPlaceholderText("e.g. Annual software licence Jan–Dec 2025")
        form.addRow("Description:", self._description_edit)

        # Reference
        self._reference_edit = QLineEdit(self)
        self._reference_edit.setPlaceholderText("Optional reference / doc number")
        form.addRow("Reference:", self._reference_edit)

        # Total amount
        self._amount_edit = QLineEdit(self)
        self._amount_edit.setPlaceholderText("0.00")
        form.addRow("Total amount:", self._amount_edit)

        # Holding account
        self._holding_label = QLabel("Holding account (476):", self)
        self._holding_combo = _AccountCombo(self)
        form.addRow(self._holding_label, self._holding_combo)

        # Recognition account
        self._recognition_label = QLabel("Recognition account (expense):", self)
        self._recognition_combo = _AccountCombo(self)
        form.addRow(self._recognition_label, self._recognition_combo)

        # Start date
        self._start_date = QDateEdit(self)
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("dd/MM/yyyy")
        self._start_date.setDate(QDate.currentDate().addDays(1 - QDate.currentDate().day()))
        form.addRow("Start date:", self._start_date)

        # Period count
        self._period_spin = QSpinBox(self)
        self._period_spin.setRange(1, 120)
        self._period_spin.setValue(12)
        self._period_spin.setSuffix(" month(s)")
        form.addRow("Periods:", self._period_spin)

        # Notes
        self._notes_edit = QPlainTextEdit(self)
        self._notes_edit.setMaximumHeight(72)
        self._notes_edit.setPlaceholderText("Optional notes…")
        form.addRow("Notes:", self._notes_edit)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._load_accounts()
        self._refresh_account_hints()

    # ── Private ───────────────────────────────────────────────────────

    def _load_accounts(self) -> None:
        try:
            coa_service = self._service_registry.chart_of_accounts_service
            accounts = coa_service.list_accounts(self._company_id)
        except Exception:
            return

        for combo in (self._holding_combo, self._recognition_combo):
            combo.clear()
            combo.addItem("— Select account —", None)
            for acct in accounts:
                combo.addItem(f"{acct.account_code}  {acct.account_name}", acct.id)

    def _refresh_account_hints(self) -> None:
        if self._type_combo.currentData() == DEFERRAL_TYPE_EXPENSE:
            self._holding_label.setText("Holding account (476 — prepaid):")
            self._recognition_label.setText("Recognition account (expense):")
        else:
            self._holding_label.setText("Holding account (477 — unearned):")
            self._recognition_label.setText("Recognition account (revenue):")

    def _accept(self) -> None:
        try:
            amount_text = self._amount_edit.text().strip().replace(",", "")
            if not amount_text:
                raise ValidationError("Total amount is required.")
            total_amount = Decimal(amount_text)
        except Exception:
            show_error(self, "Invalid amount", "Please enter a valid numeric amount.")
            return

        holding_id = self._holding_combo.current_account_id()
        recognition_id = self._recognition_combo.current_account_id()

        if holding_id is None or recognition_id is None:
            show_error(self, "Missing accounts", "Please select both the holding account and the recognition account.")
            return

        qd = self._start_date.date()
        start = date(qd.year(), qd.month(), qd.day())

        cmd = CreateDeferralScheduleCommand(
            company_id=self._company_id,
            deferral_type=self._type_combo.currentData(),
            description=self._description_edit.text().strip(),
            total_amount=total_amount,
            recognition_account_id=recognition_id,
            holding_account_id=holding_id,
            start_date=start,
            period_count=self._period_spin.value(),
            reference_text=self._reference_edit.text().strip() or None,
            notes=self._notes_edit.toPlainText().strip() or None,
            created_by_user_id=self._service_registry.app_context.current_user_id,
        )

        try:
            deferral_service = self._service_registry.deferral_service
            self.new_schedule_id = deferral_service.create_schedule(cmd)
            self.accept()
        except ValidationError as exc:
            show_error(self, "Validation error", str(exc))
        except Exception as exc:
            show_error(self, "Error", f"Could not create deferral schedule: {exc}")
