"""Builds the `AmbientThoughtContextDTO` that flows into providers.

The collector pulls from three sources, in order of authority:

1. The shell: navigation service (`nav_id`), active company context.
2. The fiscal calendar service for the current open period (best-effort).
3. The currently-visible page, via the optional `get_ambient_context()`
   duck-typed contract — pages that have rich draft state can opt in by
   implementing it.

Failures in (2) and (3) are swallowed and logged. The collector never
throws into the shell; an empty context is always preferable to a
broken UI.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from seeker_accounting.shared.dto.ambient_thought_dto import AmbientThoughtContextDTO


if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry


logger = logging.getLogger(__name__)


class AmbientThoughtContextService:
    """Stateless context assembler. Safe to call repeatedly."""

    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def build(
        self,
        *,
        nav_id: str | None = None,
        page: QWidget | None = None,
    ) -> AmbientThoughtContextDTO:
        sr = self._sr

        active_nav_id = nav_id or getattr(sr.navigation_service, "current_nav_id", None)
        active_company = sr.active_company_context
        company_id = active_company.company_id
        company_name = active_company.company_name
        base_currency_code = active_company.base_currency_code
        user_id = sr.app_context.current_user_id

        period_id: int | None = None
        period_status: str | None = None
        period_end_iso: str | None = None
        if isinstance(company_id, int):
            try:
                period = sr.fiscal_calendar_service.get_current_period(company_id)
            except Exception:
                logger.debug(
                    "Ambient context: fiscal_calendar_service.get_current_period failed.",
                    exc_info=True,
                )
                period = None
            if period is not None:
                period_id = getattr(period, "fiscal_period_id", None) or getattr(period, "id", None)
                period_status = getattr(period, "status_code", None)
                end_date = getattr(period, "end_date", None)
                if end_date is not None:
                    try:
                        period_end_iso = end_date.isoformat()
                    except Exception:
                        period_end_iso = str(end_date)

        page_context = self._collect_page_context(page)

        return AmbientThoughtContextDTO(
            nav_id=active_nav_id,
            company_id=company_id if isinstance(company_id, int) else None,
            company_name=company_name,
            base_currency_code=base_currency_code,
            fiscal_period_id=period_id if isinstance(period_id, int) else None,
            fiscal_period_status=period_status,
            fiscal_period_end_date=period_end_iso,
            user_id=user_id if isinstance(user_id, int) else None,
            page_context=page_context,
        )

    @staticmethod
    def _collect_page_context(page: QWidget | None) -> tuple[tuple[str, object], ...]:
        """Collect page context from the workspace page and any active modal dialog.

        The modal dialog (if any) takes priority over the workspace page for
        the same key — the dialog has the most current draft state.
        """
        merged: dict[str, object] = {}

        # ── workspace page ────────────────────────────────────────────
        if page is not None:
            getter = getattr(page, "get_ambient_context", None)
            if callable(getter):
                try:
                    raw = getter()
                    if isinstance(raw, dict):
                        merged.update(raw)
                except Exception:
                    logger.debug(
                        "Ambient context: page.get_ambient_context() raised; ignoring.",
                        exc_info=True,
                    )

        # ── active modal dialog ───────────────────────────────────────
        try:
            from PySide6.QtWidgets import QApplication
            modal = QApplication.activeModalWidget()
            if modal is not None:
                # Try the top-level widget directly, then its parent.
                for candidate in (modal, modal.parent()):
                    if candidate is None:
                        continue
                    dialog_getter = getattr(candidate, "get_ambient_context", None)
                    if callable(dialog_getter):
                        try:
                            raw = dialog_getter()
                            if isinstance(raw, dict):
                                merged.update(raw)  # dialog overrides page
                        except Exception:
                            logger.debug(
                                "Ambient context: dialog.get_ambient_context() raised; ignoring.",
                                exc_info=True,
                            )
                        break
        except Exception:
            logger.debug(
                "Ambient context: modal-dialog context collection failed.",
                exc_info=True,
            )

        if not merged:
            return ()
        # Sort for deterministic ordering — providers should not depend on
        # insertion order, but stable order keeps logs readable.
        return tuple(sorted(((str(k), v) for k, v in merged.items()), key=lambda kv: kv[0]))
