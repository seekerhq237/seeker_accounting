"""Statutory pack registry — central catalogue of all available pack versions.

Each pack version is a module in statutory_packs/ that exposes the canonical
seed data. The registry indexes them by pack_code and provides ordered
version history per country.

Adding a new pack version:
  1. Create a new module (e.g. cameroon_2025_pack.py) with the standard exports.
  2. Add an entry to _PACK_VERSIONS below.
  3. The service layer reads this registry to offer rollover options.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from types import ModuleType

from seeker_accounting.modules.payroll.statutory_packs import cameroon_default_pack


@dataclass(frozen=True, slots=True)
class PackVersionDescriptor:
    """Describes one statutory pack version without loading all its seed data."""
    pack_code: str
    display_name: str
    country_code: str
    effective_from: date
    description: str
    pack_module: ModuleType
    version_notes: str = ""
    last_verified: str = ""


# ── Registry ─────────────────────────────────────────────────────────────────
# Ordered by (country_code, effective_from) so that the latest version for
# a country is always last.

_PACK_VERSIONS: tuple[PackVersionDescriptor, ...] = (
    PackVersionDescriptor(
        pack_code=cameroon_default_pack.PACK_CODE,
        display_name=cameroon_default_pack.PACK_DISPLAY_NAME,
        country_code=cameroon_default_pack.PACK_COUNTRY_CODE,
        effective_from=cameroon_default_pack.PACK_EFFECTIVE_FROM,
        description=cameroon_default_pack.PACK_DESCRIPTION,
        pack_module=cameroon_default_pack,
        version_notes=getattr(cameroon_default_pack, "PACK_VERSION_NOTES", ""),
        last_verified=getattr(cameroon_default_pack, "PACK_LAST_VERIFIED", ""),
    ),
)

_BY_CODE: dict[str, PackVersionDescriptor] = {p.pack_code: p for p in _PACK_VERSIONS}


def get_all_packs() -> tuple[PackVersionDescriptor, ...]:
    return _PACK_VERSIONS


def get_pack_by_code(pack_code: str) -> PackVersionDescriptor | None:
    return _BY_CODE.get(pack_code)


def get_packs_for_country(country_code: str) -> list[PackVersionDescriptor]:
    return [p for p in _PACK_VERSIONS if p.country_code == country_code]


def get_latest_for_country(country_code: str) -> PackVersionDescriptor | None:
    packs = get_packs_for_country(country_code)
    return packs[-1] if packs else None
