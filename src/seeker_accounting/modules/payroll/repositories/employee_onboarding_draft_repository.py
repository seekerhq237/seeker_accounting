"""Repository for the Phase 4 Hire-to-Pay BP draft aggregate."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.payroll.models.employee_onboarding_draft import (
    EmployeeOnboardingDraft,
)


class EmployeeOnboardingDraftRepository:
    """Persistence for :class:`EmployeeOnboardingDraft`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Reads ────────────────────────────────────────────────────────

    def get(self, draft_id: int) -> EmployeeOnboardingDraft | None:
        return self._session.get(EmployeeOnboardingDraft, draft_id)

    def get_for_company(
        self, draft_id: int, company_id: int
    ) -> EmployeeOnboardingDraft | None:
        draft = self._session.get(EmployeeOnboardingDraft, draft_id)
        if draft is None or draft.company_id != company_id:
            return None
        return draft

    def list_active_for_company(
        self, company_id: int
    ) -> list[EmployeeOnboardingDraft]:
        """Return drafts that are still in a non-terminal state."""
        stmt = (
            select(EmployeeOnboardingDraft)
            .where(EmployeeOnboardingDraft.company_id == company_id)
            .where(EmployeeOnboardingDraft.completed_at.is_(None))
            .where(EmployeeOnboardingDraft.abandoned_at.is_(None))
            .order_by(EmployeeOnboardingDraft.id.desc())
        )
        return list(self._session.scalars(stmt))

    def list_for_company(
        self,
        company_id: int,
        *,
        include_completed: bool = False,
        include_abandoned: bool = False,
        limit: int | None = None,
    ) -> list[EmployeeOnboardingDraft]:
        stmt = select(EmployeeOnboardingDraft).where(
            EmployeeOnboardingDraft.company_id == company_id
        )
        if not include_completed:
            stmt = stmt.where(EmployeeOnboardingDraft.completed_at.is_(None))
        if not include_abandoned:
            stmt = stmt.where(EmployeeOnboardingDraft.abandoned_at.is_(None))
        stmt = stmt.order_by(EmployeeOnboardingDraft.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt))

    # ── Writes ───────────────────────────────────────────────────────

    def save(
        self, draft: EmployeeOnboardingDraft
    ) -> EmployeeOnboardingDraft:
        self._session.add(draft)
        return draft

    def delete(self, draft: EmployeeOnboardingDraft) -> None:
        self._session.delete(draft)
