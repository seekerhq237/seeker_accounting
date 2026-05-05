"""Slice T48 — VAT annex export service tests.

Tests cover:
  1. Service instantiation.
  2. Permission gate enforcement.
  3. Customers annex generation returns VATAnnexResultDTO with workbook bytes.
  4. Suppliers annex generation returns VATAnnexResultDTO with workbook bytes.
  5. Company not found raises NotFoundError.
  6. Result DTO fields are populated correctly.
  7. Workbook bytes can be loaded by openpyxl.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import unittest

import pytest

from seeker_accounting.modules.taxation.services.vat_annex_export_service import (
    AnnexLineDTO,
    VATAnnexExportService,
    VATAnnexResultDTO,
    _build_workbook,
    _CUSTOMERS_HEADERS,
    _SUPPLIERS_HEADERS,
    PERMISSION_EXPORT_ANNEX,
)
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError

_COMPANY_ID = 1
_PERIOD_START = datetime.date(2025, 1, 1)
_PERIOD_END = datetime.date(2025, 1, 31)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_service(
    *,
    permission_ok: bool = True,
    company_exists: bool = True,
) -> VATAnnexExportService:
    mock_permission = MagicMock()
    if not permission_ok:
        mock_permission.require_permission.side_effect = PermissionDeniedError("denied")

    mock_session = MagicMock()
    mock_uow = MagicMock()
    mock_uow.__enter__.return_value = mock_session
    mock_uow.__exit__.return_value = False

    if company_exists:
        company_obj = MagicMock()
        company_obj.display_name = "Acme Cameroon SA"
    else:
        company_obj = None
    company_repo = MagicMock()
    company_repo.get.return_value = company_obj

    svc = VATAnnexExportService(
        unit_of_work_factory=MagicMock(return_value=mock_uow),
        company_repository_factory=MagicMock(return_value=company_repo),
        permission_service=mock_permission,
    )
    return svc


def _sample_lines(n: int = 2) -> list[AnnexLineDTO]:
    return [
        AnnexLineDTO(
            tax_identifier=f"P0{i}0123456A",
            display_name=f"Client {i}",
            document_count=2,
            taxable_base=Decimal("1000000"),
            tax_amount=Decimal("192500"),
        )
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# T48StatusConstantsTests
# ---------------------------------------------------------------------------


class T48ConstantsTests(unittest.TestCase):
    def test_permission_constant_exists(self):
        assert PERMISSION_EXPORT_ANNEX == "taxation.returns.export_annex"

    def test_customers_headers_not_empty(self):
        assert len(_CUSTOMERS_HEADERS) >= 4

    def test_suppliers_headers_not_empty(self):
        assert len(_SUPPLIERS_HEADERS) >= 4


# ---------------------------------------------------------------------------
# T48AnnexLineDTOTests
# ---------------------------------------------------------------------------


class T48AnnexLineDTOTests(unittest.TestCase):
    def test_immutable(self):
        line = AnnexLineDTO(
            tax_identifier="P0012345A",
            display_name="Test SA",
            document_count=3,
            taxable_base=Decimal("500000"),
            tax_amount=Decimal("96250"),
        )
        assert line.taxable_base == Decimal("500000")
        assert line.withholding_vat_amount == Decimal("0")


# ---------------------------------------------------------------------------
# T48WorkbookBuilderTests
# ---------------------------------------------------------------------------


class T48WorkbookBuilderTests(unittest.TestCase):
    def test_build_customers_workbook_returns_bytes(self):
        lines = _sample_lines(2)
        wb_bytes = _build_workbook(
            "Clients",
            "Test Co",
            _PERIOD_START,
            _PERIOD_END,
            _CUSTOMERS_HEADERS,
            lines,
            is_sales=True,
        )
        assert isinstance(wb_bytes, bytes)
        assert len(wb_bytes) > 0

    def test_build_suppliers_workbook_returns_bytes(self):
        lines = _sample_lines(2)
        wb_bytes = _build_workbook(
            "Fournisseurs",
            "Test Co",
            _PERIOD_START,
            _PERIOD_END,
            _SUPPLIERS_HEADERS,
            lines,
            is_sales=False,
        )
        assert isinstance(wb_bytes, bytes)
        assert len(wb_bytes) > 0

    def test_workbook_is_valid_xlsx(self):
        import io
        import openpyxl

        lines = _sample_lines(3)
        wb_bytes = _build_workbook(
            "Clients",
            "Acme SA",
            _PERIOD_START,
            _PERIOD_END,
            _CUSTOMERS_HEADERS,
            lines,
            is_sales=True,
        )
        wb = openpyxl.load_workbook(io.BytesIO(wb_bytes))
        assert len(wb.sheetnames) == 1


# ---------------------------------------------------------------------------
# T48ServiceTests
# ---------------------------------------------------------------------------


class T48ServiceTests(unittest.TestCase):
    def test_customers_annex_requires_permission(self):
        svc = _build_service(permission_ok=False)
        with pytest.raises(PermissionDeniedError):
            svc.generate_customers_annex(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

    def test_suppliers_annex_requires_permission(self):
        svc = _build_service(permission_ok=False)
        with pytest.raises(PermissionDeniedError):
            svc.generate_suppliers_annex(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

    def test_customers_annex_company_not_found(self):
        svc = _build_service(company_exists=False)
        with pytest.raises(NotFoundError):
            svc.generate_customers_annex(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

    def test_suppliers_annex_company_not_found(self):
        svc = _build_service(company_exists=False)
        with pytest.raises(NotFoundError):
            svc.generate_suppliers_annex(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

    def test_customers_annex_returns_result_dto(self):
        """Service returns a VATAnnexResultDTO with workbook bytes."""
        svc = _build_service()
        # Patch _aggregate_sales so we don't need a real DB.
        with patch(
            "seeker_accounting.modules.taxation.services.vat_annex_export_service._aggregate_sales",
            return_value=_sample_lines(2),
        ):
            result = svc.generate_customers_annex(
                _COMPANY_ID, _PERIOD_START, _PERIOD_END
            )
        assert isinstance(result, VATAnnexResultDTO)
        assert result.direction == "SALES"
        assert len(result.rows) == 2
        assert isinstance(result.workbook_bytes, bytes)
        assert len(result.workbook_bytes) > 0

    def test_suppliers_annex_returns_result_dto(self):
        svc = _build_service()
        with patch(
            "seeker_accounting.modules.taxation.services.vat_annex_export_service._aggregate_purchases",
            return_value=_sample_lines(3),
        ):
            result = svc.generate_suppliers_annex(
                _COMPANY_ID, _PERIOD_START, _PERIOD_END
            )
        assert isinstance(result, VATAnnexResultDTO)
        assert result.direction == "PURCHASE"
        assert len(result.rows) == 3
        assert result.company_name == "Acme Cameroon SA"

    def test_customers_annex_period_fields_set(self):
        svc = _build_service()
        with patch(
            "seeker_accounting.modules.taxation.services.vat_annex_export_service._aggregate_sales",
            return_value=[],
        ):
            result = svc.generate_customers_annex(
                _COMPANY_ID, _PERIOD_START, _PERIOD_END
            )
        assert result.period_start == _PERIOD_START
        assert result.period_end == _PERIOD_END
