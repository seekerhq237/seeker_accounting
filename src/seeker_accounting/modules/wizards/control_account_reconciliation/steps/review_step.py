"""Step 2 — Review: shows the reconciliation snapshot."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.control_account_reconciliation_dto import (
    ControlAccountReconciliationDTO,
    ControlAccountReconciliationReportDTO,
)
from seeker_accounting.modules.wizards.control_account_reconciliation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ReviewStep(WizardStep):
    key = "review"
    title = "Reconciliation review"
    subtitle = "GL control balances vs subledger totals."

    def __init__(self) -> None:
        super().__init__()
        self._container: QVBoxLayout | None = None
        self._scroll_content: QWidget | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(root)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_content = QWidget(scroll)
        self._container = QVBoxLayout(self._scroll_content)
        self._container.setContentsMargins(0, 0, 0, 0)
        self._container.setSpacing(10)
        self._container.addStretch(1)
        scroll.setWidget(self._scroll_content)
        outer.addWidget(scroll, 1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._container is None:
            return
        company_id = context.require_company_id()
        as_of = state.get(K.KEY_AS_OF_DATE)
        if as_of is None:
            return

        roles: list[str] = []
        if state.get(K.KEY_INCLUDE_AR):
            roles.append("ar_control")
        if state.get(K.KEY_INCLUDE_AP):
            roles.append("ap_control")
        if not roles:
            return

        report = (
            context.service_registry.control_account_reconciliation_service.reconcile_all(
                company_id, as_of, role_codes=tuple(roles)
            )
        )
        state[K.KEY_REPORT] = report

        # Clear container, keep trailing stretch.
        self._clear_container()
        for section in report.sections:
            self._container.insertWidget(
                self._container.count() - 1, _build_section_card(section)
            )

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def _clear_container(self) -> None:
        if self._container is None:
            return
        # Remove every widget except the final stretch.
        while self._container.count() > 1:
            item = self._container.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()


def _fmt(value: Decimal | None) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,.2f}"


def _build_section_card(section: ControlAccountReconciliationDTO) -> QWidget:
    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card.setObjectName("reconCard")
    card.setStyleSheet(
        "#reconCard { border: 1px solid #d0d0d8; border-radius: 6px; padding: 10px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(6)

    # Header
    if section.account_mapped:
        status_text = "Reconciled" if section.is_reconciled else "Variance"
        status_color = "#2a7" if section.is_reconciled else "#c44"
    else:
        status_text = "Not configured"
        status_color = "#888"

    header_row = QHBoxLayout()
    title = QLabel(f"<b>{section.role_label}</b>")
    title.setTextFormat(Qt.TextFormat.RichText)
    header_row.addWidget(title)
    header_row.addStretch(1)
    status = QLabel(status_text)
    status.setStyleSheet(f"color: {status_color}; font-weight: 600;")
    header_row.addWidget(status)
    layout.addLayout(header_row)

    # Body
    if not section.account_mapped:
        msg = QLabel(
            f"No account is mapped to the <b>{section.role_label}</b> role for this company. "
            "Configure the mapping in <i>Account Role Mappings</i> before reconciling.",
            card,
        )
        msg.setWordWrap(True)
        msg.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(msg)
        return card

    account_line = QLabel(
        f"<b>Account:</b> {section.account_code or '?'} — "
        f"{section.account_name or '?'}",
        card,
    )
    account_line.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(account_line)

    grid = QVBoxLayout()
    grid.setSpacing(2)
    grid.addWidget(_kv_row("As-of date", section.as_of_date.isoformat()))
    grid.addWidget(_kv_row("GL control balance", _fmt(section.gl_balance)))
    grid.addWidget(_kv_row("Subledger total", _fmt(section.subledger_total)))
    delta_text = _fmt(section.delta)
    grid.addWidget(_kv_row("Delta (|GL| − subledger)", delta_text))
    grid.addWidget(
        _kv_row(
            "Open documents",
            f"{section.document_count} (across {section.party_count} parties)",
        )
    )
    layout.addLayout(grid)

    if section.gl_balance is None:
        note = QLabel(
            "<i>Could not read GL balance for the mapped account. The mapping "
            "may point to a missing account.</i>",
            card,
        )
        note.setTextFormat(Qt.TextFormat.RichText)
        note.setWordWrap(True)
        layout.addWidget(note)
    elif section.delta is not None and not section.is_reconciled:
        hint = QLabel(
            "<i>Likely causes: manual journals against the control account, "
            "unposted documents, allocations posted in a different period, or a "
            "draft journal that should be posted or reversed.</i>",
            card,
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        layout.addWidget(hint)

    return card


def _kv_row(label: str, value: str) -> QWidget:
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lbl = QLabel(label)
    lbl.setStyleSheet("color: #666;")
    h.addWidget(lbl)
    h.addStretch(1)
    val = QLabel(value)
    val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    h.addWidget(val)
    return row
