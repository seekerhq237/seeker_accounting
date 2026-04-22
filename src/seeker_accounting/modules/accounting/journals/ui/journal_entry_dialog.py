from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.accounting.journals.dto.journal_commands import (
    CreateJournalEntryCommand,
    JournalLineCommand,
    UpdateJournalEntryCommand,
)
from seeker_accounting.modules.accounting.journals.dto.journal_dto import JournalEntryDetailDTO
from seeker_accounting.modules.accounting.journals.ui.journal_entry_lines_grid import JournalEntryLinesGrid
from seeker_accounting.modules.accounting.journals.ui.line_allocation_dialog import LineAllocationDialog
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.guided_resolution_coordinator import GuidedResolutionCoordinator
from seeker_accounting.shared.ui.message_boxes import show_error


class JournalEntryDialog(BaseDialog):
    JOURNAL_TYPE_OPTIONS = (
        ("GENERAL", "General"),
        ("ADJUSTMENT", "Adjustment"),
        ("OPENING", "Opening"),
        ("CLOSING", "Closing"),
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        journal_entry_id: int | None = None,
        read_only: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._journal_entry_id = journal_entry_id
        self._saved_entry: JournalEntryDetailDTO | None = None
        self._loaded_entry: JournalEntryDetailDTO | None = None
        self._read_only = read_only

        title = "New Journal Entry" if journal_entry_id is None else "Journal Entry"
        super().__init__(title, parent, help_key="dialog.journal_entry")
        self.setObjectName("JournalEntryDialog")
        self.resize(960, 680)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_header_section())
        self.body_layout.addWidget(self._build_lines_section(), 1)
        self.body_layout.addWidget(self._build_totals_section())

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        self._save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if self._save_button is not None:
            self._save_button.setText("Save Draft")
            self._save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._save_and_new_btn: QPushButton | None = None
        if journal_entry_id is None:
            self._save_and_new_btn = self.button_box.addButton(
                "Save & New", QDialogButtonBox.ButtonRole.ActionRole
            )
            self._save_and_new_btn.setProperty("variant", "secondary")
            self._save_and_new_btn.clicked.connect(self._handle_save_and_new)

        self._populate_journal_type_combo()
        if journal_entry_id is not None:
            self._load_entry()

        self._apply_read_only_mode()
        self._update_totals()

    @property
    def saved_entry(self) -> JournalEntryDetailDTO | None:
        return self._saved_entry

    # -- Factory methods ---------------------------------------------------

    @classmethod
    def create_journal(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
        *,
        draft_snapshot: dict | None = None,
    ) -> JournalEntryDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if draft_snapshot is not None:
            dialog._restore_from_snapshot(draft_snapshot)
        dialog.exec()
        # Return the last saved entry regardless of how the dialog was closed.
        # Entries saved via "Save & New" are already persisted; the caller
        # should reload if saved_entry is not None.
        return dialog.saved_entry

    @classmethod
    def edit_journal(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        journal_entry_id: int,
        parent: QWidget | None = None,
    ) -> JournalEntryDetailDTO | None:
        dialog = cls(
            service_registry,
            company_id,
            company_name,
            journal_entry_id=journal_entry_id,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_entry
        return None

    @classmethod
    def view_journal(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        journal_entry_id: int,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(
            service_registry,
            company_id,
            company_name,
            journal_entry_id=journal_entry_id,
            read_only=True,
            parent=parent,
        )
        dialog.exec()

    # -- UI construction ---------------------------------------------------

    def _build_header_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(0)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        self._journal_type_combo = QComboBox(card)
        grid.addWidget(create_field_block("Entry Type", self._journal_type_combo), 0, 0)

        self._transaction_date_edit = QDateEdit(card)
        self._transaction_date_edit.setCalendarPopup(True)
        self._transaction_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._transaction_date_edit.setDate(QDate.currentDate())
        grid.addWidget(create_field_block("Transaction Date", self._transaction_date_edit), 0, 1)

        self._reference_edit = QLineEdit(card)
        self._reference_edit.setPlaceholderText("Optional reference")
        grid.addWidget(create_field_block("Reference", self._reference_edit), 1, 0)

        self._description_edit = QLineEdit(card)
        self._description_edit.setPlaceholderText("Short entry description")
        self._description_edit.textChanged.connect(self._on_description_changed)
        grid.addWidget(create_field_block("Description", self._description_edit), 1, 1)

        layout.addLayout(grid)
        return card

    def _build_lines_section(self) -> QWidget:
        """Editable lines grid with allocation toolbar."""
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        # ── Allocation toolbar ───────────────────────────────────────
        self._alloc_toolbar = QWidget(container)
        toolbar_layout = QHBoxLayout(self._alloc_toolbar)
        toolbar_layout.setContentsMargins(4, 0, 4, 0)
        toolbar_layout.setSpacing(10)

        self._select_all_check = QCheckBox("Select All", self._alloc_toolbar)
        self._select_all_check.stateChanged.connect(self._on_select_all_changed)
        toolbar_layout.addWidget(self._select_all_check)

        self._allocate_btn = QPushButton("Allocate Selected", self._alloc_toolbar)
        self._allocate_btn.setProperty("variant", "secondary")
        self._allocate_btn.setToolTip("Assign selected lines to Contract / Project / Job / Cost Code")
        self._allocate_btn.clicked.connect(self._allocate_selected)
        toolbar_layout.addWidget(self._allocate_btn)

        toolbar_layout.addStretch(1)
        container_layout.addWidget(self._alloc_toolbar)

        # ── Lines grid ───────────────────────────────────────────────
        self._lines_grid = JournalEntryLinesGrid(
            service_registry=self._service_registry,
            company_id=self._company_id,
            parent=container,
        )
        self._lines_grid.lines_changed.connect(self._update_totals)
        container_layout.addWidget(self._lines_grid, 1)

        return container
    def _build_totals_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(24)

        # Total Debit
        total_debit_block = QWidget(card)
        total_debit_layout = QVBoxLayout(total_debit_block)
        total_debit_layout.setContentsMargins(0, 0, 0, 0)
        total_debit_layout.setSpacing(2)
        lbl = QLabel("Total Debit", total_debit_block)
        lbl.setProperty("role", "caption")
        total_debit_layout.addWidget(lbl)
        self._total_debit_value = QLabel("0.00", total_debit_block)
        self._total_debit_value.setObjectName("ToolbarValue")
        self._total_debit_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        total_debit_layout.addWidget(self._total_debit_value)
        layout.addWidget(total_debit_block)

        # Total Credit
        total_credit_block = QWidget(card)
        total_credit_layout = QVBoxLayout(total_credit_block)
        total_credit_layout.setContentsMargins(0, 0, 0, 0)
        total_credit_layout.setSpacing(2)
        lbl2 = QLabel("Total Credit", total_credit_block)
        lbl2.setProperty("role", "caption")
        total_credit_layout.addWidget(lbl2)
        self._total_credit_value = QLabel("0.00", total_credit_block)
        self._total_credit_value.setObjectName("ToolbarValue")
        self._total_credit_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        total_credit_layout.addWidget(self._total_credit_value)
        layout.addWidget(total_credit_block)

        layout.addStretch(1)

        # Balance status
        balance_block = QWidget(card)
        balance_layout = QVBoxLayout(balance_block)
        balance_layout.setContentsMargins(0, 0, 0, 0)
        balance_layout.setSpacing(2)
        lbl3 = QLabel("Balance", balance_block)
        lbl3.setProperty("role", "caption")
        lbl3.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        balance_layout.addWidget(lbl3)
        self._imbalance_value = QLabel("Balanced", balance_block)
        self._imbalance_value.setObjectName("ToolbarValue")
        self._imbalance_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        balance_layout.addWidget(self._imbalance_value)
        layout.addWidget(balance_block)
        return card

    # -- Description default propagation -----------------------------------

    def _on_description_changed(self, text: str) -> None:
        self._lines_grid.set_header_description(text)

    # -- Allocation toolbar ------------------------------------------------

    def _on_select_all_changed(self, state: int) -> None:
        self._lines_grid.set_all_checked(state == Qt.CheckState.Checked.value)

    def _allocate_selected(self) -> None:
        indices = self._lines_grid.get_selected_indices()
        if not indices:
            self._set_error("Select one or more lines to allocate.")
            return
        self._set_error(None)

        current = self._lines_grid.get_allocation(indices[0])
        result = LineAllocationDialog.get_allocation(
            service_registry=self._service_registry,
            company_id=self._company_id,
            current_values=current,
            parent=self,
        )
        if result is not None:
            self._lines_grid.set_allocation(indices, result)

    # -- Reference data & population ---------------------------------------

    def _populate_journal_type_combo(self) -> None:
        self._journal_type_combo.clear()
        for code, label in self.JOURNAL_TYPE_OPTIONS:
            self._journal_type_combo.addItem(label, code)

    # -- Totals ------------------------------------------------------------

    def _update_totals(self) -> None:
        total_debit, total_credit, imbalance, _ = self._lines_grid.calculate_totals()

        self._total_debit_value.setText(f"{total_debit:,.2f}")
        self._total_credit_value.setText(f"{total_credit:,.2f}")
        if imbalance == Decimal("0.00"):
            self._imbalance_value.setText("\u2713  Balanced")
            self._imbalance_value.setProperty("imbalanceState", "balanced")
        else:
            self._imbalance_value.setText(f"\u26a0  Imbalance: {abs(imbalance):,.2f}")
            self._imbalance_value.setProperty("imbalanceState", "imbalanced")
        self._imbalance_value.style().unpolish(self._imbalance_value)
        self._imbalance_value.style().polish(self._imbalance_value)

    # -- Loading (edit / view) ---------------------------------------------

    def _load_entry(self) -> None:
        try:
            entry = self._service_registry.journal_service.get_journal_entry(
                self._company_id,
                self._journal_entry_id or 0,
            )
        except NotFoundError as exc:
            show_error(self, "Journal Entry", str(exc))
            self.reject()
            return

        self._loaded_entry = entry
        index = self._journal_type_combo.findData(entry.journal_type_code)
        self._journal_type_combo.setCurrentIndex(index if index >= 0 else 0)
        if entry.transaction_date is not None:
            self._transaction_date_edit.setDate(
                QDate(entry.transaction_date.year, entry.transaction_date.month, entry.transaction_date.day)
            )
        self._reference_edit.setText(entry.reference_text or "")
        self._description_edit.setText(entry.description or "")

        self._lines_grid.set_lines(entry.lines)

        if entry.status_code != "DRAFT":
            self._read_only = True
            self.setWindowTitle("Journal Entry Detail")

    # -- Read-only mode ----------------------------------------------------

    def _apply_read_only_mode(self) -> None:
        header_widgets = (
            self._journal_type_combo,
            self._transaction_date_edit,
            self._reference_edit,
            self._description_edit,
        )
        for widget in header_widgets:
            widget.setEnabled(not self._read_only)

        self._lines_grid.set_read_only(self._read_only)
        self._alloc_toolbar.setVisible(not self._read_only)

        if self._save_button is not None:
            self._save_button.setVisible(not self._read_only)

        if self._save_and_new_btn is not None:
            self._save_and_new_btn.setVisible(not self._read_only)

        if self._read_only:
            self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
            close_button = self.button_box.button(QDialogButtonBox.StandardButton.Close)
            if close_button is not None:
                close_button.setProperty("variant", "secondary")
                close_button.clicked.connect(self.reject)

    # -- Error display -----------------------------------------------------

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    # -- Save & New --------------------------------------------------------

    def _handle_save_and_new(self) -> None:
        """Save the current draft then reset the form for a new entry, keeping the transaction date."""
        self._set_error(None)

        line_commands = self._lines_grid.get_line_commands()
        if len(line_commands) < 2:
            self._set_error("A journal entry requires at least two lines.")
            return

        saved_date = self._transaction_date_edit.date()

        command = CreateJournalEntryCommand(
            journal_type_code=str(self._journal_type_combo.currentData() or ""),
            transaction_date=saved_date.toPython(),
            reference_text=self._reference_edit.text().strip() or None,
            description=self._description_edit.text().strip() or None,
            lines=tuple(line_commands),
        )

        try:
            self._saved_entry = self._service_registry.journal_service.create_draft_journal(
                self._company_id, command
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_FISCAL_PERIOD:
                coordinator = GuidedResolutionCoordinator(
                    resolver=ErrorResolutionResolver(),
                    workflow_resume_service=self._service_registry.workflow_resume_service,
                    navigation_service=self._service_registry.navigation_service,
                )
                result = coordinator.handle_exception(
                    parent=self,
                    error=exc,
                    workflow_key="journal_entry.create",
                    workflow_snapshot=self._build_journal_snapshot,
                    origin_nav_id=nav_ids.JOURNALS,
                    resolution_context={"company_name": self._company_name},
                )
                if result.handled and result.selected_action and result.selected_action.nav_id:
                    self.reject()
                    return
            self._set_error(str(exc))
            return
        except PeriodLockedError as exc:
            if exc.app_error_code == AppErrorCode.LOCKED_FISCAL_PERIOD:
                coordinator = GuidedResolutionCoordinator(
                    resolver=ErrorResolutionResolver(),
                    workflow_resume_service=self._service_registry.workflow_resume_service,
                    navigation_service=self._service_registry.navigation_service,
                )
                result = coordinator.handle_exception(
                    parent=self,
                    error=exc,
                    workflow_key="journal_entry.create",
                    workflow_snapshot=self._build_journal_snapshot,
                    origin_nav_id=nav_ids.JOURNALS,
                    resolution_context={"company_name": self._company_name},
                )
                if result.handled and result.selected_action and result.selected_action.nav_id:
                    self.reject()
                    return
            self._set_error(str(exc))
            return
        except ConflictError as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Journal Entry", str(exc))
            return

        # Success — reset form for next entry, preserving the transaction date.
        index = self._journal_type_combo.findData("GENERAL")
        if index >= 0:
            self._journal_type_combo.setCurrentIndex(index)
        self._transaction_date_edit.setDate(saved_date)
        self._reference_edit.clear()
        self._description_edit.clear()
        self._lines_grid.set_lines(())
        self._update_totals()

    # -- Submit ------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._set_error(None)

        line_commands = self._lines_grid.get_line_commands()
        if len(line_commands) < 2:
            self._set_error("A journal entry requires at least two lines.")
            return

        lines_tuple = tuple(line_commands)

        if self._journal_entry_id is None:
            command = CreateJournalEntryCommand(
                journal_type_code=str(self._journal_type_combo.currentData() or ""),
                transaction_date=self._transaction_date_edit.date().toPython(),
                reference_text=self._reference_edit.text().strip() or None,
                description=self._description_edit.text().strip() or None,
                lines=lines_tuple,
            )
            save_operation = lambda: self._service_registry.journal_service.create_draft_journal(
                self._company_id,
                command,
            )
        else:
            command = UpdateJournalEntryCommand(
                journal_type_code=str(self._journal_type_combo.currentData() or ""),
                transaction_date=self._transaction_date_edit.date().toPython(),
                reference_text=self._reference_edit.text().strip() or None,
                description=self._description_edit.text().strip() or None,
                lines=lines_tuple,
            )
            save_operation = lambda: self._service_registry.journal_service.update_draft_journal(
                self._company_id,
                self._journal_entry_id,
                command,
            )

        try:
            self._saved_entry = save_operation()
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_FISCAL_PERIOD:
                coordinator = GuidedResolutionCoordinator(
                    resolver=ErrorResolutionResolver(),
                    workflow_resume_service=self._service_registry.workflow_resume_service,
                    navigation_service=self._service_registry.navigation_service,
                )
                result = coordinator.handle_exception(
                    parent=self,
                    error=exc,
                    workflow_key=(
                        "journal_entry.create"
                        if self._journal_entry_id is None
                        else "journal_entry.update"
                    ),
                    workflow_snapshot=self._build_journal_snapshot,
                    origin_nav_id=nav_ids.JOURNALS,
                    resolution_context={"company_name": self._company_name},
                )
                if result.handled and result.selected_action and result.selected_action.nav_id:
                    self.reject()
                    return
                self._set_error(str(exc))
                return
            self._set_error(str(exc))
            return
        except PeriodLockedError as exc:
            if exc.app_error_code == AppErrorCode.LOCKED_FISCAL_PERIOD:
                coordinator = GuidedResolutionCoordinator(
                    resolver=ErrorResolutionResolver(),
                    workflow_resume_service=self._service_registry.workflow_resume_service,
                    navigation_service=self._service_registry.navigation_service,
                )
                result = coordinator.handle_exception(
                    parent=self,
                    error=exc,
                    workflow_key=(
                        "journal_entry.create"
                        if self._journal_entry_id is None
                        else "journal_entry.update"
                    ),
                    workflow_snapshot=self._build_journal_snapshot,
                    origin_nav_id=nav_ids.JOURNALS,
                    resolution_context={"company_name": self._company_name},
                )
                if result.handled and result.selected_action and result.selected_action.nav_id:
                    self.reject()
                    return
            self._set_error(str(exc))
            return
        except ConflictError as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Journal Entry", str(exc))
            return

        self.accept()

    # -- Snapshot (for workflow resume) ------------------------------------

    def _build_journal_snapshot(self) -> dict:
        """Capture the current unsaved header and line state for workflow resume."""
        line_commands = self._lines_grid.get_line_commands()
        lines: list[dict] = []
        for lc in line_commands:
            lines.append({
                "account_id": lc.account_id,
                "line_description": lc.line_description,
                "debit_amount": f"{lc.debit_amount or Decimal('0.00'):.2f}",
                "credit_amount": f"{lc.credit_amount or Decimal('0.00'):.2f}",
                "contract_id": lc.contract_id,
                "project_id": lc.project_id,
                "project_job_id": lc.project_job_id,
                "project_cost_code_id": lc.project_cost_code_id,
            })
        return {
            "journal_type_code": str(self._journal_type_combo.currentData() or "GENERAL"),
            "transaction_date": self._transaction_date_edit.date().toPython().isoformat(),
            "reference": self._reference_edit.text().strip() or None,
            "description": self._description_edit.text().strip() or None,
            "lines": lines,
        }

    def _restore_from_snapshot(self, snapshot: dict) -> None:
        """Restore header and line fields from a workflow resume snapshot."""
        journal_type_code = snapshot.get("journal_type_code", "GENERAL")
        index = self._journal_type_combo.findData(str(journal_type_code))
        if index >= 0:
            self._journal_type_combo.setCurrentIndex(index)

        raw_txn_date = snapshot.get("transaction_date")
        if raw_txn_date:
            from datetime import date as _date

            parsed = _date.fromisoformat(raw_txn_date)
            self._transaction_date_edit.setDate(QDate(parsed.year, parsed.month, parsed.day))

        self._reference_edit.setText(snapshot.get("reference") or "")
        self._description_edit.setText(snapshot.get("description") or "")

        # Build synthetic JournalLineDTO objects for set_lines
        from seeker_accounting.modules.accounting.journals.dto.journal_dto import JournalLineDTO
        from datetime import datetime as _datetime

        now = _datetime.now()
        raw_lines: list[dict] = snapshot.get("lines") or []
        synthetic_lines: list[JournalLineDTO] = []
        for i, line_data in enumerate(raw_lines):
            account_id = line_data.get("account_id") or 0
            synthetic_lines.append(
                JournalLineDTO(
                    id=0,
                    line_number=i + 1,
                    account_id=account_id,
                    account_code="",
                    account_name="",
                    line_description=line_data.get("line_description"),
                    debit_amount=Decimal(str(line_data.get("debit_amount", "0.00"))),
                    credit_amount=Decimal(str(line_data.get("credit_amount", "0.00"))),
                    created_at=now,
                    updated_at=now,
                    contract_id=line_data.get("contract_id"),
                    project_id=line_data.get("project_id"),
                    project_job_id=line_data.get("project_job_id"),
                    project_cost_code_id=line_data.get("project_cost_code_id"),
                )
            )
        self._lines_grid.set_lines(tuple(synthetic_lines))
        self._update_totals()
