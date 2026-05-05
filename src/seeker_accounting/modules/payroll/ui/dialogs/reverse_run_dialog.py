"""ReverseRunDialog — Phase 8 reversal confirmation dialog.

Captures the three fields required by ``ReversePayrollRunCommand``:

- **Reversal date** — defaults to today; must be a date whose fiscal
  period is still OPEN.
- **Reason** — mandatory; a concise business reason for the reversal.
- **Narration** — optional; additional GL narrative for the reversal JE.

The dialog is self-contained: it accepts a fully-loaded run DTO, builds
the reversal command, calls ``payroll_posting_service.reverse_run``, and
returns a ``PayrollReversalResultDTO`` on success.  It does **not** post
the result back to the cockpit — the caller is responsible for
refreshing its state after the dialog closes.

Usage::

    result = ReverseRunDialog.run(registry, company_id, run, actor_id, parent)
    if result is not None:
        # reversal succeeded; refresh cockpit
"""
from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    PayrollRunDetailDTO,
)
from seeker_accounting.modules.payroll.dto.payroll_posting_dto import (
    PayrollReversalResultDTO,
    ReversePayrollRunCommand,
)
from seeker_accounting.platform.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.shared.ui.components.form_dialog import FormDialog

_log = logging.getLogger(__name__)


class ReverseRunDialog(FormDialog):
    """Capture reversal details and execute ``payroll_posting_service.reverse_run``."""

    def __init__(
        self,
        registry: ServiceRegistry,
        company_id: int,
        run: PayrollRunDetailDTO,
        actor_user_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            f"Reverse Payroll run \u2014 {run.run_reference}",
            parent=parent,
            primary_label="Confirm Reversal",
            secondary_label="Cancel",
            min_width=520,
            min_height=400,
        )
        self._registry = registry
        self._company_id = company_id
        self._run = run
        self._actor_user_id = actor_user_id
        self._reversal_result: PayrollReversalResultDTO | None = None

        # ── Warning banner ──────────────────────────────────────────────
        warn = self.add_section("Warning")
        warning_label = QLabel(
            f"<b>Run:</b> {run.run_reference} \u2014 {run.run_label}<br>"
            f"<b>Period:</b> {run.period_year}-{run.period_month:02d}<br>"
            f"<b>Status:</b> {run.status_code}<br><br>"
            "Reversing a posted payroll run creates offsetting GL entries "
            "and marks the run as <b>reversed</b>. This action cannot be undone. "
            "The reversal date must fall within an open fiscal period.",
            self,
        )
        warning_label.setObjectName("DialogWarningLabel")
        warning_label.setWordWrap(True)
        warn.addRow(warning_label)

        # ── Fields ─────────────────────────────────────────────────────
        section = self.add_section("Reversal Details")

        today = date.today()
        self._reversal_date_edit = QDateEdit()
        self._reversal_date_edit.setCalendarPopup(True)
        self._reversal_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._reversal_date_edit.setDate(QDate(today.year, today.month, today.day))
        section.addRow("Reversal Date *", self._reversal_date_edit)

        self._reason_edit = QLineEdit()
        self._reason_edit.setPlaceholderText("Required \u2014 e.g. Duplicate run, calculation error")
        self._reason_edit.setMaxLength(255)
        section.addRow("Reason *", self._reason_edit)

        self._narration_edit = QPlainTextEdit()
        self._narration_edit.setPlaceholderText(
            "Optional GL narrative for the reversal journal entry."
        )
        self._narration_edit.setFixedHeight(80)
        section.addRow("Narration", self._narration_edit)

    # ── Public API ─────────────────────────────────────────────────────

    @property
    def reversal_result(self) -> PayrollReversalResultDTO | None:
        return self._reversal_result

    @classmethod
    def run(
        cls,
        registry: ServiceRegistry,
        company_id: int,
        run: PayrollRunDetailDTO,
        actor_user_id: int | None = None,
        parent: QWidget | None = None,
    ) -> PayrollReversalResultDTO | None:
        dlg = cls(registry, company_id, run, actor_user_id=actor_user_id, parent=parent)
        dlg.exec()
        return dlg.reversal_result

    # ── FormDialog hook ────────────────────────────────────────────────

    def on_submit(self) -> bool:
        reason = self._reason_edit.text().strip()
        if not reason:
            self.show_error("Reason is required.")
            return False

        reversal_date = self._reversal_date_edit.date().toPython()
        narration = self._narration_edit.toPlainText().strip() or None

        cmd = ReversePayrollRunCommand(
            run_id=self._run.id,
            reversal_date=reversal_date,
            reason=reason,
            narration=narration,
        )

        try:
            result = self._registry.payroll_posting_service.reverse_run(
                self._company_id,
                cmd,
                actor_user_id=self._actor_user_id,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            self.show_error(str(exc))
            return False
        except PeriodLockedError as exc:
            self.show_error(
                f"Cannot reverse: {exc}\n\n"
                "Ensure the fiscal period covering the reversal date is open."
            )
            return False
        except Exception as exc:  # noqa: BLE001
            _log.exception("Reversal failed unexpectedly")
            self.show_error(f"Unexpected error: {exc}")
            return False

        self._reversal_result = result
        return True
