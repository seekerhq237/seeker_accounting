"""Step 2 — Period review: ensure all periods are CLOSED/LOCKED, optionally lock CLOSED ones."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.wizards.year_end_close import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)


_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="period", title="Period", min_width=100),
    DataTableColumn(key="date_range", title="Date range", min_width=240),
    DataTableColumn(key="status", title="Status", min_width=110),
)


class PeriodsReviewStep(WizardStep):
    key = "periods_review"
    title = "Review periods"
    subtitle = "All periods must be CLOSED or LOCKED."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._table: DataTable | None = None
        self._model: QStandardItemModel | None = None
        self._status_delegate = None
        self._lock_checkbox: QCheckBox | None = None
        self._summary: QLabel | None = None
        self._result: QLabel | None = None

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

        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        outer.addWidget(self._summary)

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
        self._status_delegate = apply_status_chip_to_column(
            self._table.view(), 2
        )
        outer.addWidget(self._table, 1)

        self._lock_checkbox = QCheckBox(
            "Lock all CLOSED periods before closing the year (recommended).", root
        )
        self._lock_checkbox.setChecked(True)
        outer.addWidget(self._lock_checkbox)

        self._result = QLabel(root)
        self._result.setObjectName("WizardSuccessText")
        outer.addWidget(self._result)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        fy_id = state.get(K.KEY_FISCAL_YEAR_ID)
        if not isinstance(fy_id, int):
            return
        try:
            periods = context.service_registry.fiscal_calendar_service.list_periods(
                company_id, fiscal_year_id=fy_id
            )
        except Exception:
            periods = []
        snapshot = [
            {
                "id": int(p.id),
                "period_code": str(p.period_code),
                "start_date": str(p.start_date),
                "end_date": str(p.end_date),
                "status_code": str(p.status_code),
            }
            for p in periods
        ]
        state[K.KEY_PERIODS_SNAPSHOT] = snapshot
        if self._model is not None:
            self._model.removeRows(0, self._model.rowCount())
            for p in snapshot:
                self._model.appendRow([
                    self._make_item(p["period_code"]),
                    self._make_item(f"{p['start_date']} → {p['end_date']}"),
                    self._make_item(p["status_code"]),
                ])
        open_count = sum(1 for p in snapshot if p["status_code"] == "OPEN")
        closed_count = sum(1 for p in snapshot if p["status_code"] == "CLOSED")
        locked_count = sum(1 for p in snapshot if p["status_code"] == "LOCKED")
        if self._summary is not None:
            self._summary.setText(
                f"{len(snapshot)} period(s): {open_count} OPEN, {closed_count} CLOSED, "
                f"{locked_count} LOCKED."
            )
        if self._lock_checkbox is not None:
            self._lock_checkbox.setChecked(
                bool(state.get(K.KEY_LOCK_CLOSED_PERIODS, True))
            )
        if self._result is not None and state.get(K.KEY_PERIODS_LOCKED_AT_COMMIT):
            self._result.setText(
                f"Locked {state.get(K.KEY_PERIODS_LOCKED_COUNT) or 0} period(s)."
            )

    def write_back(self, state: WizardState) -> None:
        if self._lock_checkbox is not None:
            state[K.KEY_LOCK_CLOSED_PERIODS] = bool(self._lock_checkbox.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        snapshot = state.get(K.KEY_PERIODS_SNAPSHOT) or []
        if not snapshot:
            return StepValidationResult.fail("No periods exist for this fiscal year.")
        # If user does not want to lock, then any OPEN status blocks advance.
        if not state.get(K.KEY_LOCK_CLOSED_PERIODS, True):
            still_open = [p for p in snapshot if p["status_code"] == "OPEN"]
            if still_open:
                codes = ", ".join(p["period_code"] for p in still_open)
                return StepValidationResult.fail(
                    f"Close these periods before continuing: {codes}."
                )
        else:
            # Even with lock-all-closed enabled, any OPEN blocks: this wizard does not close
            # OPEN periods (period_control_service.lock_period requires CLOSED status first).
            still_open = [p for p in snapshot if p["status_code"] == "OPEN"]
            if still_open:
                codes = ", ".join(p["period_code"] for p in still_open)
                return StepValidationResult.fail(
                    f"Close these periods first (lock cannot be applied to OPEN periods): {codes}."
                )
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_PERIODS_LOCKED_AT_COMMIT):
            return
        if not state.get(K.KEY_LOCK_CLOSED_PERIODS, True):
            state[K.KEY_PERIODS_LOCKED_COUNT] = 0
            state[K.KEY_PERIODS_LOCKED_AT_COMMIT] = True
            return
        company_id = context.require_company_id()
        snapshot = state.get(K.KEY_PERIODS_SNAPSHOT) or []
        locked = 0
        sr = context.service_registry
        for p in snapshot:
            if p.get("status_code") != "CLOSED":
                continue
            try:
                sr.period_control_service.lock_period(
                    company_id, int(p["id"]), context.user_id
                )
                locked += 1
            except Exception:
                # Continue; report at end.
                continue
        state[K.KEY_PERIODS_LOCKED_COUNT] = locked
        state[K.KEY_PERIODS_LOCKED_AT_COMMIT] = True

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        snap = state.get(K.KEY_PERIODS_SNAPSHOT) or []
        return f"{len(snap)} period(s)" if snap else None
