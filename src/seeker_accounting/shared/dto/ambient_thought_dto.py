"""DTOs for the Ambient Intelligence subsystem.

These DTOs are the contract between thought providers, the orchestrator
service, and the overlay widget. Providers return `AmbientThoughtDTO`
instances; the overlay renders them. Context flowing into providers is
captured as an immutable `AmbientThoughtContextDTO`.

Design notes:
* All DTOs are frozen dataclasses with slots for cheap copying and safe
  hashing. Nested collections use tuples, not lists, so a thought can be
  freely passed across the shell without aliasing risk.
* `tone` is intentionally narrow ("hint", "caution", "projection"). Tones
  describe how the thought should be felt, not how severe it is. Severity
  is implicit in the chosen rule.
* `why_items` is a tuple of short bullets. The overlay's "Why" panel binds
  directly to it; providers must keep each entry to one short sentence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


AmbientThoughtTone = Literal["hint", "caution", "projection"]


@dataclass(frozen=True, slots=True)
class AmbientThoughtContextDTO:
    """Snapshot of where the user currently is.

    Built by `AmbientThoughtContextService` once per shell refresh and
    handed to every provider. Providers MUST treat this as read-only and
    MUST NOT cache it across calls.
    """

    nav_id: str | None
    company_id: int | None
    company_name: str | None
    base_currency_code: str | None
    fiscal_period_id: int | None
    fiscal_period_status: str | None
    fiscal_period_end_date: str | None  # ISO; kept stringly to keep DTO importable from anywhere
    user_id: int | None
    page_context: tuple[tuple[str, object], ...] = field(default_factory=tuple)

    def page_value(self, key: str, default: object = None) -> object:
        """Convenience: page-context tuples are awkward to scan inline."""
        for k, v in self.page_context:
            if k == key:
                return v
        return default


@dataclass(frozen=True, slots=True)
class AmbientThoughtDTO:
    """A single thought candidate.

    Providers create these. The orchestrator filters, ranks, and returns
    the best one to the overlay.
    """

    thought_code: str
    tone: AmbientThoughtTone
    summary: str
    detail: str = ""
    confidence_label: str = "Likely"  # human-facing: "Likely", "Watch", "High confidence"
    relevance: float = 0.5  # 0..1 — how tightly tied to current page
    urgency: float = 0.0    # 0..1 — deadline / risk proximity
    confidence: float = 0.5  # 0..1 — strength of evidence
    importance: float = 0.5  # 0..1 — domain-set priority
    source_kind: str = "rule"  # "rule" | "trend" | "deadline" | "demo"
    nav_id: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    why_items: tuple[str, ...] = field(default_factory=tuple)
    expires_at: datetime | None = None
