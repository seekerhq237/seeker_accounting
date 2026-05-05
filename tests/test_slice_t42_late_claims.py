"""T42 — Late-claim auto-rollover tests.

Verifies that PostedTaxLine rows whose tax_point_date falls before the
current return period and have never been included in a return
(included_in_return_id IS NULL) are rolled into the current period's
VAT return by _compute_vat_form_lines.
"""
from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


# ── Repository method signatures ──────────────────────────────────────────────

class TestT42RepositoryMethods:
    def test_aggregate_late_claims_exists(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        assert hasattr(PostedTaxLineRepository, "aggregate_late_claims")

    def test_aggregate_late_claims_signature(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        sig = inspect.signature(PostedTaxLineRepository.aggregate_late_claims)
        params = list(sig.parameters)
        assert "company_id" in params
        assert "before_date" in params

    def test_stamp_included_in_return_exists(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        assert hasattr(PostedTaxLineRepository, "stamp_included_in_return")

    def test_clear_included_in_return_exists(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        assert hasattr(PostedTaxLineRepository, "clear_included_in_return")


# ── aggregate_late_claims query logic ─────────────────────────────────────────

class TestT42AggregateLateClaimsQuery:
    def _make_repo(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        session = MagicMock()
        session.execute.return_value.all.return_value = []
        return PostedTaxLineRepository(session)

    def test_returns_list(self):
        repo = self._make_repo()
        result = repo.aggregate_late_claims(
            company_id=1,
            before_date=date(2025, 4, 1),
        )
        assert isinstance(result, list)

    def test_result_type(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineAggregate,
        )
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        session = MagicMock()
        session.execute.return_value.all.return_value = [
            (1, True, Decimal("1000.00"), Decimal("192.50"))
        ]
        repo = PostedTaxLineRepository(session)
        result = repo.aggregate_late_claims(1, date(2025, 4, 1))
        assert len(result) == 1
        assert isinstance(result[0], PostedTaxLineAggregate)
        assert result[0].tax_code_id == 1
        assert result[0].taxable_base == Decimal("1000.00")
        assert result[0].tax_amount == Decimal("192.50")


# ── TaxReturnService merges late claims ───────────────────────────────────────

class TestT42ServiceMergesLateClaims:
    """Verifies _compute_vat_form_lines calls aggregate_late_claims and
    merges the results into the computed totals.
    """

    def _make_service(self, *, sales_aggs=None, purchase_aggs=None, late_sales=None, late_purchases=None):
        from seeker_accounting.modules.taxation.services.tax_return_service import TaxReturnService

        if sales_aggs is None:
            sales_aggs = []
        if purchase_aggs is None:
            purchase_aggs = []
        if late_sales is None:
            late_sales = []
        if late_purchases is None:
            late_purchases = []

        mock_session = MagicMock()

        mock_ptl_repo = MagicMock()
        mock_ptl_repo.aggregate_for_period.return_value = []
        mock_ptl_repo.aggregate_late_claims.side_effect = lambda company_id, before_date, direction=None, tax_type_code=None: (
            late_sales if direction == "SALES" else late_purchases
        )

        mock_fp_repo = MagicMock()
        mock_fp = MagicMock()
        mock_fp.id = 1
        mock_fp.start_date = date(2025, 4, 1)
        mock_fp.end_date = date(2025, 4, 30)
        mock_fp_repo.list_by_company.return_value = [mock_fp]

        mock_profile_repo = MagicMock()
        mock_profile = MagicMock()
        mock_profile.vat_accounting_basis = "ACCRUAL"
        mock_profile.vat_pro_rata_percent = None
        mock_profile_repo.get_by_company.return_value = mock_profile

        uow = MagicMock()
        uow.session = mock_session
        uow.__enter__ = lambda s: s
        uow.__exit__ = MagicMock(return_value=False)

        uow_factory = MagicMock(return_value=uow)

        mock_perm = MagicMock()
        mock_perm.require_permission.return_value = None

        svc = TaxReturnService(
            unit_of_work_factory=uow_factory,
            app_context=MagicMock(),
            tax_return_repository_factory=MagicMock(),
            tax_obligation_repository_factory=MagicMock(),
            company_repository_factory=MagicMock(),
            posted_tax_line_repository_factory=lambda s: mock_ptl_repo,
            fiscal_period_repository_factory=lambda s: mock_fp_repo,
            permission_service=mock_perm,
            company_tax_profile_repository_factory=lambda s: mock_profile_repo,
        )
        return svc, mock_ptl_repo, mock_session

    def test_aggregate_late_claims_is_called_for_accrual(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineAggregate,
        )
        late_sale = PostedTaxLineAggregate(
            tax_code_id=None,
            is_recoverable=None,
            taxable_base=Decimal("500.00"),
            tax_amount=Decimal("0.00"),
        )
        svc, mock_ptl_repo, _ = self._make_service(late_sales=[late_sale])
        result = svc._compute_vat_form_lines(
            MagicMock(),
            company_id=1,
            period_start=date(2025, 4, 1),
            period_end=date(2025, 4, 30),
        )
        mock_ptl_repo.aggregate_late_claims.assert_called()

    def test_late_sales_aggregate_merged_into_output(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineAggregate,
        )
        from seeker_accounting.modules.taxation.constants import VAT_RETURN_LINE_L17
        late_sale = PostedTaxLineAggregate(
            tax_code_id=None,
            is_recoverable=None,
            taxable_base=Decimal("600.00"),
            tax_amount=Decimal("115.50"),
        )
        svc, _, _ = self._make_service(late_sales=[late_sale])
        mock_session = MagicMock()
        result = svc._compute_vat_form_lines(
            mock_session,
            company_id=1,
            period_start=date(2025, 4, 1),
            period_end=date(2025, 4, 30),
        )
        # Late sale with no tax code goes to L17.
        l17 = result.get(VAT_RETURN_LINE_L17, {})
        assert l17.get("base", Decimal(0)) == Decimal("600.00")

    def test_late_purchases_aggregate_merged_into_output(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineAggregate,
        )
        from seeker_accounting.modules.taxation.constants import VAT_RETURN_LINE_L26
        late_purchase = PostedTaxLineAggregate(
            tax_code_id=None,
            is_recoverable=True,
            taxable_base=Decimal("400.00"),
            tax_amount=Decimal("77.00"),
        )
        svc, _, _ = self._make_service(late_purchases=[late_purchase])
        mock_session = MagicMock()
        result = svc._compute_vat_form_lines(
            mock_session,
            company_id=1,
            period_start=date(2025, 4, 1),
            period_end=date(2025, 4, 30),
        )
        # Recoverable purchase with no tax code goes to L26.
        l26 = result.get(VAT_RETURN_LINE_L26, {})
        assert l26.get("tax", Decimal(0)) == Decimal("77.00")

    def test_cash_basis_does_not_call_aggregate_late_claims(self):
        # Rebuild the service with a CASH-basis profile.
        from seeker_accounting.modules.taxation.services.tax_return_service import TaxReturnService

        mock_ptl_repo2 = MagicMock()
        mock_ptl_repo2.aggregate_for_period.return_value = []
        mock_ptl_repo2.aggregate_late_claims.return_value = []

        mock_fp_repo2 = MagicMock()
        mock_fp2 = MagicMock()
        mock_fp2.id = 1
        mock_fp2.start_date = date(2025, 4, 1)
        mock_fp2.end_date = date(2025, 4, 30)
        mock_fp_repo2.list_by_company.return_value = [mock_fp2]

        mock_profile = MagicMock()
        mock_profile.vat_accounting_basis = "CASH"
        mock_profile.vat_pro_rata_percent = None

        mock_profile_repo2 = MagicMock()
        mock_profile_repo2.get_by_company.return_value = mock_profile

        svc2 = TaxReturnService(
            unit_of_work_factory=MagicMock(),
            app_context=MagicMock(),
            tax_return_repository_factory=MagicMock(),
            tax_obligation_repository_factory=MagicMock(),
            company_repository_factory=MagicMock(),
            posted_tax_line_repository_factory=lambda s: mock_ptl_repo2,
            fiscal_period_repository_factory=lambda s: mock_fp_repo2,
            permission_service=MagicMock(),
            company_tax_profile_repository_factory=lambda s: mock_profile_repo2,
        )
        svc2._compute_vat_form_lines(
            MagicMock(),
            company_id=1,
            period_start=date(2025, 4, 1),
            period_end=date(2025, 4, 30),
        )
        mock_ptl_repo2.aggregate_late_claims.assert_not_called()


# ── stamp_included_in_return SQL logic ────────────────────────────────────────

class TestT42StampClearMethods:
    def test_stamp_calls_execute(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        session = MagicMock()
        session.execute.return_value.rowcount = 2
        repo = PostedTaxLineRepository(session)
        count = repo.stamp_included_in_return(
            company_id=1,
            return_id=42,
            before_date=date(2025, 4, 1),
        )
        session.execute.assert_called()
        assert count == 2

    def test_clear_calls_execute(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        session = MagicMock()
        session.execute.return_value.rowcount = 3
        repo = PostedTaxLineRepository(session)
        count = repo.clear_included_in_return(company_id=1, return_id=42)
        session.execute.assert_called()
        assert count == 3
