"""Enterprise DataTable wrapper component.

A reusable Carbon-style data table primitive built on top of ``QTableView``.
The component is presentation-only — it never imports services or
repositories and never performs persistence. It exposes a small,
disciplined API that feature pages will adopt during Phase 2.

Layout (top → bottom):

* Header strip — title, count chip, search, column chooser, density toggle.
* Toolbar — embeds a :class:`CommandBar` (lazy import — falls back to an
  empty frame if the component has not landed yet).
* Selection action band — only visible when the user has selected rows.
* Table view — ``QTableView`` named ``EnterpriseTable``.
* Empty-state overlay — visible when the proxy has zero rows.

The component does not own any business logic. Sorting and search are
implemented through an internal ``QSortFilterProxyModel`` subclass so
they stay decoupled from the underlying source model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.services.ui_preferences_service import (
    get_default_ui_preferences_service,
)
from seeker_accounting.shared.ui.accessibility import (
    describe_button,
    describe_item_view,
    set_accessible_metadata,
)
from seeker_accounting.shared.ui.keyboard_shortcuts import install_shortcut, shortcut_map

# --- Lazy / defensive imports ------------------------------------------------
# The Phase-1 token & palette work, plus the CommandBar component, are landing
# in parallel. We import them lazily so this module imports cleanly even when
# its peers have not been committed yet.

try:  # pragma: no cover - exercised indirectly
    from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS  # type: ignore

    _TOKEN_TOOLBAR_HEIGHT = getattr(
        DEFAULT_TOKENS.sizes, "data_table_toolbar_height", 36
    )
    _TOKEN_HEADER_HEIGHT = getattr(
        DEFAULT_TOKENS.sizes, "data_table_header_height", 28
    )
    _TOKEN_ROW_HEIGHT = getattr(
        DEFAULT_TOKENS.sizes,
        "data_table_row_height",
        getattr(DEFAULT_TOKENS.sizes, "row_height", 28),
    )
    _TOKEN_ROW_HEIGHT_DENSE = getattr(
        DEFAULT_TOKENS.sizes,
        "data_table_row_height_dense",
        getattr(DEFAULT_TOKENS.sizes, "row_height_dense", 22),
    )
    _TOKEN_CELL_PADDING_H = getattr(
        DEFAULT_TOKENS.sizes, "data_table_cell_padding_h", 10
    )
except Exception:  # pragma: no cover - very defensive
    _TOKEN_TOOLBAR_HEIGHT = 36
    _TOKEN_HEADER_HEIGHT = 28
    _TOKEN_ROW_HEIGHT = 28
    _TOKEN_ROW_HEIGHT_DENSE = 22
    _TOKEN_CELL_PADDING_H = 10


def _try_import_command_bar():
    """Lazy import for :class:`CommandBar`.

    Returns ``(CommandBar, CommandItem, CommandSeparator)`` or ``None`` when
    the component has not been committed yet. Allows this module to be used
    in isolation (and unit-tested) regardless of the parallel agent's
    progress.
    """

    try:  # pragma: no cover - import probing
        from seeker_accounting.shared.ui.components.command_bar import (  # type: ignore
            CommandBar,
            CommandItem,
            CommandSeparator,
        )

        return CommandBar, CommandItem, CommandSeparator
    except Exception:
        return None


# --- Public dataclasses ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DataTableColumn:
    """Declarative column descriptor for :class:`DataTable`.

    The component reads these descriptors once at construction and uses them
    for header titles, default widths, alignment, search inclusion, sortability
    and column-chooser membership.
    """

    key: str
    title: str
    width: int | None = None
    min_width: int = 60
    align: Qt.AlignmentFlag = (
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    sortable: bool = True
    visible_default: bool = True
    hideable: bool = True
    is_numeric: bool = False
    delegate_factory: Callable[[QTableView], object] | None = None


# --- Internal proxy ----------------------------------------------------------


class _DataTableProxyModel(QSortFilterProxyModel):
    """Filter/sort proxy with multi-column case-insensitive search.

    When a custom predicate is installed (``set_filter_predicate``) it takes
    priority over the default search text behaviour.
    """

    def __init__(self, columns: Sequence[DataTableColumn], parent=None) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._needle: str = ""
        self._predicate: Callable[[QAbstractItemModel, int, QModelIndex], bool] | None = None
        self._numeric_columns: set[int] = {
            i for i, col in enumerate(self._columns) if col.is_numeric
        }
        self._alignment_for_column: dict[int, Qt.AlignmentFlag] = {
            i: (
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                if col.is_numeric
                else col.align
            )
            for i, col in enumerate(self._columns)
        }
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # Visible columns track which source columns participate in search.
        self._search_columns: set[int] = {
            i for i, col in enumerate(self._columns) if col.visible_default
        }

    # -- search wiring --------------------------------------------------------

    def set_search_text(self, text: str) -> None:
        new_value = text or ""
        if new_value == self._needle:
            return
        self._needle = new_value.casefold()
        self.invalidateRowsFilter()

    def set_filter_predicate(
        self,
        predicate: Callable[[QAbstractItemModel, int, QModelIndex], bool] | None,
    ) -> None:
        self._predicate = predicate
        self.invalidateRowsFilter()

    def set_search_columns(self, source_columns: Iterable[int]) -> None:
        self._search_columns = set(source_columns)
        self.invalidateRowsFilter()

    def filterAcceptsRow(  # type: ignore[override]
        self, source_row: int, source_parent: QModelIndex
    ) -> bool:
        source_model = self.sourceModel()
        if source_model is None:
            return True
        if self._predicate is not None:
            try:
                return bool(self._predicate(source_model, source_row, source_parent))
            except Exception:
                return True
        if not self._needle:
            return True
        column_count = source_model.columnCount(source_parent)
        candidates = (
            self._search_columns
            if self._search_columns
            else range(column_count)
        )
        for col in candidates:
            if col < 0 or col >= column_count:
                continue
            idx = source_model.index(source_row, col, source_parent)
            value = source_model.data(idx, Qt.ItemDataRole.DisplayRole)
            if value is None:
                continue
            if self._needle in str(value).casefold():
                return True
        return False

    # -- alignment hint -------------------------------------------------------

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            col = index.column()
            if col in self._alignment_for_column:
                return int(self._alignment_for_column[col])
        return super().data(index, role)


# --- Public component --------------------------------------------------------


class DataTable(QWidget):
    """Carbon-style data table with toolbar, search, density and column chooser.

    The component never reaches into services or repositories. Pages drive
    it by setting a model and reacting to its high-level signals.
    """

    selection_changed = Signal(list)
    row_activated = Signal(int)
    search_text_changed = Signal(str)
    density_changed = Signal(str)
    command_activated = Signal(str)
    command_toggled = Signal(str, bool)

    _SEARCH_DEBOUNCE_MS = 200

    def __init__(
        self,
        *,
        columns: Sequence[DataTableColumn],
        title: str = "",
        toolbar_commands: Sequence[Any] = (),
        selection_mode: str = "extended",
        density: str | None = None,
        show_search: bool = True,
        show_count: bool = True,
        show_density_toggle: bool = True,
        show_column_chooser: bool = True,
        empty_state_text: str = "No records to display.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if not columns:
            raise ValueError("DataTable requires at least one column.")
        self._columns: list[DataTableColumn] = list(columns)
        self._title_text = title
        self._density: str = ""
        self._empty_state_text = empty_state_text
        self._command_bar = None  # type: ignore[assignment]
        self._command_bar_factory = _try_import_command_bar()
        self._explicit_count: int | None = None
        self._persist_density = show_density_toggle
        self._ui_preferences = get_default_ui_preferences_service()
        initial_density = density or (
            self._ui_preferences.get_table_density()
            if show_density_toggle
            else "comfortable"
        )

        self._proxy = _DataTableProxyModel(self._columns, self)

        self._build_layout(
            show_search=show_search,
            show_count=show_count,
            show_density_toggle=show_density_toggle,
            show_column_chooser=show_column_chooser,
            toolbar_commands=toolbar_commands,
        )
        self._configure_view(selection_mode=selection_mode)
        self._wire_signals()

        self.set_density(initial_density, persist=False)
        self._refresh_count_label()
        self._update_empty_state()

    # -- construction helpers -------------------------------------------------

    def _build_layout(
        self,
        *,
        show_search: bool,
        show_count: bool,
        show_density_toggle: bool,
        show_column_chooser: bool,
        toolbar_commands: Sequence[Any],
    ) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- header strip ---------------------------------------------------
        self._header_strip = QFrame(self)
        self._header_strip.setObjectName("DataTableHeaderStrip")
        self._header_strip.setFixedHeight(_TOKEN_HEADER_HEIGHT + 4)
        header_layout = QHBoxLayout(self._header_strip)
        header_layout.setContentsMargins(8, 2, 8, 2)
        header_layout.setSpacing(8)

        self._title_label = QLabel(self._title_text, self._header_strip)
        self._title_label.setObjectName("DataTableTitle")
        font = self._title_label.font()
        font.setWeight(font.Weight.DemiBold)
        self._title_label.setFont(font)
        if not self._title_text:
            self._title_label.setVisible(False)
        header_layout.addWidget(self._title_label)

        self._count_label = QLabel("", self._header_strip)
        self._count_label.setObjectName("DataTableCountChip")
        self._show_count = show_count
        self._count_label.setVisible(show_count)
        header_layout.addWidget(self._count_label)
        header_layout.addStretch(1)

        self._search_edit = QLineEdit(self._header_strip)
        self._search_edit.setObjectName("DataTableSearchEdit")
        self._search_edit.setPlaceholderText("Search…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setMinimumWidth(200)
        self._search_edit.setVisible(show_search)
        set_accessible_metadata(self._search_edit, "Table search", "Search visible table rows.")
        header_layout.addWidget(self._search_edit)

        self._column_chooser_button = QToolButton(self._header_strip)
        self._column_chooser_button.setObjectName("DataTableColumnChooser")
        self._column_chooser_button.setText("Columns ▾")
        self._column_chooser_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self._column_chooser_button.setVisible(show_column_chooser)
        self._column_chooser_menu = QMenu(self._column_chooser_button)
        self._column_chooser_button.setMenu(self._column_chooser_menu)
        describe_button(
            self._column_chooser_button,
            "Choose table columns",
            "Show or hide optional columns in this table.",
        )
        self._column_actions: dict[str, QAction] = {}
        for index, col in enumerate(self._columns):
            if not col.hideable:
                continue
            action = QAction(col.title, self._column_chooser_menu)
            action.setCheckable(True)
            action.setChecked(col.visible_default)
            action.toggled.connect(
                lambda checked, key=col.key: self.set_column_visible(key, checked)
            )
            self._column_chooser_menu.addAction(action)
            self._column_actions[col.key] = action
        header_layout.addWidget(self._column_chooser_button)

        self._density_button = QToolButton(self._header_strip)
        self._density_button.setObjectName("DataTableDensityToggle")
        self._density_button.setCheckable(True)
        self._density_button.setText("Comfortable")
        self._density_button.setVisible(show_density_toggle)
        describe_button(
            self._density_button,
            "Toggle table density",
            "Switch between comfortable and dense table rows.",
        )
        header_layout.addWidget(self._density_button)

        outer.addWidget(self._header_strip)

        # ---- toolbar --------------------------------------------------------
        self._toolbar_host = QFrame(self)
        self._toolbar_host.setObjectName("DataTableToolbar")
        self._toolbar_host.setFixedHeight(_TOKEN_TOOLBAR_HEIGHT)
        toolbar_layout = QHBoxLayout(self._toolbar_host)
        toolbar_layout.setContentsMargins(4, 2, 4, 2)
        toolbar_layout.setSpacing(4)
        if self._command_bar_factory is not None:
            CommandBar, _, _ = self._command_bar_factory
            try:
                self._command_bar = CommandBar(parent=self._toolbar_host)
                if toolbar_commands:
                    if hasattr(self._command_bar, "set_commands"):
                        self._command_bar.set_commands(list(toolbar_commands))
                    elif hasattr(self._command_bar, "set_items"):
                        self._command_bar.set_items(list(toolbar_commands))
                toolbar_layout.addWidget(self._command_bar, 1)
            except Exception:
                self._command_bar = None
        if self._command_bar is None:
            # Fallback: invisible spacer so layout heights stay stable.
            placeholder = QWidget(self._toolbar_host)
            placeholder.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            toolbar_layout.addWidget(placeholder, 1)
            self._toolbar_host.setVisible(bool(toolbar_commands))

        outer.addWidget(self._toolbar_host)

        # ---- selection action bar ------------------------------------------
        self._selection_bar = QFrame(self)
        self._selection_bar.setObjectName("DataTableSelectionBar")
        self._selection_bar.setVisible(False)
        sel_layout = QHBoxLayout(self._selection_bar)
        sel_layout.setContentsMargins(8, 2, 8, 2)
        sel_layout.setSpacing(8)
        self._selection_count_label = QLabel("", self._selection_bar)
        self._selection_count_label.setObjectName("DataTableSelectionCount")
        sel_layout.addWidget(self._selection_count_label)
        self._selection_actions_host = QWidget(self._selection_bar)
        sel_actions_layout = QHBoxLayout(self._selection_actions_host)
        sel_actions_layout.setContentsMargins(0, 0, 0, 0)
        sel_actions_layout.setSpacing(4)
        sel_layout.addWidget(self._selection_actions_host)
        sel_layout.addStretch(1)
        self._selection_clear_button = QPushButton("Clear", self._selection_bar)
        self._selection_clear_button.setObjectName("DataTableSelectionClear")
        self._selection_clear_button.clicked.connect(self.clear_selection)
        sel_layout.addWidget(self._selection_clear_button)
        outer.addWidget(self._selection_bar)

        # ---- table view -----------------------------------------------------
        self._view = QTableView(self)
        self._view.setObjectName("EnterpriseTable")
        self._view.setModel(self._proxy)
        describe_item_view(
            self._view,
            self._title_text or "Data table",
            "Sortable table. Use arrow keys to move between rows.",
        )
        outer.addWidget(self._view, 1)

        # ---- empty-state overlay (parented to viewport) --------------------
        self._empty_label = QLabel(self._empty_state_text, self._view.viewport())
        self._empty_label.setObjectName("DataTableEmptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setVisible(False)
        self._view.viewport().installEventFilter(self)

    def _configure_view(self, *, selection_mode: str) -> None:
        view = self._view
        view.setAlternatingRowColors(True)
        view.setShowGrid(False)
        view.setSortingEnabled(True)
        view.setWordWrap(False)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        mode_map = {
            "single": QAbstractItemView.SelectionMode.SingleSelection,
            "extended": QAbstractItemView.SelectionMode.ExtendedSelection,
            "none": QAbstractItemView.SelectionMode.NoSelection,
        }
        view.setSelectionMode(
            mode_map.get(selection_mode, QAbstractItemView.SelectionMode.ExtendedSelection)
        )
        view.verticalHeader().setVisible(False)

        header = view.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def _wire_signals(self) -> None:
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self._SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._emit_search_change)
        self._search_edit.textChanged.connect(self._on_search_typed)

        self._density_button.toggled.connect(self._on_density_toggled)

        self._proxy.rowsInserted.connect(self._on_rows_changed)
        self._proxy.rowsRemoved.connect(self._on_rows_changed)
        self._proxy.modelReset.connect(self._on_rows_changed)
        self._proxy.layoutChanged.connect(self._on_rows_changed)

        self._view.doubleClicked.connect(self._on_double_clicked)
        sel_model = self._view.selectionModel()
        if sel_model is not None:
            sel_model.selectionChanged.connect(self._on_selection_changed)

        if self._command_bar is not None:
            for sig_name, target in (
                ("command_activated", self.command_activated),
                ("command_toggled", self.command_toggled),
            ):
                signal = getattr(self._command_bar, sig_name, None)
                if signal is not None:
                    try:
                        signal.connect(target)
                    except Exception:
                        pass
        shortcuts = shortcut_map("table")
        if self._persist_density and (toggle_density := shortcuts.get("toggle_density")):
            install_shortcut(
                self,
                toggle_density,
                lambda: self.set_density(
                    "comfortable" if self._density == "dense" else "dense"
                ),
            )
        if clear_selection := shortcuts.get("clear_selection"):
            install_shortcut(self, clear_selection, self.clear_selection)

    # -- public API: model ----------------------------------------------------

    def set_model(self, model: QAbstractItemModel) -> None:
        """Install a source model. Sorting and filtering remain in the proxy."""

        self._proxy.setSourceModel(model)
        # Re-bind the selection model after the view rebinds it.
        sel_model = self._view.selectionModel()
        if sel_model is not None:
            try:
                sel_model.selectionChanged.disconnect(self._on_selection_changed)
            except (TypeError, RuntimeError):
                pass
            sel_model.selectionChanged.connect(self._on_selection_changed)
        # Apply default visibility from descriptors.
        for index, col in enumerate(self._columns):
            self._view.setColumnHidden(index, not col.visible_default)
            if col.width is not None:
                self._view.setColumnWidth(index, col.width)
            if col.delegate_factory is not None:
                try:
                    delegate = col.delegate_factory(self._view)
                    if delegate is not None:
                        self._view.setItemDelegateForColumn(index, delegate)
                except Exception:
                    pass
            if not col.sortable:
                # No direct Qt switch per-section; we rely on header behaviour
                # being uniform. Descriptor remains advisory for now.
                pass
        self._refresh_count_label()
        self._update_empty_state()

    def model(self) -> QAbstractItemModel | None:
        return self._proxy.sourceModel()

    def view(self) -> QTableView:
        return self._view

    # -- public API: selection ------------------------------------------------

    def selected_rows(self) -> list[int]:
        sel_model = self._view.selectionModel()
        if sel_model is None:
            return []
        rows: set[int] = set()
        for proxy_index in sel_model.selectedRows():
            source_index = self._proxy.mapToSource(proxy_index)
            if source_index.isValid():
                rows.add(source_index.row())
        return sorted(rows)

    def clear_selection(self) -> None:
        sel_model = self._view.selectionModel()
        if sel_model is not None:
            sel_model.clearSelection()

    # -- public API: toolbar / commands --------------------------------------

    def command_bar(self):
        return self._command_bar

    def set_toolbar_commands(self, items: Sequence[Any]) -> None:
        if self._command_bar is None:
            self._toolbar_host.setVisible(bool(items))
            return
        for method_name in ("set_commands", "set_items"):
            method = getattr(self._command_bar, method_name, None)
            if method is not None:
                method(list(items))
                self._toolbar_host.setVisible(True)
                return

    def set_command_enablement(self, state: Mapping[str, bool]) -> None:
        if self._command_bar is None:
            return
        method = getattr(self._command_bar, "set_command_enablement", None)
        if method is not None:
            method(dict(state))
            return
        method = getattr(self._command_bar, "set_enablement", None)
        if method is not None:
            method(dict(state))

    def set_selection_actions(self, items: Sequence[Any]) -> None:
        """Phase-1 stub. Keeps API surface stable for later wiring."""

        layout = self._selection_actions_host.layout()
        if layout is None:
            return
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget() if child is not None else None
            if widget is not None:
                widget.deleteLater()
        # Placeholder: items are accepted but rendering is deferred until a
        # later slice introduces selection-action rendering.
        for item in items or ():
            label = getattr(item, "label", None) or str(item)
            button = QPushButton(label, self._selection_actions_host)
            layout.addWidget(button)

    # -- public API: density / search / count --------------------------------

    def set_density(self, density: str, *, persist: bool = True) -> None:
        if density not in ("comfortable", "dense"):
            raise ValueError(
                f"Unknown density {density!r}; expected 'comfortable' or 'dense'."
            )
        if density == self._density:
            return
        self._density = density
        row_height = (
            _TOKEN_ROW_HEIGHT_DENSE if density == "dense" else _TOKEN_ROW_HEIGHT
        )
        vh = self._view.verticalHeader()
        vh.setMinimumSectionSize(row_height)
        vh.setDefaultSectionSize(row_height)
        # Sync toggle UI without recursion.
        was_blocked = self._density_button.blockSignals(True)
        try:
            self._density_button.setChecked(density == "dense")
            self._density_button.setText(
                "Compact" if density == "dense" else "Comfortable"
            )
        finally:
            self._density_button.blockSignals(was_blocked)
        if persist and self._persist_density:
            self._ui_preferences.set_table_density(density)
        self.density_changed.emit(density)

    def density(self) -> str:
        return self._density

    def set_search_text(self, text: str) -> None:
        was_blocked = self._search_edit.blockSignals(True)
        try:
            self._search_edit.setText(text or "")
        finally:
            self._search_edit.blockSignals(was_blocked)
        self._proxy.set_search_text(text or "")
        self._refresh_count_label()
        self._update_empty_state()
        self.search_text_changed.emit(text or "")

    def set_count(self, count: int | None = None) -> None:
        self._explicit_count = count
        self._refresh_count_label()

    # -- public API: column visibility ---------------------------------------

    def set_column_visible(self, key: str, visible: bool) -> None:
        for index, col in enumerate(self._columns):
            if col.key != key:
                continue
            self._view.setColumnHidden(index, not visible)
            action = self._column_actions.get(key)
            if action is not None and action.isChecked() != visible:
                was_blocked = action.blockSignals(True)
                try:
                    action.setChecked(visible)
                finally:
                    action.blockSignals(was_blocked)
            # Update search inclusion to match visible columns.
            visible_indices = [
                i for i, c in enumerate(self._columns)
                if not self._view.isColumnHidden(i)
            ]
            self._proxy.set_search_columns(visible_indices)
            return

    def visible_columns(self) -> list[str]:
        return [
            col.key
            for index, col in enumerate(self._columns)
            if not self._view.isColumnHidden(index)
        ]

    # -- internal handlers ----------------------------------------------------

    def _on_search_typed(self, _text: str) -> None:
        self._search_timer.start()

    def _emit_search_change(self) -> None:
        text = self._search_edit.text()
        self._proxy.set_search_text(text)
        self._refresh_count_label()
        self._update_empty_state()
        self.search_text_changed.emit(text)

    def _on_density_toggled(self, checked: bool) -> None:
        self.set_density("dense" if checked else "comfortable")

    def _on_rows_changed(self, *_args) -> None:
        self._refresh_count_label()
        self._update_empty_state()

    def _on_double_clicked(self, proxy_index: QModelIndex) -> None:
        source_index = self._proxy.mapToSource(proxy_index)
        if source_index.isValid():
            self.row_activated.emit(source_index.row())

    def _on_selection_changed(self, *_args) -> None:
        rows = self.selected_rows()
        count = len(rows)
        self._selection_bar.setVisible(count > 0)
        if count > 0:
            self._selection_count_label.setText(
                f"{count} selected" if count != 1 else "1 selected"
            )
        self.selection_changed.emit(rows)

    def _refresh_count_label(self) -> None:
        if not self._show_count:
            return
        if self._explicit_count is not None:
            count = self._explicit_count
        else:
            count = self._proxy.rowCount()
        noun = "record" if count == 1 else "records"
        self._count_label.setText(f"{count} {noun}")

    def _update_empty_state(self) -> None:
        is_empty = self._proxy.rowCount() == 0
        self._empty_label.setVisible(is_empty)
        if is_empty:
            self._reposition_empty_label()

    def _reposition_empty_label(self) -> None:
        viewport = self._view.viewport()
        if viewport is None:
            return
        self._empty_label.setGeometry(viewport.rect())

    # -- QObject overrides ----------------------------------------------------

    def eventFilter(self, watched, event):  # type: ignore[override]
        if watched is self._view.viewport():
            from PySide6.QtCore import QEvent

            if event.type() == QEvent.Type.Resize:
                self._reposition_empty_label()
        return super().eventFilter(watched, event)
