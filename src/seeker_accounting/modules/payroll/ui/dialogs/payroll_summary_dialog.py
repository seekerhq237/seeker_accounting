from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.message_boxes import show_error

_MONTHS = [
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December"),
]


def _fmt(v) -> str:
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return "—"


class PayrollSummaryDialog(QDialog):
    """Display a payroll period summary including exposures."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        period_year: int,
        period_month: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id

        self.setWindowTitle("Payroll Period Summary")
        self.setMinimumSize(560, 520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(12)

        # Period selector
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Year:"))
        self._year = QSpinBox()
        self._year.setRange(2000, 2100)
        self._year.setValue(period_year)
        sel_row.addWidget(self._year)
        sel_row.addWidget(QLabel("Month:"))
        self._month = QComboBox()
        for num, name in _MONTHS:
            self._month.addItem(name, num)
        self._month.setCurrentIndex(period_month - 1)
        sel_row.addWidget(self._month)

        from PySide6.QtWidgets import QPushButton
        refresh_btn = QPushButton("Load")
        refresh_btn.clicked.connect(self._load)
        sel_row.addWidget(refresh_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        self._content_frame = QFrame()
        self._content_layout = QVBoxLayout(self._content_frame)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        layout.addWidget(self._content_frame)
        layout.addStretch()

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_summary", dialog=True)

        self._load()

    def _load(self) -> None:
        # Clear content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        year = self._year.value()
        month = self._month.currentData()
        try:
            summary = self._registry.payroll_summary_service.get_period_summary(
                self._company_id, year, month
            )
        except Exception as exc:
            self._content_layout.addWidget(QLabel(f"Error: {exc}"))
            return

        # Run summary
        run = summary.run_summary
        if run is None:
            self._content_layout.addWidget(
                QLabel(f"No payroll run found for {_MONTHS[month - 1][1]} {year}.")
            )
        else:
            run_frame = QFrame()
            run_frame.setFrameShape(QFrame.Shape.StyledPanel)
            rf = QVBoxLayout(run_frame)
            rf.setContentsMargins(12, 10, 12, 10)
            rf.setSpacing(4)
            rf.addWidget(
                self._bold(f"{run.run_reference}  ·  {run.run_label}  [{run.status_code.upper()}]")
            )
            rf.addWidget(self._row("Gross Earnings", _fmt(run.total_gross_earnings)))
            rf.addWidget(self._row("Total Net Payable", _fmt(run.total_net_payable)))
            rf.addWidget(self._row("Total Taxes", _fmt(run.total_taxes)))
            rf.addWidget(self._row("Employer Cost", _fmt(run.total_employer_cost)))
            rf.addWidget(self._row("Employees (included / error)", f"{run.included_count} / {run.error_count}"))
            if run.is_posted:
                rf.addWidget(self._row("Journal Entry", str(run.journal_entry_id)))
            self._content_layout.addWidget(run_frame)

        # Net pay exposure
        exp = summary.net_pay_exposure
        pay_frame = QFrame()
        pay_frame.setFrameShape(QFrame.Shape.StyledPanel)
        pf = QVBoxLayout(pay_frame)
        pf.setContentsMargins(12, 10, 12, 10)
        pf.setSpacing(4)
        pf.addWidget(self._bold("Employee Net Pay Exposure"))
        pf.addWidget(self._row("Total Net Payable", _fmt(exp.total_net_payable)))
        pf.addWidget(self._row("Total Paid", _fmt(exp.total_paid)))
        pf.addWidget(self._row("Outstanding", _fmt(exp.outstanding)))
        pf.addWidget(self._row(
            "Status (paid / partial / unpaid)",
            f"{exp.paid_count} / {exp.partial_count} / {exp.unpaid_count}"
        ))
        self._content_layout.addWidget(pay_frame)

        # Statutory exposure
        if summary.statutory_exposures:
            stat_frame = QFrame()
            stat_frame.setFrameShape(QFrame.Shape.StyledPanel)
            sf = QVBoxLayout(stat_frame)
            sf.setContentsMargins(12, 10, 12, 10)
            sf.setSpacing(4)
            sf.addWidget(self._bold("Statutory Remittance Exposure"))
            for stat in summary.statutory_exposures:
                sf.addWidget(
                    self._row(
                        stat.authority_label,
                        f"Due {_fmt(stat.total_due)}  |  Paid {_fmt(stat.total_remitted)}"
                        f"  |  Outstanding {_fmt(stat.outstanding)}"
                    )
                )
            self._content_layout.addWidget(stat_frame)

    @staticmethod
    def _bold(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        return lbl

    @staticmethod
    def _row(label: str, value: str) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label + ":")
        lbl.setStyleSheet("font-size: 11px; color: #555;")
        val = QLabel(value)
        val.setStyleSheet("font-size: 11px;")
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(val)
        return w
