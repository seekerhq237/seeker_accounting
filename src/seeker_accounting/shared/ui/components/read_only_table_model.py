"""ReadOnlyTableModel — high-performance QAbstractTableModel for read-only lists.

Why this exists
---------------
The old pattern of populating QTableWidget via per-row ``insertRow()`` +
per-cell ``setItem()`` calls triggers a full layout pass for every row, making
1 000-row tables noticeably slow.  ``QAbstractTableModel`` with
``beginResetModel()`` / ``endResetModel()`` delivers all rows to the view in a
single pass so the delegate only paints the visible viewport.

Usage
-----
    from seeker_accounting.shared.ui.components.read_only_table_model import (
        ReadOnlyTableModel, selected_user_data,
    )

    # Build once (e.g., inside _build_employee_table):
    self._emp_model = ReadOnlyTableModel(
        ["Employee No.", "Name", "Department", "Status"],
    )
    self._emp_proxy = QSortFilterProxyModel(parent)
    self._emp_proxy.setSourceModel(self._emp_model)

    self._emp_view = QTableView(parent)
    configure_compact_table(self._emp_view)
    self._emp_view.setModel(self._emp_proxy)

    # Populate (atomic, single layout pass):
    rows  = [[e.employee_number, e.display_name, e.dept, "Active"] for e in employees]
    udata = [e.id for e in employees]
    self._emp_model.reset_data(rows, udata)

    # Read selected UserRole value:
    emp_id = selected_user_data(self._emp_view)
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtWidgets import QTableView


class ReadOnlyTableModel(QAbstractTableModel):
    """Generic read-only table model backed by a list of row-lists.

    Each cell value is rendered as ``str(value)`` or ``""`` if *None*.
    A per-row *user_data* list (defaults to all ``None``) is stored and
    returned via ``Qt.ItemDataRole.UserRole`` on column 0.  Callers
    commonly store the primary key there.

    Numeric columns receive right-alignment automatically when their
    index is included in *right_align_cols*.
    """

    def __init__(
        self,
        headers: list[str],
        right_align_cols: frozenset[int] | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._headers: list[str] = list(headers)
        self._right_cols: frozenset[int] = right_align_cols or frozenset()
        self._rows: list[list[Any]] = []
        self._user_data: list[Any] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def reset_data(
        self,
        rows: list[list[Any]],
        user_data: list[Any] | None = None,
    ) -> None:
        """Replace all rows atomically.

        Wraps the mutation in ``beginResetModel`` / ``endResetModel`` so the
        view performs a single layout pass regardless of row count.
        """
        self.beginResetModel()
        self._rows = list(rows)
        n = len(self._rows)
        self._user_data = list(user_data) if user_data is not None else [None] * n
        self.endResetModel()

    def user_data_at(self, source_row: int) -> Any:
        """Return the UserRole value stored for *source_row* (proxy-safe)."""
        if 0 <= source_row < len(self._user_data):
            return self._user_data[source_row]
        return None

    # ── QAbstractTableModel interface ─────────────────────────────────────────

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._rows):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            val = self._rows[row][col]
            return "" if val is None else str(val)
        if role == Qt.ItemDataRole.UserRole:
            return self._user_data[row] if row < len(self._user_data) else None
        if role == Qt.ItemDataRole.TextAlignmentRole and col in self._right_cols:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._headers)
        ):
            return self._headers[section]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:  # type: ignore[override]
        """In-place sort so QTableView header clicks work without a proxy."""
        if not self._rows:
            return
        self.layoutAboutToBeChanged.emit()
        reverse = order == Qt.SortOrder.DescendingOrder
        combined = list(zip(self._rows, self._user_data))
        combined.sort(
            key=lambda pair: (str(pair[0][column]).lower() if pair[0][column] is not None else ""),
            reverse=reverse,
        )
        self._rows, self._user_data = map(list, zip(*combined))
        self.layoutChanged.emit()


# ── Convenience helper ────────────────────────────────────────────────────────

def selected_user_data(view: QTableView) -> Any:
    """Return the ``UserRole`` value for the view's currently selected row.

    Handles the common pattern where the view uses a ``QSortFilterProxyModel``
    in front of a :class:`ReadOnlyTableModel` — the proxy index is mapped back
    to the source before reading UserRole data.

    Returns *None* if nothing is selected.
    """
    sel = view.selectionModel()
    if sel is None:
        return None
    idx = sel.currentIndex()
    if not idx.isValid():
        return None
    model = view.model()
    if isinstance(model, QSortFilterProxyModel):
        src_idx = model.mapToSource(model.index(idx.row(), 0))
        return model.sourceModel().data(src_idx, Qt.ItemDataRole.UserRole)
    return model.data(model.index(idx.row(), 0), Qt.ItemDataRole.UserRole)
