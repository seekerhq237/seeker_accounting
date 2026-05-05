"""Slice T32–T37 VAT scheme tests.

Tests cover:
  T32 – Cash-basis VAT (payment_date filtering)
  T33 – Reverse-charge VAT (paired SALES fact from TaxFactService)
  T34 – Pro-rata deduction (L24 / L31 / L37)
  T35 – VAT return amendments (amend_vat_return)
  T36 – Credit carry-forward chain (L25 / L30)
  T37 – Withholding VAT / précompte (L45 / L47)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from seeker_accounting.modules.taxation.constants import (
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_FILED,
    TAX_TYPE_VAT,
    VAT_BASIS_ACCRUAL,
    VAT_BASIS_CASH,
    VAT_RETURN_LINE_L17,
    VAT_RETURN_LINE_L24,
    VAT_RETURN_LINE_L25,
    VAT_RETURN_LINE_L26,
    VAT_RETURN_LINE_L29,
    VAT_RETURN_LINE_L30,
    VAT_RETURN_LINE_L31,
    VAT_RETURN_LINE_L36,
    VAT_RETURN_LINE_L37,
    VAT_RETURN_LINE_L40,
    VAT_RETURN_LINE_L43,
    VAT_RETURN_LINE_L44,
    VAT_RETURN_LINE_L45,
    VAT_RETURN_LINE_L47,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    AmendVATReturnCommand,
    DraftVATReturnCommand,
    TaxReturnDTO,
)
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineAggregate,
    PostedTaxLineRepository,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _make_agg(
    tax_code_id: int,
    taxable_base: str,
    tax_amount: str,
    is_recoverable: bool | None = True,
) -> PostedTaxLineAggregate:
    return PostedTaxLineAggregate(
        tax_code_id=tax_code_id,
        is_recoverable=is_recoverable,
        taxable_base=Decimal(taxable_base),
        tax_amount=Decimal(tax_amount),
    )


def _zero() -> Decimal:
    return Decimal("0.00")


# ──────────────────────────────────────────────────────────────────────
# T32 – Cash-basis VAT
# ──────────────────────────────────────────────────────────────────────

class TestCashBasisVATTests:
    """T32: when company uses CASH basis, aggregate_for_period is called
    with payment_date_start / payment_date_end and empty period_ids."""

    def test_cash_basis_passes_payment_date_kwargs(self, tmp_path):
        """aggregate_for_period receives payment_date kwargs when CASH basis."""
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )

        mock_ptl_repo = MagicMock(spec=PostedTaxLineRepository)
        mock_ptl_repo.aggregate_for_period.return_value = []

        mock_profile = MagicMock()
        mock_profile.vat_accounting_basis = VAT_BASIS_CASH
        mock_profile.vat_pro_rata_percent = None

        mock_ctp_repo = MagicMock()
        mock_ctp_repo.get_by_company.return_value = mock_profile

        mock_fp_repo = MagicMock()
        mock_fp_repo.list_by_company.return_value = []

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._posted_tax_line_repository_factory = lambda s: mock_ptl_repo
        svc._fiscal_period_repository_factory = lambda s: mock_fp_repo
        svc._company_tax_profile_repository_factory = lambda s: mock_ctp_repo

        p_start = date(2024, 1, 1)
        p_end = date(2024, 1, 31)

        svc._compute_vat_form_lines(
            session=MagicMock(),
            company_id=1,
            period_start=p_start,
            period_end=p_end,
        )

        # Both calls must use payment_date kwargs.
        for call in mock_ptl_repo.aggregate_for_period.call_args_list:
            kwargs = call.kwargs
            assert kwargs.get("payment_date_start") == p_start
            assert kwargs.get("payment_date_end") == p_end
            # period_ids argument must be empty list.
            assert call.args[1] == []

    def test_accrual_basis_does_not_pass_payment_date_kwargs(self):
        """aggregate_for_period does NOT receive payment_date kwargs when ACCRUAL."""
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )

        mock_ptl_repo = MagicMock(spec=PostedTaxLineRepository)
        mock_ptl_repo.aggregate_for_period.return_value = []

        mock_profile = MagicMock()
        mock_profile.vat_accounting_basis = VAT_BASIS_ACCRUAL
        mock_profile.vat_pro_rata_percent = None

        mock_ctp_repo = MagicMock()
        mock_ctp_repo.get_by_company.return_value = mock_profile

        mock_fp_repo = MagicMock()
        mock_fp_repo.list_by_company.return_value = []

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._posted_tax_line_repository_factory = lambda s: mock_ptl_repo
        svc._fiscal_period_repository_factory = lambda s: mock_fp_repo
        svc._company_tax_profile_repository_factory = lambda s: mock_ctp_repo

        svc._compute_vat_form_lines(
            session=MagicMock(),
            company_id=1,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
        )

        for call in mock_ptl_repo.aggregate_for_period.call_args_list:
            kwargs = call.kwargs
            assert "payment_date_start" not in kwargs


# ──────────────────────────────────────────────────────────────────────
# T33 – Reverse-charge (TaxFactService dual recording)
# ──────────────────────────────────────────────────────────────────────

class TestReverseChargeVATTests:
    """T33: TaxFactService.record_facts_in_session writes a paired SALES
    fact row when a TaxFactInput has is_reverse_charge=True and direction
    is DIRECTION_PURCHASE."""

    def test_reverse_charge_creates_paired_sales_row(self):
        from seeker_accounting.modules.taxation.services.tax_fact_service import (
            TaxFactInput,
            TaxFactService,
            DIRECTION_PURCHASE,
            DIRECTION_SALES,
        )
        from seeker_accounting.modules.taxation.models.posted_tax_line import (
            PostedTaxLine,
        )

        recorded: list[PostedTaxLine] = []

        mock_session = MagicMock()
        mock_session.add = lambda obj: recorded.append(obj)

        mock_repo = MagicMock()
        mock_repo_session_calls = []

        svc = TaxFactService.__new__(TaxFactService)
        svc._repository_factory = lambda s: mock_repo

        # Patch the PostedTaxLine appending directly.
        appended: list[dict] = []

        with patch(
            "seeker_accounting.modules.taxation.services.tax_fact_service.PostedTaxLine",
        ) as MockLine:
            instances = []
            def make_line(**kwargs):
                m = MagicMock()
                m._kwargs = kwargs
                instances.append(m)
                return m

            MockLine.side_effect = make_line
            mock_repo.add_all = MagicMock()

            svc.record_facts_in_session(
                session=mock_session,
                company_id=1,
                fiscal_period_id=10,
                direction=DIRECTION_PURCHASE,
                source_document_type="BILL",
                source_document_id=99,
                journal_entry_id=5,
                tax_point_date=date(2024, 1, 15),
                posted_at=MagicMock(),
                posted_by_user_id=1,
                line_facts=[
                    TaxFactInput(
                        tax_code_id=42,
                        taxable_base=Decimal("1000.00"),
                        tax_amount=Decimal("192.50"),
                        is_recoverable=True,
                        source_line_id=1,
                        is_reverse_charge=True,
                    )
                ],
            )

        # Should have created 2 PostedTaxLine instances — PURCHASE + SALES.
        assert len(instances) == 2
        purchase_row = instances[0]
        sales_row = instances[1]
        assert purchase_row._kwargs["direction"] == DIRECTION_PURCHASE
        assert purchase_row._kwargs["is_reverse_charge"] is True
        assert sales_row._kwargs["direction"] == DIRECTION_SALES
        assert sales_row._kwargs["is_reverse_charge"] is True
        assert sales_row._kwargs["tax_amount"] == Decimal("192.50")

    def test_non_reverse_charge_creates_single_row(self):
        from seeker_accounting.modules.taxation.services.tax_fact_service import (
            TaxFactInput,
            TaxFactService,
            DIRECTION_PURCHASE,
        )

        svc = TaxFactService.__new__(TaxFactService)
        mock_repo = MagicMock()
        svc._repository_factory = lambda s: mock_repo

        with patch(
            "seeker_accounting.modules.taxation.services.tax_fact_service.PostedTaxLine",
        ) as MockLine:
            instances = []
            def make_line(**kwargs):
                m = MagicMock()
                m._kwargs = kwargs
                instances.append(m)
                return m
            MockLine.side_effect = make_line

            svc.record_facts_in_session(
                session=MagicMock(),
                company_id=1,
                fiscal_period_id=10,
                direction=DIRECTION_PURCHASE,
                source_document_type="BILL",
                source_document_id=99,
                journal_entry_id=5,
                tax_point_date=date(2024, 1, 15),
                posted_at=MagicMock(),
                posted_by_user_id=1,
                line_facts=[
                    TaxFactInput(
                        tax_code_id=42,
                        taxable_base=Decimal("1000.00"),
                        tax_amount=Decimal("192.50"),
                        is_recoverable=True,
                        source_line_id=1,
                        is_reverse_charge=False,
                    )
                ],
            )

        assert len(instances) == 1
        assert instances[0]._kwargs["direction"] == DIRECTION_PURCHASE


# ──────────────────────────────────────────────────────────────────────
# T34 – Pro-rata deduction
# ──────────────────────────────────────────────────────────────────────

class TestProRataDeductionTests:
    """T34: when vat_pro_rata_percent is set, L24 / L31 / L37 are
    computed from gross input L30 × (pro_rata / 100)."""

    def _make_svc_with_profile(self, pro_rata_pct: float, aggs_purchase, aggs_sales=None):
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )
        from seeker_accounting.modules.accounting.reference_data.models.tax_code import (
            TaxCode,
        )

        if aggs_sales is None:
            aggs_sales = []

        mock_profile = MagicMock()
        mock_profile.vat_accounting_basis = VAT_BASIS_ACCRUAL
        mock_profile.vat_pro_rata_percent = pro_rata_pct

        mock_ctp_repo = MagicMock()
        mock_ctp_repo.get_by_company.return_value = mock_profile

        mock_ptl_repo = MagicMock(spec=PostedTaxLineRepository)
        def _agg(company_id, period_ids, direction=None, **kwargs):
            if direction == "PURCHASE":
                return aggs_purchase
            return aggs_sales
        mock_ptl_repo.aggregate_for_period.side_effect = _agg

        mock_fp = MagicMock()
        mock_fp.start_date = date(2024, 1, 1)
        mock_fp.end_date = date(2024, 1, 31)
        mock_fp.id = 1
        mock_fp_repo = MagicMock()
        mock_fp_repo.list_by_company.return_value = [mock_fp]

        mock_session = MagicMock()
        # scalars() for TaxCode lookup
        mock_session.scalars.return_value = []

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._posted_tax_line_repository_factory = lambda s: mock_ptl_repo
        svc._fiscal_period_repository_factory = lambda s: mock_fp_repo
        svc._company_tax_profile_repository_factory = lambda s: mock_ctp_repo

        return svc, mock_session

    def test_pro_rata_75_sets_l24_l31_l37(self):
        aggs = [_make_agg(1, "1000.00", "192.50")]
        svc, sess = self._make_svc_with_profile(75.0, aggs)

        result = svc._compute_vat_form_lines(
            session=sess,
            company_id=1,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
        )

        assert result[VAT_RETURN_LINE_L24]["tax"] == Decimal("75.00")
        expected_l31 = (Decimal("192.50") * Decimal("75") / Decimal("100")).quantize(
            Decimal("0.01")
        )
        assert result[VAT_RETURN_LINE_L31]["tax"] == expected_l31
        assert result[VAT_RETURN_LINE_L37]["tax"] == expected_l31

    def test_no_pro_rata_l37_equals_l30(self):
        aggs = [_make_agg(1, "1000.00", "192.50")]
        svc, sess = self._make_svc_with_profile.__func__(
            self,
            pro_rata_pct=None,
            aggs_purchase=aggs,
        ) if False else None, None
        # Use a separate path: no profile at all.
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )
        mock_ptl_repo = MagicMock(spec=PostedTaxLineRepository)
        def _agg(company_id, period_ids, direction=None, **kwargs):
            if direction == "PURCHASE":
                return [_make_agg(1, "1000.00", "192.50")]
            return []
        mock_ptl_repo.aggregate_for_period.side_effect = _agg

        mock_fp = MagicMock()
        mock_fp.start_date = date(2024, 1, 1)
        mock_fp.end_date = date(2024, 1, 31)
        mock_fp.id = 1
        mock_fp_repo = MagicMock()
        mock_fp_repo.list_by_company.return_value = [mock_fp]

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._posted_tax_line_repository_factory = lambda s: mock_ptl_repo
        svc._fiscal_period_repository_factory = lambda s: mock_fp_repo
        svc._company_tax_profile_repository_factory = None

        mock_session = MagicMock()
        mock_session.scalars.return_value = []

        result = svc._compute_vat_form_lines(
            session=mock_session,
            company_id=1,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
        )

        # Without pro-rata, L37 = L30 (gross input).
        assert result[VAT_RETURN_LINE_L37]["tax"] == result[VAT_RETURN_LINE_L30]["tax"]
        # L31 should be zero when no pro-rata.
        assert result[VAT_RETURN_LINE_L31]["tax"] == _zero()


# ──────────────────────────────────────────────────────────────────────
# T35 – VAT return amendments
# ──────────────────────────────────────────────────────────────────────

class TestVATAmendmentTests:
    """T35: amend_vat_return creates a DRAFT return with is_amended=True
    and amends_return_id pointing to the original FILED return."""

    def test_amendment_command_has_correct_fields(self):
        cmd = AmendVATReturnCommand(
            obligation_id=5,
            original_return_id=12,
            notes="Correction of import VAT",
        )
        assert cmd.obligation_id == 5
        assert cmd.original_return_id == 12
        assert cmd.notes == "Correction of import VAT"

    def test_amendment_command_is_immutable(self):
        cmd = AmendVATReturnCommand(obligation_id=1, original_return_id=2)
        with pytest.raises((AttributeError, TypeError)):
            cmd.original_return_id = 99  # type: ignore[misc]

    def test_amend_vat_return_requires_filed_original(self):
        """amend_vat_return raises ValidationError if original is not FILED."""
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )
        from seeker_accounting.platform.exceptions import ValidationError

        # Build minimal mock UOW.
        mock_original = MagicMock()
        mock_original.status_code = RETURN_STATUS_DRAFT  # Not FILED.
        mock_original.id = 7

        mock_return_repo = MagicMock()
        mock_return_repo.get_by_id.return_value = mock_original

        mock_obligation = MagicMock()
        mock_obligation.id = 5
        mock_obligation.tax_type_code = TAX_TYPE_VAT
        mock_obligation.period_start = date(2024, 1, 1)
        mock_obligation.period_end = date(2024, 1, 31)

        mock_obligation_repo = MagicMock()
        mock_obligation_repo.get_by_id.return_value = mock_obligation

        mock_uow = MagicMock()
        mock_uow.__enter__ = lambda s: s
        mock_uow.__exit__ = MagicMock(return_value=False)
        mock_uow.session = MagicMock()

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._unit_of_work_factory = lambda: mock_uow
        svc._app_context = MagicMock()
        svc._app_context.current_user_id = 1
        svc._company_repository_factory = lambda s: MagicMock(
            **{"get_by_id.return_value": MagicMock()}
        )
        svc._tax_return_repository_factory = lambda s: mock_return_repo
        svc._tax_obligation_repository_factory = lambda s: mock_obligation_repo
        svc._permission_service = MagicMock()

        with pytest.raises(ValidationError):
            svc.amend_vat_return(
                company_id=1,
                command=AmendVATReturnCommand(
                    obligation_id=5, original_return_id=7
                ),
            )


# ──────────────────────────────────────────────────────────────────────
# T36 – Credit carry-forward chain
# ──────────────────────────────────────────────────────────────────────

class TestCreditCarryForwardTests:
    """T36: _resolve_credit_brought_forward reads L43 from the most recent
    FILED return and populates L25 / L30 accordingly."""

    def test_resolve_credit_returns_l43_from_latest_filed(self):
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )

        # Build a mock FILED return with an L43 line.
        mock_l43_line = MagicMock()
        mock_l43_line.box_code = VAT_RETURN_LINE_L43
        mock_l43_line.amount = Decimal("350.00")

        mock_filed_return = MagicMock()
        mock_filed_return.id = 1
        mock_filed_return.period_end = date(2023, 12, 31)
        mock_filed_return.lines = [mock_l43_line]

        mock_repo = MagicMock()
        mock_repo.list_by_company.return_value = [mock_filed_return]

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._tax_return_repository_factory = lambda s: mock_repo

        result = svc._resolve_credit_brought_forward(
            session=MagicMock(),
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            exclude_return_id=None,
        )

        assert result == Decimal("350.00")

    def test_resolve_credit_returns_zero_when_no_filed_returns(self):
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )

        mock_repo = MagicMock()
        mock_repo.list_by_company.return_value = []

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._tax_return_repository_factory = lambda s: mock_repo

        result = svc._resolve_credit_brought_forward(
            session=MagicMock(),
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            exclude_return_id=None,
        )

        assert result == _zero()

    def test_credit_bf_appears_in_l25_and_l30(self):
        """When credit_brought_forward > 0, L25 and L30 include it."""
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )

        mock_ptl_repo = MagicMock(spec=PostedTaxLineRepository)
        mock_ptl_repo.aggregate_for_period.return_value = []

        mock_fp = MagicMock()
        mock_fp.start_date = date(2024, 2, 1)
        mock_fp.end_date = date(2024, 2, 29)
        mock_fp.id = 2
        mock_fp_repo = MagicMock()
        mock_fp_repo.list_by_company.return_value = [mock_fp]

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._posted_tax_line_repository_factory = lambda s: mock_ptl_repo
        svc._fiscal_period_repository_factory = lambda s: mock_fp_repo
        svc._company_tax_profile_repository_factory = None

        mock_session = MagicMock()
        mock_session.scalars.return_value = []

        credit_bf = Decimal("500.00")
        result = svc._compute_vat_form_lines(
            session=mock_session,
            company_id=1,
            period_start=date(2024, 2, 1),
            period_end=date(2024, 2, 29),
            credit_brought_forward=credit_bf,
        )

        assert result[VAT_RETURN_LINE_L25]["tax"] == Decimal("500.00")
        # L30 = L25 + L26..L29 = 500 + 0 = 500.
        assert result[VAT_RETURN_LINE_L30]["tax"] == Decimal("500.00")


# ──────────────────────────────────────────────────────────────────────
# T37 – Withholding VAT
# ──────────────────────────────────────────────────────────────────────

class TestWithholdingVATTests:
    """T37: withholding_vat_amount is stored in L45; L47 = L40 - L45."""

    def test_withholding_vat_reduces_l47(self):
        """L47 = L40 - L45 when withholding VAT is present."""
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )
        from seeker_accounting.modules.accounting.reference_data.models.tax_code import (
            TaxCode,
        )

        # Set up 1 sales fact → L17 → L36 = 192.50 → L40 = 192.50.
        mock_tc = MagicMock(spec=TaxCode)
        mock_tc.id = 1
        mock_tc.exemption_kind = None
        mock_tc.is_export = False
        mock_tc.return_box_code = VAT_RETURN_LINE_L17

        mock_ptl_repo = MagicMock(spec=PostedTaxLineRepository)
        def _agg(company_id, period_ids, direction=None, **kwargs):
            if direction == "SALES":
                return [_make_agg(1, "1000.00", "192.50", is_recoverable=None)]
            return []
        mock_ptl_repo.aggregate_for_period.side_effect = _agg

        mock_fp = MagicMock()
        mock_fp.start_date = date(2024, 1, 1)
        mock_fp.end_date = date(2024, 1, 31)
        mock_fp.id = 1
        mock_fp_repo = MagicMock()
        mock_fp_repo.list_by_company.return_value = [mock_fp]

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._posted_tax_line_repository_factory = lambda s: mock_ptl_repo
        svc._fiscal_period_repository_factory = lambda s: mock_fp_repo
        svc._company_tax_profile_repository_factory = None

        mock_session = MagicMock()
        mock_session.scalars.return_value = [mock_tc]

        withholding = Decimal("50.00")
        result = svc._compute_vat_form_lines(
            session=mock_session,
            company_id=1,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            withholding_vat_amount=withholding,
        )

        l40 = result[VAT_RETURN_LINE_L40]["tax"]
        l45 = result[VAT_RETURN_LINE_L45]["tax"]
        l47 = result[VAT_RETURN_LINE_L47]["tax"]

        assert l45 == Decimal("50.00")
        assert l47 == max(_zero(), l40 - withholding)

    def test_withholding_vat_stored_in_l45(self):
        """L45 is exactly the withholding amount passed in."""
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )

        mock_ptl_repo = MagicMock(spec=PostedTaxLineRepository)
        mock_ptl_repo.aggregate_for_period.return_value = []

        mock_fp = MagicMock()
        mock_fp.start_date = date(2024, 1, 1)
        mock_fp.end_date = date(2024, 1, 31)
        mock_fp.id = 1
        mock_fp_repo = MagicMock()
        mock_fp_repo.list_by_company.return_value = [mock_fp]

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._posted_tax_line_repository_factory = lambda s: mock_ptl_repo
        svc._fiscal_period_repository_factory = lambda s: mock_fp_repo
        svc._company_tax_profile_repository_factory = None

        mock_session = MagicMock()
        mock_session.scalars.return_value = []

        result = svc._compute_vat_form_lines(
            session=mock_session,
            company_id=1,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            withholding_vat_amount=Decimal("123.45"),
        )

        assert result[VAT_RETURN_LINE_L45]["tax"] == Decimal("123.45")

    def test_l47_cannot_go_below_zero(self):
        """When withholding > L40, L47 clamps to 0 (over-withheld)."""
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )

        mock_ptl_repo = MagicMock(spec=PostedTaxLineRepository)
        mock_ptl_repo.aggregate_for_period.return_value = []

        mock_fp = MagicMock()
        mock_fp.start_date = date(2024, 1, 1)
        mock_fp.end_date = date(2024, 1, 31)
        mock_fp.id = 1
        mock_fp_repo = MagicMock()
        mock_fp_repo.list_by_company.return_value = [mock_fp]

        svc = TaxReturnService.__new__(TaxReturnService)
        svc._posted_tax_line_repository_factory = lambda s: mock_ptl_repo
        svc._fiscal_period_repository_factory = lambda s: mock_fp_repo
        svc._company_tax_profile_repository_factory = None

        mock_session = MagicMock()
        mock_session.scalars.return_value = []

        result = svc._compute_vat_form_lines(
            session=mock_session,
            company_id=1,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            # L40 will be 0 (no sales), withholding > 0.
            withholding_vat_amount=Decimal("200.00"),
        )

        assert result[VAT_RETURN_LINE_L47]["tax"] == _zero()


# ──────────────────────────────────────────────────────────────────────
# Posted tax line repository — cash-basis filter
# ──────────────────────────────────────────────────────────────────────

class TestPostedTaxLineRepositoryT32Tests:
    """T32: aggregate_for_period accepts payment_date_start/end kwargs."""

    def test_aggregate_accepts_payment_date_kwargs(self):
        """aggregate_for_period signature accepts payment_date kwargs without error."""
        import inspect
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )

        sig = inspect.signature(PostedTaxLineRepository.aggregate_for_period)
        params = sig.parameters
        assert "payment_date_start" in params
        assert "payment_date_end" in params

    def test_empty_returns_when_no_ids_and_no_date_filters(self):
        """Returns empty list when all filter kwargs are absent."""
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )

        repo = PostedTaxLineRepository.__new__(PostedTaxLineRepository)
        result = repo.aggregate_for_period(
            company_id=1,
            fiscal_period_ids=[],
        )
        assert result == []
