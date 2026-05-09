"""Orchestrator service for the Ambient Intelligence subsystem.

Given an `AmbientThoughtContextDTO`, asks every registered provider for
its candidate thoughts, drops anything muted or expired, ranks the rest,
and returns the best one (or all of them, for callers that want a list).

Providers are duck-typed: anything with
``provide(context: AmbientThoughtContextDTO) -> Iterable[AmbientThoughtDTO]``
is acceptable. Provider failures are caught and skipped — a single
broken provider must never silence the whole layer.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Iterable, Protocol

from seeker_accounting.shared.dto.ambient_thought_dto import (
    AmbientThoughtContextDTO,
    AmbientThoughtDTO,
)


if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry
    from seeker_accounting.shared.services.ambient_thought_preferences_service import (
        AmbientThoughtPreferencesService,
    )


logger = logging.getLogger(__name__)


class AmbientThoughtProvider(Protocol):
    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> Iterable[AmbientThoughtDTO]: ...


class AmbientThoughtService:
    """Single entry point for the overlay to obtain a thought."""

    def __init__(
        self,
        preferences_service: "AmbientThoughtPreferencesService",
    ) -> None:
        self._sr: "ServiceRegistry | None" = None
        self._prefs = preferences_service
        self._providers: list[AmbientThoughtProvider] = []
        self._recently_shown: list[str] = []
        self._max_recent = 8

    def bind(self, service_registry: "ServiceRegistry") -> None:
        """Attach the service registry. Must be called once before use.

        The two-phase construction lets the registry hold this service as
        a non-optional field while still being able to be passed back in
        as the providers' shared dependency.
        """
        self._sr = service_registry
        self._build_providers()

    # ── Public API ───────────────────────────────────────────────────

    def get_best_thought(
        self, context: AmbientThoughtContextDTO
    ) -> AmbientThoughtDTO | None:
        thoughts = self.get_thoughts(context)
        return thoughts[0] if thoughts else None

    def get_thoughts(
        self, context: AmbientThoughtContextDTO
    ) -> tuple[AmbientThoughtDTO, ...]:
        if self._sr is None:
            return ()
        if not self._prefs.is_enabled() or self._prefs.is_snoozed():
            return ()

        candidates: list[AmbientThoughtDTO] = []
        for provider in self._providers:
            try:
                produced = provider.provide(context)
            except Exception:
                logger.debug(
                    "Ambient provider %s raised during provide(); skipping.",
                    type(provider).__name__,
                    exc_info=True,
                )
                continue
            if not produced:
                continue
            for thought in produced:
                if not isinstance(thought, AmbientThoughtDTO):
                    continue
                candidates.append(thought)

        muted = set(self._prefs.muted_codes())
        now = datetime.now()
        viable = [
            t for t in candidates
            if t.thought_code not in muted
            and (t.expires_at is None or t.expires_at > now)
        ]

        if not viable:
            return ()

        ranked = sorted(viable, key=self._score, reverse=True)
        return tuple(ranked)

    def mark_shown(self, thought: AmbientThoughtDTO) -> None:
        """Track a thought as shown to suppress repeats / reward novelty."""
        self._recently_shown.append(thought.thought_code)
        if len(self._recently_shown) > self._max_recent:
            self._recently_shown = self._recently_shown[-self._max_recent :]

    def mark_dismissed(self, thought: AmbientThoughtDTO) -> None:
        """Record an explicit user dismissal (not mute). Adds the code
        once more to the recent-shown list so the annoyance penalty kicks
        in sooner if the user keeps dismissing the same thought."""
        self._recently_shown.append(thought.thought_code)
        if len(self._recently_shown) > self._max_recent:
            self._recently_shown = self._recently_shown[-self._max_recent :]

    # ── Ranking ──────────────────────────────────────────────────────

    def _score(self, thought: AmbientThoughtDTO) -> float:
        novelty = 0.0 if thought.thought_code in self._recently_shown else 0.2
        annoyance_penalty = 0.0
        # Small penalty if the same code shows up again and again. Cheap
        # but enough to keep us from "haunting" the user with one rule.
        if self._recently_shown.count(thought.thought_code) >= 3:
            annoyance_penalty = 0.3
        return (
            (thought.relevance * 1.0)
            + (thought.urgency * 1.2)
            + (thought.confidence * 0.6)
            + (thought.importance * 0.6)
            + novelty
            - annoyance_penalty
        )

    # ── Provider wiring ──────────────────────────────────────────────

    def _build_providers(self) -> None:
        sr = self._sr
        if sr is None:
            return
        # Lazy imports keep module load cheap and avoid tugging in feature
        # modules at registry construction time.
        from seeker_accounting.modules.payroll.services.payroll_thought_provider import (
            PayrollThoughtProvider,
        )
        from seeker_accounting.modules.sales.services.sales_thought_provider import (
            SalesThoughtProvider,
        )
        from seeker_accounting.modules.purchases.services.purchases_thought_provider import (
            PurchasesThoughtProvider,
        )
        from seeker_accounting.modules.treasury.services.treasury_thought_provider import (
            TreasuryThoughtProvider,
        )
        from seeker_accounting.modules.accounting.reference_data.services.tax_thought_provider import (
            TaxThoughtProvider,
        )
        from seeker_accounting.modules.accounting.reference_data.services.master_data_thought_provider import (
            MasterDataThoughtProvider,
        )
        from seeker_accounting.modules.reporting.services.reporting_thought_provider import (
            ReportingThoughtProvider,
        )
        from seeker_accounting.modules.reporting.services.forecast_thought_provider import (
            ForecastThoughtProvider,
        )

        self._providers = [
            PayrollThoughtProvider(sr),
            SalesThoughtProvider(sr),
            PurchasesThoughtProvider(sr),
            TreasuryThoughtProvider(sr),
            TaxThoughtProvider(sr),
            MasterDataThoughtProvider(sr),
            ReportingThoughtProvider(sr),
            ForecastThoughtProvider(sr),
        ]
