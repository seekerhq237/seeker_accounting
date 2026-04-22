"""PurchaseBillDetailPage — full document workspace for a single purchase bill.

Navigated to via:
    navigation_service.navigate(nav_ids.PURCHASE_BILL_DETAIL, context={"bill_id": <int>})

Shows: header KPIs, line items tab, and document details tab.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import (
    PurchaseBillDetailDTO,
    PurchaseBillLineDTO,
)
from seeker_accounting.modules.purchases.dto.supplier_payment_dto import BillPaymentRowDTO
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.shared.ui.entity_detail.entity_detail_page import EntityDetailPage
from seeker_accounting.shared.ui.entity_detail.money_bar import MoneyBarItem
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_dense_table

_log = logging.getLogger(__name__)

_CURRENCY_FMT = "{:,.2f}"
_STATUS_LABELS = {
    "draft": "Draft",
    "DRAFT": "Draft",
    "posted": "Posted",
    "POSTED": "Posted",
    "cancelled": "Cancelled",
    "CANCELLED": "Cancelled",
    "void": "Void",
    "VOID": "Void",
}
_PAYMENT_STATUS_LABELS = {
    "unpaid": "Unpaid",
    "UNPAID": "Unpaid",
    "partially_paid": "Partially Paid",
    "PARTIALLY_PAID": "Partially Paid",
    "paid": "Paid",
    "PAID": "Paid",
    "overpaid": "Overpaid",
    "OVERPAID": "Overpaid",
}


def _fmt(value: Decimal | None, currency: str = "") -> str:
    if value is None:
        return "—"
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{_CURRENCY_FMT.format(value)}"


class PurchaseBillDetailPage(EntityDetailPage):
    """Full detail workspace for a single purchase bill."""

    _back_nav_id = nav_ids.PURCHASE_BILLS
    _back_label = "Back to Purchase Bills"

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(service_registry, parent)
        self.setObjectName("PurchaseBillDetailPage")

        self._bill_id: int | None = None
        self._bill: PurchaseBillDetailDTO | None = None
        self._payments_data: list[BillPaymentRowDTO] = []

        # Action buttons
        self._edit_button = QPushButton("Edit Bill", self)
        self._edit_button.setObjectName("SecondaryButton")
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.clicked.connect(self._open_edit_dialog)
        self._action_row_layout.addWidget(self._edit_button)

        self._post_button = QPushButton("Post Bill", self)
        self._post_button.setObjectName("PrimaryButton")
        self._post_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._post_button.clicked.connect(self._go_to_bills_for_posting)
        self._action_row_layout.addWidget(self._post_button)

        # Build tabs
        self._lines_tab = self._build_lines_tab()
        self._payments_tab = self._build_payments_tab()
        self._details_tab = self._build_details_tab()
        self._initialize_tabs()

        self._set_actions_enabled(False)

    # ── Tab construction ──────────────────────────────────────────────

    def _build_tabs(self) -> list[tuple[str, QWidget]]:
        return [
            ("Lines", self._lines_tab),
            ("Payments", self._payments_tab),
            ("Details", self._details_tab),
        ]

    def _build_lines_tab(self) -> QWidget:
        container = QFrame()
        container.setObjectName("EntityInfoTab")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._lines_table = QTableWidget(container)
        self._lines_table.setObjectName("DashboardActivityTable")
        self._lines_table.setColumnCount(7)
        self._lines_table.setHorizontalHeaderLabels(
            ("Description", "Account", "Qty", "Unit Cost", "Tax", "Subtotal", "Total")
        )
        configure_dense_table(self._lines_table)

        hdr = self._lines_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        self._lines_empty = QLabel("No line items.", container)
        self._lines_empty.setObjectName("DashboardEmptyLabel")
        self._lines_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lines_empty.setMinimumHeight(60)
        self._lines_empty.setVisible(False)

        # Totals footer
        totals_row = QWidget(container)
        totals_layout = QHBoxLayout(totals_row)
        totals_layout.setContentsMargins(0, 4, 0, 0)
        totals_layout.setSpacing(24)
        totals_layout.addStretch(1)

        def _total_cell(label_text: str, attr: str) -> None:
            cell = QWidget(totals_row)
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)
            lbl = QLabel(label_text, cell)
            lbl.setObjectName("EntityInfoLabel")
            cell_layout.addWidget(lbl)
            val = QLabel("—", cell)
            val.setObjectName("EntityInfoValue")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            cell_layout.addWidget(val)
            totals_layout.addWidget(cell)
            setattr(self, attr, val)

        _total_cell("Subtotal", "_totals_subtotal")
        _total_cell("Tax", "_totals_tax")
        _total_cell("Total", "_totals_total")

        sep = QFrame(container)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("EntityInfoSeparator")

        layout.addWidget(self._lines_table, 1)
        layout.addWidget(self._lines_empty)
        layout.addWidget(sep)
        layout.addWidget(totals_row)
        return container

    def _build_details_tab(self) -> QWidget:
        container = QFrame()
        container.setObjectName("EntityInfoTab")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        def _row(label_text: str, attr_name: str) -> None:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)
            lbl = QLabel(label_text, row_widget)
            lbl.setObjectName("EntityInfoLabel")
            lbl.setFixedWidth(180)
            row_layout.addWidget(lbl)
            val = QLabel("—", row_widget)
            val.setObjectName("EntityInfoValue")
            val.setWordWrap(True)
            row_layout.addWidget(val, 1)
            layout.addWidget(row_widget)
            setattr(self, attr_name, val)

        _row("Bill Number", "_det_number")
        _row("Supplier", "_det_supplier")
        _row("Bill Date", "_det_date")
        _row("Due Date", "_det_due_date")
        _row("Currency", "_det_currency")
        _row("Status", "_det_status")
        _row("Payment Status", "_det_payment_status")
        _row("Supplier Reference", "_det_supplier_ref")
        _row("Notes", "_det_notes")
        _row("Posted At", "_det_posted_at")
        _row("Journal Entry", "_det_journal_entry")
        _row("Created", "_det_created")
        layout.addStretch(1)
        return container

    def _build_payments_tab(self) -> QWidget:
        container = QFrame()
        container.setObjectName("EntityInfoTab")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._payments_table = QTableWidget(container)
        self._payments_table.setObjectName("DashboardActivityTable")
        self._payments_table.setColumnCount(6)
        self._payments_table.setHorizontalHeaderLabels(
            ("Payment #", "Date", "Account", "Amount Paid", "Applied Here", "Status")
        )
        configure_dense_table(self._payments_table)

        hdr = self._payments_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self._payments_empty = QLabel("No payments allocated to this bill.", container)
        self._payments_empty.setObjectName("DashboardEmptyLabel")
        self._payments_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._payments_empty.setMinimumHeight(60)
        self._payments_empty.setVisible(False)

        self._payments_table.itemDoubleClicked.connect(self._on_payment_double_clicked)

        layout.addWidget(self._payments_table, 1)
        layout.addWidget(self._payments_empty)
        return container

    # ── Navigation context ────────────────────────────────────────────

    def set_navigation_context(self, context: dict) -> None:
        bill_id = context.get("bill_id")
        if not isinstance(bill_id, int):
            return
        self._bill_id = bill_id
        self._load_data()

    # ── Data loading ──────────────────────────────────────────────────

    def _load_data(self) -> None:
        if self._bill_id is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        try:
            self._bill = self._service_registry.purchase_bill_service.get_purchase_bill(
                active_company.company_id, self._bill_id
            )
        except NotFoundError:
            show_error(self, "Bill Detail", "Purchase bill not found.")
            self._navigate_back()
            return
        except Exception as exc:
            show_error(self, "Bill Detail", f"Failed to load purchase bill: {exc}")
            return

        try:
            self._payments_data = self._service_registry.supplier_payment_service.list_payments_for_bill(
                active_company.company_id, self._bill_id
            )
        except Exception:
            self._payments_data = []

        self._populate_header()
        self._populate_money_bar()
        self._populate_lines_tab()
        self._populate_payments_tab()
        self._populate_details_tab()
        self._set_actions_enabled(True)

    # ── Population ────────────────────────────────────────────────────

    def _populate_header(self) -> None:
        bill = self._bill
        if bill is None:
            return
        status_label = _STATUS_LABELS.get(bill.status_code, bill.status_code.title())
        payment_label = _PAYMENT_STATUS_LABELS.get(bill.payment_status_code, bill.payment_status_code.replace("_", " ").title())
        is_active = bill.status_code.upper() == "POSTED"
        subtitle = (
            f"{bill.supplier_code}  ·  {bill.supplier_name}  ·  "
            f"{bill.bill_date.strftime('%d %b %Y')}  ·  Due {bill.due_date.strftime('%d %b %Y')}"
        )
        self._set_header(
            title=f"Bill {bill.bill_number}",
            subtitle=subtitle,
            status_label=f"{status_label}  ·  {payment_label}",
            is_active=is_active,
        )

    def _populate_money_bar(self) -> None:
        bill = self._bill
        if bill is None:
            return
        t = bill.totals
        currency = bill.currency_code
        is_paid = bill.payment_status_code.upper() == "PAID"
        open_tone = "neutral" if is_paid else ("warning" if t.open_balance_amount > 0 else "neutral")
        self._set_money_bar([
            MoneyBarItem(label="Subtotal", value=_fmt(t.subtotal_amount, currency), tone="neutral"),
            MoneyBarItem(label="Tax", value=_fmt(t.tax_amount, currency), tone="neutral"),
            MoneyBarItem(label="Total", value=_fmt(t.total_amount, currency), tone="info"),
            MoneyBarItem(label="Allocated", value=_fmt(t.allocated_amount, currency), tone="success" if t.allocated_amount > 0 else "neutral"),
            MoneyBarItem(label="Open Balance", value=_fmt(t.open_balance_amount, currency), tone=open_tone),
        ])

    def _populate_lines_tab(self) -> None:
        bill = self._bill
        if bill is None:
            return

        table = self._lines_table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        if not bill.lines:
            table.setVisible(False)
            self._lines_empty.setVisible(True)
        else:
            table.setVisible(True)
            self._lines_empty.setVisible(False)
            for row_idx, line in enumerate(bill.lines):
                self._add_lines_table_row(table, row_idx, line)
            table.setSortingEnabled(True)

        t = bill.totals
        currency = bill.currency_code
        self._totals_subtotal.setText(_fmt(t.subtotal_amount, currency))
        self._totals_tax.setText(_fmt(t.tax_amount, currency))
        self._totals_total.setText(_fmt(t.total_amount, currency))

    def _add_lines_table_row(self, table: QTableWidget, row_idx: int, line: PurchaseBillLineDTO) -> None:
        table.insertRow(row_idx)

        table.setItem(row_idx, 0, QTableWidgetItem(line.description or "—"))

        acct_text = f"{line.expense_account_code}  {line.expense_account_name}"
        table.setItem(row_idx, 1, QTableWidgetItem(acct_text))

        if line.quantity is not None:
            qty_str = _CURRENCY_FMT.format(line.quantity).rstrip("0").rstrip(".")
        else:
            qty_str = "—"
        qty_cell = QTableWidgetItem(qty_str)
        qty_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_idx, 2, qty_cell)

        cost_str = _CURRENCY_FMT.format(line.unit_cost) if line.unit_cost is not None else "—"
        cost_cell = QTableWidgetItem(cost_str)
        cost_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_idx, 3, cost_cell)

        tax_text = line.tax_code_code or "—"
        table.setItem(row_idx, 4, QTableWidgetItem(tax_text))

        subtotal_cell = QTableWidgetItem(_CURRENCY_FMT.format(line.line_subtotal_amount))
        subtotal_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_idx, 5, subtotal_cell)

        total_cell = QTableWidgetItem(_CURRENCY_FMT.format(line.line_total_amount))
        total_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_idx, 6, total_cell)

    def _populate_details_tab(self) -> None:
        bill = self._bill
        if bill is None:
            return

        def _or_dash(val: str | None) -> str:
            return val or "—"

        self._det_number.setText(_or_dash(bill.bill_number))
        self._det_supplier.setText(f"{bill.supplier_code}  {bill.supplier_name}")
        self._det_date.setText(bill.bill_date.strftime("%d %b %Y"))
        self._det_due_date.setText(bill.due_date.strftime("%d %b %Y"))
        self._det_currency.setText(_or_dash(bill.currency_code))
        self._det_status.setText(_STATUS_LABELS.get(bill.status_code, bill.status_code.title()))
        self._det_payment_status.setText(_PAYMENT_STATUS_LABELS.get(bill.payment_status_code, bill.payment_status_code.replace("_", " ").title()))
        self._det_supplier_ref.setText(_or_dash(bill.supplier_bill_reference))
        self._det_notes.setText(_or_dash(bill.notes))
        self._det_posted_at.setText(bill.posted_at.strftime("%d %b %Y %H:%M") if bill.posted_at else "—")
        self._det_journal_entry.setText(str(bill.posted_journal_entry_id) if bill.posted_journal_entry_id else "—")
        self._det_created.setText(bill.created_at.strftime("%d %b %Y %H:%M"))

    def _populate_payments_tab(self) -> None:
        rows = self._payments_data
        table = self._payments_table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        if not rows:
            table.setVisible(False)
            self._payments_empty.setVisible(True)
            return

        table.setVisible(True)
        self._payments_empty.setVisible(False)

        currency = self._bill.currency_code if self._bill else ""

        for row_idx, row in enumerate(rows):
            table.insertRow(row_idx)

            num_item = QTableWidgetItem(row.payment_number)
            num_item.setData(Qt.ItemDataRole.UserRole, row.payment_id)
            table.setItem(row_idx, 0, num_item)

            table.setItem(row_idx, 1, QTableWidgetItem(row.payment_date.strftime("%d %b %Y")))

            acct_text = f"{row.financial_account_code}  {row.financial_account_name}".strip() or "—"
            table.setItem(row_idx, 2, QTableWidgetItem(acct_text))

            paid_cell = QTableWidgetItem(_fmt(row.amount_paid, row.currency_code))
            paid_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 3, paid_cell)

            applied_cell = QTableWidgetItem(_fmt(row.allocated_to_bill, currency))
            applied_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 4, applied_cell)

            status_text = _STATUS_LABELS.get(row.status_code, row.status_code.title())
            table.setItem(row_idx, 5, QTableWidgetItem(status_text))

        table.setSortingEnabled(True)

    def _on_payment_double_clicked(self, item: QTableWidgetItem) -> None:
        row = self._payments_table.row(item)
        id_item = self._payments_table.item(row, 0)
        if id_item is None:
            return
        payment_id = id_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payment_id, int):
            self._service_registry.navigation_service.navigate(
                nav_ids.SUPPLIER_PAYMENTS,
                context={"select_payment_id": payment_id},
            )

    # ── Actions ───────────────────────────────────────────────────────

    def _set_actions_enabled(self, enabled: bool) -> None:
        bill = self._bill
        is_draft = bill is not None and bill.status_code.upper() == "DRAFT"
        is_posted = bill is not None and bill.status_code.upper() == "POSTED"
        self._edit_button.setEnabled(enabled and is_draft)
        self._post_button.setEnabled(enabled and not is_posted)
        self._post_button.setVisible(enabled and not is_posted)

    def _open_edit_dialog(self) -> None:
        if self._bill is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return
        from seeker_accounting.modules.purchases.ui.purchase_bill_dialog import PurchaseBillDialog
        updated = PurchaseBillDialog.edit_bill(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            bill_id=self._bill.id,
            parent=self,
        )
        if updated is not None:
            self._load_data()

    def _go_to_bills_for_posting(self) -> None:
        if self._bill is None:
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.PURCHASE_BILLS,
            context={"select_bill_id": self._bill.id},
        )
