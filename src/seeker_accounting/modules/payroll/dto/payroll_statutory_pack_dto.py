from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class StatutoryPackSummaryDTO:
    """Lightweight descriptor for a statutory payroll pack."""

    pack_code: str
    display_name: str
    country_code: str
    description: str


@dataclass(frozen=True, slots=True)
class ApplyPackResultDTO:
    """Result returned after applying a statutory payroll pack to a company."""

    pack_code: str
    version_code: str
    components_created: int
    components_skipped: int
    rule_sets_created: int
    rule_sets_skipped: int
    brackets_created: int
    settings_updated: bool
    settings_action: str
    superseded_previous_pack_code: str | None = None
    message: str = field(default="")
