"""InlineIssueBand — a top-of-dialog band showing validation issues.

The band is QSS-driven via ``#InlineIssueBand[severity="..."]``. It can
show a single dominant message, or summarise a list of structured
:class:`ValidationIssue` items with the highest severity colouring
the band.

This is a leaf UI primitive — no business logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components.code_label_registry import CODE_LABELS
from seeker_accounting.shared.ui.components.severity_pill import (
    DEFAULT_SEVERITY,
    VALID_SEVERITIES,
    highest_severity,
    normalize_severity,
)
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: str
    message: str
    field_id: str = ""
    rule_code: str = ""


class InlineIssueBand(QFrame):
    """Render a banner-style block at the top of a form / dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InlineIssueBand")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        spacing = DEFAULT_TOKENS.spacing
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._inner = QVBoxLayout()
        self._inner.setContentsMargins(
            spacing.issue_band_padding_h,
            spacing.issue_band_padding_v,
            spacing.issue_band_padding_h,
            spacing.issue_band_padding_v,
        )
        self._inner.setSpacing(spacing.inline_error_gap)
        outer.addLayout(self._inner)

        self._title = QLabel(self)
        self._title.setObjectName("InlineIssueBandTitle")
        self._title.setWordWrap(True)
        self._title.setVisible(False)
        self._inner.addWidget(self._title)

        self._body = QLabel(self)
        self._body.setObjectName("InlineIssueBandBody")
        self._body.setWordWrap(True)
        self._body.setVisible(False)
        self._inner.addWidget(self._body)

        self._severity: str = DEFAULT_SEVERITY
        self.setProperty("severity", self._severity)
        self.setVisible(False)

    # ── public API -----------------------------------------------------

    def show_message(
        self,
        message: str,
        *,
        severity: str = "error",
        title: str | None = None,
    ) -> None:
        if not message and not title:
            self.clear()
            return
        self._set_severity(severity)
        if title:
            self._title.setText(title)
            self._title.setVisible(True)
        else:
            self._title.setVisible(False)
        self._body.setText(message)
        self._body.setVisible(bool(message))
        self.setVisible(True)

    def show_issues(self, issues: Sequence[ValidationIssue]) -> None:
        if not issues:
            self.clear()
            return
        top = highest_severity([i.severity for i in issues])
        self._set_severity(top)
        title = CODE_LABELS.label("severity", top)
        if len(issues) > 1:
            title = f"{title} ({len(issues)})"
        self._title.setText(title)
        self._title.setVisible(True)
        body_lines = [f"• {i.message}" for i in issues if i.message]
        self._body.setText("\n".join(body_lines))
        self._body.setVisible(bool(body_lines))
        self.setVisible(True)

    def clear(self) -> None:
        self._title.clear()
        self._title.setVisible(False)
        self._body.clear()
        self._body.setVisible(False)
        self.setVisible(False)

    # ── internals ------------------------------------------------------

    def _set_severity(self, severity: str) -> None:
        norm = normalize_severity(severity)
        if norm == self._severity:
            return
        self._severity = norm
        self.setProperty("severity", norm)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()
