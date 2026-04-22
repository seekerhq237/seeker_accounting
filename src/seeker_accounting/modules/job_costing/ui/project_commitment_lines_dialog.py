from __future__ import annotations

import logging

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.job_costing.dto.project_commitment_commands import (
    AddProjectCommitmentLineCommand,
    UpdateProjectCommitmentLineCommand,
)
from seeker_accounting.modules.job_costing.dto.project_commitment_dto import ProjectCommitmentLineDTO
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)


# ── Commitment Line Form Dialog ──────────────────────────────────────────


class CommitmentLineFormDialog(BaseDialog):
    """Create or edit a single commitment line."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        commitment_id: int,
        existing_lines: list[ProjectCommitmentLineDTO],
        line_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._commitment_id = commitment_id
        self._existing_lines = existing_lines
        self._line_id = line_id
        self._saved = False

        title = "New Commitment Line" if line_id is None else "Edit Commitment Line"
        super().__init__(title, parent, help_key="dialog.project_commitment_line")
        self.setObjectName("CommitmentLineFormDialog")
        self.resize(620, 520)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_form_section())
        self.body_layout.addWidget(self._build_notes_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        save_btn = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setText("Add" if line_id is None else "Save Changes")
            save_btn.setProperty("variant", "primary")

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")

        self._load_reference_data()

        if self._line_id is not None:
            self._load_line()

    @property
    def was_saved(self) -> bool:
        return self._saved

    @classmethod
    def create_line(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        commitment_id: int,
        existing_lines: list[ProjectCommitmentLineDTO],
        parent: QWidget | None = None,
    ) -> bool:
        dialog = cls(service_registry, company_id, project_id, commitment_id, existing_lines, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.was_saved
        return False

    @classmethod
    def edit_line(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        commitment_id: int,
        existing_lines: list[ProjectCommitmentLineDTO],
        line_id: int,
        parent: QWidget | None = None,
    ) -> bool:
        dialog = cls(
            service_registry, company_id, project_id, commitment_id,
            existing_lines, line_id=line_id, parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.was_saved
        return False

    # ------------------------------------------------------------------
    # Form sections
    # ------------------------------------------------------------------

    def _build_form_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Line Details", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._line_number_spin = QSpinBox(card)
        self._line_number_spin.setMinimum(1)
        self._line_number_spin.setMaximum(9999)
        next_num = max((ln.line_number for ln in self._existing_lines), default=0) + 1
        self._line_number_spin.setValue(next_num)
        grid.addWidget(create_field_block("Line Number", self._line_number_spin), 0, 0)

        self._cost_code_combo = QComboBox(card)
        grid.addWidget(create_field_block("Cost Code", self._cost_code_combo), 0, 1)

        self._job_combo = QComboBox(card)
        grid.addWidget(create_field_block("Job", self._job_combo, "Optional"), 1, 0)

        self._description_edit = QLineEdit(card)
        self._description_edit.setPlaceholderText("Optional description")
        grid.addWidget(create_field_block("Description", self._description_edit, "Optional"), 1, 1)

        self._quantity_edit = QLineEdit(card)
        self._quantity_edit.setPlaceholderText("Optional")
        grid.addWidget(create_field_block("Quantity", self._quantity_edit, "Optional"), 2, 0)

        self._unit_rate_edit = QLineEdit(card)
        self._unit_rate_edit.setPlaceholderText("Optional")
        grid.addWidget(create_field_block("Unit Rate", self._unit_rate_edit, "Optional"), 2, 1)

        self._amount_edit = QLineEdit(card)
        self._amount_edit.setPlaceholderText("0.00")
        grid.addWidget(create_field_block("Line Amount", self._amount_edit), 3, 0)

        layout.addLayout(grid)
        return card

    def _build_notes_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Notes", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setPlaceholderText("Optional notes")
        self._notes_edit.setFixedHeight(60)
        layout.addWidget(self._notes_edit)
        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        # Cost codes
        self._cost_code_combo.clear()
        try:
            cost_codes = self._service_registry.project_cost_code_service.list_cost_codes(
                self._company_id, active_only=True
            )
            for cc in cost_codes:
                self._cost_code_combo.addItem(f"{cc.code} — {cc.name}", cc.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        # Jobs
        self._job_combo.clear()
        self._job_combo.addItem("(None)", None)
        try:
            jobs = self._service_registry.project_structure_service.list_jobs(self._project_id)
            for j in jobs:
                self._job_combo.addItem(f"{j.job_code} — {j.job_name}", j.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_line(self) -> None:
        line_dto: ProjectCommitmentLineDTO | None = None
        for ln in self._existing_lines:
            if ln.id == self._line_id:
                line_dto = ln
                break
        if line_dto is None:
            show_error(self, "Not Found", "Commitment line not found.")
            self.reject()
            return

        self._line_number_spin.setValue(line_dto.line_number)

        idx = self._cost_code_combo.findData(line_dto.project_cost_code_id)
        if idx >= 0:
            self._cost_code_combo.setCurrentIndex(idx)

        if line_dto.project_job_id is not None:
            jidx = self._job_combo.findData(line_dto.project_job_id)
            if jidx >= 0:
                self._job_combo.setCurrentIndex(jidx)

        self._description_edit.setText(line_dto.description or "")
        if line_dto.quantity is not None:
            self._quantity_edit.setText(str(line_dto.quantity))
        if line_dto.unit_rate is not None:
            self._unit_rate_edit.setText(str(line_dto.unit_rate))
        self._amount_edit.setText(str(line_dto.line_amount))
        self._notes_edit.setPlainText(line_dto.notes or "")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._set_error(None)

        line_number = self._line_number_spin.value()
        cost_code_id = self._cost_code_combo.currentData()
        if cost_code_id is None:
            self._set_error("Cost code is required.")
            return

        job_id = self._job_combo.currentData()
        description = self._description_edit.text().strip() or None

        quantity: Decimal | None = None
        qty_text = self._quantity_edit.text().strip()
        if qty_text:
            try:
                quantity = Decimal(qty_text)
            except InvalidOperation:
                self._set_error("Quantity must be a valid number.")
                return

        unit_rate: Decimal | None = None
        rate_text = self._unit_rate_edit.text().strip()
        if rate_text:
            try:
                unit_rate = Decimal(rate_text)
            except InvalidOperation:
                self._set_error("Unit rate must be a valid number.")
                return

        amount_text = self._amount_edit.text().strip()
        if not amount_text:
            self._set_error("Line amount is required.")
            return
        try:
            line_amount = Decimal(amount_text)
        except InvalidOperation:
            self._set_error("Line amount must be a valid number.")
            return

        notes = self._notes_edit.toPlainText().strip() or None

        svc = self._service_registry.project_commitment_service

        try:
            if self._line_id is None:
                svc.add_line(
                    AddProjectCommitmentLineCommand(
                        project_commitment_id=self._commitment_id,
                        line_number=line_number,
                        project_cost_code_id=cost_code_id,
                        line_amount=line_amount,
                        project_job_id=job_id,
                        description=description,
                        quantity=quantity,
                        unit_rate=unit_rate,
                        notes=notes,
                    )
                )
            else:
                svc.update_line(
                    self._line_id,
                    UpdateProjectCommitmentLineCommand(
                        line_number=line_number,
                        project_cost_code_id=cost_code_id,
                        line_amount=line_amount,
                        project_job_id=job_id,
                        description=description,
                        quantity=quantity,
                        unit_rate=unit_rate,
                        notes=notes,
                    ),
                )
            self._saved = True
            self.accept()
        except (ValidationError, NotFoundError, ConflictError) as exc:
            self._set_error(str(exc))


# ── Commitment Lines List Dialog ─────────────────────────────────────────


class ProjectCommitmentLinesDialog(BaseDialog):
    """List and manage commitment lines."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        commitment_id: int,
        commitment_number: str,
        commitment_status: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Commitment Lines — {commitment_number}", parent, help_key="dialog.project_commitment_lines_list")
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._commitment_id = commitment_id
        self._commitment_number = commitment_number
        self._commitment_status = commitment_status
        self._lines: list[ProjectCommitmentLineDTO] = []

        self.setObjectName("ProjectCommitmentLinesDialog")
        self.resize(940, 500)

        self.body_layout.addWidget(self._build_toolbar())
        self.body_layout.addWidget(self._build_table_card(), 1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        close_btn = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setProperty("variant", "secondary")

        self._reload()

    @classmethod
    def manage_lines(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        commitment_id: int,
        commitment_number: str,
        commitment_status: str,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(
            service_registry, company_id, project_id,
            commitment_id, commitment_number, commitment_status,
            parent=parent,
        )
        dialog.exec()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget(self)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        is_draft = self._commitment_status == "draft"

        self._add_button = QPushButton("Add Line", toolbar)
        self._add_button.setProperty("variant", "primary")
        self._add_button.clicked.connect(self._add_line)
        self._add_button.setEnabled(is_draft)
        layout.addWidget(self._add_button)

        self._edit_button = QPushButton("Edit", toolbar)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._edit_line)
        layout.addWidget(self._edit_button)

        self._delete_button = QPushButton("Delete", toolbar)
        self._delete_button.setProperty("variant", "secondary")
        self._delete_button.clicked.connect(self._delete_line)
        layout.addWidget(self._delete_button)

        layout.addStretch(1)

        self._total_label = QLabel(toolbar)
        self._total_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._total_label)

        self._count_label = QLabel(toolbar)
        self._count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._count_label)

        return toolbar

    def _build_table_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        self._table = QTableWidget(card)
        self._table.setObjectName("CommitmentLinesTable")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ("#", "Cost Code", "Job", "Description", "Qty", "Unit Rate", "Amount")
        )
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(lambda *_: self._edit_line())
        layout.addWidget(self._table)
        return card

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _reload(self) -> None:
        try:
            detail = self._service_registry.project_commitment_service.get_commitment_detail(
                self._commitment_id, self._company_id
            )
            self._lines = detail.lines
            self._commitment_status = detail.status_code
        except Exception as exc:
            show_error(self, "Commitment Lines", str(exc))
            self._lines = []

        self._populate_table()
        self._update_action_state()

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        total = Decimal("0.00")
        for ln in self._lines:
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(str(ln.line_number))
            num_item.setData(Qt.ItemDataRole.UserRole, ln.id)
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, num_item)

            self._table.setItem(row, 1, QTableWidgetItem(ln.cost_code_name))
            self._table.setItem(row, 2, QTableWidgetItem(ln.job_name or ""))
            self._table.setItem(row, 3, QTableWidgetItem(ln.description or ""))

            qty_item = QTableWidgetItem(str(ln.quantity) if ln.quantity is not None else "")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, qty_item)

            rate_item = QTableWidgetItem(str(ln.unit_rate) if ln.unit_rate is not None else "")
            rate_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 5, rate_item)

            amount_item = QTableWidgetItem(f"{ln.line_amount:,.2f}")
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 6, amount_item)

            total += ln.line_amount

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.Stretch)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._lines)
        self._count_label.setText(f"{count} line" if count == 1 else f"{count} lines")
        self._total_label.setText(f"Total: {total:,.2f}  ")

    def _selected_line(self) -> ProjectCommitmentLineDTO | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        line_id = item.data(Qt.ItemDataRole.UserRole)
        for ln in self._lines:
            if ln.id == line_id:
                return ln
        return None

    def _update_action_state(self) -> None:
        selected = self._selected_line()
        has_selection = selected is not None
        is_draft = self._commitment_status == "draft"

        self._add_button.setEnabled(is_draft)
        self._edit_button.setEnabled(has_selection and is_draft)
        self._delete_button.setEnabled(has_selection and is_draft)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add_line(self) -> None:
        if self._commitment_status != "draft":
            return
        result = CommitmentLineFormDialog.create_line(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            commitment_id=self._commitment_id,
            existing_lines=self._lines,
            parent=self,
        )
        if result:
            self._reload()

    def _edit_line(self) -> None:
        selected = self._selected_line()
        if selected is None or self._commitment_status != "draft":
            return
        result = CommitmentLineFormDialog.edit_line(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            commitment_id=self._commitment_id,
            existing_lines=self._lines,
            line_id=selected.id,
            parent=self,
        )
        if result:
            self._reload()

    def _delete_line(self) -> None:
        selected = self._selected_line()
        if selected is None or self._commitment_status != "draft":
            return

        choice = QMessageBox.question(
            self,
            "Delete Line",
            f"Delete line #{selected.line_number}?\n\nThis cannot be undone.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.project_commitment_service.remove_line(selected.id)
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Delete Failed", str(exc))
        self._reload()
