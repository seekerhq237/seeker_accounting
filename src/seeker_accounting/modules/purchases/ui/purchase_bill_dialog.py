from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
import logging

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.purchases.dto.purchase_bill_commands import (
    CreatePurchaseBillCommand,
    UpdatePurchaseBillCommand,
)
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import PurchaseBillDetailDTO
from seeker_accounting.modules.purchases.ui.purchase_bill_lines_grid import PurchaseBillLinesGrid
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.document import DocumentWorkspace, DocumentWorkspaceSpec
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox


_log = logging.getLogger(__name__)


class PurchaseBillDialog(QDialog):
    # Emitted whenever draft content changes — the ambient overlay listens
    # to this signal while the dialog is open to keep its context fresh.
    ambient_context_changed = Signal()

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        bill_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._bill_id = bill_id
        self._saved_bill: PurchaseBillDetailDTO | None = None

        is_edit = bill_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Purchase Bill - {company_name}")
        self.setModal(True)
        apply_window_size(self, "modules.purchases.ui.purchase.bill.dialog.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._workspace = DocumentWorkspace(
            DocumentWorkspaceSpec(
                document_type_label="Purchase Bill",
                show_command_row=True,
                show_identity_strip=True,
                show_metadata_strip=True,
                show_totals_dock=True,
                show_action_rail=True,
            ),
            self,
        )
        layout.addWidget(self._workspace, 1)

        self._status_chip = self._build_status_chip("Draft", "warning")
        self._build_command_row(is_edit)
        self._build_metadata()
        self._workspace.set_lines_widget(self._build_lines_section())
        self._build_totals_dock()

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._build_action_rail(is_edit)

        self._refresh_identity()

        self._load_reference_data()
        if is_edit:
            self._load_bill()

        from seeker_accounting.shared.ui.help_button import install_help_button

        install_help_button(self, "dialog.purchase_bill")

    @property
    def saved_bill(self) -> PurchaseBillDetailDTO | None:
        return self._saved_bill

    @classmethod
    def create_bill(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> PurchaseBillDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_bill
        return None

    @classmethod
    def edit_bill(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        bill_id: int,
        parent: QWidget | None = None,
    ) -> PurchaseBillDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, bill_id=bill_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_bill
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_status_chip(self, text: str, tone: str) -> QLabel:
        chip = QLabel(text.upper(), self)
        chip.setProperty("chipTone", tone)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return chip

    def _build_command_row(self, is_edit: bool) -> None:
        row = self._workspace.command_row
        row_layout = row.layout()

        caption = QLabel("Draft workspace", row)
        caption.setObjectName("PanelHeaderCaption")
        row_layout.addWidget(caption)
        row_layout.addStretch(1)

        recalc_button = QPushButton("Recalculate", row)
        recalc_button.setProperty("variant", "ghost")
        recalc_button.clicked.connect(self._update_totals)
        row_layout.addWidget(recalc_button)

        save_button = QPushButton("Save Draft" if not is_edit else "Save Changes", row)
        save_button.setProperty("variant", "primary")
        save_button.clicked.connect(self._handle_submit)
        row_layout.addWidget(save_button)

    def _build_metadata(self) -> None:
        strip = self._workspace.metadata_strip

        self._supplier_combo = SearchableComboBox(strip)
        self._workspace.add_metadata_pair(0, "Supplier", self._supplier_combo)

        self._supplier_bill_reference_input = QLineEdit(strip)
        self._supplier_bill_reference_input.setPlaceholderText("Optional reference")
        self._workspace.add_metadata_pair(1, "Supplier Bill Ref", self._supplier_bill_reference_input)

        self._bill_date_edit = QDateEdit(strip)
        self._bill_date_edit.setCalendarPopup(True)
        self._bill_date_edit.setDate(date.today())
        self._workspace.add_metadata_pair(2, "Bill Date", self._bill_date_edit)

        self._due_date_edit = QDateEdit(strip)
        self._due_date_edit.setCalendarPopup(True)
        self._due_date_edit.setDate(date.today())
        self._workspace.add_metadata_pair(3, "Due Date", self._due_date_edit)

        self._currency_combo = SearchableComboBox(strip)
        self._workspace.add_metadata_pair(4, "Currency", self._currency_combo)

        self._exchange_rate_input = QLineEdit(strip)
        self._exchange_rate_input.setPlaceholderText("Base currency")
        self._exchange_rate_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._exchange_rate_input.setEnabled(False)
        self._workspace.add_metadata_pair(5, "Rate", self._exchange_rate_input)

        self._contract_combo = SearchableComboBox(strip)
        self._workspace.add_metadata_pair(6, "Contract", self._contract_combo)

        self._project_combo = SearchableComboBox(strip)
        self._workspace.add_metadata_pair(7, "Project", self._project_combo)

        self._notes_input = QPlainTextEdit(strip)
        self._notes_input.setMinimumHeight(56)
        self._notes_input.setMaximumHeight(84)
        self._notes_input.setPlaceholderText("Notes")
        self._workspace.add_metadata_full_row(8, "Notes", self._notes_input)

        self._tax_point_date_edit = QDateEdit(strip)
        self._tax_point_date_edit.setCalendarPopup(True)
        self._tax_point_date_edit.setDate(date.today())
        self._workspace.add_metadata_pair(10, "Tax Point Date", self._tax_point_date_edit)
        self._tax_point_date_edit.setVisible(False)

    def _build_lines_section(self) -> QWidget:
        self._lines_grid = PurchaseBillLinesGrid(self._service_registry, self._company_id, self)
        return self._lines_grid

    def _build_totals_dock(self) -> None:
        dock = self._workspace.totals_dock
        dock_layout = dock.layout()

        self._line_count_label = QLabel("0 lines", dock)
        self._line_count_label.setObjectName("MetaLabel")
        dock_layout.addWidget(self._line_count_label)

        def add_row(label_text: str, value_object: str) -> QLabel:
            row = QFrame(dock)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            lbl = QLabel(label_text, row)
            lbl.setObjectName("MetaLabel")
            row_layout.addWidget(lbl)
            row_layout.addStretch(1)
            value = QLabel("0.00", row)
            value.setObjectName(value_object)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(value)
            dock_layout.addWidget(row)
            return value

        self._subtotal_value = add_row("Subtotal", "MetaValue")
        self._tax_value = add_row("Tax", "MetaValue")

        separator = QFrame(dock)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("TotalsSeparator")
        dock_layout.addWidget(separator)

        self._total_value = add_row("Total", "TotalsGrandTotal")
        dock_layout.addStretch(1)

    def _build_action_rail(self, is_edit: bool) -> None:
        rail = self._workspace.action_rail
        rail_layout = rail.layout()

        rail_layout.addStretch(1)

        cancel_button = QPushButton("Cancel", rail)
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        rail_layout.addWidget(cancel_button)

        save_button = QPushButton("Save Changes" if is_edit else "Create Bill", rail)
        save_button.setProperty("variant", "primary")
        save_button.clicked.connect(self._handle_submit)
        rail_layout.addWidget(save_button)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            suppliers = self._service_registry.supplier_service.list_suppliers(
                self._company_id, active_only=True
            )
            self._supplier_combo.set_items(
                [(f"{s.supplier_code} - {s.display_name}", s.id) for s in suppliers],
                placeholder="-- Select supplier --",
                search_texts=[f"{s.supplier_code} {s.display_name}" for s in suppliers],
            )

            contracts = self._service_registry.contract_service.list_contracts(self._company_id)
            self._contract_combo.set_items(
                [
                    (f"{c.contract_number} - {c.contract_title}", c.id)
                    for c in contracts
                ],
                placeholder="-- No contract --",
            )

            projects = self._service_registry.project_service.list_projects(self._company_id)
            self._project_combo.set_items(
                [
                    (f"{p.project_code} - {p.project_name}", p.id)
                    for p in projects
                ],
                placeholder="-- No project --",
            )

            currencies = self._service_registry.reference_data_service.list_active_currencies()
            self._currency_combo.set_items(
                [(currency.code, currency.code) for currency in currencies],
                placeholder="-- Select currency --",
            )

            base_currency_code = self._base_currency_code()
            if base_currency_code:
                self._currency_combo.set_current_value(base_currency_code)

            self._supplier_combo.value_changed.connect(self._on_data_changed)
            self._contract_combo.value_changed.connect(self._on_data_changed)
            self._project_combo.value_changed.connect(self._on_data_changed)
            self._bill_date_edit.dateChanged.connect(self._on_data_changed)
            self._due_date_edit.dateChanged.connect(self._on_data_changed)
            self._currency_combo.value_changed.connect(self._on_currency_changed)
            self._exchange_rate_input.textChanged.connect(self._on_data_changed)
            self._supplier_bill_reference_input.textChanged.connect(self._on_data_changed)
            self._notes_input.textChanged.connect(self._on_data_changed)
            self._lines_grid.lines_changed.connect(self._on_data_changed)
            self._on_currency_changed(self._currency_combo.current_value())

            # Show tax_point_date field only if company uses tax-point scheme
            try:
                tp = self._service_registry.company_tax_profile_service.get_or_default(self._company_id)
                if tp.vat_uses_tax_point:
                    self._show_tax_point_row(True)
            except Exception:
                pass
        except AppError as exc:
            self._show_error(f"Failed to load reference data: {exc}")

        except Exception:
            _log.exception("Unexpected error")
            self._show_error("An unexpected error occurred. See application log for details.")

    def _load_bill(self) -> None:
        if self._bill_id is None:
            return

        try:
            bill = self._service_registry.purchase_bill_service.get_purchase_bill(
                self._company_id, self._bill_id
            )

            self._supplier_combo.set_current_value(bill.supplier_id)
            self._contract_combo.set_current_value(bill.contract_id)
            self._project_combo.set_current_value(bill.project_id)

            self._bill_date_edit.setDate(bill.bill_date)
            self._due_date_edit.setDate(bill.due_date)

            if bill.tax_point_date is not None:
                self._tax_point_date_edit.setDate(bill.tax_point_date)

            self._currency_combo.set_current_value(bill.currency_code)

            if bill.exchange_rate is not None:
                self._exchange_rate_input.setText(str(bill.exchange_rate))

            self._supplier_bill_reference_input.setText(bill.supplier_bill_reference or "")
            self._notes_input.setPlainText(bill.notes or "")
            self._lines_grid.set_lines(bill.lines)

            self._on_currency_changed(self._currency_combo.current_value())
            self._update_totals()
            self._refresh_identity()
        except AppError as exc:
            self._show_error(f"Failed to load bill: {exc}")

        except Exception:
            _log.exception("Unexpected error")
            self._show_error("An unexpected error occurred. See application log for details.")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_data_changed(self, *_args: object) -> None:
        self._update_totals()
        self._refresh_identity()
        self.ambient_context_changed.emit()

    def get_ambient_context(self) -> dict[str, object]:
        """Implement the ambient page contract so the overlay gets draft state."""
        lines: list = []
        if hasattr(self, "_lines_grid"):
            try:
                lines = self._lines_grid.get_line_commands()
            except Exception:
                pass
        has_missing_tax = any(
            getattr(ln, "tax_code_id", None) is None for ln in lines
        )

        # Check if the selected supplier has a tax identifier (NIU / VAT reg).
        supplier_tax_incomplete = False
        supplier_id = None
        if hasattr(self, "_supplier_combo"):
            supplier_id = self._supplier_combo.current_value()
        if isinstance(supplier_id, int):
            try:
                supplier = self._service_registry.supplier_service.get_supplier(
                    self._company_id, supplier_id
                )
                supplier_tax_incomplete = not bool(
                    getattr(supplier, "tax_identifier", None)
                )
            except Exception:
                pass

        return {
            "has_line_without_tax": has_missing_tax,
            "supplier_tax_details_incomplete": supplier_tax_incomplete,
        }

    def _on_currency_changed(self, _value: object) -> None:
        current_currency = self._currency_combo.current_value()
        base_currency = self._base_currency_code()
        is_base_currency = bool(current_currency) and current_currency == base_currency

        if is_base_currency:
            self._exchange_rate_input.clear()
            self._exchange_rate_input.setEnabled(False)
            self._exchange_rate_input.setPlaceholderText("Base currency")
        else:
            self._exchange_rate_input.setEnabled(True)
            self._exchange_rate_input.setPlaceholderText("Required for foreign currency")

        self._update_totals()

    def _update_totals(self) -> None:
        subtotal, tax_total, total, line_count = self._lines_grid.calculate_totals()
        self._line_count_label.setText("1 line" if line_count == 1 else f"{line_count} lines")
        self._subtotal_value.setText(f"{subtotal:,.2f}")
        self._tax_value.setText(f"{tax_total:,.2f}")
        self._total_value.setText(f"{total:,.2f}")

    def _refresh_identity(self) -> None:
        bill_date = self._bill_date_edit.date().toPython() if hasattr(self, "_bill_date_edit") else None
        due_date = self._due_date_edit.date().toPython() if hasattr(self, "_due_date_edit") else None

        dates_text = ""
        if bill_date is not None and due_date is not None:
            dates_text = f"{bill_date.strftime('%d %b %Y')} / Due {due_date.strftime('%d %b %Y')}"

        counterparty = ""
        if hasattr(self, "_supplier_combo"):
            counterparty = self._supplier_combo.currentText().strip()

        self._workspace.set_identity(
            document_label="Purchase Bill",
            document_number="New" if self._bill_id is None else f"#{self._bill_id}",
            status_widget=self._status_chip,
            dates_text=dates_text,
            counterparty=counterparty,
        )

    def _handle_submit(self) -> None:
        self._error_label.hide()

        try:
            supplier_id = self._supplier_combo.current_value()
            if supplier_id is None:
                self._show_error("Supplier is required")
                return

            bill_date = self._bill_date_edit.date().toPython()
            due_date = self._due_date_edit.date().toPython()
            currency_code = self._currency_combo.current_value()
            if currency_code is None:
                self._show_error("Currency is required")
                return

            exchange_rate: Decimal | None = None
            if self._exchange_rate_input.text().strip():
                try:
                    exchange_rate = Decimal(self._exchange_rate_input.text().replace(",", "").strip())
                except InvalidOperation:
                    self._show_error("Invalid exchange rate")
                    return

            supplier_bill_reference = self._supplier_bill_reference_input.text().strip() or None
            notes = self._notes_input.toPlainText().strip() or None
            contract_id = self._contract_combo.current_value()
            project_id = self._project_combo.current_value()
            lines = tuple(self._lines_grid.get_line_commands())

            if not lines:
                self._show_error("Bill must have at least one line")
                return

            if self._bill_id is None:
                command = CreatePurchaseBillCommand(
                    supplier_id=supplier_id,
                    bill_date=bill_date,
                    due_date=due_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    supplier_bill_reference=supplier_bill_reference,
                    notes=notes,
                    contract_id=contract_id,
                    project_id=project_id,
                    tax_point_date=self._tax_point_date_edit.date().toPython() if self._tax_point_date_edit.isVisible() else None,
                    lines=lines,
                )
                self._saved_bill = self._service_registry.purchase_bill_service.create_draft_bill(
                    self._company_id, command
                )
            else:
                command = UpdatePurchaseBillCommand(
                    supplier_id=supplier_id,
                    bill_date=bill_date,
                    due_date=due_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    supplier_bill_reference=supplier_bill_reference,
                    notes=notes,
                    contract_id=contract_id,
                    project_id=project_id,
                    tax_point_date=self._tax_point_date_edit.date().toPython() if self._tax_point_date_edit.isVisible() else None,
                    lines=lines,
                )
                self._saved_bill = self._service_registry.purchase_bill_service.update_draft_bill(
                    self._company_id, self._bill_id, command
                )

            self.accept()
        except ValidationError as exc:
            self._show_error(str(exc))
        except AppError as exc:
            self._show_error(f"Failed to save bill: {exc}")

        except Exception:
            _log.exception("Unexpected error")
            self._show_error("An unexpected error occurred. See application log for details.")

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _show_tax_point_row(self, visible: bool) -> None:
        """Show or hide the Tax Point Date field and its label in the metadata grid."""
        grid = self._workspace.metadata_grid
        # row 10 with 2 columns → grid_row=5, pair_index=0 → label_col=0, value_col=1
        for col in (0, 1):
            item = grid.itemAtPosition(5, col)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setVisible(visible)

    def _base_currency_code(self) -> str | None:
        return getattr(self._service_registry.active_company_context, "base_currency_code", None)
