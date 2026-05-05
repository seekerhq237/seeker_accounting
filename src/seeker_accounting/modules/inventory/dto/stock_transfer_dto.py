"""Stock transfer DTOs.

Per Slice 2.3: transfers use a two-document model (``transfer_out`` and
``transfer_in``), or optionally a single "in-transit" document that sits
between. These DTOs carry the commands and results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateTransferCommand:
    """Command to create a direct or in-transit stock transfer."""

    from_location_id: int
    to_location_id: int
    transfer_date: date
    reference_number: str | None
    notes: str | None
    # in_transit=True → produces a transfer_in_transit doc; False → direct
    use_in_transit: bool
    lines: tuple["TransferLineCommand", ...]


@dataclass(frozen=True, slots=True)
class TransferLineCommand:
    item_id: int
    quantity: Decimal
    batch_id: int | None = None
    serial_ids: tuple[int, ...] = ()
    counterparty_account_id: int | None = None
    contract_id: int | None = None
    project_id: int | None = None


@dataclass(frozen=True, slots=True)
class TransferResultDTO:
    """Result returned after creating/completing a transfer."""

    transfer_document_id: int
    """The originating transfer document (transfer_out or transfer_in_transit)."""
    transfer_status_code: str
    receive_document_id: int | None
    """The matched receive document (transfer_in), if created immediately."""
