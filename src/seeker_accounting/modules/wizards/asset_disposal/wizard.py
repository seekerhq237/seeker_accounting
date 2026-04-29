"""Asset Disposal Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.asset_disposal import state_keys as K
from seeker_accounting.modules.wizards.asset_disposal.advisor import (
    build_asset_disposal_advisor,
)
from seeker_accounting.modules.wizards.asset_disposal.steps.confirm_step import ConfirmStep
from seeker_accounting.modules.wizards.asset_disposal.steps.disposal_details_step import (
    DisposalDetailsStep,
)
from seeker_accounting.modules.wizards.asset_disposal.steps.pick_asset_step import (
    PickAssetStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "asset_disposal"


@dataclass(slots=True)
class AssetDisposalResult:
    completed: bool
    disposed: bool
    asset_id: int | None
    journal_entry_id: int | None
    journal_entry_number: str | None
    wizard_run_id: int | None


class AssetDisposalWizard:
    @staticmethod
    def steps_factory():
        return [PickAssetStep(), DisposalDetailsStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_asset_disposal_advisor()


def launch_asset_disposal_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> AssetDisposalResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Asset Disposal",
        intro=(
            "Dispose of a fixed asset. The wizard posts a single balanced journal "
            "entry that records proceeds, clears the asset cost and accumulated "
            "depreciation, and books the residual gain or loss."
        ),
        steps_factory=AssetDisposalWizard.steps_factory,
        advisor_factory=AssetDisposalWizard.advisor_factory,
        feature_label="Asset Disposal",
        parent=parent,
    )
    if outcome is None:
        return AssetDisposalResult(False, False, None, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    asset_id = outcome.state.get(K.KEY_ASSET_ID)
    je_id = outcome.state.get(K.KEY_DISPOSAL_RESULT_JE_ID)
    return AssetDisposalResult(
        completed=outcome.completed,
        disposed=bool(outcome.state.get(K.KEY_DISPOSED)),
        asset_id=int(asset_id) if isinstance(asset_id, int) else None,
        journal_entry_id=int(je_id) if isinstance(je_id, int) else None,
        journal_entry_number=outcome.state.get(K.KEY_DISPOSAL_RESULT_JE_NUMBER),
        wizard_run_id=outcome.wizard_run_id,
    )
