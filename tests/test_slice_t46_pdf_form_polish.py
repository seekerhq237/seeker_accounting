"""Slice T46 — PDF form polish tests.

Covers:
  1. Regime checkbox rendering — dynamic based on ``tax_regime_code``.
  2. Certification block — always present, taxpayer name populated.
  3. Tax centre and taxpayer segment appear in identity block.
  4. NIU sourced from tax profile when available; falls back to company.tax_identifier.
  5. _snapshot_company handles absent tax profile gracefully.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from seeker_accounting.modules.taxation.services.tax_return_pdf_export_service import (
    TaxReturnPDFExportService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _company(
    *,
    name: str = "Acme SA",
    legal_name: str | None = "Acme Société Anonyme",
    tax_identifier: str | None = None,
    registration_number: str | None = "RC123",
    phone: str | None = None,
    email: str | None = None,
) -> MagicMock:
    c = MagicMock()
    c.display_name = name
    c.legal_name = legal_name
    c.tax_identifier = tax_identifier
    c.registration_number = registration_number
    c.phone = phone
    c.email = email
    c.address_line_1 = None
    c.address_line_2 = None
    c.city = None
    c.region = None
    return c


def _tax_profile(
    *,
    niu: str | None = "P012345678901A",
    tax_regime_code: str | None = "ACTUAL",
    tax_center_code: str | None = "Douala Centre",
    taxpayer_segment_code: str | None = "LARGE",
) -> MagicMock:
    p = MagicMock()
    p.niu = niu
    p.tax_regime_code = tax_regime_code
    p.tax_center_code = tax_center_code
    p.taxpayer_segment_code = taxpayer_segment_code
    return p


def _snapshot(company_mock, profile_mock=None) -> dict:
    return TaxReturnPDFExportService._snapshot_company(company_mock, profile_mock)


# ---------------------------------------------------------------------------
# 1. _snapshot_company
# ---------------------------------------------------------------------------

class TestSnapshotCompany:
    def test_niu_from_tax_profile_preferred_over_tax_identifier(self):
        company = _company(tax_identifier="OLD-ID")
        profile = _tax_profile(niu="NIU-FROM-PROFILE")
        snap = _snapshot(company, profile)
        assert snap["tax_id"] == "NIU-FROM-PROFILE"

    def test_niu_falls_back_to_tax_identifier_when_profile_absent(self):
        company = _company(tax_identifier="FALLBACK-ID")
        snap = _snapshot(company, None)
        assert snap["tax_id"] == "FALLBACK-ID"

    def test_niu_falls_back_to_tax_identifier_when_profile_niu_is_none(self):
        company = _company(tax_identifier="FALLBACK-ID")
        profile = _tax_profile(niu=None)
        snap = _snapshot(company, profile)
        assert snap["tax_id"] == "FALLBACK-ID"

    def test_tax_regime_code_included_from_profile(self):
        company = _company()
        profile = _tax_profile(tax_regime_code="SIMPLIFIED")
        snap = _snapshot(company, profile)
        assert snap["tax_regime_code"] == "SIMPLIFIED"

    def test_tax_center_and_segment_included_from_profile(self):
        company = _company()
        profile = _tax_profile(tax_center_code="Yaoundé Est", taxpayer_segment_code="SME")
        snap = _snapshot(company, profile)
        assert snap["tax_center_code"] == "Yaoundé Est"
        assert snap["taxpayer_segment_code"] == "SME"

    def test_profile_fields_are_none_when_no_profile(self):
        company = _company()
        snap = _snapshot(company, None)
        assert snap["tax_regime_code"] is None
        assert snap["tax_center_code"] is None
        assert snap["taxpayer_segment_code"] is None


# ---------------------------------------------------------------------------
# 2. Regime checkbox rendering
# ---------------------------------------------------------------------------

class TestRegimeCheckboxRendering:
    """Verify that the regime checkboxes are dynamic in _render_identity_block."""

    def _make_service(self) -> TaxReturnPDFExportService:
        return TaxReturnPDFExportService(
            unit_of_work_factory=MagicMock(),
            app_context=MagicMock(),
            tax_return_repository_factory=MagicMock(),
            company_repository_factory=MagicMock(),
            permission_service=MagicMock(),
            print_engine=MagicMock(),
        )

    def _make_return_dto(self) -> MagicMock:
        dto = MagicMock()
        dto.status_code = "DRAFT"
        dto.period_start = datetime.date(2025, 1, 1)
        dto.period_end = datetime.date(2025, 1, 31)
        dto.filed_at = None
        dto.otp_reference = None
        dto.external_reference = None
        dto.tax_type_code = "VAT"
        return dto

    def _identity_html(self, regime_code: str | None) -> str:
        svc = self._make_service()
        company = {
            "name": "Acme SA",
            "legal_name": "Acme SA",
            "tax_id": "P012345",
            "registration_number": "RC001",
            "address": None,
            "phone": None,
            "email": None,
            "tax_regime_code": regime_code,
            "tax_center_code": None,
            "taxpayer_segment_code": None,
        }
        return svc._render_identity_block(company, self._make_return_dto(), None)

    def test_actual_regime_ticks_actual_checkbox(self):
        html = self._identity_html("ACTUAL")
        actual_pos = html.find("Actual (R")
        simplified_pos = html.find("Simplified (Simplifi")
        # Checkbox immediately before "Actual (Réel)" should contain tick
        actual_checkbox_region = html[max(0, actual_pos - 60):actual_pos]
        # Checkbox between "Actual (Réel)" and "Simplified" should be blank
        between_region = html[actual_pos:simplified_pos]
        assert "\u2713" in actual_checkbox_region
        assert "&nbsp;" in between_region  # the Simplified checkbox is blank

    def test_simplified_regime_ticks_simplified_checkbox(self):
        html = self._identity_html("SIMPLIFIED")
        simplified_pos = html.find("Simplified")
        actual_pos = html.find("Actual")
        simplified_checkbox_html = html[max(0, simplified_pos - 80):simplified_pos]
        actual_checkbox_html = html[max(0, actual_pos - 80):actual_pos]
        assert "\u2713" in simplified_checkbox_html
        assert "\u2713" not in actual_checkbox_html

    def test_none_regime_defaults_to_ticking_actual(self):
        """With no regime set, fall back ticks Actual (régime réel by default)."""
        html = self._identity_html(None)
        actual_pos = html.find("Actual")
        actual_checkbox_html = html[max(0, actual_pos - 80):actual_pos]
        assert "\u2713" in actual_checkbox_html

    def test_tax_center_appears_in_identity_block(self):
        svc = self._make_service()
        company = {
            "name": "Acme", "legal_name": None, "tax_id": None,
            "registration_number": None, "address": None, "phone": None, "email": None,
            "tax_regime_code": None,
            "tax_center_code": "Douala Centre",
            "taxpayer_segment_code": "LARGE",
        }
        html = svc._render_identity_block(company, self._make_return_dto(), None)
        assert "Douala Centre" in html
        assert "LARGE" in html


# ---------------------------------------------------------------------------
# 3. Certification block
# ---------------------------------------------------------------------------

class TestCertificationBlock:
    def _make_service(self) -> TaxReturnPDFExportService:
        return TaxReturnPDFExportService(
            unit_of_work_factory=MagicMock(),
            app_context=MagicMock(),
            tax_return_repository_factory=MagicMock(),
            company_repository_factory=MagicMock(),
            permission_service=MagicMock(),
            print_engine=MagicMock(),
        )

    def test_certification_statement_present(self):
        svc = self._make_service()
        company = {"name": "Acme SA"}
        html = svc._render_certification_block(company)
        assert "Je certifie" in html
        assert "I certify" in html

    def test_certification_includes_taxpayer_name(self):
        svc = self._make_service()
        company = {"name": "Kamgue &amp; Partners"}
        html = svc._render_certification_block(company)
        assert "Kamgue" in html

    def test_certification_includes_signature_and_stamp_label(self):
        svc = self._make_service()
        company = {"name": "Acme SA"}
        html = svc._render_certification_block(company)
        assert "signature" in html.lower() or "cachet" in html.lower()

    def test_certification_includes_place_and_date_fields(self):
        svc = self._make_service()
        company = {"name": "Test Co"}
        html = svc._render_certification_block(company)
        assert "Fait" in html or "Done at" in html
