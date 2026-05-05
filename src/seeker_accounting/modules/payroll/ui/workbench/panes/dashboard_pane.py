"""Payroll dashboard pane (Phase 2, slice S2).

Three calm sections:

1. **Period card** — current period state (open / locked / closed) with
   readiness badge.
2. **Next actions** — task list driven by
   :class:`PayrollValidationDashboardService` (errors first, then
   warnings).
3. **Recent activity** — last few payroll runs with their state.

The pane reads from existing services only; if any service is missing
or raises, the affected section degrades to a calm empty state.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.services.payroll_setup_checklist_service import (
    PayrollSetupChecklistService,
)
from seeker_accounting.modules.payroll.ui.workbench.setup_checklist_widget import (
    SetupChecklistWidget,
)
from seeker_accounting.shared.ui.components import (
    SeverityPill,
    StatusChip,
    normalize_severity,
)
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Section header
# ──────────────────────────────────────────────────────────────────────


class _SectionTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("PayrollDashboardSectionTitle")


# ──────────────────────────────────────────────────────────────────────
# Pane
# ──────────────────────────────────────────────────────────────────────


class PayrollDashboardPane(QFrame):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollDashboardPane")
        self._sr = service_registry
        self._checklist_service = PayrollSetupChecklistService()

        spacing = DEFAULT_TOKENS.spacing

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget(scroll)
        content.setObjectName("PayrollDashboardContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        layout.setSpacing(spacing.dialog_section_gap)

        # Section: First-run setup checklist (P12.S2).
        self._setup_checklist = SetupChecklistWidget(content)
        layout.addWidget(self._setup_checklist)

        # Section: Period card.
        self._period_section = self._build_period_section()
        layout.addWidget(self._period_section)

        # Section: Next actions.
        self._next_actions_title = _SectionTitle("Next actions", content)
        layout.addWidget(self._next_actions_title)
        self._next_actions_host = QFrame(content)
        self._next_actions_host.setObjectName("PayrollDashboardNextActions")
        self._next_actions_layout = QVBoxLayout(self._next_actions_host)
        self._next_actions_layout.setContentsMargins(0, 0, 0, 0)
        self._next_actions_layout.setSpacing(spacing.dialog_field_gap)
        layout.addWidget(self._next_actions_host)

        # Section: Recent activity.
        layout.addWidget(_SectionTitle("Recent payroll runs", content))
        self._activity_host = QFrame(content)
        self._activity_host.setObjectName("PayrollDashboardActivity")
        self._activity_layout = QVBoxLayout(self._activity_host)
        self._activity_layout.setContentsMargins(0, 0, 0, 0)
        self._activity_layout.setSpacing(spacing.dialog_field_gap)
        layout.addWidget(self._activity_host)

        layout.addStretch(1)

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.refresh()

    # ── Public ───────────────────────────────────────────────────────

    def refresh(self) -> None:
        company_id = self._active_company_id()
        self._refresh_setup_checklist(company_id)
        self._refresh_period_card(company_id)
        self._refresh_next_actions(company_id)
        self._refresh_activity(company_id)

    def _refresh_setup_checklist(self, company_id: int | None) -> None:
        """Evaluate and display the first-run setup checklist."""
        if company_id is None:
            self._setup_checklist.hide()
            return
        try:
            result = self._checklist_service.evaluate(company_id, self._sr)
        except Exception:  # pragma: no cover — defensive
            logger.debug("setup_checklist evaluate failed", exc_info=True)
            self._setup_checklist.hide()
            return
        self._setup_checklist.load(company_id, result)

    # ── Helpers ──────────────────────────────────────────────────────

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            company = ctx.get_active_company()
        except Exception:  # pragma: no cover — defensive
            logger.debug("get_active_company failed", exc_info=True)
            return None
        return getattr(company, "id", None) if company else None

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    # ── Period section ───────────────────────────────────────────────

    def _build_period_section(self) -> QWidget:
        spacing = DEFAULT_TOKENS.spacing
        host = QFrame(self)
        host.setObjectName("PayrollDashboardPeriodCard")
        host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(host)
        layout.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        layout.setSpacing(spacing.dialog_field_gap)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(spacing.compact_gap)

        self._period_label = QLabel("—", host)
        self._period_label.setObjectName("PayrollDashboardPeriodTitle")
        title_row.addWidget(self._period_label)
        title_row.addStretch(1)

        self._period_state_pill = SeverityPill("info", label="Loading…", parent=host)
        title_row.addWidget(self._period_state_pill)

        self._period_readiness_pill = SeverityPill("info", label="Readiness pending", parent=host)
        title_row.addWidget(self._period_readiness_pill)

        layout.addLayout(title_row)

        self._period_summary = QLabel("", host)
        self._period_summary.setObjectName("PayrollDashboardPeriodSummary")
        self._period_summary.setWordWrap(True)
        layout.addWidget(self._period_summary)

        return host

    def _refresh_period_card(self, company_id: int | None) -> None:
        if company_id is None:
            self._period_label.setText("No active company")
            self._period_state_pill.set_severity("notice")
            self._period_state_pill.set_label("—")
            self._period_readiness_pill.set_severity("notice")
            self._period_readiness_pill.set_label("Select a company to view payroll readiness")
            self._period_summary.setText("")
            return

        today = date.today()
        period_year = today.year
        period_month = today.month
        period_label = self._period_label_for(company_id, today)
        self._period_label.setText(period_label or f"{today.strftime('%B %Y')}")

        # Period state — try fiscal calendar.
        state_text, state_severity = self._period_state(company_id, today)
        self._period_state_pill.set_severity(state_severity)
        self._period_state_pill.set_label(state_text)

        # Readiness.
        readiness = self._readiness_for(company_id, period_year, period_month)
        if readiness is None:
            self._period_readiness_pill.set_severity("notice")
            self._period_readiness_pill.set_label("Readiness check unavailable")
            self._period_summary.setText("")
            return

        ready, total = readiness["ready"], readiness["total"]
        errors, warnings = readiness["errors"], readiness["warnings"]

        if errors:
            self._period_readiness_pill.set_severity("error")
            self._period_readiness_pill.set_label(f"{errors} blocking issue(s)")
        elif warnings:
            self._period_readiness_pill.set_severity("warning")
            self._period_readiness_pill.set_label(f"{warnings} warning(s)")
        else:
            self._period_readiness_pill.set_severity("info")
            self._period_readiness_pill.set_label("Ready to run")

        if total > 0:
            self._period_summary.setText(
                f"{ready} / {total} employees ready · "
                f"{errors} error(s), {warnings} warning(s)"
            )
        else:
            self._period_summary.setText("No employees configured for this period.")

    def _period_label_for(self, company_id: int, target: date) -> str | None:
        svc = getattr(self._sr, "fiscal_calendar_service", None)
        if svc is None:
            return None
        try:
            period = svc.get_current_period(company_id)
        except Exception:  # pragma: no cover — defensive
            logger.debug("get_current_period failed", exc_info=True)
            return None
        if period is None:
            return None
        for attr in ("label", "name", "code"):
            value = getattr(period, attr, None)
            if value:
                return str(value)
        return None

    def _period_state(self, company_id: int, target: date) -> tuple[str, str]:
        """Return (label, severity) for the period state pill."""
        svc = getattr(self._sr, "fiscal_calendar_service", None)
        if svc is None:
            return ("Open", "info")
        try:
            period = svc.get_current_period(company_id)
        except Exception:  # pragma: no cover — defensive
            return ("Open", "info")
        if period is None:
            return ("No period", "notice")
        # Common shapes: status_code, is_locked, is_closed, state.
        status = (
            getattr(period, "status_code", None)
            or getattr(period, "state", None)
            or ("closed" if getattr(period, "is_closed", False) else None)
            or ("locked" if getattr(period, "is_locked", False) else None)
            or "open"
        )
        severity_map = {
            "open": "info",
            "locked": "warning",
            "closed": "notice",
        }
        return (str(status).title(), severity_map.get(str(status).lower(), "info"))

    def _readiness_for(
        self,
        company_id: int,
        period_year: int,
        period_month: int,
    ) -> dict[str, int] | None:
        svc = getattr(self._sr, "payroll_validation_dashboard_service", None)
        if svc is None:
            return None
        try:
            result = svc.run_full_assessment(company_id, period_year, period_month)
        except Exception:  # pragma: no cover — defensive (permission denied etc.)
            logger.debug("run_full_assessment failed", exc_info=True)
            return None
        return {
            "ready": getattr(result, "ready_employee_count", 0),
            "total": getattr(result, "employee_count", 0),
            "errors": getattr(result, "error_count", 0),
            "warnings": getattr(result, "warning_count", 0),
        }

    # ── Next actions ─────────────────────────────────────────────────

    def _refresh_next_actions(self, company_id: int | None) -> None:
        self._clear_layout(self._next_actions_layout)
        if company_id is None:
            self._next_actions_layout.addWidget(
                build_empty_state("payroll.no_company")
            )
            return

        today = date.today()
        readiness = self._readiness_checks_for(company_id, today.year, today.month)
        if readiness is None:
            self._next_actions_layout.addWidget(
                build_empty_state("generic.no_records")
            )
            return

        if not readiness:
            self._next_actions_layout.addWidget(
                build_empty_state("payroll.dashboard.no_actions")
            )
            return

        # Order: error > warning > info; cap at 8 items.
        ordered = sorted(
            readiness,
            key=lambda c: (
                {"error": 0, "warning": 1, "info": 2}.get(
                    str(getattr(c, "severity", "info")).lower(), 3
                ),
                str(getattr(c, "title", "")),
            ),
        )[:8]
        for check in ordered:
            self._next_actions_layout.addWidget(self._build_action_row(check))

    def _readiness_checks_for(
        self,
        company_id: int,
        period_year: int,
        period_month: int,
    ) -> list[Any] | None:
        svc = getattr(self._sr, "payroll_validation_dashboard_service", None)
        if svc is None:
            return None
        try:
            result = svc.run_full_assessment(company_id, period_year, period_month)
        except Exception:
            logger.debug("run_full_assessment failed for next actions", exc_info=True)
            return None
        return list(getattr(result, "checks", ()) or ())

    def _build_action_row(self, check: Any) -> QWidget:
        spacing = DEFAULT_TOKENS.spacing
        row = QFrame(self)
        row.setObjectName("PayrollDashboardActionRow")
        row.setProperty("severity", normalize_severity(getattr(check, "severity", "info")))

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(
            spacing.dialog_field_gap,
            spacing.dialog_label_gap,
            spacing.dialog_field_gap,
            spacing.dialog_label_gap,
        )
        row_layout.setSpacing(spacing.compact_gap)

        pill = SeverityPill(
            normalize_severity(getattr(check, "severity", "info")),
            label=getattr(check, "category", "").title() or "Action",
            parent=row,
        )
        row_layout.addWidget(pill)

        text_box = QFrame(row)
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title = QLabel(str(getattr(check, "title", "—")), text_box)
        title.setObjectName("PayrollDashboardActionTitle")
        title.setWordWrap(True)
        text_layout.addWidget(title)

        message = str(getattr(check, "message", ""))
        if message:
            body = QLabel(message, text_box)
            body.setObjectName("PayrollDashboardActionBody")
            body.setWordWrap(True)
            text_layout.addWidget(body)

        row_layout.addWidget(text_box, 1)

        entity_label = getattr(check, "entity_label", None)
        if entity_label:
            anchor = QLabel(str(entity_label), row)
            anchor.setObjectName("PayrollDashboardActionEntity")
            anchor.setAlignment(Qt.AlignmentFlag.AlignRight)
            row_layout.addWidget(anchor)

        return row

    # ── Recent activity ──────────────────────────────────────────────

    def _refresh_activity(self, company_id: int | None) -> None:
        self._clear_layout(self._activity_layout)
        if company_id is None:
            self._activity_layout.addWidget(
                build_empty_state("payroll.dashboard.no_activity")
            )
            return

        runs = self._recent_runs(company_id)
        if not runs:
            self._activity_layout.addWidget(
                build_empty_state("payroll.dashboard.no_activity")
            )
            return

        for run in runs[:6]:
            self._activity_layout.addWidget(self._build_run_row(run))

    def _recent_runs(self, company_id: int) -> list[Any]:
        svc = getattr(self._sr, "payroll_run_service", None)
        if svc is None:
            return []
        try:
            runs = list(svc.list_runs(company_id))
        except Exception:  # pragma: no cover — defensive
            logger.warning("list_runs failed for activity feed", exc_info=True)
            return []
        runs.sort(
            key=lambda r: (
                getattr(r, "period_year", 0) or 0,
                getattr(r, "period_month", 0) or 0,
            ),
            reverse=True,
        )
        return runs

    def _build_run_row(self, run: Any) -> QWidget:
        spacing = DEFAULT_TOKENS.spacing
        row = QFrame(self)
        row.setObjectName("PayrollDashboardActivityRow")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(
            spacing.dialog_field_gap,
            spacing.dialog_label_gap,
            spacing.dialog_field_gap,
            spacing.dialog_label_gap,
        )
        layout.setSpacing(spacing.compact_gap)

        label_text = (
            getattr(run, "run_label", None)
            or getattr(run, "run_reference", None)
            or "Payroll run"
        )
        period = ""
        py = getattr(run, "period_year", None)
        pm = getattr(run, "period_month", None)
        if py and pm:
            period = f"{py:04d}-{pm:02d}"
        title = QLabel(f"{label_text}    {period}".strip(), row)
        title.setObjectName("PayrollDashboardActivityTitle")
        layout.addWidget(title, 1)

        amount = getattr(run, "total_net_payable", None)
        ccy = getattr(run, "currency_code", "")
        if isinstance(amount, Decimal):
            amount_label = QLabel(f"{ccy} {amount:,.0f}".strip(), row)
        elif amount is not None:
            amount_label = QLabel(f"{ccy} {amount}".strip(), row)
        else:
            amount_label = QLabel("", row)
        amount_label.setObjectName("PayrollDashboardActivityAmount")
        amount_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(amount_label)

        status = getattr(run, "status_code", "draft")
        chip = StatusChip(str(status).title(), family=None, parent=row)
        layout.addWidget(chip)

        return row
