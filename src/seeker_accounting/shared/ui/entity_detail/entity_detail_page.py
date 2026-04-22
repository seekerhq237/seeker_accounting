"""EntityDetailPage — reusable base for entity detail workspaces.

Provides a consistent layout:
  ┌─────────────────────────────────────────────────────┐
  │  ← Back   [Action Button(s)]                        │  ← _action_row
  │─────────────────────────────────────────────────────│
  │  Title (entity name)                  ● Status chip │  ← _header_frame
  │  Subtitle (key meta line)                           │
  ├─────────────────────────────────────────────────────┤
  │  [ KPI ]  [ KPI ]  [ KPI ]  [ KPI ]                │  ← _money_bar
  ├─────────────────────────────────────────────────────┤
  │ [Tab A] [Tab B] [Tab C]                             │  ← _tab_bar
  │─────────────────────────────────────────────────────│
  │  ... tab content ...                                │  ← _tab_stack
  └─────────────────────────────────────────────────────┘

Subclasses must implement:
  - _back_nav_id: str  — the nav_id to navigate back to
  - _back_label: str   — label for the back button
  - _build_tabs() -> list[tuple[str, QWidget]]  — tab label + content widget pairs
  - set_navigation_context(context: dict) -> None  — receives entity id, loads data

Subclasses typically call:
  - _set_header(title, subtitle, status_label, is_active)
  - _money_bar.set_items([...])
  - _set_loading(True/False)

The page is shared-UI — it must not import domain services directly.
Domain services are accessed through service_registry in subclass implementations.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids as _nav_ids
from seeker_accounting.shared.ui.entity_detail.money_bar import MoneyBar, MoneyBarItem


class EntityDetailPage(QWidget):
    """Base class for entity detail workspaces.

    Do not instantiate directly — subclass and implement the required members.
    """

    # Subclass MUST set these as class attributes or override in __init__
    _back_nav_id: str = _nav_ids.DASHBOARD
    _back_label: str = "Back"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self.setObjectName("EntityDetailPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 20)
        root.setSpacing(0)

        # ── Action row (Back button + primary actions) ─────────────────
        self._action_row = self._build_action_row()
        root.addWidget(self._action_row)

        # ── Header frame (name, subtitle, status) ─────────────────────
        self._header_frame = QFrame(self)
        self._header_frame.setObjectName("EntityDetailHeader")
        header_layout = QVBoxLayout(self._header_frame)
        header_layout.setContentsMargins(0, 10, 0, 10)
        header_layout.setSpacing(3)

        # Name + status chip row
        name_row = QWidget(self._header_frame)
        name_row_layout = QHBoxLayout(name_row)
        name_row_layout.setContentsMargins(0, 0, 0, 0)
        name_row_layout.setSpacing(12)

        self._title_label = QLabel("—", self._header_frame)
        self._title_label.setObjectName("EntityDetailTitle")
        name_row_layout.addWidget(self._title_label, 1)

        self._status_chip = QLabel("", self._header_frame)
        self._status_chip.setObjectName("EntityDetailStatusChipActive")
        self._status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        name_row_layout.addWidget(self._status_chip)

        header_layout.addWidget(name_row)

        self._subtitle_label = QLabel("", self._header_frame)
        self._subtitle_label.setObjectName("EntityDetailSubtitle")
        self._subtitle_label.setWordWrap(False)
        header_layout.addWidget(self._subtitle_label)

        root.addWidget(self._header_frame)

        # ── Separator ──────────────────────────────────────────────────
        sep1 = QFrame(self)
        sep1.setObjectName("EntityDetailSeparator")
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFixedHeight(1)
        root.addWidget(sep1)

        # ── Money bar ─────────────────────────────────────────────────
        self._money_bar = MoneyBar(self)
        root.addWidget(self._money_bar)
        root.addSpacing(8)

        # ── Separator ──────────────────────────────────────────────────
        sep2 = QFrame(self)
        sep2.setObjectName("EntityDetailSeparator")
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        root.addWidget(sep2)

        # ── Tab bar + content stack ────────────────────────────────────
        self._tab_bar = QTabBar(self)
        self._tab_bar.setObjectName("EntityDetailTabBar")
        self._tab_bar.setExpanding(False)
        self._tab_bar.setDrawBase(False)
        root.addWidget(self._tab_bar)

        self._tab_stack = QStackedWidget(self)
        root.addWidget(self._tab_stack, 1)

        # Build tabs after subclass __init__ so _build_tabs() can reference
        # subclass-level state (set by _add_action_buttons in subclass __init__).

    def _build_action_row(self) -> QWidget:
        """Build the top action row with back button slot and action button slot."""
        row = QWidget(self)
        row.setObjectName("EntityDetailActionRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(8)

        self._back_button = QPushButton(f"← {self._back_label}", row)
        self._back_button.setObjectName("EntityDetailBackButton")
        self._back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_button.clicked.connect(self._navigate_back)
        layout.addWidget(self._back_button)

        layout.addStretch(1)

        # Subclasses inject their action buttons here via _action_row_layout
        self._action_row_layout = layout
        return row

    def _initialize_tabs(self) -> None:
        """Call this from the subclass __init__ after setting up tab content widgets.

        Builds the tab bar from the list returned by _build_tabs().
        """
        tabs = self._build_tabs()
        for label, widget in tabs:
            self._tab_bar.addTab(label)
            self._tab_stack.addWidget(widget)

        self._tab_bar.currentChanged.connect(self._tab_stack.setCurrentIndex)

    def _build_tabs(self) -> list[tuple[str, QWidget]]:
        """Return a list of (tab_label, content_widget) pairs.

        Subclasses must override this. Called by _initialize_tabs().
        """
        raise NotImplementedError

    def _navigate_back(self) -> None:
        self._service_registry.navigation_service.navigate(self._back_nav_id)

    def _set_header(
        self,
        title: str,
        subtitle: str,
        status_label: str,
        is_active: bool,
    ) -> None:
        """Update the header section with entity data."""
        self._title_label.setText(title)
        self._subtitle_label.setText(subtitle)
        self._status_chip.setText(f"  {status_label}  ")
        chip_name = "EntityDetailStatusChipActive" if is_active else "EntityDetailStatusChipInactive"
        self._status_chip.setObjectName(chip_name)
        # Force QSS re-evaluation after objectName change
        self._status_chip.style().unpolish(self._status_chip)
        self._status_chip.style().polish(self._status_chip)

    def _set_money_bar(self, items: list[MoneyBarItem]) -> None:
        """Convenience delegate to the money bar."""
        self._money_bar.set_items(items)
