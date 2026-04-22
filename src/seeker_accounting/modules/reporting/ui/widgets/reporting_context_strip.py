from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.reporting_context_dto import ReportingContextDTO
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)


class ReportingContextStrip(QFrame):
    """
    Compact horizontal strip displaying active company, fiscal period,
    currency, and report basis. Refreshes automatically on company change.
    """

    def __init__(
        self,
        context_service: ReportingContextService,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._context_service = context_service
        self._active_company_context = service_registry.active_company_context

        self.setObjectName("ReportContextStrip")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(0)

        self._company_value = self._add_panel(layout, "Company", "—")
        self._add_vsep(layout)
        self._fiscal_value = self._add_panel(layout, "Fiscal Period", "—")
        self._add_vsep(layout)
        self._currency_value = self._add_panel(layout, "Currency", "—")
        self._add_vsep(layout)
        self._basis_value = self._add_panel(layout, "Basis", "Posted Only")

        layout.addStretch(1)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._refresh()

    # ── panel helpers ──────────────────────────────────────────────────────

    def _add_panel(self, layout: QHBoxLayout, caption: str, value: str) -> QLabel:
        container = QWidget(self)
        hl = QHBoxLayout(container)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(7)

        caption_lbl = QLabel(caption, container)
        caption_lbl.setProperty("role", "caption")
        hl.addWidget(caption_lbl)

        value_lbl = QLabel(value, container)
        value_lbl.setObjectName("TopBarValue")
        hl.addWidget(value_lbl)

        layout.addWidget(container)
        return value_lbl

    def _add_vsep(self, layout: QHBoxLayout) -> None:
        sep = QFrame(self)
        sep.setFixedWidth(1)
        sep.setFixedHeight(16)
        sep.setStyleSheet("background: palette(mid);")
        layout.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)

    # ── signal handlers ────────────────────────────────────────────────────

    def _on_company_changed(self, company_id: object, company_name: object) -> None:
        self._refresh()

    def _refresh(self) -> None:
        company_id = self._active_company_context.company_id
        ctx = self._context_service.get_context(company_id)
        self._apply_context(ctx)

    def _apply_context(self, ctx: ReportingContextDTO) -> None:
        self._company_value.setText(ctx.company_name)

        if ctx.fiscal_period_code:
            period_text = ctx.fiscal_period_code
            if ctx.fiscal_period_status:
                period_text = f"{period_text}  ·  {ctx.fiscal_period_status.title()}"
        else:
            period_text = "No period"
        self._fiscal_value.setText(period_text)

        self._currency_value.setText(ctx.base_currency_code or "—")
        self._basis_value.setText(ctx.report_basis)
