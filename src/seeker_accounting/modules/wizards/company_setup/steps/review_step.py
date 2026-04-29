"""Step 7 — Review & finish.

Renders a read-only summary of every prior step's preview() so the user
sees exactly what the wizard will do (or has already done, for steps that
committed in-flight). Clicking Finish runs ``commit_all`` for any deferred
commits.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.company_setup import state_keys as K
from seeker_accounting.platform.wizards import (
    WizardContext,
    WizardState,
    WizardStep,
)


class ReviewStep(WizardStep):
    key = "review"
    title = "Review"
    subtitle = "Confirm what the wizard will commit."

    def __init__(self) -> None:
        super().__init__()
        self._summary_layout: QVBoxLayout | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Summary of changes", root)
        title.setStyleSheet("font-size: 13px; font-weight: 600; color: #1A2230;")
        layout.addWidget(title)

        helper = QLabel(
            "Review the actions the wizard has already performed and any final "
            "steps that will commit when you click Finish.",
            root,
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #4E5866; font-size: 11px;")
        layout.addWidget(helper)

        card = QFrame(root)
        card.setStyleSheet(
            "background: #F4F6FA; border: 1px solid #D4DAE3; border-radius: 2px;"
        )
        self._summary_layout = QVBoxLayout(card)
        self._summary_layout.setContentsMargins(12, 10, 12, 10)
        self._summary_layout.setSpacing(6)
        layout.addWidget(card)
        layout.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        layout = self._summary_layout
        if layout is None:
            return
        # Clear prior labels (re-render on every load).
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # Walk siblings for previews.
        controller_steps = self._gather_sibling_steps(context, state)
        rendered_any = False
        for step in controller_steps:
            preview = step.preview(context, state)
            if not preview:
                continue
            row = QLabel(f"\u2022  {preview}", self.widget)
            row.setWordWrap(True)
            row.setStyleSheet("color: #1A2230; font-size: 12px;")
            layout.addWidget(row)
            rendered_any = True

        # Companion lines that surface counts captured in state.
        coa_count = state.get(K.KEY_COA_ACCOUNTS_CREATED)
        if coa_count is not None and coa_count > 0:
            layout.addWidget(self._info_line(f"Chart of accounts: {coa_count} accounts seeded."))
        seq_count = state.get(K.KEY_DOC_SEQ_CREATED)
        if seq_count is not None:
            layout.addWidget(self._info_line(f"Document sequences created: {seq_count}."))
        tax_count = state.get(K.KEY_TAX_CODES_CREATED)
        if tax_count is not None:
            layout.addWidget(self._info_line(f"Tax codes created: {tax_count}."))
        periods = state.get(K.KEY_FISCAL_PERIODS_GENERATED)
        if periods:
            layout.addWidget(self._info_line(f"Fiscal periods generated: {periods}."))

        if not rendered_any:
            empty = QLabel("Nothing to commit.", self.widget)
            empty.setStyleSheet("color: #7A8392; font-size: 12px;")
            layout.addWidget(empty)

    def _info_line(self, text: str) -> QLabel:
        label = QLabel(text, self.widget)
        label.setStyleSheet("color: #4E5866; font-size: 11px;")
        return label

    def _gather_sibling_steps(self, context: WizardContext, state: WizardState):
        """Return previously-imported step instances by importing them.

        We import lazily to avoid a circular dependency between the review
        step and the wizard composition module.
        """
        from seeker_accounting.modules.wizards.company_setup.steps.account_role_mappings_step import (
            AccountRoleMappingsStep,
        )
        from seeker_accounting.modules.wizards.company_setup.steps.chart_of_accounts_step import (
            ChartOfAccountsStep,
        )
        from seeker_accounting.modules.wizards.company_setup.steps.company_info_step import (
            CompanyInfoStep,
        )
        from seeker_accounting.modules.wizards.company_setup.steps.document_sequences_step import (
            DocumentSequencesStep,
        )
        from seeker_accounting.modules.wizards.company_setup.steps.fiscal_year_step import (
            FiscalYearStep,
        )
        from seeker_accounting.modules.wizards.company_setup.steps.tax_codes_step import (
            TaxCodesStep,
        )

        # Build transient instances purely for preview() text — they don't
        # carry widgets, so this is cheap.
        return [
            CompanyInfoStep(),
            FiscalYearStep(),
            ChartOfAccountsStep(),
            DocumentSequencesStep(),
            TaxCodesStep(),
            AccountRoleMappingsStep(),
        ]
