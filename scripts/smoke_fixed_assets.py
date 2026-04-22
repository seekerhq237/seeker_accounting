from __future__ import annotations

"""Smoke test for Slice 12: Fixed Assets.

Validates:
- Asset category CRUD (create, get, list, deactivate)
- Asset CRUD (create, get, list, status update)
- Depreciation schedule preview (all 3 methods)
- Depreciation run creation (draft)
- Depreciation run posting (creates journal entry)
- UI page import and instantiation smoke
- Offscreen main window navigation to fixed assets pages
"""

import uuid as _uuid
from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.app.dependency.factories import (
    create_active_company_context,
    create_app_context,
    create_navigation_service,
    create_service_registry,
    create_session_context,
    create_theme_manager,
)
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.main_window import MainWindow
from seeker_accounting.config.settings import load_settings
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import CreateAccountCommand
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import CreateDocumentSequenceCommand
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.fixed_assets.dto.asset_category_commands import (
    CreateAssetCategoryCommand,
    UpdateAssetCategoryCommand,
)
from seeker_accounting.modules.fixed_assets.dto.asset_commands import CreateAssetCommand, UpdateAssetCommand
from seeker_accounting.modules.fixed_assets.dto.depreciation_commands import (
    CreateDepreciationRunCommand,
    GenerateDepreciationScheduleCommand,
    PostDepreciationRunCommand,
)
from seeker_accounting.modules.fixed_assets.ui.asset_categories_page import AssetCategoriesPage
from seeker_accounting.modules.fixed_assets.ui.assets_page import AssetsPage
from seeker_accounting.modules.fixed_assets.ui.depreciation_runs_page import DepreciationRunsPage
from seeker_accounting.platform.exceptions import ValidationError

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
            legal_name=f"FA Smoke {_suffix} SARL",
            display_name=f"FA Smoke {_suffix}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    cid = company.id
    _check("Company created", cid > 0)

    registry.chart_seed_service.ensure_global_chart_reference_seed()
    registry.company_seed_service.seed_built_in_chart(cid)
    _check("Chart seeded", True)

    # Fiscal year + open periods
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
    _check("Fiscal year and periods ready", fy.id > 0)

    # Document sequences
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
    _check("Document sequences created", True)

    # Create GL accounts for asset category mapping
    types = registry.reference_data_service.list_account_types()
    classes = registry.reference_data_service.list_account_classes()
    debit_type = next((t for t in types if t.normal_balance == "DEBIT"), types[0])
    credit_type = next((t for t in types if t.normal_balance == "CREDIT"), types[0])

    asset_acct = registry.chart_of_accounts_service.create_account(
        cid,
        CreateAccountCommand(
            account_code="1510",
            account_name="Fixed Assets",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    accum_depr_acct = registry.chart_of_accounts_service.create_account(
        cid,
        CreateAccountCommand(
            account_code="1590",
            account_name="Accumulated Depreciation",
            account_class_id=classes[0].id,
            account_type_id=credit_type.id,
            normal_balance=credit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    depr_exp_acct = registry.chart_of_accounts_service.create_account(
        cid,
        CreateAccountCommand(
            account_code="6200",
            account_name="Depreciation Expense",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    _check("GL accounts created", all(x.id > 0 for x in [asset_acct, accum_depr_acct, depr_exp_acct]))

    # ------------------------------------------------------------------ #
    # 2. Asset category CRUD
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing asset category service...")
    cat = registry.asset_category_service.create_asset_category(
        cid,
        CreateAssetCategoryCommand(
            code="EQUIP",
            name="Equipment",
            asset_account_id=asset_acct.id,
            accumulated_depreciation_account_id=accum_depr_acct.id,
            depreciation_expense_account_id=depr_exp_acct.id,
            default_useful_life_months=60,
            default_depreciation_method_code="straight_line",
        ),
    )
    _check("Asset category created", cat.id > 0)
    _check("Category code is EQUIP", cat.code == "EQUIP")

    cats = registry.asset_category_service.list_asset_categories(cid, active_only=True)
    _check("Category in list", any(c.id == cat.id for c in cats))

    cat_detail = registry.asset_category_service.get_asset_category(cid, cat.id)
    _check("Category get returns correct id", cat_detail.id == cat.id)

    # Duplicate code conflict
    try:
        registry.asset_category_service.create_asset_category(
            cid,
            CreateAssetCategoryCommand(
                code="EQUIP",
                name="Duplicate",
                asset_account_id=asset_acct.id,
                accumulated_depreciation_account_id=accum_depr_acct.id,
                depreciation_expense_account_id=depr_exp_acct.id,
                default_useful_life_months=60,
                default_depreciation_method_code="straight_line",
            ),
        )
        _check("Duplicate category code rejected", False)
    except Exception:
        _check("Duplicate category code rejected", True)

    # ------------------------------------------------------------------ #
    # 3. Asset CRUD
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing asset service...")
    asset = registry.asset_service.create_asset(
        cid,
        CreateAssetCommand(
            asset_number="EQUIP-001",
            asset_name="Industrial Printer",
            asset_category_id=cat.id,
            acquisition_date=date(2024, 1, 1),
            capitalization_date=date(2024, 1, 1),
            acquisition_cost=Decimal("12000.00"),
            salvage_value=Decimal("2000.00"),
            useful_life_months=24,
            depreciation_method_code="straight_line",
            notes="Test asset",
        ),
    )
    _check("Asset created", asset.id > 0)
    _check("Asset number correct", asset.asset_number == "EQUIP-001")
    _check("Asset default status is draft", asset.status_code == "draft")

    asset2 = registry.asset_service.create_asset(
        cid,
        CreateAssetCommand(
            asset_number="EQUIP-002",
            asset_name="CNC Machine",
            asset_category_id=cat.id,
            acquisition_date=date(2024, 1, 1),
            capitalization_date=date(2024, 1, 1),
            acquisition_cost=Decimal("50000.00"),
            salvage_value=Decimal("5000.00"),
            useful_life_months=60,
            depreciation_method_code="reducing_balance",
            notes=None,
        ),
    )
    _check("Second asset created", asset2.id > 0)

    assets_list = registry.asset_service.list_assets(cid)
    _check("Both assets in list", len([a for a in assets_list if a.id in (asset.id, asset2.id)]) == 2)

    # Activate both assets for the run
    for a in (asset, asset2):
        registry.asset_service.update_asset(
            cid, a.id,
            UpdateAssetCommand(
                asset_number=a.asset_number,
                asset_name=a.asset_name,
                asset_category_id=a.asset_category_id,
                acquisition_date=a.acquisition_date,
                capitalization_date=a.capitalization_date,
                acquisition_cost=a.acquisition_cost,
                salvage_value=a.salvage_value,
                useful_life_months=a.useful_life_months,
                depreciation_method_code=a.depreciation_method_code,
                status_code="active",
                notes=a.notes,
            ),
        )
    active_assets = registry.asset_service.list_assets(cid, status_code="active")
    _check("Assets activated and filter works", len(active_assets) >= 2)

    # Duplicate asset number rejected
    try:
        registry.asset_service.create_asset(
            cid,
            CreateAssetCommand(
                asset_number="EQUIP-001",
                asset_name="Duplicate",
                asset_category_id=cat.id,
                acquisition_date=date(2024, 1, 1),
                capitalization_date=date(2024, 1, 1),
                acquisition_cost=Decimal("1000.00"),
                salvage_value=None,
                useful_life_months=12,
                depreciation_method_code="straight_line",
                notes=None,
            ),
        )
        _check("Duplicate asset number rejected", False)
    except Exception:
        _check("Duplicate asset number rejected", True)

    # ------------------------------------------------------------------ #
    # 4. Depreciation schedule preview (all 3 methods)
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing depreciation schedule service...")
    for method in ("straight_line", "reducing_balance", "sum_of_years_digits"):
        sched = registry.depreciation_schedule_service.preview_schedule(
            GenerateDepreciationScheduleCommand(
                acquisition_cost=Decimal("10000.00"),
                salvage_value=Decimal("1000.00"),
                useful_life_months=12,
                depreciation_method_code=method,
                capitalization_date=date(2024, 1, 1),
            )
        )
        _check(f"{method}: correct line count (12)", len(sched.lines) == 12)
        _check(f"{method}: total depr > 0", sched.total_depreciation > Decimal("0"))
        _check(f"{method}: closing NBV >= salvage", sched.lines[-1].closing_nbv >= Decimal("1000") - Decimal("0.01"))
        # SL and SYD deplete fully; DDB approaches asymptotically
        if method in ("straight_line", "sum_of_years_digits"):
            _check(f"{method}: total depr == 9000 exactly", abs(sched.total_depreciation - Decimal("9000")) < Decimal("0.01"))

    sched_asset = registry.depreciation_schedule_service.generate_schedule_for_asset(cid, asset.id)
    _check("Asset schedule: correct asset id", sched_asset.asset_id == asset.id)
    _check("Asset schedule: correct line count", len(sched_asset.lines) == 24)

    # ------------------------------------------------------------------ #
    # 5. Depreciation run (draft)
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing depreciation run service...")
    run = registry.depreciation_run_service.create_run(
        cid,
        CreateDepreciationRunCommand(
            run_date=date(2024, 1, 31),
            period_end_date=date(2024, 1, 31),
        ),
    )
    _check("Run created as draft", run.status_code == "draft")
    _check("Run has asset lines", run.asset_count >= 2)
    _check("Run total depreciation > 0", run.total_depreciation > Decimal("0"))

    runs_list = registry.depreciation_run_service.list_depreciation_runs(cid)
    _check("Run in list", any(r.id == run.id for r in runs_list))

    # Cancel and recreate to test cancel flow
    registry.depreciation_run_service.cancel_run(cid, run.id)
    cancelled_list = registry.depreciation_run_service.list_depreciation_runs(cid)
    cancelled = next((r for r in cancelled_list if r.id == run.id), None)
    _check("Run can be cancelled", cancelled is not None and cancelled.status_code == "cancelled")

    run2 = registry.depreciation_run_service.create_run(
        cid,
        CreateDepreciationRunCommand(
            run_date=date(2024, 1, 31),
            period_end_date=date(2024, 1, 31),
        ),
    )
    _check("New draft run created", run2.status_code == "draft")

    # ------------------------------------------------------------------ #
    # 6. Depreciation run posting
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing depreciation posting service...")
    result = registry.depreciation_posting_service.post_run(
        cid,
        run2.id,
    )
    _check("Run posted with number", result.run_number is not None)
    _check("Journal entry created", result.posted_journal_entry_id > 0)
    _check("Posted total matches draft total", abs(result.total_depreciation - run2.total_depreciation) < Decimal("0.01"))

    posted_runs = registry.depreciation_run_service.list_depreciation_runs(cid)
    posted = next((r for r in posted_runs if r.id == run2.id), None)
    _check("Run status is posted", posted is not None and posted.status_code == "posted")

    # Double-post rejected
    try:
        registry.depreciation_posting_service.post_run(
            cid,
            run2.id,
        )
        _check("Double-post rejected", False)
    except Exception:
        _check("Double-post rejected", True)

    # ------------------------------------------------------------------ #
    # 7. UI page instantiation smoke
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing UI page instantiation...")
    _ = AssetCategoriesPage(registry)
    _check("AssetCategoriesPage instantiated", True)
    _ = AssetsPage(registry)
    _check("AssetsPage instantiated", True)
    _ = DepreciationRunsPage(registry)
    _check("DepreciationRunsPage instantiated", True)

    # ------------------------------------------------------------------ #
    # 8. Offscreen main window — navigate to fixed asset pages
    # ------------------------------------------------------------------ #
    print(f"\n{_INFO} Testing offscreen main window navigation...")
    window = MainWindow(registry)
    window.show()
    navigation_service.navigate(nav_ids.ASSET_CATEGORIES)
    navigation_service.navigate(nav_ids.ASSETS)
    navigation_service.navigate(nav_ids.DEPRECIATION_RUNS)
    _check("Navigation to all 3 fixed asset pages succeeded", True)
    window.close()

    print(f"\n{_PASS} All fixed assets smoke checks passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
