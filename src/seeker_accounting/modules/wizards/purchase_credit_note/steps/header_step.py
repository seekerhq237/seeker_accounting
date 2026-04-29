"""Step 1 — Header (supplier, date, currency, optional source bill, reason)."""
from __future__ import annotations

from datetime import date as _date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.purchase_credit_note import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class HeaderStep(WizardStep):
    key = "header"
    title = "Header"
    subtitle = "Supplier, credit date, currency, and optional source bill."

    def __init__(self) -> None:
        super().__init__()
        self._supplier: QComboBox | None = None
        self._date: QDateEdit | None = None
        self._currency: QLineEdit | None = None
        self._source_bill: QComboBox | None = None
        self._reason: QTextEdit | None = None
        self._supplier_ref: QLineEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._supplier = QComboBox(root)
        form.addRow(QLabel("Supplier:", root), self._supplier)

        self._date = QDateEdit(root)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate.currentDate())
        form.addRow(QLabel("Credit date:", root), self._date)

        self._currency = QLineEdit(root)
        self._currency.setMaxLength(3)
        self._currency.setPlaceholderText("USD")
        form.addRow(QLabel("Currency:", root), self._currency)

        self._source_bill = QComboBox(root)
        form.addRow(QLabel("Source bill (optional):", root), self._source_bill)

        self._supplier_ref = QLineEdit(root)
        self._supplier_ref.setPlaceholderText("Supplier credit memo number (optional)")
        form.addRow(QLabel("Supplier reference:", root), self._supplier_ref)

        self._reason = QTextEdit(root)
        self._reason.setMaximumHeight(60)
        form.addRow(QLabel("Reason:", root), self._reason)

        outer.addLayout(form)
        outer.addStretch(1)

        if self._supplier is not None:
            self._supplier.currentIndexChanged.connect(self._on_supplier_changed)
        return root

    def _on_supplier_changed(self, _idx: int) -> None:
        # Refresh source-bill list when the supplier changes.
        if self._source_bill is None or self._supplier is None:
            return
        self._source_bill.clear()
        self._source_bill.addItem("(none)", None)

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        if self._supplier is not None and self._supplier.count() == 0:
            self._supplier.addItem("(pick a supplier)", None)
            for s in context.service_registry.supplier_service.list_suppliers(
                company_id, active_only=True
            ):
                self._supplier.addItem(f"{s.supplier_code} \u2014 {s.display_name}", s.id)
            prior = state.get(K.KEY_SUPPLIER_ID)
            if isinstance(prior, int):
                idx = self._supplier.findData(prior)
                if idx >= 0:
                    self._supplier.setCurrentIndex(idx)
        # Refresh source bill list against current supplier
        sup_id = self._supplier.currentData() if self._supplier is not None else None
        if self._source_bill is not None:
            self._source_bill.clear()
            self._source_bill.addItem("(none)", None)
            if isinstance(sup_id, int):
                for bill in context.service_registry.purchase_bill_service.list_open_bills_for_supplier(
                    company_id, sup_id
                ):
                    self._source_bill.addItem(
                        f"{bill.bill_number} \u2014 {bill.total_amount} {bill.currency_code}",
                        bill.id,
                    )
                prior_bill = state.get(K.KEY_SOURCE_BILL_ID)
                if isinstance(prior_bill, int):
                    idx = self._source_bill.findData(prior_bill)
                    if idx >= 0:
                        self._source_bill.setCurrentIndex(idx)
        if self._date is not None:
            d = state.get(K.KEY_CREDIT_DATE)
            if isinstance(d, str):
                qd = QDate.fromString(d, "yyyy-MM-dd")
                if qd.isValid():
                    self._date.setDate(qd)
        if self._currency is not None:
            self._currency.setText(str(state.get(K.KEY_CURRENCY_CODE) or "USD"))
        if self._supplier_ref is not None and state.get(K.KEY_SUPPLIER_CREDIT_REFERENCE):
            self._supplier_ref.setText(str(state[K.KEY_SUPPLIER_CREDIT_REFERENCE]))
        if self._reason is not None and state.get(K.KEY_REASON_TEXT):
            self._reason.setPlainText(str(state[K.KEY_REASON_TEXT]))

    def write_back(self, state: WizardState) -> None:
        if self._supplier is not None:
            data = self._supplier.currentData()
            new_sup = int(data) if isinstance(data, int) else None
            if new_sup != state.get(K.KEY_SUPPLIER_ID):
                # supplier changed — invalidate stale source-bill + lines
                state[K.KEY_SOURCE_BILL_ID] = None
                state[K.KEY_LINES] = []
            state[K.KEY_SUPPLIER_ID] = new_sup
        if self._date is not None:
            state[K.KEY_CREDIT_DATE] = self._date.date().toString("yyyy-MM-dd")
        if self._currency is not None:
            state[K.KEY_CURRENCY_CODE] = self._currency.text().strip().upper() or "USD"
        if self._source_bill is not None:
            data = self._source_bill.currentData()
            state[K.KEY_SOURCE_BILL_ID] = int(data) if isinstance(data, int) else None
        if self._supplier_ref is not None:
            state[K.KEY_SUPPLIER_CREDIT_REFERENCE] = self._supplier_ref.text().strip() or None
        if self._reason is not None:
            state[K.KEY_REASON_TEXT] = self._reason.toPlainText().strip() or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_SUPPLIER_ID), int):
            return StepValidationResult.fail("Pick a supplier.")
        cc = state.get(K.KEY_CURRENCY_CODE)
        if not cc or len(str(cc)) != 3:
            return StepValidationResult.fail("Currency must be a 3-letter ISO code.")
        d = state.get(K.KEY_CREDIT_DATE)
        if not d:
            return StepValidationResult.fail("Credit date is required.")
        try:
            _date.fromisoformat(str(d))
        except ValueError:
            return StepValidationResult.fail("Credit date is invalid.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        sup = state.get(K.KEY_SUPPLIER_ID)
        d = state.get(K.KEY_CREDIT_DATE)
        if sup and d:
            return f"Credit note from supplier #{sup} on {d}"
        return None
