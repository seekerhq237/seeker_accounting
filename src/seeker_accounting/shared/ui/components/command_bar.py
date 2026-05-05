"""
CommandBar — adaptive horizontal command surface.

A reusable shared UI primitive that renders a sequence of
:class:`CommandItem` and :class:`CommandSeparator` entries as a single-row
toolbar. It supports priority-driven adaptive overflow:

* ``primary`` priority items always render on the bar with their label.
* ``secondary`` priority items try to fit with their label, demote to
  icon-only if width is constrained, and finally collapse into the
  overflow menu when there is still not enough room.
* ``overflow`` priority items render exclusively inside the overflow menu.

The component is a pure UI primitive — it has no knowledge of business
state, services, or accounting workflows. It only emits semantic
signals (:attr:`command_activated`, :attr:`command_toggled`) carrying
the opaque ``command_id`` of each item.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, Union

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLayout,
    QMenu,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


CommandVariant = Literal["default", "primary", "danger"]
CommandPriority = Literal["primary", "secondary", "overflow"]


# ── Token defaults ────────────────────────────────────────────────────
# Resolved lazily so the component continues to work if the parallel
# tokens patch has not yet landed. The patch overrides these via real
# attributes on ``DEFAULT_TOKENS.sizes``.
_TOKEN_DEFAULTS: dict[str, int] = {
    "command_bar_height": 36,
    "command_bar_button_height": 28,
    "command_bar_button_min_width": 28,
    "command_bar_button_padding_h": 10,
    "command_bar_icon_size": 16,
    "command_bar_overflow_width": 28,
    "command_bar_group_gap": 12,
    "command_bar_item_gap": 4,
}


def _size(name: str) -> int:
    return int(getattr(DEFAULT_TOKENS.sizes, name, _TOKEN_DEFAULTS[name]))


# ── Data classes ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CommandItem:
    """Declarative description of a single command on the bar."""

    command_id: str
    label: str
    icon_name: str = ""
    tooltip: str = ""
    shortcut: str = ""
    variant: CommandVariant = "default"
    priority: CommandPriority = "secondary"
    enabled: bool = True
    checkable: bool = False
    checked: bool = False
    group: str = ""


@dataclass(frozen=True, slots=True)
class CommandSeparator:
    """Explicit separator between two items in the same group."""

    key: str = "sep"


CommandBarItem = Union[CommandItem, CommandSeparator]


# ── Internal entry record ────────────────────────────────────────────


class _Entry:
    """Mutable per-item state held by the bar."""

    __slots__ = (
        "item",
        "button",
        "label_width",
        "icon_only_width",
        "is_separator",
        "separator",
    )

    def __init__(
        self,
        item: CommandBarItem,
        button: QToolButton | None,
        separator: QFrame | None,
        label_width: int,
        icon_only_width: int,
    ) -> None:
        self.item = item
        self.button = button
        self.separator = separator
        self.is_separator = isinstance(item, CommandSeparator)
        self.label_width = label_width
        self.icon_only_width = icon_only_width


# ── Widget ────────────────────────────────────────────────────────────


class CommandBar(QWidget):
    """Adaptive horizontal command bar with priority-driven overflow."""

    command_activated = Signal(str)
    command_toggled = Signal(str, bool)

    def __init__(
        self,
        items: Iterable[CommandBarItem] = (),
        *,
        icon_provider: IconProvider | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CommandBar")

        self._icon_provider = icon_provider
        self._entries: list[_Entry] = []
        # Group-separator frames placed between rendered groups.
        self._group_separators: list[QFrame] = []
        # Latest computed visibility plan keyed by entry index.
        # ("on_bar_label", "on_bar_icon", "overflow", "hidden").
        self._plan: list[str] = []

        height = _size("command_bar_height")
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # We adapt our own contents — never let the layout's content
        # minimum prevent the widget from shrinking.
        self.setMinimumWidth(0)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(0)
        self._layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._overflow_button = self._build_overflow_button()
        self._overflow_menu = QMenu(self._overflow_button)
        self._overflow_button.setMenu(self._overflow_menu)
        self._layout.addStretch(1)
        self._layout.addWidget(self._overflow_button)

        self.set_items(items)

    # ── Public API ────────────────────────────────────────────────────

    def set_items(self, items: Iterable[CommandBarItem]) -> None:
        """Replace all items and rebuild internal widgets."""
        self._clear_entries()
        for item in items:
            self._append_entry(item)
        self._relayout_static()
        self._recompute_plan()

    def set_enablement(self, state: Mapping[str, bool]) -> None:
        """Apply an enable/disable map. Missing keys retain prior state."""
        for entry in self._entries:
            if entry.is_separator or entry.button is None:
                continue
            assert isinstance(entry.item, CommandItem)
            if entry.item.command_id in state:
                entry.button.setEnabled(bool(state[entry.item.command_id]))
        self._refresh_overflow_menu()

    def set_checked(self, command_id: str, checked: bool) -> None:
        """Toggle a checkable command without re-emitting its signal."""
        entry = self._find(command_id)
        if entry is None or entry.button is None:
            return
        assert isinstance(entry.item, CommandItem)
        if not entry.item.checkable:
            return
        button = entry.button
        with _SignalBlocker(button):
            button.setChecked(bool(checked))
        # Replace the dataclass with an updated copy so subsequent
        # `set_items` calls preserve the latest state if reused.
        entry.item = _replace_item_checked(entry.item, bool(checked))
        self._refresh_overflow_menu()

    def set_label(self, command_id: str, label: str) -> None:
        """Update a command's display label and recompute layout."""
        entry = self._find(command_id)
        if entry is None or entry.button is None:
            return
        assert isinstance(entry.item, CommandItem)
        entry.item = _replace_item_label(entry.item, label)
        entry.button.setText(label)
        entry.button.setToolTip(_compose_tooltip(entry.item))
        entry.label_width = self._measure_label_width(entry.button, label)
        self._recompute_plan()

    def refresh_icons(self) -> None:
        """Re-apply icons after a theme change."""
        if self._icon_provider is None:
            return
        size = _size("command_bar_icon_size")
        for entry in self._entries:
            if entry.is_separator or entry.button is None:
                continue
            assert isinstance(entry.item, CommandItem)
            if entry.item.icon_name:
                entry.button.setIcon(
                    self._icon_provider.icon(entry.item.icon_name, size=size)
                )
        self._refresh_overflow_menu()

    # ── Construction helpers ──────────────────────────────────────────

    def _build_overflow_button(self) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("CommandBarOverflow")
        button.setText("\u22ef")  # midline horizontal ellipsis
        button.setToolTip("More commands")
        button.setAutoRaise(True)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setFixedHeight(_size("command_bar_button_height"))
        button.setFixedWidth(_size("command_bar_overflow_width"))
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setVisible(False)
        return button

    def _clear_entries(self) -> None:
        for entry in self._entries:
            if entry.button is not None:
                entry.button.deleteLater()
            if entry.separator is not None:
                entry.separator.deleteLater()
        for sep in self._group_separators:
            sep.deleteLater()
        self._entries.clear()
        self._group_separators.clear()
        self._plan.clear()

    def _append_entry(self, item: CommandBarItem) -> None:
        if isinstance(item, CommandSeparator):
            sep = self._make_inline_separator()
            self._entries.append(_Entry(item, None, sep, 0, 0))
            return

        button = self._make_button(item)
        label_width, icon_only_width = self._measure_widths(button, item)
        self._entries.append(_Entry(item, button, None, label_width, icon_only_width))

    def _make_button(self, item: CommandItem) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("CommandBarButton")
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setText(item.label)
        button.setFixedHeight(_size("command_bar_button_height"))
        button.setIconSize(QSize(_size("command_bar_icon_size"), _size("command_bar_icon_size")))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setEnabled(item.enabled)
        button.setToolTip(_compose_tooltip(item))
        if item.shortcut:
            button.setShortcut(item.shortcut)

        if item.icon_name and self._icon_provider is not None:
            button.setIcon(
                self._icon_provider.icon(
                    item.icon_name, size=_size("command_bar_icon_size")
                )
            )

        # Dynamic properties consumed by QSS.
        button.setProperty("primary", "true" if item.variant == "primary" else "false")
        button.setProperty("danger", "true" if item.variant == "danger" else "false")
        button.setProperty("commandId", item.command_id)

        if item.checkable:
            button.setCheckable(True)
            button.setChecked(bool(item.checked))
            button.toggled.connect(
                lambda checked, cid=item.command_id: self._on_toggled(cid, checked)
            )
        else:
            button.clicked.connect(
                lambda _checked=False, cid=item.command_id: self._on_clicked(cid)
            )
        return button

    def _make_inline_separator(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("CommandBarSeparator")
        frame.setFrameShape(QFrame.Shape.VLine)
        frame.setFrameShadow(QFrame.Shadow.Plain)
        frame.setFixedWidth(1)
        frame.setFixedHeight(max(_size("command_bar_button_height") - 8, 12))
        return frame

    def _make_group_separator(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("CommandBarGroupSeparator")
        frame.setFrameShape(QFrame.Shape.VLine)
        frame.setFrameShadow(QFrame.Shadow.Plain)
        frame.setFixedWidth(1)
        frame.setFixedHeight(max(_size("command_bar_button_height") - 6, 14))
        return frame

    # ── Measurement ───────────────────────────────────────────────────

    def _measure_widths(self, button: QToolButton, item: CommandItem) -> tuple[int, int]:
        return (
            self._measure_label_width(button, item.label),
            self._measure_icon_only_width(item),
        )

    def _measure_label_width(self, button: QToolButton, label: str) -> int:
        fm = button.fontMetrics()
        text_w = fm.horizontalAdvance(label) if label else 0
        icon_w = _size("command_bar_icon_size") + 6 if button.icon().isNull() is False else 0
        pad = _size("command_bar_button_padding_h") * 2
        return max(_size("command_bar_button_min_width"), text_w + icon_w + pad)

    def _measure_icon_only_width(self, item: CommandItem) -> int:
        if not item.icon_name:
            # No icon — fall back to a compact label box so the button
            # still has something to render when demoted.
            return _size("command_bar_button_min_width")
        return max(
            _size("command_bar_button_min_width"),
            _size("command_bar_icon_size") + _size("command_bar_button_padding_h") * 2,
        )

    # ── Layout & adaptive plan ────────────────────────────────────────

    def _relayout_static(self) -> None:
        """Insert all widgets into the layout once, in declared order.

        Visibility is then driven exclusively by :meth:`_recompute_plan`.
        Group separators are inserted between consecutive groups whose
        first non-separator item differs.
        """
        # Drop everything except the trailing stretch + overflow button.
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            if widget is self._overflow_button:
                continue
            widget.setParent(self)

        last_group: str | None = None
        sep_index = 0
        for entry in self._entries:
            if entry.is_separator:
                if entry.separator is not None:
                    self._layout.addWidget(entry.separator)
                continue
            assert isinstance(entry.item, CommandItem)
            current_group = entry.item.group
            if last_group is not None and current_group != last_group:
                if sep_index < len(self._group_separators):
                    sep = self._group_separators[sep_index]
                else:
                    sep = self._make_group_separator()
                    self._group_separators.append(sep)
                self._layout.addWidget(sep)
                sep_index += 1
            last_group = current_group
            if entry.button is not None:
                self._layout.addWidget(entry.button)

        # Trim any extra group separators created by previous configurations.
        for stale in self._group_separators[sep_index:]:
            stale.setParent(None)
            stale.deleteLater()
        del self._group_separators[sep_index:]

        self._layout.addStretch(1)
        self._layout.addWidget(self._overflow_button)

    def resizeEvent(self, event) -> None:  # noqa: D401, N802 (Qt naming)
        super().resizeEvent(event)
        self._recompute_plan()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        # The bar adapts its own contents — it must be allowed to shrink
        # below the natural sum of its children. We only reserve enough
        # width for the overflow trigger plus padding.
        margins = self._layout.contentsMargins()
        width = (
            margins.left()
            + margins.right()
            + _size("command_bar_overflow_width")
            + _size("command_bar_item_gap")
        )
        return QSize(width, _size("command_bar_height"))

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(400, _size("command_bar_height"))

    def _recompute_plan(self) -> None:
        """Decide visibility/state of every entry given the current width."""
        if not self._entries:
            self._overflow_button.setVisible(False)
            return

        # Step 1 — initial intent per item.
        # primary  -> on_bar_label
        # secondary -> on_bar_label
        # overflow  -> overflow
        plan: list[str] = []
        for entry in self._entries:
            if entry.is_separator:
                plan.append("separator")
                continue
            assert isinstance(entry.item, CommandItem)
            if entry.item.priority == "overflow":
                plan.append("overflow")
            else:
                plan.append("on_bar_label")

        item_gap = _size("command_bar_item_gap")
        group_gap = _size("command_bar_group_gap")
        overflow_w = _size("command_bar_overflow_width") + item_gap
        margins = self._layout.contentsMargins()
        available = max(0, self.width() - margins.left() - margins.right())

        def needed_width(plan: list[str]) -> tuple[int, bool]:
            width = 0
            last_group: str | None = None
            any_visible = False
            any_overflow = any(p == "overflow" for p in plan)
            for entry, state in zip(self._entries, plan):
                if state == "overflow":
                    continue
                if entry.is_separator:
                    if any_visible:
                        width += entry.separator.width() if entry.separator else 1
                        width += item_gap
                    continue
                assert isinstance(entry.item, CommandItem)
                if last_group is not None and entry.item.group != last_group:
                    width += group_gap
                last_group = entry.item.group
                if any_visible:
                    width += item_gap
                if state == "on_bar_label":
                    width += entry.label_width
                else:  # on_bar_icon
                    width += entry.icon_only_width
                any_visible = True
            if any_overflow:
                width += overflow_w
            return width, any_overflow

        # Step 2 — if too wide, demote secondary items (last to first)
        # from label to icon-only.
        secondary_indices = [
            i
            for i, e in enumerate(self._entries)
            if not e.is_separator
            and isinstance(e.item, CommandItem)
            and e.item.priority == "secondary"
        ]

        width, _ = needed_width(plan)
        if width > available:
            for idx in reversed(secondary_indices):
                if plan[idx] == "on_bar_label":
                    item = self._entries[idx].item
                    assert isinstance(item, CommandItem)
                    if item.icon_name:
                        plan[idx] = "on_bar_icon"
                        width, _ = needed_width(plan)
                        if width <= available:
                            break

        # Step 3 — still too wide? push secondary icon-only items into
        # overflow (last to first), then demote/push label-only secondary
        # items that have no icon.
        if width > available:
            for idx in reversed(secondary_indices):
                if plan[idx] in ("on_bar_icon", "on_bar_label"):
                    plan[idx] = "overflow"
                    width, _ = needed_width(plan)
                    if width <= available:
                        break

        # Step 4 — strip leading/trailing inline separators on the bar.
        plan = self._strip_dangling_separators(plan)

        self._plan = plan
        self._apply_plan(plan)

    def _strip_dangling_separators(self, plan: list[str]) -> list[str]:
        # Identify visible-on-bar entries, hide separators that are
        # adjacent only to overflow entries.
        new_plan = list(plan)
        # First, hide separators where neighbouring non-separator items
        # are not both on the bar.
        for i, entry in enumerate(self._entries):
            if not entry.is_separator:
                continue
            # Find prev/next non-separator visibility.
            prev_visible = False
            for j in range(i - 1, -1, -1):
                if self._entries[j].is_separator:
                    continue
                prev_visible = new_plan[j] in ("on_bar_label", "on_bar_icon")
                break
            next_visible = False
            for j in range(i + 1, len(self._entries)):
                if self._entries[j].is_separator:
                    continue
                next_visible = new_plan[j] in ("on_bar_label", "on_bar_icon")
                break
            new_plan[i] = "separator" if (prev_visible and next_visible) else "hidden"
        return new_plan

    def _apply_plan(self, plan: list[str]) -> None:
        any_overflow = False
        last_group: str | None = None
        sep_index = 0
        for entry, state in zip(self._entries, plan):
            if entry.is_separator:
                if entry.separator is not None:
                    entry.separator.setVisible(state == "separator")
                continue
            assert isinstance(entry.item, CommandItem)
            button = entry.button
            if button is None:
                continue
            if state == "on_bar_label":
                button.setVisible(True)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.setMinimumWidth(0)
            elif state == "on_bar_icon":
                button.setVisible(True)
                if entry.item.icon_name:
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                else:
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                button.setMinimumWidth(_size("command_bar_button_min_width"))
            else:  # overflow / hidden
                button.setVisible(False)
                any_overflow = any_overflow or state == "overflow"

        # Toggle visibility of group separators based on which neighbours
        # on either side are visible on the bar.
        sep_index = 0
        last_visible_group: str | None = None
        # Map entry index -> visible-on-bar?
        entry_visible_on_bar = [
            (state in ("on_bar_label", "on_bar_icon")) and not e.is_separator
            for e, state in zip(self._entries, plan)
        ]
        # Walk entries; whenever we transition between visible groups,
        # show the corresponding stored group separator if available.
        for i, entry in enumerate(self._entries):
            if entry.is_separator or not entry_visible_on_bar[i]:
                continue
            assert isinstance(entry.item, CommandItem)
            current_group = entry.item.group
            if last_visible_group is not None and current_group != last_visible_group:
                if sep_index < len(self._group_separators):
                    self._group_separators[sep_index].setVisible(True)
                sep_index += 1
            last_visible_group = current_group
        # Hide trailing/unused group separators.
        for sep in self._group_separators[sep_index:]:
            sep.setVisible(False)
        # And hide separators between groups that became fully invisible.
        # (Anything not affirmatively shown above stays hidden.)
        for sep in self._group_separators[:sep_index]:
            pass  # already shown above

        # Account for any overflow items including secondaries demoted to overflow.
        any_overflow = any(s == "overflow" for s in plan)
        self._overflow_button.setVisible(any_overflow)
        self._refresh_overflow_menu()

    # ── Overflow menu ─────────────────────────────────────────────────

    def _refresh_overflow_menu(self) -> None:
        self._overflow_menu.clear()
        if not self._plan:
            return
        last_group: str | None = None
        added_any = False
        for entry, state in zip(self._entries, self._plan):
            if entry.is_separator:
                continue
            if state != "overflow":
                continue
            assert isinstance(entry.item, CommandItem)
            if added_any and last_group is not None and entry.item.group != last_group:
                self._overflow_menu.addSeparator()
            action = QAction(entry.item.label, self._overflow_menu)
            if entry.item.icon_name and self._icon_provider is not None:
                action.setIcon(
                    self._icon_provider.icon(
                        entry.item.icon_name, size=_size("command_bar_icon_size")
                    )
                )
            action.setToolTip(_compose_tooltip(entry.item))
            action.setEnabled(
                entry.button.isEnabled() if entry.button is not None else entry.item.enabled
            )
            if entry.item.checkable:
                action.setCheckable(True)
                action.setChecked(
                    entry.button.isChecked() if entry.button is not None else entry.item.checked
                )
                action.toggled.connect(
                    lambda checked, cid=entry.item.command_id: self._on_toggled(cid, checked)
                )
            else:
                action.triggered.connect(
                    lambda _checked=False, cid=entry.item.command_id: self._on_clicked(cid)
                )
            self._overflow_menu.addAction(action)
            last_group = entry.item.group
            added_any = True

    # ── Signal handlers ───────────────────────────────────────────────

    def _on_clicked(self, command_id: str) -> None:
        entry = self._find(command_id)
        if entry is None or entry.button is None or not entry.button.isEnabled():
            return
        self.command_activated.emit(command_id)

    def _on_toggled(self, command_id: str, checked: bool) -> None:
        entry = self._find(command_id)
        if entry is None or entry.button is None:
            return
        # Mirror state on the bar button if the toggle came from the menu.
        if entry.button.isChecked() != checked:
            with _SignalBlocker(entry.button):
                entry.button.setChecked(checked)
        if isinstance(entry.item, CommandItem):
            entry.item = _replace_item_checked(entry.item, checked)
        self.command_toggled.emit(command_id, checked)

    def _find(self, command_id: str) -> _Entry | None:
        for entry in self._entries:
            if entry.is_separator:
                continue
            assert isinstance(entry.item, CommandItem)
            if entry.item.command_id == command_id:
                return entry
        return None


# ── Helpers ───────────────────────────────────────────────────────────


def _compose_tooltip(item: CommandItem) -> str:
    base = item.tooltip or item.label
    if item.shortcut:
        return f"{base} ({item.shortcut})"
    return base


def _replace_item_label(item: CommandItem, label: str) -> CommandItem:
    return CommandItem(
        command_id=item.command_id,
        label=label,
        icon_name=item.icon_name,
        tooltip=item.tooltip,
        shortcut=item.shortcut,
        variant=item.variant,
        priority=item.priority,
        enabled=item.enabled,
        checkable=item.checkable,
        checked=item.checked,
        group=item.group,
    )


def _replace_item_checked(item: CommandItem, checked: bool) -> CommandItem:
    return CommandItem(
        command_id=item.command_id,
        label=item.label,
        icon_name=item.icon_name,
        tooltip=item.tooltip,
        shortcut=item.shortcut,
        variant=item.variant,
        priority=item.priority,
        enabled=item.enabled,
        checkable=item.checkable,
        checked=checked,
        group=item.group,
    )


class _SignalBlocker:
    """Context manager that temporarily blocks Qt signals on a widget."""

    __slots__ = ("_widget", "_was_blocked")

    def __init__(self, widget: QWidget) -> None:
        self._widget = widget
        self._was_blocked = False

    def __enter__(self) -> None:
        self._was_blocked = self._widget.blockSignals(True)

    def __exit__(self, *_exc: object) -> None:
        self._widget.blockSignals(self._was_blocked)
