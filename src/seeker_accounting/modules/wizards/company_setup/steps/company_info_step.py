"""Step 1 — Company info.

Collects core identifying fields and creates the company on advance.
After this step succeeds, ``state[KEY_COMPANY_ID]`` is set and the wizard
context is rebound to that company so downstream steps are scoped.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.companies.dto.company_dto import ReferenceOptionDTO
from seeker_accounting.modules.wizards.company_setup import state_keys as K
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox


class CompanyInfoStep(WizardStep):
    key = "company_info"
    title = "Company"
    subtitle = "Identify the organisation you are setting up."
    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._countries: list[ReferenceOptionDTO] = []
        self._currencies: list[ReferenceOptionDTO] = []

    # ── UI ──────────────────────────────────────────────────────────────

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self._legal_name_edit = QLineEdit(root)
        self._legal_name_edit.setPlaceholderText("e.g. Seeker Cameroon Ltd")
        grid.addWidget(create_field_block("Legal Name", self._legal_name_edit), 0, 0)

        self._display_name_edit = QLineEdit(root)
        self._display_name_edit.setPlaceholderText("e.g. Seeker Cameroon")
        grid.addWidget(create_field_block("Display Name", self._display_name_edit), 0, 1)

        self._country_combo = SearchableComboBox(root)
        grid.addWidget(create_field_block("Country", self._country_combo), 1, 0)

        self._currency_combo = SearchableComboBox(root)
        grid.addWidget(create_field_block("Base Currency", self._currency_combo), 1, 1)

        self._tax_id_edit = QLineEdit(root)
        self._tax_id_edit.setPlaceholderText("Tax ID / NIU (optional)")
        grid.addWidget(create_field_block("Tax Identifier", self._tax_id_edit), 2, 0)

        self._email_edit = QLineEdit(root)
        self._email_edit.setPlaceholderText("info@company.example")
        grid.addWidget(create_field_block("Email", self._email_edit), 2, 1)

        layout.addLayout(grid)

        self._helper = QLabel(
            "These details will be stored on the company record and used as "
            "defaults for invoices, reports, and tax filings.",
            root,
        )
        self._helper.setWordWrap(True)
        self._helper.setStyleSheet("color: #4E5866; font-size: 11px;")
        layout.addWidget(self._helper)
        layout.addStretch(1)
        return root

    # ── Hooks ───────────────────────────────────────────────────────────

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_service = context.service_registry.company_service
        try:
            self._countries = list(company_service.list_available_countries())
            self._currencies = list(company_service.list_available_currencies())
        except Exception:  # noqa: BLE001
            self._countries = []
            self._currencies = []

        self._country_combo.set_items(
            [(f"{o.code}  {o.name}", o.code) for o in self._countries],
            placeholder="Select country",
        )
        self._currency_combo.set_items(
            [(f"{o.code}  {o.name}", o.code) for o in self._currencies],
            placeholder="Select currency",
        )

        self._legal_name_edit.setText(state.get(K.KEY_COMPANY_LEGAL_NAME, ""))
        self._display_name_edit.setText(state.get(K.KEY_COMPANY_DISPLAY_NAME, ""))
        country = state.get(K.KEY_COMPANY_COUNTRY_CODE)
        if country:
            self._country_combo.set_current_value(country)
        currency = state.get(K.KEY_COMPANY_CURRENCY_CODE)
        if currency:
            self._currency_combo.set_current_value(currency)
        self._tax_id_edit.setText(state.get(K.KEY_COMPANY_TAX_IDENTIFIER, ""))

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        errors: dict[str, str] = {}
        legal = self._legal_name_edit.text().strip()
        display = self._display_name_edit.text().strip()
        country = self._selected_code(self._country_combo)
        currency = self._selected_code(self._currency_combo)
        if not legal:
            errors["Legal Name"] = "is required."
        if not display:
            errors["Display Name"] = "is required."
        if not country:
            errors["Country"] = "is required."
        if not currency:
            errors["Base Currency"] = "is required."
        if errors:
            return StepValidationResult.fail(field_errors=errors)
        return StepValidationResult.ok()

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_COMPANY_LEGAL_NAME] = self._legal_name_edit.text().strip()
        state[K.KEY_COMPANY_DISPLAY_NAME] = self._display_name_edit.text().strip()
        state[K.KEY_COMPANY_COUNTRY_CODE] = self._selected_code(self._country_combo)
        state[K.KEY_COMPANY_CURRENCY_CODE] = self._selected_code(self._currency_combo)
        state[K.KEY_COMPANY_TAX_IDENTIFIER] = self._tax_id_edit.text().strip() or None

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_COMPANY_ID):
            return  # Idempotent: company already created on a prior attempt.
        command = CreateCompanyCommand(
            legal_name=state[K.KEY_COMPANY_LEGAL_NAME],
            display_name=state[K.KEY_COMPANY_DISPLAY_NAME],
            country_code=state[K.KEY_COMPANY_COUNTRY_CODE],
            base_currency_code=state[K.KEY_COMPANY_CURRENCY_CODE],
            tax_identifier=state.get(K.KEY_COMPANY_TAX_IDENTIFIER),
            email=self._email_edit.text().strip() or None,
        )
        try:
            dto = context.service_registry.company_service.create_company(command)
        except (ValidationError, ConflictError):
            raise
        state[K.KEY_COMPANY_ID] = dto.id
        # Rebind the wizard context to the new company for downstream steps.
        context.company_id = dto.id

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        legal = state.get(K.KEY_COMPANY_LEGAL_NAME, "—")
        country = state.get(K.KEY_COMPANY_COUNTRY_CODE, "—")
        currency = state.get(K.KEY_COMPANY_CURRENCY_CODE, "—")
        return f"Create company \u201c{legal}\u201d ({country} / {currency})."

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _selected_code(combo: SearchableComboBox) -> str:
        v = combo.current_value()
        return v if isinstance(v, str) else ""
