"""DTOs for asset disposal."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(slots=True)
class DisposeAssetCommand:
    disposal_date: date
    disposal_amount: Decimal  # cash/proceeds received (0 for scrap, negative for cost-to-dispose)
    proceeds_account_id: int  # account that receives the proceeds DR (e.g., bank/receivable)
    gain_or_loss_account_id: int  # account for the residual (one for both gain/loss to keep v1 simple)
    reference: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class AssetDisposalResultDTO:
    asset_id: int
    asset_number: str
    journal_entry_id: int
    journal_entry_number: str
    acquisition_cost: Decimal
    accumulated_depreciation: Decimal
    net_book_value: Decimal
    proceeds: Decimal
    gain_or_loss_amount: Decimal  # positive = gain, negative = loss
    disposal_date: date
    posted_at: datetime
