"""Shared wizard launcher helpers.

Centralizes the boilerplate around:

- resolving the active company id and current user id from a ``ServiceRegistry``
- recording a ``wizard_runs`` lifecycle row (begin / complete / cancel / fail)
- showing a host dialog and translating its outcome into a typed result

Domain-specific launchers (one per wizard) compose these helpers — they only
have to wire steps, advisor, title, and the post-exit result mapping.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Sequence, TypeVar

from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from seeker_accounting.platform.wizards.advisor import AssistantEngine, WizardAdvisor
from seeker_accounting.platform.wizards.context import WizardContext
from seeker_accounting.platform.wizards.controller import (
    WizardController,
    WizardLifecycleStatus,
)
from seeker_accounting.platform.wizards.host_dialog import WizardHostDialog
from seeker_accounting.platform.wizards.state import WizardState
from seeker_accounting.platform.wizards.step import WizardStep

logger = logging.getLogger("seeker_accounting.platform.wizards.launcher")

T = TypeVar("T")


@dataclass(slots=True)
class WizardOutcome:
    """Raw outcome of running a wizard host dialog."""

    completed: bool
    lifecycle: WizardLifecycleStatus
    state: WizardState
    wizard_run_id: int | None


def resolve_active_company_id(service_registry: object) -> int | None:
    ctx = getattr(service_registry, "active_company_context", None)
    if ctx is None:
        return None
    return getattr(ctx, "company_id", None)


def resolve_user_id(service_registry: object) -> int | None:
    app_context = getattr(service_registry, "app_context", None)
    if app_context is None:
        return None
    return getattr(app_context, "current_user_id", None)


def require_active_company(
    service_registry: object,
    *,
    parent: QWidget | None,
    feature_label: str,
) -> int | None:
    """Resolve the active company id; show a warning and return None if absent."""
    company_id = resolve_active_company_id(service_registry)
    if company_id is None:
        QMessageBox.warning(
            parent,
            feature_label,
            f"Pick an active company before opening {feature_label}.",
        )
    return company_id


def run_wizard(
    *,
    service_registry: object,
    wizard_code: str,
    title: str,
    intro: str,
    steps: Sequence[WizardStep],
    advisor: WizardAdvisor | None = None,
    company_id: int,
    parent: QWidget | None = None,
) -> WizardOutcome:
    """Begin a wizard run, render its host dialog, and finalize the run record."""
    user_id = resolve_user_id(service_registry)
    run_service = getattr(service_registry, "wizard_run_service", None)

    wizard_run_id: int | None = None
    if run_service is not None and user_id is not None:
        try:
            run = run_service.begin_run(
                wizard_code=wizard_code,
                user_id=user_id,
                company_id=company_id,
                initial_state_payload=None,
            )
            wizard_run_id = run.id
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to record wizard run begin (wizard_code=%s); proceeding without persistence.",
                wizard_code,
            )

    context = WizardContext(
        service_registry=service_registry,
        company_id=company_id,
        user_id=user_id,
        wizard_run_id=wizard_run_id,
    )
    controller = WizardController(
        wizard_code=wizard_code,
        steps=list(steps),
        context=context,
        state=WizardState(),
        advisor=advisor,
        assistant_engine=AssistantEngine(),
    )

    dialog = WizardHostDialog(controller=controller, title=title, intro=intro, parent=parent)
    code = dialog.exec()
    completed = (
        code == QDialog.DialogCode.Accepted
        and controller.lifecycle is WizardLifecycleStatus.COMMITTED
    )

    if run_service is not None and wizard_run_id is not None:
        try:
            payload = controller.state.to_json()
            if completed:
                run_service.complete_run(wizard_run_id, final_state_payload=payload)
            elif controller.lifecycle is WizardLifecycleStatus.FAILED:
                run_service.fail_run(wizard_run_id, "Wizard failed during commit.")
            else:
                run_service.cancel_run(wizard_run_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to update wizard run final status (wizard_run_id=%s).",
                wizard_run_id,
            )

    return WizardOutcome(
        completed=completed,
        lifecycle=controller.lifecycle,
        state=controller.state,
        wizard_run_id=wizard_run_id,
    )


def launch_wizard(
    *,
    service_registry: object,
    wizard_code: str,
    title: str,
    intro: str,
    steps_factory: Callable[[], Sequence[WizardStep]],
    advisor_factory: Callable[[], WizardAdvisor] | None = None,
    feature_label: str | None = None,
    parent: QWidget | None = None,
    result_factory: Callable[[WizardOutcome], T] | None = None,
) -> T | WizardOutcome | None:
    """Top-level helper: guards active company, runs the wizard, returns result.

    Returns ``None`` when no active company is selected (after warning the user).
    Otherwise returns the value produced by ``result_factory`` (if supplied) or
    the raw ``WizardOutcome``.
    """
    label = feature_label or title
    company_id = require_active_company(service_registry, parent=parent, feature_label=label)
    if company_id is None:
        return None

    advisor = advisor_factory() if advisor_factory is not None else None
    outcome = run_wizard(
        service_registry=service_registry,
        wizard_code=wizard_code,
        title=title,
        intro=intro,
        steps=steps_factory(),
        advisor=advisor,
        company_id=company_id,
        parent=parent,
    )
    if result_factory is not None:
        return result_factory(outcome)
    return outcome
