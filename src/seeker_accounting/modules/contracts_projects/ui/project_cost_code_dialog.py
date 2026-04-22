from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from seeker_accounting.modules.contracts_projects.dto.project_cost_code_commands import (
    CreateProjectCostCodeCommand,
    UpdateProjectCostCodeCommand,
)
from seeker_accounting.modules.contracts_projects.dto.project_cost_code_dto import (
    ProjectCostCodeDetailDTO,
    ProjectCostCodeListItemDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


# ── Cost Code Form Dialog ────────────────────────────────────────────────


class ProjectCostCodeFormDialog(BaseDialog):
    """Create or edit a single project cost code."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        cost_code_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._cost_code_id = cost_code_id
        self._saved: ProjectCostCodeDetailDTO | None = None

        title = "New Cost Code" if cost_code_id is None else "Edit Cost Code"
        super().__init__(title, parent, help_key="dialog.project_cost_code")
        self.setObjectName("ProjectCostCodeFormDialog")
        self.resize(560, 460)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_form_section())
        self.body_layout.addWidget(self._build_description_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        save_btn = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setText("Create" if cost_code_id is None else "Save Changes")
            save_btn.setProperty("variant", "primary")

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")

        if self._cost_code_id is not None:
            self._load_cost_code()
        else:
            self._suggest_code()

    @property
    def saved_cost_code(self) -> ProjectCostCodeDetailDTO | None:
        return self._saved

    @classmethod
    def create_cost_code(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> ProjectCostCodeDetailDTO | None:
        dialog = cls(service_registry, company_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_cost_code
        return None

    @classmethod
    def edit_cost_code(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        cost_code_id: int,
        parent: QWidget | None = None,
    ) -> ProjectCostCodeDetailDTO | None:
        dialog = cls(service_registry, company_id, cost_code_id=cost_code_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_cost_code
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

        title = QLabel("Cost Code Details", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._code_edit = QLineEdit(card)
        self._code_edit.setPlaceholderText("LAB-01")
        grid.addWidget(create_field_block("Code", self._code_edit), 0, 0)

        self._name_edit = QLineEdit(card)
        self._name_edit.setPlaceholderText("Cost code name")
        grid.addWidget(create_field_block("Name", self._name_edit), 0, 1)

        self._type_combo = QComboBox(card)
        self._type_combo.addItem("Labour", "labour")
        self._type_combo.addItem("Materials", "materials")
        self._type_combo.addItem("Equipment", "equipment")
        self._type_combo.addItem("Subcontract", "subcontract")
        self._type_combo.addItem("Overhead", "overhead")
        self._type_combo.addItem("Other", "other")
        grid.addWidget(create_field_block("Type", self._type_combo), 1, 0, 1, 2)

        layout.addLayout(grid)
        return card

    def _build_description_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Description", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._description_edit = QPlainTextEdit(card)
        self._description_edit.setPlaceholderText("Optional description")
        self._description_edit.setFixedHeight(70)
        layout.addWidget(self._description_edit)
        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("project_cost_code", self._company_id)
            self._code_edit.setText(code)
        except Exception:
            pass

    def _load_cost_code(self) -> None:
        try:
            detail = self._service_registry.project_cost_code_service.get_cost_code_detail(
                self._cost_code_id or 0
            )
        except NotFoundError as exc:
            show_error(self, "Not Found", str(exc))
            self.reject()
            return

        self._code_edit.setText(detail.code)
        self._code_edit.setReadOnly(True)
        self._name_edit.setText(detail.name)
        idx = self._type_combo.findData(detail.cost_code_type_code)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._description_edit.setPlainText(detail.description or "")

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
            self._set_error("Code is required.")
            return
        if not name:
            self._set_error("Name is required.")
            return

        type_code = self._type_combo.currentData()
        description = self._description_edit.toPlainText().strip() or None

        svc = self._service_registry.project_cost_code_service

        try:
            if self._cost_code_id is None:
                result = svc.create_cost_code(
                    CreateProjectCostCodeCommand(
                        company_id=self._company_id,
                        code=code,
                        name=name,
                        cost_code_type_code=type_code,
                        description=description,
                    )
                )
            else:
                result = svc.update_cost_code(
                    self._cost_code_id,
                    UpdateProjectCostCodeCommand(
                        name=name,
                        cost_code_type_code=type_code,
                        description=description,
                    ),
                )
            self._saved = result
            self.accept()
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))


# ── Cost Codes List Dialog ────────────────────────────────────────────────


class ProjectCostCodesDialog(BaseDialog):
    """List and manage cost codes for the active company."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Cost Codes — {company_name}", parent, help_key="dialog.project_cost_code_list")
        self._service_registry = service_registry
        self._company_id = company_id
        self._cost_codes: list[ProjectCostCodeListItemDTO] = []

        self.setObjectName("ProjectCostCodesDialog")
        self.resize(820, 520)

        self.body_layout.addWidget(self._build_toolbar())
        self.body_layout.addWidget(self._build_table_card(), 1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        close_btn = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setProperty("variant", "secondary")

        self._reload()

    @classmethod
    def manage_cost_codes(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog.exec()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget(self)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._new_button = QPushButton("New Cost Code", toolbar)
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
        self._table.setObjectName("ProjectCostCodesTable")
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ("Code", "Name", "Type", "Default Account", "Active")
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
        svc = self._service_registry.project_cost_code_service
        try:
            self._cost_codes = svc.list_cost_codes(self._company_id)
        except Exception as exc:
            self._cost_codes = []
            show_error(self, "Cost Codes", f"Could not load cost codes.\n\n{exc}")

        self._populate_table()
        count = len(self._cost_codes)
        self._count_label.setText(f"{count} cost code{'s' if count != 1 else ''}")

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

        for cc in self._cost_codes:
            row = self._table.rowCount()
            self._table.insertRow(row)
            values = (
                cc.code,
                cc.name,
                cc.cost_code_type_code,
                cc.default_account_code or "",
                "Yes" if cc.is_active else "No",
            )
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, cc.id)
                if col in {2, 4}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

    def _selected_cc(self) -> ProjectCostCodeListItemDTO | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        cc_id = item.data(Qt.ItemDataRole.UserRole)
        for cc in self._cost_codes:
            if cc.id == cc_id:
                return cc
        return None

    def _update_action_state(self) -> None:
        selected = self._selected_cc()
        is_active = selected.is_active if selected else None

        self._edit_button.setEnabled(selected is not None)
        self._deactivate_button.setEnabled(is_active is True)
        self._reactivate_button.setEnabled(is_active is False)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create(self) -> None:
        result = ProjectCostCodeFormDialog.create_cost_code(
            self._service_registry,
            self._company_id,
            parent=self,
        )
        if result is not None:
            self._reload(selected_id=result.id)

    def _open_edit(self) -> None:
        selected = self._selected_cc()
        if selected is None:
            return
        result = ProjectCostCodeFormDialog.edit_cost_code(
            self._service_registry,
            self._company_id,
            cost_code_id=selected.id,
            parent=self,
        )
        if result is not None:
            self._reload(selected_id=result.id)

    def _deactivate_selected(self) -> None:
        selected = self._selected_cc()
        if selected is None:
            return
        choice = QMessageBox.question(
            self, "Deactivate Cost Code",
            f"Deactivate cost code '{selected.code}'?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.project_cost_code_service.deactivate_cost_code(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Cost Codes", str(exc))
        self._reload(selected_id=selected.id)

    def _reactivate_selected(self) -> None:
        selected = self._selected_cc()
        if selected is None:
            return
        try:
            self._service_registry.project_cost_code_service.reactivate_cost_code(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Cost Codes", str(exc))
        self._reload(selected_id=selected.id)
