"""RolesPage — manage roles and their permission assignments."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.administration.dto.user_dto import RoleDTO
from seeker_accounting.modules.administration.ui.permission_assignment_dialog import PermissionAssignmentDialog
from seeker_accounting.modules.administration.ui.role_edit_dialog import RoleEditDialog
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

logger = logging.getLogger(__name__)

_COL_NAME = 0
_COL_CODE = 1
_COL_DESCRIPTION = 2
_COL_SYSTEM = 3
_COL_PERM_COUNT = 4
_COL_COUNT = 5

_ROLE_ROLE_ID = Qt.ItemDataRole.UserRole
_ROLE_IS_SYSTEM = Qt.ItemDataRole.UserRole + 1


class RolesPage(QWidget):
    """Workspace page for role CRUD and permission assignment."""

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._roles: list[RoleDTO] = []
        self._perm_counts: dict[int, int] = {}

        self.setObjectName("RolesPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_action_bar())
        root.addWidget(self._build_content_stack(), 1)

        self._search_edit.textChanged.connect(self._apply_search_filter)
        self._table.itemSelectionChanged.connect(self._update_action_state)

        self.reload_roles()

    # ── public entry point ───────────────────────────────────────────

    def reload_roles(self, selected_role_id: int | None = None) -> None:
        perm = self._service_registry.permission_service

        if not perm.has_permission("administration.roles.view"):
            self._roles = []
            self._perm_counts.clear()
            self._table.setRowCount(0)
            self._record_count_label.setText("Access denied")
            self._stack.setCurrentWidget(self._access_denied_state)
            self._update_action_state()
            return

        try:
            self._roles = self._service_registry.role_service.list_roles()
            self._perm_counts.clear()
            for role_dto in self._roles:
                detail = self._service_registry.role_service.get_role(role_dto.id)
                self._perm_counts[role_dto.id] = len(detail.permissions)
        except Exception as exc:
            logger.exception("Failed to load roles.")
            show_error(self, "Load Error", str(exc))
            self._roles = []

        self._populate_table()
        self._apply_search_filter()

        if not self._roles:
            self._record_count_label.setText("No roles")
            self._stack.setCurrentWidget(self._empty_state)
        else:
            count = len(self._roles)
            self._record_count_label.setText(f"{count} role{'s' if count != 1 else ''}")
            self._stack.setCurrentWidget(self._table_surface)

        if selected_role_id is not None:
            self._restore_selection(selected_role_id)

        self._update_action_state()

    # ── toolbar ──────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("PageToolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Roles", bar)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel("", bar)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)
        layout.addStretch(1)

        self._search_edit = QLineEdit(bar)
        self._search_edit.setPlaceholderText("Search roles…")
        self._search_edit.setFixedWidth(200)
        layout.addWidget(self._search_edit)

        self._new_button = QPushButton("New Role", bar)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._handle_new_role)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit", bar)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._handle_edit_role)
        layout.addWidget(self._edit_button)

        self._permissions_button = QPushButton("Manage Permissions", bar)
        self._permissions_button.setProperty("variant", "secondary")
        self._permissions_button.clicked.connect(self._handle_manage_permissions)
        layout.addWidget(self._permissions_button)

        self._delete_button = QPushButton("Delete", bar)
        self._delete_button.setProperty("variant", "secondary")
        self._delete_button.clicked.connect(self._handle_delete_role)
        layout.addWidget(self._delete_button)

        refresh_btn = QPushButton("Refresh", bar)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(lambda: self.reload_roles())
        layout.addWidget(refresh_btn)

        return bar

    # ── content stack ────────────────────────────────────────────────

    def _build_content_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget(self)

        # table surface
        self._table_surface = QFrame(self._stack)
        self._table_surface.setObjectName("PageCard")
        ts = QVBoxLayout(self._table_surface)
        ts.setContentsMargins(0, 0, 0, 0)
        ts.setSpacing(0)

        self._table = QTableWidget(0, _COL_COUNT, self._table_surface)
        self._table.setHorizontalHeaderLabels([
            "Name", "Code", "Description", "System", "Permissions",
        ])
        configure_compact_table(self._table)
        ts.addWidget(self._table)
        self._stack.addWidget(self._table_surface)

        # empty state
        self._empty_state = self._make_centred_card(
            "No roles found.",
            action_label="Create First Role",
            action_callback=self._handle_new_role,
        )
        self._stack.addWidget(self._empty_state)

        # access denied
        self._access_denied_state = self._make_centred_card(
            "You do not have permission to view roles.",
        )
        self._stack.addWidget(self._access_denied_state)

        return self._stack

    def _make_centred_card(
        self,
        message: str,
        action_label: str | None = None,
        action_callback=None,
    ) -> QFrame:
        card = QFrame(self._stack)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel(message, card)
        lbl.setObjectName("EmptyStateTitle")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        if action_label and action_callback:
            btn = QPushButton(action_label, card)
            btn.setProperty("variant", "primary")
            btn.clicked.connect(action_callback)
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)

        return card

    # ── table ────────────────────────────────────────────────────────

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for role in self._roles:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(role.name)
            name_item.setData(_ROLE_ROLE_ID, role.id)
            name_item.setData(_ROLE_IS_SYSTEM, role.is_system)
            self._table.setItem(row, _COL_NAME, name_item)

            self._table.setItem(row, _COL_CODE, QTableWidgetItem(role.code))
            self._table.setItem(row, _COL_DESCRIPTION, QTableWidgetItem(role.description or ""))

            sys_item = QTableWidgetItem("System" if role.is_system else "Custom")
            sys_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_SYSTEM, sys_item)

            perm_count = self._perm_counts.get(role.id, 0)
            perm_item = QTableWidgetItem(str(perm_count))
            perm_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_PERM_COUNT, perm_item)

        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)

    def _apply_search_filter(self) -> None:
        query = self._search_edit.text().lower().strip()
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, _COL_NAME)
            code_item = self._table.item(row, _COL_CODE)
            if name_item is None:
                continue
            name = name_item.text().lower()
            code = code_item.text().lower() if code_item else ""
            self._table.setRowHidden(row, bool(query) and query not in name and query not in code)

    def _restore_selection(self, role_id: int) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_NAME)
            if item and item.data(_ROLE_ROLE_ID) == role_id:
                self._table.selectRow(row)
                return

    # ── selection helpers ────────────────────────────────────────────

    def _selected_row(self) -> int | None:
        items = self._table.selectedItems()
        return items[0].row() if items else None

    def _selected_role_id(self) -> int | None:
        row = self._selected_row()
        if row is None:
            return None
        item = self._table.item(row, _COL_NAME)
        return item.data(_ROLE_ROLE_ID) if item else None

    def _selected_is_system(self) -> bool | None:
        row = self._selected_row()
        if row is None:
            return None
        item = self._table.item(row, _COL_NAME)
        return item.data(_ROLE_IS_SYSTEM) if item else None

    def _selected_role_dto(self) -> RoleDTO | None:
        role_id = self._selected_role_id()
        if role_id is None:
            return None
        for r in self._roles:
            if r.id == role_id:
                return r
        return None

    # ── action state ─────────────────────────────────────────────────

    def _update_action_state(self) -> None:
        has_selection = self._selected_role_id() is not None
        is_system = self._selected_is_system()
        perm = self._service_registry.permission_service

        self._new_button.setEnabled(perm.has_permission("administration.roles.create"))
        self._edit_button.setEnabled(has_selection and perm.has_permission("administration.roles.edit"))
        self._permissions_button.setEnabled(
            has_selection and perm.has_permission("administration.role_permissions.assign")
        )
        self._delete_button.setEnabled(
            has_selection
            and is_system is not True
            and perm.has_permission("administration.roles.delete")
        )

    # ── handlers ─────────────────────────────────────────────────────

    def _handle_new_role(self) -> None:
        result = RoleEditDialog.create_role(
            role_service=self._service_registry.role_service,
            parent=self,
        )
        if result is not None:
            self.reload_roles(selected_role_id=result.id)

    def _handle_edit_role(self) -> None:
        role = self._selected_role_dto()
        if role is None:
            return
        result = RoleEditDialog.edit_role(
            role_service=self._service_registry.role_service,
            role_dto=role,
            parent=self,
        )
        if result is not None:
            self.reload_roles(selected_role_id=result.id)

    def _handle_manage_permissions(self) -> None:
        role = self._selected_role_dto()
        if role is None:
            return
        changed = PermissionAssignmentDialog.manage(
            role_service=self._service_registry.role_service,
            role_dto=role,
            parent=self,
        )
        if changed:
            self.reload_roles(selected_role_id=role.id)

    def _handle_delete_role(self) -> None:
        role = self._selected_role_dto()
        if role is None:
            return
        if role.is_system:
            show_error(self, "Cannot Delete", "System roles cannot be deleted.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the role '{role.name}'?\n\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.role_service.delete_role(role.id)
        except ValidationError as exc:
            show_error(self, "Cannot Delete", str(exc))
            return
        except Exception as exc:
            logger.exception("Failed to delete role %s.", role.code)
            show_error(self, "Error", str(exc))
            return

        self.reload_roles()
