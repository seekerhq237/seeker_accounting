from __future__ import annotations

import datetime

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.print_preview_dto import PrintPreviewMetaDTO
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.dto.template_preview_dto import TemplatePreviewDTO


class ReportingFilterBar(QFrame):
    """
    Shared filter bar for the reports workspace.

    Provides date-range selection, posted-only toggle, and triggers
    for refresh, print-preview, and template-preview actions.
    """

    refresh_requested = Signal(object)           # ReportingFilterDTO
    print_preview_requested = Signal(object)     # PrintPreviewMetaDTO
    template_preview_requested = Signal(object)  # TemplatePreviewDTO
    export_requested = Signal()                  # financial statement export

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ReportFilterBar")

        self._company_id: int | None = None
        self._company_name: str = ""

        today = datetime.date.today()
        first_of_month = today.replace(day=1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(10)

        # ── date range ──────────────────────────────────────────────────
        from_lbl = QLabel("From", self)
        from_lbl.setProperty("role", "caption")
        layout.addWidget(from_lbl)

        self._date_from = QDateEdit(self)
        self._date_from.setDate(
            QDate(first_of_month.year, first_of_month.month, first_of_month.day)
        )
        self._date_from.setCalendarPopup(True)
        self._date_from.setFixedWidth(116)
        layout.addWidget(self._date_from)

        to_lbl = QLabel("To", self)
        to_lbl.setProperty("role", "caption")
        layout.addWidget(to_lbl)

        self._date_to = QDateEdit(self)
        self._date_to.setDate(QDate(today.year, today.month, today.day))
        self._date_to.setCalendarPopup(True)
        self._date_to.setFixedWidth(116)
        layout.addWidget(self._date_to)

        # ── posted only ─────────────────────────────────────────────────
        self._posted_only = QCheckBox("Posted Only", self)
        self._posted_only.setChecked(True)
        layout.addWidget(self._posted_only)

        layout.addStretch(1)

        # ── action buttons ───────────────────────────────────────────────
        self._refresh_btn = QPushButton("Refresh", self)
        self._refresh_btn.setProperty("variant", "primary")
        self._refresh_btn.setFixedWidth(88)
        self._refresh_btn.clicked.connect(self._on_refresh)
        layout.addWidget(self._refresh_btn)

        self._print_btn = QPushButton("Print Preview", self)
        self._print_btn.setProperty("variant", "secondary")
        self._print_btn.setFixedWidth(112)
        self._print_btn.clicked.connect(self._on_print_preview)
        layout.addWidget(self._print_btn)

        self._export_btn = QPushButton("Export", self)
        self._export_btn.setProperty("variant", "secondary")
        self._export_btn.setFixedWidth(88)
        self._export_btn.clicked.connect(self._on_export)
        self._export_btn.setVisible(False)
        layout.addWidget(self._export_btn)

        self._template_btn = QPushButton("Template View", self)
        self._template_btn.setProperty("variant", "secondary")
        self._template_btn.setFixedWidth(116)
        self._template_btn.clicked.connect(self._on_template_preview)
        layout.addWidget(self._template_btn)

    # ── public API ─────────────────────────────────────────────────────────

    def show_export_button(self) -> None:
        """Reveal the Export button (hidden by default)."""
        self._export_btn.setVisible(True)

    def set_company_context(self, company_id: int | None, company_name: str = "") -> None:
        self._company_id = company_id
        self._company_name = company_name

    def set_filter(self, filter_dto: ReportingFilterDTO) -> None:
        if filter_dto.company_id is not None:
            self._company_id = filter_dto.company_id

        if filter_dto.date_from is not None:
            self._date_from.setDate(
                QDate(
                    filter_dto.date_from.year,
                    filter_dto.date_from.month,
                    filter_dto.date_from.day,
                )
            )
        if filter_dto.date_to is not None:
            self._date_to.setDate(
                QDate(
                    filter_dto.date_to.year,
                    filter_dto.date_to.month,
                    filter_dto.date_to.day,
                )
            )
        self._posted_only.setChecked(filter_dto.posted_only)

    def get_filter(self) -> ReportingFilterDTO:
        qd_from = self._date_from.date()
        qd_to = self._date_to.date()
        return ReportingFilterDTO(
            company_id=self._company_id,
            date_from=datetime.date(qd_from.year(), qd_from.month(), qd_from.day()),
            date_to=datetime.date(qd_to.year(), qd_to.month(), qd_to.day()),
            posted_only=self._posted_only.isChecked(),
        )

    # ── signal handlers ────────────────────────────────────────────────────

    def _on_refresh(self) -> None:
        self.refresh_requested.emit(self.get_filter())

    def _on_print_preview(self) -> None:
        f = self.get_filter()
        period_label = "-"
        if f.date_from and f.date_to:
            period_label = (
                f"{f.date_from.strftime('%d %b %Y')} - {f.date_to.strftime('%d %b %Y')}"
            )
        meta = PrintPreviewMetaDTO(
            report_title="Report",
            company_name=self._company_name,
            period_label=period_label,
            generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=f"Posted Only: {f.posted_only}",
        )
        self.print_preview_requested.emit(meta)

    def _on_export(self) -> None:
        self.export_requested.emit()

    def _on_template_preview(self) -> None:
        meta = TemplatePreviewDTO(
            template_code="default",
            template_title="Report Template",
            description="Template preview framework - engine available in a future slice.",
            standard_note="Framework Ready",
        )
        self.template_preview_requested.emit(meta)
