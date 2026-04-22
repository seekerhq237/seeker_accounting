from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PackVersionListItemDTO:
    pack_code: str
    display_name: str
    country_code: str
    effective_from: date
    description: str
    is_current: bool


@dataclass(frozen=True, slots=True)
class PackRolloverPreviewDTO:
    """Preview what a rollover from current to target would do."""
    current_pack_code: str | None
    target_pack_code: str
    target_display_name: str
    components_to_create: int
    rule_sets_to_create: int
    existing_components: int
    existing_rule_sets: int
    message: str


@dataclass(frozen=True, slots=True)
class PackRolloverResultDTO:
    previous_pack_code: str | None
    new_pack_code: str
    components_created: int
    components_skipped: int
    rule_sets_created: int
    rule_sets_skipped: int
    brackets_created: int
    settings_action: str
    superseded_previous_pack_code: str | None
    outcome_code: str
    message: str
