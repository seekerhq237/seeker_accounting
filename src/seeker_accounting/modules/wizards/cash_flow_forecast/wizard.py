"""Cash Flow Forecast wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.cash_flow_forecast_dto import (
    CashFlowForecastDTO,
)
from seeker_accounting.modules.wizards.cash_flow_forecast import state_keys as K
from seeker_accounting.modules.wizards.cash_flow_forecast.advisor import (
    build_cash_flow_forecast_advisor,
)
from seeker_accounting.modules.wizards.cash_flow_forecast.steps.review_step import (
    ReviewStep,
)
from seeker_accounting.modules.wizards.cash_flow_forecast.steps.setup_step import (
    SetupStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "cash_flow_forecast"


@dataclass(slots=True)
class CashFlowForecastResult:
    completed: bool
    forecast: CashFlowForecastDTO | None
    wizard_run_id: int | None


class CashFlowForecastWizard:
    @staticmethod
    def steps_factory():
        return [SetupStep(), ReviewStep()]

    @staticmethod
    def advisor_factory():
        return build_cash_flow_forecast_advisor()


def launch_cash_flow_forecast_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> CashFlowForecastResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Cash Flow Forecast",
        intro=(
            "Project net cash position over a chosen horizon using current "
            "posted balances plus open AR and AP documents grouped by due date. "
            "This is a read-only diagnostic — nothing is posted."
        ),
        steps_factory=CashFlowForecastWizard.steps_factory,
        advisor_factory=CashFlowForecastWizard.advisor_factory,
        feature_label="Cash Flow Forecast",
        parent=parent,
    )
    if outcome is None:
        return CashFlowForecastResult(False, None, None)
    assert isinstance(outcome, WizardOutcome)
    forecast = outcome.state.get(K.KEY_FORECAST)
    return CashFlowForecastResult(
        completed=outcome.completed,
        forecast=forecast if isinstance(forecast, CashFlowForecastDTO) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
