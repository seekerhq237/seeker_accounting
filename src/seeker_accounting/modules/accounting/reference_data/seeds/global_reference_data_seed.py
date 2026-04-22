"""Global reference-data seeding for countries and currencies.

Reads committed CSV seed assets and upserts rows idempotently.
Follows the same architectural pattern as global_chart_reference_seed.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).parent


@dataclass(frozen=True, slots=True)
class GlobalReferenceSeedResult:
    countries_inserted: int
    currencies_inserted: int


def _load_country_seeds() -> list[dict[str, str]]:
    path = _SEED_DIR / "countries.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _load_currency_seeds() -> list[dict[str, str]]:
    path = _SEED_DIR / "currencies.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def ensure_global_reference_data_seed(
    country_repository: CountryRepository,
    currency_repository: CurrencyRepository,
) -> GlobalReferenceSeedResult:
    """Idempotently seed all countries and currencies from CSV assets.

    Existing rows (matched by primary-key code) are skipped.
    No rows are deleted or deactivated.
    """
    countries_inserted = 0
    for row in _load_country_seeds():
        code = row["code"].strip()
        if country_repository.get_by_code(code) is not None:
            continue
        country_repository.add(
            Country(
                code=code,
                name=row["name"].strip(),
                is_active=bool(int(row["is_active"])),
            )
        )
        countries_inserted += 1

    currencies_inserted = 0
    for row in _load_currency_seeds():
        code = row["code"].strip()
        if currency_repository.get_by_code(code) is not None:
            continue
        currency_repository.add(
            Currency(
                code=code,
                name=row["name"].strip(),
                symbol=row.get("symbol", "").strip() or None,
                decimal_places=int(row["decimal_places"]),
                is_active=bool(int(row["is_active"])),
            )
        )
        currencies_inserted += 1

    if countries_inserted or currencies_inserted:
        logger.info(
            "Global reference seed: %d countries, %d currencies inserted.",
            countries_inserted,
            currencies_inserted,
        )

    return GlobalReferenceSeedResult(
        countries_inserted=countries_inserted,
        currencies_inserted=currencies_inserted,
    )
