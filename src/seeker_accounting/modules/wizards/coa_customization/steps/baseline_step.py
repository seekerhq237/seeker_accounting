"""Step 1 — Optionally apply the OHADA baseline chart."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.wizards.coa_customization import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)

DEFAULT_TEMPLATE = "ohada_syscohada_v1"


class BaselineStep(WizardStep):
    key = "baseline"
    title = "Baseline chart"
    subtitle = "Optionally apply the OHADA SYSCOHADA chart as the starting point."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._apply: QCheckBox | None = None
        self._info: QLabel | None = None
        self._result: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._info = QLabel(
            "Applying the baseline imports the OHADA SYSCOHADA chart in additive mode "
            "(existing accounts are preserved; only missing accounts are inserted).",
            root,
        )
        self._info.setWordWrap(True)
        self._info.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._info)

        self._apply = QCheckBox("Apply OHADA SYSCOHADA baseline", root)
        outer.addWidget(self._apply)

        self._result = QLabel(root)
        self._result.setObjectName("WizardSuccessText")
        self._result.setWordWrap(True)
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._apply is not None:
            self._apply.setChecked(bool(state.get(K.KEY_APPLY_BASELINE)))
        if self._result is not None and state.get(K.KEY_BASELINE_APPLIED):
            imported = int(state.get(K.KEY_BASELINE_RESULT_IMPORTED) or 0)
            skipped = int(state.get(K.KEY_BASELINE_RESULT_SKIPPED) or 0)
            total = int(state.get(K.KEY_BASELINE_RESULT_TOTAL) or 0)
            self._result.setText(
                f"Baseline applied: {imported} imported, {skipped} already existed "
                f"(of {total} template rows)."
            )

    def write_back(self, state: WizardState) -> None:
        if self._apply is not None:
            state[K.KEY_APPLY_BASELINE] = bool(self._apply.isChecked())
        state.setdefault(K.KEY_BASELINE_TEMPLATE, DEFAULT_TEMPLATE)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if not state.get(K.KEY_APPLY_BASELINE):
            return
        if state.get(K.KEY_BASELINE_APPLIED):
            return
        company_id = context.require_company_id()
        template = str(state.get(K.KEY_BASELINE_TEMPLATE) or DEFAULT_TEMPLATE)
        # ChartSeedService.seed_built_in_chart is additive (skips existing).
        result = context.service_registry.chart_seed_service.seed_built_in_chart(
            company_id, template
        )
        state[K.KEY_BASELINE_RESULT_IMPORTED] = int(result.imported_count)
        state[K.KEY_BASELINE_RESULT_SKIPPED] = int(result.skipped_existing_count)
        state[K.KEY_BASELINE_RESULT_INVALID] = int(result.invalid_row_count)
        state[K.KEY_BASELINE_RESULT_TOTAL] = int(result.total_template_rows)
        state[K.KEY_BASELINE_RESULT_MESSAGES] = list(result.messages)
        state[K.KEY_BASELINE_APPLIED] = True

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        if state.get(K.KEY_BASELINE_APPLIED):
            return f"Imported {state.get(K.KEY_BASELINE_RESULT_IMPORTED)} accounts."
        return "Baseline will be applied." if state.get(K.KEY_APPLY_BASELINE) else "Skip baseline."
