"""Step 4 — Post the approved payroll run to the GL."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.payroll.dto.payroll_posting_dto import PostPayrollRunCommand
from seeker_accounting.modules.wizards.payroll_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class PostStep(WizardStep):
    key = "post"
    title = "Post"
    subtitle = "Post the approved run to the General Ledger."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._posting_date: QDateEdit | None = None
        self._narration: QLineEdit | None = None
        self._confirm: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._summary = QLabel("", root)
        self._summary.setWordWrap(True)
        self._summary.setObjectName("WizardBodyText")
        outer.addWidget(self._summary)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        today = date.today()
        self._posting_date = QDateEdit(root)
        self._posting_date.setCalendarPopup(True)
        self._posting_date.setDisplayFormat("yyyy-MM-dd")
        self._posting_date.setDate(QDate(today.year, today.month, today.day))
        form.addRow(QLabel("Posting date:", root), self._posting_date)

        self._narration = QLineEdit(root)
        self._narration.setPlaceholderText("Optional GL narration")
        form.addRow(QLabel("Narration:", root), self._narration)
        outer.addLayout(form)

        self._confirm = QCheckBox("I confirm the run should be posted.", root)
        outer.addWidget(self._confirm)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            ref = state.get(K.KEY_RUN_REFERENCE) or "(unknown)"
            net = state.get(K.KEY_TOTAL_NET) or "0"
            cur = state.get(K.KEY_CURRENCY_CODE) or ""
            self._summary.setText(
                f"About to post run {ref} (net {net} {cur}). Posting creates one "
                "balanced journal entry on the chosen date."
            )
        if self._posting_date is not None:
            run_date_raw = state.get(K.KEY_POSTING_DATE) or state.get(K.KEY_RUN_DATE)
            if run_date_raw:
                try:
                    d = date.fromisoformat(str(run_date_raw))
                    self._posting_date.setDate(QDate(d.year, d.month, d.day))
                except ValueError:
                    pass
        if self._narration is not None and state.get(K.KEY_POSTING_NARRATION):
            self._narration.setText(str(state[K.KEY_POSTING_NARRATION]))
        if self._confirm is not None:
            already_posted = bool(state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID))
            self._confirm.setChecked(already_posted)

    def write_back(self, state: WizardState) -> None:
        if self._posting_date is not None:
            qd = self._posting_date.date()
            state[K.KEY_POSTING_DATE] = date(qd.year(), qd.month(), qd.day()).isoformat()
        if self._narration is not None:
            text = self._narration.text().strip()
            state[K.KEY_POSTING_NARRATION] = text or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not (self._confirm and self._confirm.isChecked()):
            return StepValidationResult.fail("Confirm to post the run.")
        if not isinstance(state.get(K.KEY_RUN_ID), int):
            return StepValidationResult.fail("No run to post.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID):
            return
        company_id = context.require_company_id()
        service = context.service_registry.payroll_posting_service
        run_id = int(state[K.KEY_RUN_ID])
        posting_date = date.fromisoformat(str(state[K.KEY_POSTING_DATE]))
        cmd = PostPayrollRunCommand(
            run_id=run_id,
            posting_date=posting_date,
            narration=state.get(K.KEY_POSTING_NARRATION),
        )
        result = service.post_run(company_id, cmd, actor_user_id=context.user_id)
        state[K.KEY_POSTED_JOURNAL_ENTRY_ID] = result.journal_entry_id
        state[K.KEY_POSTED_ENTRY_NUMBER] = result.entry_number
        state[K.KEY_RUN_STATUS] = "posted"

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        je_id = state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)
        if je_id:
            num = state.get(K.KEY_POSTED_ENTRY_NUMBER) or je_id
            return f"Posted to GL — journal entry {num}."
        d = state.get(K.KEY_POSTING_DATE) or "(today)"
        return f"Post run {state.get(K.KEY_RUN_REFERENCE)} on {d}."
