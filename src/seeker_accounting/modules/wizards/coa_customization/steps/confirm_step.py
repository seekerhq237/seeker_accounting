"""Step 3 — Confirm: persist role mapping changes."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.wizards.coa_customization import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


def _diff_role_changes(state: WizardState) -> tuple[dict[str, int], list[str]]:
    """Returns (to_set: role_code -> account_id, to_clear: list[role_code])."""
    selections: dict[str, int | None] = dict(state.get(K.KEY_ROLE_SELECTIONS) or {})
    current: dict[str, int] = dict(state.get(K.KEY_ROLE_CURRENT) or {})
    to_set: dict[str, int] = {}
    to_clear: list[str] = []
    for role_code, new_account_id in selections.items():
        existing = current.get(role_code)
        if isinstance(new_account_id, int):
            if existing != new_account_id:
                to_set[role_code] = new_account_id
        else:
            if isinstance(existing, int):
                to_clear.append(role_code)
    return to_set, to_clear


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Review and persist role mappings."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._result: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._summary)
        self._result = QLabel(root)
        self._result.setStyleSheet("color: #2a7;")
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        to_set, to_clear = _diff_role_changes(state)
        if self._summary is not None:
            html_parts = [
                "<b>Baseline:</b> "
                + ("applied" if state.get(K.KEY_BASELINE_APPLIED) else "skipped")
                + "<br>"
            ]
            if state.get(K.KEY_BASELINE_APPLIED):
                html_parts.append(
                    f"&nbsp;&nbsp;Imported: {state.get(K.KEY_BASELINE_RESULT_IMPORTED)} | "
                    f"Skipped: {state.get(K.KEY_BASELINE_RESULT_SKIPPED)} | "
                    f"Total: {state.get(K.KEY_BASELINE_RESULT_TOTAL)}<br>"
                )
            html_parts.append(
                f"<b>Role mappings to set:</b> {len(to_set)}<br>"
                f"<b>Role mappings to clear:</b> {len(to_clear)}"
            )
            self._summary.setText("".join(html_parts))
        if self._result is not None and state.get(K.KEY_MAPPINGS_PERSISTED):
            updated = int(state.get(K.KEY_MAPPINGS_UPDATED_COUNT) or 0)
            cleared = int(state.get(K.KEY_MAPPINGS_CLEARED_COUNT) or 0)
            self._result.setText(f"Persisted: {updated} updated, {cleared} cleared.")

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_MAPPINGS_PERSISTED):
            return
        company_id = context.require_company_id()
        sr = context.service_registry
        to_set, to_clear = _diff_role_changes(state)

        updated = 0
        for role_code, account_id in to_set.items():
            try:
                sr.account_role_mapping_service.set_role_mapping(
                    company_id,
                    SetAccountRoleMappingCommand(role_code=role_code, account_id=account_id),
                )
                updated += 1
            except Exception:
                # Continue with the rest of the batch; fail-soft per role.
                continue

        cleared = 0
        for role_code in to_clear:
            try:
                sr.account_role_mapping_service.clear_role_mapping(company_id, role_code)
                cleared += 1
            except Exception:
                continue

        state[K.KEY_MAPPINGS_UPDATED_COUNT] = updated
        state[K.KEY_MAPPINGS_CLEARED_COUNT] = cleared
        state[K.KEY_MAPPINGS_PERSISTED] = True

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        if state.get(K.KEY_MAPPINGS_PERSISTED):
            return (
                f"Updated {state.get(K.KEY_MAPPINGS_UPDATED_COUNT)}, "
                f"cleared {state.get(K.KEY_MAPPINGS_CLEARED_COUNT)}."
            )
        return "Ready to persist."
