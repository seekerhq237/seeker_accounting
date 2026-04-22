from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum


class LicenseState(Enum):
    """Current license state of the installation."""

    TRIAL_ACTIVE = "trial_active"
    TRIAL_EXPIRED = "trial_expired"
    LICENSED_ACTIVE = "licensed_active"
    LICENSED_EXPIRED = "licensed_expired"


@dataclass(frozen=True, slots=True)
class LicenseInfo:
    """Immutable snapshot of the current license state."""

    state: LicenseState
    # Days remaining in trial (only meaningful when state is TRIAL_ACTIVE)
    trial_days_remaining: int
    # Date the current license expires (None if no license key has been activated)
    license_expires_at: datetime.date | None
    # Short summary for UI display (e.g. "Trial – 12 days remaining", "Licensed until 2027-04-02")
    summary: str

    @property
    def is_write_permitted(self) -> bool:
        return self.state in {LicenseState.TRIAL_ACTIVE, LicenseState.LICENSED_ACTIVE}

    @property
    def is_trial(self) -> bool:
        return self.state in {LicenseState.TRIAL_ACTIVE, LicenseState.TRIAL_EXPIRED}
