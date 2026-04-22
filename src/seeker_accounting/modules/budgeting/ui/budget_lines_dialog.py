from __future__ import annotations

import logging

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
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
from seeker_accounting.modules.budgeting.dto.project_budget_commands import (
    AddProjectBudgetLineCommand,
    UpdateProjectBudgetLineCommand,
)
from seeker_accounting.modules.budgeting.dto.project_budget_dto import ProjectBudgetLineDTO
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)


# ── Budget Line Form Dialog ──────────────────────────────────────────────


class BudgetLineFormDialog(BaseDialog):
    """Create or edit a single budget line."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        version_id: int,
        existing_lines: list[ProjectBudgetLineDTO],
        line_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._version_id = version_id
        self._existing_lines = existing_lines
        self._line_id = line_id
        self._saved: ProjectBudgetLineDTO | None = None

        title = "New Budget Line" if line_id is None else "Edit Budget Line"
        super().__init__(title, parent, help_key="dialog.budget_lines")
        self.setObjectName("BudgetLineFormDialog")
        self.resize(620, 560)

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

        # Load reference data for combos
        self._load_reference_data()

        if self._line_id is not None:
            self._load_line()

    @property
    def saved_line(self) -> ProjectBudgetLineDTO | None:
        return self._saved

    @classmethod
    def create_line(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        version_id: int,
        existing_lines: list[ProjectBudgetLineDTO],
        parent: QWidget | None = None,
    ) -> ProjectBudgetLineDTO | None:
        dialog = cls(
            service_registry, company_id, project_id, version_id,
            existing_lines, parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_line
        return None

    @classmethod
    def edit_line(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        version_id: int,
        existing_lines: list[ProjectBudgetLineDTO],
        line_id: int,
        parent: QWidget | None = None,
    ) -> ProjectBudgetLineDTO | None:
        dialog = cls(
            service_registry, company_id, project_id, version_id,
            existing_lines, line_id=line_id, parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_line
        return None

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
        self._line_number_spin.setMaximum(99999)
        next_num = max((l.line_number for l in self._existing_lines), default=0) + 1
        self._line_number_spin.setValue(next_num)
        grid.addWidget(create_field_block("Line #", self._line_number_spin), 0, 0)

        self._job_combo = QComboBox(card)
        self._job_combo.addItem("(No job)", None)
        grid.addWidget(create_field_block("Job", self._job_combo, "Optional"), 0, 1)

        self._cost_code_combo = QComboBox(card)
        grid.addWidget(create_field_block("Cost Code", self._cost_code_combo), 1, 0, 1, 2)

        self._description_edit = QLineEdit(card)
        self._description_edit.setPlaceholderText("Line description (optional)")
        grid.addWidget(create_field_block("Description", self._description_edit), 2, 0, 1, 2)

        self._quantity_edit = QLineEdit(card)
        self._quantity_edit.setPlaceholderText("0.0000")
        grid.addWidget(create_field_block("Quantity", self._quantity_edit, "Optional"), 3, 0)

        self._unit_rate_edit = QLineEdit(card)
        self._unit_rate_edit.setPlaceholderText("0.0000")
        grid.addWidget(create_field_block("Unit Rate", self._unit_rate_edit, "Optional"), 3, 1)

        self._amount_edit = QLineEdit(card)
        self._amount_edit.setPlaceholderText("0.00")
        grid.addWidget(create_field_block("Line Amount", self._amount_edit), 4, 0)

        # Dates row
        self._start_date_edit = QDateEdit(card)
        self._start_date_edit.setCalendarPopup(True)
        self._start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._start_date_edit.setDate(date.today())
        self._start_date_edit.setSpecialValueText(" ")
        grid.addWidget(create_field_block("Start Date", self._start_date_edit, "Optional"), 4, 1)

        self._end_date_edit = QDateEdit(card)
        self._end_date_edit.setCalendarPopup(True)
        self._end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._end_date_edit.setDate(date.today())
        self._end_date_edit.setSpecialValueText(" ")
        grid.addWidget(create_field_block("End Date", self._end_date_edit, "Optional"), 5, 0)

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
    # Reference data
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        # Load jobs for the project
        try:
            jobs = self._service_registry.project_structure_service.list_jobs(self._project_id)
            for j in jobs:
                self._job_combo.addItem(f"{j.job_code} — {j.job_name}", j.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        # Load cost codes for the company
        try:
            cost_codes = self._service_registry.project_cost_code_service.list_cost_codes(
                self._company_id
            )
            for cc in cost_codes:
                self._cost_code_combo.addItem(f"{cc.code} — {cc.name}", cc.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_line(self) -> None:
        line = None
        for l in self._existing_lines:
            if l.id == self._line_id:
                line = l
                break
        if line is None:
            show_error(self, "Not Found", "Budget line not found.")
            self.reject()
            return

        self._line_number_spin.setValue(line.line_number)

        if line.project_job_id is not None:
            idx = self._job_combo.findData(line.project_job_id)
            if idx >= 0:
                self._job_combo.setCurrentIndex(idx)

        cc_idx = self._cost_code_combo.findData(line.project_cost_code_id)
        if cc_idx >= 0:
            self._cost_code_combo.setCurrentIndex(cc_idx)

        self._description_edit.setText(line.description or "")

        if line.quantity is not None:
            self._quantity_edit.setText(str(line.quantity))
        if line.unit_rate is not None:
            self._unit_rate_edit.setText(str(line.unit_rate))
        self._amount_edit.setText(str(line.line_amount))

        if line.start_date:
            self._start_date_edit.setDate(line.start_date)
        if line.end_date:
            self._end_date_edit.setDate(line.end_date)

        self._notes_edit.setPlainText(line.notes or "")

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

    def _parse_decimal(self, text: str) -> Decimal | None:
        text = text.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._set_error(None)

        cost_code_id = self._cost_code_combo.currentData()
        if cost_code_id is None:
            self._set_error("Cost code is required.")
            return

        amount_text = self._amount_edit.text().strip()
        if not amount_text:
            self._set_error("Line amount is required.")
            return
        line_amount = self._parse_decimal(amount_text)
        if line_amount is None:
            self._set_error("Line amount must be a valid number.")
            return

        quantity = self._parse_decimal(self._quantity_edit.text())
        unit_rate = self._parse_decimal(self._unit_rate_edit.text())
        job_id = self._job_combo.currentData()
        description = self._description_edit.text().strip() or None
        notes = self._notes_edit.toPlainText().strip() or None
        line_number = self._line_number_spin.value()
        start = self._start_date_edit.date().toPython()
        end = self._end_date_edit.date().toPython()

        svc = self._service_registry.project_budget_service

        try:
            if self._line_id is None:
                result = svc.add_line(
                    AddProjectBudgetLineCommand(
                        project_budget_version_id=self._version_id,
                        line_number=line_number,
                        project_cost_code_id=cost_code_id,
                        line_amount=line_amount,
                        project_job_id=job_id,
                        description=description,
                        quantity=quantity,
                        unit_rate=unit_rate,
                        start_date=start,
                        end_date=end,
                        notes=notes,
                    )
                )
            else:
                result = svc.update_line(
                    self._line_id,
                    UpdateProjectBudgetLineCommand(
                        line_number=line_number,
                        project_cost_code_id=cost_code_id,
                        line_amount=line_amount,
                        project_job_id=job_id,
                        description=description,
                        quantity=quantity,
                        unit_rate=unit_rate,
                        start_date=start,
                        end_date=end,
                        notes=notes,
                    ),
                )
            self._saved = result
            self.accept()
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))


# ── Budget Lines List Dialog ─────────────────────────────────────────────


class BudgetLinesDialog(BaseDialog):
    """List and manage budget lines for a specific version."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        version_id: int,
        version_name: str,
        version_status: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Budget Lines — {version_name}", parent, help_key="dialog.budget_lines_list")
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._version_id = version_id
        self._version_status = version_status
        self._lines: list[ProjectBudgetLineDTO] = []

        self.setObjectName("BudgetLinesDialog")
        self.resize(980, 580)

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
        version_id: int,
        version_name: str,
        version_status: str,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(
            service_registry, company_id, project_id, version_id,
            version_name, version_status, parent=parent,
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

        is_editable = self._version_status in ("draft", "submitted")

        self._add_button = QPushButton("Add Line", toolbar)
        self._add_button.setProperty("variant", "primary")
        self._add_button.setEnabled(is_editable)
        self._add_button.clicked.connect(self._add_line)
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
        self._total_label.setObjectName("ToolbarValue")
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
        self._table.setObjectName("BudgetLinesTable")
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ("Line #", "Job", "Cost Code", "Description", "Qty", "Rate", "Amount", "Dates")
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
            self._lines = self._service_registry.project_budget_service.list_lines(
                self._version_id
            )
        except Exception as exc:
            show_error(self, "Budget Lines", str(exc))
            self._lines = []

        self._populate_table()
        self._update_action_state()

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        total = Decimal("0")
        for line in self._lines:
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(str(line.line_number))
            num_item.setData(Qt.ItemDataRole.UserRole, line.id)
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, num_item)

            self._table.setItem(row, 1, QTableWidgetItem(line.project_job_code or ""))
            self._table.setItem(row, 2, QTableWidgetItem(line.project_cost_code_name or ""))
            self._table.setItem(row, 3, QTableWidgetItem(line.description or ""))

            qty_item = QTableWidgetItem(str(line.quantity) if line.quantity is not None else "")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, qty_item)

            rate_item = QTableWidgetItem(str(line.unit_rate) if line.unit_rate is not None else "")
            rate_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 5, rate_item)

            amount_item = QTableWidgetItem(f"{line.line_amount:,.2f}")
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 6, amount_item)

            date_parts = []
            if line.start_date:
                date_parts.append(str(line.start_date))
            if line.end_date:
                date_parts.append(str(line.end_date))
            self._table.setItem(row, 7, QTableWidgetItem(" → ".join(date_parts)))

            total += line.line_amount

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.Stretch)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._lines)
        self._count_label.setText(f"{count} line" if count == 1 else f"{count} lines")
        self._total_label.setText(f"Total: {total:,.2f}")

    def _selected_line(self) -> ProjectBudgetLineDTO | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        line_id = item.data(Qt.ItemDataRole.UserRole)
        for line in self._lines:
            if line.id == line_id:
                return line
        return None

    def _update_action_state(self) -> None:
        is_editable = self._version_status in ("draft", "submitted")
        selected = self._selected_line()
        self._edit_button.setEnabled(selected is not None and is_editable)
        self._delete_button.setEnabled(selected is not None and is_editable)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add_line(self) -> None:
        result = BudgetLineFormDialog.create_line(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            version_id=self._version_id,
            existing_lines=self._lines,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _edit_line(self) -> None:
        selected = self._selected_line()
        if selected is None or self._version_status not in ("draft", "submitted"):
            return
        result = BudgetLineFormDialog.edit_line(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            version_id=self._version_id,
            existing_lines=self._lines,
            line_id=selected.id,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _delete_line(self) -> None:
        selected = self._selected_line()
        if selected is None or self._version_status not in ("draft", "submitted"):
            return
        choice = QMessageBox.question(
            self,
            "Delete Budget Line",
            f"Delete line #{selected.line_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.project_budget_service.delete_line(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Budget Lines", str(exc))
        self._reload()
