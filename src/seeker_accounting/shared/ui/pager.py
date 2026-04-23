"""Compact pagination control used by register-style list pages.

Emits ``page_changed`` when the user navigates; the owner page reloads
the corresponding slice through the paginated service method.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from seeker_accounting.shared.dto.paginated_result import PaginatedResult


_DEFAULT_PAGE_SIZES = (50, 100, 250, 500)


class Pager(QWidget):
    """Prev/Next pager + page-size selector + "n of N" status."""

    page_changed = Signal(int)        # new 1-based page
    page_size_changed = Signal(int)   # new page size

    def __init__(
        self,
        parent: QWidget | None = None,
        page_sizes: tuple[int, ...] = _DEFAULT_PAGE_SIZES,
        default_page_size: int = 100,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Pager")
        self._page = 1
        self._page_count = 1
        self._page_size = default_page_size
        self._total_count = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._status_label = QLabel("", self)
        self._status_label.setObjectName("StatusRailText")
        layout.addWidget(self._status_label)

        layout.addStretch(1)

        self._page_size_combo = QComboBox(self)
        for size in page_sizes:
            self._page_size_combo.addItem(f"{size} / page", size)
        # Select the requested default if it exists, otherwise use index 0
        for idx in range(self._page_size_combo.count()):
            if self._page_size_combo.itemData(idx) == default_page_size:
                self._page_size_combo.setCurrentIndex(idx)
                break
        self._page_size_combo.currentIndexChanged.connect(self._handle_page_size_changed)
        layout.addWidget(self._page_size_combo)

        self._prev_button = QPushButton("Previous", self)
        self._prev_button.setProperty("variant", "ghost")
        self._prev_button.clicked.connect(self._go_prev)
        layout.addWidget(self._prev_button)

        self._page_label = QLabel("Page 1 of 1", self)
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setMinimumWidth(110)
        layout.addWidget(self._page_label)

        self._next_button = QPushButton("Next", self)
        self._next_button.setProperty("variant", "ghost")
        self._next_button.clicked.connect(self._go_next)
        layout.addWidget(self._next_button)

        self._refresh_controls()

    # ------------------------------------------------------------------

    @property
    def page(self) -> int:
        return self._page

    @property
    def page_size(self) -> int:
        return self._page_size

    def reset(self) -> None:
        """Return to page 1 without emitting signals (useful when filters change)."""
        self._page = 1
        self._refresh_controls()

    def apply_result(self, result: PaginatedResult) -> None:
        """Sync pager state to a freshly loaded page."""
        self._page = max(1, int(result.page))
        self._page_count = max(1, int(result.page_count))
        self._total_count = max(0, int(result.total_count))
        # Keep combo in sync if service reshaped the page size
        for idx in range(self._page_size_combo.count()):
            if self._page_size_combo.itemData(idx) == result.page_size:
                self._page_size_combo.blockSignals(True)
                self._page_size_combo.setCurrentIndex(idx)
                self._page_size_combo.blockSignals(False)
                self._page_size = result.page_size
                break
        start, end = result.start_index, result.end_index
        if self._total_count == 0:
            self._status_label.setText("No records")
        else:
            self._status_label.setText(
                f"{start}–{end} of {self._total_count}"
            )
        self._refresh_controls()

    # ------------------------------------------------------------------

    def _refresh_controls(self) -> None:
        self._page_label.setText(f"Page {self._page} of {self._page_count}")
        self._prev_button.setEnabled(self._page > 1)
        self._next_button.setEnabled(self._page < self._page_count)

    def _go_prev(self) -> None:
        if self._page > 1:
            self._page -= 1
            self._refresh_controls()
            self.page_changed.emit(self._page)

    def _go_next(self) -> None:
        if self._page < self._page_count:
            self._page += 1
            self._refresh_controls()
            self.page_changed.emit(self._page)

    def _handle_page_size_changed(self, _index: int) -> None:
        new_size = int(self._page_size_combo.currentData() or self._page_size)
        if new_size == self._page_size:
            return
        self._page_size = new_size
        self._page = 1  # Reset to first page for consistency
        self._refresh_controls()
        self.page_size_changed.emit(self._page_size)
