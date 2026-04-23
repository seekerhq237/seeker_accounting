"""PayrollActivationWizardDialog — guided onboarding for payroll on a new company.

Orchestrates the existing payroll setup services so a bookkeeper can
activate payroll without chasing through multiple dialogs:

1. **Settings**        — frequency, currency, CNPS regime, risk class.
2. **Statutory Pack**  — pick and apply a country pack (components + rules).
3. **Structure**       — create first department and position (optional).
4. **Review**          — show readiness summary for components, rules,
                          and payroll-payable GL mapping.
5. **Done**            — confirmation with counts of what was created.

The wizard calls services — it never touches repositories directly. All
existing expert dialogs remain available; this is an opinionated entry
point, not a replacement.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.payroll.dto.payroll_setup_commands import (
    CreateDepartmentCommand,
    CreatePositionCommand,
    UpsertCompanyPayrollSettingsCommand,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row


@dataclass(frozen=True, slots=True)
class PayrollActivationWizardResult:
    """Returned by the wizard on successful completion."""

    settings_applied: bool
    pack_code: str | None
    components_created: int
    rule_sets_created: int
    departments_created: int
    positions_created: int
    payroll_payable_mapped: bool
    summary: str


_PAY_FREQ_CHOICES = (
    ("monthly", "Monthly"),
    ("bi_weekly", "Bi-weekly"),
    ("weekly", "Weekly"),
)
_CNPS_REGIME_CHOICES = (
    ("general", "General"),
    ("domestic", "Domestic"),
    ("agricultural", "Agricultural"),
)
_RISK_CLASS_CHOICES = (
    ("A", "Class A (1.75%)"),
    ("B", "Class B (2.50%)"),
    ("C", "Class C (5.00%)"),
)


class PayrollActivationWizardDialog(BaseDialog):
    """Multi-step guided dialog — see module docstring."""

    _STEP_LABELS = (
        "1. Settings",
        "2. Statutory Pack",
        "3. Structure",
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
        self._result: PayrollActivationWizardResult | None = None
        self._current_step = 0
        self._apply_result = None  # ApplyPackResultDTO after commit

        super().__init__(
            "Payroll Activation",
            parent,
            help_key="wizard.payroll_activation",
        )
        self.setObjectName("PayrollActivationWizardDialog")
        self.resize(680, 580)

        intro = QLabel(
            "Set up payroll for this company in a few guided steps.",
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
        self._load_defaults()
        self._update_step_pills()
        self._update_buttons()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def result_payload(self) -> PayrollActivationWizardResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> PayrollActivationWizardResult | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog.exec()
        return dialog.result_payload

    # ── Step header ───────────────────────────────────────────────────

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

    # ── Steps stack ───────────────────────────────────────────────────

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_settings_page())
        self._stack.addWidget(self._build_pack_page())
        self._stack.addWidget(self._build_structure_page())
        self._stack.addWidget(self._build_gl_mapping_page())
        self._stack.addWidget(self._build_review_page())
        self._stack.addWidget(self._build_done_page())
        return self._stack

    def _build_gl_mapping_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card("Payroll Payable Account")
        hint = QLabel(
            "Payroll posting requires the <b>payroll_payable</b> role to be "
            "mapped to a liability account. You can map it now or skip and "
            "configure it later under <i>Account Roles</i>.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._gl_status_label = QLabel(card)
        self._gl_status_label.setObjectName("DialogSectionSummary")
        self._gl_status_label.setWordWrap(True)
        card.layout().addWidget(self._gl_status_label)

        self._payable_account_combo = QComboBox(card)
        card.layout().addWidget(create_field_block("Payroll Payable Account", self._payable_account_combo))

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card("Company Payroll Settings")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._frequency_combo = QComboBox(card)
        for code, label in _PAY_FREQ_CHOICES:
            self._frequency_combo.addItem(label, code)
        grid.addWidget(create_field_block("Pay Frequency", self._frequency_combo), 0, 0)

        self._currency_edit = QLineEdit(card)
        self._currency_edit.setPlaceholderText("XAF")
        grid.addWidget(create_field_block("Currency", self._currency_edit), 0, 1)

        self._cnps_combo = QComboBox(card)
        for code, label in _CNPS_REGIME_CHOICES:
            self._cnps_combo.addItem(label, code)
        grid.addWidget(create_field_block("CNPS Regime", self._cnps_combo), 1, 0)

        self._risk_combo = QComboBox(card)
        for code, label in _RISK_CLASS_CHOICES:
            self._risk_combo.addItem(label, code)
        grid.addWidget(create_field_block("Accident Risk Class", self._risk_combo), 1, 1)

        card.layout().addLayout(grid)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_pack_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card("Statutory Pack")
        hint = QLabel(
            "Applying a pack creates the standard payroll components "
            "(CNPS, IRPP, TDL, CRTV, …) and their calculation rules. "
            "Existing items are never overwritten.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._pack_combo = QComboBox(card)
        try:
            packs = self._registry.payroll_statutory_pack_service.list_available_packs()
        except Exception:  # noqa: BLE001
            packs = []
        self._pack_combo.addItem("— Skip (configure manually later) —", None)
        for pack in packs:
            self._pack_combo.addItem(
                f"{pack.display_name} ({pack.country_code})", pack.pack_code
            )
        card.layout().addWidget(create_field_block("Pack", self._pack_combo))

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_structure_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card("Organization Structure")
        hint = QLabel(
            "Optional — create a first department and position now so you "
            "can hire employees immediately.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._dept_code_edit = QLineEdit(card)
        self._dept_code_edit.setPlaceholderText("OPS")
        grid.addWidget(create_field_block("Department Code", self._dept_code_edit), 0, 0)

        self._dept_name_edit = QLineEdit(card)
        self._dept_name_edit.setPlaceholderText("Operations")
        grid.addWidget(create_field_block("Department Name", self._dept_name_edit), 0, 1)

        self._pos_code_edit = QLineEdit(card)
        self._pos_code_edit.setPlaceholderText("MGR")
        grid.addWidget(create_field_block("Position Code", self._pos_code_edit), 1, 0)

        self._pos_name_edit = QLineEdit(card)
        self._pos_name_edit.setPlaceholderText("Manager")
        grid.addWidget(create_field_block("Position Name", self._pos_name_edit), 1, 1)

        card.layout().addLayout(grid)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card("Review")
        self._review_label = QLabel(card)
        self._review_label.setObjectName("DialogSectionSummary")
        self._review_label.setWordWrap(True)
        card.layout().addWidget(self._review_label)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card("Payroll activated")
        self._done_label = QLabel(card)
        self._done_label.setObjectName("DialogSectionSummary")
        self._done_label.setWordWrap(True)
        card.layout().addWidget(self._done_label)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

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

    # ── Buttons ───────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        self._back_button = QPushButton("Back", self)
        self._back_button.setProperty("variant", "secondary")
        self._back_button.clicked.connect(self._go_back)
        self.button_box.addButton(self._back_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._next_button = QPushButton("Next", self)
        self._next_button.setProperty("variant", "primary")
        self._next_button.clicked.connect(self._go_next)
        self.button_box.addButton(self._next_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._apply_button = QPushButton("Activate Payroll", self)
        self._apply_button.setProperty("variant", "primary")
        self._apply_button.clicked.connect(self._handle_apply)
        self.button_box.addButton(self._apply_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._close_button = QPushButton("Cancel", self)
        self._close_button.setProperty("variant", "ghost")
        self._close_button.clicked.connect(self.reject)
        self.button_box.addButton(self._close_button, QDialogButtonBox.ButtonRole.RejectRole)

    # ── Defaults / navigation ─────────────────────────────────────────

    def _load_defaults(self) -> None:
        # Prefer existing settings if present
        try:
            existing = self._registry.payroll_setup_service.get_company_payroll_settings(
                self._company_id
            )
        except Exception:  # noqa: BLE001
            existing = None

        if existing:
            self._set_combo(self._frequency_combo, existing.default_pay_frequency_code)
            self._currency_edit.setText(existing.default_payroll_currency_code or "XAF")
            self._set_combo(self._cnps_combo, existing.cnps_regime_code or "general")
            self._set_combo(self._risk_combo, existing.accident_risk_class_code or "A")
        else:
            self._set_combo(self._frequency_combo, "monthly")
            self._currency_edit.setText("XAF")
            self._set_combo(self._cnps_combo, "general")
            self._set_combo(self._risk_combo, "A")

    @staticmethod
    def _set_combo(combo: QComboBox, data) -> None:
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _go_next(self) -> None:
        if self._current_step == 0 and not self._validate_settings():
            return
        if self._current_step == 4:  # review → apply
            self._handle_apply()
            return
        self._current_step += 1
        if self._current_step == 3:
            self._refresh_gl_mapping()
        if self._current_step == 4:
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
        on_review = self._current_step == 4
        on_done = self._current_step == 5

        self._back_button.setVisible(self._current_step > 0 and not on_done)
        self._next_button.setVisible(not on_review and not on_done)
        self._apply_button.setVisible(on_review)
        self._close_button.setText("Close" if on_done else "Cancel")

    # ── Validation ────────────────────────────────────────────────────

    def _validate_settings(self) -> bool:
        if not self._currency_edit.text().strip():
            self._set_error("Currency is required.")
            return False
        return True

    # ── Review summary ────────────────────────────────────────────────
    def _refresh_gl_mapping(self) -> None:
        # Load liability accounts and current mapping (first call only)
        if self._payable_account_combo.count() > 0:
            return
        try:
            mappings = self._registry.account_role_mapping_service.list_role_mappings(
                self._company_id
            )
        except Exception:  # noqa: BLE001
            mappings = []
        current = next(
            (m for m in mappings if m.role_code == "payroll_payable"), None
        )
        already_mapped = current is not None and current.account_id is not None

        try:
            accounts = self._registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
        except Exception:  # noqa: BLE001
            accounts = []
        liabilities = [
            a for a in accounts
            if (a.account_class_code or "").lower() == "liability"
            and a.allow_manual_posting
            and not a.is_control_account
        ]

        self._payable_account_combo.clear()
        skip_label = (
            "— Keep current mapping —" if already_mapped else "— Skip (map later) —"
        )
        self._payable_account_combo.addItem(skip_label, None)
        for acc in liabilities:
            label = f"{acc.account_code} — {acc.account_name}"
            self._payable_account_combo.addItem(label, acc.id)

        if already_mapped:
            self._gl_status_label.setText(
                f"<b>Currently mapped</b>: {current.account_code} — {current.account_name}"
            )
        elif liabilities:
            self._gl_status_label.setText(
                f"<b>Not mapped</b>. {len(liabilities)} eligible liability account(s) available."
            )
        else:
            self._gl_status_label.setText(
                "<b>Not mapped</b>. No eligible liability accounts found — "
                "create one in Chart of Accounts and return to this step, "
                "or skip and map later."
            )
    def _refresh_review(self) -> None:
        pack_code = self._pack_combo.currentData()
        freq_label = self._frequency_combo.currentText()
        currency = self._currency_edit.text().strip()
        cnps_label = self._cnps_combo.currentText()
        risk_label = self._risk_combo.currentText()

        dept = self._dept_code_edit.text().strip()
        pos = self._pos_code_edit.text().strip()

        lines = [
            f"<b>Settings</b>: {freq_label}, {currency}, {cnps_label}, {risk_label}",
            f"<b>Statutory pack</b>: {pack_code or '(none)'}",
            f"<b>Department</b>: {dept or '(none)'}",
            f"<b>Position</b>: {pos or '(none)'}",
        ]

        # GL payable readiness
        selected_account_id = self._payable_account_combo.currentData()
        if selected_account_id:
            lines.append(
                f"<b>Payroll payable account</b>: will be mapped to "
                f"{self._payable_account_combo.currentText()}"
            )
        else:
            try:
                mappings = self._registry.account_role_mapping_service.list_role_mappings(
                    self._company_id
                )
                payable_mapped = any(
                    m.role_code == "payroll_payable" and m.account_id is not None
                    for m in mappings
                )
            except Exception:  # noqa: BLE001
                payable_mapped = False
            lines.append(
                f"<b>Payroll payable account</b>: "
                f"{'already mapped (unchanged)' if payable_mapped else 'NOT MAPPED — set later in Account Roles'}"
            )

        self._review_label.setText("<br>".join(lines))

    # ── Commit ────────────────────────────────────────────────────────

    def _handle_apply(self) -> None:
        self._set_error(None)
        self._apply_button.setEnabled(False)
        try:
            if not self._commit_settings():
                return
            apply_result = self._commit_pack()
            dept_created, pos_created = self._commit_structure()
            self._commit_gl_mapping()
            components_created = apply_result.components_created if apply_result else 0
            rule_sets_created = apply_result.rule_sets_created if apply_result else 0
            pack_code = apply_result.pack_code if apply_result else None

            try:
                mappings = self._registry.account_role_mapping_service.list_role_mappings(
                    self._company_id
                )
                payable_mapped = any(
                    m.role_code == "payroll_payable" for m in mappings
                )
            except Exception:  # noqa: BLE001
                payable_mapped = False

            summary_bits = [
                f"Settings saved for {self._company_name}.",
                (
                    f"Pack {pack_code}: {components_created} component(s), "
                    f"{rule_sets_created} rule set(s) created."
                ) if pack_code else "No statutory pack applied.",
            ]
            if dept_created:
                summary_bits.append(f"Created department '{self._dept_code_edit.text().strip()}'.")
            if pos_created:
                summary_bits.append(f"Created position '{self._pos_code_edit.text().strip()}'.")
            summary_bits.append(
                "Payroll payable account is mapped."
                if payable_mapped
                else "Remember to map the payroll_payable account role before posting."
            )
            if payable_mapped:
                summary_bits.append(
                    "Recommended next step: <b>Hire your first employee</b> via the "
                    "Employees tab."
                )
            else:
                summary_bits.append(
                    "Recommended next step: open <i>Account Roles</i> and map "
                    "<b>payroll_payable</b> so this company can post payroll."
                )
            summary = " ".join(summary_bits)

            self._result = PayrollActivationWizardResult(
                settings_applied=True,
                pack_code=pack_code,
                components_created=components_created,
                rule_sets_created=rule_sets_created,
                departments_created=1 if dept_created else 0,
                positions_created=1 if pos_created else 0,
                payroll_payable_mapped=payable_mapped,
                summary=summary,
            )
            self._done_label.setText(summary)

            self._current_step = 5
            self._stack.setCurrentIndex(self._current_step)
            self._update_step_pills()
            self._update_buttons()
        finally:
            self._apply_button.setEnabled(True)

    def _commit_settings(self) -> bool:
        cmd = UpsertCompanyPayrollSettingsCommand(
            default_pay_frequency_code=self._frequency_combo.currentData(),
            default_payroll_currency_code=self._currency_edit.text().strip(),
            cnps_regime_code=self._cnps_combo.currentData(),
            accident_risk_class_code=self._risk_combo.currentData(),
        )
        try:
            self._registry.payroll_setup_service.upsert_company_payroll_settings(
                self._company_id, cmd
            )
            return True
        except (ValidationError, ConflictError, PermissionDeniedError, NotFoundError) as exc:
            self._set_error(str(exc))
            return False

    def _commit_pack(self):
        pack_code = self._pack_combo.currentData()
        if not pack_code:
            return None
        try:
            return self._registry.payroll_statutory_pack_service.apply_pack(
                self._company_id, pack_code
            )
        except (ValidationError, ConflictError, PermissionDeniedError, NotFoundError) as exc:
            self._set_error(f"Pack apply failed: {exc}")
            return None

    def _commit_structure(self) -> tuple[bool, bool]:
        dept_created = False
        pos_created = False
        code = self._dept_code_edit.text().strip()
        name = self._dept_name_edit.text().strip()
        if code and name:
            try:
                self._registry.payroll_setup_service.create_department(
                    self._company_id, CreateDepartmentCommand(code=code, name=name)
                )
                dept_created = True
            except ConflictError:
                pass  # already exists — acceptable during re-run
            except (ValidationError, PermissionDeniedError) as exc:
                self._set_error(f"Department: {exc}")
        pcode = self._pos_code_edit.text().strip()
        pname = self._pos_name_edit.text().strip()
        if pcode and pname:
            try:
                self._registry.payroll_setup_service.create_position(
                    self._company_id, CreatePositionCommand(code=pcode, name=pname)
                )
                pos_created = True
            except ConflictError:
                pass
            except (ValidationError, PermissionDeniedError) as exc:
                self._set_error(f"Position: {exc}")
        return dept_created, pos_created

    def _commit_gl_mapping(self) -> None:
        account_id = self._payable_account_combo.currentData()
        if not account_id:
            return
        try:
            self._registry.account_role_mapping_service.set_role_mapping(
                self._company_id,
                SetAccountRoleMappingCommand(
                    role_code="payroll_payable", account_id=int(account_id)
                ),
            )
        except (ValidationError, ConflictError, PermissionDeniedError, NotFoundError) as exc:
            self._set_error(f"GL mapping: {exc}")

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()
