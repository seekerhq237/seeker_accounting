"""Calculate-run confirmation dialog (Phase 3 / P3.S3).

A small read-only summary shown before the cockpit invokes
``PayrollRunService.calculate_run``. The user must click "Calculate" to
proceed; "Cancel" backs out without side effects.
"""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.payroll.services.payroll_dry_run import (
    PayrollDryRunEstimate,
)
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{Decimal(value):,.2f}"
    except Exception:  # noqa: BLE001
        return str(value)


class CalculateRunConfirmDialog(QDialog):
    """Pre-flight summary for a calculate-run command."""

    def __init__(
        self,
        estimate: PayrollDryRunEstimate,
        *,
        is_recalc: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        verb = "Recalculate" if is_recalc else "Calculate"
        self.setWindowTitle(f"{verb} payroll run")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        spacing = DEFAULT_TOKENS.spacing

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        outer.setSpacing(spacing.dialog_section_gap)

        # Heading.
        title = QLabel(f"Ready to {verb.lower()} {estimate.run_reference}", self)
        title_font = QFont(title.font())
        title_font.setPointSizeF(title_font.pointSizeF() * 1.1)
        title_font.setBold(True)
        title.setFont(title_font)
        outer.addWidget(title)

        period = ""
        if 1 <= estimate.period_month <= 12:
            period = f"{_MONTHS[estimate.period_month - 1]} {estimate.period_year}"
        else:
            period = f"{estimate.period_year}-{estimate.period_month:02d}"
        sub = QLabel(
            f"Period {period} · Currency {estimate.currency_code}",
            self,
        )
        sub.setObjectName("DryRunSubtitle")
        outer.addWidget(sub)

        # Summary form.
        form_frame = QFrame(self)
        form_frame.setObjectName("DryRunSummary")
        form = QFormLayout(form_frame)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(spacing.dialog_label_gap * 2)
        form.setVerticalSpacing(spacing.dialog_label_gap)

        form.addRow(
            "Employees to process",
            QLabel(f"{estimate.employee_count}", form_frame),
        )
        form.addRow(
            "Approved variable inputs",
            QLabel(f"{estimate.approved_input_batches}", form_frame),
        )
        if estimate.draft_input_batches:
            warn = QLabel(
                f"{estimate.draft_input_batches} (excluded — still in draft)",
                form_frame,
            )
            warn.setObjectName("DryRunWarning")
            form.addRow("Draft variable inputs", warn)

        if estimate.has_prior:
            anchor = (
                f"{_fmt_money(estimate.prior_total_gross)} gross / "
                f"{_fmt_money(estimate.prior_total_net)} net"
            )
            ref = estimate.prior_run_reference or ""
            label = QLabel(
                f"{anchor}\nfrom {ref} ({estimate.prior_period_label or 'prior period'})",
                form_frame,
            )
            label.setWordWrap(True)
            form.addRow("Anchor (prior run)", label)
        else:
            form.addRow(
                "Anchor (prior run)",
                QLabel("No prior run for this currency.", form_frame),
            )

        outer.addWidget(form_frame)

        # Warnings.
        if estimate.warnings:
            warn_label = QLabel("\n".join(f"• {w}" for w in estimate.warnings), self)
            warn_label.setObjectName("DryRunWarning")
            warn_label.setWordWrap(True)
            warn_label.setTextFormat(Qt.TextFormat.PlainText)
            outer.addWidget(warn_label)

        # Buttons.
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText(verb)
            ok_btn.setDefault(True)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
