"""Slice T50 — E-filing scaffold tests.

Tests cover:
  1. VATEFilingPayloadService exists and can be imported.
  2. Permission constants exist.
  3. generate_payload requires PERMISSION_FILE permission.
  4. generate_payload raises NotFoundError for unknown company.
  5. generate_payload raises NotFoundError for unknown return.
  6. generate_payload raises ValidationError if return is not FILED.
  7. generate_payload returns EFilingPayloadDTO with XML and hash.
  8. XML payload contains required elements.
  9. Payload hash is SHA-256 of the XML.
  10. record_submission_acknowledgement raises ConflictError if not in awaiting state.
  11. EFilingPayloadDTO is immutable (frozen dataclass).
  12. TaxReturn model has all 3 e-filing scaffold columns.
"""
from __future__ import annotations

import datetime
import hashlib
from decimal import Decimal
from unittest.mock import MagicMock

import unittest

import pytest

from seeker_accounting.modules.taxation.services.vat_efiling_payload_service import (
    EFilingPayloadDTO,
    RecordAcknowledgementCommand,
    VATEFilingPayloadService,
    PERMISSION_GENERATE_EFILING,
    PERMISSION_RECORD_ACK,
    _build_xml,
)
from seeker_accounting.modules.taxation.constants import (
    RETURN_STATUS_FILED,
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

_COMPANY_ID = 1
_RETURN_ID = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_line(box_code: str = "VAT_OUTPUT", amount: str = "192500") -> MagicMock:
    line = MagicMock()
    line.box_code = box_code
    line.label = "TVA collectée"
    line.amount = Decimal(amount)
    line.base_amount = Decimal("1000000")
    line.sort_order = 0
    return line


def _mock_return(
    *,
    status_code: str = RETURN_STATUS_FILED,
    lines: list | None = None,
) -> MagicMock:
    ret = MagicMock()
    ret.id = _RETURN_ID
    ret.status_code = status_code
    ret.period_start = datetime.date(2025, 1, 1)
    ret.period_end = datetime.date(2025, 1, 31)
    ret.filed_at = datetime.datetime(2025, 2, 5, 10, 0, 0)
    ret.otp_reference = "OTP-12345"
    ret.lines = lines if lines is not None else [_mock_line()]
    return ret


def _build_service(
    *,
    permission_ok: bool = True,
    company_exists: bool = True,
    tax_return: MagicMock | None = None,
) -> VATEFilingPayloadService:
    mock_permission = MagicMock()
    if not permission_ok:
        mock_permission.require_permission.side_effect = PermissionDeniedError("denied")

    mock_session = MagicMock()
    mock_uow = MagicMock()
    mock_uow.__enter__.return_value = mock_session
    mock_uow.__exit__.return_value = False

    company_obj = MagicMock() if company_exists else None
    if company_obj:
        company_obj.display_name = "Acme Cameroon SA"
    company_repo = MagicMock()
    company_repo.get.return_value = company_obj

    return_repo = MagicMock()
    return_repo.get_by_id.return_value = tax_return

    svc = VATEFilingPayloadService(
        unit_of_work_factory=MagicMock(return_value=mock_uow),
        company_repository_factory=MagicMock(return_value=company_repo),
        tax_return_repository_factory=MagicMock(return_value=return_repo),
        permission_service=mock_permission,
    )
    return svc


# ---------------------------------------------------------------------------
# T50ConstantsTests
# ---------------------------------------------------------------------------


class T50ConstantsTests(unittest.TestCase):
    def test_permission_generate_efiling(self):
        assert PERMISSION_GENERATE_EFILING == "taxation.returns.file"

    def test_permission_record_ack(self):
        assert PERMISSION_RECORD_ACK == "taxation.returns.confirm"

    def test_efiling_payload_dto_is_frozen(self):
        dto = EFilingPayloadDTO(
            return_id=1,
            payload_xml="<xml/>",
            payload_hash="abc123",
        )
        with pytest.raises((AttributeError, TypeError)):
            dto.return_id = 999  # type: ignore[misc]

    def test_tax_return_model_has_efiling_columns(self):
        from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
        assert hasattr(TaxReturn, "submission_payload_hash")
        assert hasattr(TaxReturn, "submission_acknowledgement_id")
        assert hasattr(TaxReturn, "submission_authority_timestamp")


# ---------------------------------------------------------------------------
# T50XMLBuilderTests
# ---------------------------------------------------------------------------


class T50XMLBuilderTests(unittest.TestCase):
    def test_build_xml_returns_string(self):
        xml = _build_xml(
            company_name="Acme SA",
            niu="P0012345A",
            tax_centre="DGE",
            tax_regime="REAL",
            period_start="2025-01-01",
            period_end="2025-01-31",
            filed_at="2025-02-05T10:00:00",
            otp_reference="OTP-999",
            lines=[{"box_code": "VAT_OUTPUT", "label": "TVA", "amount": "192500", "base_amount": None}],
        )
        assert isinstance(xml, str)
        assert len(xml) > 0

    def test_build_xml_contains_niu(self):
        xml = _build_xml(
            company_name="Test",
            niu="P0012345A",
            tax_centre=None,
            tax_regime=None,
            period_start="2025-01-01",
            period_end="2025-01-31",
            filed_at="2025-02-05",
            otp_reference=None,
            lines=[],
        )
        assert "P0012345A" in xml

    def test_build_xml_contains_company_name(self):
        xml = _build_xml(
            company_name="Acme Cameroon SA",
            niu=None,
            tax_centre=None,
            tax_regime=None,
            period_start="2025-01-01",
            period_end="2025-01-31",
            filed_at="",
            otp_reference=None,
            lines=[],
        )
        assert "Acme Cameroon SA" in xml

    def test_build_xml_schema_version_present(self):
        xml = _build_xml(
            company_name="X",
            niu=None,
            tax_centre=None,
            tax_regime=None,
            period_start="2025-01-01",
            period_end="2025-01-31",
            filed_at="",
            otp_reference=None,
            lines=[],
        )
        assert "SeekerDGI" in xml


# ---------------------------------------------------------------------------
# T50ServiceTests
# ---------------------------------------------------------------------------


class T50ServiceTests(unittest.TestCase):
    def test_generate_payload_requires_permission(self):
        svc = _build_service(permission_ok=False)
        with pytest.raises(PermissionDeniedError):
            svc.generate_payload(_COMPANY_ID, _RETURN_ID)

    def test_generate_payload_company_not_found(self):
        svc = _build_service(company_exists=False)
        with pytest.raises(NotFoundError):
            svc.generate_payload(_COMPANY_ID, _RETURN_ID)

    def test_generate_payload_return_not_found(self):
        svc = _build_service(tax_return=None)
        with pytest.raises(NotFoundError):
            svc.generate_payload(_COMPANY_ID, _RETURN_ID)

    def test_generate_payload_rejects_draft_return(self):
        draft_return = _mock_return(status_code=RETURN_STATUS_DRAFT)
        svc = _build_service(tax_return=draft_return)
        with pytest.raises(ValidationError):
            svc.generate_payload(_COMPANY_ID, _RETURN_ID)

    def test_generate_payload_success_returns_dto(self):
        filed_return = _mock_return(status_code=RETURN_STATUS_FILED)
        svc = _build_service(tax_return=filed_return)
        result = svc.generate_payload(_COMPANY_ID, _RETURN_ID)
        assert isinstance(result, EFilingPayloadDTO)
        assert result.return_id == _RETURN_ID
        assert len(result.payload_xml) > 0
        assert len(result.payload_hash) == 64  # SHA-256 hex

    def test_generate_payload_hash_is_sha256_of_xml(self):
        filed_return = _mock_return(status_code=RETURN_STATUS_FILED)
        svc = _build_service(tax_return=filed_return)
        result = svc.generate_payload(_COMPANY_ID, _RETURN_ID)
        expected_hash = hashlib.sha256(result.payload_xml.encode("UTF-8")).hexdigest()
        assert result.payload_hash == expected_hash

    def test_generate_payload_transitions_state(self):
        """generate_payload should transition return to SUBMITTED_AWAITING_CONFIRMATION."""
        filed_return = _mock_return(status_code=RETURN_STATUS_FILED)
        svc = _build_service(tax_return=filed_return)
        svc.generate_payload(_COMPANY_ID, _RETURN_ID)
        assert filed_return.status_code == RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION

    def test_generate_payload_stores_hash_on_return(self):
        filed_return = _mock_return(status_code=RETURN_STATUS_FILED)
        svc = _build_service(tax_return=filed_return)
        result = svc.generate_payload(_COMPANY_ID, _RETURN_ID)
        assert filed_return.submission_payload_hash == result.payload_hash

    def test_record_ack_rejects_non_awaiting_state(self):
        filed_return = _mock_return(status_code=RETURN_STATUS_FILED)
        svc = _build_service(tax_return=filed_return)
        cmd = RecordAcknowledgementCommand(
            return_id=_RETURN_ID,
            acknowledgement_id="DGI-ACK-9999",
        )
        with pytest.raises(ConflictError):
            svc.record_submission_acknowledgement(_COMPANY_ID, cmd)

    def test_record_ack_requires_permission(self):
        svc = _build_service(permission_ok=False)
        cmd = RecordAcknowledgementCommand(
            return_id=_RETURN_ID,
            acknowledgement_id="DGI-ACK-9999",
        )
        with pytest.raises(PermissionDeniedError):
            svc.record_submission_acknowledgement(_COMPANY_ID, cmd)

    def test_record_ack_requires_nonempty_id(self):
        awaiting_return = _mock_return(
            status_code=RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION
        )
        svc = _build_service(tax_return=awaiting_return)
        cmd = RecordAcknowledgementCommand(
            return_id=_RETURN_ID,
            acknowledgement_id="  ",  # whitespace only
        )
        with pytest.raises(ValidationError):
            svc.record_submission_acknowledgement(_COMPANY_ID, cmd)
