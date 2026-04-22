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
from seeker_accounting.modules.purchases.dto.supplier_payment_commands import (
    SupplierPaymentAllocationCommand,
)
from seeker_accounting.modules.purchases.dto.supplier_payment_dto import SupplierPaymentAllocationDTO
from seeker_accounting.platform.exceptions import PermissionDeniedError
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

logger = logging.getLogger(__name__)


class SupplierPaymentAllocationsPanel(QFrame):
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

        title = QLabel("Bill Allocations", header_row)
        title.setObjectName("CardTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self._alloc_summary_label = QLabel("", header_row)
        self._alloc_summary_label.setObjectName("ToolbarMeta")
        header_layout.addWidget(self._alloc_summary_label)

        layout.addWidget(header_row)

        helper_label = QLabel(
            "Only posted bills in the same currency are available for allocation.",
            self,
        )
        helper_label.setObjectName("ToolbarMeta")
        helper_label.setWordWrap(True)
        layout.addWidget(helper_label)

        self._table = QTableWidget(self)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            (
                "Bill #",
                "Bill Date",
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

        self._empty_label = QLabel("Select a supplier to see open bills.", self)
        self._empty_label.setObjectName("PageSummary")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

    def load_open_bills(self, supplier_id: int) -> None:
        self._table.setRowCount(0)
        self._empty_label.hide()
        self._table.show()

        try:
            open_bills = self._service_registry.supplier_payment_service.list_allocatable_bills(
                self._company_id, supplier_id
            )
        except PermissionDeniedError as exc:
            self._table.hide()
            self._empty_label.setText(str(exc))
            self._empty_label.show()
            self._alloc_summary_label.setText("")
            self.allocations_changed.emit()
            return
        except Exception:
            logger.exception("Failed to load open bills for supplier %s.", supplier_id)
            self._table.hide()
            self._empty_label.setText("Could not load open bills. Please try again.")
            self._empty_label.show()
            self._alloc_summary_label.setText("")
            self.allocations_changed.emit()
            return

        if not open_bills:
            self._empty_label.setText("No open bills for this supplier.")
            self._empty_label.show()
            self._alloc_summary_label.setText("")
            self.allocations_changed.emit()
            return

        for bill in open_bills:
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(bill.bill_number)
            num_item.setData(Qt.ItemDataRole.UserRole, bill.id)
            self._table.setItem(row, 0, num_item)

            self._table.setItem(row, 1, QTableWidgetItem(bill.bill_date.strftime("%Y-%m-%d")))
            self._table.setItem(row, 2, QTableWidgetItem(bill.due_date.strftime("%Y-%m-%d")))
            self._table.setItem(row, 3, QTableWidgetItem(bill.currency_code))

            total_item = QTableWidgetItem(f"{bill.total_amount:,.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, total_item)

            outstanding_item = QTableWidgetItem(f"{bill.open_balance_amount:,.2f}")
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
        supplier_id: int,
        existing_allocations: tuple[SupplierPaymentAllocationDTO, ...],
    ) -> None:
        self.load_open_bills(supplier_id)

        alloc_by_bill: dict[int, Decimal] = {
            a.purchase_bill_id: a.allocated_amount for a in existing_allocations
        }

        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None:
                continue
            bill_id = item.data(Qt.ItemDataRole.UserRole)
            if bill_id in alloc_by_bill:
                widget = self._table.cellWidget(row, 6)
                if isinstance(widget, QLineEdit):
                    widget.setText(str(alloc_by_bill[bill_id]))

        self._refresh_summary()
        self.allocations_changed.emit()

    def get_allocation_commands(self) -> list[SupplierPaymentAllocationCommand]:
        commands: list[SupplierPaymentAllocationCommand] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None:
                continue
            bill_id = item.data(Qt.ItemDataRole.UserRole)
            widget = self._table.cellWidget(row, 6)
            if not isinstance(widget, QLineEdit):
                continue
            amount = self._parse_decimal(widget.text())
            if amount is not None and amount > Decimal("0"):
                commands.append(
                    SupplierPaymentAllocationCommand(
                        purchase_bill_id=bill_id,
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
        self._empty_label.setText("Select a supplier to see open bills.")
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
        bill_count = self._table.rowCount()
        if bill_count == 0:
            self._alloc_summary_label.setText("")
            return

        entered_total = self.entered_total()
        summary = "1 open bill" if bill_count == 1 else f"{bill_count} open bills"
        if entered_total > Decimal("0.00"):
            summary = f"{summary} | {entered_total:,.2f} entered"
        self._alloc_summary_label.setText(summary)

    def _on_allocations_changed(self, *_args: object) -> None:
        self._refresh_summary()
        self.allocations_changed.emit()
