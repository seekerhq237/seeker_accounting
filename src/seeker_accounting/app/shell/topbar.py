from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.license_chip import LicenseStatusChip
from seeker_accounting.app.shell.user_profile_menu import UserProfileMenu
from seeker_accounting.modules.administration.dto.user_commands import ChangePasswordCommand
from seeker_accounting.modules.administration.ui.password_change_dialog import PasswordChangeDialog
from seeker_accounting.modules.administration.ui.profile_edit_dialog import ProfileEditDialog
from seeker_accounting.shared.services.notification_center import NotificationCenter
from seeker_accounting.shared.ui.avatar import apply_avatar_to_label
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS
from seeker_accounting.shared.utils.text import coalesce_text, humanize_identifier


class ElidedLabel(QLabel):
    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        elide_mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
    ) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._elide_mode = elide_mode
        self.setText(text)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text or ""
        self._apply_elision()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_elision()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._apply_elision()

    def changeEvent(self, event) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.StyleChange,
        }:
            self._apply_elision()

    def _apply_elision(self) -> None:
        available_width = max(self.contentsRect().width(), 0)
        if available_width <= 0:
            display_text = self._full_text
        else:
            display_text = self.fontMetrics().elidedText(
                self._full_text,
                self._elide_mode,
                available_width,
            )

        QLabel.setText(self, display_text)
        self.setToolTip(self._full_text if display_text != self._full_text else "")


class ClickableFrame(QFrame):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() in {
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        }:
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ShellTopBar(QFrame):
    logout_requested = Signal()

    def __init__(
        self,
        service_registry: ServiceRegistry,
        toggle_sidebar: Callable[[], None] | None = None,
        show_command_palette: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._app_context = service_registry.app_context
        self._active_company_context = service_registry.active_company_context
        self._toggle_sidebar = toggle_sidebar
        self._show_command_palette = show_command_palette
        self._profile_menu: UserProfileMenu | None = None
        self._bell_panel: _NotificationPanel | None = None
        self._icon_provider = IconProvider(service_registry.theme_manager)
        self._notification_center = NotificationCenter(service_registry)
        service_registry.theme_manager.theme_changed.connect(self._refresh_icons)

        self.setObjectName("CommandBand")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        # ── Left: "+ New" only (sidebar has navigation; status rail has company)
        left_container = QFrame(self)
        left_container.setObjectName("CommandBandGroup")
        left_layout = QHBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(6)

        self._new_button = self._build_new_button()
        left_layout.addWidget(self._new_button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(left_container, 0)

        # ── Centre: real search field ─────────────────────────────────
        self._search_frame = self._build_inline_search()
        layout.addWidget(self._search_frame, 1, Qt.AlignmentFlag.AlignVCenter)

        # ── Right: theme toggle + bell + fiscal + license + profile ───
        right_container = QFrame(self)
        right_container.setObjectName("CommandBandGroup")
        right_container.setProperty("groupEdge", "end")
        right_layout = QHBoxLayout(right_container)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(6)

        self._theme_toggle_btn = self._build_theme_toggle_button()
        right_layout.addWidget(self._theme_toggle_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._bell_btn = self._build_bell_button()
        right_layout.addWidget(self._bell_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        right_layout.addWidget(self._build_divider(), 0, Qt.AlignmentFlag.AlignVCenter)

        self._fiscal_chip = self._build_fiscal_chip()
        right_layout.addWidget(self._fiscal_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        self._license_chip = LicenseStatusChip(right_container)
        right_layout.addWidget(self._license_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        self._profile_chip = self._build_profile_chip()
        right_layout.addWidget(self._profile_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(right_container, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Connections ───────────────────────────────────────────────
        self._profile_chip.clicked.connect(self._show_profile_menu)
        self._license_chip.activate_requested.connect(self._show_license_dialog)
        self._active_company_context.active_company_changed.connect(self._handle_active_company_changed)

        self.refresh_context()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.refresh_context()

    def refresh_context(self) -> None:
        self._update_company_display()
        self._update_fiscal_display(self._active_company_context.company_id)
        self._update_user_display()
        self._update_license_display()

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        # Sage-style: sidebar is permanent. No-op kept for API compatibility.
        return None

    def _build_sidebar_toggle_button(self) -> QPushButton:
        button = QPushButton(self)
        button.setObjectName("TopBarSidebarToggle")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIcon(self._icon_provider.icon("menu", size=18))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(
            DEFAULT_TOKENS.sizes.topbar_control_height,
            DEFAULT_TOKENS.sizes.topbar_control_height,
        )
        button.clicked.connect(self._handle_sidebar_toggle_requested)
        button.setEnabled(self._toggle_sidebar is not None)
        return button

    def _build_divider(self) -> QFrame:
        divider = QFrame(self)
        divider.setObjectName("TopBarDivider")
        divider.setFixedWidth(1)
        divider.setFixedHeight(18)
        return divider

    def _build_company_switcher(self) -> ClickableFrame:
        """Clickable company-name chip that opens a company switcher dropdown."""
        chip = ClickableFrame(self)
        chip.setObjectName("TopBarCompanySwitcher")
        chip.setFixedHeight(DEFAULT_TOKENS.sizes.topbar_control_height)
        chip.setMinimumWidth(90)
        chip.setMaximumWidth(DEFAULT_TOKENS.sizes.topbar_company_width)
        chip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        chip.setToolTip("Switch active company")

        layout = QHBoxLayout(chip)
        layout.setContentsMargins(8, 0, 6, 0)
        layout.setSpacing(4)

        self._company_name_label = ElidedLabel("No company", chip)
        self._company_name_label.setObjectName("TopBarCompanyName")
        self._company_name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._company_name_label.setProperty("companyState", "empty")
        layout.addWidget(self._company_name_label, 1, Qt.AlignmentFlag.AlignVCenter)

        self._company_chevron_label = QLabel(chip)
        self._company_chevron_label.setObjectName("TopBarProfileChevron")
        self._company_chevron_label.setFixedSize(12, 12)
        self._company_chevron_label.setPixmap(
            self._icon_provider.icon("chevron_down", size=12).pixmap(12, 12)
        )
        layout.addWidget(self._company_chevron_label, 0, Qt.AlignmentFlag.AlignVCenter)

        chip.clicked.connect(self._handle_company_switcher_requested)
        return chip

    def _build_new_button(self) -> QToolButton:
        """'+ New' split-button with categorised create actions."""
        btn = QToolButton(self)
        btn.setObjectName("TopBarNewButton")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setText("New")
        btn.setIcon(self._icon_provider.icon("plus", state="on_accent", size=15))
        btn.setIconSize(QSize(15, 15))
        btn.setFixedHeight(DEFAULT_TOKENS.sizes.topbar_control_height)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Create a new document or record (+ New)")

        menu = QMenu(btn)
        menu.setObjectName("TopBarNewMenu")

        def _nav(nav_id: str) -> None:
            from seeker_accounting.app.navigation import nav_ids as _nids  # noqa: F401
            self._service_registry.navigation_service.navigate(
                nav_id,
                context={"command_palette_action": "open_create_dialog"},
            )

        # ── Sales ──
        menu.addSection("Sales")
        menu.addAction("Sales Invoice", lambda: _nav("sales_invoices"))
        menu.addAction("Customer Receipt", lambda: _nav("customer_receipts"))
        menu.addAction("Customer", lambda: _nav("customers"))

        # ── Purchases ──
        menu.addSection("Purchases")
        menu.addAction("Purchase Bill", lambda: _nav("purchase_bills"))
        menu.addAction("Supplier Payment", lambda: _nav("supplier_payments"))
        menu.addAction("Supplier", lambda: _nav("suppliers"))

        # ── Accounting ──
        menu.addSection("Accounting")
        menu.addAction("Journal Entry", lambda: _nav("journals"))

        # ── Banking ──
        menu.addSection("Banking")
        menu.addAction("Cash/Bank Transaction", lambda: _nav("treasury_transactions"))
        menu.addAction("Transfer", lambda: _nav("treasury_transfers"))

        # ── Inventory ──
        menu.addSection("Inventory")
        menu.addAction("Item", lambda: _nav("items"))
        menu.addAction("Inventory Document", lambda: _nav("inventory_documents"))

        # ── Payroll ──
        menu.addSection("Payroll")
        menu.addAction("Payroll Run", lambda: _nav("payroll_calculation"))

        btn.setMenu(menu)
        return btn

    def _build_inline_search(self) -> QFrame:
        """Real search input that forwards typed text to the command palette."""
        frame = QFrame(self)
        frame.setObjectName("TopBarSearchTrigger")
        frame.setFixedHeight(DEFAULT_TOKENS.sizes.topbar_control_height)
        frame.setMinimumWidth(260)
        frame.setMaximumWidth(DEFAULT_TOKENS.sizes.topbar_search_width)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self._search_icon_label = QLabel(frame)
        self._search_icon_label.setObjectName("TopBarSearchIcon")
        self._search_icon_label.setFixedSize(16, 16)
        self._search_icon_label.setPixmap(
            self._icon_provider.icon("search", size=16).pixmap(16, 16)
        )
        layout.addWidget(self._search_icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._search_input = QLineEdit(frame)
        self._search_input.setObjectName("TopBarSearchInput")
        self._search_input.setPlaceholderText("Search pages, actions, reports…")
        self._search_input.setClearButtonEnabled(False)
        self._search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._search_input.setToolTip("Search pages, actions, reports, and entities (Ctrl+F)")
        layout.addWidget(self._search_input, 1)

        shortcut_hint = QLabel("Ctrl+F", frame)
        shortcut_hint.setObjectName("TopBarShortcutHint")
        shortcut_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(shortcut_hint, 0, Qt.AlignmentFlag.AlignVCenter)

        self._search_input.returnPressed.connect(self._show_search_palette)
        self._search_input.textChanged.connect(self._on_search_text_changed)

        if self._show_command_palette is None:
            frame.setEnabled(False)
        return frame

    def _build_theme_toggle_button(self) -> QPushButton:
        """Sun/moon icon button that toggles the app theme."""
        btn = QPushButton(self)
        btn.setObjectName("TopBarThemeToggle")
        btn.setFixedSize(DEFAULT_TOKENS.sizes.topbar_control_height, DEFAULT_TOKENS.sizes.topbar_control_height)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Toggle light/dark theme")
        btn.clicked.connect(self._handle_toggle_theme)
        self._update_theme_toggle_icon(btn)
        return btn

    def _build_bell_button(self) -> QPushButton:
        """Notification bell button."""
        btn = QPushButton(self)
        btn.setObjectName("TopBarBellButton")
        btn.setFixedSize(DEFAULT_TOKENS.sizes.topbar_control_height, DEFAULT_TOKENS.sizes.topbar_control_height)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Notifications")
        btn.setIcon(self._icon_provider.icon("bell", size=17))
        btn.setIconSize(QSize(17, 17))
        btn.clicked.connect(self._show_bell_panel)
        return btn

    def _build_fiscal_chip(self) -> ClickableFrame:
        chip = ClickableFrame(self)
        chip.setObjectName("TopBarChip")
        chip.setProperty("chipKind", "fiscal")
        chip.setProperty("fiscalTone", "neutral")
        chip.setFixedHeight(DEFAULT_TOKENS.sizes.topbar_control_height)
        chip.setMinimumWidth(152)
        chip.setMaximumWidth(DEFAULT_TOKENS.sizes.topbar_fiscal_width)
        chip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        chip.setToolTip("Current fiscal period — click to manage periods")

        layout = QHBoxLayout(chip)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self._fiscal_status_dot = QLabel(chip)
        self._fiscal_status_dot.setObjectName("TopBarStatusDot")
        self._fiscal_status_dot.setProperty("statusTone", "neutral")
        self._fiscal_status_dot.setFixedSize(8, 8)
        layout.addWidget(self._fiscal_status_dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._fiscal_value_label = ElidedLabel("No company", chip)
        self._fiscal_value_label.setObjectName("TopBarChipValue")
        layout.addWidget(self._fiscal_value_label, 1)

        chip.clicked.connect(self._handle_fiscal_click)
        return chip

    def _build_profile_chip(self) -> ClickableFrame:
        chip = ClickableFrame(self)
        chip.setObjectName("TopBarProfileChip")
        chip.setFixedHeight(DEFAULT_TOKENS.sizes.topbar_control_height)
        chip.setMinimumWidth(86)
        chip.setMaximumWidth(DEFAULT_TOKENS.sizes.topbar_user_width)
        chip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(chip)
        layout.setContentsMargins(4, 2, 8, 2)
        layout.setSpacing(8)

        self._avatar_label = QLabel("?", chip)
        self._avatar_label.setObjectName("TopBarAvatar")
        self._avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar_label.setFixedSize(30, 30)
        layout.addWidget(self._avatar_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._user_name_label = ElidedLabel("", chip)
        self._user_name_label.setObjectName("TopBarProfileName")
        layout.addWidget(self._user_name_label, 1, Qt.AlignmentFlag.AlignVCenter)

        self._profile_chevron_label = QLabel(chip)
        self._profile_chevron_label.setObjectName("TopBarProfileChevron")
        self._profile_chevron_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._profile_chevron_label.setFixedSize(14, 14)
        self._profile_chevron_label.setPixmap(
            self._icon_provider.icon("chevron_down", size=14).pixmap(14, 14)
        )
        layout.addWidget(self._profile_chevron_label, 0, Qt.AlignmentFlag.AlignVCenter)
        return chip

    # ── Profile menu ──────────────────────────────────────────────────

    def _show_profile_menu(self) -> None:
        if self._profile_menu is None:
            self._profile_menu = UserProfileMenu(self._service_registry)
            self._profile_menu.edit_profile_requested.connect(self._handle_edit_profile)
            self._profile_menu.change_password_requested.connect(self._handle_change_password)
            self._profile_menu.toggle_theme_requested.connect(self._handle_toggle_theme)
            self._profile_menu.logout_requested.connect(self.logout_requested.emit)
        self._profile_menu.refresh_and_show(self._profile_chip)

    def _handle_edit_profile(self) -> None:
        saved = ProfileEditDialog.prompt(self._service_registry, parent=self.window())
        if saved:
            self._update_user_display()

    def _handle_change_password(self) -> None:
        ctx = self._app_context
        user_id = ctx.current_user_id
        if not isinstance(user_id, int) or user_id <= 0:
            return
        password_result = PasswordChangeDialog.prompt(
            username=ctx.current_user_display_name,
            allow_skip=True,
            require_current_password=True,
            parent=self.window(),
        )
        if password_result is None:
            return
        try:
            self._service_registry.user_auth_service.change_password(
                ChangePasswordCommand(
                    user_id=user_id,
                    new_password=password_result.new_password,
                    current_password=password_result.current_password,
                )
            )
            show_info(self.window(), "Password Changed", "Your password has been updated.")
        except Exception as exc:
            show_error(self.window(), "Password Change", f"Could not change password.\n\n{exc}")

    def _handle_toggle_theme(self) -> None:
        self._service_registry.theme_manager.toggle_theme()

    # ── Icons ─────────────────────────────────────────────────────────

    def _refresh_icons(self, _theme_name: str = "") -> None:
        """Re-apply Lucide icons after a theme change so colors re-tint."""
        if hasattr(self, "_search_icon_label"):
            self._search_icon_label.setPixmap(
                self._icon_provider.icon("search", size=16).pixmap(16, 16)
            )
        if hasattr(self, "_profile_chevron_label"):
            self._profile_chevron_label.setPixmap(
                self._icon_provider.icon("chevron_down", size=14).pixmap(14, 14)
            )
        if hasattr(self, "_company_chevron_label"):
            self._company_chevron_label.setPixmap(
                self._icon_provider.icon("chevron_down", size=12).pixmap(12, 12)
            )
        if hasattr(self, "_new_button"):
            self._new_button.setIcon(self._icon_provider.icon("plus", state="on_accent", size=15))
        if hasattr(self, "_bell_btn"):
            self._bell_btn.setIcon(self._icon_provider.icon("bell", size=17))
        if hasattr(self, "_theme_toggle_btn"):
            self._update_theme_toggle_icon(self._theme_toggle_btn)

    def _update_theme_toggle_icon(self, btn: QPushButton) -> None:
        current = self._service_registry.theme_manager.current_theme
        icon_name = "moon" if current == "light" else "sun"
        btn.setIcon(self._icon_provider.icon(icon_name, size=17))
        btn.setIconSize(QSize(17, 17))

    # ── Search ────────────────────────────────────────────────────────

    def _on_search_text_changed(self, text: str) -> None:
        # Forwarding text on every keystroke would spam the palette; wait for
        # Return or enough characters.
        pass  # User presses Enter or uses Ctrl+F for full palette

    def _show_search_palette(self) -> None:
        """Open command palette pre-populated with whatever is in the search bar."""
        if self._show_command_palette is None:
            return
        text = self._search_input.text().strip() if hasattr(self, "_search_input") else ""
        # Forward the typed text into the palette then clear the topbar field.
        # We rely on CommandPalette.show_palette(initial_query=...) added in Phase 2.
        from seeker_accounting.app.shell.command_palette import CommandPalette
        palette_widget = None
        # Walk up to find the CommandPalette in the shell root
        parent = self.window()
        if parent is not None:
            for child in parent.findChildren(CommandPalette):
                palette_widget = child
                break
        if palette_widget is not None:
            palette_widget.show_palette(initial_query=text)
        else:
            self._show_command_palette()
        if hasattr(self, "_search_input"):
            QTimer.singleShot(50, self._search_input.clear)

    def _handle_search_requested(self) -> None:
        self._show_search_palette()

    def _handle_sidebar_toggle_requested(self) -> None:
        if self._toggle_sidebar is not None:
            self._toggle_sidebar()

    # ── Company switcher ──────────────────────────────────────────────

    def _handle_company_switcher_requested(self) -> None:
        """Show company list in a dropdown menu."""
        try:
            companies = self._service_registry.company_service.list_companies()
        except Exception:
            companies = []

        if not companies:
            return  # No companies accessible — nothing to show

        menu = QMenu(self)
        menu.setObjectName("TopBarNewMenu")

        current_id = self._active_company_context.company_id
        for company in companies:
            action = menu.addAction(company.display_name)
            if isinstance(current_id, int) and company.id == current_id:
                action.setEnabled(False)  # already active
            else:
                action.triggered.connect(
                    lambda checked=False, cid=company.id: self._switch_company(cid)
                )

        global_pos = self._company_switcher.mapToGlobal(
            self._company_switcher.rect().bottomLeft()
        )
        menu.exec(global_pos)

    def _switch_company(self, company_id: int) -> None:
        try:
            self._service_registry.company_context_service.set_active_company(company_id)
        except Exception as exc:
            show_error(self.window(), "Company Switch", f"Could not switch company.\n\n{exc}")

    # ── Fiscal chip ───────────────────────────────────────────────────

    def _handle_fiscal_click(self) -> None:
        """Navigate to the Fiscal Periods page."""
        from seeker_accounting.app.navigation import nav_ids
        try:
            self._service_registry.navigation_service.navigate(nav_ids.FISCAL_PERIODS)
        except Exception:
            pass

    # ── Theme toggle ──────────────────────────────────────────────────

    def _handle_toggle_theme(self) -> None:
        self._service_registry.theme_manager.toggle_theme()
        self._update_theme_toggle_icon(self._theme_toggle_btn)

    # ── Notifications bell ────────────────────────────────────────────

    def _show_bell_panel(self) -> None:
        if self._bell_panel is None:
            self._bell_panel = _NotificationPanel(self._service_registry, self._notification_center)
        self._bell_panel.refresh_and_show(self._bell_btn)

    # ── License ───────────────────────────────────────────────────────

    def _update_license_display(self) -> None:
        try:
            info = self._service_registry.license_service.get_license_info()
            self._license_chip.refresh(info)
        except Exception:
            pass  # Do not crash the topbar on license check failure

    def _show_license_dialog(self) -> None:
        from seeker_accounting.app.shell.license_dialog import LicenseDialog
        LicenseDialog.show_modal(self._service_registry.license_service, parent=self.window())
        self._update_license_display()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002        self._update_company_display()
        self._update_fiscal_display(company_id)
        self._update_user_display()

    def _update_company_display(self) -> None:
        # Company identity is presented in the status rail (Sage-style).
        # The topbar no longer hosts a company switcher chip.
        return None

    def _update_fiscal_display(self, company_id: object) -> None:
        if not isinstance(company_id, int) or company_id <= 0:
            self._set_fiscal_state(
                period_text="No company",
                tone="neutral",
                tooltip="Select an active company to load fiscal context.",
            )
            return

        try:
            current_period = self._service_registry.fiscal_calendar_service.get_current_period(company_id)
        except Exception:
            self._set_fiscal_state(
                period_text="Unavailable",
                tone="danger",
                tooltip="Fiscal calendar data is unavailable right now.",
            )
            return

        if current_period is None:
            self._set_fiscal_state(
                period_text="No open period",
                tone="warning",
                tooltip="No open fiscal period was found for the active company.",
            )
            return

        period_text = current_period.period_code
        status_text = current_period.status_code.title()
        tone = self._fiscal_tone_for_status(current_period.status_code)
        self._set_fiscal_state(
            period_text=period_text,
            tone=tone,
            tooltip=f"Current fiscal period: {current_period.period_code}\nStatus: {status_text}",
        )

    def _update_user_display(self) -> None:
        display_name = coalesce_text(self._app_context.current_user_display_name, "Guest user")
        chip_name = self._chip_name_for_display_name(display_name)
        role_text = self._resolve_role_text()
        avatar_size = 30
        avatar_path = None

        user_id = self._app_context.current_user_id
        if isinstance(user_id, int) and user_id > 0:
            try:
                user_dto = self._service_registry.user_auth_service.get_user(user_id)
                if user_dto.avatar_storage_path:
                    resolved = self._service_registry.user_avatar_service.resolve_avatar_path(
                        user_dto.avatar_storage_path
                    )
                    if resolved is not None:
                        avatar_path = str(resolved)
            except Exception:
                pass  # Gracefully fall back to initials

        apply_avatar_to_label(
            self._avatar_label,
            display_name=display_name,
            size=avatar_size,
            image_path=avatar_path,
        )
        self._user_name_label.setText(chip_name)
        self._profile_chip.setToolTip(f"{display_name}\n{role_text}")

    def _resolve_role_text(self) -> str:
        user_id = self._app_context.current_user_id
        if not isinstance(user_id, int) or user_id <= 0:
            return "No role"

        try:
            roles = self._service_registry.user_auth_service.get_user_roles(user_id)
        except Exception:
            return "No role"

        if not roles:
            return "No role"

        primary_role = roles[0]
        role_name = primary_role.name.strip() if primary_role.name else ""
        if role_name:
            return role_name
        if primary_role.code:
            return humanize_identifier(primary_role.code)
        return "No role"

    def _set_fiscal_state(
        self,
        *,
        period_text: str,
        tone: str,
        tooltip: str,
    ) -> None:
        self._fiscal_value_label.setText(period_text)
        self._fiscal_status_dot.setProperty("statusTone", tone)
        self._fiscal_status_dot.style().unpolish(self._fiscal_status_dot)
        self._fiscal_status_dot.style().polish(self._fiscal_status_dot)

        self._fiscal_chip.setProperty("fiscalTone", tone)
        self._fiscal_chip.style().unpolish(self._fiscal_chip)
        self._fiscal_chip.style().polish(self._fiscal_chip)
        self._fiscal_chip.setToolTip(tooltip)

    @staticmethod
    def _fiscal_tone_for_status(status_code: str) -> str:
        normalized = status_code.strip().upper()
        if normalized == "OPEN":
            return "success"
        if normalized == "CLOSED":
            return "warning"
        if normalized == "LOCKED":
            return "danger"
        if normalized == "DRAFT":
            return "neutral"
        return "info"

    @staticmethod
    def _chip_name_for_display_name(display_name: str) -> str:
        words = [segment for segment in display_name.strip().split() if segment]
        if not words:
            return "User"
        return words[0]


# ── Notification panel ────────────────────────────────────────────────────────

class _NotificationPanel(QFrame):
    """Popup panel that lists current AppNotifications anchored below a widget."""

    _PANEL_WIDTH = 320

    def __init__(
        self,
        service_registry: ServiceRegistry,
        notification_center: NotificationCenter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._sr = service_registry
        self._nc = notification_center
        self.setObjectName("NotificationPanel")
        self.setFixedWidth(self._PANEL_WIDTH)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header row
        header = QWidget(self)
        header.setObjectName("NotificationPanelHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 10, 14, 10)

        title = QLabel("Notifications", header)
        title.setObjectName("NotificationPanelTitle")
        hl.addWidget(title, 1)
        root.addWidget(header)

        sep = QFrame(self)
        sep.setObjectName("NotificationPanelSeparator")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Notification body (re-populated on each show)
        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        root.addWidget(self._body)

    def refresh_and_show(self, anchor: QWidget) -> None:
        self._populate()
        global_pos = anchor.mapToGlobal(anchor.rect().bottomRight())
        self.move(global_pos.x() - self.width(), global_pos.y() + 4)
        self.show()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _populate(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        notifications = self._nc.get_notifications()

        if not notifications:
            empty = QLabel("No notifications", self._body)
            empty.setObjectName("NotificationEmptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._body_layout.addWidget(empty)
        else:
            for notif in notifications:
                row = self._build_row(notif)
                self._body_layout.addWidget(row)

        self.adjustSize()

    def _build_row(self, notif: "AppNotification") -> QWidget:
        from seeker_accounting.shared.services.notification_center import AppNotification  # noqa
        row = QFrame(self._body)
        row.setObjectName("NotificationRow")
        row.setProperty("notifTone", notif.tone)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        dot = QLabel(row)
        dot.setObjectName("NotificationDot")
        dot.setProperty("notifTone", notif.tone)
        dot.setFixedSize(8, 8)
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

        text_block = QVBoxLayout()
        text_block.setSpacing(2)

        title_lbl = QLabel(notif.title, row)
        title_lbl.setObjectName("NotificationTitle")
        title_lbl.setWordWrap(True)
        text_block.addWidget(title_lbl)

        body_lbl = QLabel(notif.body, row)
        body_lbl.setObjectName("NotificationBody")
        body_lbl.setWordWrap(True)
        text_block.addWidget(body_lbl)

        layout.addLayout(text_block, 1)

        if notif.nav_id:
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            nav_id = notif.nav_id

            def _on_click(checked: bool = False, nid: str = nav_id) -> None:
                self.hide()
                try:
                    self._sr.navigation_service.navigate(nid)
                except Exception:
                    pass

            row.mousePressEvent = lambda event, fn=_on_click: fn()  # type: ignore[method-assign]

        return row
