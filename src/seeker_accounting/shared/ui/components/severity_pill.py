"""SeverityPill — small pill widget for inline issue lists / validation rows.

Severity is one of ``blocker``, ``error``, ``warning``, ``info``,
``notice`` (see ``SeverityTokens.order``). Visual styling is fully QSS
driven via ``#SeverityPill[severity="..."]`` selectors in
``qss_builder``.

This is a leaf UI primitive — no business logic.
"""
from __future__ import annotations

from typing import Final, Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from seeker_accounting.shared.ui.components.code_label_registry import CODE_LABELS
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

Severity = Literal["blocker", "error", "warning", "info", "notice"]

VALID_SEVERITIES: Final[tuple[str, ...]] = DEFAULT_TOKENS.severity.order
DEFAULT_SEVERITY: Final[str] = "info"


def normalize_severity(value: str | None) -> str:
    if not value:
        return DEFAULT_SEVERITY
    v = value.strip().lower()
    return v if v in VALID_SEVERITIES else DEFAULT_SEVERITY


def severity_rank(value: str | None) -> int:
    """0 = most severe (blocker). Useful for sorting."""
    norm = normalize_severity(value)
    try:
        return VALID_SEVERITIES.index(norm)
    except ValueError:
        return len(VALID_SEVERITIES)


def highest_severity(values: list[str | None]) -> str:
    """Return the most-severe value across a list. Empty → ``info``."""
    best_rank = len(VALID_SEVERITIES)
    best: str = DEFAULT_SEVERITY
    for v in values:
        r = severity_rank(v)
        if r < best_rank:
            best_rank = r
            best = normalize_severity(v)
    return best


class SeverityPill(QWidget):
    """Compact pill for a single severity level + optional label override."""

    def __init__(
        self,
        severity: str | None = None,
        *,
        label: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SeverityPill")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizes = DEFAULT_TOKENS.sizes
        self.setFixedHeight(sizes.severity_pill_height)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._label)

        self._severity: str = DEFAULT_SEVERITY
        self._explicit_label: str | None = label
        self.set_severity(severity)

    # ── public API -----------------------------------------------------

    def severity(self) -> str:
        return self._severity

    def set_severity(self, severity: str | None) -> None:
        norm = normalize_severity(severity)
        self._severity = norm
        self.setProperty("severity", norm)
        if self._explicit_label is None:
            self._label.setText(CODE_LABELS.label("severity", norm))
        # Re-poll style so QSS picks up new property value.
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()

    def set_label(self, label: str | None) -> None:
        self._explicit_label = label
        if label is None:
            self._label.setText(CODE_LABELS.label("severity", self._severity))
        else:
            self._label.setText(label)
