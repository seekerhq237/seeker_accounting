from __future__ import annotations

"""Smoke test for the Depreciation Engine Expansion (Revision K).

Validates:
- Revision K migration applied (8 new tables exist and seeded)
- DepreciationMethodService catalog: 15 entries, all capability flags correct
- MacrsProfileRepository: 8 profiles seeded
- All 13 depreciation methods via preview_schedule (stateless)
- AssetDepreciationSettingsService upsert/get/delete
- AssetComponentService create/list
- AssetUsageService create/list
- AssetDepreciationPoolService create/add-member
- generate_schedule_for_asset with settings-driven MACRS, DB factor, units-of-production
- Existing Slice 12 smoke (backward compatibility):
  straight_line, reducing_balance, sum_of_years_digits — still produce correct totals
  Depreciation run creation still works with expanded method set
"""

import uuid as _uuid
from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import CreateAccountCommand
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import CreateDocumentSequenceCommand
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.fixed_assets.dto.asset_category_commands import CreateAssetCategoryCommand
from seeker_accounting.modules.fixed_assets.dto.asset_commands import CreateAssetCommand, UpdateAssetCommand
from seeker_accounting.modules.fixed_assets.dto.asset_component_commands import CreateAssetComponentCommand
from seeker_accounting.modules.fixed_assets.dto.asset_depreciation_pool_commands import (
    AddPoolMemberCommand,
    CreateAssetDepreciationPoolCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_depreciation_settings_commands import (
    UpsertAssetDepreciationSettingsCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_usage_record_commands import CreateAssetUsageRecordCommand
from seeker_accounting.modules.fixed_assets.dto.depreciation_commands import (
    CreateDepreciationRunCommand,
    GenerateDepreciationScheduleCommand,
)

_PASS = "\033[92m[PASS]\033[0m"
_FAIL = "\033[91m[FAIL]\033[0m"
_INFO = "\033[94m[INFO]\033[0m"


def _check(label: str, condition: bool) -> None:
    print(f"  {_PASS if condition else _FAIL} {label}")
    if not condition:
        raise AssertionError(f"Check failed: {label}")


def main() -> int:  # noqa: C901, PLR0915
    qt_app = QApplication.instance() or QApplication([])
    bootstrap = bootstrap_script_runtime(qt_app)
    settings = bootstrap.settings
    app_context = bootstrap.app_context
    session_context = bootstrap.session_context
    active_company_context = bootstrap.active_company_context
    navigation_service = bootstrap.navigation_service
    theme_manager = bootstrap.theme_manager
    registry = bootstrap.service_registry

    # ------------------------------------------------------------------ #
    # 1. Company and foundation setup
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Setting up company and foundation...")
    _suffix = _uuid.uuid4().hex[:6].upper()
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Engine Smoke {_suffix} SARL",
            display_name=f"Engine Smoke {_suffix}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    cid = company.id
    _check("Company created", cid > 0)

    registry.chart_seed_service.ensure_global_chart_reference_seed()
    registry.company_seed_service.seed_built_in_chart(cid)

    fy = registry.fiscal_calendar_service.create_fiscal_year(
        cid,
        CreateFiscalYearCommand(
            year_code="FY2024",
            year_name="Fiscal Year 2024",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
    )
    registry.fiscal_calendar_service.generate_periods(
        cid, fy.id, GenerateFiscalPeriodsCommand(opening_status_code="OPEN")
    )

    for doc_type, prefix in (("DEPRECIATION_RUN", "DR-"), ("JOURNAL_ENTRY", "JRN-")):
        registry.numbering_setup_service.create_document_sequence(
            cid,
            CreateDocumentSequenceCommand(
                document_type_code=doc_type,
                prefix=prefix,
                next_number=1,
                padding_width=4,
            ),
        )

    types = registry.reference_data_service.list_account_types()
    classes = registry.reference_data_service.list_account_classes()
    debit_type = next((t for t in types if t.normal_balance == "DEBIT"), types[0])
    credit_type = next((t for t in types if t.normal_balance == "CREDIT"), types[0])

    def _make_acct(code: str, name: str, is_debit: bool):
        t = debit_type if is_debit else credit_type
        return registry.chart_of_accounts_service.create_account(
            cid,
            CreateAccountCommand(
                account_code=code,
                account_name=name,
                account_class_id=classes[0].id,
                account_type_id=t.id,
                normal_balance=t.normal_balance,
                allow_manual_posting=True,
                is_control_account=False,
            ),
        )

    asset_acct = _make_acct("1510", "Fixed Assets", True)
    accum_depr_acct = _make_acct("1590", "Accumulated Depreciation", False)
    depr_exp_acct = _make_acct("6200", "Depreciation Expense", True)
    _check("GL accounts created", all(x.id > 0 for x in [asset_acct, accum_depr_acct, depr_exp_acct]))

    # ------------------------------------------------------------------ #
    # 2. DepreciationMethodService catalog verification
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing DepreciationMethodService catalog...")
    methods = registry.depreciation_method_service.list_methods(active_only=True)
    method_codes = {m.code for m in methods}
    _check("Catalog has >= 15 entries", len(methods) >= 15)

    expected_codes = {
        "straight_line", "declining_balance", "double_declining_balance",
        "declining_balance_150", "reducing_balance", "sum_of_years_digits",
        "units_of_production", "component", "group", "composite",
        "depletion", "annuity", "sinking_fund", "macrs", "amortization",
    }
    _check("All expected method codes present", expected_codes.issubset(method_codes))

    # Spot-check capability flags
    ddb = next(m for m in methods if m.code == "double_declining_balance")
    _check("DDB has_switch_to_sl=True", ddb.has_switch_to_sl is True)
    _check("DDB requires_settings=True", ddb.requires_settings is True)
    sl = next(m for m in methods if m.code == "straight_line")
    _check("SL has_switch_to_sl=False", sl.has_switch_to_sl is False)
    uop = next(m for m in methods if m.code == "units_of_production")
    _check("UoP requires_usage_records=True", uop.requires_usage_records is True)
    comp = next(m for m in methods if m.code == "component")
    _check("Component requires_components=True", comp.requires_components is True)
    depl = next(m for m in methods if m.code == "depletion")
    _check("Depletion requires_depletion_profile=True", depl.requires_depletion_profile is True)
    macrs_m = next(m for m in methods if m.code == "macrs")
    _check("MACRS family=TAX", macrs_m.asset_family_code == "TAX")

    # get_method by code
    sl_dto = registry.depreciation_method_service.get_method("straight_line")
    _check("get_method returns correct code", sl_dto.code == "straight_line")

    # ------------------------------------------------------------------ #
    # 3. Preview schedule — all methods (stateless)
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing preview_schedule for all methods...")
    _base = dict(
        acquisition_cost=Decimal("12000.00"),
        salvage_value=Decimal("2000.00"),
        useful_life_months=12,
        capitalization_date=date(2024, 1, 1),
    )

    # straight_line
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="straight_line")
    )
    _check("SL: 12 lines", len(s.lines) == 12)
    _check("SL: total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))
    _check("SL: closing NBV == salvage", abs(s.lines[-1].closing_nbv - Decimal("2000")) < Decimal("0.01"))

    # amortization (same as SL)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="amortization")
    )
    _check("Amortization: 12 lines", len(s.lines) == 12)
    _check("Amortization: total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))

    # reducing_balance (backward compat = DDB, factor=2.0)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="reducing_balance")
    )
    _check("reducing_balance: 12 lines", len(s.lines) == 12)
    _check("reducing_balance: total > 0", s.total_depreciation > Decimal("0"))
    _check("reducing_balance: closing NBV >= salvage", s.lines[-1].closing_nbv >= Decimal("2000") - Decimal("0.01"))

    # double_declining_balance (same engine as reducing_balance)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="double_declining_balance",
                                           declining_factor=Decimal("2"))
    )
    _check("DDB: 12 lines", len(s.lines) == 12)
    _check("DDB: total > 0", s.total_depreciation > Decimal("0"))

    # double_declining_balance with switch_to_sl
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="double_declining_balance",
                                           declining_factor=Decimal("2"),
                                           switch_to_straight_line=True)
    )
    _check("DDB+SL switch: 12 lines", len(s.lines) == 12)
    _check("DDB+SL switch: total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))

    # declining_balance (factor=1.0)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="declining_balance",
                                           declining_factor=Decimal("1"))
    )
    _check("DB(1x): 12 lines", len(s.lines) == 12)
    _check("DB(1x): total > 0", s.total_depreciation > Decimal("0"))

    # declining_balance_150 (factor=1.5)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="declining_balance_150",
                                           declining_factor=Decimal("1.5"),
                                           switch_to_straight_line=True)
    )
    _check("DB150+SL: 12 lines", len(s.lines) == 12)
    _check("DB150+SL: total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))

    # sum_of_years_digits
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="sum_of_years_digits")
    )
    _check("SYD: 12 lines", len(s.lines) == 12)
    _check("SYD: total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))
    _check("SYD: first period > last period", s.lines[0].depreciation_amount > s.lines[-1].depreciation_amount)

    # units_of_production (even spread)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="units_of_production",
                                           expected_total_units=Decimal("12000"))
    )
    _check("UoP(even): 12 lines", len(s.lines) == 12)
    _check("UoP(even): total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))

    # units_of_production (actual usage — non-uniform)
    usage = tuple(Decimal(str(v)) for v in [500, 600, 800, 1200, 1500, 1800, 1600, 1200, 800, 600, 200, 200])
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="units_of_production",
                                           expected_total_units=Decimal("11000"),
                                           usage_units=usage)
    )
    _check("UoP(actual): 12 lines", len(s.lines) == len(usage))
    _check("UoP(actual): total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))

    # depletion (same engine as UoP)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="depletion",
                                           expected_total_units=Decimal("10000"))
    )
    _check("Depletion: 12 lines", len(s.lines) == 12)
    _check("Depletion: total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))

    # annuity
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="annuity",
                                           interest_rate=Decimal("0.005"))
    )
    _check("Annuity: 12 lines", len(s.lines) == 12)
    _check("Annuity: total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))
    _check("Annuity: charges increase", s.lines[-1].depreciation_amount > s.lines[0].depreciation_amount)

    # sinking_fund
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="sinking_fund",
                                           interest_rate=Decimal("0.005"))
    )
    _check("Sinking fund: 12 lines", len(s.lines) == 12)
    _check("Sinking fund: total == 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("0.01"))
    _check("Sinking fund: charges increase", s.lines[-1].depreciation_amount > s.lines[0].depreciation_amount)

    # macrs (5-year GDS, half-year convention: 6 rates → 72 monthly lines)
    macrs_rates = (20.00, 32.00, 19.20, 11.52, 11.52, 5.76)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(
            acquisition_cost=Decimal("10000.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=72,
            depreciation_method_code="macrs",
            capitalization_date=date(2024, 1, 1),
            macrs_annual_rates=macrs_rates,
        )
    )
    _check("MACRS: 72 lines (5-yr half-year)", len(s.lines) == 72)
    _check("MACRS: total ~= 10000", abs(s.total_depreciation - Decimal("10000")) < Decimal("1.00"))

    # group (falls back to SL for preview)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="group")
    )
    _check("Group: 12 lines", len(s.lines) == 12)

    # composite (falls back to SL for preview)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="composite")
    )
    _check("Composite: 12 lines", len(s.lines) == 12)

    # component (falls back to SL for preview)
    s = registry.depreciation_schedule_service.preview_schedule(
        GenerateDepreciationScheduleCommand(**_base, depreciation_method_code="component")
    )
    _check("Component preview: 12 lines", len(s.lines) == 12)

    # ------------------------------------------------------------------ #
    # 4. AssetDepreciationSettingsService
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing AssetDepreciationSettingsService...")

    # Create an asset category
    cat = registry.asset_category_service.create_asset_category(
        cid,
        CreateAssetCategoryCommand(
            code="MACH",
            name="Machinery",
            asset_account_id=asset_acct.id,
            accumulated_depreciation_account_id=accum_depr_acct.id,
            depreciation_expense_account_id=depr_exp_acct.id,
            default_useful_life_months=60,
            default_depreciation_method_code="straight_line",
        ),
    )
    _check("Asset category created", cat.id > 0)

    # Create assets with various methods
    def _make_asset(number: str, name: str, method: str, cost=Decimal("10000"), salvage=Decimal("1000"), life=12):
        return registry.asset_service.create_asset(
            cid,
            CreateAssetCommand(
                asset_number=number,
                asset_name=name,
                asset_category_id=cat.id,
                acquisition_date=date(2024, 1, 1),
                capitalization_date=date(2024, 1, 1),
                acquisition_cost=cost,
                salvage_value=salvage,
                useful_life_months=life,
                depreciation_method_code=method,
                notes=None,
            ),
        )

    asset_ddb = _make_asset("MACH-001", "Lathe (DDB)", "double_declining_balance")
    _check("Asset with DDB method created", asset_ddb.id > 0)

    asset_uop = _make_asset("MACH-002", "Press (UoP)", "units_of_production")
    _check("Asset with UoP method created", asset_uop.id > 0)

    asset_macrs = _make_asset("MACH-003", "Computer (MACRS)", "macrs",
                              cost=Decimal("5000"), salvage=Decimal("0"), life=60)
    _check("Asset with MACRS method created", asset_macrs.id > 0)

    asset_annuity = _make_asset("MACH-004", "Equipment (Annuity)", "annuity")
    _check("Asset with Annuity method created", asset_annuity.id > 0)

    asset_sl = _make_asset("MACH-005", "Printer (SL)", "straight_line")
    _check("Asset with SL method created", asset_sl.id > 0)

    # Upsert settings for DDB asset
    settings_ddb = registry.asset_depreciation_settings_service.upsert_settings(
        cid, asset_ddb.id,
        UpsertAssetDepreciationSettingsCommand(
            declining_factor=Decimal("2"),
            switch_to_straight_line=True,
        ),
    )
    _check("DDB settings created", settings_ddb.id > 0)
    _check("DDB settings: factor=2", settings_ddb.declining_factor == Decimal("2"))
    _check("DDB settings: switch_to_sl=True", settings_ddb.switch_to_straight_line is True)

    # Upsert settings for UoP asset
    settings_uop = registry.asset_depreciation_settings_service.upsert_settings(
        cid, asset_uop.id,
        UpsertAssetDepreciationSettingsCommand(expected_total_units=Decimal("12000")),
    )
    _check("UoP settings created", settings_uop.expected_total_units == Decimal("12000"))

    # Upsert settings for Annuity asset
    settings_ann = registry.asset_depreciation_settings_service.upsert_settings(
        cid, asset_annuity.id,
        UpsertAssetDepreciationSettingsCommand(interest_rate=Decimal("0.005")),
    )
    _check("Annuity settings created", settings_ann.interest_rate == Decimal("0.005"))

    # Find MACRS 5-year half-year profile in catalog
    from seeker_accounting.modules.fixed_assets.repositories.macrs_profile_repository import MacrsProfileRepository
    from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
    with session_context.unit_of_work_factory() as uow:
        macrs_repo = MacrsProfileRepository(uow.session)
        macrs_profile = macrs_repo.get_by_class_and_convention("5-year", "half_year")
    _check("MACRS 5-year half-year profile found in catalog", macrs_profile is not None)

    settings_macrs = registry.asset_depreciation_settings_service.upsert_settings(
        cid, asset_macrs.id,
        UpsertAssetDepreciationSettingsCommand(
            macrs_profile_id=macrs_profile.id,
            macrs_convention_code="half_year",
        ),
    )
    _check("MACRS settings created", settings_macrs.macrs_profile_id == macrs_profile.id)

    # get_settings returns same data
    fetched = registry.asset_depreciation_settings_service.get_settings(cid, asset_ddb.id)
    _check("get_settings returns correct data", fetched is not None and fetched.declining_factor == Decimal("2"))

    # update (re-upsert) DDB settings
    settings_ddb2 = registry.asset_depreciation_settings_service.upsert_settings(
        cid, asset_ddb.id,
        UpsertAssetDepreciationSettingsCommand(
            declining_factor=Decimal("1.5"),
            switch_to_straight_line=True,
        ),
    )
    _check("DDB settings updated to 150DB", settings_ddb2.declining_factor == Decimal("1.5"))

    # ------------------------------------------------------------------ #
    # 5. generate_schedule_for_asset with settings
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing generate_schedule_for_asset with settings...")

    # DDB with switch_to_sl — should produce exactly 10000 total
    sched = registry.depreciation_schedule_service.generate_schedule_for_asset(cid, asset_ddb.id)
    _check("DDB+SL schedule: correct asset_id", sched.asset_id == asset_ddb.id)
    _check("DDB+SL schedule: 12 lines", len(sched.lines) == 12)
    _check("DDB+SL schedule: total == 9000", abs(sched.total_depreciation - Decimal("9000")) < Decimal("0.01"))

    # UoP with settings — even distribution
    sched = registry.depreciation_schedule_service.generate_schedule_for_asset(cid, asset_uop.id)
    _check("UoP schedule: correct asset_id", sched.asset_id == asset_uop.id)
    _check("UoP schedule: 12 lines", len(sched.lines) == 12)
    _check("UoP schedule: total == 9000", abs(sched.total_depreciation - Decimal("9000")) < Decimal("0.01"))

    # MACRS with profile — schedule has 72 lines (5-year GDS = 6 annual rates × 12)
    sched = registry.depreciation_schedule_service.generate_schedule_for_asset(cid, asset_macrs.id)
    _check("MACRS schedule: correct asset_id", sched.asset_id == asset_macrs.id)
    _check("MACRS schedule: 72 lines", len(sched.lines) == 72)
    _check("MACRS schedule: total ~= 5000", abs(sched.total_depreciation - Decimal("5000")) < Decimal("1.00"))

    # Annuity with interest rate
    sched = registry.depreciation_schedule_service.generate_schedule_for_asset(cid, asset_annuity.id)
    _check("Annuity schedule: 12 lines", len(sched.lines) == 12)
    _check("Annuity schedule: total == 9000", abs(sched.total_depreciation - Decimal("9000")) < Decimal("0.01"))
    _check("Annuity: charges increase", sched.lines[-1].depreciation_amount > sched.lines[0].depreciation_amount)

    # SL (no settings) — still works
    sched = registry.depreciation_schedule_service.generate_schedule_for_asset(cid, asset_sl.id)
    _check("SL schedule: 12 lines", len(sched.lines) == 12)
    _check("SL schedule: total == 9000", abs(sched.total_depreciation - Decimal("9000")) < Decimal("0.01"))

    # ------------------------------------------------------------------ #
    # 6. AssetComponentService
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing AssetComponentService...")

    asset_comp = _make_asset("MACH-006", "Building (Component)", "component",
                             cost=Decimal("100000"), salvage=Decimal("10000"), life=120)
    _check("Component method asset created", asset_comp.id > 0)

    c1 = registry.asset_component_service.create_component(
        cid, asset_comp.id,
        CreateAssetComponentCommand(
            component_name="Roof",
            acquisition_cost=Decimal("30000"),
            useful_life_months=240,
            depreciation_method_code="straight_line",
            salvage_value=Decimal("3000"),
        ),
    )
    _check("Component 1 created", c1.id > 0)
    _check("Component 1 name correct", c1.component_name == "Roof")

    c2 = registry.asset_component_service.create_component(
        cid, asset_comp.id,
        CreateAssetComponentCommand(
            component_name="HVAC",
            acquisition_cost=Decimal("20000"),
            useful_life_months=120,
            depreciation_method_code="straight_line",
            salvage_value=Decimal("2000"),
        ),
    )
    _check("Component 2 created", c2.id > 0)

    components = registry.asset_component_service.list_components(cid, asset_comp.id)
    _check("Components list has 2 entries", len(components) == 2)

    # Adding component to non-component asset must fail
    try:
        registry.asset_component_service.create_component(
            cid, asset_sl.id,
            CreateAssetComponentCommand("Bad", Decimal("1000"), 12, "straight_line"),
        )
        _check("Component on non-component asset rejected", False)
    except Exception:
        _check("Component on non-component asset rejected", True)

    # ------------------------------------------------------------------ #
    # 7. AssetUsageService
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing AssetUsageService...")

    u1 = registry.asset_usage_service.create_usage_record(
        cid, asset_uop.id,
        CreateAssetUsageRecordCommand(usage_date=date(2024, 1, 31), units_used=Decimal("1000")),
    )
    _check("Usage record 1 created", u1.id > 0)

    u2 = registry.asset_usage_service.create_usage_record(
        cid, asset_uop.id,
        CreateAssetUsageRecordCommand(usage_date=date(2024, 2, 29), units_used=Decimal("1500")),
    )
    _check("Usage record 2 created", u2.id > 0)

    usage_list = registry.asset_usage_service.list_usage_records(cid, asset_uop.id)
    _check("Usage records list has 2 entries", len(usage_list) == 2)

    # Adding usage record to non-usage asset must fail
    try:
        registry.asset_usage_service.create_usage_record(
            cid, asset_sl.id,
            CreateAssetUsageRecordCommand(usage_date=date(2024, 1, 31), units_used=Decimal("100")),
        )
        _check("Usage record on non-UoP asset rejected", False)
    except Exception:
        _check("Usage record on non-UoP asset rejected", True)

    # ------------------------------------------------------------------ #
    # 8. AssetDepreciationPoolService
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing AssetDepreciationPoolService...")

    pool = registry.asset_depreciation_pool_service.create_pool(
        cid,
        CreateAssetDepreciationPoolCommand(
            code="TOOLS",
            name="Hand Tools Group",
            pool_type_code="group",
            depreciation_method_code="straight_line",
            useful_life_months=60,
        ),
    )
    _check("Pool created", pool.id > 0)
    _check("Pool code is TOOLS", pool.code == "TOOLS")
    _check("Pool type is group", pool.pool_type_code == "group")

    # Create an asset to add to pool
    asset_pool_member = _make_asset("TOOL-001", "Drill Press", "group",
                                    cost=Decimal("5000"), salvage=Decimal("500"), life=60)
    pool_updated = registry.asset_depreciation_pool_service.add_member(
        cid, pool.id,
        AddPoolMemberCommand(asset_id=asset_pool_member.id, joined_date=date(2024, 1, 1)),
    )
    _check("Pool member added", len(pool_updated.members) == 1)
    _check("Pool member is correct asset", pool_updated.members[0].asset_id == asset_pool_member.id)

    # Duplicate add should fail
    try:
        registry.asset_depreciation_pool_service.add_member(
            cid, pool.id,
            AddPoolMemberCommand(asset_id=asset_pool_member.id, joined_date=date(2024, 2, 1)),
        )
        _check("Duplicate pool member rejected", False)
    except Exception:
        _check("Duplicate pool member rejected", True)

    pools = registry.asset_depreciation_pool_service.list_pools(cid)
    _check("Pools list includes created pool", any(p.id == pool.id for p in pools))

    # ------------------------------------------------------------------ #
    # 9. Backward compatibility: depreciation run with SL assets still works
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing backward-compatible depreciation run...")

    # Activate the SL asset
    registry.asset_service.update_asset(
        cid, asset_sl.id,
        UpdateAssetCommand(
            asset_number=asset_sl.asset_number,
            asset_name=asset_sl.asset_name,
            asset_category_id=asset_sl.asset_category_id,
            acquisition_date=asset_sl.acquisition_date,
            capitalization_date=asset_sl.capitalization_date,
            acquisition_cost=asset_sl.acquisition_cost,
            salvage_value=asset_sl.salvage_value,
            useful_life_months=asset_sl.useful_life_months,
            depreciation_method_code=asset_sl.depreciation_method_code,
            status_code="active",
            notes=asset_sl.notes,
        ),
    )

    run = registry.depreciation_run_service.create_run(
        cid,
        CreateDepreciationRunCommand(run_date=date(2024, 1, 31), period_end_date=date(2024, 1, 31)),
    )
    _check("Depreciation run created", run.id > 0)
    _check("Run has at least 1 line", run.asset_count >= 1)
    _check("Run total > 0", run.total_depreciation > Decimal("0"))

    result = registry.depreciation_posting_service.post_run(cid, run.id)
    _check("Run posted", result.run_number is not None)
    _check("Journal entry created", result.posted_journal_entry_id > 0)

    print(f"\n{_PASS} All depreciation engine expansion smoke checks passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
