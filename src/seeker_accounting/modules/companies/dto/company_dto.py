from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CompanyListItemDTO:
    id: int
    legal_name: str
    display_name: str
    country_code: str
    base_currency_code: str
    logo_storage_path: str | None
    is_active: bool
    updated_at: datetime
    deleted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReferenceOptionDTO:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class CompanyPreferencesDTO:
    company_id: int
    date_format_code: str
    number_format_code: str
    decimal_places: int
    tax_inclusive_default: bool
    allow_negative_stock: bool
    default_inventory_cost_method: str | None
    idle_timeout_minutes: int
    password_expiry_days: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CompanyFiscalDefaultsDTO:
    company_id: int
    fiscal_year_start_month: int
    fiscal_year_start_day: int
    default_posting_grace_days: int | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CompanyDetailDTO:
    id: int
    legal_name: str
    display_name: str
    logo_storage_path: str | None
    logo_original_filename: str | None
    logo_content_type: str | None
    logo_updated_at: datetime | None
    registration_number: str | None
    tax_identifier: str | None
    phone: str | None
    email: str | None
    website: str | None
    sector_of_operation: str | None
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    region: str | None
    country_code: str
    base_currency_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    preferences: CompanyPreferencesDTO | None = None
    fiscal_defaults: CompanyFiscalDefaultsDTO | None = None
    cnps_employer_number: str | None = None


@dataclass(frozen=True, slots=True)
class ActiveCompanyDTO:
    company_id: int
    company_name: str
    base_currency_code: str
    logo_storage_path: str | None
