from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.sales.dto.customer_receipt_commands import CustomerReceiptAllocationCommand
from seeker_accounting.modules.sales.dto.customer_receipt_dto import CustomerReceiptAllocationDTO
from seeker_accounting.platform.exceptions import PermissionDeniedError
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

logger = logging.getLogger(__name__)


class CustomerReceiptAllocationsPanel(QFrame):
    allocations_changed = Signal()

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id

        self.setObjectName("PageCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        header_row = QWidget(self)
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        title = QLabel("Invoice Allocations", header_row)
        title.setObjectName("CardTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self._alloc_summary_label = QLabel("", header_row)
        self._alloc_summary_label.setObjectName("ToolbarMeta")
        header_layout.addWidget(self._alloc_summary_label)

        layout.addWidget(header_row)

        helper_label = QLabel(
            "Only posted invoices in the same currency are available for allocation.",
            self,
        )
        helper_label.setObjectName("ToolbarMeta")
        helper_label.setWordWrap(True)
        layout.addWidget(helper_label)

        self._table = QTableWidget(self)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            (
                "Invoice #",
                "Invoice Date",
                "Due Date",
                "Currency",
                "Total",
                "Outstanding",
                "Allocate",
            )
        )
        configure_compact_table(self._table)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self._table)

        self._empty_label = QLabel("Select a customer to see open invoices.", self)
        self._empty_label.setObjectName("PageSummary")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

    def load_open_invoices(self, customer_id: int) -> None:
        self._table.setRowCount(0)
        self._empty_label.hide()
        self._table.show()

        try:
            open_invoices = self._service_registry.customer_receipt_service.list_allocatable_invoices(
                self._company_id, customer_id
            )
        except PermissionDeniedError as exc:
            self._table.hide()
            self._empty_label.setText(str(exc))
            self._empty_label.show()
            self._alloc_summary_label.setText("")
            self.allocations_changed.emit()
            return
        except Exception:
            logger.exception("Failed to load open invoices for customer %s.", customer_id)
            self._table.hide()
            self._empty_label.setText("Could not load open invoices. Please try again.")
            self._empty_label.show()
            self._alloc_summary_label.setText("")
            self.allocations_changed.emit()
            return

        if not open_invoices:
            self._empty_label.setText("No open invoices for this customer.")
            self._empty_label.show()
            self._alloc_summary_label.setText("")
            self.allocations_changed.emit()
            return

        for inv in open_invoices:
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(inv.invoice_number)
            num_item.setData(Qt.ItemDataRole.UserRole, inv.id)
            self._table.setItem(row, 0, num_item)

            self._table.setItem(row, 1, QTableWidgetItem(inv.invoice_date.strftime("%Y-%m-%d")))
            self._table.setItem(row, 2, QTableWidgetItem(inv.due_date.strftime("%Y-%m-%d")))
            self._table.setItem(row, 3, QTableWidgetItem(inv.currency_code))

            total_item = QTableWidgetItem(f"{inv.total_amount:,.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, total_item)

            outstanding_item = QTableWidgetItem(f"{inv.open_balance_amount:,.2f}")
            outstanding_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 5, outstanding_item)

            alloc_input = QLineEdit()
            alloc_input.setPlaceholderText("0.00")
            alloc_input.setAlignment(Qt.AlignmentFlag.AlignRight)
            alloc_input.textChanged.connect(self._on_allocations_changed)
            self._table.setCellWidget(row, 6, alloc_input)

        self._refresh_summary()
        self.allocations_changed.emit()

    def set_allocations(
        self,
        customer_id: int,
        existing_allocations: tuple[CustomerReceiptAllocationDTO, ...],
    ) -> None:
        self.load_open_invoices(customer_id)

        alloc_by_invoice: dict[int, Decimal] = {
            a.sales_invoice_id: a.allocated_amount for a in existing_allocations
        }

        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None:
                continue
            invoice_id = item.data(Qt.ItemDataRole.UserRole)
            if invoice_id in alloc_by_invoice:
                widget = self._table.cellWidget(row, 6)
                if isinstance(widget, QLineEdit):
                    widget.setText(str(alloc_by_invoice[invoice_id]))

        self._refresh_summary()
        self.allocations_changed.emit()

    def get_allocation_commands(self) -> list[CustomerReceiptAllocationCommand]:
        commands: list[CustomerReceiptAllocationCommand] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None:
                continue
            invoice_id = item.data(Qt.ItemDataRole.UserRole)
            widget = self._table.cellWidget(row, 6)
            if not isinstance(widget, QLineEdit):
                continue
            amount = self._parse_decimal(widget.text())
            if amount is not None and amount > Decimal("0"):
                commands.append(
                    CustomerReceiptAllocationCommand(
                        sales_invoice_id=invoice_id,
                        allocated_amount=amount,
                    )
                )
        return commands

    def entered_total(self) -> Decimal:
        total = Decimal("0.00")
        for row in range(self._table.rowCount()):
            widget = self._table.cellWidget(row, 6)
            if not isinstance(widget, QLineEdit):
                continue
            amount = self._parse_decimal(widget.text())
            if amount is not None and amount > Decimal("0.00"):
                total += amount
        return total

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._empty_label.setText("Select a customer to see open invoices.")
        self._empty_label.show()
        self._alloc_summary_label.setText("")
        self.allocations_changed.emit()

    def _parse_decimal(self, text: str) -> Decimal | None:
        text = text.replace(",", "").strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    def _refresh_summary(self) -> None:
        invoice_count = self._table.rowCount()
        if invoice_count == 0:
            self._alloc_summary_label.setText("")
            return

        entered_total = self.entered_total()
        summary = "1 open invoice" if invoice_count == 1 else f"{invoice_count} open invoices"
        if entered_total > Decimal("0.00"):
            summary = f"{summary} | {entered_total:,.2f} entered"
        self._alloc_summary_label.setText(summary)

    def _on_allocations_changed(self, *_args: object) -> None:
        self._refresh_summary()
        self.allocations_changed.emit()
