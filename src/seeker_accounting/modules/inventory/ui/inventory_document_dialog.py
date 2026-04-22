from __future__ import annotations

import logging

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CreateInventoryDocumentCommand,
    UpdateInventoryDocumentCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_document_dto import InventoryDocumentDetailDTO
from seeker_accounting.modules.inventory.ui.inventory_document_lines_grid import (
    InventoryDocumentLinesGrid,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class InventoryDocumentDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        document_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._document_id = document_id
        self._saved_document: InventoryDocumentDetailDTO | None = None

        is_edit = document_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Inventory Document - {company_name}")
        self.setModal(True)
        self.resize(1020, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(self._build_header_section())
        layout.addWidget(self._build_lines_section(), 1)
        layout.addWidget(self._build_totals_panel())

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
        save_button = self._button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Create Document" if not is_edit else "Save Changes")
            save_button.setProperty("variant", "primary")
        cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")
        layout.addWidget(self._button_box)

        self._load_reference_data()
        if is_edit:
            self._load_document()

        self._on_document_type_changed()

        from seeker_accounting.shared.ui.help_button import install_help_button

        install_help_button(self, "dialog.inventory_document")

    @property
    def saved_document(self) -> InventoryDocumentDetailDTO | None:
        return self._saved_document

    @classmethod
    def create_document(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> InventoryDocumentDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_document
        return None

    @classmethod
    def edit_document(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        document_id: int,
        parent: QWidget | None = None,
    ) -> InventoryDocumentDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, document_id=document_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_document
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_header_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        grid = QGridLayout(card)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setSpacing(6)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)

        # Row 0: Document Type | Document Date
        self._type_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Document Type", self._type_combo), 0, 0)

        self._date_edit = QDateEdit(card)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(date.today())
        grid.addWidget(create_field_block("Document Date", self._date_edit), 0, 1)

        # Row 1: Location | Reference
        self._location_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Location", self._location_combo), 1, 0)

        self._reference_input = QLineEdit(card)
        self._reference_input.setPlaceholderText("Optional reference number")
        grid.addWidget(create_field_block("Reference", self._reference_input), 1, 1)

        # Row 2: Contract | Project
        self._contract_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Contract", self._contract_combo), 2, 0)

        self._project_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Project", self._project_combo), 2, 1)

        # Row 3: Hint label (full width)
        self._document_hint_label = QLabel(card)
        self._document_hint_label.setObjectName("ToolbarMeta")
        self._document_hint_label.setWordWrap(True)
        grid.addWidget(self._document_hint_label, 3, 0, 1, 2)

        # Row 4: Notes (full width)
        self._notes_input = QPlainTextEdit(card)
        self._notes_input.setMaximumHeight(36)
        self._notes_input.setPlaceholderText("Notes")
        grid.addWidget(create_field_block("Notes", self._notes_input), 4, 0, 1, 2)

        return card

    def _build_lines_section(self) -> QWidget:
        self._lines_grid = InventoryDocumentLinesGrid(
            self._service_registry, self._company_id, self
        )
        return self._lines_grid

    def _build_totals_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("InfoCard")

        outer = QHBoxLayout(panel)
        outer.setContentsMargins(14, 8, 14, 8)
        outer.setSpacing(10)

        self._line_count_label = QLabel("0 lines", panel)
        self._line_count_label.setObjectName("ToolbarMeta")
        outer.addWidget(self._line_count_label)
        outer.addStretch(1)

        lbl_total = QLabel("Total", panel)
        lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_total.setObjectName("CardTitle")
        outer.addWidget(lbl_total)

        self._total_value = QLabel("0.00", panel)
        self._total_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._total_value.setObjectName("TotalsGrandTotal")
        self._total_value.setMinimumWidth(110)
        outer.addWidget(self._total_value)

        return panel

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            self._type_combo.set_items(
                [("Receipt", "receipt"), ("Issue", "issue"), ("Adjustment", "adjustment")],
                placeholder="-- Select type --",
            )
            self._type_combo.set_current_value("receipt")

            locations = self._service_registry.inventory_location_service.list_inventory_locations(
                self._company_id, active_only=True
            )
            self._location_combo.set_items(
                [(f"{loc.code} - {loc.name}", loc.id) for loc in locations],
                placeholder="-- No location --",
            )

            contracts = self._service_registry.contract_service.list_contracts(self._company_id)
            self._contract_combo.set_items(
                [(f"{c.contract_number} - {c.contract_title}", c.id) for c in contracts],
                placeholder="-- No contract --",
            )

            projects = self._service_registry.project_service.list_projects(self._company_id)
            self._project_combo.set_items(
                [(f"{p.project_code} - {p.project_name}", p.id) for p in projects],
                placeholder="-- No project --",
            )

            self._type_combo.value_changed.connect(self._on_document_type_changed)
            self._location_combo.value_changed.connect(self._on_data_changed)
            self._contract_combo.value_changed.connect(self._on_data_changed)
            self._project_combo.value_changed.connect(self._on_data_changed)
            self._date_edit.dateChanged.connect(self._on_data_changed)
            self._reference_input.textChanged.connect(self._on_data_changed)
            self._notes_input.textChanged.connect(self._on_data_changed)
            self._lines_grid.lines_changed.connect(self._on_data_changed)
        except Exception as exc:
            self._show_error(f"Failed to load reference data: {exc}")

    def _load_document(self) -> None:
        if self._document_id is None:
            return
        try:
            doc = self._service_registry.inventory_document_service.get_inventory_document(
                self._company_id, self._document_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._type_combo.set_current_value(doc.document_type_code)
        self._location_combo.set_current_value(doc.location_id)
        self._contract_combo.set_current_value(doc.contract_id)
        self._project_combo.set_current_value(doc.project_id)
        self._date_edit.setDate(doc.document_date)
        self._reference_input.setText(doc.reference_number or "")
        self._notes_input.setPlainText(doc.notes or "")
        self._lines_grid.set_lines(doc.lines)

        self._on_document_type_changed()
        self._update_totals()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_data_changed(self, *_args: object) -> None:
        self._update_totals()

    def _on_document_type_changed(self, *_args: object) -> None:
        document_type = self._type_combo.current_value()
        if document_type == "receipt":
            message = "Receipts require positive quantities and a positive unit cost on each line."
        elif document_type == "issue":
            message = (
                "Issues require positive quantities. Enter a unit cost only when you want a draft value preview."
            )
        else:
            message = (
                "Adjustments can increase or decrease stock. Positive adjustments usually need a unit cost."
            )
        self._document_hint_label.setText(message)
        self._update_totals()

    def _update_totals(self) -> None:
        total, _, _, line_count = self._lines_grid.calculate_totals()
        self._line_count_label.setText("1 line" if line_count == 1 else f"{line_count} lines")
        self._total_value.setText(f"{total:,.2f}")

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        doc_type = self._type_combo.current_value()
        if not doc_type:
            self._show_error("Document type is required.")
            return

        location_id = self._location_combo.current_value()
        doc_date = self._date_edit.date().toPython()
        reference = self._reference_input.text().strip() or None
        notes = self._notes_input.toPlainText().strip() or None
        contract_id = self._contract_combo.current_value()
        project_id = self._project_combo.current_value()

        line_commands = self._lines_grid.get_line_commands()
        if not line_commands:
            self._show_error("Add at least one line with an item selected.")
            return

        try:
            if self._document_id is None:
                result = self._service_registry.inventory_document_service.create_draft_document(
                    self._company_id,
                    CreateInventoryDocumentCommand(
                        document_type_code=doc_type,
                        document_date=doc_date,
                        location_id=location_id,
                        reference_number=reference,
                        notes=notes,
                        contract_id=contract_id,
                        project_id=project_id,
                        lines=tuple(line_commands),
                    ),
                )
            else:
                result = self._service_registry.inventory_document_service.update_draft_document(
                    self._company_id,
                    self._document_id,
                    UpdateInventoryDocumentCommand(
                        document_type_code=doc_type,
                        document_date=doc_date,
                        location_id=location_id,
                        reference_number=reference,
                        notes=notes,
                        contract_id=contract_id,
                        project_id=project_id,
                        lines=tuple(line_commands),
                    ),
                )
            self._saved_document = result
            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
