"""SalesInvoiceDetailPage — full document workspace for a single sales invoice.

Navigated to via:
    navigation_service.navigate(nav_ids.SALES_INVOICE_DETAIL, context={"invoice_id": <int>})

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
from seeker_accounting.modules.sales.dto.sales_invoice_dto import (
    SalesInvoiceDetailDTO,
    SalesInvoiceLineDTO,
)
from seeker_accounting.modules.sales.dto.customer_receipt_dto import InvoiceReceiptRowDTO
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
    "issued": "Issued",
    "ISSUED": "Issued",
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


class SalesInvoiceDetailPage(EntityDetailPage):
    """Full detail workspace for a single sales invoice."""

    _back_nav_id = nav_ids.SALES_INVOICES
    _back_label = "Back to Invoices"

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(service_registry, parent)
        self.setObjectName("SalesInvoiceDetailPage")

        self._invoice_id: int | None = None
        self._invoice: SalesInvoiceDetailDTO | None = None
        self._receipts_data: list[InvoiceReceiptRowDTO] = []

        # Action buttons
        self._edit_button = QPushButton("Edit Invoice", self)
        self._edit_button.setObjectName("SecondaryButton")
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.clicked.connect(self._open_edit_dialog)
        self._action_row_layout.addWidget(self._edit_button)

        self._post_button = QPushButton("Post Invoice", self)
        self._post_button.setObjectName("PrimaryButton")
        self._post_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._post_button.clicked.connect(self._open_post_dialog)
        self._action_row_layout.addWidget(self._post_button)

        # Build tabs
        self._lines_tab = self._build_lines_tab()
        self._receipts_tab = self._build_receipts_tab()
        self._details_tab = self._build_details_tab()
        self._initialize_tabs()

        self._set_actions_enabled(False)

    # ── Tab construction ──────────────────────────────────────────────

    def _build_tabs(self) -> list[tuple[str, QWidget]]:
        return [
            ("Lines", self._lines_tab),
            ("Receipts", self._receipts_tab),
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
            ("Description", "Account", "Qty", "Unit Price", "Tax", "Subtotal", "Total")
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

        _row("Invoice Number", "_det_number")
        _row("Customer", "_det_customer")
        _row("Invoice Date", "_det_date")
        _row("Due Date", "_det_due_date")
        _row("Currency", "_det_currency")
        _row("Status", "_det_status")
        _row("Payment Status", "_det_payment_status")
        _row("Reference", "_det_reference")
        _row("Notes", "_det_notes")
        _row("Posted At", "_det_posted_at")
        _row("Journal Entry", "_det_journal_entry")
        _row("Created", "_det_created")
        layout.addStretch(1)
        return container

    def _build_receipts_tab(self) -> QWidget:
        container = QFrame()
        container.setObjectName("EntityInfoTab")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._receipts_table = QTableWidget(container)
        self._receipts_table.setObjectName("DashboardActivityTable")
        self._receipts_table.setColumnCount(6)
        self._receipts_table.setHorizontalHeaderLabels(
            ("Receipt #", "Date", "Account", "Amount Received", "Applied Here", "Status")
        )
        configure_dense_table(self._receipts_table)

        hdr = self._receipts_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self._receipts_empty = QLabel("No receipts allocated to this invoice.", container)
        self._receipts_empty.setObjectName("DashboardEmptyLabel")
        self._receipts_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._receipts_empty.setMinimumHeight(60)
        self._receipts_empty.setVisible(False)

        self._receipts_table.itemDoubleClicked.connect(self._on_receipt_double_clicked)

        layout.addWidget(self._receipts_table, 1)
        layout.addWidget(self._receipts_empty)
        return container

    # ── Navigation context ────────────────────────────────────────────

    def set_navigation_context(self, context: dict) -> None:
        invoice_id = context.get("invoice_id")
        if not isinstance(invoice_id, int):
            return
        self._invoice_id = invoice_id
        self._load_data()

    # ── Data loading ──────────────────────────────────────────────────

    def _load_data(self) -> None:
        if self._invoice_id is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        try:
            self._invoice = self._service_registry.sales_invoice_service.get_sales_invoice(
                active_company.company_id, self._invoice_id
            )
        except NotFoundError:
            show_error(self, "Invoice Detail", "Invoice not found.")
            self._navigate_back()
            return
        except Exception as exc:
            show_error(self, "Invoice Detail", f"Failed to load invoice: {exc}")
            return

        try:
            self._receipts_data = self._service_registry.customer_receipt_service.list_receipts_for_invoice(
                active_company.company_id, self._invoice_id
            )
        except Exception:
            self._receipts_data = []

        self._populate_header()
        self._populate_money_bar()
        self._populate_lines_tab()
        self._populate_receipts_tab()
        self._populate_details_tab()
        self._set_actions_enabled(True)

    # ── Population ────────────────────────────────────────────────────

    def _populate_header(self) -> None:
        inv = self._invoice
        if inv is None:
            return
        status_label = _STATUS_LABELS.get(inv.status_code, inv.status_code.title())
        payment_label = _PAYMENT_STATUS_LABELS.get(inv.payment_status_code, inv.payment_status_code.replace("_", " ").title())
        is_active = inv.status_code.upper() == "POSTED"
        subtitle = (
            f"{inv.customer_code}  ·  {inv.customer_name}  ·  "
            f"{inv.invoice_date.strftime('%d %b %Y')}  ·  Due {inv.due_date.strftime('%d %b %Y')}"
        )
        self._set_header(
            title=f"Invoice {inv.invoice_number}",
            subtitle=subtitle,
            status_label=f"{status_label}  ·  {payment_label}",
            is_active=is_active,
        )

    def _populate_money_bar(self) -> None:
        inv = self._invoice
        if inv is None:
            return
        t = inv.totals
        currency = inv.currency_code
        is_paid = inv.payment_status_code.upper() == "PAID"
        open_tone = "neutral" if is_paid else ("warning" if t.open_balance_amount > 0 else "neutral")
        self._set_money_bar([
            MoneyBarItem(label="Subtotal", value=_fmt(t.subtotal_amount, currency), tone="neutral"),
            MoneyBarItem(label="Tax", value=_fmt(t.tax_amount, currency), tone="neutral"),
            MoneyBarItem(label="Total", value=_fmt(t.total_amount, currency), tone="info"),
            MoneyBarItem(label="Allocated", value=_fmt(t.allocated_amount, currency), tone="success" if t.allocated_amount > 0 else "neutral"),
            MoneyBarItem(label="Open Balance", value=_fmt(t.open_balance_amount, currency), tone=open_tone),
        ])

    def _populate_lines_tab(self) -> None:
        inv = self._invoice
        if inv is None:
            return

        table = self._lines_table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        if not inv.lines:
            table.setVisible(False)
            self._lines_empty.setVisible(True)
        else:
            table.setVisible(True)
            self._lines_empty.setVisible(False)
            for row_idx, line in enumerate(inv.lines):
                self._add_lines_table_row(table, row_idx, line)
            table.setSortingEnabled(True)

        currency = inv.currency_code
        t = inv.totals
        self._totals_subtotal.setText(_fmt(t.subtotal_amount, currency))
        self._totals_tax.setText(_fmt(t.tax_amount, currency))
        self._totals_total.setText(_fmt(t.total_amount, currency))

    def _add_lines_table_row(self, table: QTableWidget, row_idx: int, line: SalesInvoiceLineDTO) -> None:
        table.insertRow(row_idx)

        table.setItem(row_idx, 0, QTableWidgetItem(line.description or "—"))

        acct_text = f"{line.revenue_account_code}  {line.revenue_account_name}"
        table.setItem(row_idx, 1, QTableWidgetItem(acct_text))

        qty_cell = QTableWidgetItem(_CURRENCY_FMT.format(line.quantity).rstrip("0").rstrip("."))
        qty_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_idx, 2, qty_cell)

        price_cell = QTableWidgetItem(_CURRENCY_FMT.format(line.unit_price))
        price_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_idx, 3, price_cell)

        tax_text = line.tax_code_code or "—"
        table.setItem(row_idx, 4, QTableWidgetItem(tax_text))

        subtotal_cell = QTableWidgetItem(_CURRENCY_FMT.format(line.line_subtotal_amount))
        subtotal_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_idx, 5, subtotal_cell)

        total_cell = QTableWidgetItem(_CURRENCY_FMT.format(line.line_total_amount))
        total_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_idx, 6, total_cell)

    def _populate_details_tab(self) -> None:
        inv = self._invoice
        if inv is None:
            return

        def _or_dash(val: str | None) -> str:
            return val or "—"

        self._det_number.setText(_or_dash(inv.invoice_number))
        self._det_customer.setText(f"{inv.customer_code}  {inv.customer_name}")
        self._det_date.setText(inv.invoice_date.strftime("%d %b %Y"))
        self._det_due_date.setText(inv.due_date.strftime("%d %b %Y"))
        self._det_currency.setText(_or_dash(inv.currency_code))
        self._det_status.setText(_STATUS_LABELS.get(inv.status_code, inv.status_code.title()))
        self._det_payment_status.setText(_PAYMENT_STATUS_LABELS.get(inv.payment_status_code, inv.payment_status_code.replace("_", " ").title()))
        self._det_reference.setText(_or_dash(inv.reference_number))
        self._det_notes.setText(_or_dash(inv.notes))
        self._det_posted_at.setText(inv.posted_at.strftime("%d %b %Y %H:%M") if inv.posted_at else "—")
        self._det_journal_entry.setText(str(inv.posted_journal_entry_id) if inv.posted_journal_entry_id else "—")
        self._det_created.setText(inv.created_at.strftime("%d %b %Y %H:%M"))

    def _populate_receipts_tab(self) -> None:
        rows = self._receipts_data
        table = self._receipts_table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        if not rows:
            table.setVisible(False)
            self._receipts_empty.setVisible(True)
            return

        table.setVisible(True)
        self._receipts_empty.setVisible(False)

        currency = self._invoice.currency_code if self._invoice else ""
        status_labels = _STATUS_LABELS

        for row_idx, row in enumerate(rows):
            table.insertRow(row_idx)

            num_item = QTableWidgetItem(row.receipt_number)
            num_item.setData(Qt.ItemDataRole.UserRole, row.receipt_id)
            table.setItem(row_idx, 0, num_item)

            table.setItem(row_idx, 1, QTableWidgetItem(row.receipt_date.strftime("%d %b %Y")))

            acct_text = f"{row.financial_account_code}  {row.financial_account_name}".strip() or "—"
            table.setItem(row_idx, 2, QTableWidgetItem(acct_text))

            recv_cell = QTableWidgetItem(_fmt(row.amount_received, row.currency_code))
            recv_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 3, recv_cell)

            applied_cell = QTableWidgetItem(_fmt(row.allocated_to_invoice, currency))
            applied_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 4, applied_cell)

            status_text = status_labels.get(row.status_code, row.status_code.title())
            table.setItem(row_idx, 5, QTableWidgetItem(status_text))

        table.setSortingEnabled(True)

    def _on_receipt_double_clicked(self, item: QTableWidgetItem) -> None:
        row = self._receipts_table.row(item)
        id_item = self._receipts_table.item(row, 0)
        if id_item is None:
            return
        receipt_id = id_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(receipt_id, int):
            self._service_registry.navigation_service.navigate(
                nav_ids.CUSTOMER_RECEIPTS,
                context={"select_receipt_id": receipt_id},
            )

    # ── Actions ───────────────────────────────────────────────────────

    def _set_actions_enabled(self, enabled: bool) -> None:
        inv = self._invoice
        is_draft = inv is not None and inv.status_code.upper() == "DRAFT"
        is_posted = inv is not None and inv.status_code.upper() == "POSTED"
        self._edit_button.setEnabled(enabled and is_draft)
        self._post_button.setEnabled(enabled and not is_posted)
        # Hide Post button once the invoice is already posted
        self._post_button.setVisible(enabled and not is_posted)

    def _open_edit_dialog(self) -> None:
        if self._invoice is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return
        from seeker_accounting.modules.sales.ui.sales_invoice_dialog import SalesInvoiceDialog
        updated = SalesInvoiceDialog.edit_invoice(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            invoice_id=self._invoice.id,
            parent=self,
        )
        if updated is not None:
            self._load_data()

    def _open_post_dialog(self) -> None:
        if self._invoice is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return
        # Navigate to invoices page to use its post workflow
        self._service_registry.navigation_service.navigate(
            nav_ids.SALES_INVOICES,
            context={"select_invoice_id": self._invoice.id},
        )
