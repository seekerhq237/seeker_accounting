"""Price List Line Edit Dialog.

Used by PriceListDialog to add or edit a single price list line.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.inventory.services.price_list_service import PriceListLineDTO
from seeker_accounting.shared.ui.message_boxes import show_error

if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry


class PriceListLineEditDialog(QDialog):
    """Modal dialog for creating or editing a price list line."""

    def __init__(
        self,
        service_registry: "ServiceRegistry",
        company_id: int,
        line_dto: PriceListLineDTO | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._original_dto = line_dto
        self.result_dto: PriceListLineDTO | None = None
        self._build_ui()
        if line_dto is not None:
            self._populate(line_dto)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("Price List Line")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        # Item ID (integer; a full item selector could be used here in future)
        self._item_id_edit = QSpinBox()
        self._item_id_edit.setMinimum(1)
        self._item_id_edit.setMaximum(999999)
        form.addRow("Item ID:", self._item_id_edit)

        # UoM ID (optional)
        self._uom_id_edit = QSpinBox()
        self._uom_id_edit.setMinimum(0)
        self._uom_id_edit.setMaximum(999999)
        self._uom_id_edit.setSpecialValueText("(default UoM)")
        form.addRow("UoM ID:", self._uom_id_edit)

        # Min quantity
        self._min_qty_spin = QDoubleSpinBox()
        self._min_qty_spin.setMinimum(0.0)
        self._min_qty_spin.setMaximum(999999999.0)
        self._min_qty_spin.setDecimals(3)
        self._min_qty_spin.setValue(1.0)
        form.addRow("Min Quantity:", self._min_qty_spin)

        # Unit price
        self._unit_price_spin = QDoubleSpinBox()
        self._unit_price_spin.setMinimum(0.0)
        self._unit_price_spin.setMaximum(999999999.99)
        self._unit_price_spin.setDecimals(2)
        form.addRow("Unit Price:", self._unit_price_spin)

        # Valid from
        self._valid_from_edit = QDateEdit()
        self._valid_from_edit.setCalendarPopup(True)
        self._valid_from_edit.setSpecialValueText("(no start)")
        form.addRow("Valid From:", self._valid_from_edit)

        # Valid until
        self._valid_to_edit = QDateEdit()
        self._valid_to_edit.setCalendarPopup(True)
        self._valid_to_edit.setSpecialValueText("(no end)")
        form.addRow("Valid Until:", self._valid_to_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Populate from existing DTO
    # ------------------------------------------------------------------

    def _populate(self, dto: PriceListLineDTO) -> None:
        self._item_id_edit.setValue(dto.item_id)
        if dto.uom_id:
            self._uom_id_edit.setValue(dto.uom_id)
        if dto.min_quantity:
            self._min_qty_spin.setValue(float(dto.min_quantity))
        if dto.unit_price:
            self._unit_price_spin.setValue(float(dto.unit_price))
        if dto.valid_from:
            from PySide6.QtCore import QDate
            self._valid_from_edit.setDate(
                QDate(dto.valid_from.year, dto.valid_from.month, dto.valid_from.day)
            )
        if dto.valid_to:
            from PySide6.QtCore import QDate
            self._valid_to_edit.setDate(
                QDate(dto.valid_to.year, dto.valid_to.month, dto.valid_to.day)
            )

    # ------------------------------------------------------------------
    # Accept
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        item_id = self._item_id_edit.value()
        if item_id < 1:
            show_error(self, "Validation", "Item ID is required.")
            return

        unit_price = Decimal(str(round(self._unit_price_spin.value(), 2)))
        min_qty = Decimal(str(round(self._min_qty_spin.value(), 3)))

        uom_id_raw = self._uom_id_edit.value()
        uom_id = uom_id_raw if uom_id_raw > 0 else None

        # Parse dates — treat minimum dates as None
        from PySide6.QtCore import QDate
        _min_date = QDate(1900, 1, 1)

        vf_qdate = self._valid_from_edit.date()
        valid_from: date | None = None
        if vf_qdate.isValid() and vf_qdate > _min_date:
            valid_from = date(vf_qdate.year(), vf_qdate.month(), vf_qdate.day())

        vt_qdate = self._valid_to_edit.date()
        valid_to: date | None = None
        if vt_qdate.isValid() and vt_qdate > _min_date:
            valid_to = date(vt_qdate.year(), vt_qdate.month(), vt_qdate.day())

        price_list_id = self._original_dto.price_list_id if self._original_dto else 0

        self.result_dto = PriceListLineDTO(
            id=self._original_dto.id if self._original_dto else None,
            price_list_id=price_list_id,
            item_id=item_id,
            uom_id=uom_id,
            valid_from=valid_from,
            valid_to=valid_to,
            unit_price=unit_price,
            min_quantity=min_qty,
        )
        self.accept()
