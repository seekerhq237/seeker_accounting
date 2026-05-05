"""Inventory Reports Page — tabbed viewer for all 6 inventory reports."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.message_boxes import show_error


def _hdr_label(text: str, parent: QWidget) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet("font-weight: 600; font-size: 12px; margin-bottom: 4px;")
    return lbl


def _date_from_qdate(qd: QDate) -> date:
    return date(qd.year(), qd.month(), qd.day())


class InventoryReportsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self.setObjectName("InventoryReportsPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        lbl = QLabel("Inventory Reports", self)
        lbl.setObjectName("PageTitle")
        lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(lbl)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_kardex_tab(), "Kardex")
        self._tabs.addTab(self._build_ageing_tab(), "Ageing")
        self._tabs.addTab(self._build_abc_tab(), "ABC Analysis")
        self._tabs.addTab(self._build_profitability_tab(), "Profitability")
        self._tabs.addTab(self._build_grni_tab(), "GRNI Accrual")
        self._tabs.addTab(self._build_reconciliation_tab(), "GL Reconciliation")
        root.addWidget(self._tabs, 1)

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_kardex_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        # Simple: show text prompt (full widget would need item selector)
        lay.addWidget(_hdr_label("Stock Kardex (Item Ledger Card)", w))
        lay.addWidget(QLabel("Select an item from the Items page → View Kardex to see the full card.", w))
        # Provide date range + run button for a basic version
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:", w))
        self._kardex_from = QDateEdit(w)
        self._kardex_from.setDate(QDate.currentDate().addMonths(-1))
        self._kardex_from.setCalendarPopup(True)
        filter_row.addWidget(self._kardex_from)
        filter_row.addWidget(QLabel("To:", w))
        self._kardex_to = QDateEdit(w)
        self._kardex_to.setDate(QDate.currentDate())
        self._kardex_to.setCalendarPopup(True)
        filter_row.addWidget(self._kardex_to)
        filter_row.addStretch()
        lay.addLayout(filter_row)
        self._kardex_table = self._make_table(
            ["Date", "Doc Type", "Dir", "Qty", "Unit Cost", "Value", "Run Qty", "Run Value"], w
        )
        lay.addWidget(self._kardex_table, 1)
        return w

    def _build_ageing_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_hdr_label("Inventory Ageing Analysis", w))
        run_btn = QPushButton("Run Report", w)
        run_btn.setFixedHeight(28)
        run_btn.clicked.connect(self._run_ageing)
        lay.addWidget(run_btn)
        cols = ["Item Code", "Item Name", "On Hand Qty", "Value", "0-30d", "31-60d", "61-90d", "91-180d", "180+d"]
        self._ageing_table = self._make_table(cols, w)
        lay.addWidget(self._ageing_table, 1)
        return w

    def _build_abc_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_hdr_label("ABC Analysis (COGS Pareto)", w))
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:", w))
        self._abc_from = QDateEdit(w)
        self._abc_from.setDate(QDate.currentDate().addMonths(-12))
        self._abc_from.setCalendarPopup(True)
        filter_row.addWidget(self._abc_from)
        filter_row.addWidget(QLabel("To:", w))
        self._abc_to = QDateEdit(w)
        self._abc_to.setDate(QDate.currentDate())
        self._abc_to.setCalendarPopup(True)
        filter_row.addWidget(self._abc_to)
        run_btn = QPushButton("Run", w)
        run_btn.setFixedHeight(26)
        run_btn.clicked.connect(self._run_abc)
        filter_row.addWidget(run_btn)
        filter_row.addStretch()
        lay.addLayout(filter_row)
        self._abc_table = self._make_table(
            ["Class", "Item Code", "Item Name", "COGS", "% Total", "Cumulative %"], w
        )
        lay.addWidget(self._abc_table, 1)
        return w

    def _build_profitability_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_hdr_label("Item Profitability (Gross Margin)", w))
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:", w))
        self._prof_from = QDateEdit(w)
        self._prof_from.setDate(QDate.currentDate().addMonths(-3))
        self._prof_from.setCalendarPopup(True)
        filter_row.addWidget(self._prof_from)
        filter_row.addWidget(QLabel("To:", w))
        self._prof_to = QDateEdit(w)
        self._prof_to.setDate(QDate.currentDate())
        self._prof_to.setCalendarPopup(True)
        filter_row.addWidget(self._prof_to)
        run_btn = QPushButton("Run", w)
        run_btn.setFixedHeight(26)
        run_btn.clicked.connect(self._run_profitability)
        filter_row.addWidget(run_btn)
        filter_row.addStretch()
        lay.addLayout(filter_row)
        self._prof_table = self._make_table(
            ["Item Code", "Item Name", "Revenue", "COGS", "Gross Margin", "Margin %"], w
        )
        lay.addWidget(self._prof_table, 1)
        return w

    def _build_grni_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_hdr_label("GRNI Accrual (Uninvoiced Receipts)", w))
        run_btn = QPushButton("Run Report", w)
        run_btn.setFixedHeight(28)
        run_btn.clicked.connect(self._run_grni)
        lay.addWidget(run_btn)
        self._grni_table = self._make_table(
            ["Doc #", "Date", "Supplier", "Item", "Qty", "Unit Cost", "Amount", "Days Outstanding"], w
        )
        lay.addWidget(self._grni_table, 1)
        return w

    def _build_reconciliation_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_hdr_label("Inventory GL Reconciliation", w))
        run_btn = QPushButton("Run Report", w)
        run_btn.setFixedHeight(28)
        run_btn.clicked.connect(self._run_reconciliation)
        lay.addWidget(run_btn)
        self._recon_table = self._make_table(
            ["Account", "Account Name", "GL Balance", "Stock Ledger Value", "Difference", "Reconciled?"], w
        )
        lay.addWidget(self._recon_table, 1)
        return w

    # ------------------------------------------------------------------
    # Report runners
    # ------------------------------------------------------------------

    def _active_company_id(self) -> int | None:
        active = self._service_registry.active_company_context.get_active_company()
        return active.company_id if active else None

    def _run_ageing(self) -> None:
        cid = self._active_company_id()
        if cid is None:
            return
        svc = self._service_registry.inventory_aging_report_service
        try:
            report = svc.get_report(cid)
        except Exception as exc:
            show_error(self, "Ageing Report", str(exc))
            return
        tbl = self._ageing_table
        tbl.setRowCount(len(report.rows))
        for r, row in enumerate(report.rows):
            tbl.setItem(r, 0, QTableWidgetItem(row.item_code))
            tbl.setItem(r, 1, QTableWidgetItem(row.item_name))
            self._set_numeric(tbl, r, 2, row.on_hand_qty)
            self._set_numeric(tbl, r, 3, row.on_hand_value)
            for i, v in enumerate(row.bucket_values, 4):
                self._set_numeric(tbl, r, i, v)

    def _run_abc(self) -> None:
        cid = self._active_company_id()
        if cid is None:
            return
        svc = self._service_registry.inventory_abc_analysis_service
        try:
            report = svc.get_report(
                cid,
                _date_from_qdate(self._abc_from.date()),
                _date_from_qdate(self._abc_to.date()),
            )
        except Exception as exc:
            show_error(self, "ABC Analysis", str(exc))
            return
        tbl = self._abc_table
        tbl.setRowCount(len(report.rows))
        for r, row in enumerate(report.rows):
            tbl.setItem(r, 0, QTableWidgetItem(row.abc_class))
            tbl.setItem(r, 1, QTableWidgetItem(row.item_code))
            tbl.setItem(r, 2, QTableWidgetItem(row.item_name))
            self._set_numeric(tbl, r, 3, row.total_cogs)
            self._set_numeric(tbl, r, 4, row.pct_of_total)
            self._set_numeric(tbl, r, 5, row.cumulative_pct)

    def _run_profitability(self) -> None:
        cid = self._active_company_id()
        if cid is None:
            return
        from seeker_accounting.modules.reporting.services.inventory_item_profitability_service import (
            ItemProfitabilityFilterDTO,
        )
        svc = self._service_registry.inventory_item_profitability_service
        try:
            report = svc.get_report(
                ItemProfitabilityFilterDTO(
                    company_id=cid,
                    date_from=_date_from_qdate(self._prof_from.date()),
                    date_to=_date_from_qdate(self._prof_to.date()),
                )
            )
        except Exception as exc:
            show_error(self, "Profitability", str(exc))
            return
        tbl = self._prof_table
        tbl.setRowCount(len(report.rows))
        for r, row in enumerate(report.rows):
            tbl.setItem(r, 0, QTableWidgetItem(row.item_code))
            tbl.setItem(r, 1, QTableWidgetItem(row.item_name))
            self._set_numeric(tbl, r, 2, row.total_revenue)
            self._set_numeric(tbl, r, 3, row.total_cogs)
            self._set_numeric(tbl, r, 4, row.gross_margin)
            self._set_numeric(tbl, r, 5, row.gross_margin_pct)

    def _run_grni(self) -> None:
        cid = self._active_company_id()
        if cid is None:
            return
        svc = self._service_registry.grni_accrual_report_service
        try:
            report = svc.get_report(cid)
        except Exception as exc:
            show_error(self, "GRNI Report", str(exc))
            return
        tbl = self._grni_table
        tbl.setRowCount(len(report.rows))
        for r, row in enumerate(report.rows):
            tbl.setItem(r, 0, QTableWidgetItem(row.document_number or ""))
            tbl.setItem(r, 1, QTableWidgetItem(str(row.receipt_date)))
            tbl.setItem(r, 2, QTableWidgetItem(row.supplier_name or ""))
            tbl.setItem(r, 3, QTableWidgetItem(row.item_name or ""))
            self._set_numeric(tbl, r, 4, row.received_qty)
            self._set_numeric(tbl, r, 5, row.unit_cost)
            self._set_numeric(tbl, r, 6, row.line_amount)
            tbl.setItem(r, 7, QTableWidgetItem(str(row.days_outstanding)))

    def _run_reconciliation(self) -> None:
        cid = self._active_company_id()
        if cid is None:
            return
        svc = self._service_registry.inventory_reconciliation_report_service
        try:
            report = svc.get_report(cid)
        except Exception as exc:
            show_error(self, "Reconciliation", str(exc))
            return
        tbl = self._recon_table
        tbl.setRowCount(len(report.rows))
        for r, row in enumerate(report.rows):
            tbl.setItem(r, 0, QTableWidgetItem(row.account_code or ""))
            tbl.setItem(r, 1, QTableWidgetItem(row.account_name or ""))
            self._set_numeric(tbl, r, 2, row.gl_balance)
            self._set_numeric(tbl, r, 3, row.stock_ledger_value)
            self._set_numeric(tbl, r, 4, row.difference)
            tbl.setItem(r, 5, QTableWidgetItem("✓" if row.is_reconciled else "✗"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_table(self, cols: list[str], parent: QWidget) -> QTableWidget:
        tbl = QTableWidget(0, len(cols), parent)
        tbl.setHorizontalHeaderLabels(cols)
        tbl.horizontalHeader().setSectionResizeMode(
            1 if len(cols) > 1 else 0,
            tbl.horizontalHeader().ResizeMode.Stretch
        )
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        return tbl

    def _set_numeric(self, tbl: QTableWidget, row: int, col: int, value) -> None:
        item = QTableWidgetItem(f"{value:,.4f}" if value is not None else "")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tbl.setItem(row, col, item)
