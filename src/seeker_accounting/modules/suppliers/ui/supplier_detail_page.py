"""SupplierDetailPage — full supplier workspace with bills, payments, and info tabs.

Navigated to via:
    navigation_service.navigate(nav_ids.SUPPLIER_DETAIL, context={"supplier_id": <int>})
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import PurchaseBillListItemDTO
from seeker_accounting.modules.purchases.dto.supplier_payment_dto import SupplierPaymentListItemDTO
from seeker_accounting.modules.suppliers.dto.supplier_dto import SupplierDetailDTO
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.shared.ui.entity_detail.entity_detail_page import EntityDetailPage
from seeker_accounting.shared.ui.entity_detail.money_bar import MoneyBarItem
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_CURRENCY_FMT = "{:,.0f}"


def _fmt_amount(value: Decimal) -> str:
    return _CURRENCY_FMT.format(value)


class SupplierDetailPage(EntityDetailPage):
    """Full detail workspace for a single supplier."""

    _back_nav_id = nav_ids.SUPPLIERS
    _back_label = "Back to Suppliers"

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(service_registry, parent)
        self.setObjectName("SupplierDetailPage")

        self._supplier_id: int | None = None
        self._supplier: SupplierDetailDTO | None = None
        self._bills: list[PurchaseBillListItemDTO] = []
        self._payments: list[SupplierPaymentListItemDTO] = []

        # Action buttons
        self._new_bill_button = QPushButton("New Bill", self)
        self._new_bill_button.setObjectName("PrimaryButton")
        self._new_bill_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_bill_button.clicked.connect(self._open_new_bill)
        self._action_row_layout.addWidget(self._new_bill_button)

        self._new_payment_button = QPushButton("New Payment", self)
        self._new_payment_button.setObjectName("SecondaryButton")
        self._new_payment_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_payment_button.clicked.connect(self._open_new_payment)
        self._action_row_layout.addWidget(self._new_payment_button)

        self._edit_button = QPushButton("Edit", self)
        self._edit_button.setObjectName("SecondaryButton")
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.clicked.connect(self._open_edit_dialog)
        self._action_row_layout.addWidget(self._edit_button)

        # Build tabs
        self._bills_tab = self._build_bills_tab()
        self._payments_tab = self._build_payments_tab()
        self._info_tab = self._build_info_tab()

        self._initialize_tabs()
        self._set_actions_enabled(False)

    # ── Tab construction ──────────────────────────────────────────────

    def _build_tabs(self) -> list[tuple[str, QWidget]]:
        return [
            ("Bills", self._bills_tab),
            ("Payments", self._payments_tab),
            ("Info", self._info_tab),
        ]

    def _build_bills_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(0)

        self._bills_table = QTableWidget(container)
        configure_compact_table(self._bills_table)
        self._bills_table.setColumnCount(7)
        self._bills_table.setHorizontalHeaderLabels([
            "Bill #", "Date", "Due Date", "Status", "Payment Status",
            "Total", "Open Balance",
        ])
        self._bills_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bills_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._bills_table.setSortingEnabled(True)
        self._bills_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._bills_table)

        return container

    def _build_payments_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(0)

        self._payments_table = QTableWidget(container)
        configure_compact_table(self._payments_table)
        self._payments_table.setColumnCount(5)
        self._payments_table.setHorizontalHeaderLabels([
            "Payment #", "Date", "Account", "Status", "Amount Paid",
        ])
        self._payments_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._payments_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._payments_table.setSortingEnabled(True)
        self._payments_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._payments_table)

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

        _row("Supplier Code", "_info_code")
        _row("Legal Name", "_info_legal_name")
        _row("Group", "_info_group")
        _row("Payment Term", "_info_payment_term")
        _row("Tax Identifier", "_info_tax_id")
        _row("Email", "_info_email")
        _row("Phone", "_info_phone")
        _row("Address", "_info_address")
        _row("Notes", "_info_notes")
        _row("Created", "_info_created")
        layout.addStretch(1)

        return container

    # ── Navigation context ────────────────────────────────────────────

    def set_navigation_context(self, context: dict) -> None:
        supplier_id = context.get("supplier_id")
        if not isinstance(supplier_id, int):
            return
        self._supplier_id = supplier_id
        self._load_data()

    # ── Data loading ──────────────────────────────────────────────────

    def _load_data(self) -> None:
        if self._supplier_id is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        company_id = active_company.company_id

        try:
            self._supplier = self._service_registry.supplier_service.get_supplier(
                company_id, self._supplier_id
            )
        except NotFoundError:
            show_error(self, "Supplier Detail", "Supplier not found.")
            self._navigate_back()
            return
        except Exception as exc:
            show_error(self, "Supplier Detail", f"Failed to load supplier: {exc}")
            return

        try:
            all_bills = self._service_registry.purchase_bill_service.list_purchase_bills(company_id)
            self._bills = [b for b in all_bills if b.supplier_id == self._supplier_id]
        except Exception as exc:
            _log.warning("Could not load bills for supplier %s: %s", self._supplier_id, exc)
            self._bills = []

        try:
            all_payments = self._service_registry.supplier_payment_service.list_supplier_payments(company_id)
            self._payments = [p for p in all_payments if p.supplier_id == self._supplier_id]
        except Exception as exc:
            _log.warning("Could not load payments for supplier %s: %s", self._supplier_id, exc)
            self._payments = []

        self._populate_header()
        self._populate_money_bar()
        self._populate_bills_table()
        self._populate_payments_table()
        self._populate_info_tab()
        self._set_actions_enabled(True)

    # ── Population ────────────────────────────────────────────────────

    def _populate_header(self) -> None:
        s = self._supplier
        if s is None:
            return
        parts = [p for p in [s.supplier_group_name, s.payment_term_name] if p]
        subtitle = f"{s.supplier_code}  ·  " + "  ·  ".join(parts) if parts else s.supplier_code
        self._set_header(
            title=s.display_name,
            subtitle=subtitle,
            status_label="Active" if s.is_active else "Inactive",
            is_active=s.is_active,
        )

    def _populate_money_bar(self) -> None:
        today = date.today()
        cutoff_30d = today - timedelta(days=30)

        posted_bills = [b for b in self._bills if b.status_code == "POSTED"]
        overdue_total = sum(
            b.open_balance_amount
            for b in posted_bills
            if b.due_date < today and b.open_balance_amount > Decimal(0)
        )
        open_total = sum(
            b.open_balance_amount
            for b in posted_bills
            if b.open_balance_amount > Decimal(0)
        )
        paid_30d = sum(
            p.amount_paid
            for p in self._payments
            if p.status_code == "POSTED" and p.payment_date >= cutoff_30d
        )

        self._set_money_bar([
            MoneyBarItem(
                label="Overdue Bills",
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
        ])

    def _populate_bills_table(self) -> None:
        self._bills_table.setSortingEnabled(False)
        self._bills_table.setRowCount(0)
        self._bills_table.setRowCount(len(self._bills))

        for row, bill in enumerate(sorted(self._bills, key=lambda x: x.bill_date, reverse=True)):
            def _cell(text: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
                return item

            right = Qt.AlignmentFlag.AlignRight

            self._bills_table.setItem(row, 0, _cell(bill.bill_number))
            self._bills_table.setItem(row, 1, _cell(bill.bill_date.strftime("%d %b %Y")))
            self._bills_table.setItem(row, 2, _cell(bill.due_date.strftime("%d %b %Y")))
            self._bills_table.setItem(row, 3, _cell(bill.status_code.title()))
            self._bills_table.setItem(row, 4, _cell(bill.payment_status_code.replace("_", " ").title()))
            self._bills_table.setItem(row, 5, _cell(_fmt_amount(bill.total_amount), right))
            self._bills_table.setItem(row, 6, _cell(_fmt_amount(bill.open_balance_amount), right))

        self._bills_table.setSortingEnabled(True)
        self._bills_table.resizeColumnsToContents()

    def _populate_payments_table(self) -> None:
        self._payments_table.setSortingEnabled(False)
        self._payments_table.setRowCount(0)
        self._payments_table.setRowCount(len(self._payments))

        for row, payment in enumerate(sorted(self._payments, key=lambda x: x.payment_date, reverse=True)):
            def _cell(text: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
                return item

            right = Qt.AlignmentFlag.AlignRight

            self._payments_table.setItem(row, 0, _cell(payment.payment_number))
            self._payments_table.setItem(row, 1, _cell(payment.payment_date.strftime("%d %b %Y")))
            self._payments_table.setItem(row, 2, _cell(payment.financial_account_name))
            self._payments_table.setItem(row, 3, _cell(payment.status_code.title()))
            self._payments_table.setItem(row, 4, _cell(_fmt_amount(payment.amount_paid), right))

        self._payments_table.setSortingEnabled(True)
        self._payments_table.resizeColumnsToContents()

    def _populate_info_tab(self) -> None:
        s = self._supplier
        if s is None:
            return

        def _or_dash(val: str | None) -> str:
            return val or "—"

        addr_parts = [p for p in [s.address_line_1, s.address_line_2, s.city, s.region] if p]
        address = ", ".join(addr_parts) or "—"
        if s.country_code:
            address = f"{address} ({s.country_code})" if address != "—" else s.country_code

        self._info_code.setText(_or_dash(s.supplier_code))
        self._info_legal_name.setText(_or_dash(s.legal_name))
        self._info_group.setText(_or_dash(s.supplier_group_name))
        self._info_payment_term.setText(_or_dash(s.payment_term_name))
        self._info_tax_id.setText(_or_dash(s.tax_identifier))
        self._info_email.setText(_or_dash(s.email))
        self._info_phone.setText(_or_dash(s.phone))
        self._info_address.setText(address)
        self._info_notes.setText(_or_dash(s.notes))
        self._info_created.setText(s.created_at.strftime("%d %b %Y %H:%M"))

    # ── Actions ───────────────────────────────────────────────────────

    def _set_actions_enabled(self, enabled: bool) -> None:
        self._new_bill_button.setEnabled(enabled)
        self._new_payment_button.setEnabled(enabled)
        self._edit_button.setEnabled(enabled)

    def _open_new_bill(self) -> None:
        self._service_registry.navigation_service.navigate(
            nav_ids.PURCHASE_BILLS,
            context={"command_palette_action": "open_create_dialog"},
        )

    def _open_new_payment(self) -> None:
        self._service_registry.navigation_service.navigate(
            nav_ids.SUPPLIER_PAYMENTS,
            context={"command_palette_action": "open_create_dialog"},
        )

    def _open_edit_dialog(self) -> None:
        if self._supplier is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        from seeker_accounting.modules.suppliers.ui.supplier_dialog import SupplierDialog
        updated = SupplierDialog.edit_supplier(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            supplier_id=self._supplier.id,
            parent=self,
        )
        if updated is not None:
            self._load_data()
