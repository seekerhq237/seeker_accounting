"""Payroll Workbench page (Phase 2, slice S1).

Replaces the four legacy payroll sidebar nodes with a single workbench
page composed of:

- a workbench header (title, period subtitle, KPI tiles),
- a left rail with eight task-oriented panes,
- a stacked workspace that lazily builds each pane the first time it
  is opened.

The legacy four pages remain reachable via the existing sidebar entries
while the workbench rolls out behind ``FLAG_PAYROLL_WORKBENCH``.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.ui.workbench.workbench_panes import (
    PANE_AUDIT,
    PANE_COMPENSATION,
    PANE_DASHBOARD,
    PANE_KEYS,
    PANE_PEOPLE,
    PANE_REPORTS,
    PANE_RUN,
    PANE_SETUP,
    PANE_STATUTORY,
    build_workbench_panes,
)
from seeker_accounting.modules.payroll.ui.i18n import tr
from seeker_accounting.shared.ui.components import (
    KpiTile,
    KpiTileData,
    WorkbenchHeader,
)
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)


class PayrollWorkbenchPage(QWidget):
    """Top-level page for ``nav_ids.PAYROLL_WORKBENCH``."""

    #: Emitted when the user selects a pane (key from ``PANE_KEYS``).
    pane_changed = Signal(str)

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollWorkbenchPage")
        self._sr = service_registry
        self._panes: dict[str, QWidget] = {}
        self._pane_specs = build_workbench_panes()
        self._kpi_tiles: dict[str, KpiTile] = {}
        self._current_pane_key: str = PANE_DASHBOARD

        self._build_ui()
        self._wire_active_company_signal()
        self.refresh()

    # ── Construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        sizes = DEFAULT_TOKENS.sizes

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header.
        self._header = WorkbenchHeader(self)
        self._header.set_title(tr("Payroll Workbench"))
        self._header.set_subtitle(tr("Loading..."))
        self._kpi_strip = self._build_kpi_strip()
        self._header.set_context_widget(self._kpi_strip)
        outer.addWidget(self._header)

        # Body: rail + stacked workspace.
        body = QFrame(self)
        body.setObjectName("PayrollWorkbenchBody")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._rail = QListWidget(body)
        self._rail.setObjectName("PayrollWorkbenchRail")
        self._rail.setFixedWidth(sizes.side_panel_min_width // 2 + 60)  # ≈ 220px
        self._rail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._rail.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._rail.setAlternatingRowColors(False)
        self._rail.setUniformItemSizes(True)
        for pane in self._pane_specs:
            item = QListWidgetItem(pane.label, self._rail)
            item.setData(Qt.ItemDataRole.UserRole, pane.key)
            item.setToolTip(pane.description)
        self._rail.currentRowChanged.connect(self._on_rail_row_changed)
        body_layout.addWidget(self._rail)

        self._stack = QStackedWidget(body)
        self._stack.setObjectName("PayrollWorkbenchStack")
        body_layout.addWidget(self._stack, 1)

        outer.addWidget(body, 1)

        # Default to Dashboard.
        self._rail.setCurrentRow(0)

    def _build_kpi_strip(self) -> QWidget:
        host = QFrame(self)
        host.setObjectName("PayrollWorkbenchKpiStrip")
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Four placeholders; populated by ``_refresh_kpis``.
        for key, label in (
            ("open_run", "Open run"),
            ("last_posted", "Last posted"),
            ("active_employees", "Active employees"),
            ("statutory_due", "Statutory due"),
        ):
            tile = KpiTile(KpiTileData(label=tr(label), value="—"))
            self._kpi_tiles[key] = tile
            layout.addWidget(tile)

        return host

    # ── Active company plumbing ──────────────────────────────────────

    def _wire_active_company_signal(self) -> None:
        ctx = getattr(self._sr, "active_company_context", None)
        if ctx is None:
            return
        signal = getattr(ctx, "active_company_changed", None)
        if signal is not None:
            try:
                signal.connect(self._on_active_company_changed)
            except Exception:  # pragma: no cover — defensive
                logger.debug("active_company_changed signal not connectable", exc_info=True)

    def _on_active_company_changed(self, *_args: Any) -> None:
        self.refresh()

    def _active_company(self) -> Any | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            return ctx.get_active_company()
        except Exception:  # pragma: no cover — defensive
            logger.warning("get_active_company failed", exc_info=True)
            return None

    # ── Public API ───────────────────────────────────────────────────

    def refresh(self) -> None:
        """Re-read header subtitle and KPI values."""
        self._refresh_header()
        self._refresh_kpis()

    def select_pane(self, key: str) -> None:
        if key not in PANE_KEYS:
            logger.warning("Unknown payroll workbench pane key: %s", key)
            return
        for row in range(self._rail.count()):
            item = self._rail.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
                self._rail.setCurrentRow(row)
                return

    def current_pane(self) -> str:
        return self._current_pane_key

    def handle_navigation_context(self, context: Mapping[str, Any] | None) -> None:
        """Hook used by deep links: ``context={"pane": "people"}``."""
        if not context:
            return
        pane = context.get("pane")
        if isinstance(pane, str):
            self.select_pane(pane)

    # ``WorkspaceHost`` calls ``set_navigation_context(dict)`` after each
    # navigation. We forward to the public deep-link handler.
    def set_navigation_context(self, context: Mapping[str, Any] | None) -> None:
        self.handle_navigation_context(context)

    # ── Event handlers ───────────────────────────────────────────────

    def _on_rail_row_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self._rail.item(row)
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(key, str):
            return
        self._show_pane(key)

    def _show_pane(self, key: str) -> None:
        widget = self._panes.get(key)
        if widget is None:
            widget = self._build_pane(key)
            self._panes[key] = widget
            self._stack.addWidget(widget)
        self._stack.setCurrentWidget(widget)
        self._current_pane_key = key
        self.pane_changed.emit(key)

    # ── Pane factories ───────────────────────────────────────────────

    def _build_pane(self, key: str) -> QWidget:
        """Lazily construct each pane the first time it is opened."""
        # Imports localised to avoid pulling all panes on first paint.
        if key == PANE_DASHBOARD:
            from seeker_accounting.modules.payroll.ui.workbench.panes.dashboard_pane import (
                PayrollDashboardPane,
            )
            return PayrollDashboardPane(self._sr, self)

        if key == PANE_PEOPLE:
            from seeker_accounting.modules.payroll.ui.workbench.panes.people_pane import (
                PeoplePaneWidget,
            )
            return PeoplePaneWidget(self._sr, self)

        if key == PANE_RUN:
            from seeker_accounting.modules.payroll.ui.workbench.panes.run_pane import (
                RunPaneWidget,
            )
            return RunPaneWidget(self._sr, self)

        if key == PANE_COMPENSATION:
            from seeker_accounting.modules.payroll.ui.workbench.panes.compensation_pane import (
                CompensationPaneWidget,
            )
            return CompensationPaneWidget(self._sr, self)

        if key == PANE_SETUP:
            from seeker_accounting.modules.payroll.ui.workbench.panes.setup_pane import (
                SetupPaneWidget,
            )
            return SetupPaneWidget(self._sr, self)

        if key == PANE_STATUTORY:
            from seeker_accounting.modules.payroll.ui.workbench.panes.statutory_pane import (
                StatutoryPaneWidget,
            )
            return StatutoryPaneWidget(self._sr, self)

        if key in (PANE_REPORTS, PANE_AUDIT):
            from seeker_accounting.modules.payroll.ui.workbench.panes.reports_pane import (
                ReportsAuditPaneWidget,
            )
            # Build once; both pane keys share the same widget (PANE_AUDIT
            # switches to the Audit Log tab on open).
            pane = ReportsAuditPaneWidget(self._sr, self)
            if key == PANE_AUDIT:
                # Pre-select the Audit Log tab
                try:
                    pane._tabs.setCurrentIndex(1)
                except Exception:
                    pass
            return pane

        # Fallback for any unrecognised future key
        placeholder = QFrame(self)
        placeholder.setObjectName(f"PayrollWorkbenchPane.{key}")
        inner = QVBoxLayout(placeholder)
        inner.addStretch(1)
        inner.addWidget(QLabel(f"Unknown pane: {key}", placeholder), 0, Qt.AlignmentFlag.AlignCenter)
        inner.addStretch(1)
        return placeholder

    # ── Header / KPI refresh ─────────────────────────────────────────

    def _refresh_header(self) -> None:
        company = self._active_company()
        company_name = getattr(company, "name", None) if company else None
        period_label = self._current_period_label()
        if company_name and period_label:
            subtitle = f"{company_name} · {period_label}"
        elif company_name:
            subtitle = str(company_name)
        elif period_label:
            subtitle = period_label
        else:
            subtitle = tr("No active company selected")
        self._header.set_subtitle(subtitle)

    def _current_period_label(self) -> str | None:
        company = self._active_company()
        if company is None:
            return None
        company_id = getattr(company, "id", None)
        if company_id is None:
            return None
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
        # Period DTOs in this codebase carry a label or start/end dates;
        # be resilient to either.
        for attr in ("label", "name", "code"):
            value = getattr(period, attr, None)
            if value:
                return str(value)
        start = getattr(period, "start_date", None)
        end = getattr(period, "end_date", None)
        if start and end:
            return f"{start} → {end}"
        return None

    def _refresh_kpis(self) -> None:
        company = self._active_company()
        if company is None:
            for tile in self._kpi_tiles.values():
                tile.update_data(KpiTileData(label=tile._data.label, value="—"))  # type: ignore[attr-defined]
            return

        company_id = getattr(company, "id", None)
        if company_id is None:
            return

        run_svc = getattr(self._sr, "payroll_run_service", None)
        emp_svc = getattr(self._sr, "employee_service", None)

        # Open run (latest non-posted).
        open_value = "—"
        last_posted_value = "—"
        if run_svc is not None:
            try:
                runs = run_svc.list_runs(company_id)
            except Exception:  # pragma: no cover — defensive
                logger.warning("payroll_run_service.list_runs failed", exc_info=True)
                runs = []
            open_runs = [r for r in runs if getattr(r, "status_code", "") not in ("posted", "closed")]
            if open_runs:
                latest = max(
                    open_runs,
                    key=lambda r: (
                        getattr(r, "period_year", 0) or 0,
                        getattr(r, "period_month", 0) or 0,
                    ),
                )
                open_value = f"{getattr(latest, 'run_label', None) or getattr(latest, 'run_reference', '')}".strip() or "1 in progress"
            posted_runs = [r for r in runs if getattr(r, "status_code", "") == "posted"]
            if posted_runs:
                latest_posted = max(
                    posted_runs,
                    key=lambda r: (
                        getattr(r, "period_year", 0) or 0,
                        getattr(r, "period_month", 0) or 0,
                    ),
                )
                amount = getattr(latest_posted, "total_net_payable", None)
                ccy = getattr(latest_posted, "currency_code", "")
                if isinstance(amount, Decimal):
                    last_posted_value = f"{ccy} {amount:,.0f}".strip()
                elif amount is not None:
                    last_posted_value = f"{ccy} {amount}".strip()
                else:
                    last_posted_value = (
                        getattr(latest_posted, "run_label", None)
                        or getattr(latest_posted, "run_reference", "—")
                    )

        # Active employees.
        active_value = "—"
        if emp_svc is not None:
            try:
                employees = emp_svc.list_employees(company_id, active_only=True)
            except Exception:  # pragma: no cover — defensive
                logger.warning("employee_service.list_employees failed", exc_info=True)
                employees = []
            active_value = str(len(employees))

        # Statutory due — keep aspirational until P5; show the count of
        # configured packs, otherwise "—".
        statutory_value = "—"
        pack_svc = getattr(self._sr, "payroll_statutory_pack_service", None)
        if pack_svc is not None:
            try:
                versions = pack_svc.list_pack_versions(company_id)
            except TypeError:
                # Some signatures require an authority code.
                versions = []
            except Exception:  # pragma: no cover — defensive
                logger.debug("list_pack_versions failed", exc_info=True)
                versions = []
            if versions:
                statutory_value = f"{len(versions)} pack(s)"

        self._kpi_tiles["open_run"].update_data(
            KpiTileData(label=tr("Open run"), value=open_value)
        )
        self._kpi_tiles["last_posted"].update_data(
            KpiTileData(label=tr("Last posted"), value=last_posted_value)
        )
        self._kpi_tiles["active_employees"].update_data(
            KpiTileData(label=tr("Active employees"), value=active_value)
        )
        self._kpi_tiles["statutory_due"].update_data(
            KpiTileData(label=tr("Statutory due"), value=statutory_value)
        )
