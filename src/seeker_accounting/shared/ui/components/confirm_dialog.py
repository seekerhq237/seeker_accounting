"""ConfirmDialog — tiered confirmation for destructive verbs.

Three levels:

- ``warn``      : standard yes / no, default to *No*.
- ``typed``     : user must type a confirmation phrase before the
                   primary action becomes enabled.
- ``double``    : a second confirmation step (intent → consequences →
                   final confirm). Used for posted-run reversal,
                   year-end rollback and similar.

This is a leaf UI primitive — no business logic.
"""
from __future__ import annotations

from typing import Final, Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components.severity_pill import SeverityPill
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

ConfirmTier = Literal["warn", "typed", "double"]


def confirm(
    *,
    parent: QWidget | None,
    title: str,
    message: str,
    primary_label: str = "Confirm",
    cancel_label: str = "Cancel",
    severity: str = "warning",
    tier: ConfirmTier = "warn",
    typed_phrase: str | None = None,
    consequences: list[str] | None = None,
) -> bool:
    """Convenience runner. Returns ``True`` if the user confirmed."""
    dlg = ConfirmDialog(
        title=title,
        message=message,
        primary_label=primary_label,
        cancel_label=cancel_label,
        severity=severity,
        tier=tier,
        typed_phrase=typed_phrase,
        consequences=consequences,
        parent=parent,
    )
    return dlg.exec() == QDialog.DialogCode.Accepted


class ConfirmDialog(QDialog):
    """Tiered confirmation dialog."""

    def __init__(
        self,
        *,
        title: str,
        message: str,
        primary_label: str = "Confirm",
        cancel_label: str = "Cancel",
        severity: str = "warning",
        tier: ConfirmTier = "warn",
        typed_phrase: str | None = None,
        consequences: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(440, 220)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        self._tier = tier
        self._typed_phrase = (typed_phrase or "").strip()
        self._typed_ok = tier != "typed"
        self._double_acked = tier != "double"

        spacing = DEFAULT_TOKENS.spacing
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        outer.setSpacing(spacing.dialog_section_gap)

        # Header row: severity pill + title.
        header = QHBoxLayout()
        header.setSpacing(spacing.compact_gap)
        pill = SeverityPill(severity, parent=self)
        header.addWidget(pill)
        title_label = QLabel(title, self)
        title_label.setObjectName("FormDialogSectionTitle")
        title_label.setWordWrap(True)
        header.addWidget(title_label, 1)
        outer.addLayout(header)

        body = QLabel(message, self)
        body.setObjectName("ConfirmDialogBody")
        body.setWordWrap(True)
        outer.addWidget(body)

        if consequences:
            cons_frame = QFrame(self)
            cons_frame.setObjectName("ConfirmDialogConsequences")
            cons_layout = QVBoxLayout(cons_frame)
            cons_layout.setContentsMargins(0, 0, 0, 0)
            cons_layout.setSpacing(spacing.inline_error_gap)
            for line in consequences:
                lbl = QLabel(f"• {line}", cons_frame)
                lbl.setWordWrap(True)
                lbl.setObjectName("FormFieldHint")
                cons_layout.addWidget(lbl)
            outer.addWidget(cons_frame)

        if tier == "typed" and typed_phrase:
            prompt = QLabel(
                f'Type "<b>{typed_phrase}</b>" to confirm.', self
            )
            prompt.setWordWrap(True)
            prompt.setObjectName("FormFieldHint")
            outer.addWidget(prompt)
            self._typed_input = QLineEdit(self)
            self._typed_input.setObjectName("ConfirmDialogTypedInput")
            self._typed_input.textChanged.connect(self._on_typed_change)
            outer.addWidget(self._typed_input)

        if tier == "double":
            self._ack_check = QCheckBox(
                "I understand this action cannot be undone automatically.", self
            )
            self._ack_check.toggled.connect(self._on_ack_toggle)
            outer.addWidget(self._ack_check)

        outer.addStretch(1)

        # Footer.
        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel_btn = QPushButton(cancel_label, self)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)
        self._primary_btn = QPushButton(primary_label, self)
        self._primary_btn.setObjectName("ConfirmDialogPrimaryButton")
        self._primary_btn.setDefault(False)  # never default for destructive
        self._primary_btn.setAutoDefault(False)
        self._primary_btn.clicked.connect(self.accept)
        footer.addWidget(self._primary_btn)
        outer.addLayout(footer)

        cancel_btn.setDefault(True)
        cancel_btn.setAutoDefault(True)
        self._refresh_primary()

    # ── internals ─────────────────────────────────────────────────────

    def _on_typed_change(self, text: str) -> None:
        self._typed_ok = text.strip() == self._typed_phrase
        self._refresh_primary()

    def _on_ack_toggle(self, checked: bool) -> None:
        self._double_acked = checked
        self._refresh_primary()

    def _refresh_primary(self) -> None:
        self._primary_btn.setEnabled(self._typed_ok and self._double_acked)
