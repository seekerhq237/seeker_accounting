"""Slice T45 — VAT control reconciliation service tests.

Tests cover:
  1. Pure DTO property calculations (VATReconciliationRowDTO and VATReconciliationDTO).
  2. Service-level behaviour via mock-wired VATReconciliationService.

The service uses session.scalar() directly for three aggregate queries:
  - _sum_fact (DIRECTION_SALES)  → output_fact
  - _sum_fact (DIRECTION_PURCHASE) → input_fact
  - _find_filed_return           → TaxReturn | None

When VAT account mappings are present, two additional scalar calls are made:
  - _sum_gl (output accounts, credit_side=True)
  - _sum_gl (input accounts, credit_side=False)

The order of session.scalar() calls is deterministic and matched by side_effect lists
in each test.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from seeker_accounting.modules.taxation.services.vat_reconciliation_service import (
    VATReconciliationDTO,
    VATReconciliationRowDTO,
    VATReconciliationService,
)
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError

_ZERO = Decimal("0.00")
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
    mappings: list | None = None,
) -> tuple[VATReconciliationService, MagicMock]:
    """Build a VATReconciliationService fully wired with mocks.

    Returns ``(service, mock_session)`` so tests can set side_effect on
    ``mock_session.scalar`` to control the three (or five) query results.
    """
    mock_permission = MagicMock()
    if not permission_ok:
        mock_permission.require_permission.side_effect = PermissionDeniedError("denied")

    mock_session = MagicMock()
    mock_uow = MagicMock()
    mock_uow.__enter__.return_value = mock_uow
    mock_uow.__exit__.return_value = False  # never suppress exceptions
    mock_uow.session = mock_session

    company_obj = MagicMock() if company_exists else None
    company_repo = MagicMock()
    company_repo.get_by_id.return_value = company_obj

    account_repo = MagicMock()
    account_repo.get_by_id.return_value = None  # no accounts found → fallback labels

    mapping_repo = MagicMock()
    mapping_repo.list_by_company.return_value = mappings if mappings is not None else []

    svc = VATReconciliationService(
        unit_of_work_factory=MagicMock(return_value=mock_uow),
        company_repository_factory=MagicMock(return_value=company_repo),
        account_repository_factory=MagicMock(return_value=account_repo),
        tax_code_account_mapping_repository_factory=MagicMock(return_value=mapping_repo),
        posted_tax_line_repository_factory=MagicMock(return_value=MagicMock()),
        tax_return_repository_factory=MagicMock(return_value=MagicMock()),
        permission_service=mock_permission,
    )
    return svc, mock_session


def _make_filed_return(
    output_amount: Decimal = _ZERO,
    input_amount: Decimal = _ZERO,
) -> MagicMock:
    """Return a mock TaxReturn with one output line (L17) and one input line (L30)."""
    output_line = MagicMock()
    output_line.box_code = "L17"
    output_line.amount = output_amount

    input_line = MagicMock()
    input_line.box_code = "L30"
    input_line.amount = input_amount

    mock_return = MagicMock()
    mock_return.lines = [output_line, input_line]
    return mock_return


# ---------------------------------------------------------------------------
# 1. Pure DTO tests — no service involved
# ---------------------------------------------------------------------------


class TestVATReconciliationRowDTO:
    def test_all_match_is_reconciled(self):
        row = VATReconciliationRowDTO(
            label="Output VAT",
            gl_balance=Decimal("1000.00"),
            fact_total=Decimal("1000.00"),
            return_total=Decimal("1000.00"),
        )
        assert row.is_reconciled is True
        assert row.gl_vs_fact_variance == _ZERO
        assert row.fact_vs_return_variance == _ZERO

    def test_gl_fact_differ_not_reconciled(self):
        row = VATReconciliationRowDTO(
            label="Output VAT",
            gl_balance=Decimal("1100.00"),
            fact_total=Decimal("1000.00"),
            return_total=Decimal("1000.00"),
        )
        assert row.is_reconciled is False
        assert row.gl_vs_fact_variance == Decimal("100.00")
        assert row.fact_vs_return_variance == _ZERO

    def test_fact_return_differ_not_reconciled(self):
        row = VATReconciliationRowDTO(
            label="Input VAT Recoverable",
            gl_balance=Decimal("500.00"),
            fact_total=Decimal("500.00"),
            return_total=Decimal("400.00"),
        )
        assert row.is_reconciled is False
        assert row.gl_vs_fact_variance == _ZERO
        assert row.fact_vs_return_variance == Decimal("100.00")


class TestVATReconciliationDTO:
    def test_fully_reconciled_when_all_rows_match(self):
        rows = (
            VATReconciliationRowDTO("Output", Decimal("100"), Decimal("100"), Decimal("100")),
            VATReconciliationRowDTO("Input", Decimal("50"), Decimal("50"), Decimal("50")),
        )
        dto = VATReconciliationDTO(
            company_id=1,
            period_start=_PERIOD_START,
            period_end=_PERIOD_END,
            rows=rows,
            notes=(),
        )
        assert dto.is_fully_reconciled is True

    def test_not_fully_reconciled_when_one_row_has_gl_variance(self):
        rows = (
            VATReconciliationRowDTO("Output", Decimal("110"), Decimal("100"), Decimal("100")),
            VATReconciliationRowDTO("Input", Decimal("50"), Decimal("50"), Decimal("50")),
        )
        dto = VATReconciliationDTO(
            company_id=1,
            period_start=_PERIOD_START,
            period_end=_PERIOD_END,
            rows=rows,
            notes=(),
        )
        assert dto.is_fully_reconciled is False


# ---------------------------------------------------------------------------
# 2. Service tests
# ---------------------------------------------------------------------------


class TestVATReconciliationServiceReconcilePeriod:
    """Test reconcile_period() via mock-wired service instances."""

    def test_raises_permission_denied_without_view_permission(self):
        svc, _ = _build_service(permission_ok=False)
        with pytest.raises(PermissionDeniedError):
            svc.reconcile_period(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

    def test_raises_not_found_for_missing_company(self):
        svc, _ = _build_service(company_exists=False)
        with pytest.raises(NotFoundError):
            svc.reconcile_period(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

    def test_no_data_all_zero_totals_and_note(self):
        """With no facts, no GL mappings, and no filed return — all totals are zero."""
        svc, mock_session = _build_service()
        # 3 scalar calls (no account mappings → _sum_gl short-circuits):
        #   output_fact, input_fact, _find_filed_return
        mock_session.scalar.side_effect = [None, None, None]

        result = svc.reconcile_period(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

        assert isinstance(result, VATReconciliationDTO)
        assert result.company_id == _COMPANY_ID
        assert result.period_start == _PERIOD_START
        assert result.period_end == _PERIOD_END
        assert len(result.rows) == 2
        for row in result.rows:
            assert row.gl_balance == _ZERO
            assert row.fact_total == _ZERO
            assert row.return_total == _ZERO
        assert result.is_fully_reconciled is True
        assert any("No filed VAT return" in n for n in result.notes)

    def test_no_filed_return_shows_zero_return_totals_with_note(self):
        """Facts exist but no filed return → return_total is zero, advisory note added."""
        svc, mock_session = _build_service()
        mock_session.scalar.side_effect = [
            Decimal("500.00"),  # output_fact
            Decimal("200.00"),  # input_fact
            None,               # _find_filed_return → no return found
        ]

        result = svc.reconcile_period(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

        assert result.rows[0].fact_total == Decimal("500.00")
        assert result.rows[0].return_total == _ZERO
        assert result.rows[0].fact_vs_return_variance == Decimal("500.00")
        assert result.rows[1].fact_total == Decimal("200.00")
        assert result.rows[1].return_total == _ZERO
        assert result.rows[1].fact_vs_return_variance == Decimal("200.00")
        assert any("No filed VAT return" in n for n in result.notes)

    def test_filed_return_with_matching_lines_zero_fact_return_variance(self):
        """When facts and return lines agree, fact_vs_return_variance is zero."""
        svc, mock_session = _build_service()
        filed_return = _make_filed_return(
            output_amount=Decimal("1000.00"),
            input_amount=Decimal("300.00"),
        )
        mock_session.scalar.side_effect = [
            Decimal("1000.00"),  # output_fact
            Decimal("300.00"),   # input_fact
            filed_return,        # _find_filed_return
        ]

        result = svc.reconcile_period(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

        assert result.rows[0].fact_total == Decimal("1000.00")
        assert result.rows[0].return_total == Decimal("1000.00")
        assert result.rows[0].fact_vs_return_variance == _ZERO
        assert result.rows[1].fact_total == Decimal("300.00")
        assert result.rows[1].return_total == Decimal("300.00")
        assert result.rows[1].fact_vs_return_variance == _ZERO
        assert len(result.notes) == 0

    def test_account_mappings_populate_gl_balances(self):
        """When VAT account mappings exist, GL balances come from session.scalar."""
        mock_mapping = MagicMock()
        mock_mapping.tax_liability_account_id = 100  # output VAT account
        mock_mapping.tax_asset_account_id = 200       # input VAT account
        svc, mock_session = _build_service(mappings=[mock_mapping])

        # 5 scalar calls (account mappings present → _sum_gl called twice):
        #   output_fact, input_fact, output_gl, input_gl, _find_filed_return
        mock_session.scalar.side_effect = [
            Decimal("1000.00"),  # output_fact
            Decimal("300.00"),   # input_fact
            Decimal("1000.00"),  # output_gl (credit net on account 100)
            Decimal("300.00"),   # input_gl  (debit net on account 200)
            None,                # no filed return
        ]

        result = svc.reconcile_period(_COMPANY_ID, _PERIOD_START, _PERIOD_END)

        assert result.rows[0].gl_balance == Decimal("1000.00")
        assert result.rows[0].fact_total == Decimal("1000.00")
        assert result.rows[0].gl_vs_fact_variance == _ZERO
        assert result.rows[1].gl_balance == Decimal("300.00")
        assert result.rows[1].fact_total == Decimal("300.00")
        assert result.rows[1].gl_vs_fact_variance == _ZERO
