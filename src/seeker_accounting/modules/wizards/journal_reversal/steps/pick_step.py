"""Step 1 — Pick the posted journal entry to reverse."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.wizards.journal_reversal import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="entry_number", title="Entry #", min_width=100),
    DataTableColumn(key="entry_date", title="Date", min_width=100),
    DataTableColumn(key="type", title="Type", min_width=120),
    DataTableColumn(key="description", title="Description", min_width=240),
    DataTableColumn(key="total", title="Total", is_numeric=True, min_width=110),
    DataTableColumn(key="posted_at", title="Posted at", min_width=140),
)


class PickJournalStep(WizardStep):
    key = "pick"
    title = "Choose journal entry"
    subtitle = "Pick the posted journal entry you want to reverse."

    def __init__(self) -> None:
        super().__init__()
        self._table: DataTable | None = None
        self._model: QStandardItemModel | None = None
        self._rows: list[dict] = []
        self._loaded = False

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return item

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        info = QLabel(
            "Only POSTED entries are listed. Reversal entries are excluded.", root
        )
        info.setWordWrap(True)
        outer.addWidget(info)

        self._model = QStandardItemModel(0, len(_COLUMNS), root)
        self._model.setHorizontalHeaderLabels([c.title for c in _COLUMNS])
        self._table = DataTable(
            columns=_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=root,
        )
        self._table.set_model(self._model)
        self._table.selection_changed.connect(self._on_selection_changed)
        outer.addWidget(self._table, 1)
        return root

    def _on_selection_changed(self, _rows: list[int]) -> None:
        # Selection drives validate(); state is refreshed live so the wizard
        # shell can re-evaluate the Next button on each click.
        # write_back() will be called by the shell before validate() anyway,
        # but emitting an immediate refresh keeps UX consistent.
        return

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._loaded:
            return
        self._populate(context, state)
        self._loaded = True

    def _populate(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None or self._model is None:
            return
        company_id = context.require_company_id()
        try:
            entries = context.service_registry.journal_service.list_journal_entries(
                company_id, status_code="POSTED"
            )
        except Exception:
            entries = []
        # Filter out reversal entries (already-reversal type) so user can't
        # reverse a reversal.
        entries = [e for e in entries if (e.journal_type_code or "").upper() != "JOURNAL_REVERSAL"]
        self._model.removeRows(0, self._model.rowCount())
        self._rows = []
        preselect_id = state.get(K.KEY_SOURCE_JE_ID)
        preselect_source_row = -1
        for entry in entries:
            r = self._model.rowCount()
            self._model.appendRow([
                self._make_item(entry.entry_number or ""),
                self._make_item(str(entry.entry_date)),
                self._make_item(entry.journal_type_code or ""),
                self._make_item(entry.description or entry.reference_text or ""),
                self._make_numeric(entry.total_debit),
                self._make_item(str(entry.posted_at) if entry.posted_at else ""),
            ])
            self._rows.append(
                {
                    "id": int(entry.id),
                    "entry_number": entry.entry_number,
                    "entry_date": entry.entry_date,
                    "description": entry.description or entry.reference_text or "",
                    "total": entry.total_debit,
                }
            )
            if preselect_id == int(entry.id):
                preselect_source_row = r
        if preselect_source_row >= 0:
            self._restore_selection(preselect_source_row)

    def _restore_selection(self, source_row: int) -> None:
        if self._table is None or self._model is None:
            return
        proxy = self._table.view().model()
        if proxy is None:
            return
        source_index = self._model.index(source_row, 0)
        proxy_index = proxy.mapFromSource(source_index)
        if proxy_index.isValid():
            self._table.view().selectRow(proxy_index.row())

    def write_back(self, state: WizardState) -> None:
        if self._table is None:
            state[K.KEY_SOURCE_JE_ID] = None
            return
        rows = self._table.selected_rows()
        if not rows:
            state[K.KEY_SOURCE_JE_ID] = None
            return
        idx = rows[0]
        if idx < 0 or idx >= len(self._rows):
            state[K.KEY_SOURCE_JE_ID] = None
            return
        meta = self._rows[idx]
        state[K.KEY_SOURCE_JE_ID] = meta["id"]
        state[K.KEY_SOURCE_ENTRY_NUMBER] = meta["entry_number"]
        state[K.KEY_SOURCE_ENTRY_DATE] = meta["entry_date"]
        state[K.KEY_SOURCE_DESCRIPTION] = meta["description"]
        state[K.KEY_SOURCE_TOTAL] = meta["total"]

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_SOURCE_JE_ID):
            return StepValidationResult.fail("Select a journal entry to reverse.")
        return StepValidationResult.ok()
