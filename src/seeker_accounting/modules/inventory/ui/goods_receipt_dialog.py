"""Goods Receipt (GRN) Dialog — create a GRN from a Purchase Order."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error


class GoodsReceiptDialog(QDialog):
    """Create a GRN document against an open Purchase Order."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        purchase_order_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._purchase_order_id = purchase_order_id
        self._po_lines: list = []

        self.setWindowTitle("Goods Receipt (GRN)")
        self.setModal(True)
        self.setMinimumWidth(720)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addWidget(self._build_header_form())
        root.addWidget(QLabel("Lines to Receive:", self))
        root.addWidget(self._build_lines_table())
        root.addWidget(self._build_buttons())

        if purchase_order_id is not None:
            self._load_po_lines()

    # ------------------------------------------------------------------
    def _build_header_form(self) -> QWidget:
        frame = QFrame(self)
        form = QFormLayout(frame)
        form.setContentsMargins(0, 0, 0, 0)

        self._po_id_edit = QLineEdit(frame)
        self._po_id_edit.setPlaceholderText("Purchase Order ID")
        if self._purchase_order_id is not None:
            self._po_id_edit.setText(str(self._purchase_order_id))
        load_btn = QPushButton("Load PO", frame)
        load_btn.setFixedHeight(26)
        load_btn.clicked.connect(self._load_po_lines)
        po_row = QHBoxLayout()
        po_row.addWidget(self._po_id_edit)
        po_row.addWidget(load_btn)

        self._receipt_date = QDateEdit(frame)
        self._receipt_date.setDate(QDate.currentDate())
        self._receipt_date.setCalendarPopup(True)

        self._reference_edit = QLineEdit(frame)
        self._reference_edit.setPlaceholderText("Delivery note / reference")

        form.addRow("Purchase Order *", po_row)
        form.addRow("Receipt Date *", self._receipt_date)
        form.addRow("Reference", self._reference_edit)
        return frame

    def _build_lines_table(self) -> QTableWidget:
        self._lines_table = QTableWidget(0, 6, self)
        self._lines_table.setHorizontalHeaderLabels(
            ["PO Line", "Item", "Description", "Ordered Qty", "Rcv Qty", "Unit Cost"]
        )
        self._lines_table.horizontalHeader().setSectionResizeMode(
            2, self._lines_table.horizontalHeader().ResizeMode.Stretch
        )
        self._lines_table.verticalHeader().setVisible(False)
        self._lines_table.setAlternatingRowColors(True)
        self._lines_table.setMinimumHeight(220)
        return self._lines_table

    def _build_buttons(self) -> QDialogButtonBox:
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setText("Create GRN")
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        return btns

    # ------------------------------------------------------------------
    def _load_po_lines(self) -> None:
        po_id_text = self._po_id_edit.text().strip()
        if not po_id_text:
            return
        try:
            po_id = int(po_id_text)
        except ValueError:
            show_error(self, "Load PO", "Please enter a valid PO ID.")
            return

        self._purchase_order_id = po_id
        svc = self._service_registry
        try:
            po = svc.purchase_order_service.get_purchase_order(self._company_id, po_id)
        except Exception as exc:
            show_error(self, "Load PO", str(exc))
            return

        self._po_lines = po.lines if hasattr(po, "lines") else []
        self._lines_table.setRowCount(len(self._po_lines))
        for r, line in enumerate(self._po_lines):
            self._lines_table.setItem(r, 0, QTableWidgetItem(str(line.id)))
            self._lines_table.setItem(r, 1, QTableWidgetItem(str(line.item_id or "")))
            self._lines_table.setItem(r, 2, QTableWidgetItem(line.line_description or ""))

            qty_item = QTableWidgetItem(str(line.quantity))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            qty_item.setFlags(qty_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._lines_table.setItem(r, 3, qty_item)

            rcv_item = QTableWidgetItem(str(line.quantity))
            rcv_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._lines_table.setItem(r, 4, rcv_item)

            cost_item = QTableWidgetItem(str(line.unit_cost or "0"))
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._lines_table.setItem(r, 5, cost_item)

    def _save(self) -> None:
        if self._purchase_order_id is None:
            show_error(self, "Validation", "Load a Purchase Order first.")
            return

        from seeker_accounting.modules.inventory.services.goods_receipt_service import GrnLineCommand
        from decimal import Decimal

        lines = []
        for r in range(self._lines_table.rowCount()):
            line = self._po_lines[r]
            rcv_text = self._lines_table.item(r, 4).text().strip() if self._lines_table.item(r, 4) else "0"
            cost_text = self._lines_table.item(r, 5).text().strip() if self._lines_table.item(r, 5) else "0"
            try:
                rcv_qty = Decimal(rcv_text)
                unit_cost = Decimal(cost_text)
            except Exception:
                show_error(self, "Validation", f"Invalid qty or cost on line {r + 1}.")
                return
            if rcv_qty > 0:
                lines.append(
                    GrnLineCommand(
                        purchase_order_line_id=line.id,
                        item_id=line.item_id,
                        received_qty=rcv_qty,
                        unit_cost=unit_cost,
                        batch_id=None,
                        uom_id=getattr(line, "uom_id", None),
                        uom_ratio_snapshot=None,
                    )
                )

        if not lines:
            show_error(self, "Validation", "No lines with qty > 0.")
            return

        qd = self._receipt_date.date()
        receipt_date = date(qd.year(), qd.month(), qd.day())

        svc = self._service_registry.goods_receipt_service
        try:
            result = svc.create_from_po(
                company_id=self._company_id,
                purchase_order_id=self._purchase_order_id,
                lines=lines,
                location_id=None,  # default location
                receipt_date=receipt_date,
                reference=self._reference_edit.text().strip() or None,
                actor_user_id=None,
            )
            QMessageBox.information(self, "GRN Created", f"GRN document ID {result.inventory_document_id} created.")
            self.accept()
        except (ValidationError, Exception) as exc:
            show_error(self, "Create GRN", str(exc))
