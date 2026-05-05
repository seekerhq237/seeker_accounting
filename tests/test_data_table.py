"""Smoke tests for the enterprise :class:`DataTable` component."""

from __future__ import annotations

import os

# Force offscreen platform before importing Qt-bound modules. Tests run in
# headless CI without an X server / Windows display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication

from seeker_accounting.shared.ui.components.data_table import (
    DataTable,
    DataTableColumn,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


def _build_model(rows: int = 10) -> QStandardItemModel:
    model = QStandardItemModel(rows, 3)
    model.setHorizontalHeaderLabels(["Code", "Name", "Status"])
    for r in range(rows):
        model.setItem(r, 0, QStandardItem(f"P{r:03d}"))
        model.setItem(r, 1, QStandardItem(f"Project {r}"))
        model.setItem(r, 2, QStandardItem("Active" if r % 2 == 0 else "Closed"))
    return model


def _columns() -> list[DataTableColumn]:
    return [
        DataTableColumn(key="Code", title="Code", width=120),
        DataTableColumn(key="Name", title="Name", width=240),
        DataTableColumn(key="Status", title="Status", width=120, hideable=True),
    ]


def test_count_chip_reflects_model_row_count(qapp: QApplication) -> None:
    table = DataTable(columns=_columns(), title="Projects")
    table.set_model(_build_model(10))
    assert "10" in table._count_label.text()


def test_search_filters_rows(qapp: QApplication) -> None:
    table = DataTable(columns=_columns())
    table.set_model(_build_model(10))
    table.set_search_text("P002")
    assert table._proxy.rowCount() == 1
    table.set_search_text("")
    assert table._proxy.rowCount() == 10


def test_density_toggle_changes_row_height(qapp: QApplication) -> None:
    table = DataTable(columns=_columns(), density="comfortable")
    table.set_model(_build_model(3))
    comfortable_height = table.view().verticalHeader().defaultSectionSize()
    table.set_density("dense")
    dense_height = table.view().verticalHeader().defaultSectionSize()
    assert dense_height < comfortable_height
    # Internal token alignment: dense path drives the dense token value.
    from seeker_accounting.shared.ui.components import data_table as dt_module

    assert dense_height == dt_module._TOKEN_ROW_HEIGHT_DENSE


def test_column_chooser_hides_column(qapp: QApplication) -> None:
    table = DataTable(columns=_columns())
    table.set_model(_build_model(5))
    assert "Name" in table.visible_columns()
    table.set_column_visible("Name", False)
    assert "Name" not in table.visible_columns()
    # And the underlying view actually hides the column.
    name_index = next(
        i for i, c in enumerate(table._columns) if c.key == "Name"
    )
    assert table.view().isColumnHidden(name_index)


def test_selection_emits_source_row_indices(qapp: QApplication) -> None:
    table = DataTable(columns=_columns())
    model = _build_model(5)
    table.set_model(model)

    received: list[list[int]] = []
    table.selection_changed.connect(received.append)

    proxy = table._proxy
    sel_model = table.view().selectionModel()
    assert sel_model is not None

    # Select rows 0 and 2 in source -> map through proxy.
    from PySide6.QtCore import QItemSelection, QItemSelectionModel

    sel_model.clearSelection()
    selection = QItemSelection()
    for source_row in (0, 2):
        proxy_index = proxy.mapFromSource(model.index(source_row, 0))
        # Build a row range across all columns.
        last_proxy_index = proxy.mapFromSource(
            model.index(source_row, model.columnCount() - 1)
        )
        selection.select(proxy_index, last_proxy_index)
    sel_model.select(
        selection,
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows,
    )

    assert table.selected_rows() == [0, 2]
    assert received, "selection_changed should have fired at least once"
    assert received[-1] == [0, 2]


def test_empty_model_shows_empty_state(qapp: QApplication) -> None:
    table = DataTable(columns=_columns(), empty_state_text="Nothing here.")
    table.set_model(QStandardItemModel(0, 3))
    # Qt's isVisible() requires a shown ancestor chain; isHidden() reflects
    # the explicit show/hide state we control internally.
    assert table._empty_label.isHidden() is False
    assert table._empty_label.text() == "Nothing here."

    # And once rows arrive, the empty-state label is hidden again.
    table.set_model(_build_model(2))
    assert table._empty_label.isHidden() is True
