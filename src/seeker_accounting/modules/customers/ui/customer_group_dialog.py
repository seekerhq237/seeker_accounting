from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


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
        self.resize(700, 520)

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
        self._table.itemSelectionChanged.connect(self._sync_editor_state)

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

        self._table = QTableWidget(card)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(("Code", "Name", "Status"))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemDoubleClicked.connect(lambda *_args: self._code_edit.setFocus())
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
            self._table.setRowCount(0)
            self._set_error(f"Customer groups could not be loaded.\n\n{exc}")
            return

        self._set_error(None)
        self._populate_table()
        self._restore_selection(selected_group_id)
        self._sync_editor_state()

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for group in self._groups:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (group.code, group.name, "Active" if group.is_active else "Inactive")
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, group.id)
                if column_index == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, column_index, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

    def _restore_selection(self, selected_group_id: int | None) -> None:
        if self._table.rowCount() == 0:
            self._clear_editor()
            return
        if selected_group_id is None:
            self._table.selectRow(0)
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_group_id:
                self._table.selectRow(row_index)
                return
        self._table.selectRow(0)

    def _selected_group(self) -> CustomerGroupListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        group_id = item.data(Qt.ItemDataRole.UserRole)
        for group in self._groups:
            if group.id == group_id:
                return group
        return None

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
        self._table.clearSelection()
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
