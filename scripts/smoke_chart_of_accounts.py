from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

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
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import (
    CreateAccountCommand,
    UpdateAccountCommand,
)
from seeker_accounting.modules.accounting.chart_of_accounts.dto.chart_import_dto import (
    ImportChartTemplateCommand,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_loader import (
    ChartTemplateLoader,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_profile import (
    BUILT_IN_TEMPLATE_CODE_OHADA,
)
from seeker_accounting.modules.accounting.chart_of_accounts.ui.account_form_dialog import (
    AccountFormDialog,
)
from seeker_accounting.modules.accounting.chart_of_accounts.ui.chart_import_dialog import (
    ChartImportDialog,
)
from seeker_accounting.modules.accounting.chart_of_accounts.ui.chart_of_accounts_page import (
    ChartOfAccountsPage,
)
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_code_account_mapping_dto import (
    SetTaxCodeAccountMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import (
    CreateTaxCodeCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.ui.account_role_mapping_dialog import (
    AccountRoleMappingDialog,
)
from seeker_accounting.modules.accounting.reference_data.ui.tax_code_account_mapping_dialog import (
    TaxCodeAccountMappingDialog,
)
from seeker_accounting.modules.accounting.reference_data.ui.tax_codes_page import TaxCodesPage
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.platform.exceptions import ConflictError, ValidationError


OHADA_WORKBOOK_PATH = Path(r"C:\Users\User\Desktop\OHADA Chart of Accounts.xlsx")
CANONICAL_TEMPLATE_PATH = Path("src/seeker_accounting/resources/chart_templates/ohada_syscohada_v1.csv")


@contextmanager
def auto_confirm_message_boxes() -> None:
    original_question = QMessageBox.question

    def _always_yes(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return QMessageBox.StandardButton.Yes

    QMessageBox.question = _always_yes  # type: ignore[assignment]
    try:
        yield
    finally:
        QMessageBox.question = original_question  # type: ignore[assignment]


def main() -> int:
    app = QApplication([])
    bootstrap = bootstrap_script_runtime(app)
    settings = bootstrap.settings
    app_context = bootstrap.app_context
    session_context = bootstrap.session_context
    active_company_context = bootstrap.active_company_context
    navigation_service = bootstrap.navigation_service
    theme_manager = bootstrap.theme_manager
    registry = bootstrap.service_registry

    _ensure_country_and_currency(registry)

    template_loader = ChartTemplateLoader()
    built_in_profile = template_loader.load_built_in_profile(BUILT_IN_TEMPLATE_CODE_OHADA)
    built_in_rows = template_loader.load_built_in_rows(BUILT_IN_TEMPLATE_CODE_OHADA)
    print("built_in_template_profile", built_in_profile.template_code, built_in_profile.row_count)
    print("built_in_template_rows", len(built_in_rows))
    print("canonical_template_exists", CANONICAL_TEMPLATE_PATH.exists())
    print("source_workbook_exists", OHADA_WORKBOOK_PATH.exists())

    primary_company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Chart Smoke Company SARL",
            display_name="Chart Smoke Company",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    secondary_company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Chart Smoke Company Two SARL",
            display_name="Chart Smoke Company Two",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    print("companies_created", primary_company.id, secondary_company.id)

    seed_counts = registry.chart_seed_service.ensure_global_chart_reference_seed()
    print("global_seed", seed_counts[0], seed_counts[1])

    seed_result = registry.chart_seed_service.seed_built_in_chart(primary_company.id)
    print("built_in_seed_imported", seed_result.imported_count, seed_result.skipped_existing_count)

    repeated_seed_result = registry.chart_seed_service.seed_built_in_chart(primary_company.id)
    print(
        "built_in_seed_repeat",
        repeated_seed_result.imported_count,
        repeated_seed_result.skipped_existing_count,
    )

    built_in_preview = registry.chart_template_import_service.preview_import(
        primary_company.id,
        ImportChartTemplateCommand(
            source_kind="built_in",
            template_code=BUILT_IN_TEMPLATE_CODE_OHADA,
            add_missing_only=True,
        ),
    )
    print("preview_built_in", built_in_preview.importable_count, built_in_preview.skipped_existing_count)

    csv_preview = registry.chart_template_import_service.preview_import(
        primary_company.id,
        ImportChartTemplateCommand(
            source_kind="csv",
            file_path=str(CANONICAL_TEMPLATE_PATH),
            add_missing_only=True,
        ),
    )
    print("preview_csv", csv_preview.normalized_row_count, csv_preview.skipped_existing_count)

    if OHADA_WORKBOOK_PATH.exists():
        xlsx_preview = registry.chart_template_import_service.preview_import(
            primary_company.id,
            ImportChartTemplateCommand(
                source_kind="xlsx",
                file_path=str(OHADA_WORKBOOK_PATH),
                add_missing_only=True,
            ),
        )
        print("preview_xlsx", xlsx_preview.normalized_row_count, xlsx_preview.duplicate_source_count)

    seeded_accounts = registry.chart_of_accounts_service.list_accounts(primary_company.id)
    print("seeded_accounts", len(seeded_accounts))
    if not seeded_accounts:
        raise RuntimeError("Built-in chart seed produced no accounts.")

    reference_account = seeded_accounts[0]
    updated_reference = registry.chart_of_accounts_service.update_account(
        primary_company.id,
        reference_account.id,
        UpdateAccountCommand(
            account_code=reference_account.account_code,
            account_name=f"{reference_account.account_name} Custom",
            account_class_id=reference_account.account_class_id,
            account_type_id=reference_account.account_type_id,
            parent_account_id=reference_account.parent_account_id,
            normal_balance=reference_account.normal_balance,
            allow_manual_posting=reference_account.allow_manual_posting,
            is_control_account=reference_account.is_control_account,
            is_active=reference_account.is_active,
        ),
    )
    import_result = registry.chart_template_import_service.import_add_missing(
        primary_company.id,
        ImportChartTemplateCommand(
            source_kind="built_in",
            template_code=BUILT_IN_TEMPLATE_CODE_OHADA,
            add_missing_only=True,
        ),
    )
    preserved_reference = registry.chart_of_accounts_service.get_account(primary_company.id, reference_account.id)
    print("import_conflicts", import_result.conflict_count)
    print("import_preserved_name", preserved_reference.account_name == updated_reference.account_name)

    registry.company_context_service.clear_active_company()
    main_window = MainWindow(registry)
    main_window.show()
    app.processEvents()

    chart_page = _get_page(main_window, nav_ids.CHART_OF_ACCOUNTS, ChartOfAccountsPage, app)
    print("chart_page_no_active", chart_page._stack.currentWidget() is chart_page._no_active_company_state)

    active_company = registry.company_context_service.set_active_company(primary_company.id)
    app.processEvents()
    print("active_company_set", active_company.company_id, active_company.company_name)
    print("chart_page_ready", chart_page._stack.currentWidget() is chart_page._tree_surface)

    account_classes = registry.reference_data_service.list_account_classes()
    account_types = registry.reference_data_service.list_account_types()
    if not account_classes or not account_types:
        raise RuntimeError("Account classes or account types are unavailable.")

    existing_codes = {
        account.account_code
        for account in registry.chart_of_accounts_service.list_accounts(primary_company.id)
    }
    parent_code = _unique_code("99990010", existing_codes)
    existing_codes.add(parent_code)
    child_code = _unique_code("99990011", existing_codes)
    existing_codes.add(child_code)
    foreign_parent_code = _unique_code("88880010", existing_codes)

    parent_dialog = AccountFormDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.display_name,
        parent=chart_page,
    )
    _prepare_account_dialog(
        parent_dialog,
        account_code=parent_code,
        account_name="Manual Parent Account",
        account_class_id=account_classes[0].id,
        account_type_id=account_types[0].id,
    )
    parent_dialog._handle_submit()
    parent_account = parent_dialog.saved_account
    if parent_account is None:
        raise RuntimeError("Manual parent account was not created.")
    print("account_created_parent", parent_account.id, parent_account.account_code)

    child_dialog = AccountFormDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.display_name,
        parent=chart_page,
    )
    _prepare_account_dialog(
        child_dialog,
        account_code=child_code,
        account_name="Manual Child Account",
        account_class_id=account_classes[0].id,
        account_type_id=account_types[0].id,
        parent_account_id=parent_account.id,
    )
    child_dialog._handle_submit()
    child_account = child_dialog.saved_account
    if child_account is None:
        raise RuntimeError("Manual child account was not created.")
    print("account_created_child", child_account.id, child_account.parent_account_id)

    duplicate_dialog = AccountFormDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.display_name,
        parent=chart_page,
    )
    _prepare_account_dialog(
        duplicate_dialog,
        account_code=parent_code,
        account_name="Duplicate Code Account",
        account_class_id=account_classes[0].id,
        account_type_id=account_types[0].id,
    )
    duplicate_dialog._handle_submit()
    duplicate_blocked = "already exists" in duplicate_dialog._error_label.text().lower()
    print("duplicate_account_blocked", duplicate_blocked)
    if not duplicate_blocked:
        raise RuntimeError("Duplicate account code was not blocked.")

    other_account = registry.chart_of_accounts_service.create_account(
        secondary_company.id,
        CreateAccountCommand(
            account_code=foreign_parent_code,
            account_name="Foreign Parent Account",
            account_class_id=account_classes[0].id,
            account_type_id=account_types[0].id,
            normal_balance=account_types[0].normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    print("foreign_account_created", other_account.id, other_account.company_id)

    try:
        registry.chart_of_accounts_service.create_account(
            primary_company.id,
            CreateAccountCommand(
                account_code=_unique_code("99990012", existing_codes),
                account_name="Invalid Foreign Parent Account",
                account_class_id=account_classes[0].id,
                account_type_id=account_types[0].id,
                normal_balance=account_types[0].normal_balance,
                allow_manual_posting=True,
                is_control_account=False,
                parent_account_id=other_account.id,
            ),
        )
    except ValidationError as exc:
        print("foreign_parent_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Cross-company parent validation did not block the invalid account.")

    parent_detail = registry.chart_of_accounts_service.get_account(primary_company.id, parent_account.id)
    try:
        registry.chart_of_accounts_service.update_account(
            primary_company.id,
            parent_account.id,
            UpdateAccountCommand(
                account_code=parent_detail.account_code,
                account_name=parent_detail.account_name,
                account_class_id=parent_detail.account_class_id,
                account_type_id=parent_detail.account_type_id,
                parent_account_id=parent_account.id,
                normal_balance=parent_detail.normal_balance,
                allow_manual_posting=parent_detail.allow_manual_posting,
                is_control_account=parent_detail.is_control_account,
                is_active=parent_detail.is_active,
            ),
        )
    except ValidationError as exc:
        print("self_parent_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Self-parent validation did not block the invalid update.")

    try:
        registry.chart_of_accounts_service.update_account(
            primary_company.id,
            parent_account.id,
            UpdateAccountCommand(
                account_code=parent_detail.account_code,
                account_name=parent_detail.account_name,
                account_class_id=parent_detail.account_class_id,
                account_type_id=parent_detail.account_type_id,
                parent_account_id=child_account.id,
                normal_balance=parent_detail.normal_balance,
                allow_manual_posting=parent_detail.allow_manual_posting,
                is_control_account=parent_detail.is_control_account,
                is_active=parent_detail.is_active,
            ),
        )
    except ValidationError as exc:
        print("descendant_cycle_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Descendant cycle validation did not block the invalid update.")

    edit_dialog = AccountFormDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.display_name,
        account_id=child_account.id,
        parent=chart_page,
    )
    edit_dialog._account_name_edit.setText("Manual Child Account Updated")
    edit_dialog._notes_edit.setPlainText("Updated from smoke script")
    edit_dialog._handle_submit()
    updated_child = edit_dialog.saved_account
    if updated_child is None:
        raise RuntimeError("Manual child account was not updated.")
    print("account_updated", updated_child.id, updated_child.account_name)

    chart_page.reload_accounts(selected_account_id=updated_child.id)
    app.processEvents()
    with auto_confirm_message_boxes():
        chart_page._deactivate_selected_account()
    app.processEvents()
    deactivated_child = registry.chart_of_accounts_service.get_account(primary_company.id, updated_child.id)
    print("account_deactivated", not deactivated_child.is_active)

    import_dialog = ChartImportDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.display_name,
        parent=chart_page,
    )
    import_dialog._handle_preview()
    print("dialog_preview_built_in", import_dialog._preview_result is not None)

    import_dialog._source_kind_combo.setCurrentIndex(import_dialog._source_kind_combo.findData("csv"))
    import_dialog._sync_source_fields()
    import_dialog._file_path_edit.setText(str(CANONICAL_TEMPLATE_PATH))
    import_dialog._handle_preview()
    print("dialog_preview_csv", import_dialog._preview_result is not None)

    if OHADA_WORKBOOK_PATH.exists():
        import_dialog._source_kind_combo.setCurrentIndex(import_dialog._source_kind_combo.findData("xlsx"))
        import_dialog._sync_source_fields()
        import_dialog._file_path_edit.setText(str(OHADA_WORKBOOK_PATH))
        import_dialog._handle_preview()
        print("dialog_preview_xlsx", import_dialog._preview_result is not None)

    import_missing_dialog = ChartImportDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.display_name,
        parent=chart_page,
    )
    import_missing_dialog._handle_import()
    if import_missing_dialog.import_result is None:
        raise RuntimeError("Chart import dialog did not produce an import result.")
    print(
        "dialog_import_missing_only",
        import_missing_dialog.import_result.imported_count,
        import_missing_dialog.import_result.skipped_existing_count,
    )

    active_accounts = registry.chart_of_accounts_service.list_accounts(primary_company.id, active_only=True)
    if len(active_accounts) < 3:
        raise RuntimeError("Not enough active accounts were available for mapping validation.")

    role_dialog = AccountRoleMappingDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.display_name,
        parent=chart_page,
    )
    role_mapping = role_dialog._selected_mapping()
    if role_mapping is None:
        raise RuntimeError("Role mapping dialog did not load any role rows.")
    role_dialog._account_combo.setCurrentIndex(role_dialog._account_combo.findData(active_accounts[0].id))
    role_dialog._save_mapping()
    saved_role_mapping = registry.account_role_mapping_service.list_role_mappings(primary_company.id)[0]
    print("account_role_mapped", saved_role_mapping.role_code, saved_role_mapping.account_id)

    role_dialog._account_combo.setCurrentIndex(role_dialog._account_combo.findData(active_accounts[1].id))
    role_dialog._save_mapping()
    updated_role_mapping = registry.account_role_mapping_service.list_role_mappings(primary_company.id)[0]
    print("account_role_updated", updated_role_mapping.account_id == active_accounts[1].id)

    tax_code = registry.tax_setup_service.create_tax_code(
        primary_company.id,
        CreateTaxCodeCommand(
            code="VAT_STD",
            name="Standard VAT",
            tax_type_code="VAT",
            calculation_method_code="PERCENTAGE",
            rate_percent=Decimal("19.2500"),
            is_recoverable=True,
            effective_from=date(2026, 1, 1),
        ),
    )
    print("tax_code_created", tax_code.id, tax_code.code)

    tax_codes_page = _get_page(main_window, nav_ids.TAX_CODES, TaxCodesPage, app)
    print("tax_codes_page_ready", tax_codes_page._stack.currentWidget() is not tax_codes_page._no_active_company_state)

    tax_mapping_dialog = TaxCodeAccountMappingDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.display_name,
        parent=tax_codes_page,
    )
    tax_mapping_dialog.reload_mappings(selected_tax_code_id=tax_code.id)
    tax_mapping_dialog._sales_account_combo.setCurrentIndex(
        tax_mapping_dialog._sales_account_combo.findData(active_accounts[0].id)
    )
    tax_mapping_dialog._purchase_account_combo.setCurrentIndex(
        tax_mapping_dialog._purchase_account_combo.findData(active_accounts[1].id)
    )
    tax_mapping_dialog._tax_liability_account_combo.setCurrentIndex(
        tax_mapping_dialog._tax_liability_account_combo.findData(active_accounts[2].id)
    )
    tax_mapping_dialog._save_mapping()
    saved_tax_mapping = registry.tax_setup_service.get_tax_code_account_mapping(primary_company.id, tax_code.id)
    print("tax_mapping_saved", saved_tax_mapping.tax_code_id, saved_tax_mapping.sales_account_id)

    tax_mapping_dialog._tax_asset_account_combo.setCurrentIndex(
        tax_mapping_dialog._tax_asset_account_combo.findData(active_accounts[0].id)
    )
    tax_mapping_dialog._save_mapping()
    updated_tax_mapping = registry.tax_setup_service.get_tax_code_account_mapping(primary_company.id, tax_code.id)
    print("tax_mapping_updated", updated_tax_mapping.tax_asset_account_id == active_accounts[0].id)

    chart_page._search_edit.setText(parent_code)
    app.processEvents()
    print("chart_search_filtered", "shown of" in chart_page._record_count_label.text())

    main_window.close()
    app.quit()
    return 0


def _ensure_country_and_currency(registry: object) -> None:
    with registry.session_context.unit_of_work_factory() as uow:  # type: ignore[attr-defined]
        session = uow.session
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        if session.get(Country, "CM") is None:
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if session.get(Currency, "XAF") is None:
            session.add(
                Currency(
                    code="XAF",
                    name="Central African CFA franc",
                    symbol="FCFA",
                    decimal_places=0,
                    is_active=True,
                )
            )
        uow.commit()


def _unique_code(base_code: str, existing_codes: set[str]) -> str:
    code = base_code
    counter = 1
    while code in existing_codes:
        code = f"{base_code}{counter}"
        counter += 1
    return code


def _prepare_account_dialog(
    dialog: AccountFormDialog,
    *,
    account_code: str,
    account_name: str,
    account_class_id: int,
    account_type_id: int,
    parent_account_id: int | None = None,
) -> None:
    dialog._account_code_edit.setText(account_code)
    dialog._account_name_edit.setText(account_name)

    class_index = dialog._account_class_combo.findData(account_class_id)
    if class_index < 0:
        raise RuntimeError(f"Account class {account_class_id} was not available in the dialog.")
    dialog._account_class_combo.setCurrentIndex(class_index)

    type_index = dialog._account_type_combo.findData(account_type_id)
    if type_index < 0:
        raise RuntimeError(f"Account type {account_type_id} was not available in the dialog.")
    dialog._account_type_combo.setCurrentIndex(type_index)

    parent_index = dialog._parent_account_combo.findData(parent_account_id)
    dialog._parent_account_combo.setCurrentIndex(parent_index if parent_index >= 0 else 0)


def _get_page(main_window: MainWindow, nav_id: str, page_type: type, app: QApplication) -> object:
    main_window._service_registry.navigation_service.navigate(nav_id)  # type: ignore[attr-defined]
    app.processEvents()
    page = main_window.findChild(page_type)
    if page is None:
        raise RuntimeError(f"Page {page_type.__name__} could not be located.")
    return page


if __name__ == "__main__":
    raise SystemExit(main())
