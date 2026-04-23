"""Unified budget editor — header + inline editable lines grid in one atomic dialog.

Replaces the split "version form then lines dialog" pattern with a single
workspace that creates a budget version and all its lines in one transaction
via :meth:`ProjectBudgetService.create_version_with_lines` or edits an existing
draft's lines in one transaction via
:meth:`ProjectBudgetService.replace_version_lines`.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
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
    BudgetLineDraftDTO,
    CreateProjectBudgetVersionWithLinesCommand,
    SubmitProjectBudgetVersionCommand,
)
from seeker_accounting.modules.budgeting.dto.project_budget_dto import (
    ProjectBudgetVersionDetailDTO,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_VERSION_TYPES = (
    ("original", "Original"),
    ("revision", "Revision"),
    ("working", "Working"),
    ("forecast", "Forecast"),
)

# Grid column indexes
_COL_LINE = 0
_COL_JOB = 1
_COL_COST_CODE = 2
_COL_DESCRIPTION = 3
_COL_QTY = 4
_COL_RATE = 5
_COL_AMOUNT = 6
_COL_NOTES = 7
_COL_COUNT = 8


def _parse_decimal(text: str) -> Decimal | None:
    text = (text or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _fmt_decimal(value: Decimal | None, places: int = 2) -> str:
    if value is None:
        return ""
    quantize = Decimal(10) ** -places
    try:
        return f"{Decimal(value).quantize(quantize):f}"
    except Exception:
        return str(value)


class BudgetEditorDialog(BaseDialog):
    """Create or edit a project budget version with its lines atomically."""

    # signal so parents can react without polling
    saved = Signal(object)  # emits ProjectBudgetVersionDetailDTO

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        *,
        version_id: int | None = None,
        seed_version_number: int | None = None,
        seed_version_name: str | None = None,
        seed_version_type_code: str = "original",
        seed_base_version_id: int | None = None,
        seed_revision_reason: str | None = None,
        seed_lines: tuple[BudgetLineDraftDTO, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._version_id = version_id
        self._is_edit = version_id is not None
        self._saved_version: ProjectBudgetVersionDetailDTO | None = None

        # Reference data (populated in _load_reference_data)
        self._jobs: list[tuple[int, str]] = []  # (id, label)
        self._cost_codes: list[tuple[int, str]] = []  # (id, label)

        title = "Edit Budget" if self._is_edit else "New Budget"
        super().__init__(title, parent, help_key="dialog.budget_editor")
        self.setObjectName("BudgetEditorDialog")
        self.resize(1100, 720)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_header_card())
        self.body_layout.addWidget(self._build_lines_card(), 1)
        self.body_layout.addLayout(self._build_button_bar())

        self._load_reference_data()

        # Seed defaults / existing values
        if self._is_edit:
            self._load_existing_version()
        else:
            self._apply_seeds(
                version_number=seed_version_number,
                version_name=seed_version_name,
                version_type_code=seed_version_type_code,
                base_version_id=seed_base_version_id,
                revision_reason=seed_revision_reason,
            )
            for draft in seed_lines:
                self._append_row_from_draft(draft)
            self._recompute_total()

    # ------------------------------------------------------------------ factories
    @classmethod
    def create(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        parent: QWidget | None = None,
        *,
        seed_version_number: int | None = None,
        seed_version_name: str | None = None,
        seed_version_type_code: str = "original",
        seed_base_version_id: int | None = None,
        seed_revision_reason: str | None = None,
        seed_lines: tuple[BudgetLineDraftDTO, ...] = (),
    ) -> ProjectBudgetVersionDetailDTO | None:
        dialog = cls(
            service_registry,
            company_id,
            project_id,
            seed_version_number=seed_version_number,
            seed_version_name=seed_version_name,
            seed_version_type_code=seed_version_type_code,
            seed_base_version_id=seed_base_version_id,
            seed_revision_reason=seed_revision_reason,
            seed_lines=seed_lines,
            parent=parent,
        )
        if dialog.exec() == BaseDialog.DialogCode.Accepted:
            return dialog._saved_version
        return None

    @classmethod
    def revise_from_approved(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        parent: QWidget | None = None,
    ) -> ProjectBudgetVersionDetailDTO | None:
        """Open the editor seeded from the project's current approved version.

        Falls back to ``create()`` (empty) if no approved version exists.
        """
        seed = service_registry.budget_approval_service.prepare_revision_draft(project_id)
        if seed is None:
            return cls.create(service_registry, company_id, project_id, parent)
        next_number, default_name, base_version_id, drafts = seed
        return cls.create(
            service_registry,
            company_id,
            project_id,
            parent,
            seed_version_number=next_number,
            seed_version_name=default_name,
            seed_version_type_code="revision",
            seed_base_version_id=base_version_id,
            seed_lines=drafts,
        )

    @classmethod
    def edit_draft(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        version_id: int,
        parent: QWidget | None = None,
    ) -> ProjectBudgetVersionDetailDTO | None:
        dialog = cls(
            service_registry,
            company_id,
            project_id,
            version_id=version_id,
            parent=parent,
        )
        if dialog.exec() == BaseDialog.DialogCode.Accepted:
            return dialog._saved_version
        return None

    # ------------------------------------------------------------------ UI build
    def _build_header_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(10)

        title = QLabel("Budget Version", card)
        title.setObjectName("DialogSectionTitle")
        outer.addWidget(title)

        grid = QHBoxLayout()
        grid.setSpacing(12)

        self._version_number_spin = QSpinBox(card)
        self._version_number_spin.setRange(1, 9999)
        self._version_number_spin.setMinimumWidth(90)
        grid.addLayout(create_field_block("Version #", self._version_number_spin))

        self._name_edit = QLineEdit(card)
        self._name_edit.setPlaceholderText("e.g. Original Budget, Revision 1")
        grid.addLayout(create_field_block("Name", self._name_edit), 2)

        self._type_combo = QComboBox(card)
        for code, label in _VERSION_TYPES:
            self._type_combo.addItem(label, code)
        self._type_combo.setMinimumWidth(140)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        grid.addLayout(create_field_block("Type", self._type_combo))

        self._date_edit = QDateEdit(card)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setMinimumWidth(140)
        grid.addLayout(create_field_block("Budget date", self._date_edit))

        outer.addLayout(grid)

        self._reason_label = QLabel("Revision reason", card)
        self._reason_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        self._reason_edit = QPlainTextEdit(card)
        self._reason_edit.setFixedHeight(52)
        self._reason_edit.setPlaceholderText("Why is this version being created?")
        outer.addWidget(self._reason_label)
        outer.addWidget(self._reason_edit)
        self._update_reason_visibility()

        return card

    def _build_lines_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Budget Lines", card)
        title.setObjectName("DialogSectionTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._add_button = QPushButton("Add Line", card)
        self._add_button.clicked.connect(self._on_add_line)
        header.addWidget(self._add_button)

        self._duplicate_button = QPushButton("Duplicate", card)
        self._duplicate_button.setProperty("variant", "secondary")
        self._duplicate_button.clicked.connect(self._on_duplicate_line)
        header.addWidget(self._duplicate_button)

        self._delete_button = QPushButton("Delete", card)
        self._delete_button.setProperty("variant", "secondary")
        self._delete_button.clicked.connect(self._on_delete_line)
        header.addWidget(self._delete_button)

        outer.addLayout(header)

        self._table = QTableWidget(0, _COL_COUNT, card)
        self._table.setHorizontalHeaderLabels(
            ["#", "Job", "Cost Code", "Description", "Qty", "Rate", "Amount", "Notes"]
        )
        configure_compact_table(self._table)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        header_view = self._table.horizontalHeader()
        header_view.setSectionResizeMode(_COL_LINE, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(_COL_JOB, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(_COL_COST_CODE, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(_COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(_COL_QTY, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(_COL_RATE, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(_COL_AMOUNT, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(_COL_NOTES, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(_COL_JOB, 180)
        self._table.setColumnWidth(_COL_COST_CODE, 200)
        self._table.setColumnWidth(_COL_NOTES, 160)
        self._table.itemChanged.connect(self._on_item_changed)
        outer.addWidget(self._table, 1)

        # Footer: line count + total
        footer = QHBoxLayout()
        footer.addStretch(1)
        self._footer_label = QLabel("0 lines  ·  Total: 0.00", card)
        self._footer_label.setStyleSheet("font-weight: 600;")
        footer.addWidget(self._footer_label)
        outer.addLayout(footer)

        return card

    def _build_button_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addStretch(1)

        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self.reject)
        bar.addWidget(self._cancel_button)

        self._save_draft_button = QPushButton("Save Draft", self)
        self._save_draft_button.clicked.connect(lambda: self._on_save(submit_after=False))
        bar.addWidget(self._save_draft_button)

        self._save_submit_button = QPushButton("Save && Submit", self)
        self._save_submit_button.setProperty("variant", "primary")
        self._save_submit_button.clicked.connect(lambda: self._on_save(submit_after=True))
        bar.addWidget(self._save_submit_button)

        return bar

    # ------------------------------------------------------------------ reference data
    def _load_reference_data(self) -> None:
        try:
            jobs = self._service_registry.project_structure_service.list_jobs(self._project_id)
            self._jobs = [(j.id, f"{j.job_code} — {j.job_name}") for j in jobs]
        except NotFoundError:
            self._jobs = []
        except Exception:
            _log.warning("Failed to load jobs", exc_info=True)
            self._jobs = []

        try:
            cost_codes = self._service_registry.project_cost_code_service.list_cost_codes(
                self._company_id
            )
            self._cost_codes = [(cc.id, f"{cc.code} — {cc.name}") for cc in cost_codes]
        except Exception:
            _log.warning("Failed to load cost codes", exc_info=True)
            self._cost_codes = []

    # ------------------------------------------------------------------ seeds / load
    def _apply_seeds(
        self,
        *,
        version_number: int | None,
        version_name: str | None,
        version_type_code: str,
        base_version_id: int | None,
        revision_reason: str | None,
    ) -> None:
        if version_number is None:
            # Default to next available version number
            try:
                existing = self._service_registry.project_budget_service.list_versions(
                    self._project_id
                )
                version_number = (
                    max((v.version_number for v in existing), default=0) + 1
                )
            except Exception:
                version_number = 1
        self._version_number_spin.setValue(version_number)

        if version_name:
            self._name_edit.setText(version_name)
        else:
            self._name_edit.setText(
                "Original Budget" if version_number == 1 else f"Revision {version_number - 1}"
            )

        idx = self._type_combo.findData(version_type_code)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)

        self._base_version_id = base_version_id
        if revision_reason:
            self._reason_edit.setPlainText(revision_reason)
        self._update_reason_visibility()

    def _load_existing_version(self) -> None:
        try:
            detail = self._service_registry.project_budget_service.get_version_detail(
                self._version_id  # type: ignore[arg-type]
            )
            lines = self._service_registry.project_budget_service.list_lines(
                self._version_id  # type: ignore[arg-type]
            )
        except NotFoundError as exc:
            show_error(self, "Budget", str(exc))
            self.reject()
            return

        self._version_number_spin.setValue(detail.version_number)
        self._version_number_spin.setEnabled(False)  # locked on edit
        self._name_edit.setText(detail.version_name or "")
        idx = self._type_combo.findData(detail.version_type_code)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        if detail.budget_date:
            self._date_edit.setDate(
                QDate(detail.budget_date.year, detail.budget_date.month, detail.budget_date.day)
            )
        self._base_version_id = detail.base_version_id
        self._reason_edit.setPlainText(detail.revision_reason or "")
        self._update_reason_visibility()

        for line in lines:
            self._append_row_from_draft(
                BudgetLineDraftDTO(
                    line_number=line.line_number,
                    project_cost_code_id=line.project_cost_code_id,
                    line_amount=line.line_amount,
                    project_job_id=line.project_job_id,
                    description=line.description,
                    quantity=line.quantity,
                    unit_rate=line.unit_rate,
                    start_date=line.start_date,
                    end_date=line.end_date,
                    notes=line.notes,
                )
            )
        self._recompute_total()

    # ------------------------------------------------------------------ grid row builders
    def _append_row_from_draft(self, draft: BudgetLineDraftDTO) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._build_row(row, draft)

    def _append_blank_row(self) -> None:
        next_line_number = self._table.rowCount() + 1
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._build_row(
            row,
            BudgetLineDraftDTO(
                line_number=next_line_number,
                project_cost_code_id=0,
                line_amount=Decimal("0"),
            ),
        )

    def _build_row(self, row: int, draft: BudgetLineDraftDTO) -> None:
        self._table.blockSignals(True)
        try:
            # #
            num_item = QTableWidgetItem(str(draft.line_number))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_LINE, num_item)

            # Job combo
            job_combo = QComboBox(self._table)
            job_combo.addItem("— (No job) —", None)
            for jid, label in self._jobs:
                job_combo.addItem(label, jid)
            if draft.project_job_id is not None:
                idx = job_combo.findData(draft.project_job_id)
                if idx >= 0:
                    job_combo.setCurrentIndex(idx)
            self._table.setCellWidget(row, _COL_JOB, job_combo)

            # Cost code combo
            cc_combo = QComboBox(self._table)
            cc_combo.addItem("— Select cost code —", 0)
            for cid, label in self._cost_codes:
                cc_combo.addItem(label, cid)
            if draft.project_cost_code_id:
                idx = cc_combo.findData(draft.project_cost_code_id)
                if idx >= 0:
                    cc_combo.setCurrentIndex(idx)
            self._table.setCellWidget(row, _COL_COST_CODE, cc_combo)

            # Description
            self._table.setItem(
                row, _COL_DESCRIPTION, QTableWidgetItem(draft.description or "")
            )

            # Qty / Rate / Amount — plain text items
            qty_item = QTableWidgetItem(_fmt_decimal(draft.quantity, 4))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_QTY, qty_item)

            rate_item = QTableWidgetItem(_fmt_decimal(draft.unit_rate, 4))
            rate_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_RATE, rate_item)

            amount_item = QTableWidgetItem(_fmt_decimal(draft.line_amount, 2))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_AMOUNT, amount_item)

            self._table.setItem(row, _COL_NOTES, QTableWidgetItem(draft.notes or ""))
        finally:
            self._table.blockSignals(False)

    # ------------------------------------------------------------------ grid events
    def _on_add_line(self) -> None:
        self._append_blank_row()
        self._recompute_total()

    def _on_duplicate_line(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        draft = self._row_to_draft(row, allow_partial=True)
        if draft is None:
            return
        new_line_number = self._table.rowCount() + 1
        self._append_row_from_draft(
            BudgetLineDraftDTO(
                line_number=new_line_number,
                project_cost_code_id=draft.project_cost_code_id,
                line_amount=draft.line_amount,
                project_job_id=draft.project_job_id,
                description=draft.description,
                quantity=draft.quantity,
                unit_rate=draft.unit_rate,
                start_date=draft.start_date,
                end_date=draft.end_date,
                notes=draft.notes,
            )
        )
        self._recompute_total()

    def _on_delete_line(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.removeRow(row)
        self._renumber_rows()
        self._recompute_total()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        col = item.column()
        if col in (_COL_QTY, _COL_RATE):
            # Recompute amount from qty × rate if both present
            row = item.row()
            qty = _parse_decimal(self._table.item(row, _COL_QTY).text() if self._table.item(row, _COL_QTY) else "")
            rate = _parse_decimal(self._table.item(row, _COL_RATE).text() if self._table.item(row, _COL_RATE) else "")
            if qty is not None and rate is not None:
                amount = (qty * rate).quantize(Decimal("0.01"))
                self._table.blockSignals(True)
                try:
                    amount_item = self._table.item(row, _COL_AMOUNT)
                    if amount_item is None:
                        amount_item = QTableWidgetItem()
                        amount_item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        )
                        self._table.setItem(row, _COL_AMOUNT, amount_item)
                    amount_item.setText(_fmt_decimal(amount, 2))
                finally:
                    self._table.blockSignals(False)
        if col in (_COL_QTY, _COL_RATE, _COL_AMOUNT):
            self._recompute_total()

    def _renumber_rows(self) -> None:
        self._table.blockSignals(True)
        try:
            for row in range(self._table.rowCount()):
                item = self._table.item(row, _COL_LINE)
                if item is None:
                    item = QTableWidgetItem()
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                    self._table.setItem(row, _COL_LINE, item)
                item.setText(str(row + 1))
        finally:
            self._table.blockSignals(False)

    def _recompute_total(self) -> None:
        total = Decimal("0")
        count = self._table.rowCount()
        for row in range(count):
            amount_item = self._table.item(row, _COL_AMOUNT)
            amount = _parse_decimal(amount_item.text() if amount_item else "")
            if amount is not None:
                total += amount
        self._footer_label.setText(
            f"{count} line{'s' if count != 1 else ''}  ·  Total: {_fmt_decimal(total, 2)}"
        )

    def _on_type_changed(self) -> None:
        self._update_reason_visibility()

    def _update_reason_visibility(self) -> None:
        is_original = self._type_combo.currentData() == "original"
        self._reason_label.setVisible(not is_original)
        self._reason_edit.setVisible(not is_original)

    # ------------------------------------------------------------------ save
    def _row_to_draft(self, row: int, *, allow_partial: bool = False) -> BudgetLineDraftDTO | None:
        """Build a draft from row; returns None if invalid (with error raised unless allow_partial)."""
        line_number_item = self._table.item(row, _COL_LINE)
        try:
            line_number = int((line_number_item.text() if line_number_item else "").strip() or (row + 1))
        except ValueError:
            line_number = row + 1

        job_combo = self._table.cellWidget(row, _COL_JOB)
        job_id: int | None = None
        if isinstance(job_combo, QComboBox):
            data = job_combo.currentData()
            job_id = int(data) if data is not None else None

        cc_combo = self._table.cellWidget(row, _COL_COST_CODE)
        cost_code_id = 0
        if isinstance(cc_combo, QComboBox):
            cost_code_id = int(cc_combo.currentData() or 0)
        if cost_code_id == 0 and not allow_partial:
            raise ValidationError(f"Line {line_number}: cost code is required.")

        desc_item = self._table.item(row, _COL_DESCRIPTION)
        description = (desc_item.text().strip() if desc_item else "") or None

        qty_item = self._table.item(row, _COL_QTY)
        quantity = _parse_decimal(qty_item.text() if qty_item else "")

        rate_item = self._table.item(row, _COL_RATE)
        unit_rate = _parse_decimal(rate_item.text() if rate_item else "")

        amount_item = self._table.item(row, _COL_AMOUNT)
        amount = _parse_decimal(amount_item.text() if amount_item else "")
        if amount is None:
            if allow_partial:
                amount = Decimal("0")
            else:
                raise ValidationError(f"Line {line_number}: amount is required.")

        notes_item = self._table.item(row, _COL_NOTES)
        notes = (notes_item.text().strip() if notes_item else "") or None

        return BudgetLineDraftDTO(
            line_number=line_number,
            project_cost_code_id=cost_code_id,
            line_amount=amount,
            project_job_id=job_id,
            description=description,
            quantity=quantity,
            unit_rate=unit_rate,
            notes=notes,
        )

    def _collect_line_drafts(self) -> tuple[BudgetLineDraftDTO, ...]:
        drafts: list[BudgetLineDraftDTO] = []
        for row in range(self._table.rowCount()):
            draft = self._row_to_draft(row, allow_partial=False)
            if draft is not None:
                drafts.append(draft)
        return tuple(drafts)

    def _on_save(self, *, submit_after: bool) -> None:
        self._error_label.hide()

        name = self._name_edit.text().strip()
        if not name:
            self._show_error("Version name is required.")
            return

        type_code = self._type_combo.currentData() or "original"
        qd = self._date_edit.date()
        budget_date = date(qd.year(), qd.month(), qd.day())
        reason = self._reason_edit.toPlainText().strip() or None
        version_number = int(self._version_number_spin.value())

        try:
            drafts = self._collect_line_drafts()
        except ValidationError as exc:
            self._show_error(str(exc))
            return

        if submit_after and not drafts:
            self._show_error("Add at least one budget line before submitting for approval.")
            return

        try:
            if self._is_edit:
                # Edit path: replace lines on the draft; header edits via separate service.
                detail = self._service_registry.project_budget_service.update_version(
                    self._version_id,  # type: ignore[arg-type]
                    self._build_update_command(name, type_code, budget_date, reason),
                )
                detail = self._service_registry.project_budget_service.replace_version_lines(
                    self._version_id,  # type: ignore[arg-type]
                    drafts,
                )
            else:
                command = CreateProjectBudgetVersionWithLinesCommand(
                    company_id=self._company_id,
                    project_id=self._project_id,
                    version_number=version_number,
                    version_name=name,
                    version_type_code=type_code,
                    budget_date=budget_date,
                    lines=drafts,
                    base_version_id=getattr(self, "_base_version_id", None),
                    revision_reason=reason,
                )
                detail = self._service_registry.project_budget_service.create_version_with_lines(
                    command
                )

            if submit_after:
                detail = self._service_registry.budget_approval_service.submit_version(
                    SubmitProjectBudgetVersionCommand(
                        version_id=detail.id, company_id=self._company_id
                    )
                )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._show_error(str(exc))
            return

        self._saved_version = detail
        self.saved.emit(detail)
        self.accept()

    def _build_update_command(
        self, name: str, type_code: str, budget_date: date, reason: str | None
    ):
        from seeker_accounting.modules.budgeting.dto.project_budget_commands import (
            UpdateProjectBudgetVersionCommand,
        )

        return UpdateProjectBudgetVersionCommand(
            version_name=name,
            version_type_code=type_code,
            budget_date=budget_date,
            base_version_id=getattr(self, "_base_version_id", None),
            revision_reason=reason,
        )

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
