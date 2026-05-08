"""PayrollComponentCreationWizardDialog — guided component creation flow.

Steps:

1. **Identity**        — Code, Name.
2. **Classification**  — Component type, calculation method.
3. **Behavior**        — Taxable, Pensionable flags and optional notes.
4. **GL Mapping**      — Expense account, Liability account (both optional).
5. **Review**          — Full summary before committing.
6. **Done**            — Confirmation with next actions.

The existing ``PayrollComponentFormDialog`` remains available as the expert
Edit path. This wizard is the recommended creation entry point only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_component_dto import (
    CreatePayrollComponentCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.layout_constraints import apply_window_size

_log = logging.getLogger(__name__)

# ── Reference data ────────────────────────────────────────────────────────────

_COMPONENT_TYPES = (
    ("earning",               "Earning",               "Adds to gross pay (salary, allowances, bonuses, BIK)."),
    ("deduction",             "Deduction",             "Reduces net pay (employee CNPS, FNE, CRTV, TDL …)."),
    ("employer_contribution", "Employer Contribution", "Employer-side charges not deducted from employee pay."),
    ("tax",                   "Tax",                   "Withholding tax applied to taxable income (IRPP, CAC)."),
    ("informational",         "Informational",         "Displayed on payslip only — does not affect net pay."),
)

_CALC_METHODS = (
    ("fixed_amount", "Fixed Amount",  "A constant monetary amount entered per period."),
    ("percentage",   "Percentage",    "A percentage of another component (e.g. % of base salary)."),
    ("rule_based",   "Rule Based",    "Computed by an attached rule set with bracketed rates."),
    ("manual_input", "Manual Input",  "Amount entered manually in each payroll run."),
    ("hourly",       "Hourly",        "Rate × hours worked (overtime, part-time, …)."),
)


@dataclass(frozen=True, slots=True)
class PayrollComponentCreationResult:
    component_id: int
    component_code: str
    component_name: str
    component_type_code: str


class PayrollComponentCreationWizardDialog(BaseDialog):
    """5-step guided component creation dialog — see module docstring."""

    _STEP_LABELS = (
        "1. Identity",
        "2. Classification",
        "3. Behavior",
        "4. GL Mapping",
        "5. Review",
        "6. Done",
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._result: PayrollComponentCreationResult | None = None
        self._current_step = 0

        super().__init__(
            "New Payroll Component",
            parent,
            help_key="wizard.payroll_component_creation",
        )
        self.setObjectName("PayrollComponentCreationWizardDialog")
        apply_window_size(self, "modules.payroll.ui.wizards.payroll.component.creation.wizard.0")

        intro = QLabel(
            "Define a new payroll component in a few guided steps. "
            "You can adjust all settings afterwards via Edit.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)
        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self.body_layout.addWidget(self._build_step_header())

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_stack(), 1)
        self._build_buttons()
        self._update_step_pills()
        self._update_buttons()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def result_payload(self) -> PayrollComponentCreationResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> PayrollComponentCreationResult | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog.exec()
        return dialog.result_payload

    # ── Step header ───────────────────────────────────────────────────────────

    def _build_step_header(self) -> QWidget:
        header = QWidget(self)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._step_pills: list[QLabel] = []
        for text in self._STEP_LABELS:
            pill = QLabel(text, header)
            pill.setObjectName("WizardStepPill")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(pill)
            self._step_pills.append(pill)
        layout.addStretch(1)
        return header

    # ── Stack ─────────────────────────────────────────────────────────────────

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_identity_page())
        self._stack.addWidget(self._build_classification_page())
        self._stack.addWidget(self._build_behavior_page())
        self._stack.addWidget(self._build_gl_mapping_page())
        self._stack.addWidget(self._build_review_page())
        self._stack.addWidget(self._build_done_page())
        return self._stack

    # ── Pages ─────────────────────────────────────────────────────────────────

    def _build_identity_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = self._card("Component Identity")
        hint = QLabel(
            "The code is a short uppercase identifier used in rules and formulas "
            "(e.g. <b>BASE_SALARY</b>, <b>EMPLOYEE_CNPS</b>). "
            "The name is the human-readable label shown on payslips.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._code_edit = QLineEdit(card)
        self._code_edit.setPlaceholderText("e.g. BASE_SALARY")
        self._code_edit.setMaxLength(30)
        self._code_edit.textChanged.connect(self._auto_uppercase_code)
        grid.addWidget(create_field_block("Code *", self._code_edit), 0, 0)

        self._name_edit = QLineEdit(card)
        self._name_edit.setPlaceholderText("e.g. Base Salary")
        self._name_edit.setMaxLength(100)
        grid.addWidget(create_field_block("Name *", self._name_edit), 0, 1)

        card.layout().addLayout(grid)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_classification_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        # ── Type card ─────────────────────────────────────────────────────────
        type_card = self._card("Component Type")
        type_hint = QLabel(
            "The component type controls how this item affects gross and net pay "
            "and how it appears on the payroll accounting journal.",
            type_card,
        )
        type_hint.setObjectName("DialogSectionSummary")
        type_hint.setWordWrap(True)
        type_card.layout().addWidget(type_hint)

        self._type_combo = QComboBox(type_card)
        self._type_combo.currentIndexChanged.connect(self._refresh_type_description)
        for code, label, _ in _COMPONENT_TYPES:
            self._type_combo.addItem(label, code)
        type_card.layout().addWidget(create_field_block("Type *", self._type_combo))

        self._type_desc = QLabel(type_card)
        self._type_desc.setObjectName("DialogSectionSummary")
        self._type_desc.setWordWrap(True)
        type_card.layout().addWidget(self._type_desc)

        outer.addWidget(type_card)

        # ── Method card ───────────────────────────────────────────────────────
        method_card = self._card("Calculation Method")
        method_hint = QLabel(
            "The calculation method determines how the component amount is "
            "derived during payroll runs.",
            method_card,
        )
        method_hint.setObjectName("DialogSectionSummary")
        method_hint.setWordWrap(True)
        method_card.layout().addWidget(method_hint)

        self._method_combo = QComboBox(method_card)
        self._method_combo.currentIndexChanged.connect(self._refresh_method_description)
        for code, label, _ in _CALC_METHODS:
            self._method_combo.addItem(label, code)
        method_card.layout().addWidget(create_field_block("Method *", self._method_combo))

        self._method_desc = QLabel(method_card)
        self._method_desc.setObjectName("DialogSectionSummary")
        self._method_desc.setWordWrap(True)
        method_card.layout().addWidget(self._method_desc)

        outer.addWidget(method_card)
        outer.addStretch(1)

        # Trigger initial descriptions
        self._refresh_type_description()
        self._refresh_method_description()
        return page

    def _build_behavior_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = self._card("Payroll Behavior Flags")
        hint = QLabel(
            "These flags control how this component participates in tax and "
            "pension calculations.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._taxable_cb = QCheckBox(card)
        self._taxable_cb.setText(
            "Taxable — this component's amount contributes to the IRPP taxable base"
        )
        card.layout().addWidget(self._taxable_cb)

        self._pensionable_cb = QCheckBox(card)
        self._pensionable_cb.setText(
            "Pensionable — this component is included in the CNPS contributory wage"
        )
        card.layout().addWidget(self._pensionable_cb)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_gl_mapping_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = self._card("GL Account Mapping (Optional)")
        hint = QLabel(
            "Map this component to chart of accounts entries for payroll posting. "
            "Both fields are optional — you can assign or change accounts later.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._expense_acct_combo = QComboBox(card)
        grid.addWidget(
            create_field_block("Expense Account", self._expense_acct_combo), 0, 0
        )

        self._liability_acct_combo = QComboBox(card)
        grid.addWidget(
            create_field_block("Liability Account", self._liability_acct_combo), 0, 1
        )

        card.layout().addLayout(grid)
        outer.addWidget(card)
        outer.addStretch(1)

        self._accounts_loaded = False
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = self._card("Review — confirm before creating")
        self._review_label = QLabel(card)
        self._review_label.setObjectName("DialogSectionSummary")
        self._review_label.setWordWrap(True)
        card.layout().addWidget(self._review_label)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = self._card("Component created")
        self._done_label = QLabel(card)
        self._done_label.setObjectName("DialogSectionSummary")
        self._done_label.setWordWrap(True)
        card.layout().addWidget(self._done_label)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    # ── Card helper ───────────────────────────────────────────────────────────

    def _card(self, title: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        tlabel = QLabel(title, card)
        tlabel.setObjectName("DialogSectionTitle")
        layout.addWidget(tlabel)
        return card

    # ── Buttons ───────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        self._back_btn = QPushButton("Back", self)
        self._back_btn.setProperty("variant", "secondary")
        self._back_btn.clicked.connect(self._go_back)
        self.button_box.addButton(self._back_btn, QDialogButtonBox.ButtonRole.ActionRole)

        self._next_btn = QPushButton("Next", self)
        self._next_btn.setProperty("variant", "primary")
        self._next_btn.clicked.connect(self._go_next)
        self.button_box.addButton(self._next_btn, QDialogButtonBox.ButtonRole.ActionRole)

        self._create_btn = QPushButton("Create Component", self)
        self._create_btn.setProperty("variant", "primary")
        self._create_btn.clicked.connect(self._handle_create)
        self.button_box.addButton(self._create_btn, QDialogButtonBox.ButtonRole.ActionRole)

        self._cancel_btn = QPushButton("Cancel", self)
        self._cancel_btn.setProperty("variant", "ghost")
        self._cancel_btn.clicked.connect(self.reject)
        self.button_box.addButton(self._cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

    # ── Navigation ────────────────────────────────────────────────────────────

    _REVIEW_STEP = 4
    _DONE_STEP = 5

    def _go_next(self) -> None:
        if not self._validate_current_step():
            return
        self._current_step += 1
        if self._current_step == 3:
            self._ensure_accounts_loaded()
        if self._current_step == self._REVIEW_STEP:
            self._refresh_review()
        self._stack.setCurrentIndex(self._current_step)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _go_back(self) -> None:
        if self._current_step <= 0:
            return
        self._current_step -= 1
        self._stack.setCurrentIndex(self._current_step)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _update_step_pills(self) -> None:
        for index, pill in enumerate(self._step_pills):
            if index < self._current_step:
                pill.setProperty("completed", "true")
                pill.setProperty("current", "false")
            elif index == self._current_step:
                pill.setProperty("completed", "false")
                pill.setProperty("current", "true")
            else:
                pill.setProperty("completed", "false")
                pill.setProperty("current", "false")
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _update_buttons(self) -> None:
        on_review = self._current_step == self._REVIEW_STEP
        on_done = self._current_step == self._DONE_STEP
        self._back_btn.setVisible(self._current_step > 0 and not on_done)
        self._next_btn.setVisible(not on_review and not on_done)
        self._create_btn.setVisible(on_review)
        self._cancel_btn.setText("Close" if on_done else "Cancel")

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate_current_step(self) -> bool:
        if self._current_step == 0:
            return self._validate_identity()
        return True

    def _validate_identity(self) -> bool:
        code = self._code_edit.text().strip()
        name = self._name_edit.text().strip()
        if not code:
            self._set_error("Component code is required.")
            return False
        if not name:
            self._set_error("Component name is required.")
            return False
        return True

    # ── Dynamic helpers ───────────────────────────────────────────────────────

    def _auto_uppercase_code(self, text: str) -> None:
        upper = text.upper().replace(" ", "_")
        if upper != text:
            cursor = self._code_edit.cursorPosition()
            self._code_edit.blockSignals(True)
            self._code_edit.setText(upper)
            self._code_edit.setCursorPosition(min(cursor, len(upper)))
            self._code_edit.blockSignals(False)

    def _refresh_type_description(self) -> None:
        idx = self._type_combo.currentIndex()
        if 0 <= idx < len(_COMPONENT_TYPES):
            self._type_desc.setText(_COMPONENT_TYPES[idx][2])

    def _refresh_method_description(self) -> None:
        idx = self._method_combo.currentIndex()
        if 0 <= idx < len(_CALC_METHODS):
            self._method_desc.setText(_CALC_METHODS[idx][2])

    def _ensure_accounts_loaded(self) -> None:
        if self._accounts_loaded:
            return
        try:
            accounts = self._registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
        except Exception:
            accounts = []
        for combo in (self._expense_acct_combo, self._liability_acct_combo):
            combo.clear()
            combo.addItem("— None —", None)
            for acct in accounts:
                combo.addItem(f"{acct.account_code} — {acct.account_name}", acct.id)
        self._accounts_loaded = True

    def _refresh_review(self) -> None:
        code = self._code_edit.text().strip()
        name = self._name_edit.text().strip()
        type_label = self._type_combo.currentText()
        method_label = self._method_combo.currentText()
        taxable = "Yes" if self._taxable_cb.isChecked() else "No"
        pensionable = "Yes" if self._pensionable_cb.isChecked() else "No"
        expense = self._expense_acct_combo.currentText() if self._accounts_loaded else "— None —"
        liability = self._liability_acct_combo.currentText() if self._accounts_loaded else "— None —"

        lines = [
            f"<b>Code:</b> {code}",
            f"<b>Name:</b> {name}",
            f"<b>Type:</b> {type_label}",
            f"<b>Calculation Method:</b> {method_label}",
            f"<b>Taxable:</b> {taxable}",
            f"<b>Pensionable:</b> {pensionable}",
            f"<b>Expense Account:</b> {expense}",
            f"<b>Liability Account:</b> {liability}",
        ]
        self._review_label.setText("<br>".join(lines))

    # ── Create handler ────────────────────────────────────────────────────────

    def _handle_create(self) -> None:
        code = self._code_edit.text().strip()
        name = self._name_edit.text().strip()
        type_code = self._type_combo.currentData()
        method_code = self._method_combo.currentData()
        is_taxable = self._taxable_cb.isChecked()
        is_pensionable = self._pensionable_cb.isChecked()
        expense_id = self._expense_acct_combo.currentData() if self._accounts_loaded else None
        liability_id = self._liability_acct_combo.currentData() if self._accounts_loaded else None

        try:
            dto = self._registry.payroll_component_service.create_component(
                self._company_id,
                CreatePayrollComponentCommand(
                    component_code=code,
                    component_name=name,
                    component_type_code=type_code,
                    calculation_method_code=method_code,
                    is_taxable=is_taxable,
                    is_pensionable=is_pensionable,
                    expense_account_id=expense_id,
                    liability_account_id=liability_id,
                ),
            )
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except Exception:
            _log.exception("Unexpected error creating payroll component")
            self._set_error("An unexpected error occurred. Please check the application log.")
            return

        self._result = PayrollComponentCreationResult(
            component_id=dto.id,
            component_code=dto.component_code,
            component_name=dto.component_name,
            component_type_code=dto.component_type_code,
        )

        type_label = self._type_combo.currentText()
        method_label = self._method_combo.currentText()
        self._done_label.setText(
            f"<b>{dto.component_code}</b> — {dto.component_name}<br><br>"
            f"Type: {type_label}<br>"
            f"Method: {method_label}<br><br>"
            "The component is now active and available for assignment to employees "
            "via compensation profiles."
        )
        self._current_step = self._DONE_STEP
        self._stack.setCurrentIndex(self._DONE_STEP)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()
        self.accept()

    # ── Error display ─────────────────────────────────────────────────────────

    def _set_error(self, message: str | None) -> None:
        if message:
            self._error_label.setText(message)
            self._error_label.show()
        else:
            self._error_label.hide()
