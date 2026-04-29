"""Repository for ``wizard_runs``."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.platform.wizards.persistence.wizard_run import WizardRun


class WizardRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: WizardRun) -> WizardRun:
        self._session.add(run)
        return run

    def get_by_id(self, run_id: int) -> WizardRun | None:
        return self._session.get(WizardRun, run_id)

    def list_resumable_for_user(
        self,
        user_id: int,
        wizard_code: str | None = None,
    ) -> list[WizardRun]:
        statement = select(WizardRun).where(
            WizardRun.initiated_by_user_id == user_id,
            WizardRun.status_code.in_(("draft", "in_progress", "failed")),
        )
        if wizard_code is not None:
            statement = statement.where(WizardRun.wizard_code == wizard_code)
        statement = statement.order_by(WizardRun.updated_at.desc(), WizardRun.id.desc())
        return list(self._session.scalars(statement))

    def save(self, run: WizardRun) -> WizardRun:
        self._session.add(run)
        return run
