"""Company tax profile DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class CompanyTaxProfileDTO:
    """Detail view of a company's tax-compliance profile.

    Returned by ``CompanyTaxProfileService.get_or_default()`` — when no
    row exists yet, the service returns an "empty" DTO with default
    flags, so the UI can always render the form without a separate
    "create vs edit" branch.
    """

    company_id: int
    exists: bool

    niu: str | None
    tax_center_code: str | None
    taxpayer_segment_code: str | None
    tax_regime_code: str | None

    is_vat_liable: bool
    vat_effective_from: date | None

    cit_rate_profile_code: str | None
    cit_installment_profile_code: str | None
    sme_qualified_flag: bool

    dsf_form_code: str | None
    dsf_submission_mode_code: str | None

    otp_enabled_flag: bool
    default_withholding_applicable_flag: bool

    updated_by_user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class UpsertCompanyTaxProfileCommand:
    """Single command for both first-time creation and subsequent edits.

    Because the profile is one-per-company, there is no ``id`` to
    distinguish create from update at the API level — the company id is
    the natural key. The service performs an upsert.
    """

    niu: str | None = None
    tax_center_code: str | None = None
    taxpayer_segment_code: str | None = None
    tax_regime_code: str | None = None

    is_vat_liable: bool = False
    vat_effective_from: date | None = None

    cit_rate_profile_code: str | None = None
    cit_installment_profile_code: str | None = None
    sme_qualified_flag: bool = False

    dsf_form_code: str | None = None
    dsf_submission_mode_code: str | None = None

    otp_enabled_flag: bool = False
    default_withholding_applicable_flag: bool = False
