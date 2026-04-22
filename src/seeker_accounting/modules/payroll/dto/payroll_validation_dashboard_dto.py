from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ValidationCheckDTO:
    """One readiness check result."""
    check_code: str
    category: str  # setup, employees, components, rules, accounts, period
    severity: str  # error, warning, info
    title: str
    message: str
    entity_type: str | None = None
    entity_id: int | None = None
    entity_label: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationDashboardResultDTO:
    """Full readiness assessment for a payroll period."""
    company_id: int
    period_year: int
    period_month: int
    checks: tuple[ValidationCheckDTO, ...]
    employee_count: int
    ready_employee_count: int

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.checks if c.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for c in self.checks if c.severity == "info")

    @property
    def is_ready(self) -> bool:
        return self.error_count == 0

    @property
    def categories(self) -> tuple[str, ...]:
        seen: list[str] = []
        for c in self.checks:
            if c.category not in seen:
                seen.append(c.category)
        return tuple(seen)

    def checks_by_category(self, category: str) -> tuple[ValidationCheckDTO, ...]:
        return tuple(c for c in self.checks if c.category == category)
