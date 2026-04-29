"""Step 2 — Surface unposted draft journal entries for the period.

Closing a period with drafts isn't blocked by the period_control_service,
but it's almost always a mistake. The wizard surfaces drafts and requires
explicit acknowledgement before allowing the close.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.month_end_close import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class DraftsCheckStep(WizardStep):
    key = "drafts_check"
    title = "Unposted Drafts"
    subtitle = "Review drafts that fall in the selected period."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._summary: QLabel | None = None
        self._ack: QCheckBox | None = None
        self._draft_count = 0

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._summary = QLabel("Loading drafts…", root)
        self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")
        outer.addWidget(self._summary)

        self._table = QTableWidget(0, 4, root)
        self._table.setHorizontalHeaderLabels(["Entry #", "Date", "Reference", "Amount"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self._table, 1)

        self._ack = QCheckBox(
            "I understand drafts in this period will not be posted by closing.",
            root,
        )
        outer.addWidget(self._ack)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None or self._summary is None or self._ack is None:
            return
        company_id = context.require_company_id()
        period_id = state.get(K.KEY_PERIOD_ID)
        service = context.service_registry.journal_service
        try:
            entries = service.list_journal_entries(company_id, status_code="DRAFT")
        except Exception:  # noqa: BLE001
            entries = []

        # Filter to selected period.
        scoped = [e for e in entries if e.fiscal_period_id == period_id]
        self._draft_count = len(scoped)

        self._table.setRowCount(len(scoped))
        for row, entry in enumerate(scoped):
            self._table.setItem(row, 0, QTableWidgetItem(entry.entry_number or "(unnumbered)"))
            self._table.setItem(row, 1, QTableWidgetItem(entry.entry_date.isoformat()))
            self._table.setItem(row, 2, QTableWidgetItem(entry.reference_text or entry.description or ""))
            amount_item = QTableWidgetItem(f"{entry.total_debit:,.2f}")
            amount_item.setTextAlignment(0x0002 | 0x0080)  # Qt.AlignmentFlag.AlignRight | AlignVCenter
            self._table.setItem(row, 3, amount_item)

        if self._draft_count == 0:
            self._summary.setText("No unposted drafts in this period.")
            self._ack.setChecked(True)
            self._ack.setVisible(False)
        else:
            self._summary.setText(
                f"{self._draft_count} draft journal entr"
                f"{'y' if self._draft_count == 1 else 'ies'} in this period — review or post before closing."
            )
            self._ack.setVisible(True)
            self._ack.setChecked(bool(state.get(K.KEY_DRAFTS_ACKNOWLEDGED)))

        state[K.KEY_DRAFTS_COUNT] = self._draft_count
        state[K.KEY_DRAFTS_FOR_PERIOD] = [e.id for e in scoped]

    def write_back(self, state: WizardState) -> None:
        if self._ack is not None:
            state[K.KEY_DRAFTS_ACKNOWLEDGED] = bool(self._ack.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if self._draft_count > 0 and not state.get(K.KEY_DRAFTS_ACKNOWLEDGED):
            return StepValidationResult.fail(
                "Acknowledge the unposted drafts before continuing."
            )
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        n = state.get(K.KEY_DRAFTS_COUNT, 0)
        if n == 0:
            return "No unposted drafts in the selected period."
        return f"{n} unposted draft(s) will remain after close."
