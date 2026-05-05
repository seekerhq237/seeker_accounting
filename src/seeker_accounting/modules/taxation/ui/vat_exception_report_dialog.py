"""VAT Exception Report dialog (T41).

Surfaces the VATExceptionReportService output in a 3-tab dialog.
The user selects a date range and presses Run to retrieve:

  Tab 1 — Draft Documents: unposted invoices/bills dated in period.
  Tab 2 — Foreign Currency: posted documents in non-local currency.
  Tab 3 — Missing Tax Code: posted lines with amount but no tax code.

Architecture: all business logic lives in VATExceptionReportService.
This dialog is a pure UI surface.
"""

from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
import logging
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDateEdit,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.dialogs import BaseDialog

_log = logging.getLogger(__name__)

_BUCKET_TYPES = ("DRAFT_DOCUMENT", "FOREIGN_CURRENCY", "MISSING_TAX_CODE")
_BUCKET_LABELS = (
    "Draft Documents",
    "Foreign Currency",
    "Missing Tax Code",
)


class VATExceptionReportDialog(BaseDialog):
    """Show VAT exceptions grouped into three buckets."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "VAT Exception Report",
            parent,
            help_key="dialog.vat_exception_report",
        )
        self._service_registry = service_registry
        self._company_id = company_id

        self.setObjectName("VATExceptionReportDialog")
        apply_window_size(self, "modules.taxation.ui.vat.exception.report.dialog.0")

        self._build_controls()
        self._build_tabs()
        self._build_status()

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject)

    # ── Controls ─────────────────────────────────────────────────────

    def _build_controls(self) -> None:
        bar = QFrame(self)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 4)
        bar_layout.setSpacing(8)

        bar_layout.addWidget(QLabel("From:", bar))
        today = date.today()
        self._from_date = QDateEdit(bar)
        self._from_date.setCalendarPopup(True)
        self._from_date.setDate(today.replace(day=1))
        bar_layout.addWidget(self._from_date)

        bar_layout.addWidget(QLabel("To:", bar))
        self._to_date = QDateEdit(bar)
        self._to_date.setCalendarPopup(True)
        self._to_date.setDate(today)
        bar_layout.addWidget(self._to_date)

        run_btn = QPushButton("Run", bar)
        run_btn.setProperty("variant", "primary")
        run_btn.clicked.connect(self._run)
        bar_layout.addWidget(run_btn)

        bar_layout.addStretch(1)

        self.body_layout.addWidget(bar)

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget(self)
        self._models: dict[str, QStandardItemModel] = {}
        self._tables: dict[str, DataTable] = {}

        headers = [
            "Document type",
            "Document ID",
            "Number",
            "Date",
            "Total amount",
            "Detail",
        ]
        for bucket_type, bucket_label in zip(_BUCKET_TYPES, _BUCKET_LABELS):
            model = QStandardItemModel(0, len(headers), self)
            model.setHorizontalHeaderLabels(headers)
            table = DataTable(
                columns=tuple(
                    DataTableColumn(key=str(i), title=h) for i, h in enumerate(headers)
                ),
                show_search=False,
                parent=self,
            )
            table.set_model(model)
            self._models[bucket_type] = model
            self._tables[bucket_type] = table

            tab_widget = QWidget(self)
            tab_layout = QVBoxLayout(tab_widget)
            tab_layout.setContentsMargins(4, 4, 4, 4)
            tab_layout.addWidget(table)
            self._tabs.addTab(tab_widget, bucket_label)

        self.body_layout.addWidget(self._tabs, 1)

    def _build_status(self) -> None:
        self._status_label = QLabel(
            "Select a date range and press Run to check for exceptions.", self
        )
        self._status_label.setObjectName("DialogStatusLabel")
        self.body_layout.addWidget(self._status_label)

    # ── Run ──────────────────────────────────────────────────────────

    def _run(self) -> None:
        period_start = self._from_date.date().toPython()
        period_end = self._to_date.date().toPython()

        if period_start > period_end:
            self._status_label.setText("'From' date must not be after 'To' date.")
            return

        try:
            items = self._service_registry.vat_exception_report_service.list_exceptions(
                company_id=self._company_id,
                period_start=period_start,
                period_end=period_end,
            )
        except Exception as exc:
            _log.exception("VAT exception report")
            self._status_label.setText(f"Error: {exc}")
            return

        # Clear all bucket models.
        for model in self._models.values():
            model.removeRows(0, model.rowCount())

        counts: dict[str, int] = {t: 0 for t in _BUCKET_TYPES}
        for item in items:
            bucket = item.exception_type
            model = self._models.get(bucket)
            if model is None:
                continue
            model.appendRow([
                self._make_item(item.document_type),
                self._make_item(str(item.document_id)),
                self._make_item(item.document_number or "—"),
                self._make_item(str(item.document_date) if item.document_date else "—"),
                self._make_right_item(item.total_amount),
                self._make_item(item.detail or ""),
            ])
            counts[bucket] = counts.get(bucket, 0) + 1

        # Update tab labels with counts.
        for i, (bucket_type, label) in enumerate(zip(_BUCKET_TYPES, _BUCKET_LABELS)):
            n = counts.get(bucket_type, 0)
            self._tabs.setTabText(i, f"{label} ({n})")

        total = sum(counts.values())
        if total == 0:
            self._status_label.setText("No exceptions found for the selected period.")
        else:
            self._status_label.setText(
                f"{total} exception{'s' if total != 1 else ''} found across "
                f"{sum(1 for c in counts.values() if c > 0)} bucket(s). "
                "Review each tab and resolve before filing."
            )

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _make_item(text: str) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        return item

    def _make_right_item(self, value: object) -> QStandardItem:
        from decimal import Decimal
        try:
            formatted = f"{Decimal(str(value)):,.2f}"
        except Exception:
            formatted = str(value)
        item = QStandardItem(formatted)
        item.setEditable(False)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return item
