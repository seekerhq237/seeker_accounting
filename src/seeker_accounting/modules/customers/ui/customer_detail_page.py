"""CustomerDetailPage — full customer workspace with activity, invoices, receipts, and info tabs.

Navigated to via:
    navigation_service.navigate(nav_ids.CUSTOMER_DETAIL, context={"customer_id": <int>})

Computes KPIs from posted transaction lists (no stored balance truth).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.customers.dto.customer_dto import CustomerDetailDTO
from seeker_accounting.modules.sales.dto.customer_receipt_dto import CustomerReceiptListItemDTO
from seeker_accounting.modules.sales.dto.sales_invoice_dto import SalesInvoiceListItemDTO
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.shared.ui.entity_detail.entity_detail_page import EntityDetailPage
from seeker_accounting.shared.ui.entity_detail.money_bar import MoneyBarItem
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_CURRENCY_FMT = "{:,.0f}"


def _fmt_amount(value: Decimal, currency: str = "") -> str:
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{_CURRENCY_FMT.format(value)}"


class CustomerDetailPage(EntityDetailPage):
    """Full detail workspace for a single customer."""

    _back_nav_id = nav_ids.CUSTOMERS
    _back_label = "Back to Customers"

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(service_registry, parent)
        self.setObjectName("CustomerDetailPage")

        self._customer_id: int | None = None
        self._customer: CustomerDetailDTO | None = None
        self._invoices: list[SalesInvoiceListItemDTO] = []
        self._receipts: list[CustomerReceiptListItemDTO] = []

        # Add action buttons to the action row
        self._new_invoice_button = QPushButton("New Invoice", self)
        self._new_invoice_button.setObjectName("PrimaryButton")
        self._new_invoice_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_invoice_button.clicked.connect(self._open_new_invoice)
        self._action_row_layout.addWidget(self._new_invoice_button)

        self._new_receipt_button = QPushButton("New Receipt", self)
        self._new_receipt_button.setObjectName("SecondaryButton")
        self._new_receipt_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_receipt_button.clicked.connect(self._open_new_receipt)
        self._action_row_layout.addWidget(self._new_receipt_button)

        self._edit_button = QPushButton("Edit", self)
        self._edit_button.setObjectName("SecondaryButton")
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.clicked.connect(self._open_edit_dialog)
        self._action_row_layout.addWidget(self._edit_button)

        # Build tabs
        self._invoices_tab = self._build_invoices_tab()
        self._receipts_tab = self._build_receipts_tab()
        self._info_tab = self._build_info_tab()

        self._initialize_tabs()

        # Initial disabled state until context arrives
        self._set_actions_enabled(False)

    # ── Tab construction ──────────────────────────────────────────────

    def _build_tabs(self) -> list[tuple[str, QWidget]]:
        return [
            ("Invoices", self._invoices_tab),
            ("Receipts", self._receipts_tab),
            ("Info", self._info_tab),
        ]

    def _build_invoices_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(0)

        self._invoices_table = QTableWidget(container)
        configure_compact_table(self._invoices_table)
        self._invoices_table.setColumnCount(7)
        self._invoices_table.setHorizontalHeaderLabels([
            "Invoice #", "Date", "Due Date", "Status", "Payment Status",
            "Total", "Open Balance",
        ])
        self._invoices_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._invoices_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._invoices_table.setSortingEnabled(True)
        self._invoices_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._invoices_table)

        return container

    def _build_receipts_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(0)

        self._receipts_table = QTableWidget(container)
        configure_compact_table(self._receipts_table)
        self._receipts_table.setColumnCount(5)
        self._receipts_table.setHorizontalHeaderLabels([
            "Receipt #", "Date", "Account", "Status", "Amount Received",
        ])
        self._receipts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._receipts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._receipts_table.setSortingEnabled(True)
        self._receipts_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._receipts_table)

        return container

    def _build_info_tab(self) -> QWidget:
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
            lbl.setFixedWidth(160)
            row_layout.addWidget(lbl)

            val = QLabel("—", row_widget)
            val.setObjectName("EntityInfoValue")
            val.setWordWrap(True)
            row_layout.addWidget(val, 1)
            layout.addWidget(row_widget)
            setattr(self, attr_name, val)

        _row("Customer Code", "_info_code")
        _row("Legal Name", "_info_legal_name")
        _row("Group", "_info_group")
        _row("Payment Term", "_info_payment_term")
        _row("Tax Identifier", "_info_tax_id")
        _row("Email", "_info_email")
        _row("Phone", "_info_phone")
        _row("Address", "_info_address")
        _row("Credit Limit", "_info_credit_limit")
        _row("Notes", "_info_notes")
        _row("Created", "_info_created")
        layout.addStretch(1)

        return container

    # ── Navigation context ────────────────────────────────────────────

    def set_navigation_context(self, context: dict) -> None:
        customer_id = context.get("customer_id")
        if not isinstance(customer_id, int):
            return
        self._customer_id = customer_id
        self._load_data()

    # ── Data loading ──────────────────────────────────────────────────

    def _load_data(self) -> None:
        if self._customer_id is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        company_id = active_company.company_id

        # Load customer detail
        try:
            self._customer = self._service_registry.customer_service.get_customer(
                company_id, self._customer_id
            )
        except NotFoundError:
            show_error(self, "Customer Detail", "Customer not found.")
            self._navigate_back()
            return
        except Exception as exc:
            show_error(self, "Customer Detail", f"Failed to load customer: {exc}")
            return

        # Load invoices (filter to this customer)
        try:
            all_invoices = self._service_registry.sales_invoice_service.list_sales_invoices(company_id)
            self._invoices = [inv for inv in all_invoices if inv.customer_id == self._customer_id]
        except Exception as exc:
            _log.warning("Could not load invoices for customer %s: %s", self._customer_id, exc)
            self._invoices = []

        # Load receipts (filter to this customer)
        try:
            all_receipts = self._service_registry.customer_receipt_service.list_customer_receipts(company_id)
            self._receipts = [r for r in all_receipts if r.customer_id == self._customer_id]
        except Exception as exc:
            _log.warning("Could not load receipts for customer %s: %s", self._customer_id, exc)
            self._receipts = []

        self._populate_header()
        self._populate_money_bar()
        self._populate_invoices_table()
        self._populate_receipts_table()
        self._populate_info_tab()
        self._set_actions_enabled(True)

    # ── Population ────────────────────────────────────────────────────

    def _populate_header(self) -> None:
        c = self._customer
        if c is None:
            return
        parts = [p for p in [c.customer_group_name, c.payment_term_name] if p]
        subtitle = f"{c.customer_code}  ·  " + "  ·  ".join(parts) if parts else c.customer_code
        self._set_header(
            title=c.display_name,
            subtitle=subtitle,
            status_label="Active" if c.is_active else "Inactive",
            is_active=c.is_active,
        )

    def _populate_money_bar(self) -> None:
        today = date.today()
        cutoff_30d = today - timedelta(days=30)

        posted_invoices = [inv for inv in self._invoices if inv.status_code == "POSTED"]
        overdue_total = sum(
            inv.open_balance_amount
            for inv in posted_invoices
            if inv.due_date < today and inv.open_balance_amount > Decimal(0)
        )
        open_total = sum(
            inv.open_balance_amount
            for inv in posted_invoices
            if inv.open_balance_amount > Decimal(0)
        )
        paid_30d = sum(
            r.amount_received
            for r in self._receipts
            if r.status_code == "POSTED" and r.receipt_date >= cutoff_30d
        )

        credit_limit = self._customer.credit_limit_amount if self._customer else None

        items = [
            MoneyBarItem(
                label="Overdue",
                value=_fmt_amount(overdue_total) if overdue_total else "0",
                tone="danger" if overdue_total > Decimal(0) else "neutral",
            ),
            MoneyBarItem(
                label="Open Balance",
                value=_fmt_amount(open_total) if open_total else "0",
                tone="warning" if open_total > Decimal(0) else "neutral",
            ),
            MoneyBarItem(
                label="Paid (30 days)",
                value=_fmt_amount(paid_30d) if paid_30d else "0",
                tone="success" if paid_30d > Decimal(0) else "neutral",
            ),
        ]
        if credit_limit is not None:
            items.append(MoneyBarItem(
                label="Credit Limit",
                value=_fmt_amount(credit_limit),
                tone="neutral",
            ))

        self._set_money_bar(items)

    def _populate_invoices_table(self) -> None:
        self._invoices_table.setSortingEnabled(False)
        self._invoices_table.setRowCount(0)
        self._invoices_table.setRowCount(len(self._invoices))

        for row, inv in enumerate(sorted(self._invoices, key=lambda x: x.invoice_date, reverse=True)):
            def _cell(text: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
                return item

            right = Qt.AlignmentFlag.AlignRight

            self._invoices_table.setItem(row, 0, _cell(inv.invoice_number))
            self._invoices_table.setItem(row, 1, _cell(inv.invoice_date.strftime("%d %b %Y")))
            self._invoices_table.setItem(row, 2, _cell(inv.due_date.strftime("%d %b %Y")))
            self._invoices_table.setItem(row, 3, _cell(inv.status_code.title()))
            self._invoices_table.setItem(row, 4, _cell(inv.payment_status_code.replace("_", " ").title()))
            self._invoices_table.setItem(row, 5, _cell(_fmt_amount(inv.total_amount), right))
            self._invoices_table.setItem(row, 6, _cell(_fmt_amount(inv.open_balance_amount), right))

        self._invoices_table.setSortingEnabled(True)
        self._invoices_table.resizeColumnsToContents()

    def _populate_receipts_table(self) -> None:
        self._receipts_table.setSortingEnabled(False)
        self._receipts_table.setRowCount(0)
        self._receipts_table.setRowCount(len(self._receipts))

        for row, receipt in enumerate(sorted(self._receipts, key=lambda x: x.receipt_date, reverse=True)):
            def _cell(text: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
                return item

            right = Qt.AlignmentFlag.AlignRight

            self._receipts_table.setItem(row, 0, _cell(receipt.receipt_number))
            self._receipts_table.setItem(row, 1, _cell(receipt.receipt_date.strftime("%d %b %Y")))
            self._receipts_table.setItem(row, 2, _cell(receipt.financial_account_name))
            self._receipts_table.setItem(row, 3, _cell(receipt.status_code.title()))
            self._receipts_table.setItem(row, 4, _cell(_fmt_amount(receipt.amount_received), right))

        self._receipts_table.setSortingEnabled(True)
        self._receipts_table.resizeColumnsToContents()

    def _populate_info_tab(self) -> None:
        c = self._customer
        if c is None:
            return

        def _or_dash(val: str | None) -> str:
            return val or "—"

        addr_parts = [p for p in [c.address_line_1, c.address_line_2, c.city, c.region] if p]
        address = ", ".join(addr_parts) or "—"
        if c.country_code:
            address = f"{address} ({c.country_code})" if address != "—" else c.country_code

        self._info_code.setText(_or_dash(c.customer_code))
        self._info_legal_name.setText(_or_dash(c.legal_name))
        self._info_group.setText(_or_dash(c.customer_group_name))
        self._info_payment_term.setText(_or_dash(c.payment_term_name))
        self._info_tax_id.setText(_or_dash(c.tax_identifier))
        self._info_email.setText(_or_dash(c.email))
        self._info_phone.setText(_or_dash(c.phone))
        self._info_address.setText(address)
        self._info_credit_limit.setText(
            _fmt_amount(c.credit_limit_amount) if c.credit_limit_amount is not None else "—"
        )
        self._info_notes.setText(_or_dash(c.notes))
        self._info_created.setText(c.created_at.strftime("%d %b %Y %H:%M"))

    # ── Actions ───────────────────────────────────────────────────────

    def _set_actions_enabled(self, enabled: bool) -> None:
        self._new_invoice_button.setEnabled(enabled)
        self._new_receipt_button.setEnabled(enabled)
        self._edit_button.setEnabled(enabled)

    def _open_new_invoice(self) -> None:
        self._service_registry.navigation_service.navigate(
            nav_ids.SALES_INVOICES,
            context={"command_palette_action": "open_create_dialog"},
        )

    def _open_new_receipt(self) -> None:
        self._service_registry.navigation_service.navigate(
            nav_ids.CUSTOMER_RECEIPTS,
            context={"command_palette_action": "open_create_dialog"},
        )

    def _open_edit_dialog(self) -> None:
        if self._customer is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        from seeker_accounting.modules.customers.ui.customer_dialog import CustomerDialog
        updated = CustomerDialog.edit_customer(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            customer_id=self._customer.id,
            parent=self,
        )
        if updated is not None:
            self._load_data()
