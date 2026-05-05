"""Payroll first-run setup checklist widget (P12.S2).

Displays a compact, dismissable setup checklist on the payroll workbench
dashboard until all seven setup steps are complete and at least one payroll
run has been posted.

The widget:
- Shows one row per setup step (done/pending).
- Provides an action link per pending step that emits ``action_requested``
  so the pane can navigate to the relevant workbench pane.
- Can be dismissed by the user; dismissal state is stored in a module-level
  in-memory set (per-session, cleared on restart).  It is shown again if a
  new company with an incomplete setup is selected.
- Is hidden automatically once all steps are done.
- Emits ``pane_navigate_requested(pane_key: str)`` for the dashboard to
  forward to the workbench.

Usage::

    checklist = SetupChecklistWidget(parent=self)
    checklist.pane_navigate_requested.connect(workbench_page.open_pane)
    checklist.load(result)          # SetupChecklistResult from the service
"""
from __future__ import annotations

import logging
from typing import Callable

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

from seeker_accounting.modules.payroll.services.payroll_setup_checklist_service import (
    SetupChecklistResult,
)
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)

# In-memory dismissal state: company_ids the user has explicitly dismissed.
_DISMISSED_COMPANY_IDS: set[int] = set()


class SetupChecklistWidget(QFrame):
    """Collapsible setup-checklist card for the payroll workbench dashboard.

    Signals
    -------
    pane_navigate_requested(pane_key)
        Emitted when the user clicks an action link. ``pane_key`` is one of
        the workbench pane keys (e.g. ``"setup"``, ``"people"``, ``"run"``).
    dismissed(company_id)
        Emitted when the user clicks Dismiss.
    """

    pane_navigate_requested = Signal(str)
    dismissed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollSetupChecklist")
        self.setProperty("card", True)
        self._company_id: int | None = None

        spacing = DEFAULT_TOKENS.spacing

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        outer.setSpacing(spacing.dialog_field_gap)

        # Header row: title + progress + dismiss button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(spacing.compact_gap)

        self._title_label = QLabel("Set up payroll", self)
        self._title_label.setObjectName("PayrollSetupChecklistTitle")
        header.addWidget(self._title_label)

        self._progress_label = QLabel("", self)
        self._progress_label.setObjectName("PayrollSetupChecklistProgress")
        header.addWidget(self._progress_label)

        header.addStretch(1)

        self._dismiss_button = QPushButton("Dismiss", self)
        self._dismiss_button.setObjectName("PayrollSetupChecklistDismiss")
        self._dismiss_button.setProperty("variant", "ghost")
        self._dismiss_button.setFlat(True)
        self._dismiss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_button.clicked.connect(self._on_dismiss)
        header.addWidget(self._dismiss_button)
        outer.addLayout(header)

        # Sub-title
        self._subtitle_label = QLabel(
            "Complete these steps to run payroll for the first time.",
            self,
        )
        self._subtitle_label.setObjectName("PayrollSetupChecklistSubtitle")
        self._subtitle_label.setWordWrap(True)
        outer.addWidget(self._subtitle_label)

        # Items container
        self._items_container = QFrame(self)
        self._items_container.setObjectName("PayrollSetupChecklistItems")
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(2)
        outer.addWidget(self._items_container)

        self.hide()

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, company_id: int, result: SetupChecklistResult) -> None:
        """Populate the checklist from an evaluated result.

        Hides the widget if the checklist is complete or has been dismissed
        by the user for this company.
        """
        self._company_id = company_id

        if result.all_done or company_id in _DISMISSED_COMPANY_IDS:
            self.hide()
            return

        self._progress_label.setText(
            f"{result.done_count} / {result.total_count} complete"
        )

        # Rebuild item rows
        self._clear_items()
        for item in result.items:
            row = self._build_item_row(item)
            self._items_layout.addWidget(row)

        self.show()

    # ── Item rows ─────────────────────────────────────────────────────────────

    def _build_item_row(self, item) -> QWidget:
        spacing = DEFAULT_TOKENS.spacing
        row = QFrame(self._items_container)
        row.setObjectName("PayrollSetupChecklistRow")
        row.setProperty("done", str(item.done).lower())

        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 2, 0, 2)
        hl.setSpacing(spacing.compact_gap)

        # Checkmark / pending indicator
        glyph = QLabel("✓" if item.done else "○", row)
        glyph.setObjectName(
            "PayrollSetupChecklistDone" if item.done else "PayrollSetupChecklistPending"
        )
        glyph.setFixedWidth(DEFAULT_TOKENS.sizes.glyph_col_w)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(glyph)

        # Label + description
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        label = QLabel(item.label, row)
        label.setObjectName(
            "PayrollSetupChecklistLabelDone"
            if item.done
            else "PayrollSetupChecklistLabel"
        )
        text_col.addWidget(label)

        if item.description and not item.done:
            desc = QLabel(item.description, row)
            desc.setObjectName("PayrollSetupChecklistDesc")
            desc.setWordWrap(True)
            text_col.addWidget(desc)

        hl.addLayout(text_col, 1)

        # Action link (only for pending items)
        if not item.done and item.action_label and item.action_key:
            action_btn = QPushButton(item.action_label, row)
            action_btn.setObjectName("PayrollSetupChecklistAction")
            action_btn.setProperty("variant", "link")
            action_btn.setFlat(True)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            pane_key = item.action_key  # capture for closure
            action_btn.clicked.connect(
                lambda _checked, k=pane_key: self.pane_navigate_requested.emit(k)
            )
            hl.addWidget(action_btn)

        return row

    # ── Dismissal ─────────────────────────────────────────────────────────────

    def _on_dismiss(self) -> None:
        if self._company_id is not None:
            _DISMISSED_COMPANY_IDS.add(self._company_id)
            self.dismissed.emit(self._company_id)
        self.hide()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_items(self) -> None:
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()


def clear_dismissal(company_id: int) -> None:
    """Allow a dismissed checklist to reappear (e.g. after settings reset)."""
    _DISMISSED_COMPANY_IDS.discard(company_id)
