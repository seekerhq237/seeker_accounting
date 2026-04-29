"""Step 1 — Pick the asset to dispose."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.asset_disposal import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class PickAssetStep(WizardStep):
    key = "pick_asset"
    title = "Select asset"
    subtitle = "Pick the asset to dispose. Only active or fully-depreciated assets are eligible."

    def __init__(self) -> None:
        super().__init__()
        self._combo: QComboBox | None = None
        self._populated_once = False
        self._info: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()
        self._combo = QComboBox(root)
        form.addRow(QLabel("Asset:", root), self._combo)
        outer.addLayout(form)
        self._info = QLabel("", root)
        self._info.setWordWrap(True)
        outer.addWidget(self._info)
        outer.addStretch(1)
        self._combo.currentIndexChanged.connect(self._update_info)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._combo is None or self._populated_once:
            self._update_info(0)
            return
        company_id = context.require_company_id()
        try:
            assets = context.service_registry.asset_service.list_assets(company_id)
        except Exception:
            assets = []
        self._combo.clear()
        # Stash a parallel mapping so we can hydrate state without re-fetching.
        self._asset_by_id: dict[int, object] = {}
        for a in assets:
            if a.status_code not in ("active", "fully_depreciated"):
                continue
            label = (
                f"{a.asset_number} — {a.asset_name} "
                f"(cost {a.acquisition_cost}) [{a.status_code}]"
            )
            self._combo.addItem(label, int(a.id))
            self._asset_by_id[int(a.id)] = a
        existing = state.get(K.KEY_ASSET_ID)
        if isinstance(existing, int):
            idx = self._combo.findData(existing)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        self._populated_once = True
        self._update_info(self._combo.currentIndex())

    def _update_info(self, _idx: int) -> None:
        if self._combo is None or self._info is None:
            return
        data = self._combo.currentData()
        if not isinstance(data, int):
            self._info.setText("")
            return
        a = getattr(self, "_asset_by_id", {}).get(data)
        if a is None:
            self._info.setText("")
            return
        self._info.setText(
            f"Acquisition cost: {a.acquisition_cost}<br>"
            f"Acquired: {a.acquisition_date} | Capitalized: {a.capitalization_date}<br>"
            f"Status: {a.status_code}"
        )

    def write_back(self, state: WizardState) -> None:
        if self._combo is None:
            return
        data = self._combo.currentData()
        if isinstance(data, int):
            a = getattr(self, "_asset_by_id", {}).get(data)
            state[K.KEY_ASSET_ID] = int(data)
            if a is not None:
                state[K.KEY_ASSET_NUMBER] = a.asset_number
                state[K.KEY_ASSET_NAME] = a.asset_name
                state[K.KEY_ASSET_ACQUISITION_COST] = a.acquisition_cost
                state[K.KEY_ASSET_STATUS_CODE] = a.status_code
        else:
            state[K.KEY_ASSET_ID] = None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_ASSET_ID), int):
            return StepValidationResult.fail(
                "Pick an asset. If none are listed, no eligible assets exist."
            )
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        return state.get(K.KEY_ASSET_NUMBER)
