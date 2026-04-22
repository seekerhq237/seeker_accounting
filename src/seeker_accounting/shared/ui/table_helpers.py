from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
)

from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

_COMPACT_ROW_HEIGHT = 28


class _NoCellFocusDelegate(QStyledItemDelegate):
    """Suppresses the per-cell focus rectangle.

    Sage-style registers highlight the entire selected *row* but never
    paint a focus frame around a single cell. Qt's default delegate
    draws a dotted ``PE_FrameFocusRect`` when an item has focus — we
    clear that state before the base delegate paints.
    """

    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        super().initStyleOption(option, index)
        option.state = option.state & ~QStyle.StateFlag.State_HasFocus


def _apply_compact_base(table: QTableView) -> None:
    """Shared visual baseline for compact tables.

    Operational Desktop note: compact tables now adopt the same flat
    dense grammar as register tables (visible grid, dense row height,
    no highlighted header sections, no per-cell focus frame) so every
    list/table in the app reads with the same rhythm.
    """
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setWordWrap(False)
    table.setTabKeyNavigation(False)
    table.setItemDelegate(_NoCellFocusDelegate(table))
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(DEFAULT_TOKENS.sizes.row_height_dense)
    table.verticalHeader().setMinimumSectionSize(DEFAULT_TOKENS.sizes.row_height_dense)

    header = table.horizontalHeader()
    header.setStretchLastSection(True)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setHighlightSections(False)
    header.setFixedHeight(DEFAULT_TOKENS.sizes.row_height_dense + 2)


def configure_compact_table(table: QTableView) -> None:
    """Standard compact read-only table: sorting on, editing off."""
    _apply_compact_base(table)
    table.setSortingEnabled(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)


def configure_compact_editable_table(table: QTableView) -> None:
    """Compact table that preserves cell editing. Sorting disabled to avoid
    row reorder during user input."""
    _apply_compact_base(table)
    table.setSortingEnabled(False)
    # Editable tables keep the default delegate so edit triggers stay active;
    # re-install the default Qt delegate (the focus-suppressing one would
    # still allow editing, but we keep behavior explicit).
    table.setItemDelegate(QStyledItemDelegate(table))
    # Single-click activates editing (for cells without persistent editors)
    table.setEditTriggers(
        QAbstractItemView.EditTrigger.CurrentChanged
        | QAbstractItemView.EditTrigger.SelectedClicked
        | QAbstractItemView.EditTrigger.AnyKeyPressed
        | QAbstractItemView.EditTrigger.DoubleClicked
    )


def configure_dense_table(table: QTableView) -> None:
    """Operational Desktop dense register table.

    Stronger rhythm than compact: visible grid (column separators
    surface naturally via the QSS header/table rules), token-driven
    dense row height, sort enabled, editing disabled, no per-cell
    focus frame. Intended for register/list screens.
    """
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setWordWrap(False)
    table.setTabKeyNavigation(False)
    table.setItemDelegate(_NoCellFocusDelegate(table))
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(DEFAULT_TOKENS.sizes.row_height_dense)
    table.verticalHeader().setMinimumSectionSize(DEFAULT_TOKENS.sizes.row_height_dense)

    header = table.horizontalHeader()
    header.setStretchLastSection(True)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setHighlightSections(False)
    header.setFixedHeight(DEFAULT_TOKENS.sizes.row_height_dense + 2)

    table.setSortingEnabled(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

