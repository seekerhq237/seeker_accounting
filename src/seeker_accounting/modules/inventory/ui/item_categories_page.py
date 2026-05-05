from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.inventory.dto.inventory_reference_commands import (
    CreateItemCategoryCommand,
    UpdateItemCategoryCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_dto import ItemCategoryDTO
from seeker_accounting.platform.exceptions import ConflictError, PermissionDeniedError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error


ITEM_CATEGORY_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="code", title="Code"),
    DataTableColumn(key="name", title="Name"),
    DataTableColumn(key="description", title="Description"),
    DataTableColumn(key="active", title="Active"),
)


_log = logging.getLogger(__name__)


class _CategoryDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        category_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._category_id = category_id
        self._saved: ItemCategoryDTO | None = None

        is_edit = category_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Item Category — {company_name}")
        self.setModal(True)
        apply_window_size(self, "modules.inventory.ui.item.categories.page.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = QFrame(self)
        card.setObjectName("PageCard")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self._code_input = QLineEdit(card)
        self._code_input.setPlaceholderText("Unique category code")
        form.addRow("Code", self._code_input)

        self._name_input = QLineEdit(card)
        self._name_input.setPlaceholderText("Category name")
        form.addRow("Name", self._name_input)

        self._desc_input = QPlainTextEdit(card)
        self._desc_input.setMaximumHeight(60)
        form.addRow("Description", self._desc_input)

        self._active_checkbox = QCheckBox("Active", card)
        self._active_checkbox.setChecked(True)
        if is_edit:
            form.addRow("", self._active_checkbox)

        layout.addWidget(card)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if is_edit:
            self._load()

    @property
    def saved(self) -> ItemCategoryDTO | None:
        return self._saved

    def _load(self) -> None:
        try:
            cat = self._service_registry.item_category_service.get_item_category(
                self._company_id, self._category_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._code_input.setText(cat.code)
        self._name_input.setText(cat.name)
        self._desc_input.setPlainText(cat.description or "")
        self._active_checkbox.setChecked(cat.is_active)

    def _submit(self) -> None:
        self._error_label.hide()
        code = self._code_input.text().strip()
        name = self._name_input.text().strip()
        description = self._desc_input.toPlainText().strip() or None
        is_active = self._active_checkbox.isChecked()
        try:
            if self._category_id is None:
                self._saved = self._service_registry.item_category_service.create_item_category(
                    self._company_id, CreateItemCategoryCommand(code=code, name=name, description=description)
                )
            else:
                self._saved = self._service_registry.item_category_service.update_item_category(
                    self._company_id,
                    self._category_id,
                    UpdateItemCategoryCommand(code=code, name=name, description=description, is_active=is_active),
                )
            self.accept()
        except PermissionDeniedError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
        except (ValidationError, ConflictError) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()


class ItemCategoriesPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    def reload(self) -> None:
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            self._model.removeRows(0, self._model.rowCount())
            self._count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_company_state)
            return
        try:
            rows = self._service_registry.item_category_service.list_item_categories(active_company.company_id)
        except Exception as exc:
            self._model.removeRows(0, self._model.rowCount())
            self._count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            show_error(self, "Item Categories", f"Could not load data.\n\n{exc}")
            return
        self._populate(rows)
        self._sync_stack(active_company, rows)
        self._update_action_state()

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Item Categories",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        has_company = active_company is not None
        has_selection = bool(self._table.selected_rows())
        permission_service = self._service_registry.permission_service
        self._new_btn.setEnabled(
            has_company and permission_service.has_permission("inventory.categories.create")
        )
        self._edit_btn.setEnabled(
            has_company
            and has_selection
            and permission_service.has_permission("inventory.categories.edit")
        )

    def _build_toolbar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel('Item Categories', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._count_label = QLabel(card)
        self._count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._count_label)

        layout.addStretch(1)
        self._new_btn = QPushButton("New Category", card)
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.clicked.connect(self._on_new)
        layout.addWidget(self._new_btn)

        self._edit_btn = QPushButton("Edit", card)
        self._edit_btn.setProperty("variant", "secondary")
        self._edit_btn.clicked.connect(self._on_edit)
        layout.addWidget(self._edit_btn)

        refresh_btn = QPushButton("Refresh", card)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(self.reload)
        layout.addWidget(refresh_btn)
        return card

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_company_state = self._build_no_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = QStandardItemModel(0, len(ITEM_CATEGORY_COLUMNS), self)
        self._model.setHorizontalHeaderLabels([c.title for c in ITEM_CATEGORY_COLUMNS])

        self._table = DataTable(
            columns=ITEM_CATEGORY_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No item categories to display.",
            parent=card,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 3)
        self._table.row_activated.connect(lambda _row: self._on_edit())
        self._table.selection_changed.connect(lambda _rows: self._update_action_state())
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("No item categories", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel("Create item categories to group your inventory items.", card)
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addStretch(1)
        return card

    def _build_no_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel("Item categories are company-scoped.", card)
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        actions = QWidget(card)
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 4, 0, 0)
        al.addStretch(1)
        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate(self, rows: list[ItemCategoryDTO]) -> None:
        self._rows: list[ItemCategoryDTO] = list(rows)
        self._model.removeRows(0, self._model.rowCount())
        for row in rows:
            self._model.appendRow([
                self._make_item(row.code, user_data=row.id),
                self._make_item(row.name),
                self._make_item(row.description or ""),
                self._make_item("active" if row.is_active else "inactive"),
            ])
        count = len(rows)
        self._count_label.setText(f"{count} record" if count == 1 else f"{count} records")

    def _sync_stack(self, active_company: ActiveCompanyDTO | None, rows: list) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_company_state)
        elif rows:
            self._stack.setCurrentWidget(self._table_surface)
        else:
            self._stack.setCurrentWidget(self._empty_state)

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _on_new(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Item Categories", "Select an active company first.")
            return
        if not self._service_registry.permission_service.has_permission("inventory.categories.create"):
            self._show_permission_denied("inventory.categories.create")
            return
        dialog = _CategoryDialog(self._service_registry, company.company_id, company.company_name, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _on_edit(self) -> None:
        company = self._active_company()
        if company is None:
            return
        rows = self._table.selected_rows()
        if not rows:
            return
        if not self._service_registry.permission_service.has_permission("inventory.categories.edit"):
            self._show_permission_denied("inventory.categories.edit")
            return
        idx = rows[0]
        if not (0 <= idx < len(getattr(self, "_rows", []))):
            return
        cat_id = self._rows[idx].id
        dialog = _CategoryDialog(
            self._service_registry, company.company_id, company.company_name, category_id=cat_id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()
