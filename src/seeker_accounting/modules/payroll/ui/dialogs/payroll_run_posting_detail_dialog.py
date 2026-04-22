from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_STATUS_COLORS = {
    "posted": "#1a7a2e",
    "approved": "#2471a3",
    "calculated": "#7d6608",
    "draft": "#555",
    "voided": "#c0392b",
}


class PayrollRunPostingDetailDialog(QDialog):
    """Show the posting summary for a posted payroll run."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        run_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._run_id = run_id

        self.setWindowTitle("Payroll Run — Posting Detail")
        self.setMinimumSize(660, 500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(12)

        try:
            run_dto = self._registry.payroll_run_service.get_run(company_id, run_id)
        except Exception as exc:
            layout.addWidget(QLabel(f"Error loading run: {exc}"))
            layout.addWidget(QDialogButtonBox(QDialogButtonBox.StandardButton.Close))
            return

        # Header
        header = QFrame()
        header.setFrameShape(QFrame.Shape.StyledPanel)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(4)

        title = QLabel(f"{run_dto.run_reference}  ·  {run_dto.run_label}")
        title.setStyleSheet("font-weight: 700; font-size: 14px;")
        h_layout.addWidget(title)

        status_color = _STATUS_COLORS.get(run_dto.status_code, "#555")
        meta = QLabel(
            f"Status: <b style='color:{status_color}'>{run_dto.status_code.upper()}</b>  "
            f"|  Period: {run_dto.period_month:02d}/{run_dto.period_year}  "
            f"|  Posted: {run_dto.posted_at.strftime('%Y-%m-%d %H:%M') if run_dto.posted_at else '—'}"
        )
        meta.setTextFormat(Qt.TextFormat.RichText)
        meta.setStyleSheet("font-size: 11px;")
        h_layout.addWidget(meta)

        if run_dto.posted_journal_entry_id:
            je_label = QLabel(f"Journal Entry ID: {run_dto.posted_journal_entry_id}")
            je_label.setStyleSheet("font-size: 11px; color: #555;")
            h_layout.addWidget(je_label)

        layout.addWidget(header)

        # Journal lines table (if we have posting result)
        # Show a summary message since we don't cache the full line DTO here.
        # The user can navigate to Journals for full line detail.
        info = QLabel(
            "Posting creates one balanced journal entry linked to this run.\n"
            "Navigate to Journals to view the full journal entry and GL lines."
        )
        info.setStyleSheet("font-size: 11px; color: #555;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_run_posting_detail", dialog=True)
