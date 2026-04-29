"""Step 1 — Setup: pick date range, output folder, and include-audit-events toggle."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.audit_export import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class SetupStep(WizardStep):
    key = "setup"
    title = "Audit export setup"
    subtitle = (
        "Choose the date range, output folder, and whether to include the "
        "audit event log."
    )

    def __init__(self) -> None:
        super().__init__()
        self._from_date: QDateEdit | None = None
        self._to_date: QDateEdit | None = None
        self._output_dir: QLineEdit | None = None
        self._include_events: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        today = QDate.currentDate()
        first_of_year = QDate(today.year(), 1, 1)

        self._from_date = QDateEdit(root)
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("yyyy-MM-dd")
        self._from_date.setDate(first_of_year)
        form.addRow("From date", self._from_date)

        self._to_date = QDateEdit(root)
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("yyyy-MM-dd")
        self._to_date.setDate(today)
        form.addRow("To date", self._to_date)

        dir_row = QWidget(root)
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(6)
        self._output_dir = QLineEdit(dir_row)
        self._output_dir.setPlaceholderText("Choose an empty folder for the export package")
        dir_layout.addWidget(self._output_dir, 1)
        browse = QPushButton("Browse…", dir_row)
        browse.clicked.connect(self._on_browse)
        dir_layout.addWidget(browse)
        form.addRow("Output folder", dir_row)

        outer.addLayout(form)

        self._include_events = QCheckBox(
            "Include audit event log (recommended)", root
        )
        self._include_events.setChecked(True)
        outer.addWidget(self._include_events)
        outer.addStretch(1)
        return root

    def _on_browse(self) -> None:
        if self._output_dir is None:
            return
        chosen = QFileDialog.getExistingDirectory(
            self._output_dir,
            "Select Audit Export Folder",
            self._output_dir.text() or str(Path.home()),
        )
        if chosen:
            self._output_dir.setText(chosen)

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._from_date is not None:
            existing = state.get(K.KEY_FROM_DATE)
            if isinstance(existing, date):
                self._from_date.setDate(QDate(existing.year, existing.month, existing.day))
        if self._to_date is not None:
            existing_to = state.get(K.KEY_TO_DATE)
            if isinstance(existing_to, date):
                self._to_date.setDate(QDate(existing_to.year, existing_to.month, existing_to.day))
        if self._output_dir is not None:
            existing_dir = state.get(K.KEY_OUTPUT_DIR)
            if isinstance(existing_dir, str):
                self._output_dir.setText(existing_dir)
        if self._include_events is not None:
            existing_flag = state.get(K.KEY_INCLUDE_AUDIT_EVENTS)
            if isinstance(existing_flag, bool):
                self._include_events.setChecked(existing_flag)

    def write_back(self, state: WizardState) -> None:
        if self._from_date is not None:
            qd = self._from_date.date()
            state[K.KEY_FROM_DATE] = date(qd.year(), qd.month(), qd.day())
        if self._to_date is not None:
            qd2 = self._to_date.date()
            state[K.KEY_TO_DATE] = date(qd2.year(), qd2.month(), qd2.day())
        if self._output_dir is not None:
            state[K.KEY_OUTPUT_DIR] = self._output_dir.text().strip()
        if self._include_events is not None:
            state[K.KEY_INCLUDE_AUDIT_EVENTS] = self._include_events.isChecked()
        # Invalidate any prior preview/result.
        state[K.KEY_PREVIEW] = None
        state[K.KEY_RESULT] = None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        from_d = state.get(K.KEY_FROM_DATE)
        to_d = state.get(K.KEY_TO_DATE)
        if not isinstance(from_d, date) or not isinstance(to_d, date):
            return StepValidationResult.fail("Pick both a from-date and a to-date.")
        if to_d < from_d:
            return StepValidationResult.fail("To-date must be on or after from-date.")
        out_dir = state.get(K.KEY_OUTPUT_DIR)
        if not isinstance(out_dir, str) or not out_dir:
            return StepValidationResult.fail("Choose an output folder.")
        path = Path(out_dir)
        if path.exists() and not path.is_dir():
            return StepValidationResult.fail("Output path exists and is not a folder.")
        return StepValidationResult.ok()
