"""Step 5 — Default tax codes."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import (
    CreateTaxCodeCommand,
)
from seeker_accounting.modules.wizards.company_setup import state_keys as K
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


# (code, name, tax_type, calculation_method, rate_percent, is_recoverable,
#  has_cac, base_rate_percent, cac_rate_percent, exemption_kind, return_box_code)
_DEFAULTS: tuple[
    tuple[
        str,
        str,
        str,
        str,
        Decimal | None,
        bool | None,
        bool,
        Decimal | None,
        Decimal | None,
        str | None,
        str | None,
    ],
    ...,
] = (
    (
        "VAT-19.25",
        "VAT 19.25% (Standard)",
        "VAT",
        "PERCENTAGE",
        Decimal("19.25"),
        True,
        True,
        Decimal("17.5000"),
        Decimal("10.0000"),
        None,
        "L17",
    ),
    (
        "VAT-EXEMPT",
        "VAT Exempt",
        "VAT",
        "EXEMPT",
        None,
        None,
        False,
        None,
        None,
        "EXEMPT",
        "L22",
    ),
    (
        "WHT-5.5",
        "Withholding 5.5%",
        "WITHHOLDING",
        "PERCENTAGE",
        Decimal("5.5"),
        False,
        False,
        None,
        None,
        None,
        None,
    ),
)


class TaxCodesStep(WizardStep):
    key = "tax_codes"
    title = "Tax Codes"
    subtitle = "Seed common VAT and withholding tax codes for this company."

    def __init__(self) -> None:
        super().__init__()
        self._checkboxes: dict[str, QCheckBox] = {}

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        intro = QLabel(
            "Seeded tax codes use defaults for OHADA jurisdictions. Edit rates, "
            "validity windows, and account mappings later in Reference Data \u203a Taxes.",
            root,
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #4E5866; font-size: 11px;")
        layout.addWidget(intro)

        for code, name, *_rest in _DEFAULTS:
            cb = QCheckBox(f"{code}  ·  {name}", root)
            cb.setChecked(True)
            self._checkboxes[code] = cb
            layout.addWidget(cb)

        layout.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        selected = state.get(K.KEY_TAX_CODES_TO_CREATE)
        if isinstance(selected, list):
            for code, cb in self._checkboxes.items():
                cb.setChecked(code in selected)

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_TAX_CODES_TO_CREATE] = [
            code for code, cb in self._checkboxes.items() if cb.isChecked()
        ]

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_TAX_CODES_CREATED) is not None:
            return
        company_id = context.require_company_id()
        service = context.service_registry.tax_setup_service
        wanted = set(state.get(K.KEY_TAX_CODES_TO_CREATE, []))
        existing = {tc.code for tc in service.list_tax_codes(company_id)}
        effective_from = date.today().replace(month=1, day=1)
        created = 0
        for (
            code,
            name,
            tax_type,
            calc_method,
            rate,
            recoverable,
            has_cac,
            base_rate,
            cac_rate,
            exemption_kind,
            return_box_code,
        ) in _DEFAULTS:
            if code not in wanted or code in existing:
                continue
            try:
                service.create_tax_code(
                    company_id,
                    CreateTaxCodeCommand(
                        code=code,
                        name=name,
                        tax_type_code=tax_type,
                        calculation_method_code=calc_method,
                        effective_from=effective_from,
                        rate_percent=rate,
                        is_recoverable=recoverable,
                        has_cac=has_cac,
                        base_rate_percent=base_rate,
                        cac_rate_percent=cac_rate,
                        exemption_kind=exemption_kind,
                        return_box_code=return_box_code,
                    ),
                )
            except (ValidationError, ConflictError):
                continue
            created += 1
        state[K.KEY_TAX_CODES_CREATED] = created

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        chosen = state.get(K.KEY_TAX_CODES_TO_CREATE) or []
        if not chosen:
            return "No tax codes will be created."
        return f"Create tax codes: {', '.join(chosen)}."
