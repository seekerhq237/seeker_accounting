"""Smart code/number auto-suggestion for master-data entity creation dialogs.

Algorithm: inspect existing codes within a scope (e.g. company_id), detect the
dominant prefix and current maximum numeric suffix, then return prefix + (max+1)
zero-padded.  Falls back to *default_prefix* + "001" when no codes exist yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

UnitOfWorkFactory = Callable[[], Any]  # returns a UnitOfWork context manager


# ---------------------------------------------------------------------------
# Pure algorithm
# ---------------------------------------------------------------------------

_CODE_SPLIT_RE = re.compile(r"^(.*?)(\d+)$")


def suggest_next_code(
    existing_codes: Sequence[str],
    default_prefix: str,
    padding: int = 3,
) -> str:
    """Derive the next logical code from *existing_codes*.

    Strategy:
    1. Parse each code into ``(prefix, number)`` via trailing-digit regex.
    2. Group by prefix and pick the prefix that appears most often (ties
       broken by the highest max number – i.e. the "most active" prefix).
    3. Return ``prefix + zero_padded(max_number + 1)``.
    4. If nothing is parseable, return ``default_prefix + "001"`` (padded).
    """
    if not existing_codes:
        return f"{default_prefix}{str(1).zfill(padding)}"

    # bucket -> { prefix: [numbers] }
    buckets: dict[str, list[int]] = {}
    for code in existing_codes:
        m = _CODE_SPLIT_RE.match(code.strip())
        if m:
            prefix, digits = m.group(1), int(m.group(2))
            buckets.setdefault(prefix, []).append(digits)

    if not buckets:
        return f"{default_prefix}{str(1).zfill(padding)}"

    # Pick the dominant prefix: most occurrences, then highest max number.
    best_prefix = max(
        buckets,
        key=lambda p: (len(buckets[p]), max(buckets[p])),
    )
    next_num = max(buckets[best_prefix]) + 1
    effective_padding = max(padding, len(str(max(buckets[best_prefix]))))
    return f"{best_prefix}{str(next_num).zfill(effective_padding)}"


# ---------------------------------------------------------------------------
# Entity configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EntityCodeConfig:
    """Describes how to look up existing codes for an entity type."""

    model_class: type
    """The SQLAlchemy ORM model."""

    code_attribute: str
    """Column attribute name on the model (e.g. ``'customer_code'``)."""

    scope_attribute: str
    """Column attribute name used to filter by scope (e.g. ``'company_id'``)."""

    default_prefix: str
    """Fallback prefix when no existing codes exist (e.g. ``'CUST-'``)."""

    padding: int = 3
    """Minimum zero-padding width for the numeric portion."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class CodeSuggestionService:
    """Suggests the next code/number for a master-data entity.

    Entity configurations are registered at boot via
    :meth:`register_entity`.  Dialogs call :meth:`suggest` in create mode
    to pre-populate the code field.  The suggested value is advisory – the
    user may always change it.
    """

    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._registry: dict[str, EntityCodeConfig] = {}

    # -- configuration ------------------------------------------------------

    def register_entity(self, entity_key: str, config: EntityCodeConfig) -> None:
        self._registry[entity_key] = config

    # -- public API ---------------------------------------------------------

    def suggest(self, entity_key: str, scope_id: int) -> str:
        """Return the next suggested code for *entity_key* within *scope_id*.

        Returns a sensible default if no codes exist yet or if the entity
        key is unknown.
        """
        config = self._registry.get(entity_key)
        if config is None:
            raise ValueError(f"Unknown entity key: {entity_key!r}")

        existing = self._fetch_existing_codes(config, scope_id)
        return suggest_next_code(existing, config.default_prefix, config.padding)

    # -- internals ----------------------------------------------------------

    def _fetch_existing_codes(
        self,
        config: EntityCodeConfig,
        scope_id: int,
    ) -> list[str]:
        code_col = getattr(config.model_class, config.code_attribute)
        scope_col = getattr(config.model_class, config.scope_attribute)

        with self._unit_of_work_factory() as uow:
            stmt = (
                select(code_col)
                .where(scope_col == scope_id)
                .where(code_col.isnot(None))
                .order_by(config.model_class.id.desc())
            )
            rows = uow.session.execute(stmt).scalars().all()
        return list(rows)
