from __future__ import annotations

import datetime
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_remittance_dto import (
    CreatePayrollRemittanceBatchCommand,
)
from seeker_accounting.shared.ui.message_boxes import show_configuration_error, show_error

_AUTHORITIES = [
    ("dgi", "DGI — Tax Authority"),
    ("cnps", "CNPS — Social Insurance"),
    ("other", "Other"),
]


class PayrollRemittanceBatchDialog(QDialog):
    """Create a new payroll remittance batch."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        payroll_run_id: int | None = None,
        period_start: datetime.date | None = None,
        period_end: datetime.date | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._payroll_run_id = payroll_run_id

        self.setWindowTitle("Create Remittance Batch")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        today = datetime.date.today()
        start = period_start or datetime.date(today.year, today.month, 1)
        import calendar
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = period_end or datetime.date(today.year, today.month, last_day)

        self._period_start = QDateEdit()
        self._period_start.setCalendarPopup(True)
        self._period_start.setDisplayFormat("yyyy-MM-dd")
        self._period_start.setDate(QDate(start.year, start.month, start.day))
        form.addRow("Period Start:", self._period_start)

        self._period_end = QDateEdit()
        self._period_end.setCalendarPopup(True)
        self._period_end.setDisplayFormat("yyyy-MM-dd")
        self._period_end.setDate(QDate(end.year, end.month, end.day))
        form.addRow("Period End:", self._period_end)

        self._authority = QComboBox()
        for code, label in _AUTHORITIES:
            self._authority.addItem(label, code)
        form.addRow("Authority:", self._authority)

        self._amount_due = QDoubleSpinBox()
        self._amount_due.setRange(0, 999_999_999.99)
        self._amount_due.setDecimals(2)
        form.addRow("Amount Due:", self._amount_due)

        self._notes = QTextEdit()
        self._notes.setMaximumHeight(54)
        self._notes.setPlaceholderText("Optional notes")
        form.addRow("Notes:", self._notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_remittance_batch", dialog=True)

    def _on_accept(self) -> None:
        try:
            self._registry.payroll_remittance_service.create_batch(
                self._company_id,
                CreatePayrollRemittanceBatchCommand(
                    period_start_date=self._period_start.date().toPython(),
                    period_end_date=self._period_end.date().toPython(),
                    remittance_authority_code=self._authority.currentData(),
                    payroll_run_id=self._payroll_run_id,
                    amount_due=Decimal(str(self._amount_due.value())),
                    notes=self._notes.toPlainText().strip() or None,
                ),
            )
            self.accept()
        except Exception as exc:
            error_msg = str(exc)
            if "document sequence" in error_msg.lower():
                from seeker_accounting.app.navigation import nav_ids
                if show_configuration_error(
                    self,
                    "Remittance Batch",
                    f"{error_msg}\n\nConfigure it in Accounting Setup \u2192 Document Sequences.",
                    "Open Document Sequences",
                ):
                    self._registry.navigation_service.navigate(nav_ids.DOCUMENT_SEQUENCES)
                    self.reject()
            else:
                show_error(self, "Remittance Batch", error_msg)
