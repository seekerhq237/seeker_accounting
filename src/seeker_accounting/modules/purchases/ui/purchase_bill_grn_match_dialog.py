from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.inventory.services.goods_receipt_service import (
    GrnBillMatchBillLineDTO,
    GrnBillMatchLineCommand,
    GrnBillMatchOptionsDTO,
    GrnBillMatchReceiptLineDTO,
    GrnBillMatchResultDTO,
)
from seeker_accounting.platform.exceptions import AppError, ValidationError
from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from seeker_accounting.shared.ui.message_boxes import show_error


_ZERO = Decimal("0")


class PurchaseBillGrnMatchDialog(QDialog):
    """Match posted purchase bill lines to posted GRN lines."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        purchase_bill_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._purchase_bill_id = purchase_bill_id
        self._options: GrnBillMatchOptionsDTO = (
            service_registry.goods_receipt_service.get_match_options(company_id, purchase_bill_id)
        )
        self._receipt_rows: list[GrnBillMatchReceiptLineDTO] = []
        self._saved_result: GrnBillMatchResultDTO | None = None

        self.setWindowTitle(f"Match GRNs - Bill {self._options.bill_number}")
        self.setModal(True)
        apply_window_size(self, "modules.purchases.ui.purchase.bill.grn_match.dialog.0")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addWidget(self._build_header())
        root.addWidget(self._build_bill_line_selector())
        root.addWidget(self._build_receipt_table(), 1)
        root.addWidget(self._build_summary())
        root.addWidget(self._build_buttons())

        self._populate_bill_lines()
        self._refresh_receipts()
        self._sync_action_state()

    @property
    def saved_result(self) -> GrnBillMatchResultDTO | None:
        return self._saved_result

    @classmethod
    def match_bill(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        purchase_bill_id: int,
        parent: QWidget | None = None,
    ) -> GrnBillMatchResultDTO | None:
        dialog = cls(service_registry, company_id, purchase_bill_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_result
        return None

    def _build_header(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("PageCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        title = QLabel(f"Bill {self._options.bill_number}", frame)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        meta = QLabel(
            f"Posted bill date: {self._options.bill_date:%d %b %Y}  |  "
            f"Open bill lines: {len(self._options.bill_lines)}  |  "
            f"Open GRN lines: {len(self._options.receipt_lines)}",
            frame,
        )
        meta.setObjectName("MetaLabel")
        layout.addWidget(meta)
        return frame

    def _build_bill_line_selector(self) -> QWidget:
        frame = QFrame(self)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel("Bill line", frame)
        label.setObjectName("MetaLabel")
        layout.addWidget(label)

        self._bill_line_combo = QComboBox(frame)
        self._bill_line_combo.currentIndexChanged.connect(lambda _index: self._refresh_receipts())
        layout.addWidget(self._bill_line_combo, 1)
        return frame

    def _build_receipt_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 7, self)
        self._table.setHorizontalHeaderLabels(
            ["GRN", "Date", "Item", "Available", "Unit Cost", "Amount", "Match Qty"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(260)
        self._table.itemChanged.connect(lambda _item: self._update_summary())
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(2, self._table.horizontalHeader().ResizeMode.Stretch)
        return self._table

    def _build_summary(self) -> QWidget:
        row = QFrame(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._summary_label = QLabel("No quantities selected", row)
        self._summary_label.setObjectName("StatusRailText")
        layout.addWidget(self._summary_label)
        layout.addStretch(1)
        return row

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._match_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self._match_button.setText("Match GRNs")
        buttons.accepted.connect(self._handle_match)
        buttons.rejected.connect(self.reject)
        return buttons

    def _populate_bill_lines(self) -> None:
        self._bill_line_combo.clear()
        for line in self._options.bill_lines:
            item_hint = f" | item {line.item_id}" if line.item_id is not None else ""
            self._bill_line_combo.addItem(
                f"#{line.line_number} {line.description} | available {line.available_qty}{item_hint}",
                line.purchase_bill_line_id,
            )

    def _selected_bill_line(self) -> GrnBillMatchBillLineDTO | None:
        line_id = self._bill_line_combo.currentData()
        if not isinstance(line_id, int):
            return None
        return next(
            (line for line in self._options.bill_lines if line.purchase_bill_line_id == line_id),
            None,
        )

    def _refresh_receipts(self) -> None:
        selected_line = self._selected_bill_line()
        if selected_line is None:
            self._receipt_rows = []
        else:
            self._receipt_rows = [
                row
                for row in self._options.receipt_lines
                if selected_line.item_id is None or row.item_id == selected_line.item_id
            ]

        self._table.blockSignals(True)
        self._table.setRowCount(len(self._receipt_rows))
        for row_index, row in enumerate(self._receipt_rows):
            self._set_readonly_item(row_index, 0, row.document_number)
            self._set_readonly_item(row_index, 1, f"{row.receipt_date:%Y-%m-%d}")
            item_label = f"{row.item_code}  {row.item_name}".strip() or str(row.item_id)
            self._set_readonly_item(row_index, 2, item_label)
            self._set_readonly_item(row_index, 3, self._fmt_quantity(row.available_qty), align_right=True)
            self._set_readonly_item(row_index, 4, self._fmt_money(row.unit_cost), align_right=True)
            self._set_readonly_item(row_index, 5, self._fmt_money(row.available_amount), align_right=True)
            qty_item = QTableWidgetItem("")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_index, 6, qty_item)
        self._table.blockSignals(False)
        self._update_summary()
        self._sync_action_state()

    def _set_readonly_item(
        self,
        row: int,
        column: int,
        text: str,
        *,
        align_right: bool = False,
    ) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, column, item)

    def _handle_match(self) -> None:
        selected_line = self._selected_bill_line()
        if selected_line is None:
            show_error(self, "Match GRNs", "There are no open bill lines to match.")
            return

        try:
            commands = self._collect_commands(selected_line)
        except ValidationError as exc:
            show_error(self, "Match GRNs", str(exc))
            return

        if not commands:
            show_error(self, "Match GRNs", "Enter a quantity on at least one GRN line.")
            return

        try:
            self._saved_result = self._service_registry.goods_receipt_service.match_to_bill(
                company_id=self._company_id,
                purchase_bill_id=self._purchase_bill_id,
                lines=commands,
            )
            self.accept()
        except AppError as exc:
            show_error(self, "Match GRNs", str(exc))
        except Exception as exc:
            show_error(self, "Match GRNs", f"An unexpected error occurred.\n\n{exc}")

    def _collect_commands(
        self,
        selected_line: GrnBillMatchBillLineDTO,
    ) -> list[GrnBillMatchLineCommand]:
        commands: list[GrnBillMatchLineCommand] = []
        total_qty = _ZERO
        for row_index, receipt_line in enumerate(self._receipt_rows):
            item = self._table.item(row_index, 6)
            text = item.text().strip() if item is not None else ""
            if not text:
                continue
            try:
                qty = Decimal(text)
            except (InvalidOperation, ValueError) as exc:
                raise ValidationError(f"Match quantity on row {row_index + 1} must be numeric.") from exc
            if qty <= _ZERO:
                continue
            if qty > receipt_line.available_qty:
                raise ValidationError(f"Match quantity on row {row_index + 1} exceeds the available GRN quantity.")
            total_qty += qty
            commands.append(
                GrnBillMatchLineCommand(
                    purchase_bill_line_id=selected_line.purchase_bill_line_id,
                    inventory_document_line_id=receipt_line.inventory_document_line_id,
                    matched_qty=qty,
                )
            )
        if total_qty > selected_line.available_qty:
            raise ValidationError("Total matched quantity exceeds the selected bill line's available quantity.")
        return commands

    def _sync_action_state(self) -> None:
        self._match_button.setEnabled(bool(self._options.bill_lines and self._receipt_rows))

    def _update_summary(self) -> None:
        selected_line = self._selected_bill_line()
        if selected_line is None:
            self._summary_label.setText("No open bill lines")
            return
        total = _ZERO
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 6)
            text = item.text().strip() if item is not None else ""
            if not text:
                continue
            try:
                qty = Decimal(text)
            except (InvalidOperation, ValueError):
                continue
            if qty > _ZERO:
                total += qty
        self._summary_label.setText(
            f"Selected {self._fmt_quantity(total)} of {self._fmt_quantity(selected_line.available_qty)} available"
        )

    @staticmethod
    def _fmt_quantity(value: Decimal) -> str:
        return f"{Decimal(str(value)):,.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def _fmt_money(value: Decimal) -> str:
        return f"{Decimal(str(value)):,.2f}"