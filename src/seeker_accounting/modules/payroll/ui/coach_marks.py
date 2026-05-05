"""Payroll inline coach marks (P12.S3).

Provides dismissable tooltip-style coach marks for unfamiliar payroll
terms encountered on the workbench.  Coach marks appear only on the
first encounter and are never re-shown after dismissal.

Usage::

    cm = create_coach_mark("cnps_regime", parent=label_widget)
    if cm is not None:                # None = already dismissed
        layout.addWidget(cm)

The coach mark is a small "?" button.  On click it shows a ``QToolTip``-
style popup (``QFrame`` popover) with:
  - term title
  - one-line explanation
  - "Learn more" link (emits ``learn_more_requested`` signal or opens URL)

Dismissal is stored in ``_DISMISSED_TERMS`` (class-level set, per session).
A ``dismiss_all()`` function resets all dismissals (useful for testing).

Registered terms
----------------
- ``cnps_regime``   : Caisse Nationale de Prévoyance Sociale contribution regime
- ``risk_class``    : CNPS occupational-risk classification
- ``statutory_pack``: Pre-built statutory rules bundle for a jurisdiction
- ``bik_mode``      : Benefits-in-Kind valuation method
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Registry ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CoachMarkSpec:
    key: str
    term: str
    explanation: str
    help_key: str | None = None


COACH_MARK_REGISTRY: dict[str, CoachMarkSpec] = {
    "cnps_regime": CoachMarkSpec(
        key="cnps_regime",
        term="CNPS Regime",
        explanation=(
            "The Caisse Nationale de Prévoyance Sociale (CNPS) contribution regime "
            "determines the rates at which employer and employee social-security "
            "contributions are calculated.  Typical regimes differ by sector "
            "(private, agro-industrial, public enterprise)."
        ),
        help_key="payroll.statutory",
    ),
    "risk_class": CoachMarkSpec(
        key="risk_class",
        term="Risk Class",
        explanation=(
            "CNPS occupational-risk classification.  Employers are rated A, B, or C "
            "based on the statistical accident frequency in their industry sector.  "
            "Higher risk classes attract a higher employer contribution rate."
        ),
        help_key="payroll.statutory",
    ),
    "statutory_pack": CoachMarkSpec(
        key="statutory_pack",
        term="Statutory pack",
        explanation=(
            "A statutory pack is a pre-built bundle of tax tables, CNPS rates, "
            "and authority codes for a specific country or jurisdiction.  Applying "
            "a pack loads all the rules needed to calculate statutory deductions "
            "automatically without manual configuration."
        ),
        help_key="payroll.statutory",
    ),
    "bik_mode": CoachMarkSpec(
        key="bik_mode",
        term="BIK Mode",
        explanation=(
            "Benefits-in-Kind (BIK) valuation mode controls how non-cash benefits "
            "such as company vehicles, housing allowances, or meal vouchers are "
            "converted to a taxable monetary equivalent for IRPP and CNPS purposes."
        ),
        help_key="payroll.setup",
    ),
}

# Per-session dismissal state
_DISMISSED_TERMS: set[str] = set()

# ── Widget ────────────────────────────────────────────────────────────────────


class PayrollCoachMark(QFrame):
    """A small "?" button that reveals an inline coach-mark tooltip.

    Signals
    -------
    dismissed(key)
        Emitted when the user closes the popover and the term is recorded
        as dismissed.
    learn_more_requested(help_key)
        Emitted when the user clicks the "Learn more" link.  The caller
        may connect this to the help panel.
    """

    dismissed = Signal(str)
    learn_more_requested = Signal(str)

    def __init__(self, spec: CoachMarkSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._popover: QFrame | None = None

        self.setObjectName("PayrollCoachMark")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._trigger = QPushButton("?", self)
        self._trigger.setObjectName("PayrollCoachMarkTrigger")
        self._trigger.setFixedSize(16, 16)
        self._trigger.setProperty("variant", "ghost")
        self._trigger.setFlat(True)
        self._trigger.setCursor(Qt.CursorShape.PointingHandCursor)
        self._trigger.setToolTip(f"What is {spec.term}?")
        self._trigger.clicked.connect(self._on_trigger)
        layout.addWidget(self._trigger)

    def _on_trigger(self) -> None:
        if self._popover is not None and self._popover.isVisible():
            self._popover.hide()
            return
        self._show_popover()

    def _show_popover(self) -> None:
        if self._popover is None:
            self._popover = self._build_popover()
        self._popover.show()
        self._popover.adjustSize()
        # Position below the trigger button, aligned left
        trigger_pos = self._trigger.mapToGlobal(
            self._trigger.rect().bottomLeft()
        )
        self._popover.move(trigger_pos)

    def _build_popover(self) -> QFrame:
        """Build the popover QFrame (parented to the desktop, so it floats)."""
        pop = QFrame(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        pop.setObjectName("PayrollCoachMarkPopover")
        pop.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )

        vl = QVBoxLayout(pop)
        vl.setContentsMargins(12, 10, 12, 10)
        vl.setSpacing(6)

        # Title row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title = QLabel(f"<b>{self._spec.term}</b>", pop)
        title.setObjectName("PayrollCoachMarkTitle")
        title_row.addWidget(title, 1)

        close_btn = QPushButton("×", pop)
        close_btn.setObjectName("PayrollCoachMarkClose")
        close_btn.setFlat(True)
        close_btn.setFixedSize(16, 16)
        close_btn.clicked.connect(self._on_dismiss)
        title_row.addWidget(close_btn)
        vl.addLayout(title_row)

        # Explanation
        explanation = QLabel(self._spec.explanation, pop)
        explanation.setObjectName("PayrollCoachMarkBody")
        explanation.setWordWrap(True)
        explanation.setMaximumWidth(320)
        vl.addWidget(explanation)

        # "Learn more" link
        if self._spec.help_key:
            learn_btn = QPushButton("Learn more →", pop)
            learn_btn.setObjectName("PayrollCoachMarkLearnMore")
            learn_btn.setFlat(True)
            learn_btn.setProperty("variant", "link")
            help_key = self._spec.help_key
            learn_btn.clicked.connect(
                lambda: self.learn_more_requested.emit(help_key)
            )
            vl.addWidget(learn_btn)

        return pop

    def _on_dismiss(self) -> None:
        if self._popover is not None:
            self._popover.hide()
        _DISMISSED_TERMS.add(self._spec.key)
        self.dismissed.emit(self._spec.key)
        self.hide()


# ── Factory ───────────────────────────────────────────────────────────────────


def create_coach_mark(
    key: str, parent: QWidget | None = None
) -> PayrollCoachMark | None:
    """Return a ``PayrollCoachMark`` for *key*, or ``None`` if already dismissed.

    Returns ``None`` also when *key* is not in the registry (fail-safe).
    """
    if key in _DISMISSED_TERMS:
        return None
    spec = COACH_MARK_REGISTRY.get(key)
    if spec is None:
        logger.warning("Unknown coach mark key: %r", key)
        return None
    return PayrollCoachMark(spec, parent=parent)


def dismiss_all() -> None:
    """Dismiss all coach marks — resets session state (useful for tests)."""
    _DISMISSED_TERMS.clear()
