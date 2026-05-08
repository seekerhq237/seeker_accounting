"""Step 6 — Account role mappings (functional).

Maps the most posting-critical account roles (AR/AP control, VAT in/out,
retained earnings, bank clearing, payroll payable, sales/purchases default)
to concrete chart-of-accounts entries seeded earlier in the wizard.

Roles left unmapped are recorded as deferred so downstream workflows can
surface the gap.
"""
from __future__ import annotations

from typing import Final

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.wizards.company_setup import state_keys as K
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_PRIORITY_ROLES: Final[tuple[str, ...]] = (
    "ar_control",
    "ap_control",
    "vat_input",
    "vat_output",
    "retained_earnings",
    "bank_clearing",
    "payroll_payable",
    "sales_revenue_default",
    "purchases_expense_default",
)


class AccountRoleMappingsStep(WizardStep):
    key = "account_role_mappings"
    title = "Account Roles"
    subtitle = "Map control accounts now (or skip — you can finish later)."

    def __init__(self) -> None:
        super().__init__()
        self._combos: dict[str, QComboBox] = {}
        self._role_labels: dict[str, str] = {}

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        intro = QLabel(
            "Pick a chart-of-accounts entry for each role below. Leave any "
            "role on \u201c\u2014 not mapped \u2014\u201d to finish later in "
            "Reference Data \u203a Account Role Mappings.",
            root,
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardMutedText")
        outer.addWidget(intro)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        for role_code in _PRIORITY_ROLES:
            combo = QComboBox(root)
            combo.setMinimumWidth(280)
            self._combos[role_code] = combo
            label = QLabel(self._format_role_label(role_code), root)
            label.setObjectName("WizardBodyText")
            form.addRow(label, combo)
        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        registry = context.service_registry
        coa_service = registry.chart_of_accounts_service
        role_service = registry.account_role_mapping_service
        company_id = context.company_id
        if company_id is None:
            for combo in self._combos.values():
                combo.clear()
                combo.addItem("\u2014 not mapped \u2014", None)
            return

        try:
            for option in role_service.list_role_options():
                self._role_labels[option.role_code] = option.label
        except Exception:  # noqa: BLE001
            pass

        accounts = [
            acc for acc in coa_service.list_accounts(company_id, active_only=True)
            if acc.allow_manual_posting
        ]
        accounts.sort(key=lambda a: a.account_code)

        existing: dict[str, int | None] = {}
        try:
            for mapping in role_service.list_role_mappings(company_id):
                existing[mapping.role_code] = mapping.account_id
        except Exception:  # noqa: BLE001
            pass

        prior: dict[str, int | None] = state.get(K.KEY_ROLE_MAPPING_SELECTIONS, {}) or {}

        for role_code, combo in self._combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("\u2014 not mapped \u2014", None)
            for acc in accounts:
                combo.addItem(f"{acc.account_code} — {acc.account_name}", acc.id)
            preselect = prior.get(role_code, existing.get(role_code))
            if preselect is not None:
                idx = combo.findData(preselect)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def write_back(self, state: WizardState) -> None:
        selections: dict[str, int | None] = {}
        for role_code, combo in self._combos.items():
            account_id = combo.currentData()
            selections[role_code] = int(account_id) if account_id is not None else None
        state[K.KEY_ROLE_MAPPING_SELECTIONS] = selections
        deferred = [code for code, aid in selections.items() if aid is None]
        state[K.KEY_ROLE_MAPPINGS_DEFERRED] = bool(deferred)
        state[K.KEY_ROLE_MAPPINGS_DEFERRED_LIST] = deferred

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_ROLE_MAPPINGS_APPLIED) is not None:
            return
        company_id = context.company_id
        if company_id is None:
            state[K.KEY_ROLE_MAPPINGS_APPLIED] = 0
            return
        role_service = context.service_registry.account_role_mapping_service
        selections: dict[str, int | None] = state.get(K.KEY_ROLE_MAPPING_SELECTIONS, {}) or {}
        applied = 0
        for role_code, account_id in selections.items():
            if account_id is None:
                continue
            try:
                role_service.set_role_mapping(
                    company_id,
                    SetAccountRoleMappingCommand(
                        role_code=role_code,
                        account_id=int(account_id),
                    ),
                )
                applied += 1
            except (ValidationError, ConflictError, NotFoundError):
                continue
        state[K.KEY_ROLE_MAPPINGS_APPLIED] = applied

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        selections: dict[str, int | None] = state.get(K.KEY_ROLE_MAPPING_SELECTIONS, {}) or {}
        mapped = [code for code, aid in selections.items() if aid is not None]
        deferred = [code for code, aid in selections.items() if aid is None]
        if not selections:
            return "Account role mappings will be deferred."
        parts: list[str] = []
        if mapped:
            parts.append(
                f"Map {len(mapped)} role(s): "
                + ", ".join(self._format_role_label(c) for c in mapped)
                + "."
            )
        if deferred:
            parts.append(
                f"Defer {len(deferred)} role(s) to Reference Data \u203a Account Role Mappings."
            )
        return " ".join(parts)

    def _format_role_label(self, role_code: str) -> str:
        if role_code in self._role_labels:
            return self._role_labels[role_code]
        return role_code.replace("_", " ").title()
