from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
from seeker_accounting.modules.payroll.dto.payroll_project_allocation_commands import (
    PayrollProjectAllocationLineCommand,
    ReplacePayrollProjectAllocationsCommand,
)
from seeker_accounting.modules.payroll.dto.payroll_project_allocation_dto import (
    PayrollProjectAllocationSetDTO,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_MONEY_SCALE = Decimal("0.0001")


class PayrollProjectAllocationsDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        payroll_run_employee_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._payroll_run_employee_id = payroll_run_employee_id
        self._allocation_set: PayrollProjectAllocationSetDTO | None = None
        self._projects: list[object] = []
        self._contracts: list[object] = []
        self._cost_codes: list[object] = []
        self._jobs_by_project_id: dict[int, list[object]] = {}

        self.setModal(True)
        self.resize(1180, 680)
        self.setWindowTitle("Payroll Project Allocations")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)

        layout.addWidget(self._build_summary_section())
        layout.addWidget(self._build_lines_section(), 1)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close,
            self,
        )
        self._button_box.accepted.connect(self._handle_submit)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_project_allocations", dialog=True)

        self._load_reference_data()
        self._load_allocations()

    def _build_summary_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self._header_label = QLabel(card)
        self._header_label.setObjectName("DialogSectionTitle")
        layout.addWidget(self._header_label)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(18)

        self._basis_combo = QComboBox(card)
        self._basis_combo.addItem("Percent", "percent")
        self._basis_combo.addItem("Amount", "amount")
        self._basis_combo.addItem("Hours", "hours")
        self._basis_combo.currentIndexChanged.connect(self._refresh_preview)
        meta_row.addWidget(QLabel("Allocation Basis", card))
        meta_row.addWidget(self._basis_combo)

        meta_row.addStretch(1)

        self._base_amount_label = QLabel("Base: 0.0000", card)
        self._allocated_total_label = QLabel("Allocated: 0.0000", card)
        self._remaining_label = QLabel("Remaining: 0.0000", card)
        self._editable_label = QLabel(card)
        for widget in (
            self._base_amount_label,
            self._allocated_total_label,
            self._remaining_label,
            self._editable_label,
        ):
            meta_row.addWidget(widget)

        layout.addLayout(meta_row)

        hint = QLabel(
            "Slice 15.6 allocates payroll labour cost against employer cost. For percent and hours, allocated amounts are previewed and finalized in the service.",
            card,
        )
        hint.setObjectName("ToolbarMeta")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    def _build_lines_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        self._add_line_button = QPushButton("Add Allocation", card)
        self._add_line_button.clicked.connect(self._add_line)
        toolbar.addWidget(self._add_line_button)

        self._remove_line_button = QPushButton("Remove Allocation", card)
        self._remove_line_button.clicked.connect(self._remove_selected_line)
        toolbar.addWidget(self._remove_line_button)

        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._table = QTableWidget(card)
        configure_compact_table(self._table)
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ["Project", "Contract", "Job", "Cost Code", "Quantity", "Percent", "Amount", "Notes"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemChanged.connect(self._refresh_preview)
        layout.addWidget(self._table, 1)
        return card

    def _load_reference_data(self) -> None:
        try:
            self._projects = self._registry.project_service.list_projects(self._company_id)
        except Exception:
            self._projects = []

        try:
            self._contracts = self._registry.contract_service.list_contracts(self._company_id)
        except Exception:
            self._contracts = []

        try:
            self._cost_codes = self._registry.project_cost_code_service.list_cost_codes(self._company_id)
        except Exception:
            self._cost_codes = []

        self._jobs_by_project_id = {}
        for project in self._projects:
            try:
                self._jobs_by_project_id[project.id] = self._registry.project_structure_service.list_jobs(project.id)
            except Exception:
                self._jobs_by_project_id[project.id] = []

    def _load_allocations(self) -> None:
        try:
            allocation_set = self._registry.payroll_project_allocation_service.get_allocation_set(
                self._company_id,
                self._payroll_run_employee_id,
            )
        except Exception as exc:
            show_error(self, "Project Allocations", str(exc))
            self.reject()
            return

        self._allocation_set = allocation_set
        self.setWindowTitle(f"Project Allocations — {allocation_set.employee_display_name}")
        self._header_label.setText(
            f"{allocation_set.employee_number}  ·  {allocation_set.employee_display_name}  ·  Run {allocation_set.run_reference}"
        )
        self._base_amount_label.setText(f"Base: {allocation_set.allocation_base_amount:,.4f}")
        self._editable_label.setText("Editable" if allocation_set.editable else "Read-only")

        basis_code = allocation_set.lines[0].allocation_basis_code if allocation_set.lines else "amount"
        basis_index = self._basis_combo.findData(basis_code)
        self._basis_combo.setCurrentIndex(basis_index if basis_index >= 0 else 1)

        self._table.blockSignals(True)
        self._table.setRowCount(0)
        if allocation_set.lines:
            for line in allocation_set.lines:
                self._add_line(line, refresh=False)
        elif allocation_set.editable:
            self._add_line(refresh=False)
        self._table.blockSignals(False)
        self._apply_editable_state()
        self._refresh_preview()

    def _apply_editable_state(self) -> None:
        editable = self._allocation_set.editable if self._allocation_set is not None else False
        self._basis_combo.setEnabled(editable)
        self._add_line_button.setEnabled(editable)
        self._remove_line_button.setEnabled(editable)
        save_button = self._button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setVisible(editable)
        for row in range(self._table.rowCount()):
            for col in range(4):
                widget = self._table.cellWidget(row, col)
                if widget is not None:
                    widget.setEnabled(editable)
            for col in range(4, 8):
                item = self._table.item(row, col)
                if item is not None:
                    flags = item.flags()
                    if editable:
                        item.setFlags(flags | Qt.ItemFlag.ItemIsEditable)
                    else:
                        item.setFlags(flags & ~Qt.ItemFlag.ItemIsEditable)

    def _add_line(self, line: object | None = None, refresh: bool = True) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        project_combo = QComboBox(self._table)
        project_combo.addItem("Select project", None)
        for project in self._projects:
            project_combo.addItem(f"{project.project_code} — {project.project_name}", project.id)
        if line is not None:
            self._set_combo_data(project_combo, getattr(line, "project_id", None))
        self._table.setCellWidget(row, 0, project_combo)

        contract_combo = QComboBox(self._table)
        contract_combo.addItem("(None)", None)
        for contract in self._contracts:
            contract_combo.addItem(f"{contract.contract_number} — {contract.contract_title}", contract.id)
        if line is not None:
            self._set_combo_data(contract_combo, getattr(line, "contract_id", None))
        self._table.setCellWidget(row, 1, contract_combo)

        job_combo = QComboBox(self._table)
        self._populate_job_combo(job_combo, project_combo.currentData(), getattr(line, "project_job_id", None) if line is not None else None)
        self._table.setCellWidget(row, 2, job_combo)

        cost_code_combo = QComboBox(self._table)
        cost_code_combo.addItem("(None)", None)
        for cost_code in self._cost_codes:
            cost_code_combo.addItem(f"{cost_code.code} — {cost_code.name}", cost_code.id)
        if line is not None:
            self._set_combo_data(cost_code_combo, getattr(line, "project_cost_code_id", None))
        self._table.setCellWidget(row, 3, cost_code_combo)

        self._set_text_item(row, 4, getattr(line, "allocation_quantity", None))
        self._set_text_item(row, 5, getattr(line, "allocation_percent", None))
        self._set_text_item(row, 6, getattr(line, "allocated_cost_amount", None))
        self._set_text_item(row, 7, getattr(line, "notes", None))

        project_combo.currentIndexChanged.connect(
            lambda _index, combo=project_combo, job=job_combo: self._on_project_changed(combo, job)
        )
        project_combo.currentIndexChanged.connect(self._refresh_preview)
        contract_combo.currentIndexChanged.connect(self._refresh_preview)
        job_combo.currentIndexChanged.connect(self._refresh_preview)
        cost_code_combo.currentIndexChanged.connect(self._refresh_preview)

        if refresh:
            self._apply_editable_state()
            self._refresh_preview()

    def _remove_selected_line(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            row = self._table.rowCount() - 1
        if row < 0:
            return
        self._table.removeRow(row)
        self._refresh_preview()

    def _on_project_changed(self, project_combo: QComboBox, job_combo: QComboBox) -> None:
        self._populate_job_combo(job_combo, project_combo.currentData(), None)

    def _populate_job_combo(
        self,
        job_combo: QComboBox,
        project_id: int | None,
        selected_job_id: int | None,
    ) -> None:
        job_combo.blockSignals(True)
        job_combo.clear()
        job_combo.addItem("(None)", None)
        if isinstance(project_id, int) and project_id in self._jobs_by_project_id:
            for job in self._jobs_by_project_id[project_id]:
                job_combo.addItem(f"{job.job_code} — {job.job_name}", job.id)
        self._set_combo_data(job_combo, selected_job_id)
        job_combo.blockSignals(False)

    def _refresh_preview(self) -> None:
        if self._allocation_set is None:
            return
        try:
            basis_code = self._basis_combo.currentData() or "amount"
            base_amount = self._allocation_set.allocation_base_amount

            preview_amounts: list[Decimal] = []
            amount_rows: list[int] = []
            numerator_values: list[Decimal] = []

            for row in range(self._table.rowCount()):
                quantity = self._parse_decimal_item(self._table.item(row, 4)) or Decimal("0.0000")
                percent = self._parse_decimal_item(self._table.item(row, 5)) or Decimal("0.0000")
                explicit_amount = self._parse_decimal_item(self._table.item(row, 6)) or Decimal("0.0000")
                amount_rows.append(row)
                if basis_code == "percent":
                    numerator_values.append(percent)
                    preview_amounts.append(Decimal("0.0000"))
                elif basis_code == "hours":
                    numerator_values.append(quantity)
                    preview_amounts.append(Decimal("0.0000"))
                else:
                    preview_amounts.append(explicit_amount)

            if basis_code in {"percent", "hours"} and amount_rows:
                denominator = sum(numerator_values, Decimal("0.0000"))
                if basis_code == "percent" and denominator == Decimal("100.0000"):
                    self._derive_preview_amounts(
                        base_amount,
                        numerator_values,
                        Decimal("100.0000"),
                        preview_amounts,
                    )
                elif basis_code == "hours" and denominator > Decimal("0.0000"):
                    self._derive_preview_amounts(base_amount, numerator_values, denominator, preview_amounts)
                self._table.blockSignals(True)
                for row, amount in zip(amount_rows, preview_amounts, strict=False):
                    amount_item = self._table.item(row, 6)
                    if amount_item is not None:
                        amount_item.setText(f"{amount:.4f}")
                self._table.blockSignals(False)

            total_allocated = sum(preview_amounts, Decimal("0.0000")).quantize(_MONEY_SCALE)
            remaining = (base_amount - total_allocated).quantize(_MONEY_SCALE)
            self._allocated_total_label.setText(f"Allocated: {total_allocated:,.4f}")
            self._remaining_label.setText(f"Remaining: {remaining:,.4f}")
            self._set_error(None)
        except ValidationError as exc:
            self._set_error(str(exc))

    def _derive_preview_amounts(
        self,
        base_amount: Decimal,
        numerators: list[Decimal],
        denominator: Decimal,
        target_amounts: list[Decimal],
    ) -> None:
        remaining = base_amount
        for index, numerator in enumerate(numerators):
            if index == len(numerators) - 1:
                target_amounts[index] = remaining.quantize(_MONEY_SCALE)
            else:
                raw_amount = (base_amount * numerator) / denominator
                derived = raw_amount.quantize(_MONEY_SCALE, rounding=ROUND_HALF_UP)
                target_amounts[index] = derived
                remaining -= derived

    def _handle_submit(self) -> None:
        self._set_error(None)
        basis_code = self._basis_combo.currentData() or "amount"
        lines: list[PayrollProjectAllocationLineCommand] = []

        for row in range(self._table.rowCount()):
            project_combo = self._table.cellWidget(row, 0)
            contract_combo = self._table.cellWidget(row, 1)
            job_combo = self._table.cellWidget(row, 2)
            cost_code_combo = self._table.cellWidget(row, 3)

            project_id = project_combo.currentData() if isinstance(project_combo, QComboBox) else None
            if not isinstance(project_id, int) or project_id <= 0:
                self._set_error(f"Line {row + 1}: Project is required.")
                return

            quantity = self._parse_decimal_item(self._table.item(row, 4))
            percent = self._parse_decimal_item(self._table.item(row, 5))
            amount = self._parse_decimal_item(self._table.item(row, 6))
            notes = self._table.item(row, 7).text().strip() if self._table.item(row, 7) is not None else None

            lines.append(
                PayrollProjectAllocationLineCommand(
                    project_id=project_id,
                    allocation_basis_code=basis_code,
                    contract_id=contract_combo.currentData() if isinstance(contract_combo, QComboBox) else None,
                    project_job_id=job_combo.currentData() if isinstance(job_combo, QComboBox) else None,
                    project_cost_code_id=cost_code_combo.currentData() if isinstance(cost_code_combo, QComboBox) else None,
                    allocation_quantity=quantity,
                    allocation_percent=percent,
                    allocated_cost_amount=amount,
                    notes=notes or None,
                )
            )

        try:
            self._allocation_set = self._registry.payroll_project_allocation_service.replace_allocations(
                self._company_id,
                self._payroll_run_employee_id,
                ReplacePayrollProjectAllocationsCommand(lines=tuple(lines)),
            )
        except ValidationError as exc:
            self._set_error(str(exc))
            return
        except Exception as exc:
            show_error(self, "Project Allocations", str(exc))
            return

        self.accept()

    def _set_combo_data(self, combo: QComboBox, value: object) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _set_text_item(self, row: int, col: int, value: object) -> None:
        text = ""
        if isinstance(value, Decimal):
            text = f"{value:.4f}"
        elif value is not None:
            text = str(value)
        item = QTableWidgetItem(text)
        if col in (4, 5, 6):
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, col, item)

    def _parse_decimal_item(self, item: QTableWidgetItem | None) -> Decimal | None:
        if item is None:
            return None
        text = item.text().strip()
        if not text:
            return None
        try:
            return Decimal(text).quantize(_MONEY_SCALE, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("Allocation numeric fields must contain valid decimal values.") from exc

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()