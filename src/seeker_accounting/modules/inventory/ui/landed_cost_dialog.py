"""Landed Cost Dialog — create and post a landed cost voucher."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
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
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.components.confirm_dialog import confirm
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


class LandedCostDialog(QDialog):
    """Create a landed cost voucher and optionally post it."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        voucher_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._voucher_id = voucher_id

        self.setWindowTitle("Landed Cost Voucher")
        self.setModal(True)
        self.setMinimumWidth(680)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addWidget(self._build_header_form())
        root.addWidget(QLabel("Receipts (GRN documents to allocate cost to):", self))
        root.addWidget(self._build_receipts_panel())
        root.addWidget(self._build_buttons())

        if voucher_id is not None:
            self._load()

    # ------------------------------------------------------------------
    def _build_header_form(self) -> QWidget:
        frame = QFrame(self)
        form = QFormLayout(frame)
        form.setContentsMargins(0, 0, 0, 0)

        self._number_edit = QLineEdit(frame)
        self._number_edit.setPlaceholderText("Auto-assigned on save")
        self._number_edit.setReadOnly(True)

        self._voucher_date = QDateEdit(frame)
        self._voucher_date.setDate(QDate.currentDate())
        self._voucher_date.setCalendarPopup(True)

        self._desc_edit = QLineEdit(frame)
        self._desc_edit.setPlaceholderText("e.g. Import costs Dec 2024")

        self._total_edit = QLineEdit(frame)
        self._total_edit.setPlaceholderText("0.00")

        self._basis_combo = QComboBox(frame)
        for code, label in [
            ("by_value", "By Value"),
            ("by_qty", "By Quantity"),
            ("by_weight", "By Weight"),
            ("manual", "Manual"),
        ]:
            self._basis_combo.addItem(label, code)

        form.addRow("Voucher #", self._number_edit)
        form.addRow("Date *", self._voucher_date)
        form.addRow("Description", self._desc_edit)
        form.addRow("Total Landed Cost *", self._total_edit)
        form.addRow("Allocation Basis", self._basis_combo)
        return frame

    def _build_receipts_panel(self) -> QWidget:
        frame = QFrame(self)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        add_row = QHBoxLayout()
        self._receipt_doc_edit = QLineEdit(frame)
        self._receipt_doc_edit.setPlaceholderText("GRN Document ID")
        self._receipt_doc_edit.setMaximumWidth(160)
        add_btn = QPushButton("Add Receipt", frame)
        add_btn.setFixedHeight(26)
        add_btn.clicked.connect(self._on_add_receipt)
        add_row.addWidget(self._receipt_doc_edit)
        add_row.addWidget(add_btn)
        add_row.addStretch()
        lay.addLayout(add_row)

        self._receipts_table = QTableWidget(0, 3, frame)
        self._receipts_table.setHorizontalHeaderLabels(["Doc ID", "Document Number", "Remove"])
        self._receipts_table.horizontalHeader().setSectionResizeMode(
            1, self._receipts_table.horizontalHeader().ResizeMode.Stretch
        )
        self._receipts_table.verticalHeader().setVisible(False)
        self._receipts_table.setFixedHeight(150)
        lay.addWidget(self._receipts_table)
        self._receipt_doc_ids: list[int] = []
        return frame

    def _build_buttons(self) -> QWidget:
        frame = QFrame(self)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(8)
        save_btn = QPushButton("Save Draft", frame)
        save_btn.setFixedHeight(28)
        save_btn.clicked.connect(self._save)
        post_btn = QPushButton("Save & Post", frame)
        post_btn.setFixedHeight(28)
        post_btn.clicked.connect(self._save_and_post)
        cancel_btn = QPushButton("Cancel", frame)
        cancel_btn.setFixedHeight(28)
        cancel_btn.clicked.connect(self.reject)
        lay.addStretch()
        lay.addWidget(cancel_btn)
        lay.addWidget(save_btn)
        lay.addWidget(post_btn)
        return frame

    # ------------------------------------------------------------------
    def _on_add_receipt(self) -> None:
        text = self._receipt_doc_edit.text().strip()
        if not text:
            return
        try:
            doc_id = int(text)
        except ValueError:
            show_error(self, "Add Receipt", "Enter a valid document ID.")
            return
        if doc_id in self._receipt_doc_ids:
            return
        self._receipt_doc_ids.append(doc_id)
        row = self._receipts_table.rowCount()
        self._receipts_table.insertRow(row)
        self._receipts_table.setItem(row, 0, QTableWidgetItem(str(doc_id)))
        self._receipts_table.setItem(row, 1, QTableWidgetItem(f"Document #{doc_id}"))
        del_btn = QPushButton("×", self._receipts_table)
        del_btn.setFixedSize(22, 22)
        del_btn.clicked.connect(lambda _, d=doc_id: self._remove_receipt(d))
        self._receipts_table.setCellWidget(row, 2, del_btn)
        self._receipt_doc_edit.clear()

    def _remove_receipt(self, doc_id: int) -> None:
        if doc_id in self._receipt_doc_ids:
            idx = self._receipt_doc_ids.index(doc_id)
            self._receipt_doc_ids.pop(idx)
            self._receipts_table.removeRow(idx)

    def _load(self) -> None:
        svc = self._service_registry.landed_cost_service
        try:
            voucher = svc.get(self._voucher_id)
            if voucher is None:
                return
            if hasattr(voucher, "voucher_number") and voucher.voucher_number:
                self._number_edit.setText(voucher.voucher_number)
            self._desc_edit.setText(voucher.description or "")
            self._total_edit.setText(str(voucher.total_landed_cost))
        except Exception as exc:
            show_error(self, "Load", str(exc))

    def _save(self) -> bool:
        total_text = self._total_edit.text().strip()
        try:
            total = Decimal(total_text)
        except InvalidOperation:
            show_error(self, "Validation", "Total landed cost must be a valid number.")
            return False

        from seeker_accounting.modules.inventory.services.landed_cost_service import CreateLandedCostCommand
        qd = self._voucher_date.date()
        cmd = CreateLandedCostCommand(
            company_id=self._company_id,
            voucher_date=date(qd.year(), qd.month(), qd.day()),
            description=self._desc_edit.text().strip() or None,
            total_landed_cost=total,
            allocation_basis_code=self._basis_combo.currentData(),
            inventory_document_ids=list(self._receipt_doc_ids),
        )
        svc = self._service_registry.landed_cost_service
        try:
            self._voucher_id = svc.create(cmd)
            show_info(self, "Saved", f"Landed cost voucher saved (ID {self._voucher_id}).")
            return True
        except Exception as exc:
            show_error(self, "Save", str(exc))
            return False

    def _save_and_post(self) -> None:
        if not self._save():
            return
        if not confirm(
            parent=self, title="Post", message="Post this landed cost voucher now? This will create journal entries."
        ):
            return
        svc = self._service_registry.landed_cost_service
        try:
            # fiscal_period_id and account will be resolved by service defaults
            # For a production UI we would provide selectors; this is a minimal first pass
            svc.post(
                company_id=self._company_id,
                voucher_id=self._voucher_id,
                fiscal_period_id=None,
                landed_cost_account_id=None,
                actor_user_id=None,
            )
            show_info(self, "Posted", "Landed cost voucher posted.")
            self.accept()
        except Exception as exc:
            show_error(self, "Post", str(exc))
