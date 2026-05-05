"""Price List Dialog — create or edit a price list with lines grid."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.inventory.services.price_list_service import PriceListDTO, PriceListLineDTO
from seeker_accounting.shared.ui.message_boxes import show_error


class PriceListDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        price_list_id: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._price_list_id = price_list_id
        self._line_rows: list[PriceListLineDTO] = []

        self.setWindowTitle("New Price List" if price_list_id is None else "Edit Price List")
        self.setMinimumWidth(680)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        root.addWidget(self._build_header_form())
        root.addWidget(QLabel("Lines:", self))
        root.addWidget(self._build_lines_grid())
        root.addLayout(self._build_line_actions())
        root.addWidget(self._build_buttons())

        if price_list_id is not None:
            self._load()

    # ------------------------------------------------------------------
    def _build_header_form(self) -> QWidget:
        frame = QFrame(self)
        form = QFormLayout(frame)
        form.setContentsMargins(0, 0, 0, 0)

        self._name_edit = QLineEdit(frame)
        self._currency_edit = QLineEdit(frame)
        self._currency_edit.setPlaceholderText("e.g. XAF")
        self._currency_edit.setMaximumWidth(100)
        self._default_cb = QCheckBox("Is Default", frame)
        self._active_cb = QCheckBox("Active", frame)
        self._active_cb.setChecked(True)

        form.addRow("Name *", self._name_edit)
        form.addRow("Currency", self._currency_edit)
        form.addRow("", self._default_cb)
        form.addRow("", self._active_cb)
        return frame

    def _build_lines_grid(self) -> QTableWidget:
        self._lines_table = QTableWidget(0, 4, self)
        self._lines_table.setHorizontalHeaderLabels(["Item", "Min Qty", "Unit Price", "Valid Until"])
        self._lines_table.horizontalHeader().setSectionResizeMode(0, self._lines_table.horizontalHeader().ResizeMode.Stretch)
        self._lines_table.verticalHeader().setVisible(False)
        self._lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._lines_table.setAlternatingRowColors(True)
        self._lines_table.setMinimumHeight(200)
        return self._lines_table

    def _build_line_actions(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(6)
        add_btn = QPushButton("Add Line", self)
        add_btn.setFixedHeight(26)
        add_btn.clicked.connect(self._on_add_line)
        del_btn = QPushButton("Remove Line", self)
        del_btn.setFixedHeight(26)
        del_btn.clicked.connect(self._on_remove_line)
        lay.addWidget(add_btn)
        lay.addWidget(del_btn)
        lay.addStretch()
        return lay

    def _build_buttons(self) -> QDialogButtonBox:
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        return btns

    # ------------------------------------------------------------------
    def _load(self) -> None:
        svc = self._service_registry.price_list_service
        try:
            pl = svc.get(self._price_list_id)
            if pl is None:
                return
            self._name_edit.setText(pl.price_list_name)
            self._currency_edit.setText(pl.currency_code or "")
            self._default_cb.setChecked(pl.is_default)
            self._active_cb.setChecked(pl.is_active)
            self._line_rows = list(pl.lines) if hasattr(pl, "lines") else []
            self._populate_lines()
        except Exception as exc:
            show_error(self, "Load Price List", str(exc))

    def _populate_lines(self) -> None:
        self._lines_table.setRowCount(len(self._line_rows))
        for r, line in enumerate(self._line_rows):
            self._lines_table.setItem(r, 0, QTableWidgetItem(str(line.item_id)))
            self._lines_table.setItem(r, 1, QTableWidgetItem(str(line.min_quantity or "")))
            self._lines_table.setItem(r, 2, QTableWidgetItem(str(line.unit_price)))
            self._lines_table.setItem(r, 3, QTableWidgetItem(str(line.valid_until or "")))

    def _on_add_line(self) -> None:
        from seeker_accounting.modules.inventory.ui._price_list_line_edit_dialog import (
            PriceListLineEditDialog,
        )
        dlg = PriceListLineEditDialog(self._service_registry, self._company_id, None, self)
        if dlg.exec():
            self._line_rows.append(dlg.result_dto)
            self._populate_lines()

    def _on_remove_line(self) -> None:
        row = self._lines_table.currentRow()
        if 0 <= row < len(self._line_rows):
            self._line_rows.pop(row)
            self._populate_lines()

    def _save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            show_error(self, "Validation", "Name is required.")
            return
        svc = self._service_registry.price_list_service
        dto = PriceListDTO(
            id=self._price_list_id,
            company_id=self._company_id,
            name=name,
            currency_code=self._currency_edit.text().strip() or "XAF",
            valid_from=None,
            valid_to=None,
            description=None,
            is_default=self._default_cb.isChecked(),
            is_active=self._active_cb.isChecked(),
        )
        try:
            pl_id = svc.save(dto)
            # Save lines
            for line in self._line_rows:
                line_dto = PriceListLineDTO(
                    id=line.id,
                    price_list_id=pl_id,
                    item_id=line.item_id,
                    uom_id=line.uom_id,
                    min_quantity=line.min_quantity,
                    unit_price=line.unit_price,
                    valid_from=line.valid_from,
                    valid_to=line.valid_to,
                )
                svc.save_line(line_dto)
            self.accept()
        except Exception as exc:
            show_error(self, "Save", str(exc))
