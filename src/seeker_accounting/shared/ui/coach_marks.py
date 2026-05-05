"""Inline coach marks for unfamiliar accounting and workbench terms."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from seeker_accounting.shared.ui.accessibility import set_accessible_metadata


@dataclass(frozen=True, slots=True)
class CoachMark:
    key: str
    term: str
    summary: str
    detail: str = ""

    @property
    def tooltip(self) -> str:
        if self.detail:
            return f"{self.summary}\n\n{self.detail}"
        return self.summary


COACH_MARKS: dict[str, CoachMark] = {
    "term.pending_postings": CoachMark(
        key="term.pending_postings",
        term="Pending Postings",
        summary="Draft accounting documents that have not yet become posted ledger truth.",
        detail="Review and post them from the source workspace when they are ready.",
    ),
    "term.aging": CoachMark(
        key="term.aging",
        term="Aging",
        summary="Open balances grouped by how long they have been outstanding.",
        detail="Aging helps prioritize collection and payment work by due-date risk.",
    ),
    "term.cash_liquidity": CoachMark(
        key="term.cash_liquidity",
        term="Cash & Liquidity",
        summary="Cash, bank, and near-cash balances plus movement trends for the selected period.",
    ),
    "term.setup_checklist": CoachMark(
        key="term.setup_checklist",
        term="Setup Checklist",
        summary="A readiness view of the minimum company foundation needed for reliable accounting workflows.",
    ),
    "term.control_account": CoachMark(
        key="term.control_account",
        term="Control Account",
        summary="A general ledger account that reconciles to a detailed subledger such as customers or suppliers.",
    ),
}


def get_coach_mark(key: str) -> CoachMark | None:
    return COACH_MARKS.get(key)


def install_coach_mark(widget: QWidget, key: str) -> None:
    mark = get_coach_mark(key)
    if mark is None:
        return
    widget.setToolTip(mark.tooltip)
    widget.setProperty("coachMarkKey", mark.key)
    description = mark.tooltip.replace("\n", " ")
    set_accessible_metadata(widget, mark.term, description)


class CoachMarkLabel(QLabel):
    def __init__(self, key: str, *, parent: QWidget | None = None) -> None:
        mark = get_coach_mark(key)
        super().__init__(mark.term if mark else key, parent)
        self.setObjectName("CoachMarkLabel")
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        if mark is not None:
            install_coach_mark(self, key)