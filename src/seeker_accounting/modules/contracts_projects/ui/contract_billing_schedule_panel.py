"""Contract billing schedule tab panel + batch editor dialog."""
from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.contracts_projects.dto.contract_commercial_dto import (
    ContractBillingScheduleItemCommand,
    ContractBillingScheduleItemDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.message_boxes import show_error

_SCHEDULE_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("milestone", "Milestone"),
    ("percentage", "Percentage"),
    ("fixed", "Fixed Amount"),
    ("time_and_material", "Time & Material"),
    ("manual", "Manual"),
]


def _fmt_date(value: date | None) -> str:
    if value is None:
        return "—"
    return value.isoformat()


def _humanize(code: str | None) -> str:
    if not code:
        return "—"
    return code.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Panel (tab widget)
# ---------------------------------------------------------------------------


class ContractBillingSchedulePanel(QWidget):
    """Read-only list panel for the contract billing schedule."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._contract_id = contract_id
        self._items: tuple[ContractBillingScheduleItemDTO, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        title_lbl = QLabel("Billing Schedule", card)
        title_lbl.setObjectName("DialogSectionTitle")
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._summary_label = QLabel("", card)
        self._summary_label.setObjectName("DialogSectionSummary")
        header.addWidget(self._summary_label)
        self._edit_btn = QPushButton("Edit Schedule", card)
        self._edit_btn.setProperty("variant", "primary")
        self._edit_btn.clicked.connect(self._open_editor)
        header.addWidget(self._edit_btn)
        card_layout.addLayout(header)

        self._model = QStandardItemModel(0, 7, card)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="num", title="#"),
                DataTableColumn(key="type", title="Type"),
                DataTableColumn(key="description", title="Description"),
                DataTableColumn(key="date", title="Scheduled Date"),
                DataTableColumn(key="amount", title="Amount", is_numeric=True),
                DataTableColumn(key="pct", title="%", is_numeric=True),
                DataTableColumn(key="status", title="Status"),
            ),
            show_search=False,
            show_count=True,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._table.set_model(self._model)
        card_layout.addWidget(self._table, 1)
        layout.addWidget(card, 1)

    def reload(self) -> None:
        try:
            self._items = self._service_registry.contract_commercial_service.list_billing_schedule(
                self._company_id, self._contract_id
            )
        except Exception as exc:
            self._items = ()
            show_error(self, "Billing Schedule", f"Could not load billing schedule.\n\n{exc}")
        self._populate_table()

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        total = Decimal("0.00")
        for item in self._items:
            pct_str = "—" if item.billing_percent is None else f"{item.billing_percent:.2f}%"
            self._model.appendRow([
                self._make_item(str(item.line_number), user_data=item.id),
                self._make_item(_humanize(item.schedule_type_code)),
                self._make_item(item.description),
                self._make_item(_fmt_date(item.scheduled_date)),
                self._make_item(f"{item.scheduled_amount:,.2f}"),
                self._make_item(pct_str),
                self._make_item(_humanize(item.status_code)),
            ])
            total += item.scheduled_amount
        count = len(self._items)
        self._summary_label.setText(
            f"{count} item{'s' if count != 1 else ''} | Total: {total:,.2f}"
        )

    def _open_editor(self) -> None:
        dialog = ContractBillingScheduleEditorDialog(
            self._service_registry,
            self._company_id,
            self._contract_id,
            self._items,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    @staticmethod
    def _make_item(text: object, *, user_data: object = None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item


# ---------------------------------------------------------------------------
# Batch editor dialog
# ---------------------------------------------------------------------------


class ContractBillingScheduleEditorDialog(QDialog):
    """Inline table editor for creating/replacing all billing schedule items."""

    _COL_TYPE = 0
    _COL_DESCRIPTION = 1
    _COL_DATE = 2
    _COL_AMOUNT = 3
    _COL_PCT = 4
    _COL_RETENTION_PCT = 5
    _COL_ADVANCE_PCT = 6
    _COL_NOTES = 7
    _COLS = 8

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        current_items: tuple[ContractBillingScheduleItemDTO, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._contract_id = contract_id
        self.setWindowTitle("Edit Billing Schedule")
        self.setModal(True)
        apply_window_size(self, "modules.contracts.projects.ui.contract.billing.schedule.panel.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        intro = QLabel(
            "Define the billing milestones or schedule items. "
            "The total scheduled amount should reconcile to the current contract value.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._table = QTableWidget(0, self._COLS, self)
        self._table.setHorizontalHeaderLabels([
            "Type", "Description *", "Scheduled Date", "Amount *",
            "Billing %", "Retention %", "Adv. Rec. %", "Notes",
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            self._COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            self._COL_NOTES, QHeaderView.ResizeMode.Stretch
        )
        for col in (self._COL_TYPE, self._COL_DATE, self._COL_AMOUNT,
                    self._COL_PCT, self._COL_RETENTION_PCT, self._COL_ADVANCE_PCT):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        toolbar = QHBoxLayout()
        add_btn = QPushButton("Add Item", self)
        add_btn.clicked.connect(self._add_row)
        toolbar.addWidget(add_btn)
        remove_btn = QPushButton("Remove Selected", self)
        remove_btn.clicked.connect(self._remove_selected)
        toolbar.addWidget(remove_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        save_btn = button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setProperty("variant", "primary")
        button_box.accepted.connect(self._handle_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        for item in current_items:
            self._append_row(
                type_code=item.schedule_type_code,
                description=item.description,
                scheduled_date=item.scheduled_date,
                amount=str(item.scheduled_amount),
                billing_pct=str(item.billing_percent) if item.billing_percent is not None else "",
                retention_pct=str(item.retention_percent) if item.retention_percent is not None else "",
                advance_pct=str(item.advance_recovery_percent) if item.advance_recovery_percent is not None else "",
                notes=item.notes or "",
            )
        if not current_items:
            self._add_row()

    def _append_row(
        self,
        type_code: str = "milestone",
        description: str = "",
        scheduled_date: date | None = None,
        amount: str = "0.00",
        billing_pct: str = "",
        retention_pct: str = "",
        advance_pct: str = "",
        notes: str = "",
    ) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        combo = QComboBox(self._table)
        for code, label in _SCHEDULE_TYPE_OPTIONS:
            combo.addItem(label, code)
        idx = next((i for i, (c, _) in enumerate(_SCHEDULE_TYPE_OPTIONS) if c == type_code), 0)
        combo.setCurrentIndex(idx)
        self._table.setCellWidget(row, self._COL_TYPE, combo)

        self._table.setItem(row, self._COL_DESCRIPTION, QTableWidgetItem(description))

        date_edit = QDateEdit(self._table)
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("yyyy-MM-dd")
        if scheduled_date is not None:
            from PySide6.QtCore import QDate
            date_edit.setDate(QDate(scheduled_date.year, scheduled_date.month, scheduled_date.day))
        else:
            from PySide6.QtCore import QDate
            date_edit.setDate(QDate.currentDate())
        date_edit.setSpecialValueText(" ")
        self._table.setCellWidget(row, self._COL_DATE, date_edit)

        self._table.setItem(row, self._COL_AMOUNT, QTableWidgetItem(amount))
        self._table.setItem(row, self._COL_PCT, QTableWidgetItem(billing_pct))
        self._table.setItem(row, self._COL_RETENTION_PCT, QTableWidgetItem(retention_pct))
        self._table.setItem(row, self._COL_ADVANCE_PCT, QTableWidgetItem(advance_pct))
        self._table.setItem(row, self._COL_NOTES, QTableWidgetItem(notes))

    def _add_row(self) -> None:
        self._append_row()

    def _remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._table.removeRow(row)

    def _build_commands(self) -> tuple[ContractBillingScheduleItemCommand, ...] | None:
        from PySide6.QtCore import QDate

        commands: list[ContractBillingScheduleItemCommand] = []
        for row in range(self._table.rowCount()):
            combo: QComboBox | None = self._table.cellWidget(row, self._COL_TYPE)  # type: ignore[assignment]
            date_widget: QDateEdit | None = self._table.cellWidget(row, self._COL_DATE)  # type: ignore[assignment]
            desc_item = self._table.item(row, self._COL_DESCRIPTION)
            amount_item = self._table.item(row, self._COL_AMOUNT)
            pct_item = self._table.item(row, self._COL_PCT)
            ret_pct_item = self._table.item(row, self._COL_RETENTION_PCT)
            adv_pct_item = self._table.item(row, self._COL_ADVANCE_PCT)
            notes_item = self._table.item(row, self._COL_NOTES)

            type_code = combo.currentData() if combo else "milestone"
            description = (desc_item.text() if desc_item else "").strip()
            amount_str = (amount_item.text() if amount_item else "0").strip()
            pct_str = (pct_item.text() if pct_item else "").strip()
            ret_pct_str = (ret_pct_item.text() if ret_pct_item else "").strip()
            adv_pct_str = (adv_pct_item.text() if adv_pct_item else "").strip()
            notes = (notes_item.text() if notes_item else "").strip()

            if not description:
                self._show_error(f"Row {row + 1}: Description is required.")
                return None
            try:
                amount = Decimal(amount_str.replace(",", ""))
            except InvalidOperation:
                self._show_error(f"Row {row + 1}: Amount must be numeric.")
                return None

            billing_pct: Decimal | None = None
            retention_pct: Decimal | None = None
            advance_pct: Decimal | None = None
            try:
                if pct_str:
                    billing_pct = Decimal(pct_str.replace(",", ""))
                if ret_pct_str:
                    retention_pct = Decimal(ret_pct_str.replace(",", ""))
                if adv_pct_str:
                    advance_pct = Decimal(adv_pct_str.replace(",", ""))
            except InvalidOperation:
                self._show_error(f"Row {row + 1}: Percentage fields must be numeric.")
                return None

            scheduled_date: date | None = None
            if date_widget is not None:
                qd = date_widget.date()
                if qd.isValid() and qd != QDate():
                    scheduled_date = date(qd.year(), qd.month(), qd.day())

            commands.append(
                ContractBillingScheduleItemCommand(
                    schedule_type_code=type_code,
                    description=description,
                    scheduled_amount=amount,
                    scheduled_date=scheduled_date,
                    billing_percent=billing_pct,
                    retention_percent=retention_pct,
                    advance_recovery_percent=advance_pct,
                    notes=notes or None,
                )
            )
        return tuple(commands)

    def _handle_save(self) -> None:
        self._error_label.hide()
        commands = self._build_commands()
        if commands is None:
            return
        try:
            self._service_registry.contract_commercial_service.replace_billing_schedule(
                self._company_id, self._contract_id, commands
            )
        except (ValidationError, NotFoundError) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
