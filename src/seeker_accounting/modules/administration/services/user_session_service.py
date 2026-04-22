"""UserSessionService — tracks login/logout session pairs for audit integrity."""
from __future__ import annotations

import logging
import platform
import socket
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.dto.user_session_dto import UserSessionDTO
from seeker_accounting.modules.administration.models.user_session import UserSession
from seeker_accounting.modules.administration.repositories.user_session_repository import (
    UserSessionRepository,
)
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.event_type_catalog import (
    MODULE_AUTH,
    USER_SESSION_ABNORMAL_ADMIN_REVIEWED,
    USER_SESSION_ABNORMAL_RESOLVED,
    USER_SESSION_ENDED,
    USER_SESSION_STARTED,
)

if TYPE_CHECKING:
    from seeker_accounting.app.context.app_context import AppContext
    from seeker_accounting.modules.audit.services.audit_service import AuditService

_log = logging.getLogger(__name__)

UserSessionRepositoryFactory = Callable[[Session], UserSessionRepository]


class UserSessionService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        user_session_repository_factory: UserSessionRepositoryFactory,
        app_context: AppContext,
        audit_service: AuditService | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._repo_factory = user_session_repository_factory
        self._app_context = app_context
        self._audit_service = audit_service

    # ── Session lifecycle ──────────────────────────────────────────────

    def start_session(self, user_id: int, company_id: int) -> int:
        """Create a new session row and return its id."""
        from seeker_accounting import __version__

        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            us = UserSession(
                user_id=user_id,
                company_id=company_id,
                app_version=__version__,
                hostname=_safe_hostname(),
                os_info=_safe_os_info(),
            )
            repo.add(us)
            uow.commit()
            session_id = us.id

        if self._audit_service:
            try:
                self._audit_service.record_event(
                    company_id,
                    RecordAuditEventCommand(
                        event_type_code=USER_SESSION_STARTED,
                        module_code=MODULE_AUTH,
                        entity_type="UserSession",
                        entity_id=session_id,
                        description=f"Session started for user {user_id}.",
                    ),
                )
            except Exception:
                _log.warning("Failed to record session-start audit event.", exc_info=True)

        return session_id

    def end_session(self, session_id: int | None, reason: str = "normal") -> None:
        """Close an active session with the given reason."""
        if session_id is None:
            return
        company_id: int | None = None
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            repo.close_session(session_id, reason)
            us = repo.get_by_id(session_id)
            if us:
                company_id = us.company_id
            uow.commit()

        if self._audit_service and company_id is not None:
            try:
                self._audit_service.record_event(
                    company_id,
                    RecordAuditEventCommand(
                        event_type_code=USER_SESSION_ENDED,
                        module_code=MODULE_AUTH,
                        entity_type="UserSession",
                        entity_id=session_id,
                        description=f"Session ended (reason={reason}).",
                    ),
                )
            except Exception:
                _log.warning("Failed to record session-end audit event.", exc_info=True)

    # ── Abnormal session detection and resolution ──────────────────────

    def check_abnormal_previous_sessions(self, user_id: int) -> list[UserSessionDTO]:
        """Return any sessions that were never closed (abnormal termination)."""
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            rows = repo.find_open_sessions_for_user(user_id)
            return [_to_dto(r) for r in rows]

    def resolve_abnormal_session(
        self,
        session_id: int,
        explanation_code: str,
        explanation_note: str | None = None,
    ) -> None:
        """User explains what happened during an abnormal shutdown."""
        company_id: int | None = None
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            repo.resolve_abnormal(session_id, explanation_code, explanation_note)
            us = repo.get_by_id(session_id)
            if us:
                company_id = us.company_id
            uow.commit()

        if self._audit_service and company_id is not None:
            try:
                self._audit_service.record_event(
                    company_id,
                    RecordAuditEventCommand(
                        event_type_code=USER_SESSION_ABNORMAL_RESOLVED,
                        module_code=MODULE_AUTH,
                        entity_type="UserSession",
                        entity_id=session_id,
                        description=(
                            f"Abnormal session resolved: {explanation_code}"
                            + (f" — {explanation_note}" if explanation_note else "")
                        ),
                    ),
                )
            except Exception:
                _log.warning("Failed to record abnormal-resolved audit event.", exc_info=True)

    # ── Admin review ───────────────────────────────────────────────────

    def get_unreviewed_abnormal_sessions_for_company(
        self,
        company_id: int,
    ) -> list[UserSessionDTO]:
        """Return abnormal sessions that have not yet been reviewed by an admin."""
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            rows = repo.find_unreviewed_abnormal_sessions(company_id)
            return [_to_dto(r) for r in rows]

    def mark_abnormal_reviewed(self, session_id: int, reviewed_by_user_id: int) -> None:
        """Admin acknowledges an abnormal session entry."""
        company_id: int | None = None
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = self._repo_factory(uow.session)
            repo.mark_reviewed(session_id, reviewed_by_user_id)
            us = repo.get_by_id(session_id)
            if us:
                company_id = us.company_id
            uow.commit()

        if self._audit_service and company_id is not None:
            try:
                self._audit_service.record_event(
                    company_id,
                    RecordAuditEventCommand(
                        event_type_code=USER_SESSION_ABNORMAL_ADMIN_REVIEWED,
                        module_code=MODULE_AUTH,
                        entity_type="UserSession",
                        entity_id=session_id,
                        description=f"Abnormal session reviewed by user {reviewed_by_user_id}.",
                    ),
                )
            except Exception:
                _log.warning("Failed to record admin-reviewed audit event.", exc_info=True)


# ── Helpers ────────────────────────────────────────────────────────────

def _to_dto(us: UserSession) -> UserSessionDTO:
    return UserSessionDTO(
        id=us.id,
        user_id=us.user_id,
        user_display_name=us.user.display_name if us.user else "",
        company_id=us.company_id,
        login_at=us.login_at,
        logout_at=us.logout_at,
        logout_reason=us.logout_reason,
        abnormal_explanation_code=us.abnormal_explanation_code,
        abnormal_explanation_note=us.abnormal_explanation_note,
        abnormal_reviewed_by_user_id=us.abnormal_reviewed_by_user_id,
        abnormal_reviewed_at=us.abnormal_reviewed_at,
        app_version=us.app_version,
        hostname=us.hostname,
        os_info=us.os_info,
    )


def _safe_hostname() -> str:
    try:
        return socket.gethostname()[:255]
    except Exception:
        return ""


def _safe_os_info() -> str:
    try:
        return f"{platform.system()} {platform.release()} ({platform.machine()})"[:255]
    except Exception:
        return ""
