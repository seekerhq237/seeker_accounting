"""Step 1 — Pick the posted journal entry to reverse."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.journal_reversal import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_HEADERS = ("Entry #", "Date", "Type", "Description", "Total", "Posted at")


class PickJournalStep(WizardStep):
    key = "pick"
    title = "Choose journal entry"
    subtitle = "Pick the posted journal entry you want to reverse."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._rows: list[dict] = []
        self._loaded = False

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

        self._table = QTableWidget(0, len(_HEADERS), root)
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for col in (0, 1, 2, 4, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self._table, 1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._loaded:
            return
        self._populate(context, state)
        self._loaded = True

    def _populate(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None:
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
        self._table.setRowCount(0)
        self._rows = []
        preselect_id = state.get(K.KEY_SOURCE_JE_ID)
        preselect_row = -1
        for entry in entries:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, _ro(entry.entry_number or ""))
            self._table.setItem(r, 1, _ro(str(entry.entry_date)))
            self._table.setItem(r, 2, _ro(entry.journal_type_code or ""))
            self._table.setItem(r, 3, _ro(entry.description or entry.reference_text or ""))
            self._table.setItem(r, 4, _ro_num(str(entry.total_debit)))
            self._table.setItem(r, 5, _ro(str(entry.posted_at) if entry.posted_at else ""))
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
                preselect_row = r
        if preselect_row >= 0:
            self._table.selectRow(preselect_row)

    def write_back(self, state: WizardState) -> None:
        if self._table is None:
            return
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            state[K.KEY_SOURCE_JE_ID] = None
            return
        idx = rows[0].row()
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


def _ro(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _ro_num(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
    return item
