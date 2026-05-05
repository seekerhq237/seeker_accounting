from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
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
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


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
        apply_window_size(self, "modules.contracts.projects.ui.project.cost.code.dialog.0")

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
        apply_window_size(self, "modules.contracts.projects.ui.project.cost.code.dialog.1")

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

        self._model = QStandardItemModel(0, 5, card)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="code", title="Code"),
                DataTableColumn(key="name", title="Name"),
                DataTableColumn(key="type", title="Type"),
                DataTableColumn(key="default_account", title="Default Account"),
                DataTableColumn(key="active", title="Active"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._table.set_model(self._model)
        self._table.selection_changed.connect(lambda _: self._update_action_state())
        self._table.view().doubleClicked.connect(self._on_double_clicked)
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
            target_idx = next(
                (i for i, cc in enumerate(self._cost_codes) if cc.id == selected_id), 0
            )
        else:
            target_idx = 0
        proxy = self._table.view().model()
        if proxy is None:
            self._update_action_state()
            return
        src_index = self._model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if proxy_index.isValid():
            sm = self._table.view().selectionModel()
            if sm is not None:
                sm.select(proxy_index, sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows)
                self._table.view().scrollTo(proxy_index)
        self._update_action_state()

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())

        for cc in self._cost_codes:
            self._model.appendRow([
                self._make_item(cc.code, user_data=cc.id),
                self._make_item(cc.name),
                self._make_item(cc.cost_code_type_code),
                self._make_item(cc.default_account_code or ""),
                self._make_item("Yes" if cc.is_active else "No"),
            ])

    def _selected_cc(self) -> ProjectCostCodeListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        id_item = self._model.item(rows[0], 0)
        if id_item is None:
            return None
        cc_id = id_item.data(Qt.ItemDataRole.UserRole)
        for cc in self._cost_codes:
            if cc.id == cc_id:
                return cc
        return None

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _on_double_clicked(self, _index) -> None:
        self._open_edit()

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
