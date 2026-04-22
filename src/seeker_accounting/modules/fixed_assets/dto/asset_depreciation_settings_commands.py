from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class UpsertAssetDepreciationSettingsCommand:
    """Create or update method-specific settings for an asset.

    Only supply fields relevant to the chosen depreciation method.
    Omitted fields default to None (stored as NULL in DB).
    """
    # Declining-balance family
    declining_factor: Decimal | None = field(default=None)
    switch_to_straight_line: bool = field(default=False)
    # Units of production / depletion
    expected_total_units: Decimal | None = field(default=None)
    # Annuity / sinking fund
    interest_rate: Decimal | None = field(default=None)
    # MACRS
    macrs_profile_id: int | None = field(default=None)
    macrs_convention_code: str | None = field(default=None)
