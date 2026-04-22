from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateCompanyCommand:
    legal_name: str
    display_name: str
    registration_number: str | None = None
    tax_identifier: str | None = None
    cnps_employer_number: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    sector_of_operation: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str = ""
    base_currency_code: str = ""


@dataclass(frozen=True, slots=True)
class UpdateCompanyCommand:
    legal_name: str
    display_name: str
    registration_number: str | None = None
    tax_identifier: str | None = None
    cnps_employer_number: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    sector_of_operation: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str = ""
    base_currency_code: str = ""


@dataclass(frozen=True, slots=True)
class UpdateCompanyPreferencesCommand:
    date_format_code: str
    number_format_code: str
    decimal_places: int
    tax_inclusive_default: bool
    allow_negative_stock: bool = False
    default_inventory_cost_method: str | None = None
    idle_timeout_minutes: int = 2
    password_expiry_days: int = 30


@dataclass(frozen=True, slots=True)
class UpdateCompanyFiscalDefaultsCommand:
    fiscal_year_start_month: int
    fiscal_year_start_day: int
    default_posting_grace_days: int | None = None
