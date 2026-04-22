"""UserProfileMenu — popup panel anchored below the topbar profile chip."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.avatar import apply_avatar_to_label
from seeker_accounting.shared.utils.text import coalesce_text, humanize_identifier


class UserProfileMenu(QFrame):
    """Frameless popup that shows the current user's profile and quick actions."""

    edit_profile_requested = Signal()
    change_password_requested = Signal()
    toggle_theme_requested = Signal()
    logout_requested = Signal()

    _MENU_WIDTH = 296

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._service_registry = service_registry
        self.setObjectName("UserProfileMenu")
        self.setFixedWidth(self._MENU_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Profile header ────────────────────────────────────────────
        header = QWidget(self)
        header.setObjectName("ProfileMenuHeader")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(18, 18, 18, 14)
        hl.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        self._avatar = QLabel(header)
        self._avatar.setObjectName("ProfileMenuAvatar")
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setFixedSize(48, 48)
        top_row.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignTop)

        name_block = QVBoxLayout()
        name_block.setSpacing(2)

        self._display_name = QLabel(header)
        self._display_name.setObjectName("ProfileMenuName")
        name_block.addWidget(self._display_name)

        self._username_label = QLabel(header)
        self._username_label.setObjectName("ProfileMenuMeta")
        name_block.addWidget(self._username_label)

        self._role_label = QLabel(header)
        self._role_label.setObjectName("ProfileMenuMeta")
        name_block.addWidget(self._role_label)

        self._email_label = QLabel(header)
        self._email_label.setObjectName("ProfileMenuMeta")
        name_block.addWidget(self._email_label)

        top_row.addLayout(name_block, 1)
        hl.addLayout(top_row)
        root.addWidget(header)

        root.addWidget(self._separator())

        # ── Actions ───────────────────────────────────────────────────
        actions = QWidget(self)
        actions.setObjectName("ProfileMenuActions")
        al = QVBoxLayout(actions)
        al.setContentsMargins(8, 6, 8, 6)
        al.setSpacing(2)

        edit_btn = self._action_button("Edit Profile", actions)
        edit_btn.clicked.connect(self._on_edit_profile)
        al.addWidget(edit_btn)

        pwd_btn = self._action_button("Change Password", actions)
        pwd_btn.clicked.connect(self._on_change_password)
        al.addWidget(pwd_btn)

        root.addWidget(actions)
        root.addWidget(self._separator())

        # ── License ───────────────────────────────────────────────────
        license_section = QWidget(self)
        license_section.setObjectName("ProfileMenuActions")
        ls = QVBoxLayout(license_section)
        ls.setContentsMargins(8, 6, 8, 6)
        ls.setSpacing(2)

        self._license_btn = self._action_button("License…", license_section)
        self._license_btn.clicked.connect(self._on_open_license)
        ls.addWidget(self._license_btn)

        root.addWidget(license_section)
        root.addWidget(self._separator())

        # ── Theme toggle ──────────────────────────────────────────────
        theme_row = QWidget(self)
        theme_row.setObjectName("ProfileMenuActions")
        tl = QHBoxLayout(theme_row)
        tl.setContentsMargins(8, 6, 8, 6)
        tl.setSpacing(0)

        self._theme_btn = self._action_button("Switch to Dark", theme_row)
        self._theme_btn.clicked.connect(self._on_toggle_theme)
        tl.addWidget(self._theme_btn)

        root.addWidget(theme_row)
        root.addWidget(self._separator())

        # ── Logout ────────────────────────────────────────────────────
        logout_section = QWidget(self)
        logout_section.setObjectName("ProfileMenuActions")
        ll = QVBoxLayout(logout_section)
        ll.setContentsMargins(8, 6, 8, 6)
        ll.setSpacing(2)

        logout_btn = self._action_button("Log Out", logout_section)
        logout_btn.setObjectName("ProfileMenuLogout")
        logout_btn.clicked.connect(self._on_logout)
        ll.addWidget(logout_btn)

        root.addWidget(logout_section)

    # ── Public ────────────────────────────────────────────────────────

    def refresh_and_show(self, anchor: QWidget) -> None:
        """Load current user data and show the menu below *anchor*."""
        self._load_user_info()
        self._sync_theme_label()

        global_pos = anchor.mapToGlobal(anchor.rect().bottomRight())
        self.move(global_pos.x() - self.width(), global_pos.y() + 4)
        self.show()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    # ── Data loading ──────────────────────────────────────────────────

    def _load_user_info(self) -> None:
        ctx = self._service_registry.app_context
        user_id = ctx.current_user_id

        display_name = coalesce_text(ctx.current_user_display_name, "Guest")
        username = ""
        email = ""
        role_text = "No role"
        avatar_path = None

        if isinstance(user_id, int) and user_id > 0:
            try:
                user_dto = self._service_registry.user_auth_service.get_user(user_id)
                display_name = user_dto.display_name
                username = user_dto.username
                email = user_dto.email or ""

                # Try loading avatar photo
                if user_dto.avatar_storage_path:
                    resolved = self._service_registry.user_avatar_service.resolve_avatar_path(
                        user_dto.avatar_storage_path
                    )
                    if resolved is not None:
                        avatar_path = str(resolved)
            except Exception:
                pass

            try:
                roles = self._service_registry.user_auth_service.get_user_roles(user_id)
                if roles:
                    r = roles[0]
                    role_text = (r.name.strip() if r.name else "") or (
                        humanize_identifier(r.code) if r.code else "No role"
                    )
            except Exception:
                pass

        apply_avatar_to_label(
            self._avatar,
            display_name=display_name,
            size=48,
            image_path=avatar_path,
        )
        self._display_name.setText(display_name)
        self._username_label.setText(f"@{username}" if username else "")
        self._username_label.setVisible(bool(username))
        self._role_label.setText(role_text)
        self._email_label.setText(email)
        self._email_label.setVisible(bool(email))

    def _sync_theme_label(self) -> None:
        current = self._service_registry.theme_manager.current_theme
        target = "Light" if current == "dark" else "Dark"
        self._theme_btn.setText(f"Switch to {target}")

    # ── Signal forwarders ─────────────────────────────────────────────

    def _on_edit_profile(self) -> None:
        self.close()
        self.edit_profile_requested.emit()

    def _on_change_password(self) -> None:
        self.close()
        self.change_password_requested.emit()

    def _on_toggle_theme(self) -> None:
        self.close()
        self.toggle_theme_requested.emit()

    def _on_open_license(self) -> None:
        self.close()
        from seeker_accounting.app.shell.license_dialog import LicenseDialog
        LicenseDialog.show_modal(self._service_registry.license_service, parent=self.parent())

    def _on_logout(self) -> None:
        self.close()
        self.logout_requested.emit()

    # ── Helpers ───────────────────────────────────────────────────────

    def _separator(self) -> QFrame:
        line = QFrame(self)
        line.setObjectName("ProfileMenuSeparator")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line

    @staticmethod
    def _action_button(text: str, parent: QWidget) -> QPushButton:
        btn = QPushButton(text, parent)
        btn.setObjectName("ProfileMenuAction")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        return btn

