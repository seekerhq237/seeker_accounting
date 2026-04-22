from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from seeker_accounting.modules.contracts_projects.dto.project_job_commands import (
    CreateProjectJobCommand,
    UpdateProjectJobCommand,
)
from seeker_accounting.modules.contracts_projects.dto.project_job_dto import (
    ProjectJobDetailDTO,
    ProjectJobListItemDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


# ── Job Form Dialog ───────────────────────────────────────────────────────


class ProjectJobFormDialog(BaseDialog):
    """Create or edit a single project job / work package."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        jobs: list[ProjectJobListItemDTO],
        job_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._job_id = job_id
        self._jobs = jobs
        self._saved: ProjectJobDetailDTO | None = None

        title = "New Job" if job_id is None else "Edit Job"
        super().__init__(title, parent, help_key="dialog.project_job")
        self.setObjectName("ProjectJobFormDialog")
        self.resize(600, 520)

        intro = QLabel(f"Job for project {project_code}.", self)
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
            save_btn.setText("Create" if job_id is None else "Save Changes")
            save_btn.setProperty("variant", "primary")

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")

        if self._job_id is not None:
            self._load_job()
        else:
            self._suggest_code()

    @property
    def saved_job(self) -> ProjectJobDetailDTO | None:
        return self._saved

    @classmethod
    def create_job(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        jobs: list[ProjectJobListItemDTO],
        parent: QWidget | None = None,
    ) -> ProjectJobDetailDTO | None:
        dialog = cls(service_registry, company_id, project_id, project_code, jobs, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_job
        return None

    @classmethod
    def edit_job(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        jobs: list[ProjectJobListItemDTO],
        job_id: int,
        parent: QWidget | None = None,
    ) -> ProjectJobDetailDTO | None:
        dialog = cls(
            service_registry, company_id, project_id, project_code, jobs,
            job_id=job_id, parent=parent
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_job
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

        title = QLabel("Job Details", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._code_edit = QLineEdit(card)
        self._code_edit.setPlaceholderText("JOB-001")
        grid.addWidget(create_field_block("Job Code", self._code_edit), 0, 0)

        self._name_edit = QLineEdit(card)
        self._name_edit.setPlaceholderText("Job name")
        grid.addWidget(create_field_block("Job Name", self._name_edit), 0, 1)

        self._parent_combo = QComboBox(card)
        self._parent_combo.addItem("(No parent)", None)
        for j in self._jobs:
            if self._job_id is None or j.id != self._job_id:
                self._parent_combo.addItem(f"{j.job_code} — {j.job_name}", j.id)
        grid.addWidget(create_field_block("Parent Job", self._parent_combo), 1, 0)

        self._sequence_spin = QSpinBox(card)
        self._sequence_spin.setMinimum(0)
        self._sequence_spin.setMaximum(99999)
        self._sequence_spin.setValue(0)
        grid.addWidget(create_field_block("Sequence", self._sequence_spin), 1, 1)

        self._start_date_edit = QDateEdit(card)
        self._start_date_edit.setCalendarPopup(True)
        self._start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._start_date_edit.setDate(date.today())
        self._start_date_edit.setSpecialValueText(" ")
        grid.addWidget(create_field_block("Start Date", self._start_date_edit, "Optional"), 2, 0)

        self._planned_end_date_edit = QDateEdit(card)
        self._planned_end_date_edit.setCalendarPopup(True)
        self._planned_end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._planned_end_date_edit.setDate(date.today())
        self._planned_end_date_edit.setSpecialValueText(" ")
        grid.addWidget(create_field_block("Planned End Date", self._planned_end_date_edit, "Optional"), 2, 1)

        self._cost_posting_check = QCheckBox("Allow direct cost posting", card)
        self._cost_posting_check.setChecked(True)
        grid.addWidget(self._cost_posting_check, 3, 0, 1, 2)

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

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("project_job", self._project_id)
            self._code_edit.setText(code)
        except Exception:
            pass

    def _load_job(self) -> None:
        try:
            detail = self._service_registry.project_structure_service.get_job_detail(self._job_id or 0)
        except NotFoundError as exc:
            show_error(self, "Not Found", str(exc))
            self.reject()
            return

        self._code_edit.setText(detail.job_code)
        self._code_edit.setReadOnly(True)
        self._name_edit.setText(detail.job_name)

        if detail.parent_job_id is not None:
            idx = self._parent_combo.findData(detail.parent_job_id)
            if idx >= 0:
                self._parent_combo.setCurrentIndex(idx)

        self._sequence_spin.setValue(detail.sequence_number)
        if detail.start_date:
            self._start_date_edit.setDate(detail.start_date)
        if detail.planned_end_date:
            self._planned_end_date_edit.setDate(detail.planned_end_date)
        self._cost_posting_check.setChecked(detail.allow_direct_cost_posting)
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

        code = self._code_edit.text().strip()
        name = self._name_edit.text().strip()
        if not code:
            self._set_error("Job code is required.")
            return
        if not name:
            self._set_error("Job name is required.")
            return

        parent_id = self._parent_combo.currentData()
        sequence = self._sequence_spin.value()
        start = self._start_date_edit.date().toPython()
        planned_end = self._planned_end_date_edit.date().toPython()
        allow_posting = self._cost_posting_check.isChecked()
        notes = self._notes_edit.toPlainText().strip() or None

        svc = self._service_registry.project_structure_service

        try:
            if self._job_id is None:
                result = svc.create_job(
                    CreateProjectJobCommand(
                        company_id=self._company_id,
                        project_id=self._project_id,
                        job_code=code,
                        job_name=name,
                        parent_job_id=parent_id,
                        sequence_number=sequence,
                        start_date=start,
                        planned_end_date=planned_end,
                        allow_direct_cost_posting=allow_posting,
                        notes=notes,
                    )
                )
            else:
                result = svc.update_job(
                    self._job_id,
                    UpdateProjectJobCommand(
                        job_name=name,
                        parent_job_id=parent_id,
                        sequence_number=sequence,
                        start_date=start,
                        planned_end_date=planned_end,
                        allow_direct_cost_posting=allow_posting,
                        notes=notes,
                    ),
                )
            self._saved = result
            self.accept()
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))


# ── Jobs List Dialog ──────────────────────────────────────────────────────


class ProjectJobsDialog(BaseDialog):
    """List and manage jobs for a specific project."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Jobs — {project_code}", parent, help_key="dialog.project_job_list")
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._project_code = project_code
        self._jobs: list[ProjectJobListItemDTO] = []

        self.setObjectName("ProjectJobsDialog")
        self.resize(900, 560)

        self.body_layout.addWidget(self._build_toolbar())
        self.body_layout.addWidget(self._build_table_card(), 1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        close_btn = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setProperty("variant", "secondary")

        self._reload()

    @classmethod
    def manage_jobs(
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

        self._new_button = QPushButton("New Job", toolbar)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit", toolbar)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit)
        layout.addWidget(self._edit_button)

        self._deactivate_button = QPushButton("Deactivate", toolbar)
        self._deactivate_button.setProperty("variant", "secondary")
        self._deactivate_button.clicked.connect(self._deactivate_selected)
        layout.addWidget(self._deactivate_button)

        self._reactivate_button = QPushButton("Reactivate", toolbar)
        self._reactivate_button.setProperty("variant", "secondary")
        self._reactivate_button.clicked.connect(self._reactivate_selected)
        layout.addWidget(self._reactivate_button)

        self._close_button = QPushButton("Close Job", toolbar)
        self._close_button.setProperty("variant", "secondary")
        self._close_button.clicked.connect(self._close_selected)
        layout.addWidget(self._close_button)

        layout.addStretch(1)

        self._count_label = QLabel(toolbar)
        self._count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._count_label)

        return toolbar

    def _build_table_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._table = QTableWidget(card)
        self._table.setObjectName("ProjectJobsTable")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ("Code", "Name", "Parent", "Seq", "Status", "Start", "Planned End")
        )
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._open_edit)
        layout.addWidget(self._table)
        return card

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _reload(self, selected_id: int | None = None) -> None:
        svc = self._service_registry.project_structure_service
        try:
            self._jobs = svc.list_jobs(self._project_id)
        except Exception as exc:
            self._jobs = []
            show_error(self, "Jobs", f"Could not load jobs.\n\n{exc}")

        self._populate_table()
        count = len(self._jobs)
        self._count_label.setText(f"{count} job{'s' if count != 1 else ''}")

        if selected_id is not None:
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    self._table.selectRow(row)
                    self._update_action_state()
                    return

        if self._table.rowCount() > 0:
            self._table.selectRow(0)
        self._update_action_state()

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for job in self._jobs:
            row = self._table.rowCount()
            self._table.insertRow(row)
            values = (
                job.job_code,
                job.job_name,
                job.parent_job_code or "",
                str(job.sequence_number),
                job.status_code,
                str(job.start_date) if job.start_date else "",
                str(job.planned_end_date) if job.planned_end_date else "",
            )
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job.id)
                if col in {3, 4}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

    def _selected_job(self) -> ProjectJobListItemDTO | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        job_id = item.data(Qt.ItemDataRole.UserRole)
        for j in self._jobs:
            if j.id == job_id:
                return j
        return None

    def _update_action_state(self) -> None:
        selected = self._selected_job()
        status = selected.status_code if selected else None

        self._edit_button.setEnabled(status == "active")
        self._deactivate_button.setEnabled(status == "active")
        self._reactivate_button.setEnabled(status == "inactive")
        self._close_button.setEnabled(status in {"active", "inactive"})

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create(self) -> None:
        result = ProjectJobFormDialog.create_job(
            self._service_registry,
            self._company_id,
            self._project_id,
            self._project_code,
            self._jobs,
            parent=self,
        )
        if result is not None:
            self._reload(selected_id=result.id)

    def _open_edit(self) -> None:
        selected = self._selected_job()
        if selected is None or selected.status_code != "active":
            return
        result = ProjectJobFormDialog.edit_job(
            self._service_registry,
            self._company_id,
            self._project_id,
            self._project_code,
            self._jobs,
            job_id=selected.id,
            parent=self,
        )
        if result is not None:
            self._reload(selected_id=result.id)

    def _deactivate_selected(self) -> None:
        selected = self._selected_job()
        if selected is None:
            return
        choice = QMessageBox.question(
            self, "Deactivate Job",
            f"Deactivate job '{selected.job_code}'?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.project_structure_service.deactivate_job(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Jobs", str(exc))
        self._reload(selected_id=selected.id)

    def _reactivate_selected(self) -> None:
        selected = self._selected_job()
        if selected is None:
            return
        try:
            self._service_registry.project_structure_service.reactivate_job(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Jobs", str(exc))
        self._reload(selected_id=selected.id)

    def _close_selected(self) -> None:
        selected = self._selected_job()
        if selected is None:
            return
        choice = QMessageBox.question(
            self, "Close Job",
            f"Close job '{selected.job_code}'? This cannot be undone.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.project_structure_service.close_job(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Jobs", str(exc))
        self._reload(selected_id=selected.id)
