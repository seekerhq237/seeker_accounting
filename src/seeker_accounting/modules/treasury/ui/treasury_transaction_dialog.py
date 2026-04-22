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
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.treasury.dto.treasury_transaction_commands import (
    CreateTreasuryTransactionCommand,
    TreasuryTransactionLineCommand,
    UpdateTreasuryTransactionCommand,
)
from seeker_accounting.modules.treasury.dto.treasury_transaction_dto import TreasuryTransactionDetailDTO
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox
from seeker_accounting.shared.ui.table_helpers import configure_compact_editable_table

_log = logging.getLogger(__name__)


class TreasuryTransactionDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        transaction_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._transaction_id = transaction_id
        self._saved_transaction: TreasuryTransactionDetailDTO | None = None
        self._accounts: list[tuple[int, str]] = []

        is_edit = transaction_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Treasury Transaction — {company_name}")
        self.setModal(True)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_header_section())
        layout.addWidget(self._build_lines_section(), 1)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._button_box.accepted.connect(self._handle_submit)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._load_reference_data()
        if is_edit:
            self._load_transaction()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.treasury_transaction")

    @property
    def saved_transaction(self) -> TreasuryTransactionDetailDTO | None:
        return self._saved_transaction

    @classmethod
    def create_transaction(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> TreasuryTransactionDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_transaction
        return None

    @classmethod
    def edit_transaction(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        transaction_id: int,
        parent: QWidget | None = None,
    ) -> TreasuryTransactionDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, transaction_id=transaction_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_transaction
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_header_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self._type_combo = QComboBox(card)
        self._type_combo.addItem("Cash Receipt", "cash_receipt")
        self._type_combo.addItem("Cash Payment", "cash_payment")
        self._type_combo.addItem("Bank Receipt", "bank_receipt")
        self._type_combo.addItem("Bank Payment", "bank_payment")
        form.addRow("Transaction Type", self._type_combo)

        self._account_combo = SearchableComboBox(card)
        form.addRow("Financial Account", self._account_combo)

        dimensions_row = QWidget(card)
        dimensions_layout = QHBoxLayout(dimensions_row)
        dimensions_layout.setContentsMargins(0, 0, 0, 0)
        dimensions_layout.setSpacing(12)

        self._contract_combo = SearchableComboBox(card)
        dimensions_layout.addWidget(QLabel("Contract"))
        dimensions_layout.addWidget(self._contract_combo, 1)

        self._project_combo = SearchableComboBox(card)
        dimensions_layout.addWidget(QLabel("Project"))
        dimensions_layout.addWidget(self._project_combo, 1)

        form.addRow(dimensions_row)

        self._date_edit = QDateEdit(card)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(date.today())
        form.addRow("Transaction Date", self._date_edit)

        self._currency_combo = SearchableComboBox(card)
        form.addRow("Currency", self._currency_combo)

        self._exchange_rate_input = QLineEdit(card)
        self._exchange_rate_input.setPlaceholderText("Exchange rate")
        form.addRow("Exchange Rate", self._exchange_rate_input)

        self._reference_input = QLineEdit(card)
        self._reference_input.setPlaceholderText("Optional reference")
        form.addRow("Reference", self._reference_input)

        self._description_input = QLineEdit(card)
        self._description_input.setPlaceholderText("Optional description")
        form.addRow("Description", self._description_input)

        self._notes_input = QPlainTextEdit(card)
        self._notes_input.setMaximumHeight(50)
        self._notes_input.setPlaceholderText("Notes")
        form.addRow("Notes", self._notes_input)

        return card

    def _build_lines_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        lines_label = QLabel("Transaction Lines", card)
        lines_label.setObjectName("CardTitle")
        header_row.addWidget(lines_label)

        header_row.addStretch(1)

        self._total_label = QLabel("Total: 0.00", card)
        self._total_label.setObjectName("ToolbarValue")
        header_row.addWidget(self._total_label)

        layout.addLayout(header_row)

        hint_label = QLabel("Leave line dimension cells blank to inherit the header contract or project.", card)
        hint_label.setObjectName("ToolbarMeta")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        self._lines_table = QTableWidget(card)
        self._lines_table.setColumnCount(8)
        self._lines_table.setHorizontalHeaderLabels(
            ("Account", "Description", "Amount", "Contract", "Project", "Job", "Cost Code", "")
        )
        configure_compact_editable_table(self._lines_table)

        header = self._lines_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._lines_table, 1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        add_line_button = QPushButton("Add Line", card)
        add_line_button.setProperty("variant", "secondary")
        add_line_button.clicked.connect(self._add_empty_line)
        button_row.addWidget(add_line_button)

        button_row.addStretch(1)
        layout.addLayout(button_row)

        return card

    # ------------------------------------------------------------------
    # Line management
    # ------------------------------------------------------------------

    def _add_empty_line(self) -> None:
        row = self._lines_table.rowCount()
        self._lines_table.insertRow(row)

        account_combo = QComboBox()
        account_combo.addItem("-- Select account --", 0)
        for acc_id, acc_label in self._accounts:
            account_combo.addItem(acc_label, acc_id)
        self._lines_table.setCellWidget(row, 0, account_combo)

        desc_item = QTableWidgetItem("")
        self._lines_table.setItem(row, 1, desc_item)

        amount_item = QTableWidgetItem("0.00")
        amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lines_table.setItem(row, 2, amount_item)

        for column in range(3, 7):
            self._lines_table.setItem(row, column, QTableWidgetItem(""))

        remove_button = QPushButton("Remove")
        remove_button.setProperty("variant", "ghost")
        remove_button.clicked.connect(lambda checked=False, r=row: self._remove_line(r))
        self._lines_table.setCellWidget(row, 7, remove_button)

    def _remove_line(self, row: int) -> None:
        if row < self._lines_table.rowCount():
            self._lines_table.removeRow(row)
            self._reconnect_remove_buttons()
            self._update_total()

    def _reconnect_remove_buttons(self) -> None:
        for row in range(self._lines_table.rowCount()):
            remove_btn = self._lines_table.cellWidget(row, 7)
            if isinstance(remove_btn, QPushButton):
                try:
                    remove_btn.clicked.disconnect()
                except RuntimeError:
                    pass
                remove_btn.clicked.connect(lambda checked=False, r=row: self._remove_line(r))

    def _update_total(self) -> None:
        total = Decimal("0.00")
        for row in range(self._lines_table.rowCount()):
            item = self._lines_table.item(row, 2)
            if item is not None:
                val = self._parse_decimal(item.text())
                if val is not None:
                    total += val
        self._total_label.setText(f"Total: {total:,.2f}")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            contracts = self._service_registry.contract_service.list_contracts(self._company_id)
            self._contract_combo.set_items(
                [
                    (f"{contract.contract_number} — {contract.contract_title}", contract.id)
                    for contract in contracts
                ],
                placeholder="-- No contract --",
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        try:
            projects = self._service_registry.project_service.list_projects(self._company_id)
            self._project_combo.set_items(
                [
                    (f"{project.project_code} — {project.project_name}", project.id)
                    for project in projects
                ],
                placeholder="-- No project --",
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        try:
            fa_list = self._service_registry.financial_account_service.list_financial_accounts(
                self._company_id, active_only=True
            )
            self._account_combo.set_items(
                [(f"{a.account_code} — {a.name}", a.id) for a in fa_list],
                placeholder="-- Select account --",
                placeholder_value=0,
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        try:
            gl_accounts = self._service_registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
            self._accounts = [(a.id, f"{a.account_code} — {a.account_name}") for a in gl_accounts]
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            self._accounts = []

        try:
            ref = self._service_registry.reference_data_service.list_active_currencies()
            self._currency_combo.set_items(
                [(cur.code, cur.code) for cur in ref],
                placeholder="-- Select currency --",
            )
            ctx = self._service_registry.active_company_context
            if ctx.base_currency_code:
                self._currency_combo.set_current_value(ctx.base_currency_code)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_transaction(self) -> None:
        if self._transaction_id is None:
            return
        try:
            detail = self._service_registry.treasury_transaction_service.get_treasury_transaction(
                self._company_id, self._transaction_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        type_idx = self._type_combo.findData(detail.transaction_type_code)
        if type_idx >= 0:
            self._type_combo.setCurrentIndex(type_idx)

        self._account_combo.set_current_value(detail.financial_account_id)
        self._contract_combo.set_current_value(detail.contract_id)
        self._project_combo.set_current_value(detail.project_id)

        self._date_edit.setDate(detail.transaction_date)

        self._currency_combo.set_current_value(detail.currency_code)

        if detail.exchange_rate is not None:
            self._exchange_rate_input.setText(str(detail.exchange_rate))

        self._reference_input.setText(detail.reference_number or "")
        self._description_input.setText(detail.description or "")
        self._notes_input.setPlainText(detail.notes or "")

        for line in detail.lines:
            row = self._lines_table.rowCount()
            self._lines_table.insertRow(row)

            account_combo = QComboBox()
            account_combo.addItem("-- Select account --", 0)
            for acc_id, acc_label in self._accounts:
                account_combo.addItem(acc_label, acc_id)
            combo_idx = account_combo.findData(line.account_id)
            if combo_idx >= 0:
                account_combo.setCurrentIndex(combo_idx)
            self._lines_table.setCellWidget(row, 0, account_combo)

            desc_item = QTableWidgetItem(line.line_description)
            self._lines_table.setItem(row, 1, desc_item)

            amount_item = QTableWidgetItem(str(line.amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._lines_table.setItem(row, 2, amount_item)

            self._lines_table.setItem(row, 3, QTableWidgetItem("" if line.contract_id is None else str(line.contract_id)))
            self._lines_table.setItem(row, 4, QTableWidgetItem("" if line.project_id is None else str(line.project_id)))
            self._lines_table.setItem(row, 5, QTableWidgetItem("" if line.project_job_id is None else str(line.project_job_id)))
            self._lines_table.setItem(
                row,
                6,
                QTableWidgetItem("" if line.project_cost_code_id is None else str(line.project_cost_code_id)),
            )

            remove_button = QPushButton("Remove")
            remove_button.setProperty("variant", "ghost")
            remove_button.clicked.connect(lambda checked=False, r=row: self._remove_line(r))
            self._lines_table.setCellWidget(row, 7, remove_button)

        self._update_total()

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        transaction_type_code = self._type_combo.currentData()
        if not transaction_type_code:
            self._set_error("Please select a transaction type.")
            return

        financial_account_id = self._account_combo.current_value()
        if not financial_account_id or financial_account_id == 0:
            self._set_error("Please select a financial account.")
            return

        transaction_date = self._date_edit.date().toPython()
        currency_code = self._currency_combo.current_value() or ""
        exchange_rate = self._parse_decimal(self._exchange_rate_input.text())
        reference_number = self._reference_input.text().strip() or None
        description = self._description_input.text().strip() or None
        notes = self._notes_input.toPlainText().strip() or None
        contract_id = self._contract_combo.current_value()
        project_id = self._project_combo.current_value()

        lines: list[TreasuryTransactionLineCommand] = []
        for row in range(self._lines_table.rowCount()):
            account_combo = self._lines_table.cellWidget(row, 0)
            if not isinstance(account_combo, QComboBox):
                continue
            account_id = account_combo.currentData()
            if not account_id or account_id == 0:
                self._set_error(f"Line {row + 1}: Please select an account.")
                return

            desc_item = self._lines_table.item(row, 1)
            line_description = desc_item.text().strip() if desc_item else ""

            amount_item = self._lines_table.item(row, 2)
            amount = self._parse_decimal(amount_item.text()) if amount_item else None
            if amount is None or amount <= Decimal("0"):
                self._set_error(f"Line {row + 1}: Amount must be greater than zero.")
                return

            line_contract_id = self._parse_optional_int(self._lines_table.item(row, 3))
            line_project_id = self._parse_optional_int(self._lines_table.item(row, 4))
            line_project_job_id = self._parse_optional_int(self._lines_table.item(row, 5))
            line_project_cost_code_id = self._parse_optional_int(self._lines_table.item(row, 6))

            lines.append(
                TreasuryTransactionLineCommand(
                    account_id=account_id,
                    line_description=line_description,
                    amount=amount,
                    contract_id=line_contract_id,
                    project_id=line_project_id,
                    project_job_id=line_project_job_id,
                    project_cost_code_id=line_project_cost_code_id,
                )
            )

        if not lines:
            self._set_error("Add at least one transaction line.")
            return

        try:
            if self._transaction_id is None:
                cmd = CreateTreasuryTransactionCommand(
                    transaction_type_code=transaction_type_code,
                    financial_account_id=financial_account_id,
                    transaction_date=transaction_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    reference_number=reference_number,
                    description=description,
                    notes=notes,
                    contract_id=contract_id,
                    project_id=project_id,
                    lines=tuple(lines),
                )
                self._saved_transaction = (
                    self._service_registry.treasury_transaction_service.create_draft_transaction(
                        self._company_id, cmd
                    )
                )
            else:
                cmd_update = UpdateTreasuryTransactionCommand(
                    transaction_type_code=transaction_type_code,
                    financial_account_id=financial_account_id,
                    transaction_date=transaction_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    reference_number=reference_number,
                    description=description,
                    notes=notes,
                    contract_id=contract_id,
                    project_id=project_id,
                    lines=tuple(lines),
                )
                self._saved_transaction = (
                    self._service_registry.treasury_transaction_service.update_draft_transaction(
                        self._company_id, self._transaction_id, cmd_update
                    )
                )
            self.accept()
        except (ValidationError, Exception) as exc:
            self._set_error(str(exc))

    def _set_error(self, message: str) -> None:
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

    def _parse_optional_int(self, item: QTableWidgetItem | None) -> int | None:
        if item is None:
            return None
        text = item.text().strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError as exc:
            raise ValidationError("Dimension fields must be valid integer identifiers.") from exc
