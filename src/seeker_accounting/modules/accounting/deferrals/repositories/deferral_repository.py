"""Deferral repository — persistence layer for deferral schedules and lines."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.deferrals.models.deferral_schedule import (
    DEFERRAL_STATUS_ACTIVE,
    DEFERRAL_STATUS_DRAFT,
    LINE_STATUS_PENDING,
    LINE_STATUS_POSTED,
    DeferralSchedule,
    DeferralScheduleLine,
)


class DeferralRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Schedules ────────────────────────────────────────────────────

    def add_schedule(self, schedule: DeferralSchedule) -> None:
        self._session.add(schedule)

    def get_schedule_by_id(self, company_id: int, schedule_id: int) -> DeferralSchedule | None:
        return (
            self._session.query(DeferralSchedule)
            .filter(
                DeferralSchedule.id == schedule_id,
                DeferralSchedule.company_id == company_id,
            )
            .first()
        )

    def list_schedules(
        self,
        company_id: int,
        *,
        deferral_type: str | None = None,
        status_code: str | None = None,
    ) -> Sequence[DeferralSchedule]:
        q = self._session.query(DeferralSchedule).filter(
            DeferralSchedule.company_id == company_id
        )
        if deferral_type is not None:
            q = q.filter(DeferralSchedule.deferral_type == deferral_type)
        if status_code is not None:
            q = q.filter(DeferralSchedule.status_code == status_code)
        return q.order_by(DeferralSchedule.start_date.desc(), DeferralSchedule.id.desc()).all()

    def get_lines_for_schedule(self, schedule_id: int) -> Sequence[DeferralScheduleLine]:
        return (
            self._session.query(DeferralScheduleLine)
            .filter(DeferralScheduleLine.deferral_schedule_id == schedule_id)
            .order_by(DeferralScheduleLine.line_number)
            .all()
        )

    def get_line_by_id(
        self, schedule_id: int, line_id: int
    ) -> DeferralScheduleLine | None:
        return (
            self._session.query(DeferralScheduleLine)
            .filter(
                DeferralScheduleLine.id == line_id,
                DeferralScheduleLine.deferral_schedule_id == schedule_id,
            )
            .first()
        )

    def list_pending_lines_due(
        self, company_id: int, as_of_date: date
    ) -> Sequence[DeferralScheduleLine]:
        """Return all PENDING lines whose recognition_date <= as_of_date
        for ACTIVE schedules in the given company."""
        return (
            self._session.query(DeferralScheduleLine)
            .join(DeferralScheduleLine.schedule)
            .filter(
                DeferralSchedule.company_id == company_id,
                DeferralSchedule.status_code == DEFERRAL_STATUS_ACTIVE,
                DeferralScheduleLine.status_code == LINE_STATUS_PENDING,
                DeferralScheduleLine.recognition_date <= as_of_date,
            )
            .order_by(DeferralScheduleLine.recognition_date)
            .all()
        )
