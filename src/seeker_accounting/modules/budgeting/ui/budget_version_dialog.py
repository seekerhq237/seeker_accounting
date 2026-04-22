from __future__ import annotations

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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.budgeting.dto.project_budget_commands import (
    ApproveProjectBudgetVersionCommand,
    CancelProjectBudgetVersionCommand,
    CloneProjectBudgetVersionCommand,
    CreateProjectBudgetVersionCommand,
    SubmitProjectBudgetVersionCommand,
    UpdateProjectBudgetVersionCommand,
)
from seeker_accounting.modules.budgeting.ui.copy_budget_version_dialog import (
    CopyBudgetVersionDialog,
)
from seeker_accounting.modules.budgeting.dto.project_budget_dto import (
    ProjectBudgetVersionDetailDTO,
    ProjectBudgetVersionListItemDTO,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_VERSION_TYPE_OPTIONS = (
    ("original", "Original"),
    ("revision", "Revision"),
    ("working", "Working"),
    ("forecast", "Forecast"),
)


# ── Version Form Dialog ──────────────────────────────────────────────────


class BudgetVersionFormDialog(BaseDialog):
    """Create or edit a single project budget version."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        versions: list[ProjectBudgetVersionListItemDTO],
        version_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._version_id = version_id
        self._versions = versions
        self._saved: ProjectBudgetVersionDetailDTO | None = None

        title = "New Budget Version" if version_id is None else "Edit Budget Version"
        super().__init__(title, parent, help_key="dialog.budget_version")
        self.setObjectName("BudgetVersionFormDialog")
        self.resize(600, 500)

        intro = QLabel(f"Budget version for project {project_code}.", self)
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
            save_btn.setText("Create" if version_id is None else "Save Changes")
            save_btn.setProperty("variant", "primary")

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")

        if self._version_id is not None:
            self._load_version()

    @property
    def saved_version(self) -> ProjectBudgetVersionDetailDTO | None:
        return self._saved

    @classmethod
    def create_version(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        versions: list[ProjectBudgetVersionListItemDTO],
        parent: QWidget | None = None,
    ) -> ProjectBudgetVersionDetailDTO | None:
        dialog = cls(service_registry, company_id, project_id, project_code, versions, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_version
        return None

    @classmethod
    def edit_version(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        versions: list[ProjectBudgetVersionListItemDTO],
        version_id: int,
        parent: QWidget | None = None,
    ) -> ProjectBudgetVersionDetailDTO | None:
        dialog = cls(
            service_registry, company_id, project_id, project_code, versions,
            version_id=version_id, parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_version
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

        title = QLabel("Version Details", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._version_number_spin = QSpinBox(card)
        self._version_number_spin.setMinimum(1)
        self._version_number_spin.setMaximum(9999)
        next_number = max((v.version_number for v in self._versions), default=0) + 1
        self._version_number_spin.setValue(next_number)
        grid.addWidget(create_field_block("Version Number", self._version_number_spin), 0, 0)

        self._name_edit = QLineEdit(card)
        self._name_edit.setPlaceholderText("e.g. Original Budget, Revision 1")
        grid.addWidget(create_field_block("Version Name", self._name_edit), 0, 1)

        self._type_combo = QComboBox(card)
        for code, label in _VERSION_TYPE_OPTIONS:
            self._type_combo.addItem(label, code)
        grid.addWidget(create_field_block("Version Type", self._type_combo), 1, 0)

        self._budget_date_edit = QDateEdit(card)
        self._budget_date_edit.setCalendarPopup(True)
        self._budget_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._budget_date_edit.setDate(date.today())
        grid.addWidget(create_field_block("Budget Date", self._budget_date_edit), 1, 1)

        self._base_version_combo = QComboBox(card)
        self._base_version_combo.addItem("(None)", None)
        for v in self._versions:
            if self._version_id is None or v.id != self._version_id:
                self._base_version_combo.addItem(
                    f"V{v.version_number} — {v.version_name}", v.id
                )
        grid.addWidget(create_field_block("Base Version", self._base_version_combo, "Optional"), 2, 0, 1, 2)

        layout.addLayout(grid)
        return card

    def _build_notes_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Revision Reason", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._reason_edit = QPlainTextEdit(card)
        self._reason_edit.setPlaceholderText("Optional revision reason or notes")
        self._reason_edit.setFixedHeight(70)
        layout.addWidget(self._reason_edit)
        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_version(self) -> None:
        try:
            detail = self._service_registry.project_budget_service.get_version_detail(
                self._version_id or 0
            )
        except NotFoundError as exc:
            show_error(self, "Not Found", str(exc))
            self.reject()
            return

        self._version_number_spin.setValue(detail.version_number)
        self._version_number_spin.setReadOnly(True)
        self._name_edit.setText(detail.version_name)

        idx = self._type_combo.findData(detail.version_type_code)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)

        self._budget_date_edit.setDate(detail.budget_date)

        if detail.base_version_id is not None:
            base_idx = self._base_version_combo.findData(detail.base_version_id)
            if base_idx >= 0:
                self._base_version_combo.setCurrentIndex(base_idx)

        self._reason_edit.setPlainText(detail.revision_reason or "")

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

        name = self._name_edit.text().strip()
        if not name:
            self._set_error("Version name is required.")
            return

        version_number = self._version_number_spin.value()
        version_type = self._type_combo.currentData()
        budget_date = self._budget_date_edit.date().toPython()
        base_version_id = self._base_version_combo.currentData()
        reason = self._reason_edit.toPlainText().strip() or None

        svc = self._service_registry.project_budget_service

        try:
            if self._version_id is None:
                result = svc.create_version(
                    CreateProjectBudgetVersionCommand(
                        company_id=self._company_id,
                        project_id=self._project_id,
                        version_number=version_number,
                        version_name=name,
                        version_type_code=version_type,
                        budget_date=budget_date,
                        base_version_id=base_version_id,
                        revision_reason=reason,
                    )
                )
            else:
                result = svc.update_version(
                    self._version_id,
                    UpdateProjectBudgetVersionCommand(
                        version_name=name,
                        version_type_code=version_type,
                        budget_date=budget_date,
                        base_version_id=base_version_id,
                        revision_reason=reason,
                    ),
                )
            self._saved = result
            self.accept()
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))


# ── Budget Versions List Dialog ──────────────────────────────────────────


class BudgetVersionsDialog(BaseDialog):
    """List and manage budget versions for a specific project."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        project_id: int,
        project_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Budget Versions — {project_code}", parent, help_key="dialog.budget_version_list")
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._project_code = project_code
        self._versions: list[ProjectBudgetVersionListItemDTO] = []

        self.setObjectName("BudgetVersionsDialog")
        self.resize(940, 560)

        self.body_layout.addWidget(self._build_toolbar())
        self.body_layout.addWidget(self._build_table_card(), 1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        close_btn = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setProperty("variant", "secondary")

        self._reload()

    @classmethod
    def manage_versions(
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

        self._new_button = QPushButton("New Version", toolbar)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit", toolbar)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit)
        layout.addWidget(self._edit_button)

        self._lines_button = QPushButton("Budget Lines", toolbar)
        self._lines_button.setProperty("variant", "secondary")
        self._lines_button.clicked.connect(self._open_lines)
        layout.addWidget(self._lines_button)

        self._submit_button = QPushButton("Submit", toolbar)
        self._submit_button.setProperty("variant", "secondary")
        self._submit_button.clicked.connect(self._submit_version)
        layout.addWidget(self._submit_button)

        self._approve_button = QPushButton("Approve", toolbar)
        self._approve_button.setProperty("variant", "primary")
        self._approve_button.clicked.connect(self._approve_version)
        layout.addWidget(self._approve_button)

        self._cancel_button = QPushButton("Cancel Version", toolbar)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_version)
        layout.addWidget(self._cancel_button)

        self._clone_button = QPushButton("Clone", toolbar)
        self._clone_button.setProperty("variant", "secondary")
        self._clone_button.clicked.connect(self._clone_version)
        layout.addWidget(self._clone_button)

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
        self._table.setObjectName("BudgetVersionsTable")
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ("V#", "Version Name", "Type", "Budget Date", "Total Amount", "Status")
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
            self._versions = self._service_registry.project_budget_service.list_versions(
                self._project_id
            )
        except Exception as exc:
            show_error(self, "Budget Versions", str(exc))
            self._versions = []

        self._populate_table()
        self._update_action_state()

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for v in self._versions:
            row = self._table.rowCount()
            self._table.insertRow(row)

            num_item = QTableWidgetItem(str(v.version_number))
            num_item.setData(Qt.ItemDataRole.UserRole, v.id)
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, num_item)

            self._table.setItem(row, 1, QTableWidgetItem(v.version_name))
            type_item = QTableWidgetItem(v.version_type_code)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, type_item)
            self._table.setItem(row, 3, QTableWidgetItem(str(v.budget_date)))

            amount_item = QTableWidgetItem(f"{v.total_budget_amount:,.2f}")
            amount_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(row, 4, amount_item)

            status_item = QTableWidgetItem(v.status_code)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 5, status_item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._versions)
        self._count_label.setText(
            f"{count} version" if count == 1 else f"{count} versions"
        )

    def _selected_version(self) -> ProjectBudgetVersionListItemDTO | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        version_id = item.data(Qt.ItemDataRole.UserRole)
        for v in self._versions:
            if v.id == version_id:
                return v
        return None

    def _update_action_state(self) -> None:
        selected = self._selected_version()
        has_selection = selected is not None
        status = selected.status_code if selected else ""

        self._edit_button.setEnabled(has_selection and status in ("draft", "submitted"))
        self._lines_button.setEnabled(has_selection)
        self._submit_button.setEnabled(has_selection and status == "draft")
        self._approve_button.setEnabled(has_selection and status == "submitted")
        self._cancel_button.setEnabled(has_selection and status in ("draft", "submitted"))
        self._clone_button.setEnabled(has_selection)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create(self) -> None:
        result = BudgetVersionFormDialog.create_version(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            project_code=self._project_code,
            versions=self._versions,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _open_edit(self) -> None:
        selected = self._selected_version()
        if selected is None or selected.status_code not in ("draft", "submitted"):
            return
        result = BudgetVersionFormDialog.edit_version(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            project_code=self._project_code,
            versions=self._versions,
            version_id=selected.id,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _open_lines(self) -> None:
        selected = self._selected_version()
        if selected is None:
            return
        from seeker_accounting.modules.budgeting.ui.budget_lines_dialog import BudgetLinesDialog

        BudgetLinesDialog.manage_lines(
            self._service_registry,
            company_id=self._company_id,
            project_id=self._project_id,
            version_id=selected.id,
            version_name=selected.version_name,
            version_status=selected.status_code,
            parent=self,
        )
        self._reload()

    def _submit_version(self) -> None:
        selected = self._selected_version()
        if selected is None or selected.status_code != "draft":
            return
        choice = QMessageBox.question(
            self,
            "Submit Budget Version",
            f"Submit version V{selected.version_number} — {selected.version_name} for approval?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.budget_approval_service.submit_version(
                SubmitProjectBudgetVersionCommand(
                    version_id=selected.id,
                    company_id=self._company_id,
                )
            )
            show_info(self, "Submitted", "Budget version submitted for approval.")
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Submit Failed", str(exc))
        self._reload()

    def _approve_version(self) -> None:
        selected = self._selected_version()
        if selected is None or selected.status_code != "submitted":
            return
        choice = QMessageBox.question(
            self,
            "Approve Budget Version",
            f"Approve version V{selected.version_number} — {selected.version_name}?\n\n"
            "Any previously approved version will be superseded.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            user_id = self._service_registry.app_context.current_user_id or 0
            self._service_registry.budget_approval_service.approve_version(
                ApproveProjectBudgetVersionCommand(
                    version_id=selected.id,
                    company_id=self._company_id,
                    approved_by_user_id=user_id,
                )
            )
            show_info(self, "Approved", "Budget version approved.")
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Approval Failed", str(exc))
        self._reload()

    def _cancel_version(self) -> None:
        selected = self._selected_version()
        if selected is None or selected.status_code not in ("draft", "submitted"):
            return
        choice = QMessageBox.question(
            self,
            "Cancel Budget Version",
            f"Cancel version V{selected.version_number} — {selected.version_name}?\n\n"
            "This action cannot be undone.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.budget_approval_service.cancel_version(
                CancelProjectBudgetVersionCommand(
                    version_id=selected.id,
                    company_id=self._company_id,
                )
            )
            show_info(self, "Cancelled", "Budget version cancelled.")
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Cancel Failed", str(exc))
        self._reload()

    def _clone_version(self) -> None:
        selected = self._selected_version()
        if selected is None:
            return

        command = CopyBudgetVersionDialog.copy_version(
            company_id=self._company_id,
            project_id=self._project_id,
            source=selected,
            parent=self,
        )
        if command is None:
            return

        try:
            result = self._service_registry.budget_approval_service.clone_version(command)
            show_info(
                self,
                "Copy Created",
                f"New draft version V{result.version_number} — \"{result.version_name}\" "
                f"created with {result.total_budget_amount:,.2f} total budget.",
            )
        except (ValidationError, NotFoundError, ConflictError) as exc:
            show_error(self, "Copy Failed", str(exc))
        self._reload()
