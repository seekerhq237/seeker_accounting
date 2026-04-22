from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Signal,
    Qt,
)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.context.active_company_context import ActiveCompanyContext
from seeker_accounting.app.navigation.navigation_service import NavigationService
from seeker_accounting.app.security.permission_map import can_access_navigation
from seeker_accounting.app.shell.sidebar_icon_provider import SidebarIconProvider
from seeker_accounting.app.shell.shell_models import (
    NAV_ID_TO_MODULE_KEY,
    NAVIGATION_BY_ID,
    SIDEBAR_MODULES,
    SidebarModule,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.services.company_logo_service import CompanyLogoService
from seeker_accounting.shared.services.sidebar_preferences_service import SidebarPreferencesService
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS
from seeker_accounting.shared.utils.text import coalesce_text

# ── Centralized module icon map ──────────────────────────────────────────
# Centralized top-level module icons are rendered by SidebarIconProvider.

_sizes = DEFAULT_TOKENS.sizes


class ShellSidebar(QFrame):
    """Accordion sidebar with collapsible icon-rail mode."""

    collapsed_changed = Signal(bool)

    def __init__(
        self,
        navigation_service: NavigationService,
        active_company_context: ActiveCompanyContext,
        permission_service: PermissionService,
        company_logo_service: CompanyLogoService,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._navigation_service = navigation_service
        self._active_company_context = active_company_context
        self._permission_service = permission_service
        self._company_logo_service = company_logo_service
        self._theme_manager = theme_manager
        self._sidebar_icon_provider = SidebarIconProvider(theme_manager)
        self._prefs = SidebarPreferencesService()
        self._show_navigation_filter = False
        self._show_auxiliary_sections = False

        # ── State ──
        self._open_module_key: str | None = None
        self._collapsed: bool = False
        self._hovered_module_key: str | None = None
        self._module_buttons: dict[str, QPushButton] = {}
        self._child_buttons: dict[str, QPushButton] = {}
        self._child_containers: dict[str, QWidget] = {}
        self._visible_modules: dict[str, SidebarModule] = {}
        self._child_animations: dict[str, QPropertyAnimation] = {}
        self._sidebar_min_width_anim: QPropertyAnimation | None = None
        self._sidebar_max_width_anim: QPropertyAnimation | None = None
        self._recents_buttons: dict[str, QPushButton] = {}
        self._favorites_buttons: dict[str, QPushButton] = {}
        self._recents_section: QWidget | None = None
        self._favorites_section: QWidget | None = None
        self._nav_badges: dict[str, int] = {}

        self.setObjectName("Sidebar")
        self.setProperty("sidebarCollapsed", False)
        self.setFixedWidth(_sizes.sidebar_width)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        if self._show_navigation_filter:
            self._search_bar_widget = self._build_search_bar()
            root.addWidget(self._search_bar_widget)
        else:
            self._search_bar_widget = None

        scroll = QScrollArea(self)
        scroll.setObjectName("SidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_content = QWidget(scroll)
        scroll_content.setObjectName("SidebarScrollContent")
        self._nav_layout = QVBoxLayout(scroll_content)
        self._nav_layout.setContentsMargins(8, 8, 8, 8)
        self._nav_layout.setSpacing(2)

        self._build_modules()
        self._nav_layout.addStretch(1)

        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        # ── Connections ──
        self._navigation_service.navigation_changed.connect(self._on_navigation_changed)
        if self._show_auxiliary_sections:
            self._navigation_service.navigation_changed.connect(self._on_nav_for_recents)
        self._active_company_context.active_company_changed.connect(self._update_company_display)
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

        # Sync initial state
        self._on_navigation_changed(self._navigation_service.current_nav_id)
        self._update_company_display(
            self._active_company_context.company_id,
            self._active_company_context.company_name,
        )

    def refresh_navigation_modules(self) -> None:
        """Rebuild module visibility from the current permission snapshot."""
        for animation in self._child_animations.values():
            animation.stop()
            animation.deleteLater()
        self._child_animations.clear()

        self._open_module_key = None
        self._hovered_module_key = None

        self._module_buttons.clear()
        self._child_buttons.clear()
        self._child_containers.clear()
        self._visible_modules.clear()
        self._recents_buttons.clear()
        self._favorites_buttons.clear()
        self._recents_section = None
        self._favorites_section = None

        while self._nav_layout.count():
            item = self._nav_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._build_modules()
        self._nav_layout.addStretch(1)

        for btn in self._module_buttons.values():
            btn.setProperty("sidebarCollapsed", self._collapsed)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setText("" if self._collapsed else self._module_label_for_btn(btn))

        self._on_navigation_changed(self._navigation_service.current_nav_id)

    # ── Search bar ────────────────────────────────────────────────────────

    def _build_search_bar(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("SidebarSearchBar")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(0)

        self._search_input = QLineEdit(container)
        self._search_input.setObjectName("SidebarSearchInput")
        self._search_input.setPlaceholderText("Filter navigation…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._filter_modules)
        layout.addWidget(self._search_input)
        return container

    def _filter_modules(self, text: str) -> None:
        """Show/hide module rows and child rows based on filter text."""
        query = text.strip().lower()

        # Update recents/favorites visibility
        if self._recents_section is not None:
            self._recents_section.setVisible(not query and not self._collapsed)
        if self._favorites_section is not None:
            self._favorites_section.setVisible(not query and not self._collapsed)

        if not query:
            # Restore all to normal visibility
            for key, btn in self._module_buttons.items():
                btn.setVisible(True)
                container = self._child_containers.get(key)
                if container is not None:
                    # Keep container open/close state as-is
                    pass
            return

        # Filter: show modules that have at least one matching child
        for key, module in self._visible_modules.items():
            module_btn = self._module_buttons.get(key)
            container = self._child_containers.get(key)
            matching_children = []

            if container:
                for child in module.children:
                    child_btn = self._child_buttons.get(child.nav_id)
                    match = (
                        query in child.label.lower()
                        or query in key.lower()
                        or query in module.label.lower()
                    )
                    if child_btn:
                        child_btn.setVisible(match)
                    if match:
                        matching_children.append(child.nav_id)

            has_match = bool(matching_children)
            if module_btn:
                module_btn.setVisible(has_match)
            if container:
                if has_match:
                    container.setVisible(True)
                    container.setMaximumHeight(container.sizeHint().height())
                else:
                    container.setVisible(False)

    # ── Recents & Favorites ───────────────────────────────────────────────

    def _on_nav_for_recents(self, nav_id: str) -> None:
        """Track navigation history and rebuild recents section if changed."""
        if nav_id not in NAVIGATION_BY_ID:
            return
        old_recents = self._prefs.get_recents()
        self._prefs.push_recent(nav_id)
        new_recents = self._prefs.get_recents()
        if new_recents != old_recents:
            self._rebuild_recents_section()

    def _build_favorites_section(self) -> QWidget | None:
        """Build the Favorites pinned section. Returns None if empty."""
        favorites = self._prefs.get_favorites()
        # Only show favorites that exist in NAVIGATION_BY_ID
        valid_favorites = [nid for nid in favorites if nid in NAVIGATION_BY_ID]
        if not valid_favorites:
            return None

        section = QWidget(self)
        section.setObjectName("SidebarSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)

        label = QLabel("Favorites", section)
        label.setObjectName("SidebarSectionLabel")
        layout.addWidget(label)

        for nav_id in valid_favorites:
            nav_item = NAVIGATION_BY_ID[nav_id]
            btn = QPushButton(nav_item.label, section)
            btn.setObjectName("SidebarFavoriteButton")
            btn.setProperty("childNav", True)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"⭐ {nav_item.label}")
            btn.clicked.connect(
                lambda checked=False, nid=nav_id: self._navigation_service.navigate(nid)
            )
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, nid=nav_id, b=btn: self._on_favorite_context_menu(nid, b, pos)
            )
            self._favorites_buttons[nav_id] = btn
            layout.addWidget(btn)

        sep = QFrame(section)
        sep.setObjectName("SidebarSectionSeparator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)
        return section

    def _build_recents_section(self) -> QWidget | None:
        """Build the Recents auto-populated section. Returns None if empty."""
        recents = self._prefs.get_recents()
        valid_recents = [nid for nid in recents if nid in NAVIGATION_BY_ID]
        if not valid_recents:
            return None

        section = QWidget(self)
        section.setObjectName("SidebarSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)

        label = QLabel("Recent", section)
        label.setObjectName("SidebarSectionLabel")
        layout.addWidget(label)

        for nav_id in valid_recents:
            nav_item = NAVIGATION_BY_ID[nav_id]
            btn = QPushButton(nav_item.label, section)
            btn.setObjectName("SidebarRecentButton")
            btn.setProperty("childNav", True)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(nav_item.label)
            btn.clicked.connect(
                lambda checked=False, nid=nav_id: self._navigation_service.navigate(nid)
            )
            self._recents_buttons[nav_id] = btn
            layout.addWidget(btn)

        sep = QFrame(section)
        sep.setObjectName("SidebarSectionSeparator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)
        return section

    def _rebuild_recents_section(self) -> None:
        """Remove old recents section from layout and insert a fresh one."""
        if self._recents_section is not None:
            idx = self._nav_layout.indexOf(self._recents_section)
            if idx >= 0:
                self._nav_layout.takeAt(idx)
            self._recents_section.deleteLater()
            self._recents_section = None
            self._recents_buttons.clear()

        new_section = self._build_recents_section()
        if new_section is not None:
            # Insert at start of nav_layout (after favorites if present)
            insert_idx = 0
            if self._favorites_section is not None:
                fav_idx = self._nav_layout.indexOf(self._favorites_section)
                if fav_idx >= 0:
                    insert_idx = fav_idx + 1
            self._nav_layout.insertWidget(insert_idx, new_section)
            self._recents_section = new_section
            new_section.setVisible(not self._collapsed)

    def _on_favorite_context_menu(self, nav_id: str, btn: QPushButton, pos) -> None:
        menu = QMenu(btn)
        remove_action = menu.addAction("Remove from Favorites")
        action = menu.exec(btn.mapToGlobal(pos))
        if action == remove_action:
            self._prefs.remove_favorite(nav_id)
            self._rebuild_favorites_section()

    def _rebuild_favorites_section(self) -> None:
        """Remove old favorites section and insert a fresh one."""
        if self._favorites_section is not None:
            idx = self._nav_layout.indexOf(self._favorites_section)
            if idx >= 0:
                self._nav_layout.takeAt(idx)
            self._favorites_section.deleteLater()
            self._favorites_section = None
            self._favorites_buttons.clear()

        new_section = self._build_favorites_section()
        if new_section is not None:
            self._nav_layout.insertWidget(0, new_section)
            self._favorites_section = new_section
            new_section.setVisible(not self._collapsed)

    # ── Header ────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        # Sage-style: no logo/company card in sidebar. Company is shown in the
        # status rail. Return a zero-height placeholder to preserve API.
        header = QFrame(self)
        header.setObjectName("SidebarHeader")
        header.setFixedHeight(0)

        # Keep legacy attributes alive for any external readers; never shown.
        self._context_panel = header
        self._company_logo_label = QLabel(header)
        self._company_logo_label.setObjectName("SidebarCompanyLogo")
        self._company_logo_label.hide()
        self._company_name_label = QLabel(header)
        self._company_name_label.setObjectName("SidebarCompanyName")
        self._company_name_label.hide()

        return header

    # ── Module rows ───────────────────────────────────────────────────────

    def _build_modules(self) -> None:
        if self._show_auxiliary_sections:
            fav_section = self._build_favorites_section()
            if fav_section is not None:
                self._nav_layout.addWidget(fav_section)
                self._favorites_section = fav_section

            rec_section = self._build_recents_section()
            if rec_section is not None:
                self._nav_layout.addWidget(rec_section)
                self._recents_section = rec_section

        for module in SIDEBAR_MODULES:
            visible_children = tuple(
                child
                for child in module.children
                if can_access_navigation(self._permission_service, child.nav_id)
            )
            if not visible_children:
                continue
            visible_module = SidebarModule(
                key=module.key,
                label=module.label,
                children=visible_children,
            )
            self._visible_modules[visible_module.key] = visible_module

            # Parent button
            parent_btn = QPushButton(self)
            parent_btn.setProperty("moduleParent", True)
            parent_btn.setProperty("moduleOpen", False)
            parent_btn.setProperty("moduleActive", False)
            parent_btn.setProperty("moduleKey", visible_module.key)
            parent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            parent_btn.setToolTip(visible_module.label)
            parent_btn.setIconSize(QSize(_sizes.sidebar_icon_size, _sizes.sidebar_icon_size))
            parent_btn.setText(visible_module.label)
            parent_btn.installEventFilter(self)

            parent_btn.clicked.connect(
                lambda checked=False, mk=visible_module.key: self._on_module_click(mk)
            )
            self._module_buttons[visible_module.key] = parent_btn
            self._apply_module_icon(visible_module.key)
            self._nav_layout.addWidget(parent_btn)

            # Child container
            child_container = QWidget(self)
            child_container.setProperty("childContainer", True)
            child_container.setObjectName(f"ChildContainer_{visible_module.key}")
            child_layout = QVBoxLayout(child_container)
            child_layout.setContentsMargins(0, 0, 0, 0)
            child_layout.setSpacing(0)

            for child in visible_module.children:
                child_row = QWidget(child_container)
                child_row_layout = QHBoxLayout(child_row)
                child_row_layout.setContentsMargins(0, 0, 0, 0)
                child_row_layout.setSpacing(0)

                child_btn = QPushButton(child.label, child_row)
                child_btn.setProperty("childNav", True)
                child_btn.setCheckable(True)
                child_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                child_btn.setToolTip(child.label)
                child_btn.clicked.connect(
                    lambda checked=False, nid=child.nav_id: self._navigation_service.navigate(nid)
                )
                # Right-click → add/remove favorite
                child_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                child_btn.customContextMenuRequested.connect(
                    lambda pos, nid=child.nav_id, b=child_btn: self._on_child_context_menu(nid, b, pos)
                )
                self._child_buttons[child.nav_id] = child_btn
                child_row_layout.addWidget(child_btn, 1)

                # Badge label (hidden by default until a count is provided)
                badge_lbl = QLabel(child_row)
                badge_lbl.setObjectName("SidebarNavBadge")
                badge_lbl.setVisible(False)
                badge_lbl.setProperty("badgeNav", child.nav_id)
                child_row_layout.addWidget(badge_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

                child_layout.addWidget(child_row)

            child_container.setVisible(False)
            child_container.setMaximumHeight(0)
            self._child_containers[visible_module.key] = child_container
            self._nav_layout.addWidget(child_container)

    # ── Accordion logic ───────────────────────────────────────────────────

    def eventFilter(self, watched: object, event: object) -> bool:
        if isinstance(watched, QPushButton) and isinstance(event, QEvent):
            module_key = watched.property("moduleKey")
            if isinstance(module_key, str) and module_key in self._module_buttons:
                if event.type() == QEvent.Type.Enter:
                    previous_key = self._hovered_module_key
                    self._hovered_module_key = module_key
                    if previous_key and previous_key != module_key:
                        self._apply_module_icon(previous_key)
                    self._apply_module_icon(module_key)
                elif event.type() == QEvent.Type.Leave:
                    if self._hovered_module_key == module_key:
                        self._hovered_module_key = None
                    self._apply_module_icon(module_key)
                elif event.type() == QEvent.Type.EnabledChange:
                    self._apply_module_icon(module_key)
        return super().eventFilter(watched, event)

    def _on_module_click(self, module_key: str) -> None:
        module = self._visible_modules.get(module_key)
        if module is None:
            return

        # Single-child module: navigate directly
        if len(module.children) == 1:
            if self._collapsed:
                self._set_collapsed(False)
            self._navigation_service.navigate(module.children[0].nav_id)
            return

        # In collapsed mode: expand sidebar, then open this module
        if self._collapsed:
            self._set_collapsed(False)
            self._open_module(module_key)
            return

        # Toggle: if already open, close it; otherwise open it
        if self._open_module_key == module_key:
            self._close_all_modules()
        else:
            self._open_module(module_key)

    def _open_module(self, module_key: str) -> None:
        # Close previous
        if self._open_module_key and self._open_module_key != module_key:
            self._animate_child_container(self._open_module_key, opening=False)
            self._set_module_open_property(self._open_module_key, False)

        self._open_module_key = module_key
        self._set_module_open_property(module_key, True)
        self._animate_child_container(module_key, opening=True)

    def _close_all_modules(self) -> None:
        if self._open_module_key:
            self._animate_child_container(self._open_module_key, opening=False)
            self._set_module_open_property(self._open_module_key, False)
        self._open_module_key = None

    def _set_module_open_property(self, module_key: str, is_open: bool) -> None:
        btn = self._module_buttons.get(module_key)
        if btn:
            btn.setProperty("moduleOpen", is_open)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            self._apply_module_icon(module_key)

    def _set_module_active_property(self, module_key: str, is_active: bool) -> None:
        btn = self._module_buttons.get(module_key)
        if btn:
            btn.setProperty("moduleActive", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            self._apply_module_icon(module_key)

    # ── Child container animation ─────────────────────────────────────────

    def _animate_child_container(self, module_key: str, *, opening: bool) -> None:
        container = self._child_containers.get(module_key)
        if container is None:
            return

        current_animation = self._child_animations.get(module_key)
        if current_animation is not None:
            current_animation.stop()
            self._child_animations.pop(module_key, None)
            current_animation.deleteLater()

        if opening:
            container.setVisible(True)
            container.adjustSize()
            target_height = container.sizeHint().height()
        else:
            target_height = 0

        anim = QPropertyAnimation(container, b"maximumHeight", self)
        anim.setDuration(_sizes.sidebar_animation_ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(container.maximumHeight())
        anim.setEndValue(target_height)

        if not opening:
            anim.finished.connect(
                lambda mk=module_key, c=container: c.setVisible(self._open_module_key == mk)
            )

        anim.finished.connect(lambda mk=module_key: self._child_animations.pop(mk, None))
        anim.finished.connect(anim.deleteLater)
        self._child_animations[module_key] = anim

        anim.start()

    # ── Navigation sync ───────────────────────────────────────────────────

    def _on_navigation_changed(self, nav_id: str) -> None:
        # Clear all active states
        for key in self._module_buttons:
            self._set_module_active_property(key, False)
        for btn in self._child_buttons.values():
            btn.setChecked(False)

        # Find module for this nav_id
        module_key = NAV_ID_TO_MODULE_KEY.get(nav_id)
        if module_key is None:
            return

        # Mark module active
        self._set_module_active_property(module_key, True)

        # Mark child active
        child_btn = self._child_buttons.get(nav_id)
        if child_btn:
            child_btn.setChecked(True)

        # Auto-open parent module (if not collapsed)
        if not self._collapsed and self._open_module_key != module_key:
            module = self._visible_modules.get(module_key)
            if module and len(module.children) > 1:
                self._open_module(module_key)

    # ── Collapse mode ─────────────────────────────────────────────────────

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self._toggle_collapsed()

    def set_collapsed(self, collapsed: bool) -> None:
        self._set_collapsed(collapsed)

    def _toggle_collapsed(self) -> None:
        self._set_collapsed(not self._collapsed)

    def _set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed

        target_width = _sizes.sidebar_collapsed_width if collapsed else _sizes.sidebar_width

        self.setProperty("sidebarCollapsed", collapsed)
        self.style().unpolish(self)
        self.style().polish(self)

        self._animate_sidebar_width(target_width)

        if collapsed:
            # Close any open module instantly
            if self._open_module_key:
                container = self._child_containers.get(self._open_module_key)
                if container:
                    container.setMaximumHeight(0)
                    container.setVisible(False)
                self._set_module_open_property(self._open_module_key, False)
                self._open_module_key = None
        else:
            current_nav = self._navigation_service.current_nav_id
            current_module_key = NAV_ID_TO_MODULE_KEY.get(current_nav)
            current_module = self._visible_modules.get(current_module_key) if current_module_key else None
            if current_module and len(current_module.children) > 1:
                self._open_module(current_module.key)

        # Toggle visibility of header elements
        self._context_panel.setVisible(not collapsed)
        self._company_name_label.setVisible(not collapsed)

        # Toggle search bar, recents, favorites visibility
        self._search_bar_widget.setVisible(not collapsed)
        if self._recents_section is not None:
            self._recents_section.setVisible(not collapsed)
        if self._favorites_section is not None:
            self._favorites_section.setVisible(not collapsed)

        # Toggle button text visibility
        for btn in self._module_buttons.values():
            btn.setProperty("sidebarCollapsed", collapsed)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setText("" if collapsed else self._module_label_for_btn(btn))

        self.collapsed_changed.emit(collapsed)

    def _animate_sidebar_width(self, target_width: int) -> None:
        start_width = self.width()

        if self._sidebar_min_width_anim is not None:
            self._sidebar_min_width_anim.stop()
            self._sidebar_min_width_anim.deleteLater()
        if self._sidebar_max_width_anim is not None:
            self._sidebar_max_width_anim.stop()
            self._sidebar_max_width_anim.deleteLater()

        min_anim = QPropertyAnimation(self, b"minimumWidth", self)
        min_anim.setDuration(_sizes.sidebar_animation_ms)
        min_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        min_anim.setStartValue(start_width)
        min_anim.setEndValue(target_width)

        max_anim = QPropertyAnimation(self, b"maximumWidth", self)
        max_anim.setDuration(_sizes.sidebar_animation_ms)
        max_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        max_anim.setStartValue(start_width)
        max_anim.setEndValue(target_width)

        self._sidebar_min_width_anim = min_anim
        self._sidebar_max_width_anim = max_anim

        min_anim.finished.connect(lambda: setattr(self, "_sidebar_min_width_anim", None))
        max_anim.finished.connect(lambda: setattr(self, "_sidebar_max_width_anim", None))

        min_anim.start()
        max_anim.start()

    def _on_theme_changed(self, theme_name: str) -> None:  # noqa: ARG002
        self._sidebar_icon_provider.clear_cache()
        for module_key in self._module_buttons:
            self._apply_module_icon(module_key)

    def _apply_module_icon(self, module_key: str) -> None:
        btn = self._module_buttons.get(module_key)
        if btn is None:
            return
        btn.setIcon(
            self._sidebar_icon_provider.icon_for(
                module_key,
                state=self._module_icon_state(module_key),
                size=QSize(_sizes.sidebar_icon_size, _sizes.sidebar_icon_size),
            )
        )

    def _module_icon_state(self, module_key: str) -> str:
        btn = self._module_buttons.get(module_key)
        if btn is None or not btn.isEnabled():
            return "disabled"
        if bool(btn.property("moduleActive")) or bool(btn.property("moduleOpen")):
            return "active"
        if self._hovered_module_key == module_key:
            return "hover"
        return "normal"

    def _module_label_for_btn(self, btn: QPushButton) -> str:
        for module in self._visible_modules.values():
            if self._module_buttons.get(module.key) is btn:
                return module.label
        return ""

    # ── Helpers ───────────────────────────────────────────────────────────

    def _update_company_display(self, company_id: object, company_name: object) -> None:
        resolved_name = coalesce_text(
            company_name if isinstance(company_name, str) else None,
            "No active company",
        )
        self._company_name_label.setText(resolved_name)
        self._update_company_logo()

    def _update_company_logo(self) -> None:
        logo_storage_path = self._active_company_context.logo_storage_path
        if not logo_storage_path:
            self._company_logo_label.setPixmap(QPixmap())
            self._company_logo_label.setText("Logo")
            return

        resolved_path = self._company_logo_service.resolve_logo_path(logo_storage_path)
        if resolved_path is None:
            self._company_logo_label.setPixmap(QPixmap())
            self._company_logo_label.setText("Logo")
            return

        pixmap = QPixmap(str(resolved_path))
        if pixmap.isNull():
            self._company_logo_label.setPixmap(QPixmap())
            self._company_logo_label.setText("Logo")
            return

        self._company_logo_label.setText("")
        self._company_logo_label.setPixmap(
            pixmap.scaled(
                36,
                36,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ── Context menus ─────────────────────────────────────────────────────

    def _on_child_context_menu(self, nav_id: str, btn: QPushButton, pos) -> None:
        menu = QMenu(btn)
        is_fav = self._prefs.is_favorite(nav_id)
        if is_fav:
            toggle_action = menu.addAction("Remove from Favorites")
        else:
            toggle_action = menu.addAction("Add to Favorites")
        action = menu.exec(btn.mapToGlobal(pos))
        if action == toggle_action:
            if is_fav:
                self._prefs.remove_favorite(nav_id)
            else:
                self._prefs.add_favorite(nav_id)
            self._rebuild_favorites_section()

    # ── Badge API ─────────────────────────────────────────────────────────

    def set_nav_badge(self, nav_id: str, count: int) -> None:
        """Set a numeric badge on a child nav item. Pass 0 to clear."""
        self._nav_badges[nav_id] = count
        # Find badge label in the child button row
        child_btn = self._child_buttons.get(nav_id)
        if child_btn is None:
            return
        row_widget = child_btn.parentWidget()
        if row_widget is None:
            return
        # Find the badge label in the row's layout
        row_layout = row_widget.layout()
        if row_layout is None:
            return
        for i in range(row_layout.count()):
            item = row_layout.itemAt(i)
            if item and item.widget() and item.widget().objectName() == "SidebarNavBadge":
                badge_lbl: QLabel = item.widget()  # type: ignore[assignment]
                if count > 0:
                    badge_lbl.setText(str(count) if count < 100 else "99+")
                    badge_lbl.setVisible(True)
                else:
                    badge_lbl.setText("")
                    badge_lbl.setVisible(False)
                break
