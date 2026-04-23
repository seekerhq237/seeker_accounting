"""AdministrationPage — manage users and access controls for the active company."""
from __future__ import annotations

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
from seeker_accounting.modules.administration.dto.user_commands import ChangePasswordCommand
from seeker_accounting.modules.administration.dto.user_dto import UserDTO, UserWithRolesDTO
from seeker_accounting.modules.administration.ui.password_change_dialog import PasswordChangeDialog
from seeker_accounting.modules.administration.ui.role_assignment_dialog import RoleAssignmentDialog
from seeker_accounting.modules.administration.ui.user_edit_dialog import UserEditDialog
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_COL_DISPLAY_NAME = 0
_COL_USERNAME = 1
_COL_EMAIL = 2
_COL_STATUS = 3
_COL_ROLES = 4
_COL_LAST_LOGIN = 5
_COL_COUNT = 6

_ROLE_USER_ID = Qt.ItemDataRole.UserRole
_ROLE_IS_ACTIVE = Qt.ItemDataRole.UserRole + 1


class AdministrationPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._users: list[UserWithRolesDTO] = []

        self.setObjectName("AdministrationPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._search_edit.textChanged.connect(self._apply_search_filter)
        self._table.itemSelectionChanged.connect(self._update_action_state)

        self.reload_users()

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def reload_users(self, selected_user_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._users = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        if not self._service_registry.permission_service.has_permission("administration.users.view"):
            self._users = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Access denied")
            self._stack.setCurrentWidget(self._access_denied_state)
            self._update_action_state()
            return

        try:
            self._users = self._service_registry.user_auth_service.list_users_for_company(
                active_company.company_id
            )
        except Exception as exc:
            show_error(self, "Load Error", str(exc))
            self._users = []

        self._populate_table()
        self._apply_search_filter()

        if not self._users:
            self._record_count_label.setText("No users")
            self._stack.setCurrentWidget(self._empty_state)
        else:
            count = len(self._users)
            self._record_count_label.setText(f"{count} user{'s' if count != 1 else ''}")
            self._stack.setCurrentWidget(self._table_surface)

        if selected_user_id is not None:
            self._restore_selection(selected_user_id)

        self._update_action_state()

    # ------------------------------------------------------------------ #
    # Toolbar
    # ------------------------------------------------------------------ #

    def _build_action_bar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("PageToolbar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 2, 8, 2)
        bar_layout.setSpacing(6)

        title = QLabel("Users", bar)
        title.setObjectName("ToolbarTitle")
        bar_layout.addWidget(title)

        self._record_count_label = QLabel("", bar)
        self._record_count_label.setObjectName("ToolbarMeta")
        bar_layout.addWidget(self._record_count_label)
        bar_layout.addStretch(1)

        self._search_edit = QLineEdit(bar)
        self._search_edit.setPlaceholderText("Search users…")
        self._search_edit.setFixedWidth(200)
        bar_layout.addWidget(self._search_edit)

        self._new_button = QPushButton("New User", bar)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._handle_new_user)
        bar_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit", bar)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._handle_edit_user)
        bar_layout.addWidget(self._edit_button)

        self._password_button = QPushButton("Change Password", bar)
        self._password_button.setProperty("variant", "secondary")
        self._password_button.clicked.connect(self._handle_change_password)
        bar_layout.addWidget(self._password_button)

        self._toggle_active_button = QPushButton("Deactivate", bar)
        self._toggle_active_button.setProperty("variant", "secondary")
        self._toggle_active_button.clicked.connect(self._handle_toggle_active)
        bar_layout.addWidget(self._toggle_active_button)

        self._roles_button = QPushButton("Manage Roles", bar)
        self._roles_button.setProperty("variant", "secondary")
        self._roles_button.clicked.connect(self._handle_manage_roles)
        bar_layout.addWidget(self._roles_button)

        refresh_btn = QPushButton("Refresh", bar)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(lambda: self.reload_users())
        bar_layout.addWidget(refresh_btn)

        return bar

    # ------------------------------------------------------------------ #
    # Content stack
    # ------------------------------------------------------------------ #

    def _build_content_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget(self)

        # Table surface
        self._table_surface = QFrame(self._stack)
        self._table_surface.setObjectName("PageCard")
        ts_layout = QVBoxLayout(self._table_surface)
        ts_layout.setContentsMargins(0, 0, 0, 0)
        ts_layout.setSpacing(0)

        self._table = QTableWidget(0, _COL_COUNT, self._table_surface)
        self._table.setHorizontalHeaderLabels([
            "Display Name", "Username", "Email", "Status", "Roles", "Last Login",
        ])
        configure_compact_table(self._table)
        ts_layout.addWidget(self._table)
        self._stack.addWidget(self._table_surface)

        # Empty state
        self._empty_state = self._make_centred_card(
            "No users found for this company.",
            action_label="Create First User",
            action_callback=self._handle_new_user,
        )
        self._stack.addWidget(self._empty_state)

        # No active company state
        self._no_active_company_state = self._make_centred_card(
            "No active company. Log out and log in to activate a company.",
        )
        self._stack.addWidget(self._no_active_company_state)

        # Access denied state
        self._access_denied_state = self._make_centred_card(
            "You do not have permission to view user administration.",
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

    # ------------------------------------------------------------------ #
    # Table
    # ------------------------------------------------------------------ #

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for record in self._users:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(record.user.display_name)
            name_item.setData(_ROLE_USER_ID, record.user.id)
            name_item.setData(_ROLE_IS_ACTIVE, record.user.is_active)
            self._table.setItem(row, _COL_DISPLAY_NAME, name_item)

            self._table.setItem(row, _COL_USERNAME, QTableWidgetItem(record.user.username))
            self._table.setItem(row, _COL_EMAIL, QTableWidgetItem(record.user.email or ""))

            status_text = "Active" if record.user.is_active else "Inactive"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_STATUS, status_item)

            role_names = ", ".join(r.name for r in record.roles) if record.roles else "—"
            self._table.setItem(row, _COL_ROLES, QTableWidgetItem(role_names))

            login_text = (
                record.user.last_login_at.strftime("%Y-%m-%d %H:%M")
                if record.user.last_login_at
                else ""
            )
            self._table.setItem(row, _COL_LAST_LOGIN, QTableWidgetItem(login_text))

        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)

    def _apply_search_filter(self) -> None:
        query = self._search_edit.text().lower().strip()
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, _COL_DISPLAY_NAME)
            username_item = self._table.item(row, _COL_USERNAME)
            if name_item is None:
                continue
            name = name_item.text().lower()
            username = username_item.text().lower() if username_item else ""
            self._table.setRowHidden(row, bool(query) and query not in name and query not in username)

    def _restore_selection(self, user_id: int) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_DISPLAY_NAME)
            if item and item.data(_ROLE_USER_ID) == user_id:
                self._table.selectRow(row)
                return

    # ------------------------------------------------------------------ #
    # Selection helpers
    # ------------------------------------------------------------------ #

    def _selected_row(self) -> int | None:
        items = self._table.selectedItems()
        return items[0].row() if items else None

    def _selected_user_id(self) -> int | None:
        row = self._selected_row()
        if row is None:
            return None
        item = self._table.item(row, _COL_DISPLAY_NAME)
        return item.data(_ROLE_USER_ID) if item else None

    def _selected_is_active(self) -> bool | None:
        row = self._selected_row()
        if row is None:
            return None
        item = self._table.item(row, _COL_DISPLAY_NAME)
        return item.data(_ROLE_IS_ACTIVE) if item else None

    def _selected_user_dto(self) -> UserDTO | None:
        user_id = self._selected_user_id()
        if user_id is None:
            return None
        for record in self._users:
            if record.user.id == user_id:
                return record.user
        return None

    # ------------------------------------------------------------------ #
    # Action state
    # ------------------------------------------------------------------ #

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        has_company = active_company is not None
        has_selection = self._selected_user_id() is not None
        perm = self._service_registry.permission_service

        current_user_id = self._service_registry.app_context.current_user_id
        is_self = has_selection and self._selected_user_id() == current_user_id

        self._new_button.setEnabled(
            has_company and perm.has_permission("administration.users.create")
        )
        can_edit = has_company and has_selection and perm.has_permission("administration.users.edit")
        self._edit_button.setEnabled(can_edit)
        self._password_button.setEnabled(can_edit)
        self._toggle_active_button.setEnabled(
            has_company and has_selection and not is_self
            and perm.has_permission("administration.users.deactivate")
        )
        self._roles_button.setEnabled(
            has_company and has_selection and not is_self
            and perm.has_permission("administration.user_roles.assign")
        )

        is_active = self._selected_is_active()
        self._toggle_active_button.setText("Activate" if is_active is False else "Deactivate")


    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #

    def _handle_active_company_changed(self) -> None:
        self.reload_users()

    def _handle_new_user(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        result = UserEditDialog.create_user(
            self._service_registry, active_company.company_id, parent=self
        )
        if result is not None:
            self.reload_users(selected_user_id=result.id)

    def _handle_edit_user(self) -> None:
        user_dto = self._selected_user_dto()
        if user_dto is None:
            return
        result = UserEditDialog.edit_user(self._service_registry, user_dto, parent=self)
        if result is not None:
            self.reload_users(selected_user_id=result.id)

    def _handle_change_password(self) -> None:
        user_dto = self._selected_user_dto()
        if user_dto is None:
            return
        password_result = PasswordChangeDialog.prompt(
            username=user_dto.username, allow_skip=False, parent=self
        )
        if password_result is None:
            return
        try:
            self._service_registry.user_auth_service.change_password(
                ChangePasswordCommand(
                    user_id=user_dto.id,
                    new_password=password_result.new_password,
                )
            )
            show_info(self, "Password Changed", f"Password updated for {user_dto.display_name}.")
        except ValidationError as exc:
            show_error(self, "Error", str(exc))
        except Exception as exc:
            show_error(self, "Error", str(exc))

    def _handle_toggle_active(self) -> None:
        user_dto = self._selected_user_dto()
        if user_dto is None:
            return

        new_state = not user_dto.is_active
        action = "activate" if new_state else "deactivate"
        confirm = QMessageBox.question(
            self,
            "Confirm",
            f"Are you sure you want to {action} '{user_dto.display_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.user_auth_service.set_user_active(
                user_id=user_dto.id, is_active=new_state
            )
            self.reload_users(selected_user_id=user_dto.id)
        except Exception as exc:
            show_error(self, "Error", str(exc))

    def _handle_manage_roles(self) -> None:
        user_dto = self._selected_user_dto()
        if user_dto is None:
            return
        RoleAssignmentDialog.manage(self._service_registry, user_dto, parent=self)
        self.reload_users(selected_user_id=user_dto.id)

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()
