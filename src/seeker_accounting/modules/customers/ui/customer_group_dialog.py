from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerGroupCommand,
    UpdateCustomerGroupCommand,
)
from seeker_accounting.modules.customers.dto.customer_dto import (
    CustomerGroupDTO,
    CustomerGroupListItemDTO,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, apply_status_chip_to_column


class CustomerGroupDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._groups: list[CustomerGroupListItemDTO] = []

        super().__init__("Customer Groups", parent, help_key="dialog.customer_group")
        self.setObjectName("CustomerGroupDialog")
        apply_window_size(self, "modules.customers.ui.customer.group.dialog.0")

        intro_label = QLabel(
            "Keep customer segmentation compact and deliberate so later receivables workflows can reuse stable group references without widening the customer form.",
            self,
        )
        intro_label.setObjectName("PageSummary")
        intro_label.setWordWrap(True)
        self.body_layout.addWidget(intro_label)
        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_table_section())
        self.body_layout.addWidget(self._build_editor_section())
        self.body_layout.addStretch(1)

        close_button = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setProperty("variant", "secondary")

        self._new_button.clicked.connect(self._start_new_group)
        self._save_button.clicked.connect(self._save_group)
        self._deactivate_button.clicked.connect(self._deactivate_group)
        self._refresh_button.clicked.connect(self.reload_groups)
        self._table.selection_changed.connect(lambda _rows: self._sync_editor_state())

        self.reload_groups()

    @classmethod
    def manage_groups(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog.exec()

    def _build_table_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Groups", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._model = QStandardItemModel(0, 3, card)
        self._model.setHorizontalHeaderLabels(["Code", "Name", "Status"])
        self._table = DataTable(
            columns=(
                DataTableColumn(key="code", title="Code"),
                DataTableColumn(key="name", title="Name"),
                DataTableColumn(key="status", title="Status"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._table.set_model(self._model)
        apply_status_chip_to_column(self._table.view(), 2)
        self._table.view().doubleClicked.connect(lambda *_: self._code_edit.setFocus())
        layout.addWidget(self._table)
        return card

    def _build_editor_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Selected Group", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._code_edit = QLineEdit(card)
        self._code_edit.setPlaceholderText("RETAIL")
        grid.addWidget(create_field_block("Code", self._code_edit), 0, 0)

        self._name_edit = QLineEdit(card)
        self._name_edit.setPlaceholderText("Retail Customers")
        grid.addWidget(create_field_block("Name", self._name_edit), 0, 1)

        self._active_checkbox = QCheckBox("Group is active", card)
        self._active_checkbox.setChecked(True)
        grid.addWidget(self._active_checkbox, 1, 0)

        layout.addLayout(grid)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        self._new_button = QPushButton("New Group", actions)
        self._new_button.setProperty("variant", "secondary")
        actions_layout.addWidget(self._new_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._save_button = QPushButton("Save Group", actions)
        self._save_button.setProperty("variant", "primary")
        actions_layout.addWidget(self._save_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._deactivate_button = QPushButton("Deactivate", actions)
        self._deactivate_button.setProperty("variant", "secondary")
        actions_layout.addWidget(self._deactivate_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._refresh_button = QPushButton("Refresh", actions)
        self._refresh_button.setProperty("variant", "ghost")
        actions_layout.addWidget(self._refresh_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        return card

    def reload_groups(self, selected_group_id: int | None = None) -> None:
        try:
            self._groups = self._service_registry.customer_service.list_customer_groups(
                self._company_id,
                active_only=False,
            )
        except Exception as exc:
            self._groups = []
            self._model.removeRows(0, self._model.rowCount())
            self._set_error(f"Customer groups could not be loaded.\n\n{exc}")
            return

        self._set_error(None)
        self._populate_table()
        self._restore_selection(selected_group_id)
        self._sync_editor_state()

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for group in self._groups:
            self._model.appendRow([
                self._make_item(group.code, user_data=group.id),
                self._make_item(group.name),
                self._make_item("active" if group.is_active else "inactive"),
            ])

    def _restore_selection(self, selected_group_id: int | None) -> None:
        if not self._groups:
            self._clear_editor()
            return
        if selected_group_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, g in enumerate(self._groups) if g.id == selected_group_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._table.view().selectionModel()
        if sm is None:
            return
        sm.select(proxy_index, sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows)
        self._table.view().scrollTo(proxy_index)

    def _selected_group(self) -> CustomerGroupListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        row = rows[0]
        if row < 0 or row >= len(self._groups):
            return None
        return self._groups[row]

    def _sync_editor_state(self) -> None:
        group = self._selected_group()
        if group is None:
            self._deactivate_button.setEnabled(False)
            return

        try:
            detail = self._service_registry.customer_service.get_customer_group(self._company_id, group.id)
        except NotFoundError:
            self.reload_groups()
            return

        self._code_edit.setText(detail.code)
        self._name_edit.setText(detail.name)
        self._active_checkbox.setChecked(detail.is_active)
        self._deactivate_button.setEnabled(detail.is_active)

    def _clear_editor(self) -> None:
        self._table.view().clearSelection()
        self._code_edit.clear()
        self._name_edit.clear()
        self._active_checkbox.setChecked(True)
        self._deactivate_button.setEnabled(False)

    def _start_new_group(self) -> None:
        self._set_error(None)
        self._clear_editor()
        self._code_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def _save_group(self) -> None:
        self._set_error(None)
        code = self._code_edit.text().strip()
        name = self._name_edit.text().strip()

        if not code:
            self._set_error("Code is required.")
            self._code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not name:
            self._set_error("Name is required.")
            self._name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        selected_group = self._selected_group()
        try:
            if selected_group is None:
                saved_group = self._service_registry.customer_service.create_customer_group(
                    self._company_id,
                    CreateCustomerGroupCommand(code=code, name=name),
                )
            else:
                saved_group = self._service_registry.customer_service.update_customer_group(
                    self._company_id,
                    selected_group.id,
                    UpdateCustomerGroupCommand(
                        code=code,
                        name=name,
                        is_active=self._active_checkbox.isChecked(),
                    ),
                )
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Customer Groups", str(exc))
            self.reload_groups()
            return

        self.reload_groups(selected_group_id=saved_group.id)

    def _deactivate_group(self) -> None:
        selected_group = self._selected_group()
        if selected_group is None:
            show_info(self, "Customer Groups", "Select a customer group to deactivate.")
            return
        if not selected_group.is_active:
            show_info(self, "Customer Groups", "The selected customer group is already inactive.")
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Customer Group",
            f"Deactivate customer group '{selected_group.name}' ({selected_group.code})?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.customer_service.deactivate_customer_group(self._company_id, selected_group.id)
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))
            self.reload_groups()
            return

        self.reload_groups(selected_group_id=selected_group.id)
