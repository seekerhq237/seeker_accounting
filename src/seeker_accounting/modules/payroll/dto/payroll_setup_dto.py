from __future__ import annotations

from dataclasses import dataclass, field

from seeker_accounting.modules.payroll.dto.payroll_setup_commands import CompanyPayrollSettingsDTO


# ── Workspace summary ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PayrollSetupWorkspaceDTO:
    """Lightweight summary aggregated by PayrollSetupService for the setup page header."""

    company_id: int
    settings: CompanyPayrollSettingsDTO | None
    department_count: int
    position_count: int


# ── Seed result ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PayrollSeedResultDTO:
    """Result returned after running the Cameroon statutory pack seed."""

    version_code: str
    components_created: int
    components_skipped: int
    rule_sets_created: int
    rule_sets_skipped: int
    brackets_created: int
    message: str = field(default="")
