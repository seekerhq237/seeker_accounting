from __future__ import annotations

import logging

from datetime import date
from decimal import Decimal

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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.job_costing.dto.project_commitment_commands import (
    ApproveProjectCommitmentCommand,
    CancelProjectCommitmentCommand,
    CloseProjectCommitmentCommand,
    CreateProjectCommitmentCommand,
    UpdateProjectCommitmentCommand,
)
from seeker_accounting.modules.job_costing.dto.project_commitment_dto import (
    ProjectCommitmentDetailDTO,
    ProjectCommitmentListItemDTO,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_COMMITMENT_TYPE_OPTIONS = (
    ("manual_reservation", "Manual Reservation"),
    ("subcontract", "Subcontract"),
    ("materials", "Materials"),
    ("labor", "Labor"),
    ("expense", "Expense"),
    ("other", "Other"),
)


# ── Commitment Form Dialog ───────────────────────────────────────────────


class ProjectCommitmentFormDialog(BaseDialog):
    """Create or edit a single project commitment."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        commitment_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._commitment_id = commitment_id
        self._saved: ProjectCommitmentDetailDTO | None = None

        title = "New Commitment" if commitment_id is None else "Edit Commitment"
        super().__init__(title, parent, help_key="dialog.project_commitment")
        self.setObjectName("ProjectCommitmentFormDialog")
        self.resize(640, 560)

        intro = QLabel(f"Commitment for project {project_code}.", self)
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

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
            save_btn.setText("Create" if commitment_id is None else "Save Changes")
            save_btn.setProperty("variant", "primary")

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")

        self._load_suppliers()
        self._load_currencies()

        if self._commitment_id is not None:
            self._load_commitment()

    @property
    def saved_commitment(self) -> ProjectCommitmentDetailDTO | None:
        return self._saved

    @classmethod
    def create_commitment(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        parent: QWidget | None = None,
    ) -> ProjectCommitmentDetailDTO | None:
        dialog = cls(service_registry, company_id, project_id, project_code, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_commitment
        return None

    @classmethod
    def edit_commitment(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        commitment_id: int,
        parent: QWidget | None = None,
    ) -> ProjectCommitmentDetailDTO | None:
        dialog = cls(
            service_registry, company_id, project_id, project_code,
            commitment_id=commitment_id, parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_commitment
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

        title = QLabel("Commitment Details", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._number_edit = QLineEdit(card)
        self._number_edit.setPlaceholderText("e.g. CMT-001")
        grid.addWidget(create_field_block("Commitment Number", self._number_edit), 0, 0)

        self._type_combo = QComboBox(card)
        for code, label in _COMMITMENT_TYPE_OPTIONS:
            self._type_combo.addItem(label, code)
        grid.addWidget(create_field_block("Type", self._type_combo), 0, 1)

        self._date_edit = QDateEdit(card)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDate(date.today())
        grid.addWidget(create_field_block("Commitment Date", self._date_edit), 1, 0)

        self._required_date_edit = QDateEdit(card)
        self._required_date_edit.setCalendarPopup(True)
        self._required_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._required_date_edit.setSpecialValueText(" ")
        self._required_date_edit.setMinimumDate(date(2000, 1, 1))
        self._required_date_edit.setDate(self._required_date_edit.minimumDate())
        grid.addWidget(create_field_block("Required Date", self._required_date_edit, "Optional"), 1, 1)

        self._currency_combo = QComboBox(card)
        grid.addWidget(create_field_block("Currency", self._currency_combo), 2, 0)

        self._exchange_rate_edit = QLineEdit(card)
        self._exchange_rate_edit.setPlaceholderText("e.g. 1.000000")
        grid.addWidget(create_field_block("Exchange Rate", self._exchange_rate_edit, "Optional"), 2, 1)

        self._supplier_combo = QComboBox(card)
        grid.addWidget(create_field_block("Supplier", self._supplier_combo, "Optional"), 3, 0, 1, 1)

        self._reference_edit = QLineEdit(card)
        self._reference_edit.setPlaceholderText("Optional reference")
        grid.addWidget(create_field_block("Reference Number", self._reference_edit, "Optional"), 3, 1)

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
        self._notes_edit.setFixedHeight(70)
        layout.addWidget(self._notes_edit)
        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_suppliers(self) -> None:
        self._supplier_combo.clear()
        self._supplier_combo.addItem("(None)", None)
        try:
            suppliers = self._service_registry.supplier_service.list_suppliers(self._company_id, active_only=True)
            for s in suppliers:
                self._supplier_combo.addItem(s.display_name, s.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_currencies(self) -> None:
        self._currency_combo.clear()
        try:
            currencies = self._service_registry.reference_data_service.list_currencies(active_only=True)
            for c in currencies:
                self._currency_combo.addItem(f"{c.code} — {c.name}", c.code)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_commitment(self) -> None:
        try:
            detail = self._service_registry.project_commitment_service.get_commitment_detail(
                self._commitment_id or 0,
                self._company_id,
            )
        except NotFoundError as exc:
            show_error(self, "Not Found", str(exc))
            self.reject()
            return

        self._number_edit.setText(detail.commitment_number)
        self._number_edit.setReadOnly(True)

        idx = self._type_combo.findData(detail.commitment_type_code)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)

        self._date_edit.setDate(detail.commitment_date)

        if detail.required_date is not None:
            self._required_date_edit.setDate(detail.required_date)

        if detail.currency_code:
            cidx = self._currency_combo.findData(detail.currency_code)
            if cidx >= 0:
                self._currency_combo.setCurrentIndex(cidx)

        if detail.exchange_rate is not None:
            self._exchange_rate_edit.setText(str(detail.exchange_rate))

        if detail.supplier_id is not None:
            sidx = self._supplier_combo.findData(detail.supplier_id)
            if sidx >= 0:
                self._supplier_combo.setCurrentIndex(sidx)

        self._reference_edit.setText(detail.reference_number or "")
        self._notes_edit.setPlainText(detail.notes or "")

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

        commitment_number = self._number_edit.text().strip()
        if not commitment_number:
            self._set_error("Commitment number is required.")
            return

        commitment_type = self._type_combo.currentData()
        commitment_date = self._date_edit.date().toPython()
        currency_code = self._currency_combo.currentData()
        if not currency_code:
            self._set_error("Currency is required.")
            return

        required_date = self._required_date_edit.date().toPython()
        if required_date == self._required_date_edit.minimumDate().toPython():
            required_date = None

        exchange_rate_text = self._exchange_rate_edit.text().strip()
        exchange_rate = None
        if exchange_rate_text:
            try:
                exchange_rate = Decimal(exchange_rate_text)
            except Exception:
                self._set_error("Exchange rate must be a valid number.")
                return

        supplier_id = self._supplier_combo.currentData()
        reference = self._reference_edit.text().strip() or None
        notes = self._notes_edit.toPlainText().strip() or None

        svc = self._service_registry.project_commitment_service

        try:
            if self._commitment_id is None:
                result = svc.create_commitment(
                    CreateProjectCommitmentCommand(
                        company_id=self._company_id,
                        project_id=self._project_id,
                        commitment_number=commitment_number,
                        commitment_type_code=commitment_type,
                        commitment_date=commitment_date,
                        currency_code=currency_code,
                        supplier_id=supplier_id,
                        required_date=required_date,
                        exchange_rate=exchange_rate,
                        reference_number=reference,
                        notes=notes,
                    )
                )
            else:
                result = svc.update_commitment(
                    self._commitment_id,
                    self._company_id,
                    UpdateProjectCommitmentCommand(
                        commitment_type_code=commitment_type,
                        commitment_date=commitment_date,
                        currency_code=currency_code,
                        supplier_id=supplier_id,
                        required_date=required_date,
                        exchange_rate=exchange_rate,
                        reference_number=reference,
                        notes=notes,
                    ),
                )
            self._saved = result
            self.accept()
        except (ValidationError, NotFoundError, ConflictError) as exc:
            self._set_error(str(exc))


# ── Commitments List Dialog ──────────────────────────────────────────────


class ProjectCommitmentsDialog(BaseDialog):
    """List and manage commitments for a specific project."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Commitments — {project_code}", parent, help_key="dialog.project_commitment_list")
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._project_code = project_code
        self._commitments: list[ProjectCommitmentListItemDTO] = []

        self.setObjectName("ProjectCommitmentsDialog")
        self.resize(1020, 560)

        self.body_layout.addWidget(self._build_toolbar())
        self.body_layout.addWidget(self._build_table_card(), 1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        close_btn = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setProperty("variant", "secondary")

        self._reload()

    @classmethod
    def manage_commitments(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, project_id, project_code, parent=parent)
        dialog.exec()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget(self)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._new_button = QPushButton("New Commitment", toolbar)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit", toolbar)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit)
        layout.addWidget(self._edit_button)

        self._lines_button = QPushButton("Lines", toolbar)
        self._lines_button.setProperty("variant", "secondary")
        self._lines_button.clicked.connect(self._open_lines)
        layout.addWidget(self._lines_button)

        self._approve_button = QPushButton("Approve", toolbar)
        self._approve_button.setProperty("variant", "primary")
        self._approve_button.clicked.connect(self._approve_commitment)
        layout.addWidget(self._approve_button)

        self._close_button = QPushButton("Close", toolbar)
        self._close_button.setProperty("variant", "secondary")
        self._close_button.clicked.connect(self._close_commitment)
        layout.addWidget(self._close_button)

        self._cancel_button = QPushButton("Cancel", toolbar)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_commitment)
        layout.addWidget(self._cancel_button)

        layout.addStretch(1)

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
        self._table.setObjectName("ProjectCommitmentsTable")
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ("Number", "Type", "Date", "Currency", "Total Amount", "Supplier", "Reference", "Status")
        )
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(lambda *_: self._open_edit())
        layout.addWidget(self._table)
        return card

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _reload(self) -> None:
        try:
            self._commitments = self._service_registry.project_commitment_service.list_commitments(
                self._project_id
            )
        except Exception as exc:
            show_error(self, "Commitments", str(exc))
            self._commitments = []

        self._populate_table()
        self._update_action_state()

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for c in self._commitments:
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(c.commitment_number)
            num_item.setData(Qt.ItemDataRole.UserRole, c.id)
            self._table.setItem(row, 0, num_item)

            type_item = QTableWidgetItem(c.commitment_type_code)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, type_item)

            self._table.setItem(row, 2, QTableWidgetItem(str(c.commitment_date)))

            currency_item = QTableWidgetItem(c.currency_code)
            currency_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, currency_item)

            amount_item = QTableWidgetItem(f"{c.total_amount:,.2f}")
            amount_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(row, 4, amount_item)

            self._table.setItem(row, 5, QTableWidgetItem(c.supplier_name or ""))
            self._table.setItem(row, 6, QTableWidgetItem(c.reference_number or ""))

            status_item = QTableWidgetItem(c.status_code)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 7, status_item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.Stretch)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._commitments)
        self._count_label.setText(
            f"{count} commitment" if count == 1 else f"{count} commitments"
        )

    def _selected_commitment(self) -> ProjectCommitmentListItemDTO | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        commitment_id = item.data(Qt.ItemDataRole.UserRole)
        for c in self._commitments:
            if c.id == commitment_id:
                return c
        return None

    def _update_action_state(self) -> None:
        selected = self._selected_commitment()
        has_selection = selected is not None
        status = selected.status_code if selected else ""

        self._edit_button.setEnabled(has_selection and status == "draft")
        self._lines_button.setEnabled(has_selection)
        self._approve_button.setEnabled(has_selection and status == "draft")
        self._close_button.setEnabled(has_selection and status == "approved")
        self._cancel_button.setEnabled(has_selection and status == "draft")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create(self) -> None:
        result = ProjectCommitmentFormDialog.create_commitment(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            project_code=self._project_code,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _open_edit(self) -> None:
        selected = self._selected_commitment()
        if selected is None or selected.status_code != "draft":
            return
        result = ProjectCommitmentFormDialog.edit_commitment(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            project_code=self._project_code,
            commitment_id=selected.id,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _open_lines(self) -> None:
        selected = self._selected_commitment()
        if selected is None:
            return
        from seeker_accounting.modules.job_costing.ui.project_commitment_lines_dialog import (
            ProjectCommitmentLinesDialog,
        )

        ProjectCommitmentLinesDialog.manage_lines(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            commitment_id=selected.id,
            commitment_number=selected.commitment_number,
            commitment_status=selected.status_code,
            parent=self,
        )
        self._reload()

    def _approve_commitment(self) -> None:
        selected = self._selected_commitment()
        if selected is None or selected.status_code != "draft":
            return
        choice = QMessageBox.question(
            self,
            "Approve Commitment",
            f"Approve commitment {selected.commitment_number}?\n\n"
            "This commitment will become immutable.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            user_id = self._service_registry.app_context.current_user_id or 0
            self._service_registry.project_commitment_service.approve_commitment(
                ApproveProjectCommitmentCommand(
                    commitment_id=selected.id,
                    company_id=self._company_id,
                    approved_by_user_id=user_id,
                )
            )
            show_info(self, "Approved", "Commitment approved.")
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Approval Failed", str(exc))
        self._reload()

    def _close_commitment(self) -> None:
        selected = self._selected_commitment()
        if selected is None or selected.status_code != "approved":
            return
        choice = QMessageBox.question(
            self,
            "Close Commitment",
            f"Close commitment {selected.commitment_number}?\n\n"
            "This action cannot be undone.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.project_commitment_service.close_commitment(
                CloseProjectCommitmentCommand(
                    commitment_id=selected.id,
                    company_id=self._company_id,
                )
            )
            show_info(self, "Closed", "Commitment closed.")
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Close Failed", str(exc))
        self._reload()

    def _cancel_commitment(self) -> None:
        selected = self._selected_commitment()
        if selected is None or selected.status_code != "draft":
            return
        choice = QMessageBox.question(
            self,
            "Cancel Commitment",
            f"Cancel commitment {selected.commitment_number}?\n\n"
            "This action cannot be undone.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.project_commitment_service.cancel_commitment(
                CancelProjectCommitmentCommand(
                    commitment_id=selected.id,
                    company_id=self._company_id,
                )
            )
            show_info(self, "Cancelled", "Commitment cancelled.")
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Cancel Failed", str(exc))
        self._reload()
