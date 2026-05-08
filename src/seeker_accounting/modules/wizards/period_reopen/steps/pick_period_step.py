"""Step 1 — Pick a CLOSED or LOCKED period to reopen."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.period_reopen import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_REOPENABLE_STATUSES = {"CLOSED", "LOCKED"}


class PickPeriodStep(WizardStep):
    key = "pick_period"
    title = "Pick Period"
    subtitle = "Choose a closed or locked period to reopen."

    def __init__(self) -> None:
        super().__init__()
        self._combo: QComboBox | None = None
        self._info: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        intro = QLabel(
            "Reopening a period will unlock posting back into it. Use this only "
            "when you have a documented reason and the proper authority.",
            root,
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardWarningText")
        outer.addWidget(intro)

        form = QFormLayout()
        self._combo = QComboBox(root)
        form.addRow(QLabel("Period:", root), self._combo)
        outer.addLayout(form)

        self._info = QLabel("", root)
        self._info.setWordWrap(True)
        self._info.setObjectName("WizardMutedText")
        outer.addWidget(self._info)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._combo is None:
            return
        company_id = context.require_company_id()
        periods = context.service_registry.fiscal_calendar_service.list_periods(company_id)
        candidates = sorted(
            [p for p in periods if p.status_code in _REOPENABLE_STATUSES],
            key=lambda p: p.start_date,
            reverse=True,
        )
        self._combo.blockSignals(True)
        self._combo.clear()
        if not candidates:
            self._combo.addItem("(no closed or locked periods)", None)
        else:
            for p in candidates:
                self._combo.addItem(
                    f"{p.period_code} — {p.period_name}  [{p.status_code}]",
                    {"id": p.id, "code": p.period_code, "name": p.period_name, "status": p.status_code},
                )
        self._combo.blockSignals(False)

        prior_id = state.get(K.KEY_PERIOD_ID)
        if isinstance(prior_id, int):
            for i in range(self._combo.count()):
                data = self._combo.itemData(i)
                if isinstance(data, dict) and data.get("id") == prior_id:
                    self._combo.setCurrentIndex(i)
                    break

    def write_back(self, state: WizardState) -> None:
        if self._combo is None:
            return
        data = self._combo.currentData()
        if not isinstance(data, dict):
            for k in (K.KEY_PERIOD_ID, K.KEY_PERIOD_CODE, K.KEY_PERIOD_NAME, K.KEY_PREVIOUS_STATUS):
                state.pop(k, None)
            return
        state[K.KEY_PERIOD_ID] = int(data["id"])
        state[K.KEY_PERIOD_CODE] = str(data["code"])
        state[K.KEY_PERIOD_NAME] = str(data["name"])
        state[K.KEY_PREVIOUS_STATUS] = str(data["status"])

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_PERIOD_ID), int):
            return StepValidationResult.fail("Pick a period.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        code = state.get(K.KEY_PERIOD_CODE)
        if not code:
            return None
        return f"Reopen {code} (currently {state.get(K.KEY_PREVIOUS_STATUS)})."
