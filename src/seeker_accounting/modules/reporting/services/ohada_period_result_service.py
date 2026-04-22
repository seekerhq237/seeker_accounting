"""Shared OHADA current-year result computation.

Produces the net result (XI) from posted P&L activity using the same
locked OHADA prefix-matching and formula logic as the income statement
engine. Both the OHADA income statement service and the OHADA balance
sheet service consume this to guarantee identical bottom-line alignment.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.reporting.repositories.ohada_income_statement_repository import (
    OhadaAccountActivityRow,
    OhadaIncomeStatementRepository,
)
from seeker_accounting.modules.reporting.specs.ohada_income_statement_spec import (
    OHADA_BASE_LINE_SPECS,
    OHADA_FORMULA_LINE_SPECS,
)

OhadaIncomeStatementRepositoryFactory = Callable[[Session], OhadaIncomeStatementRepository]

_ZERO = Decimal("0.00")


class OhadaPeriodResultService:
    """Computes the OHADA net result (XI) for a given period.

    Uses the same locked prefix-matching and formula chain as the OHADA
    income statement engine so that the balance sheet derived current-year
    result is always identical to the income statement bottom line.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ohada_income_statement_repository_factory: OhadaIncomeStatementRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._ohada_income_statement_repository_factory = ohada_income_statement_repository_factory

    def compute_period_result(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> Decimal:
        """Load posted P&L activity and return the OHADA XI net result."""
        with self._unit_of_work_factory() as uow:
            repo = self._ohada_income_statement_repository_factory(uow.session)
            activity_rows = repo.list_period_activity(company_id, date_from, date_to)
        return self.compute_result_from_activity(activity_rows)

    @staticmethod
    def compute_result_from_activity(activity_rows: list[OhadaAccountActivityRow]) -> Decimal:
        """Pure computation: OHADA XI net result from P&L activity rows.

        Uses the same prefix-matching and formula logic as the income
        statement engine. The result uses the OHADA sign convention
        (credit − debit), so a positive value is a profit and a negative
        value is a loss.
        """
        base_amounts: dict[str, Decimal] = defaultdict(lambda: _ZERO)
        for row in activity_rows:
            matched_code = _match_base_line_code(row.account_code)
            if matched_code is None:
                continue
            base_amounts[matched_code] += row.total_credit - row.total_debit

        computed: dict[str, Decimal] = {}
        for spec in OHADA_BASE_LINE_SPECS:
            computed[spec.code] = base_amounts.get(spec.code, _ZERO)

        for spec in OHADA_FORMULA_LINE_SPECS:
            computed[spec.code] = sum(
                (computed.get(component, _ZERO) for component in spec.formula_components),
                _ZERO,
            )

        return computed.get("XI", _ZERO)


# ---------------------------------------------------------------------------
# Internal helpers — mirror the income statement engine's prefix matching.
# ---------------------------------------------------------------------------

# Pre-sort base line specs by longest prefix first so the matching
# algorithm is deterministic and consistent with the IS engine.
_SORTED_BASE_LINE_SPECS = sorted(
    OHADA_BASE_LINE_SPECS,
    key=lambda spec: max((len(prefix) for prefix in spec.prefixes), default=0),
    reverse=True,
)


def _match_base_line_code(account_code: str) -> str | None:
    """Return the OHADA base-line code for *account_code*, or ``None``."""
    normalized = (account_code or "").strip()
    if not normalized:
        return None
    for spec in _SORTED_BASE_LINE_SPECS:
        if any(normalized.startswith(prefix) for prefix in spec.prefixes):
            return spec.code
    return None
