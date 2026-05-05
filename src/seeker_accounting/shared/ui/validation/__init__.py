"""Field-level validation primitives.

The validation pipeline is intentionally synchronous and Qt-native — no
``asyncio`` coupling — because every validator we ship runs in
microseconds. For genuinely async lookups (server-side uniqueness
check, account-in-coa) callers attach a ``QThread`` / background-task
runner externally and post the resolved
:class:`ValidationResult` via a signal.

Usage::

    name_field = QLineEdit()
    pipeline = LiveValidationPipeline(
        adapter=LineEditAdapter(name_field),
        validators=[Required(), MaxLength(64)],
    )
    pipeline.result_changed.connect(my_form.on_field_validated)

This module is a pure UI primitive — no domain imports.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any, Callable, Iterable, Sequence

from PySide6.QtCore import QDate, QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)


# ──────────────────────────────────────────────────────────────────────
# ValidationResult
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ValidationResult:
    is_valid: bool
    reason: str = ""
    severity: str = "error"  # one of: blocker, error, warning, info, notice

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(True, "", "info")

    @classmethod
    def fail(cls, reason: str, severity: str = "error") -> "ValidationResult":
        return cls(False, reason, severity)


# ──────────────────────────────────────────────────────────────────────
# FieldValidator protocol
# ──────────────────────────────────────────────────────────────────────


class FieldValidator(ABC):
    """Synchronous validator. Override :meth:`validate`."""

    @abstractmethod
    def validate(self, value: Any) -> ValidationResult:
        ...


# ──────────────────────────────────────────────────────────────────────
# Built-in validators
# ──────────────────────────────────────────────────────────────────────


class Required(FieldValidator):
    def __init__(self, message: str = "This field is required") -> None:
        self._message = message

    def validate(self, value: Any) -> ValidationResult:
        if value is None:
            return ValidationResult.fail(self._message)
        if isinstance(value, str) and not value.strip():
            return ValidationResult.fail(self._message)
        if isinstance(value, (list, tuple, set, dict)) and len(value) == 0:
            return ValidationResult.fail(self._message)
        return ValidationResult.ok()


class MinLength(FieldValidator):
    def __init__(self, length: int, message: str | None = None) -> None:
        self._length = length
        self._message = message or f"At least {length} characters required"

    def validate(self, value: Any) -> ValidationResult:
        if value is None or not isinstance(value, str):
            return ValidationResult.ok()
        return (
            ValidationResult.ok()
            if len(value.strip()) >= self._length
            else ValidationResult.fail(self._message)
        )


class MaxLength(FieldValidator):
    def __init__(self, length: int, message: str | None = None) -> None:
        self._length = length
        self._message = message or f"Maximum {length} characters"

    def validate(self, value: Any) -> ValidationResult:
        if value is None or not isinstance(value, str):
            return ValidationResult.ok()
        return (
            ValidationResult.ok()
            if len(value) <= self._length
            else ValidationResult.fail(self._message)
        )


class Regex(FieldValidator):
    def __init__(self, pattern: str, message: str = "Invalid format") -> None:
        self._regex = re.compile(pattern)
        self._message = message

    def validate(self, value: Any) -> ValidationResult:
        if value is None or value == "":
            return ValidationResult.ok()
        if not isinstance(value, str):
            return ValidationResult.fail(self._message)
        return (
            ValidationResult.ok()
            if self._regex.fullmatch(value)
            else ValidationResult.fail(self._message)
        )


class DecimalRange(FieldValidator):
    def __init__(
        self,
        minimum: Decimal | None = None,
        maximum: Decimal | None = None,
        *,
        allow_negative: bool = True,
        allow_zero: bool = True,
        message: str | None = None,
    ) -> None:
        self._min = minimum
        self._max = maximum
        self._allow_neg = allow_negative
        self._allow_zero = allow_zero
        self._message = message

    def validate(self, value: Any) -> ValidationResult:
        if value is None or value == "":
            return ValidationResult.ok()
        try:
            if isinstance(value, Decimal):
                d = value
            else:
                d = Decimal(str(value))
        except (InvalidOperation, DecimalException, ValueError):
            return ValidationResult.fail(self._message or "Invalid number")
        if not self._allow_neg and d < 0:
            return ValidationResult.fail("Value cannot be negative")
        if not self._allow_zero and d == 0:
            return ValidationResult.fail("Value cannot be zero")
        if self._min is not None and d < self._min:
            return ValidationResult.fail(self._message or f"Minimum is {self._min}")
        if self._max is not None and d > self._max:
            return ValidationResult.fail(self._message or f"Maximum is {self._max}")
        return ValidationResult.ok()


class DateRange(FieldValidator):
    def __init__(
        self,
        minimum: date | None = None,
        maximum: date | None = None,
        message: str | None = None,
    ) -> None:
        self._min = minimum
        self._max = maximum
        self._message = message

    def validate(self, value: Any) -> ValidationResult:
        if value is None:
            return ValidationResult.ok()
        if isinstance(value, datetime):
            d: date | None = value.date()
        elif isinstance(value, date):
            d = value
        elif isinstance(value, QDate):
            d = value.toPython() if value.isValid() else None
        else:
            return ValidationResult.fail(self._message or "Invalid date")
        if d is None:
            return ValidationResult.ok()
        if self._min is not None and d < self._min:
            return ValidationResult.fail(self._message or f"Date must be on or after {self._min}")
        if self._max is not None and d > self._max:
            return ValidationResult.fail(self._message or f"Date must be on or before {self._max}")
        return ValidationResult.ok()


class OneOf(FieldValidator):
    def __init__(self, choices: Iterable[Any], message: str = "Invalid choice") -> None:
        self._choices = set(choices)
        self._message = message

    def validate(self, value: Any) -> ValidationResult:
        if value is None or value == "":
            return ValidationResult.ok()
        return (
            ValidationResult.ok()
            if value in self._choices
            else ValidationResult.fail(self._message)
        )


class CustomValidator(FieldValidator):
    """Wraps a callable returning a :class:`ValidationResult` (or ``None`` for OK)."""

    def __init__(self, fn: Callable[[Any], ValidationResult | None]) -> None:
        self._fn = fn

    def validate(self, value: Any) -> ValidationResult:
        result = self._fn(value)
        return result or ValidationResult.ok()


# ──────────────────────────────────────────────────────────────────────
# Field adapters — translate a Qt widget into a value + change-signal
# ──────────────────────────────────────────────────────────────────────


class FieldAdapter(ABC):
    """Adapter turning a widget into ``(get_value, change_signal)``."""

    @abstractmethod
    def get_value(self) -> Any: ...
    @abstractmethod
    def change_signal(self) -> Signal: ...
    @abstractmethod
    def widget(self) -> QWidget: ...


class LineEditAdapter(FieldAdapter):
    def __init__(self, line_edit: QLineEdit) -> None:
        self._w = line_edit

    def get_value(self) -> str:
        return self._w.text()

    def change_signal(self) -> Signal:
        return self._w.textChanged

    def widget(self) -> QWidget:
        return self._w


class TextEditAdapter(FieldAdapter):
    def __init__(self, text_edit: QPlainTextEdit | QTextEdit) -> None:
        self._w = text_edit

    def get_value(self) -> str:
        if isinstance(self._w, QPlainTextEdit):
            return self._w.toPlainText()
        return self._w.toPlainText() if hasattr(self._w, "toPlainText") else ""

    def change_signal(self) -> Signal:
        return self._w.textChanged

    def widget(self) -> QWidget:
        return self._w


class ComboBoxAdapter(FieldAdapter):
    def __init__(self, combo: QComboBox, *, use_data: bool = True) -> None:
        self._w = combo
        self._use_data = use_data

    def get_value(self) -> Any:
        if self._use_data:
            return self._w.currentData()
        return self._w.currentText()

    def change_signal(self) -> Signal:
        return self._w.currentIndexChanged

    def widget(self) -> QWidget:
        return self._w


class DateEditAdapter(FieldAdapter):
    def __init__(self, date_edit: QDateEdit) -> None:
        self._w = date_edit

    def get_value(self) -> date | None:
        d = self._w.date()
        return d.toPython() if d.isValid() else None

    def change_signal(self) -> Signal:
        return self._w.dateChanged

    def widget(self) -> QWidget:
        return self._w


class CallableAdapter(FieldAdapter):
    """Adapter for custom widgets exposing ``value()`` + a Qt ``Signal``."""

    def __init__(
        self,
        widget: QWidget,
        *,
        getter: Callable[[], Any],
        signal: Signal,
    ) -> None:
        self._w = widget
        self._getter = getter
        self._signal = signal

    def get_value(self) -> Any:
        return self._getter()

    def change_signal(self) -> Signal:
        return self._signal

    def widget(self) -> QWidget:
        return self._w


# ──────────────────────────────────────────────────────────────────────
# LiveValidationPipeline
# ──────────────────────────────────────────────────────────────────────


class LiveValidationPipeline(QObject):
    """Run a chain of validators against a single field, debounced.

    On every change, the pipeline:

    1. Stops the current debounce timer and schedules a new run.
    2. Once the debounce elapses, runs validators in order; the first
       failure wins. If all pass, emits a successful
       :class:`ValidationResult`.
    3. Emits :attr:`result_changed` with the current
       :class:`ValidationResult`.
    """

    result_changed = Signal(object)  # ValidationResult

    def __init__(
        self,
        *,
        adapter: FieldAdapter,
        validators: Sequence[FieldValidator],
        debounce_ms: int = 250,
        validate_on_init: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or adapter.widget())
        self._adapter = adapter
        self._validators = list(validators)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, debounce_ms))
        self._timer.timeout.connect(self._run_now)
        self._last_result: ValidationResult = ValidationResult.ok()

        adapter.change_signal().connect(self._on_change)
        if validate_on_init:
            self._run_now()

    # ── public API -----------------------------------------------------

    def is_valid(self) -> bool:
        return self._last_result.is_valid

    def last_result(self) -> ValidationResult:
        return self._last_result

    def run_now(self) -> ValidationResult:
        """Run synchronously (skip debounce). Returns the result."""
        self._timer.stop()
        return self._run_now()

    def set_validators(self, validators: Sequence[FieldValidator]) -> None:
        self._validators = list(validators)
        self._run_now()

    # ── internals ------------------------------------------------------

    def _on_change(self, *_: Any) -> None:
        self._timer.start()

    def _run_now(self) -> ValidationResult:
        value = self._adapter.get_value()
        result = ValidationResult.ok()
        for v in self._validators:
            r = v.validate(value)
            if not r.is_valid:
                result = r
                break
        self._last_result = result
        self.result_changed.emit(result)
        return result


# ──────────────────────────────────────────────────────────────────────
# FormValidationCoordinator — aggregate per-form validity
# ──────────────────────────────────────────────────────────────────────


class FormValidationCoordinator(QObject):
    """Aggregate multiple :class:`LiveValidationPipeline` instances.

    Use to drive the enabled state of a primary action (e.g. Save):
    the action becomes enabled only when every registered pipeline
    reports valid.
    """

    valid_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pipelines: list[LiveValidationPipeline] = []
        self._is_valid: bool = True

    def add(self, pipeline: LiveValidationPipeline) -> None:
        self._pipelines.append(pipeline)
        pipeline.result_changed.connect(self._recompute)
        self._recompute()

    def is_valid(self) -> bool:
        return self._is_valid

    def validate_all(self) -> bool:
        all_ok = True
        for p in self._pipelines:
            if not p.run_now().is_valid:
                all_ok = False
        self._is_valid = all_ok
        self.valid_changed.emit(all_ok)
        return all_ok

    def _recompute(self, *_: Any) -> None:
        new_valid = all(p.is_valid() for p in self._pipelines)
        if new_valid != self._is_valid:
            self._is_valid = new_valid
            self.valid_changed.emit(new_valid)
