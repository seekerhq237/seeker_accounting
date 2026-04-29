"""Service for persisting and resuming wizard runs.

Used by ``WizardHostDialog`` to record progress so a user can stop a long
wizard and resume later. The service intentionally does not own UI state — it
only stores what was reported by the controller.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.platform.wizards.persistence.wizard_run import WizardRun
from seeker_accounting.platform.wizards.persistence.wizard_run_dto import (
    WizardRunDTO,
    WizardRunListItemDTO,
    WizardRunStatusCode,
)
from seeker_accounting.platform.wizards.persistence.wizard_run_repository import (
    WizardRunRepository,
)

WizardRunRepositoryFactory = Callable[[Session], WizardRunRepository]


class WizardRunService:
    """Create, update, and complete wizard runs."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        repository_factory: WizardRunRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._repo_factory = repository_factory

    # ── Create ──────────────────────────────────────────────────────────

    def begin_run(
        self,
        *,
        wizard_code: str,
        user_id: int,
        company_id: int | None,
        initial_state_payload: str | None = None,
    ) -> WizardRunDTO:
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            run = WizardRun(
                wizard_code=wizard_code,
                company_id=company_id,
                initiated_by_user_id=user_id,
                current_step_index=0,
                current_step_key=None,
                status_code=WizardRunStatusCode.IN_PROGRESS.value,
                state_payload=initial_state_payload,
            )
            repo.add(run)
            uow.commit()
            uow.session.refresh(run)
            return self._to_dto(run)

    # ── Update ──────────────────────────────────────────────────────────

    def update_progress(
        self,
        run_id: int,
        *,
        current_step_index: int,
        current_step_key: str | None,
        state_payload: str | None,
        company_id: int | None = None,
    ) -> None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            run = repo.get_by_id(run_id)
            if run is None:
                raise NotFoundError(f"Wizard run {run_id} not found.")
            run.current_step_index = current_step_index
            run.current_step_key = current_step_key
            run.state_payload = state_payload
            if company_id is not None and run.company_id is None:
                run.company_id = company_id
            uow.commit()

    # ── Terminal states ─────────────────────────────────────────────────

    def complete_run(self, run_id: int, *, final_state_payload: str | None = None) -> None:
        self._set_terminal_status(
            run_id,
            WizardRunStatusCode.COMPLETED,
            final_state_payload=final_state_payload,
        )

    def cancel_run(self, run_id: int) -> None:
        self._set_terminal_status(run_id, WizardRunStatusCode.CANCELLED)

    def fail_run(self, run_id: int, reason: str) -> None:
        self._set_terminal_status(run_id, WizardRunStatusCode.FAILED, failure_reason=reason)

    def _set_terminal_status(
        self,
        run_id: int,
        status: WizardRunStatusCode,
        *,
        failure_reason: str | None = None,
        final_state_payload: str | None = None,
    ) -> None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            run = repo.get_by_id(run_id)
            if run is None:
                raise NotFoundError(f"Wizard run {run_id} not found.")
            run.status_code = status.value
            run.completed_at = datetime.utcnow()
            if failure_reason is not None:
                run.failure_reason = failure_reason
            if final_state_payload is not None:
                run.state_payload = final_state_payload
            uow.commit()

    # ── Read ────────────────────────────────────────────────────────────

    def get_run(self, run_id: int) -> WizardRunDTO:
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            run = repo.get_by_id(run_id)
            if run is None:
                raise NotFoundError(f"Wizard run {run_id} not found.")
            return self._to_dto(run)

    def list_resumable_for_user(
        self,
        user_id: int,
        wizard_code: str | None = None,
    ) -> list[WizardRunListItemDTO]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            runs = repo.list_resumable_for_user(user_id, wizard_code)
            return [
                WizardRunListItemDTO(
                    id=r.id,
                    wizard_code=r.wizard_code,
                    company_id=r.company_id,
                    current_step_index=r.current_step_index,
                    current_step_key=r.current_step_key,
                    status_code=r.status_code,
                    updated_at=r.updated_at,
                )
                for r in runs
            ]

    # ── Mapping ─────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(run: WizardRun) -> WizardRunDTO:
        return WizardRunDTO(
            id=run.id,
            wizard_code=run.wizard_code,
            company_id=run.company_id,
            initiated_by_user_id=run.initiated_by_user_id,
            current_step_index=run.current_step_index,
            current_step_key=run.current_step_key,
            status_code=run.status_code,
            state_payload=run.state_payload,
            failure_reason=run.failure_reason,
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
        )
