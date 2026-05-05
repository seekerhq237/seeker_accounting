"""Form input primitives for money / rates / quantities / currency.

These widgets replace ad-hoc ``QLineEdit`` and ``QDoubleSpinBox`` usage
across feature dialogs. They are ``Decimal``-backed, locale-aware,
emit a single canonical ``value_changed(value, is_valid, reason)``
signal, and expose ``value()`` / ``set_value(...)`` /
``is_valid()`` / ``error_reason()``.

This module is a pure UI primitive — no domain imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Final

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QWidget,
)

from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


_THOUSAND_SEPS: Final[tuple[str, ...]] = (",", " ", "\u00a0", "\u202f", "'")
_DECIMAL_SEPS: Final[tuple[str, ...]] = (".", ",")


def _parse_decimal(text: str, decimal_separator: str = ".") -> Decimal | None:
    """Parse a user-entered decimal string. Returns ``None`` on failure.

    Accepts thousand separators (comma / space / NBSP / NNBSP / apostrophe)
    and a single decimal separator (configurable, defaults to dot).
    """
    if text is None:
        return None
    s = text.strip()
    if not s:
        return None
    # Drop currency symbols / spaces commonly leaked by paste.
    s = s.replace("\u00a0", "").replace("\u202f", "")
    for sep in _THOUSAND_SEPS:
        if sep == decimal_separator:
            continue
        s = s.replace(sep, "")
    if decimal_separator != ".":
        s = s.replace(decimal_separator, ".")
    if s in {"", "-", "+", ".", "-.", "+."}:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, DecimalException):
        return None


def _format_decimal(value: Decimal, fraction_digits: int) -> str:
    quant = Decimal(1).scaleb(-fraction_digits) if fraction_digits > 0 else Decimal(1)
    try:
        v = value.quantize(quant)
    except (InvalidOperation, DecimalException):
        v = value
    s = format(v, "f")
    # Normalise sign of zero.
    if v == 0:
        s = s.lstrip("-")
    return s


# ──────────────────────────────────────────────────────────────────────
# DecimalInput — base class
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _DecimalConfig:
    fraction_digits: int = 2
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    allow_negative: bool = True
    allow_zero: bool = True


class _DecimalLineEdit(QLineEdit):
    """Internal editor — re-formats on focus-out, emits user-edit signal."""

    def focusOutEvent(self, event: QFocusEvent) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        parent = self.parent()
        if isinstance(parent, _DecimalInputBase):
            parent._on_focus_out()


class _DecimalInputBase(QWidget):
    """Abstract base for Decimal-valued single-line inputs."""

    value_changed = Signal(object, bool, str)  # (Decimal | None, is_valid, reason)

    def __init__(
        self,
        *,
        config: _DecimalConfig,
        placeholder: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._value: Decimal | None = None
        self._is_valid: bool = True
        self._reason: str = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._editor = _DecimalLineEdit(self)
        self._editor.setPlaceholderText(placeholder)
        sizes = DEFAULT_TOKENS.sizes
        self._editor.setMinimumHeight(sizes.control_height)
        self._editor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._editor.textEdited.connect(self._on_text_edited)
        layout.addWidget(self._editor, 1)

        self.setFocusProxy(self._editor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    # ── value API ------------------------------------------------------

    def value(self) -> Decimal | None:
        return self._value

    def set_value(self, value: Decimal | int | float | str | None) -> None:
        if value is None or value == "":
            self._value = None
            self._editor.setText("")
            self._validate()
            return
        if isinstance(value, Decimal):
            d: Decimal | None = value
        elif isinstance(value, (int, float)):
            d = Decimal(str(value))
        else:
            d = _parse_decimal(str(value))
        self._value = d
        self._editor.setText(_format_decimal(d, self._config.fraction_digits) if d is not None else "")
        self._validate()

    def is_valid(self) -> bool:
        return self._is_valid

    def error_reason(self) -> str:
        return self._reason

    def set_read_only(self, read_only: bool) -> None:
        self._editor.setReadOnly(read_only)

    def set_placeholder(self, text: str) -> None:
        self._editor.setPlaceholderText(text)

    # ── internals ------------------------------------------------------

    def _on_text_edited(self, text: str) -> None:
        parsed = _parse_decimal(text)
        self._value = parsed
        self._validate()

    def _on_focus_out(self) -> None:
        if self._value is not None and self._is_valid:
            self._editor.setText(
                _format_decimal(self._value, self._config.fraction_digits)
            )

    def _validate(self) -> None:
        cfg = self._config
        # If text is non-empty but parse failed → invalid.
        if self._value is None:
            if self._editor.text().strip() == "":
                self._is_valid = True
                self._reason = ""
            else:
                self._is_valid = False
                self._reason = "Enter a valid number"
            self.value_changed.emit(self._value, self._is_valid, self._reason)
            return
        v = self._value
        if not cfg.allow_negative and v < 0:
            self._is_valid = False
            self._reason = "Value cannot be negative"
        elif not cfg.allow_zero and v == 0:
            self._is_valid = False
            self._reason = "Value cannot be zero"
        elif cfg.minimum is not None and v < cfg.minimum:
            self._is_valid = False
            self._reason = f"Minimum is {_format_decimal(cfg.minimum, cfg.fraction_digits)}"
        elif cfg.maximum is not None and v > cfg.maximum:
            self._is_valid = False
            self._reason = f"Maximum is {_format_decimal(cfg.maximum, cfg.fraction_digits)}"
        else:
            self._is_valid = True
            self._reason = ""
        self.value_changed.emit(self._value, self._is_valid, self._reason)


# ──────────────────────────────────────────────────────────────────────
# MoneyInput
# ──────────────────────────────────────────────────────────────────────


class MoneyInput(_DecimalInputBase):
    """Currency-aware decimal input.

    The currency code is *display-only*: the stored value is a plain
    :class:`Decimal`. Pair with a :class:`CurrencyPicker` if the form
    needs to capture the currency choice itself.
    """

    def __init__(
        self,
        *,
        currency_code: str = "",
        fraction_digits: int = 2,
        minimum: Decimal | None = None,
        maximum: Decimal | None = None,
        allow_negative: bool = False,
        allow_zero: bool = True,
        placeholder: str = "0.00",
        parent: QWidget | None = None,
    ) -> None:
        cfg = _DecimalConfig(
            fraction_digits=fraction_digits,
            minimum=minimum,
            maximum=maximum,
            allow_negative=allow_negative,
            allow_zero=allow_zero,
        )
        super().__init__(config=cfg, placeholder=placeholder, parent=parent)
        self._currency_code: str = currency_code
        self._currency_label = QLabel(self)
        self._currency_label.setObjectName("MoneyInputCurrency")
        self._currency_label.setContentsMargins(8, 0, 4, 0)
        self._currency_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_currency(currency_code)
        # Insert currency label *before* the editor.
        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, self._currency_label)

    def set_currency(self, code: str) -> None:
        self._currency_code = (code or "").strip().upper()
        self._currency_label.setText(self._currency_code)
        self._currency_label.setVisible(bool(self._currency_code))

    def currency(self) -> str:
        return self._currency_code


# ──────────────────────────────────────────────────────────────────────
# RateInput — percentage 0–100
# ──────────────────────────────────────────────────────────────────────


class RateInput(_DecimalInputBase):
    """Rate / percentage input.

    The widget displays a percentage (e.g. ``12.5``). Use
    :meth:`ratio_value` to obtain the equivalent ratio (``0.125``).

    ``minimum`` / ``maximum`` are interpreted in percentage terms.
    """

    def __init__(
        self,
        *,
        fraction_digits: int = 2,
        minimum: Decimal | None = Decimal("0"),
        maximum: Decimal | None = Decimal("100"),
        allow_negative: bool = False,
        allow_zero: bool = True,
        placeholder: str = "0.00",
        parent: QWidget | None = None,
    ) -> None:
        cfg = _DecimalConfig(
            fraction_digits=fraction_digits,
            minimum=minimum,
            maximum=maximum,
            allow_negative=allow_negative,
            allow_zero=allow_zero,
        )
        super().__init__(config=cfg, placeholder=placeholder, parent=parent)
        self._suffix = QLabel("%", self)
        self._suffix.setObjectName("RateInputSuffix")
        self._suffix.setContentsMargins(4, 0, 8, 0)
        self._suffix.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = self.layout()
        if layout is not None:
            layout.addWidget(self._suffix)

    def ratio_value(self) -> Decimal | None:
        if self._value is None:
            return None
        return self._value / Decimal("100")

    def set_ratio_value(self, ratio: Decimal | float | int | None) -> None:
        if ratio is None:
            self.set_value(None)
            return
        if not isinstance(ratio, Decimal):
            ratio = Decimal(str(ratio))
        self.set_value(ratio * Decimal("100"))


# ──────────────────────────────────────────────────────────────────────
# QuantityInput
# ──────────────────────────────────────────────────────────────────────


class QuantityInput(_DecimalInputBase):
    """Integer or fractional quantity input.

    Default is integer (``fraction_digits=0``); for inventory weights
    use ``fraction_digits=4`` per the OHADA convention.
    """

    def __init__(
        self,
        *,
        fraction_digits: int = 0,
        minimum: Decimal | None = Decimal("0"),
        maximum: Decimal | None = None,
        allow_negative: bool = False,
        allow_zero: bool = True,
        placeholder: str = "0",
        parent: QWidget | None = None,
    ) -> None:
        cfg = _DecimalConfig(
            fraction_digits=fraction_digits,
            minimum=minimum,
            maximum=maximum,
            allow_negative=allow_negative,
            allow_zero=allow_zero,
        )
        super().__init__(config=cfg, placeholder=placeholder, parent=parent)


# ──────────────────────────────────────────────────────────────────────
# CurrencyPicker
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CurrencyOption:
    code: str
    label: str
    fraction_digits: int = 2


class CurrencyPicker(QWidget):
    """Combo-box selector for ISO-4217 currency codes.

    Never accepts free text: the user must pick from the supplied list,
    which is sourced from the active company. The widget never queries
    services directly — callers feed it a list via
    :meth:`set_currencies`.
    """

    currency_changed = Signal(str)  # emits the selected ISO code

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._combo = QComboBox(self)
        self._combo.setEditable(False)
        self._combo.currentIndexChanged.connect(self._emit_change)
        sizes = DEFAULT_TOKENS.sizes
        self._combo.setMinimumHeight(sizes.control_height)
        layout.addWidget(self._combo, 1)

        self.setFocusProxy(self._combo)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._options: list[CurrencyOption] = []

    def set_currencies(self, currencies: list[CurrencyOption]) -> None:
        self._options = list(currencies)
        prev = self.currency()
        self._combo.blockSignals(True)
        self._combo.clear()
        for opt in self._options:
            self._combo.addItem(f"{opt.code} — {opt.label}", opt.code)
        self._combo.blockSignals(False)
        if prev:
            self.set_currency(prev)
        elif self._options:
            self._combo.setCurrentIndex(0)
            self._emit_change()

    def currency(self) -> str:
        data = self._combo.currentData()
        return str(data) if data is not None else ""

    def set_currency(self, code: str) -> None:
        if not code:
            return
        target = code.strip().upper()
        for i in range(self._combo.count()):
            if str(self._combo.itemData(i)).upper() == target:
                self._combo.setCurrentIndex(i)
                return

    def fraction_digits(self) -> int:
        code = self.currency()
        for opt in self._options:
            if opt.code.upper() == code.upper():
                return opt.fraction_digits
        return 2

    def _emit_change(self) -> None:
        self.currency_changed.emit(self.currency())
