"""SearchableComboBox — shared reusable searchable dropdown for Seeker Accounting.

Provides a live-search-enabled combo box that supports:
- Multi-token search: typing "ban cam" matches "Bank of Cameroon"
- Ghost placeholder text that disappears when you start typing
- Clean mapping between display text and underlying ID/code/userData
- Keyboard navigation (arrow keys, Enter to confirm, Escape to revert)
- Combined search text (e.g. "CODE  Name") for richer matching
- Consistent round-trip of selected values via set_current_value / current_value

Usage
-----
    combo = SearchableComboBox(parent)
    combo.set_items([
        ("US  United States of America", "US"),
        ("CM  Cameroon", "CM"),
    ], placeholder="Select country")
    combo.set_current_value("CM")
    selected = combo.current_value()  # "CM"
"""
from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QWidget

# Role used to store the underlying value (ID, code, etc.)
_VALUE_ROLE = Qt.ItemDataRole.UserRole + 1
# Role used for the full searchable string (may differ from display)
_SEARCH_ROLE = Qt.ItemDataRole.UserRole + 2


class _TokenFilterProxyModel(QSortFilterProxyModel):
    """Proxy that splits the filter string into whitespace-separated tokens
    and requires ALL tokens to appear in the search text (case-insensitive).

    ``"ban cam"`` matches ``"Bank of Cameroon"`` because both ``"ban"`` and
    ``"cam"`` are found.  The placeholder row (source row 0 when present) is
    hidden during an active search so it does not clutter the filtered list.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._has_placeholder = False

    def filterAcceptsRow(self, source_row: int, source_parent: Any) -> bool:
        pattern = self.filterRegularExpression().pattern()
        if not pattern:
            return True
        # Hide placeholder while user is typing a search query
        if self._has_placeholder and source_row == 0:
            return False
        index = self.sourceModel().index(source_row, 0, source_parent)
        search_text: str = index.data(_SEARCH_ROLE) or ""
        tokens = pattern.lower().split()
        if not tokens:
            return True
        search_lower = search_text.lower()
        return all(tok in search_lower for tok in tokens)


class SearchableComboBox(QComboBox):
    """Drop-in replacement for QComboBox with live search filtering.

    Signals
    -------
    value_changed(object)
        Emitted when the selected underlying value changes. The argument
        is the value (same type passed via ``set_items``).
    """

    value_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Internal model
        self._source_model = QStandardItemModel(self)
        self._proxy_model = _TokenFilterProxyModel(self)
        self._proxy_model.setSourceModel(self._source_model)
        self._proxy_model.setFilterRole(_SEARCH_ROLE)

        # Editable for typing
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setModel(self._proxy_model)

        # No QCompleter — the proxy model handles all filtering.
        # The old completer conflicted with the proxy filter and caused
        # race conditions during popup show/hide cycles.
        self.setCompleter(None)

        # typing drives the filter
        self.lineEdit().textEdited.connect(self._on_text_edited)
        # confirmed selection (click or Enter in popup)
        self.activated.connect(self._on_activated)
        # programmatic / arrow-nav changes (only emits when not searching)
        self.currentIndexChanged.connect(self._on_index_changed)

        self._placeholder: str | None = None
        self._placeholder_value: Any = None
        self._suppress_signals = False
        self._is_searching = False
        self._pre_search_value: Any = None

        self.setMaxVisibleItems(18)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_items(
        self,
        items: Sequence[tuple[str, Any]],
        *,
        placeholder: str | None = None,
        placeholder_value: Any = None,
        search_texts: Sequence[str] | None = None,
    ) -> None:
        """Populate the combo with ``(display_text, value)`` pairs.

        Parameters
        ----------
        items:
            Sequence of ``(display_text, underlying_value)`` tuples.
        placeholder:
            Optional first entry shown before any selection (e.g. "Select country").
            Rendered as ghost text in the line edit — not as real text.
        placeholder_value:
            Value returned when the placeholder is selected (default ``None``).
        search_texts:
            Optional parallel sequence of search strings. When provided,
            typing filters against these instead of the display text.
            Useful for combining code + name when the display text is shorter.
            Must be the same length as *items*.
        """
        self._suppress_signals = True
        try:
            self._source_model.clear()
            self._placeholder = placeholder
            self._placeholder_value = placeholder_value
            self._proxy_model._has_placeholder = placeholder is not None

            if placeholder is not None:
                ph_item = QStandardItem(placeholder)
                ph_item.setData(placeholder_value, _VALUE_ROLE)
                ph_item.setData(placeholder, _SEARCH_ROLE)
                self._source_model.appendRow(ph_item)

            for i, (display_text, value) in enumerate(items):
                item = QStandardItem(display_text)
                item.setData(value, _VALUE_ROLE)
                search_str = search_texts[i] if search_texts else display_text
                item.setData(search_str, _SEARCH_ROLE)
                self._source_model.appendRow(item)

            self._proxy_model.setFilterFixedString("")
            self._proxy_model.invalidateFilter()
            self.setCurrentIndex(0)
            # Ghost placeholder in the line edit
            if placeholder is not None:
                self.lineEdit().setPlaceholderText(placeholder)
            self._sync_display()
        finally:
            self._suppress_signals = False

    def set_current_value(self, value: Any) -> None:
        """Select the item whose underlying value matches *value*."""
        self._suppress_signals = True
        try:
            for source_row in range(self._source_model.rowCount()):
                item = self._source_model.item(source_row)
                if item is not None and item.data(_VALUE_ROLE) == value:
                    source_index = self._source_model.index(source_row, 0)
                    proxy_index = self._proxy_model.mapFromSource(source_index)
                    if proxy_index.isValid():
                        self.setCurrentIndex(proxy_index.row())
                        self._sync_display()
                        return

            # Value not found — reset to first item (placeholder or first real)
            self.setCurrentIndex(0)
            self._sync_display()
        finally:
            self._suppress_signals = False

    def current_value(self) -> Any:
        """Return the underlying value of the currently selected item."""
        proxy_index = self._proxy_model.index(self.currentIndex(), 0)
        if proxy_index.isValid():
            source_index = self._proxy_model.mapToSource(proxy_index)
            item = self._source_model.itemFromIndex(source_index)
            if item is not None:
                return item.data(_VALUE_ROLE)
        return self._placeholder_value

    def clear_selection(self) -> None:
        """Reset to the placeholder (first) item."""
        self._proxy_model.setFilterFixedString("")
        self._proxy_model.invalidateFilter()
        self._suppress_signals = True
        try:
            self.setCurrentIndex(0)
            self._sync_display()
        finally:
            self._suppress_signals = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sync_display(self) -> None:
        """Set line edit text: empty for placeholder (ghost text shows), display text otherwise."""
        val = self.current_value()
        if val == self._placeholder_value and self._placeholder is not None:
            self.lineEdit().setText("")
            return
        # Read the display text from the source model item — NOT from
        # currentText() which returns lineEdit().text() on editable combos
        # and would just echo stale search text back.
        proxy_idx = self._proxy_model.index(self.currentIndex(), 0)
        if proxy_idx.isValid():
            source_idx = self._proxy_model.mapToSource(proxy_idx)
            item = self._source_model.itemFromIndex(source_idx)
            self.lineEdit().setText(item.text() if item else "")
        else:
            self.lineEdit().setText("")

    def _end_search_and_select(self, value: Any) -> None:
        """Clear the filter, re-select *value* in the unfiltered model, sync display."""
        self._is_searching = False
        self._proxy_model.setFilterFixedString("")
        self._proxy_model.invalidateFilter()
        self.set_current_value(value)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_text_edited(self, text: str) -> None:
        """Live-filter the dropdown as the user types."""
        if not self._is_searching:
            self._pre_search_value = self.current_value()
        self._is_searching = True

        self._proxy_model.setFilterFixedString(text)
        self._proxy_model.invalidateFilter()

        # Only open the popup if it isn't already visible.  Calling
        # showPopup() every keystroke causes Qt to re-layout the popup
        # window, which triggers focus churn and adds latency.
        if not self.view().isVisible():
            self.showPopup()

        if not text:
            # User backspaced to empty — exit search mode so arrow-nav works
            self._is_searching = False
            return

        # Auto-highlight (but don't emit) when exactly one real item matches.
        # The user hasn't confirmed yet — they might keep typing.
        visible = self._proxy_model.rowCount()
        if visible == 1:
            le = self.lineEdit()
            saved_text = le.text()
            saved_cursor = le.cursorPosition()
            self._suppress_signals = True
            try:
                self.setCurrentIndex(0)
            finally:
                self._suppress_signals = False
            # setCurrentIndex replaces lineEdit text with the item's
            # display text — restore the user's actual search string.
            le.setText(saved_text)
            le.setCursorPosition(saved_cursor)

    def _on_activated(self, index: int) -> None:
        """User confirmed a selection (click or Enter in the popup)."""
        value = self.current_value()
        self._end_search_and_select(value)
        self.value_changed.emit(value)

    def _on_index_changed(self, index: int) -> None:
        if self._suppress_signals or self._is_searching:
            return
        self._sync_display()
        self.value_changed.emit(self.current_value())

    # ------------------------------------------------------------------
    # Event overrides
    # ------------------------------------------------------------------

    def focusInEvent(self, event: Any) -> None:
        """Select all text on focus so typing immediately starts a search."""
        super().focusInEvent(event)
        # Don't selectAll() during an active search — popup show/hide
        # cycles on Windows can trigger re-focus events that would wipe
        # the search string the user is in the middle of typing.
        if not self._is_searching:
            self.lineEdit().selectAll()

    def focusOutEvent(self, event: Any) -> None:
        """Confirm the current selection and restore display text."""
        # Ignore popup-related focus losses — the combo's own popup
        # stealing focus is not a real focus-out.
        reason = event.reason() if hasattr(event, 'reason') else None
        if reason == Qt.FocusReason.PopupFocusReason:
            super().focusOutEvent(event)
            return
        if self._is_searching:
            value = self.current_value()
            self._end_search_and_select(value)
            self.value_changed.emit(value)
        super().focusOutEvent(event)

    def showPopup(self) -> None:
        """When opening the popup outside of a search, ensure the filter is clear."""
        if not self._is_searching:
            self._proxy_model.setFilterFixedString("")
            self._proxy_model.invalidateFilter()
        super().showPopup()

    def hidePopup(self) -> None:
        """Close the popup without clearing the filter — prevents the
        show/hide race that killed mid-search keystrokes."""
        super().hidePopup()

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape and self._is_searching:
            # Revert to what was selected before the search began
            self._end_search_and_select(self._pre_search_value)
            self.hidePopup()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._is_searching:
            value = self.current_value()
            self._end_search_and_select(value)
            self.hidePopup()
            self.value_changed.emit(value)
            return
        super().keyPressEvent(event)
