"""PayrollAccountingWorkspace — four-tab payroll accounting workspace.

Tabs:
  1. Posting          — post approved/calculated runs to the GL
  2. Employee Payments — record and track employee net-pay settlements
  3. Remittances       — statutory remittance batch management (DGI, CNPS)
  4. Summary           — period-level payroll exposure snapshot
"""

from __future__ import annotations

import logging

import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.ui.dialogs.payroll_payment_record_dialog import (
    PayrollPaymentRecordDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_post_run_dialog import (
    PayrollPostRunDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_remittance_batch_dialog import (
    PayrollRemittanceBatchDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_remittance_line_dialog import (
    PayrollRemittanceLineDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_run_posting_detail_dialog import (
    PayrollRunPostingDetailDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_summary_dialog import (
    PayrollSummaryDialog,
)
from seeker_accounting.modules.payroll.services.payroll_remittance_deadline_service import (
    compute_filing_deadline,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_STATUS_COLORS = {
    "posted": "#1a7a2e",
    "approved": "#2471a3",
    "calculated": "#7d6608",
    "draft": "#555",
    "voided": "#c0392b",
}

_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

_AUTHORITY_LABELS = {
    "dgi": "DGI",
    "cnps": "CNPS",
    "other": "Other",
}

_PAY_STATUS_LABELS = {
    "paid": "Paid",
    "partial": "Partial",
    "unpaid": "Unpaid",
}

_REMIT_STATUS_LABELS = {
    "draft": "Draft",
    "open": "Open",
    "partial": "Partial",
    "paid": "Paid",
    "cancelled": "Cancelled",
}


def _fmt(v) -> str:
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return "—"


class PayrollAccountingWorkspace(QWidget):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        stack: QStackedWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._stack = stack
        self._company_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Topbar ────────────────────────────────────────────────────────────
        topbar = QHBoxLayout()
        topbar.setContentsMargins(16, 8, 16, 8)
        topbar.setSpacing(10)

        title = QLabel("Payroll Accounting")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        topbar.addWidget(title)
        topbar.addStretch()

        self._company_label = QLabel("No company selected")
        self._company_label.setStyleSheet("color: #666; font-size: 11px;")
        topbar.addWidget(self._company_label)
        root.addLayout(topbar)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        self._posting_tab = _PostingTab(service_registry, self)
        self._payments_tab = _EmployeePaymentsTab(service_registry, self)
        self._remittances_tab = _RemittancesTab(service_registry, self)
        self._summary_tab = _SummaryTab(service_registry, self)

        self._tabs.addTab(self._posting_tab, "Posting")
        self._tabs.addTab(self._payments_tab, "Employee Payments")
        self._tabs.addTab(self._remittances_tab, "Remittances")
        self._tabs.addTab(self._summary_tab, "Summary")

        self._tabs.currentChanged.connect(self._on_tab_changed)

        ctx = self._registry.active_company_context
        if ctx.company_id:
            self._set_company(ctx.company_id, ctx.company_name or "")

    def _set_company(self, company_id: int, company_name: str) -> None:
        self._company_id = company_id
        self._company_label.setText(company_name)
        self._posting_tab.set_company(company_id)
        self._payments_tab.set_company(company_id)
        self._remittances_tab.set_company(company_id)
        self._summary_tab.set_company(company_id)

    def _on_tab_changed(self, index: int) -> None:
        if self._company_id is None:
            return
        tab = self._tabs.widget(index)
        if hasattr(tab, "refresh"):
            tab.refresh()


# ── Tab: Posting ───────────────────────────────────────────────────────────────

class _PostingTab(QWidget):
    """List payroll runs; allow posting approved/calculated runs to the GL."""

    def __init__(self, registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._btn_post = QPushButton("Post to GL…")
        self._btn_post.setFixedHeight(26)
        self._btn_post.clicked.connect(self._on_post)

        self._btn_detail = QPushButton("Posting Detail…")
        self._btn_detail.setFixedHeight(26)
        self._btn_detail.clicked.connect(self._on_detail)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedHeight(26)
        self._btn_refresh.clicked.connect(self.refresh)

        for btn in (self._btn_post, self._btn_detail, self._btn_refresh):
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableWidget()
        configure_compact_table(self._table)
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "Reference", "Label", "Period", "Status",
            "Gross", "Net Payable", "Employees", "Journal Entry",
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_detail)
        layout.addWidget(self._table)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        if self._company_id is None:
            return
        try:
            runs = self._registry.payroll_run_service.list_runs(self._company_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._table.setRowCount(0)
        for r in runs:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(r.run_reference))
            self._table.setItem(row, 1, QTableWidgetItem(r.run_label))
            self._table.setItem(row, 2, QTableWidgetItem(
                f"{_MONTHS.get(r.period_month, str(r.period_month))} {r.period_year}"
            ))
            status_lbl = QTableWidgetItem(r.status_code.upper())
            color = _STATUS_COLORS.get(r.status_code, "#555")
            status_lbl.setForeground(Qt.GlobalColor.black)
            status_lbl.setData(Qt.ItemDataRole.ForegroundRole, None)
            self._table.setItem(row, 3, status_lbl)
            gross = QTableWidgetItem(_fmt(r.total_gross_earnings))
            gross.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, gross)
            net = QTableWidgetItem(_fmt(r.total_net_payable))
            net.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 5, net)
            emp = QTableWidgetItem(str(r.employee_count))
            emp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 6, emp)
            je = QTableWidgetItem(
                str(r.posted_journal_entry_id) if r.posted_journal_entry_id else "—"
            )
            self._table.setItem(row, 7, je)
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, r)

        self._table.resizeColumnsToContents()

    def _selected_run(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_post(self) -> None:
        run = self._selected_run()
        if run is None:
            return
        if run.status_code not in ("approved", "calculated"):
            show_error(self, "Payroll Accounting", "Only approved or calculated runs can be posted to the GL.")
            return
        dlg = PayrollPostRunDialog(
            self._registry, self._company_id, run.id, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            show_info(self, "Payroll run posted to the GL.")
            self.refresh()

    def _on_detail(self) -> None:
        run = self._selected_run()
        if run is None:
            return
        if run.status_code != "posted":
            show_error(self, "Payroll Accounting", "Select a posted run to view posting detail.")
            return
        dlg = PayrollRunPostingDetailDialog(
            self._registry, self._company_id, run.id, self
        )
        dlg.exec()


# ── Tab: Employee Payments ─────────────────────────────────────────────────────

class _EmployeePaymentsTab(QWidget):
    """Track net-pay settlement per employee per run."""

    def __init__(self, registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id: int | None = None
        self._selected_run_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Run filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(QLabel("Run:"))
        self._run_combo = QComboBox()
        self._run_combo.setMinimumWidth(280)
        self._run_combo.currentIndexChanged.connect(self._on_run_changed)
        filter_row.addWidget(self._run_combo)
        filter_row.addStretch()

        self._btn_record = QPushButton("Record Payment…")
        self._btn_record.setFixedHeight(26)
        self._btn_record.clicked.connect(self._on_record_payment)
        filter_row.addWidget(self._btn_record)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedHeight(26)
        self._btn_refresh.clicked.connect(self.refresh)
        filter_row.addWidget(self._btn_refresh)
        layout.addLayout(filter_row)

        # Payments table
        self._table = QTableWidget()
        configure_compact_table(self._table)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Employee", "Net Payable", "Total Paid", "Outstanding", "Status", "Payment Date", "Records",
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self._load_run_combo()

    def _load_run_combo(self) -> None:
        self._run_combo.blockSignals(True)
        self._run_combo.clear()
        self._run_combo.addItem("— Select Run —", None)
        if self._company_id is None:
            self._run_combo.blockSignals(False)
            return
        try:
            runs = self._registry.payroll_run_service.list_runs(self._company_id)
        except Exception:
            self._run_combo.blockSignals(False)
            return
        for r in runs:
            month_label = _MONTHS.get(r.period_month, str(r.period_month))
            label = f"{r.run_reference}  ·  {month_label} {r.period_year}  [{r.status_code.upper()}]"
            self._run_combo.addItem(label, r.id)
        self._run_combo.blockSignals(False)

    def _on_run_changed(self) -> None:
        self._selected_run_id = self._run_combo.currentData()
        self.refresh()

    def refresh(self) -> None:
        self._table.setRowCount(0)
        if self._company_id is None or self._selected_run_id is None:
            return
        try:
            summaries = self._registry.payroll_payment_tracking_service.list_run_payment_summaries(
                self._company_id, self._selected_run_id
            )
        except Exception as exc:
            show_error(self, "Payroll Accounting", str(exc))
            return

        for s in summaries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(s.employee_display_name))
            for col, val in ((1, s.net_payable), (2, s.total_paid), (3, s.outstanding)):
                item = QTableWidgetItem(_fmt(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row, col, item)
            self._table.setItem(
                row, 4, QTableWidgetItem(_PAY_STATUS_LABELS.get(s.payment_status_code, s.payment_status_code))
            )
            self._table.setItem(row, 5, QTableWidgetItem(str(s.payment_date) if s.payment_date else "—"))
            rec_count = QTableWidgetItem(str(len(s.records)))
            rec_count.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 6, rec_count)
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, s)

        self._table.resizeColumnsToContents()

    def _selected_summary(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_record_payment(self) -> None:
        s = self._selected_summary()
        if s is None:
            show_error(self, "Payroll Accounting", "Select an employee row to record a payment.")
            return
        if s.payment_status_code == "paid":
            if QMessageBox.question(
                self, "Already Paid",
                "This employee is already fully paid. Record an additional payment?"
            ) != QMessageBox.StandardButton.Yes:
                return
        dlg = PayrollPaymentRecordDialog(
            self._registry, self._company_id, s.run_employee_id, s.net_payable, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()


# ── Tab: Remittances ───────────────────────────────────────────────────────────

class _RemittancesTab(QWidget):
    """Manage statutory remittance batches and lines."""

    def __init__(self, registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Batch toolbar
        batch_toolbar = QHBoxLayout()
        batch_toolbar.setSpacing(6)

        self._btn_new_batch = QPushButton("New Batch…")
        self._btn_new_batch.setFixedHeight(26)
        self._btn_new_batch.clicked.connect(self._on_new_batch)

        self._btn_open_batch = QPushButton("Open Batch")
        self._btn_open_batch.setFixedHeight(26)
        self._btn_open_batch.clicked.connect(self._on_open_batch)

        self._btn_cancel_batch = QPushButton("Cancel")
        self._btn_cancel_batch.setFixedHeight(26)
        self._btn_cancel_batch.clicked.connect(self._on_cancel_batch)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedHeight(26)
        self._btn_refresh.clicked.connect(self.refresh)

        for btn in (self._btn_new_batch, self._btn_open_batch, self._btn_cancel_batch, self._btn_refresh):
            batch_toolbar.addWidget(btn)
        batch_toolbar.addStretch()
        layout.addLayout(batch_toolbar)

        # Batch table
        self._batch_table = QTableWidget()
        configure_compact_table(self._batch_table)
        self._batch_table.setColumnCount(9)
        self._batch_table.setHorizontalHeaderLabels([
            "Batch #", "Authority", "Period", "Amount Due", "Amount Paid", "Outstanding", "Status",
            "Deadline", "Days Left",
        ])
        self._batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._batch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._batch_table.selectionModel().selectionChanged.connect(self._on_batch_selected)
        layout.addWidget(self._batch_table, 2)

        # Lines sub-section
        lines_header = QHBoxLayout()
        lines_lbl = QLabel("Lines (selected batch)")
        lines_lbl.setStyleSheet("font-size: 11px; font-weight: 600; margin-top: 6px;")
        lines_header.addWidget(lines_lbl)
        lines_header.addStretch()

        self._btn_add_line = QPushButton("Add Line…")
        self._btn_add_line.setFixedHeight(24)
        self._btn_add_line.clicked.connect(self._on_add_line)
        lines_header.addWidget(self._btn_add_line)
        layout.addLayout(lines_header)

        self._lines_table = QTableWidget()
        configure_compact_table(self._lines_table)
        self._lines_table.setColumnCount(5)
        self._lines_table.setHorizontalHeaderLabels([
            "#", "Description", "Amount Due", "Amount Paid", "Status",
        ])
        self._lines_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._lines_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._lines_table, 1)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        if self._company_id is None:
            return
        self._lines_table.setRowCount(0)
        try:
            batches = self._registry.payroll_remittance_service.list_batches(self._company_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._batch_table.setRowCount(0)
        today = datetime.date.today()
        for b in batches:
            row = self._batch_table.rowCount()
            self._batch_table.insertRow(row)
            self._batch_table.setItem(row, 0, QTableWidgetItem(b.batch_number))
            self._batch_table.setItem(
                row, 1, QTableWidgetItem(_AUTHORITY_LABELS.get(b.remittance_authority_code, b.remittance_authority_code))
            )
            self._batch_table.setItem(
                row, 2, QTableWidgetItem(f"{b.period_start_date}  →  {b.period_end_date}")
            )
            for col, val in ((3, b.amount_due), (4, b.amount_paid), (5, b.outstanding)):
                item = QTableWidgetItem(_fmt(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._batch_table.setItem(row, col, item)
            self._batch_table.setItem(
                row, 6, QTableWidgetItem(_REMIT_STATUS_LABELS.get(b.status_code, b.status_code))
            )

            # Deadline columns
            deadline = compute_filing_deadline(b.remittance_authority_code, b.period_end_date)
            if deadline and b.status_code not in ("cancelled", "paid"):
                deadline_item = QTableWidgetItem(deadline.isoformat())
                days_left = (deadline - today).days
                days_item = QTableWidgetItem(str(days_left))
                days_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if days_left < 0:
                    deadline_item.setForeground(Qt.GlobalColor.red)
                    days_item.setForeground(Qt.GlobalColor.red)
                elif days_left <= 7:
                    deadline_item.setForeground(Qt.GlobalColor.darkYellow)
                    days_item.setForeground(Qt.GlobalColor.darkYellow)
                self._batch_table.setItem(row, 7, deadline_item)
                self._batch_table.setItem(row, 8, days_item)
            else:
                self._batch_table.setItem(row, 7, QTableWidgetItem("—"))
                self._batch_table.setItem(row, 8, QTableWidgetItem("—"))

            self._batch_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, b)

        self._batch_table.resizeColumnsToContents()

    def _selected_batch(self):
        row = self._batch_table.currentRow()
        if row < 0:
            return None
        item = self._batch_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_batch_selected(self) -> None:
        batch = self._selected_batch()
        self._lines_table.setRowCount(0)
        if batch is None:
            return
        try:
            detail = self._registry.payroll_remittance_service.get_batch(
                self._company_id, batch.id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        for line in detail.lines:
            row = self._lines_table.rowCount()
            self._lines_table.insertRow(row)
            num = QTableWidgetItem(str(line.line_number))
            num.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._lines_table.setItem(row, 0, num)
            self._lines_table.setItem(row, 1, QTableWidgetItem(line.description))
            for col, val in ((2, line.amount_due), (3, line.amount_paid)):
                item = QTableWidgetItem(_fmt(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._lines_table.setItem(row, col, item)
            self._lines_table.setItem(
                row, 4, QTableWidgetItem(_REMIT_STATUS_LABELS.get(line.status_code, line.status_code))
            )
            self._lines_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, line)

        self._lines_table.resizeColumnsToContents()

    def _on_new_batch(self) -> None:
        if self._company_id is None:
            return
        dlg = PayrollRemittanceBatchDialog(self._registry, self._company_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_open_batch(self) -> None:
        batch = self._selected_batch()
        if batch is None:
            return
        if batch.status_code != "draft":
            show_error(self, "Payroll Accounting", "Only draft batches can be opened.")
            return
        try:
            self._registry.payroll_remittance_service.open_batch(self._company_id, batch.id)
            self.refresh()
        except Exception as exc:
            show_error(self, "Payroll Accounting", str(exc))

    def _on_cancel_batch(self) -> None:
        batch = self._selected_batch()
        if batch is None:
            return
        if QMessageBox.question(
            self, "Cancel Batch",
            f"Cancel remittance batch {batch.batch_number}? This cannot be undone."
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_remittance_service.cancel_batch(self._company_id, batch.id)
            self.refresh()
        except Exception as exc:
            show_error(self, "Payroll Accounting", str(exc))

    def _on_add_line(self) -> None:
        batch = self._selected_batch()
        if batch is None:
            show_error(self, "Payroll Accounting", "Select a batch to add a line.")
            return
        if batch.status_code not in ("draft", "open"):
            show_error(self, "Payroll Accounting", "Lines can only be added to draft or open batches.")
            return
        dlg = PayrollRemittanceLineDialog(
            self._registry, self._company_id, batch.id, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._on_batch_selected()


# ── Tab: Summary ───────────────────────────────────────────────────────────────

class _SummaryTab(QWidget):
    """Period-level payroll exposure snapshot."""

    def __init__(self, registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Period selector
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        sel_row.addWidget(QLabel("Year:"))
        self._year = QSpinBox()
        self._year.setRange(2000, 2100)
        today = datetime.date.today()
        self._year.setValue(today.year)
        sel_row.addWidget(self._year)

        sel_row.addWidget(QLabel("Month:"))
        self._month = QComboBox()
        _MONTH_NAMES = [
            (1, "January"), (2, "February"), (3, "March"), (4, "April"),
            (5, "May"), (6, "June"), (7, "July"), (8, "August"),
            (9, "September"), (10, "October"), (11, "November"), (12, "December"),
        ]
        for num, name in _MONTH_NAMES:
            self._month.addItem(name, num)
        self._month.setCurrentIndex(today.month - 1)
        sel_row.addWidget(self._month)

        btn_open_dlg = QPushButton("Open Full Summary…")
        btn_open_dlg.setFixedHeight(26)
        btn_open_dlg.clicked.connect(self._on_open_summary_dialog)
        sel_row.addWidget(btn_open_dlg)

        btn_load = QPushButton("Load")
        btn_load.setFixedHeight(26)
        btn_load.clicked.connect(self.refresh)
        sel_row.addWidget(btn_load)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Summary table — single flat view
        self._table = QTableWidget()
        configure_compact_table(self._table)
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Metric", "Value"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)
        layout.addStretch()

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        self._table.setRowCount(0)
        if self._company_id is None:
            return

        year = self._year.value()
        month = self._month.currentData()

        try:
            summary = self._registry.payroll_summary_service.get_period_summary(
                self._company_id, year, month
            )
        except Exception as exc:
            self._add_row("Error", str(exc))
            return

        run = summary.run_summary
        if run is None:
            month_name = self._month.currentText()
            self._add_row("Run", f"No payroll run found for {month_name} {year}")
        else:
            self._add_section(f"Run  ·  {run.run_reference}  [{run.status_code.upper()}]")
            self._add_row("Gross Earnings", _fmt(run.total_gross_earnings))
            self._add_row("Total Net Payable", _fmt(run.total_net_payable))
            self._add_row("Total Taxes", _fmt(run.total_taxes))
            self._add_row("Employer Cost", _fmt(run.total_employer_cost))
            self._add_row("Employees (included / error)", f"{run.included_count} / {run.error_count}")
            if run.is_posted:
                self._add_row("Journal Entry ID", str(run.journal_entry_id))

        exp = summary.net_pay_exposure
        self._add_section("Net Pay Exposure")
        self._add_row("Total Net Payable", _fmt(exp.total_net_payable))
        self._add_row("Total Paid", _fmt(exp.total_paid))
        self._add_row("Outstanding", _fmt(exp.outstanding))
        self._add_row("Status (paid / partial / unpaid)", f"{exp.paid_count} / {exp.partial_count} / {exp.unpaid_count}")

        if summary.statutory_exposures:
            self._add_section("Statutory Remittance Exposure")
            for stat in summary.statutory_exposures:
                self._add_row(
                    stat.authority_label,
                    f"Due {_fmt(stat.total_due)}  |  Paid {_fmt(stat.total_remitted)}  |  Outstanding {_fmt(stat.outstanding)}"
                )

        self._table.resizeColumnsToContents()

    def _add_section(self, label: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        item = QTableWidgetItem(label)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setBackground(Qt.GlobalColor.lightGray)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self._table.setItem(row, 0, item)
        blank = QTableWidgetItem("")
        blank.setBackground(Qt.GlobalColor.lightGray)
        blank.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._table.setItem(row, 1, blank)

    def _add_row(self, label: str, value: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        lbl_item = QTableWidgetItem(label)
        lbl_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._table.setItem(row, 0, lbl_item)
        val_item = QTableWidgetItem(value)
        val_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        val_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, 1, val_item)

    def _on_open_summary_dialog(self) -> None:
        if self._company_id is None:
            return
        dlg = PayrollSummaryDialog(
            self._registry, self._company_id,
            self._year.value(), self._month.currentData(), self
        )
        dlg.exec()
