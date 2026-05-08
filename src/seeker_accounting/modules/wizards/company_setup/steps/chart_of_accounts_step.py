"""Step 3 — Chart of Accounts (OHADA built-in seed)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.company_setup import state_keys as K
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_OHADA_TEMPLATE = "ohada_syscohada_v1"


class ChartOfAccountsStep(WizardStep):
    key = "chart_of_accounts"
    title = "Chart of Accounts"
    subtitle = "Seed the OHADA SYSCOHADA chart, or skip and configure manually later."
    commits_on_advance = True

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._seed_checkbox = QCheckBox(
            "Seed OHADA SYSCOHADA chart of accounts (recommended).",
            root,
        )
        self._seed_checkbox.setChecked(True)
        layout.addWidget(self._seed_checkbox)

        helper = QLabel(
            "Seeding installs the standard OHADA classes 1–9 and a working set "
            "of accounts your accountant can extend. Skipping leaves the chart "
            "empty — you must add accounts manually before posting transactions.",
            root,
        )
        helper.setWordWrap(True)
        helper.setObjectName("WizardMutedText")
        layout.addWidget(helper)
        layout.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        self._seed_checkbox.setChecked(bool(state.get(K.KEY_COA_SEED_REQUESTED, True)))

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_COA_SEED_REQUESTED] = self._seed_checkbox.isChecked()
        state[K.KEY_COA_SEED_TEMPLATE] = _OHADA_TEMPLATE

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_COA_ACCOUNTS_CREATED) is not None:
            return
        if not state.get(K.KEY_COA_SEED_REQUESTED):
            state[K.KEY_COA_ACCOUNTS_CREATED] = 0
            return
        company_id = context.require_company_id()
        try:
            result = context.service_registry.company_seed_service.initialize_new_company(
                company_id,
                seed_built_in_chart=True,
                template_code=_OHADA_TEMPLATE,
            )
        except (ValidationError, ConflictError):
            raise
        state[K.KEY_COA_ACCOUNTS_CREATED] = result.imported_count if result else 0

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        if state.get(K.KEY_COA_SEED_REQUESTED):
            return "Seed OHADA SYSCOHADA chart of accounts."
        return "Skip chart of accounts seeding."
