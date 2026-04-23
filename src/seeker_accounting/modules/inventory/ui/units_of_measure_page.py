from __future__ import annotations

import logging

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.inventory.dto.inventory_reference_commands import (
    CreateUnitOfMeasureCommand,
    UpdateUnitOfMeasureCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_dto import UnitOfMeasureDTO
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)


class _UomDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        uom_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._uom_id = uom_id
        self._saved: UnitOfMeasureDTO | None = None

        is_edit = uom_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Unit of Measure — {company_name}")
        self.setModal(True)
        self.resize(420, 340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = QFrame(self)
        card.setObjectName("PageCard")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self._code_input = QLineEdit(card)
        self._code_input.setPlaceholderText("e.g. UNIT, KG, PCS")
        form.addRow("Code", self._code_input)

        self._name_input = QLineEdit(card)
        self._name_input.setPlaceholderText("Full name")
        form.addRow("Name", self._name_input)

        self._category_combo = QComboBox(card)
        self._category_combo.addItem("— None —", None)
        self._load_categories()
        form.addRow("Category", self._category_combo)

        self._ratio_input = QLineEdit(card)
        self._ratio_input.setPlaceholderText("1")
        self._ratio_input.setToolTip("Ratio to the base unit within the category (e.g. 12 for a Dozen)")
        form.addRow("Ratio to Base", self._ratio_input)

        self._desc_input = QPlainTextEdit(card)
        self._desc_input.setMaximumHeight(60)
        form.addRow("Description", self._desc_input)

        self._active_checkbox = QCheckBox("Active", card)
        self._active_checkbox.setChecked(True)
        if is_edit:
            form.addRow("", self._active_checkbox)

        layout.addWidget(card)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if is_edit:
            self._load()

    @property
    def saved(self) -> UnitOfMeasureDTO | None:
        return self._saved

    def _load_categories(self) -> None:
        try:
            categories = self._service_registry.uom_category_service.list_categories(
                self._company_id, active_only=True
            )
            for cat in categories:
                self._category_combo.addItem(f"{cat.code} — {cat.name}", cat.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load(self) -> None:
        try:
            uom = self._service_registry.unit_of_measure_service.get_unit_of_measure(
                self._company_id, self._uom_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._code_input.setText(uom.code)
        self._name_input.setText(uom.name)
        self._desc_input.setPlainText(uom.description or "")
        self._active_checkbox.setChecked(uom.is_active)
        self._ratio_input.setText(str(uom.ratio_to_base) if uom.ratio_to_base else "1")
        if uom.category_id is not None:
            idx = self._category_combo.findData(uom.category_id)
            if idx >= 0:
                self._category_combo.setCurrentIndex(idx)

    def _submit(self) -> None:
        self._error_label.hide()
        code = self._code_input.text().strip()
        name = self._name_input.text().strip()
        description = self._desc_input.toPlainText().strip() or None
        is_active = self._active_checkbox.isChecked()
        category_id = self._category_combo.currentData()

        ratio_text = self._ratio_input.text().strip() or "1"
        try:
            ratio = Decimal(ratio_text)
            if ratio <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            self._error_label.setText("Ratio to Base must be a positive number.")
            self._error_label.show()
            return

        try:
            if self._uom_id is None:
                self._saved = self._service_registry.unit_of_measure_service.create_unit_of_measure(
                    self._company_id,
                    CreateUnitOfMeasureCommand(
                        code=code, name=name, description=description,
                        category_id=category_id, ratio_to_base=ratio,
                    ),
                )
            else:
                self._saved = self._service_registry.unit_of_measure_service.update_unit_of_measure(
                    self._company_id,
                    self._uom_id,
                    UpdateUnitOfMeasureCommand(
                        code=code, name=name, description=description, is_active=is_active,
                        category_id=category_id, ratio_to_base=ratio,
                    ),
                )
            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()


class UnitsOfMeasurePage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    def reload(self) -> None:
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            self._table.setRowCount(0)
            self._count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_company_state)
            return
        try:
            rows = self._service_registry.unit_of_measure_service.list_units_of_measure(
                active_company.company_id
            )
        except Exception as exc:
            self._table.setRowCount(0)
            self._count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            show_error(self, "Units of Measure", f"Could not load data.\n\n{exc}")
            return
        self._populate(rows)
        self._sync_stack(active_company, rows)

    def _build_toolbar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel('Units of Measure', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._count_label = QLabel(card)
        self._count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._count_label)

        layout.addStretch(1)
        self._new_btn = QPushButton("New UoM", card)
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.clicked.connect(self._on_new)
        layout.addWidget(self._new_btn)

        self._edit_btn = QPushButton("Edit", card)
        self._edit_btn.setProperty("variant", "secondary")
        self._edit_btn.clicked.connect(self._on_edit)
        layout.addWidget(self._edit_btn)

        refresh_btn = QPushButton("Refresh", card)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(self.reload)
        layout.addWidget(refresh_btn)

        return card

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_company_state = self._build_no_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._table = QTableWidget(card)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(("Code", "Name", "Category", "Ratio", "Description", "Active"))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("No units of measure", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel("Create units of measure to use on item master records.", card)
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addStretch(1)
        return card

    def _build_no_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel("Units of measure are company-scoped.", card)
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        actions = QWidget(card)
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 4, 0, 0)
        al.addStretch(1)
        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    def _populate(self, rows: list[UnitOfMeasureDTO]) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for row in rows:
            ri = self._table.rowCount()
            self._table.insertRow(ri)
            code_item = QTableWidgetItem(row.code)
            code_item.setData(Qt.ItemDataRole.UserRole, row.id)
            self._table.setItem(ri, 0, code_item)
            self._table.setItem(ri, 1, QTableWidgetItem(row.name))
            self._table.setItem(ri, 2, QTableWidgetItem(row.category_code or ""))
            ratio_item = QTableWidgetItem(str(row.ratio_to_base))
            ratio_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(ri, 3, ratio_item)
            self._table.setItem(ri, 4, QTableWidgetItem(row.description or ""))
            self._table.setItem(ri, 5, QTableWidgetItem("Yes" if row.is_active else "No"))
        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.Stretch)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)
        count = len(rows)
        self._count_label.setText(f"{count} record" if count == 1 else f"{count} records")

    def _sync_stack(self, active_company: ActiveCompanyDTO | None, rows: list) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_company_state)
        elif rows:
            self._stack.setCurrentWidget(self._table_surface)
        else:
            self._stack.setCurrentWidget(self._empty_state)

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _on_new(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Units of Measure", "Select an active company first.")
            return
        dialog = _UomDialog(self._service_registry, company.company_id, company.company_name, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _on_edit(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        uom_id = item.data(Qt.ItemDataRole.UserRole)
        dialog = _UomDialog(
            self._service_registry, company.company_id, company.company_name, uom_id=uom_id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()
