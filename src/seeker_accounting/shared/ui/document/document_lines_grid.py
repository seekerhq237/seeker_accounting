"""Shared configuration helper for document line grids (Phase 3).

Thin seam so every document (invoice, bill, journal, inventory doc)
applies the same Operational Desktop grid rhythm: dense rows,
assertive column separators, visible grid, numeric right-align
alignment left to the column delegate or cell item.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


def configure_document_lines_grid(
    table: QTableView,
    *,
    editable: bool = True,
    dense: bool = True,
) -> None:
    """Apply the operational document-lines rhythm to a QTableView.

    `editable=True` enables the standard editing triggers; `dense=True`
    uses the token-driven dense row height.
    """
    row_h = (
        DEFAULT_TOKENS.sizes.row_height_dense
        if dense
        else DEFAULT_TOKENS.sizes.row_height
    )

    table.setShowGrid(True)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_h)

    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
    header.setHighlightSections(False)

    if editable:
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.CurrentChanged
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.AnyKeyPressed
            | QAbstractItemView.EditTrigger.DoubleClicked
        )
    else:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
