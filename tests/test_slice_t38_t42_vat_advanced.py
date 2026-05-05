"""Tests for T38-T42 VAT advanced slices.

T38: Capital-goods scheme service (register, dispose, annual adjustments).
T39: Excise + lodging constants present.
T40: PostedTaxLine drill-down repo method.
T41: VAT exception report service finds draft documents.
T42: included_in_return_id column present on PostedTaxLine model.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ── T39: constants ────────────────────────────────────────────────────────────

class TestT39LodgingExciseConstants:
    def test_lodging_constant_exists(self):
        from seeker_accounting.modules.taxation.constants import TAX_TYPE_LODGING
        assert TAX_TYPE_LODGING == "LODGING"

    def test_excise_constant_exists(self):
        from seeker_accounting.modules.taxation.constants import TAX_TYPE_EXCISE
        assert TAX_TYPE_EXCISE == "EXCISE"

    def test_lodging_in_all_tax_types(self):
        from seeker_accounting.modules.taxation.constants import (
            TAX_TYPE_LODGING,
            ALL_TAX_TYPE_CODES,
        )
        assert TAX_TYPE_LODGING in ALL_TAX_TYPE_CODES


# ── T42: model column ─────────────────────────────────────────────────────────

class TestT42PostedTaxLineColumn:
    def test_included_in_return_id_column_exists(self):
        from seeker_accounting.modules.taxation.models.posted_tax_line import PostedTaxLine
        assert hasattr(PostedTaxLine, "included_in_return_id")

    def test_column_is_nullable(self):
        from seeker_accounting.modules.taxation.models.posted_tax_line import PostedTaxLine
        col = PostedTaxLine.__table__.c["included_in_return_id"]
        assert col.nullable is True


# ── T38: VatCapitalGood model ─────────────────────────────────────────────────

class TestT38CapitalGoodModel:
    def test_model_table_name(self):
        from seeker_accounting.modules.taxation.models.vat_capital_good import VatCapitalGood
        assert VatCapitalGood.__tablename__ == "vat_capital_goods_register"

    def test_model_has_expected_columns(self):
        from seeker_accounting.modules.taxation.models.vat_capital_good import VatCapitalGood
        cols = {c.name for c in VatCapitalGood.__table__.c}
        expected = {
            "id", "company_id", "asset_description", "acquisition_date",
            "base_amount", "vat_recovered_initial", "monitored_years",
            "status_code", "disposal_date", "fixed_asset_id",
        }
        assert expected.issubset(cols)


# ── T38: VatCapitalGoodsService ───────────────────────────────────────────────

class TestT38CapitalGoodsService:
    def _make_service(self, assets=None):
        from seeker_accounting.modules.taxation.services.vat_capital_goods_service import (
            VatCapitalGoodsService,
        )
        from seeker_accounting.modules.taxation.models.vat_capital_good import VatCapitalGood

        mock_session = MagicMock()
        mock_repo = MagicMock()
        mock_profile_repo = MagicMock()

        if assets is None:
            mock_repo.list_active.return_value = []
        else:
            mock_repo.list_active.return_value = assets

        mock_profile = MagicMock()
        mock_profile.vat_pro_rata_percent = None
        mock_profile_repo.get_by_company.return_value = mock_profile

        uow = MagicMock()
        uow.session = mock_session
        uow.__enter__ = lambda s: s
        uow.__exit__ = MagicMock(return_value=False)

        uow_factory = MagicMock(return_value=uow)

        repo_factory = MagicMock(return_value=mock_repo)
        profile_repo_factory = MagicMock(return_value=mock_profile_repo)

        svc = VatCapitalGoodsService(
            uow_factory=uow_factory,
            capital_good_repo_factory=repo_factory,
            tax_profile_repo_factory=profile_repo_factory,
        )
        return svc, mock_repo, mock_profile_repo

    def test_empty_adjustments_when_no_assets(self):
        svc, _, _ = self._make_service(assets=[])
        result = svc.compute_annual_adjustments(company_id=1, calendar_year=2025)
        assert result == []

    def test_asset_within_monitoring_window_produces_adjustment(self):
        from seeker_accounting.modules.taxation.models.vat_capital_good import VatCapitalGood

        asset = MagicMock(spec=VatCapitalGood)
        asset.id = 1
        asset.company_id = 1
        asset.asset_description = "Server rack"
        asset.acquisition_date = datetime.date(2022, 1, 1)
        asset.base_amount = Decimal("1000000.00")
        asset.vat_recovered_initial = Decimal("175000.00")  # 17.5% VAT
        asset.monitored_years = 5
        asset.status_code = "ACTIVE"
        asset.disposal_date = None
        asset.fixed_asset_id = None
        asset.notes = None

        svc, _, mock_profile_repo = self._make_service(assets=[asset])
        # Year 3 of monitoring (2022 + 3 = 2025), pro-rata 80% (company changed)
        # Initial was 100%, current is 80%
        # annual_vat = 175000 / 5 = 35000
        # adjustment = 35000 * (80 - 100) / 100 = -7000 (further clawback)

        result = svc.compute_annual_adjustments(
            company_id=1,
            calendar_year=2025,
            current_pro_rata_pct=80.0,
        )
        assert len(result) == 1
        adj = result[0]
        assert adj.capital_good_id == 1
        assert adj.year_number == 3
        assert adj.calendar_year == 2025
        assert adj.base_annual_vat == Decimal("35000.00")
        assert adj.adjustment_amount < Decimal("0")  # clawback (under-recovery)

    def test_asset_outside_monitoring_window_excluded(self):
        from seeker_accounting.modules.taxation.models.vat_capital_good import VatCapitalGood

        asset = MagicMock(spec=VatCapitalGood)
        asset.acquisition_date = datetime.date(2015, 1, 1)  # 10 years ago
        asset.monitored_years = 5
        asset.vat_recovered_initial = Decimal("50000.00")

        svc, _, _ = self._make_service(assets=[asset])
        result = svc.compute_annual_adjustments(company_id=1, calendar_year=2025)
        assert result == []

    def test_validate_command_rejects_zero_base(self):
        from seeker_accounting.modules.taxation.services.vat_capital_goods_service import (
            VatCapitalGoodsService,
        )
        from seeker_accounting.modules.taxation.dto.capital_goods_dto import (
            RegisterCapitalGoodCommand,
        )
        from seeker_accounting.platform.exceptions import ValidationError

        svc, _, _ = self._make_service()
        cmd = RegisterCapitalGoodCommand(
            asset_description="Test",
            acquisition_date=datetime.date(2024, 1, 1),
            base_amount=Decimal("0"),
            vat_recovered_initial=Decimal("0"),
        )
        with pytest.raises(ValidationError):
            svc.register(company_id=1, command=cmd)

    def test_validate_command_rejects_empty_description(self):
        from seeker_accounting.modules.taxation.services.vat_capital_goods_service import (
            VatCapitalGoodsService,
        )
        from seeker_accounting.modules.taxation.dto.capital_goods_dto import (
            RegisterCapitalGoodCommand,
        )
        from seeker_accounting.platform.exceptions import ValidationError

        svc, _, _ = self._make_service()
        cmd = RegisterCapitalGoodCommand(
            asset_description="   ",
            acquisition_date=datetime.date(2024, 1, 1),
            base_amount=Decimal("500000"),
            vat_recovered_initial=Decimal("87500"),
        )
        with pytest.raises(ValidationError):
            svc.register(company_id=1, command=cmd)


# ── T37 customer withholds_vat column ─────────────────────────────────────────

class TestT37CustomerWithholdsVAT:
    def test_customer_model_has_withholds_vat(self):
        from seeker_accounting.modules.customers.models.customer import Customer
        assert hasattr(Customer, "withholds_vat")

    def test_withholds_vat_is_boolean(self):
        from seeker_accounting.modules.customers.models.customer import Customer
        col = Customer.__table__.c["withholds_vat"]
        assert str(col.type).upper() == "BOOLEAN"


# ── T40: repo list_facts_for_line signature ───────────────────────────────────

class TestT40DrillDownRepo:
    def test_method_exists_on_repo(self):
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        assert hasattr(PostedTaxLineRepository, "list_facts_for_line")

    def test_method_signature_accepts_return_box_code(self):
        import inspect
        from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
            PostedTaxLineRepository,
        )
        sig = inspect.signature(PostedTaxLineRepository.list_facts_for_line)
        assert "return_box_code" in sig.parameters

    def test_dialog_module_importable(self):
        # Ensure no import errors in the new dialog file.
        import importlib
        mod = importlib.import_module(
            "seeker_accounting.modules.taxation.ui.vat_line_drilldown_dialog"
        )
        assert hasattr(mod, "VATLineDrillDownDialog")


# ── T41: exception report service ─────────────────────────────────────────────

class TestT41VATExceptionReport:
    def test_service_importable(self):
        from seeker_accounting.modules.taxation.services.vat_exception_report_service import (
            VATExceptionReportService,
            VATExceptionItem,
        )
        assert VATExceptionReportService is not None
        assert VATExceptionItem is not None

    def test_exception_item_fields(self):
        from seeker_accounting.modules.taxation.services.vat_exception_report_service import (
            VATExceptionItem,
        )
        item = VATExceptionItem(
            exception_type="DRAFT_DOCUMENT",
            document_type="SALES_INVOICE",
            document_id=1,
            document_number="INV-001",
            document_date=datetime.date(2025, 1, 15),
            total_amount=Decimal("118000"),
            detail="Invoice is unposted.",
        )
        assert item.exception_type == "DRAFT_DOCUMENT"
        assert item.document_type == "SALES_INVOICE"

    def test_service_finds_draft_invoices(self):
        """Service with a mocked session should return draft invoice exceptions."""
        from seeker_accounting.modules.taxation.services.vat_exception_report_service import (
            VATExceptionReportService,
        )
        from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice

        mock_invoice = MagicMock(spec=SalesInvoice)
        mock_invoice.id = 10
        mock_invoice.invoice_number = "INV-2025-001"
        mock_invoice.invoice_date = datetime.date(2025, 1, 5)
        mock_invoice.total_amount = Decimal("59000")

        mock_session = MagicMock()
        # 6 bucket calls: draft invoices, draft bills, foreign-currency invoices,
        # foreign-currency bills, missing-tax-code invoices, missing-tax-code bills.
        mock_session.scalars.side_effect = [
            iter([mock_invoice]),  # draft sales invoices
            iter([]),              # draft purchase bills
            iter([]),              # foreign-currency sales invoices
            iter([]),              # foreign-currency purchase bills
            iter([]),              # missing-tax-code sales invoices
            iter([]),              # missing-tax-code purchase bills
        ]

        uow = MagicMock()
        uow.session = mock_session
        uow.__enter__ = lambda s: s
        uow.__exit__ = MagicMock(return_value=False)
        uow_factory = MagicMock(return_value=uow)

        perm = MagicMock()
        perm.require_permission = MagicMock()

        svc = VATExceptionReportService(
            uow_factory=uow_factory,
            permission_service=perm,
        )

        items = svc.list_exceptions(
            company_id=1,
            period_start=datetime.date(2025, 1, 1),
            period_end=datetime.date(2025, 1, 31),
        )
        # At minimum, the draft invoice should appear
        draft_items = [i for i in items if i.exception_type == "DRAFT_DOCUMENT"]
        assert len(draft_items) >= 1
        assert draft_items[0].document_number == "INV-2025-001"
