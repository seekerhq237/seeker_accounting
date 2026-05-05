"""Unified validation engine for service-layer commands."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field
from decimal import Decimal
from typing import Any, Callable, Iterable, Literal, Protocol, TypeVar

from seeker_accounting.platform.exceptions import ValidationError

ValidationSeverity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    field: str | None = None
    severity: ValidationSeverity = "error"
    context: dict[str, Any] = dataclass_field(default_factory=dict)


class ValidationRule(Protocol):
    def validate(self, target: Any) -> ValidationIssue | None: ...


@dataclass(frozen=True, slots=True)
class ValidationResult:
    issues: tuple[ValidationIssue, ...] = dataclass_field(default_factory=tuple)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def raise_if_invalid(self) -> None:
        if self.is_valid:
            return
        message = "; ".join(issue.message for issue in self.errors)
        raise ValidationError(message, context={"issues": [asdict(issue) for issue in self.errors]})


class ValidationEngine:
    def validate(self, target: Any, rules: Iterable[ValidationRule]) -> ValidationResult:
        issues = [issue for rule in rules if (issue := rule.validate(target)) is not None]
        return ValidationResult(tuple(issues))

    def validate_or_raise(self, target: Any, rules: Iterable[ValidationRule]) -> ValidationResult:
        result = self.validate(target, rules)
        result.raise_if_invalid()
        return result


@dataclass(frozen=True, slots=True)
class RequiredFieldRule:
    field: str
    label: str | None = None
    code: str = "required"

    def validate(self, target: Any) -> ValidationIssue | None:
        value = _read_field(target, self.field)
        if value is None or value == "":
            label = self.label or self.field.replace("_", " ").title()
            return ValidationIssue(
                code=self.code,
                field=self.field,
                message=f"{label} is required.",
            )
        return None


@dataclass(frozen=True, slots=True)
class PredicateRule:
    code: str
    message: str
    predicate: Callable[[Any], bool]
    field: str | None = None
    severity: ValidationSeverity = "error"

    def validate(self, target: Any) -> ValidationIssue | None:
        if self.predicate(target):
            return None
        return ValidationIssue(
            code=self.code,
            message=self.message,
            field=self.field,
            severity=self.severity,
        )


def _read_field(target: Any, field: str) -> Any:
    if isinstance(target, dict):
        return target.get(field)
    return getattr(target, field, None)


_DEFAULT_ENGINE = ValidationEngine()
_T = TypeVar("_T")


def require_text(value: str | None, label: str, *, field: str | None = None) -> str:
    normalized = "" if value is None else value.strip()
    field_name = field or label.lower().replace(" ", "_")
    _DEFAULT_ENGINE.validate_or_raise(
        {field_name: normalized},
        (RequiredFieldRule(field_name, label),),
    )
    return normalized


def require_code(
    value: str | None,
    label: str,
    *,
    field: str | None = None,
    remove_spaces: bool = False,
) -> str:
    normalized = require_text(value, label, field=field).upper()
    return normalized.replace(" ", "") if remove_spaces else normalized


def require_int_between(
    value: int,
    label: str,
    *,
    minimum: int,
    maximum: int,
    field: str | None = None,
) -> int:
    field_name = field or label.lower().replace(" ", "_")
    _DEFAULT_ENGINE.validate_or_raise(
        {field_name: value},
        (
            PredicateRule(
                f"{field_name}.range",
                f"{label} must be between {minimum} and {maximum}.",
                lambda target: minimum <= target[field_name] <= maximum,
                field=field_name,
            ),
        ),
    )
    return value


def require_minimum_int(
    value: int,
    label: str,
    *,
    minimum: int,
    message: str | None = None,
    field: str | None = None,
) -> int:
    field_name = field or label.lower().replace(" ", "_")
    _DEFAULT_ENGINE.validate_or_raise(
        {field_name: value},
        (
            PredicateRule(
                f"{field_name}.minimum",
                message or f"{label} must be at least {minimum}.",
                lambda target: target[field_name] >= minimum,
                field=field_name,
            ),
        ),
    )
    return value


def require_non_negative_int(
    value: int,
    label: str,
    *,
    field: str | None = None,
    message: str | None = None,
) -> int:
    return require_minimum_int(
        value,
        label,
        minimum=0,
        message=message or f"{label} cannot be negative.",
        field=field,
    )


def require_non_negative_decimal(
    value: Decimal | None,
    label: str,
    *,
    field: str | None = None,
    message: str | None = None,
) -> Decimal | None:
    if value is None:
        return None
    field_name = field or label.lower().replace(" ", "_")
    _DEFAULT_ENGINE.validate_or_raise(
        {field_name: value},
        (
            PredicateRule(
                f"{field_name}.non_negative",
                message or f"{label} cannot be negative.",
                lambda target: target[field_name] >= Decimal("0"),
                field=field_name,
            ),
        ),
    )
    return value