from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DepreciationMethodDTO:
    id: int
    code: str
    name: str
    asset_family_code: str
    requires_settings: bool
    requires_components: bool
    requires_usage_records: bool
    requires_pool: bool
    requires_depletion_profile: bool
    has_switch_to_sl: bool
    sort_order: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class MacrsProfileDTO:
    id: int
    class_code: str
    class_name: str
    recovery_period_years: int
    convention_code: str
