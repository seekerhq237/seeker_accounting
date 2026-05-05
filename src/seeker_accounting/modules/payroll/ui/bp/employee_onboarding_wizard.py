"""Employee Onboarding Wizard — Phase 4 Slice 2.

Replaces the legacy ``employee_hire_wizard`` + ``employee_payroll_setup_wizard``
chain with a single threaded BP backed by
:class:`EmployeeOnboardingService`. Built on top of P1.S6 ``WizardShell``.

Steps (mirror the BP state machine):

1. Identity
2. Employment
3. Compensation
4. Payment
5. Statutory IDs
6. Components
7. Review

Each step widget is responsible for:

* ``read_payload() -> dict`` — collect fields into a JSON-able dict.
* ``set_payload(data: Mapping)`` — populate from server-side draft.

The host (``EmployeeOnboardingWizardDialog``) drives the BP service:
on Next, the current step's payload is persisted via ``update_step``,
then the BP transitions forward via ``transition_state``. On Finish,
``complete()`` materialises the Employee and closes the dialog.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Mapping

from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.payroll.dto.employee_onboarding_dto import (
    EmployeeOnboardingDraftDTO,
    EmployeeOnboardingStartCommand,
    EmployeeOnboardingState,
    EmployeeOnboardingStepUpdate,
    EmployeeOnboardingTransition,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.components.inline_issue_band import ValidationIssue
from seeker_accounting.shared.ui.components.wizard_shell import (
    WizardShell,
    WizardStepDescriptor,
)
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

if TYPE_CHECKING:  # avoid runtime import — registry module pulls in the
    # full payroll service graph which may be partially staged.
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry

_log = logging.getLogger(__name__)


# ── Step IDs aligned with the BP state machine ─────────────────────────────


_STEP_IDENTITY = "identity"
_STEP_EMPLOYMENT = "employment"
_STEP_COMPENSATION = "compensation"
_STEP_PAYMENT = "payment"
_STEP_STATUTORY = "statutory"
_STEP_COMPONENTS = "components"
_STEP_REVIEW = "review"

_STEP_TO_STATE: dict[str, str] = {
    _STEP_IDENTITY: EmployeeOnboardingState.DRAFT_IDENTITY.value,
    _STEP_EMPLOYMENT: EmployeeOnboardingState.DRAFT_EMPLOYMENT.value,
    _STEP_COMPENSATION: EmployeeOnboardingState.DRAFT_COMPENSATION.value,
    _STEP_PAYMENT: EmployeeOnboardingState.DRAFT_PAYMENT.value,
    _STEP_STATUTORY: EmployeeOnboardingState.DRAFT_STATUTORY.value,
    _STEP_COMPONENTS: EmployeeOnboardingState.DRAFT_COMPONENTS.value,
    _STEP_REVIEW: EmployeeOnboardingState.DRAFT_REVIEW.value,
}

_STATE_TO_STEP: dict[str, str] = {v: k for k, v in _STEP_TO_STATE.items()}


# ── Component grid helpers ────────────────────────────────────────────────


@dataclass
class _ComponentRow:
    """Mutable row state for the component assignment grid."""

    dto: Any  # PayrollComponentListItemDTO — imported lazily
    included: bool = field(default=False)
    override_amount: str = field(default="")


class _ComponentsTableModel(QAbstractTableModel):
    """Table model backing the P4.S4 component assignment grid.

    Columns: Include (checkbox), Code, Name, Type, Calculation, Override amount.
    """

    _HEADERS = ("", "Code", "Name", "Type", "Calculation", "Override amount")
    _COL_INCLUDED = 0
    _COL_CODE = 1
    _COL_NAME = 2
    _COL_TYPE = 3
    _COL_METHOD = 4
    _COL_OVERRIDE = 5

    def __init__(self, rows: list[_ComponentRow], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows = rows

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return self._HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if col == self._COL_INCLUDED:
            if role == Qt.ItemDataRole.CheckStateRole:
                return (
                    Qt.CheckState.Checked
                    if row.included
                    else Qt.CheckState.Unchecked
                )
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self._COL_CODE:
                return row.dto.component_code
            if col == self._COL_NAME:
                return row.dto.component_name
            if col == self._COL_TYPE:
                return row.dto.component_type_code
            if col == self._COL_METHOD:
                return row.dto.calculation_method_code
            if col == self._COL_OVERRIDE:
                return row.override_amount if row.included else ""

        if role == Qt.ItemDataRole.EditRole:
            if col == self._COL_OVERRIDE and row.included:
                return row.override_amount

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self._COL_OVERRIDE:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        col = index.column()
        if col == self._COL_INCLUDED:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        if col == self._COL_OVERRIDE and self._rows[index.row()].included:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(
        self,
        index: QModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid():
            return False
        row = self._rows[index.row()]
        col = index.column()

        if col == self._COL_INCLUDED and role == Qt.ItemDataRole.CheckStateRole:
            checked = value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value, 2)
            row.included = checked
            if not checked:
                row.override_amount = ""
            self.dataChanged.emit(
                self.index(index.row(), 0),
                self.index(index.row(), self.columnCount() - 1),
                [Qt.ItemDataRole.CheckStateRole, Qt.ItemDataRole.DisplayRole],
            )
            return True

        if col == self._COL_OVERRIDE and role == Qt.ItemDataRole.EditRole and row.included:
            row.override_amount = str(value or "").strip()
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            return True

        return False


# ── Step widget base ───────────────────────────────────────────────────────


class _StepWidget(QFrame):
    """Common base for onboarding step content widgets."""

    payload_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WizardStepContent")
        spacing = DEFAULT_TOKENS.spacing
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._inner = QWidget()
        self._scroll.setWidget(self._inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._scroll, 1)

        self._form = QFormLayout(self._inner)
        self._form.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        self._form.setSpacing(spacing.dialog_section_gap)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    def read_payload(self) -> dict[str, Any]:  # pragma: no cover - override
        return {}

    def set_payload(self, data: Mapping[str, Any]) -> None:  # pragma: no cover - override
        return None


# ── Concrete step widgets ──────────────────────────────────────────────────


class _IdentityStep(_StepWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._first_name = QLineEdit()
        self._last_name = QLineEdit()
        self._display_name = QLineEdit()
        self._email = QLineEdit()
        self._phone = QLineEdit()
        for w in (
            self._first_name, self._last_name, self._display_name,
            self._email, self._phone,
        ):
            w.textChanged.connect(self.payload_changed)
        self._form.addRow("First name *", self._first_name)
        self._form.addRow("Last name *", self._last_name)
        self._form.addRow("Display name", self._display_name)
        self._form.addRow("Email", self._email)
        self._form.addRow("Phone", self._phone)

    def read_payload(self) -> dict[str, Any]:
        return {
            "first_name": self._first_name.text().strip(),
            "last_name": self._last_name.text().strip(),
            "display_name": self._display_name.text().strip(),
            "email": self._email.text().strip(),
            "phone": self._phone.text().strip(),
        }

    def set_payload(self, data: Mapping[str, Any]) -> None:
        self._first_name.setText(str(data.get("first_name") or ""))
        self._last_name.setText(str(data.get("last_name") or ""))
        self._display_name.setText(str(data.get("display_name") or ""))
        self._email.setText(str(data.get("email") or ""))
        self._phone.setText(str(data.get("phone") or ""))


class _EmploymentStep(_StepWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._employee_number = QLineEdit()
        self._hire_date = QDateEdit()
        self._hire_date.setDisplayFormat("yyyy-MM-dd")
        self._hire_date.setCalendarPopup(True)
        self._hire_date.setDate(QDate.currentDate())
        self._employee_number.textChanged.connect(self.payload_changed)
        self._hire_date.dateChanged.connect(self.payload_changed)
        self._form.addRow("Employee number *", self._employee_number)
        self._form.addRow("Hire date *", self._hire_date)

    def read_payload(self) -> dict[str, Any]:
        return {
            "employee_number": self._employee_number.text().strip(),
            "hire_date": self._hire_date.date().toString("yyyy-MM-dd"),
        }

    def set_payload(self, data: Mapping[str, Any]) -> None:
        self._employee_number.setText(str(data.get("employee_number") or ""))
        d = data.get("hire_date")
        if isinstance(d, str) and d:
            qd = QDate.fromString(d, "yyyy-MM-dd")
            if qd.isValid():
                self._hire_date.setDate(qd)


class _CompensationStep(_StepWidget):
    """P4.S3 — Initial compensation profile for a new hire.

    Captures the basic salary, effective dating, family quotient, and
    notes. The data is stored in the draft payload under the
    ``compensation`` key and materialised by
    ``EmployeeOnboardingService.complete()`` as an
    ``EmployeeCompensationProfile`` row.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from decimal import Decimal

        from PySide6.QtWidgets import QDoubleSpinBox  # local to avoid top-level Qt init

        from seeker_accounting.shared.ui.widgets.form_inputs import MoneyInput

        self._profile_name = QLineEdit()
        self._profile_name.setPlaceholderText("e.g. Initial salary 2025")

        self._currency = QComboBox()
        self._currency.setEditable(False)
        for code in ("XAF", "EUR", "USD"):
            self._currency.addItem(code)

        self._basic_salary: MoneyInput = MoneyInput(
            currency_code="XAF",
            fraction_digits=2,
            allow_negative=False,
            allow_zero=False,
            placeholder="0.00",
        )

        self._effective_from = QDateEdit()
        self._effective_from.setDisplayFormat("yyyy-MM-dd")
        self._effective_from.setCalendarPopup(True)
        self._effective_from.setDate(QDate.currentDate())

        self._number_of_parts: QDoubleSpinBox = QDoubleSpinBox()
        self._number_of_parts.setRange(1.0, 14.0)
        self._number_of_parts.setSingleStep(0.5)
        self._number_of_parts.setDecimals(1)
        self._number_of_parts.setValue(1.0)
        self._number_of_parts.setToolTip(
            "IRPP family quotient (quotient familial). "
            "1.0 = single, 2.0 = married or 1 child, etc."
        )

        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Optional notes")

        # Signals
        self._profile_name.textChanged.connect(self.payload_changed)
        self._currency.currentIndexChanged.connect(self._on_currency_changed)
        self._basic_salary.value_changed.connect(lambda *_: self.payload_changed.emit())
        self._effective_from.dateChanged.connect(self.payload_changed)
        self._number_of_parts.valueChanged.connect(self.payload_changed)
        self._notes.textChanged.connect(self.payload_changed)

        self._form.addRow("Compensation name *", self._profile_name)
        self._form.addRow("Currency *", self._currency)
        self._form.addRow("Basic salary *", self._basic_salary)
        self._form.addRow("Effective from *", self._effective_from)
        self._form.addRow("Family parts", self._number_of_parts)
        self._form.addRow("Notes", self._notes)

    def _on_currency_changed(self) -> None:
        self._basic_salary.set_currency(self._currency.currentText())
        self.payload_changed.emit()

    def read_payload(self) -> dict[str, Any]:
        salary = self._basic_salary.value()
        return {
            "base_currency_code": self._currency.currentText(),
            "profile_name": self._profile_name.text().strip(),
            "basic_salary": str(salary) if salary is not None else "",
            "effective_from": self._effective_from.date().toString("yyyy-MM-dd"),
            "number_of_parts": str(self._number_of_parts.value()),
            "notes": self._notes.text().strip(),
        }

    def set_payload(self, data: Mapping[str, Any]) -> None:
        from decimal import Decimal, InvalidOperation

        code = str(data.get("base_currency_code") or "XAF")
        idx = self._currency.findText(code)
        if idx >= 0:
            self._currency.setCurrentIndex(idx)

        self._profile_name.setText(str(data.get("profile_name") or ""))

        salary_str = str(data.get("basic_salary") or "").strip()
        if salary_str:
            try:
                self._basic_salary.set_value(Decimal(salary_str))
            except (InvalidOperation, ValueError):
                pass

        eff_str = str(data.get("effective_from") or "").strip()
        if eff_str:
            qd = QDate.fromString(eff_str, "yyyy-MM-dd")
            if qd.isValid():
                self._effective_from.setDate(qd)

        try:
            parts = float(data.get("number_of_parts") or 1.0)
            self._number_of_parts.setValue(parts)
        except (ValueError, TypeError):
            pass

        self._notes.setText(str(data.get("notes") or ""))


class _PaymentStep(_StepWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._method = QComboBox()
        self._method.addItem("Cash", "cash")
        self._method.addItem("Bank transfer", "bank")
        self._method.addItem("Mobile money", "mobile_money")
        self._method.currentIndexChanged.connect(self.payload_changed)
        self._account = QLineEdit()
        self._account.setPlaceholderText("Bank account ID (required if method = bank)")
        self._account.textChanged.connect(self.payload_changed)
        self._form.addRow("Payment method *", self._method)
        self._form.addRow("Default payment account", self._account)
        hint = QLabel(
            "How will this person be paid? A bank account is required "
            "for bank-paid employees."
        )
        hint.setWordWrap(True)
        hint.setObjectName("WizardStepHint")
        self._form.addRow(hint)

    def read_payload(self) -> dict[str, Any]:
        method = self._method.currentData() or "cash"
        account_text = self._account.text().strip()
        try:
            account_id: int | None = int(account_text) if account_text else None
        except ValueError:
            account_id = None
        return {
            "payment_method_code": str(method),
            "default_payment_account_id": account_id,
        }

    def set_payload(self, data: Mapping[str, Any]) -> None:
        method = str(data.get("payment_method_code") or "cash")
        idx = self._method.findData(method)
        if idx >= 0:
            self._method.setCurrentIndex(idx)
        account = data.get("default_payment_account_id")
        self._account.setText("" if account is None else str(account))


class _StatutoryStep(_StepWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tax_id = QLineEdit()
        self._cnps = QLineEdit()
        self._tax_id.textChanged.connect(self.payload_changed)
        self._cnps.textChanged.connect(self.payload_changed)
        self._form.addRow("Tax identifier (NIU) *", self._tax_id)
        self._form.addRow("CNPS number *", self._cnps)
        hint = QLabel(
            "Tax ID and CNPS are required for payroll posting and "
            "official remittances."
        )
        hint.setWordWrap(True)
        hint.setObjectName("WizardStepHint")
        self._form.addRow(hint)

    def read_payload(self) -> dict[str, Any]:
        return {
            "tax_identifier": self._tax_id.text().strip(),
            "cnps_number": self._cnps.text().strip(),
        }

    def set_payload(self, data: Mapping[str, Any]) -> None:
        self._tax_id.setText(str(data.get("tax_identifier") or ""))
        self._cnps.setText(str(data.get("cnps_number") or ""))


class _ComponentsStep(QFrame):
    """P4.S4 — Component assignment grid for the hire wizard.

    Displays all active payroll components for the company. The user
    checks the ones to assign to this employee and optionally enters an
    override amount. The payload is stored as a list of assignments in
    the draft and materialised by ``EmployeeOnboardingService.complete()``
    as ``EmployeeComponentAssignment`` rows.

    Because the employee does not yet exist at this stage, the step
    operates purely on the draft payload; no service calls are made here.
    """

    payload_changed = Signal()

    def __init__(
        self,
        components: list | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WizardStepContent")
        spacing = DEFAULT_TOKENS.spacing

        active_components = [c for c in (components or []) if c.is_active]
        self._rows: list[_ComponentRow] = [
            _ComponentRow(dto=c) for c in active_components
        ]
        self._model = _ComponentsTableModel(self._rows)
        self._model.dataChanged.connect(lambda *_: self._on_model_changed())

        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked
            | QTableView.EditTrigger.SelectedClicked
        )
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnWidth(_ComponentsTableModel._COL_INCLUDED, 30)
        self._table.setColumnWidth(_ComponentsTableModel._COL_CODE, 80)
        self._table.setColumnWidth(_ComponentsTableModel._COL_NAME, 200)
        self._table.setColumnWidth(_ComponentsTableModel._COL_TYPE, 100)
        self._table.setColumnWidth(_ComponentsTableModel._COL_METHOD, 110)

        hint = QLabel(
            "Select the payroll components to assign to this employee. "
            "Double-click the Override amount column to enter a custom amount."
        )
        hint.setWordWrap(True)
        hint.setObjectName("WizardStepHint")

        self._count_label = QLabel("0 component(s) selected")
        self._count_label.setObjectName("WizardStepHint")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        layout.setSpacing(spacing.dialog_section_gap)
        layout.addWidget(hint)

        if not active_components:
            no_data = QLabel(
                "No active payroll components found for this company. "
                "Add components in Payroll → Setup → Components before onboarding."
            )
            no_data.setWordWrap(True)
            no_data.setObjectName("WizardStepHint")
            layout.addWidget(no_data)
        else:
            layout.addWidget(self._table, 1)
            layout.addWidget(self._count_label)

    def _on_model_changed(self) -> None:
        count = sum(1 for r in self._rows if r.included)
        self._count_label.setText(f"{count} component(s) selected")
        self.payload_changed.emit()

    def read_payload(self) -> dict[str, Any]:
        assignments = [
            {
                "component_id": r.dto.id,
                "override_amount": r.override_amount or None,
                "override_rate": None,
            }
            for r in self._rows
            if r.included
        ]
        return {"assignments": assignments}

    def set_payload(self, data: Mapping[str, Any]) -> None:
        assignments = data.get("assignments") or []
        assigned: dict[int, dict] = {}
        for a in assignments:
            if isinstance(a, dict) and "component_id" in a:
                try:
                    assigned[int(a["component_id"])] = a
                except (ValueError, TypeError):
                    pass

        for row in self._rows:
            if row.dto.id in assigned:
                row.included = True
                row.override_amount = str(
                    assigned[row.dto.id].get("override_amount") or ""
                )
            else:
                row.included = False
                row.override_amount = ""

        self._model.layoutChanged.emit()
        count = sum(1 for r in self._rows if r.included)
        self._count_label.setText(f"{count} component(s) selected")


class _ReviewStep(_StepWidget):
    """Read-only summary built from the current draft payload."""

    section_clicked = Signal(str)  # emits step_id when user clicks a row

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._summary.setObjectName("WizardReviewSummary")
        self._summary.linkActivated.connect(self.section_clicked)
        self._form.addRow(self._summary)

    def populate(self, payload: Mapping[str, Mapping[str, Any]]) -> None:
        identity = payload.get("identity") or {}
        employment = payload.get("employment") or {}
        compensation = payload.get("compensation") or {}
        payment = payload.get("payment") or {}
        statutory = payload.get("statutory") or {}
        components = payload.get("components") or {}

        def section(step_id: str, title: str, lines: list[str]) -> str:
            body = "<br>".join(lines) if lines else "<i>(empty)</i>"
            return (
                f"<p><b>{title}</b> &nbsp;"
                f"<a href='{step_id}'>edit</a><br>{body}</p>"
            )

        parts = [
            section(_STEP_IDENTITY, "Identity", [
                f"Name: {identity.get('first_name','')} {identity.get('last_name','')}".strip(),
                f"Email: {identity.get('email') or '—'}",
                f"Phone: {identity.get('phone') or '—'}",
            ]),
            section(_STEP_EMPLOYMENT, "Employment", [
                f"Number: {employment.get('employee_number') or '—'}",
                f"Hire date: {employment.get('hire_date') or '—'}",
            ]),
            section(_STEP_COMPENSATION, "Compensation", [
                f"Compensation: {compensation.get('profile_name') or '—'}",
                f"Basic salary: {compensation.get('base_currency_code') or ''} "
                f"{compensation.get('basic_salary') or '—'}".strip(),
                f"Effective from: {compensation.get('effective_from') or '—'}",
            ]),
            section(_STEP_PAYMENT, "Payment", [
                f"Method: {payment.get('payment_method_code') or '—'}",
                f"Account: {payment.get('default_payment_account_id') or '—'}",
            ]),
            section(_STEP_STATUTORY, "Statutory IDs", [
                f"Tax ID: {statutory.get('tax_identifier') or '—'}",
                f"CNPS: {statutory.get('cnps_number') or '—'}",
            ]),
            section(_STEP_COMPONENTS, "Components", [
                f"{len(components.get('assignments') or [])} component(s) assigned",
            ]),
        ]
        self._summary.setText("".join(parts))

    def read_payload(self) -> dict[str, Any]:
        return {}

    def set_payload(self, data: Mapping[str, Any]) -> None:
        return None


# ── Dialog ─────────────────────────────────────────────────────────────────


class EmployeeOnboardingWizardDialog(WizardShell):
    """Hire-to-Pay BP threaded wizard dialog.

    Construction:

    .. code-block:: python

        dlg = EmployeeOnboardingWizardDialog(
            service_registry=registry,
            company_id=current_company_id,
            actor_user_id=current_user_id,
        )
        if dlg.exec():
            new_employee_id = dlg.created_employee_id

    The dialog persists every step server-side, so the user can close
    and resume the draft from the People pane (delivered in P2.S3).
    """

    def __init__(
        self,
        *,
        service_registry: "ServiceRegistry",
        company_id: int,
        actor_user_id: int | None = None,
        draft_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        steps = (
            WizardStepDescriptor(_STEP_IDENTITY, "Identity"),
            WizardStepDescriptor(_STEP_EMPLOYMENT, "Employment"),
            WizardStepDescriptor(_STEP_COMPENSATION, "Compensation"),
            WizardStepDescriptor(_STEP_PAYMENT, "Payment"),
            WizardStepDescriptor(_STEP_STATUTORY, "Statutory"),
            WizardStepDescriptor(_STEP_COMPONENTS, "Components"),
            WizardStepDescriptor(_STEP_REVIEW, "Review"),
        )
        super().__init__(
            "Hire employee",
            steps,
            parent=parent,
            primary_label="Next",
            finish_label="Complete onboarding",
            cancel_label="Save & close",
        )

        self._registry = service_registry
        self._service = service_registry.employee_onboarding_service
        if self._service is None:
            raise RuntimeError(
                "EmployeeOnboardingService is not registered in the active "
                "ServiceRegistry."
            )
        self._company_id = company_id
        self._actor_user_id = actor_user_id
        self._draft: EmployeeOnboardingDraftDTO | None = None
        self.created_employee_id: int | None = None

        # Load available payroll components for the components step.
        # Defensive: if the service is absent or raises, use an empty list.
        _components: list = []
        try:
            pc_svc = getattr(service_registry, "payroll_component_service", None)
            if pc_svc is not None:
                _components = pc_svc.list_components(company_id, active_only=True)
        except Exception as _exc:  # pragma: no cover
            _log.warning("Could not load payroll components for wizard: %s", _exc)

        # Build step widgets and inject into the shell.
        self._step_widgets: dict[str, Any] = {
            _STEP_IDENTITY: _IdentityStep(),
            _STEP_EMPLOYMENT: _EmploymentStep(),
            _STEP_COMPENSATION: _CompensationStep(),
            _STEP_PAYMENT: _PaymentStep(),
            _STEP_STATUTORY: _StatutoryStep(),
            _STEP_COMPONENTS: _ComponentsStep(components=_components),
            _STEP_REVIEW: _ReviewStep(),
        }
        for step_id, widget in self._step_widgets.items():
            self.set_step_widget(step_id, widget)

        # Wire signals.
        self.next_requested.connect(self._on_next)
        self.back_requested.connect(self._on_back)
        self.jump_requested.connect(self._on_jump)
        self.finish_requested.connect(self._on_finish)
        self.cancel_requested.connect(self._on_cancel)
        review_step = self._step_widgets[_STEP_REVIEW]
        assert isinstance(review_step, _ReviewStep)
        review_step.section_clicked.connect(self._on_review_jump)

        # Start or resume.
        if draft_id is not None:
            self._resume_draft(draft_id)
        else:
            self._start_draft()

    # ── BP plumbing ──────────────────────────────────────────────────

    def _start_draft(self) -> None:
        try:
            self._draft = self._service.start_draft(
                EmployeeOnboardingStartCommand(
                    company_id=self._company_id,
                    started_by_user_id=self._actor_user_id,
                )
            )
        except (PermissionDeniedError, ValidationError) as exc:
            QMessageBox.critical(self, "Cannot start onboarding", str(exc))
            self.reject()
            return
        self._populate_from_draft()

    def _resume_draft(self, draft_id: int) -> None:
        try:
            self._draft = self._service.get_draft(self._company_id, draft_id)
        except (NotFoundError, PermissionDeniedError) as exc:
            QMessageBox.critical(self, "Cannot resume onboarding", str(exc))
            self.reject()
            return
        # Jump to the draft's persisted current step.
        self._populate_from_draft()
        target = _STATE_TO_STEP.get(self._draft.current_step)
        if target and target != self.current_step_id():
            self.goto_step(target)

    def _populate_from_draft(self) -> None:
        if self._draft is None:
            return
        payload = self._draft.payload or {}
        for step_id, widget in self._step_widgets.items():
            if step_id == _STEP_REVIEW:
                continue
            slot = payload.get(step_id) if isinstance(payload, Mapping) else None
            if isinstance(slot, Mapping):
                widget.set_payload(slot)
        self._refresh_review_step()

    def _refresh_review_step(self) -> None:
        if self._draft is None:
            return
        review = self._step_widgets[_STEP_REVIEW]
        assert isinstance(review, _ReviewStep)
        # Compose the payload from the current widget reads so the
        # review reflects in-progress edits even before the user hits
        # Next.
        payload: dict[str, dict[str, Any]] = {}
        for step_id, widget in self._step_widgets.items():
            if step_id == _STEP_REVIEW:
                continue
            payload[step_id] = widget.read_payload()
        review.populate(payload)

    def _persist_step(self, step_id: str) -> bool:
        if self._draft is None or step_id == _STEP_REVIEW:
            return True
        widget = self._step_widgets[step_id]
        try:
            self._draft = self._service.update_step(
                self._company_id,
                EmployeeOnboardingStepUpdate(
                    draft_id=self._draft.id,
                    step_code=step_id,
                    patch=widget.read_payload(),
                    actor_user_id=self._actor_user_id,
                ),
            )
            return True
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
            self._show_step_issue(step_id, str(exc))
            return False

    def _transition(self, target_state: str) -> bool:
        if self._draft is None:
            return False
        try:
            self._draft = self._service.transition_state(
                self._company_id,
                EmployeeOnboardingTransition(
                    draft_id=self._draft.id,
                    target_state=target_state,
                    actor_user_id=self._actor_user_id,
                ),
            )
            return True
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
            self._show_step_issue(self.current_step_id(), str(exc))
            return False

    def _show_step_issue(self, step_id: str, message: str) -> None:
        self.set_step_issues(
            step_id,
            [ValidationIssue(severity="error", message=message)],
        )

    # ── Slots ────────────────────────────────────────────────────────

    def _on_next(self, step_id: str) -> None:
        # Persist the current step and clear any previous issues.
        self.set_step_issues(step_id, [])
        if not self._persist_step(step_id):
            return
        # If we're moving from Components → Review, we transition to
        # DRAFT_REVIEW. Otherwise advance one drafting state.
        next_idx = self.current_step_index() + 1
        next_step_id = self.step_ids()[next_idx]
        target_state = _STEP_TO_STATE[next_step_id]
        if not self._transition(target_state):
            return
        self.advance_step(mark_complete=True)
        if self.current_step_id() == _STEP_REVIEW:
            self._refresh_review_step()

    def _on_back(self, step_id: str) -> None:
        # Save partial work (best-effort) but don't block back nav.
        self._persist_step(step_id)
        prev_idx = self.current_step_index() - 1
        if prev_idx < 0:
            return
        prev_step_id = self.step_ids()[prev_idx]
        # Tell the service we're going back so audit reflects it.
        self._transition(_STEP_TO_STATE[prev_step_id])
        self.go_back()

    def _on_jump(self, step_id: str) -> None:
        # Persist current first, then attempt the BP jump.
        self._persist_step(self.current_step_id())
        target_state = _STEP_TO_STATE[step_id]
        if self._transition(target_state):
            self.goto_step(step_id)
            if step_id == _STEP_REVIEW:
                self._refresh_review_step()

    def _on_review_jump(self, step_id: str) -> None:
        # Allow review → any earlier step via the back lane (no validation).
        if step_id not in self._step_widgets:
            return
        target_state = _STEP_TO_STATE[step_id]
        if self._transition(target_state):
            self.goto_step(step_id)

    def _on_finish(self) -> None:
        if self._draft is None:
            return
        # Make sure the components step's payload is captured.
        if not self._persist_step(_STEP_COMPONENTS):
            return
        try:
            self._draft = self._service.complete(
                self._company_id,
                self._draft.id,
                actor_user_id=self._actor_user_id,
            )
        except ValidationError as exc:
            self._show_step_issue(_STEP_REVIEW, str(exc))
            return
        except (ConflictError, NotFoundError, PermissionDeniedError) as exc:
            QMessageBox.critical(self, "Cannot complete onboarding", str(exc))
            return
        self.created_employee_id = self._draft.produced_employee_id
        self.accept()

    def _on_cancel(self) -> None:
        # The draft is already persisted server-side; closing keeps the
        # draft in its current state. The user can resume later.
        self.reject()

    # ── Test/inspection helpers ──────────────────────────────────────

    @property
    def draft(self) -> EmployeeOnboardingDraftDTO | None:
        return self._draft


__all__ = [
    "EmployeeOnboardingWizardDialog",
]
