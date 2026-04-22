from __future__ import annotations

from contextlib import suppress
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
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import (
    SeedBuiltInChartCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.ui.fiscal_periods_page import (
    FiscalPeriodsPage,
)
from seeker_accounting.modules.accounting.journals.dto.journal_commands import (
    CreateJournalEntryCommand,
    JournalLineCommand,
    UpdateJournalEntryCommand,
)
from seeker_accounting.modules.accounting.journals.ui.journals_page import JournalsPage
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.platform.exceptions import ConflictError, PeriodLockedError, ValidationError


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

    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Slice Six Smoke Company SARL",
            display_name="Slice Six Smoke Company",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    print("company_created", company.id, company.display_name)

    registry.chart_seed_service.ensure_global_chart_reference_seed()
    registry.company_seed_service.seed_built_in_chart(company.id)
    print("chart_seeded", company.id)

    registry.numbering_setup_service.create_document_sequence(
        company.id,
        CreateDocumentSequenceCommand(
            document_type_code="JOURNAL_ENTRY",
            prefix="JRN-",
            next_number=1,
            padding_width=4,
        ),
    )
    print("journal_sequence_created", company.id)

    fiscal_year = registry.fiscal_calendar_service.create_fiscal_year(
        company.id,
        CreateFiscalYearCommand(
            year_code="FY2026",
            year_name="Fiscal Year 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        ),
    )
    print("fiscal_year_created", fiscal_year.id, fiscal_year.year_code)

    try:
        registry.fiscal_calendar_service.create_fiscal_year(
            company.id,
            CreateFiscalYearCommand(
                year_code="FY2026-ALT",
                year_name="Overlapping Year",
                start_date=date(2026, 6, 1),
                end_date=date(2027, 5, 31),
            ),
        )
    except ConflictError as exc:
        print("overlap_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Overlapping fiscal year was not blocked.")

    calendar = registry.fiscal_calendar_service.generate_periods(
        company.id,
        fiscal_year.id,
        GenerateFiscalPeriodsCommand(),
    )
    print("periods_generated", len(calendar.periods))

    try:
        registry.fiscal_calendar_service.generate_periods(
            company.id,
            fiscal_year.id,
            GenerateFiscalPeriodsCommand(),
        )
    except ConflictError as exc:
        print("duplicate_generation_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Duplicate period generation was not blocked.")

    current_period = registry.period_control_service.validate_posting_date(company.id, date(2026, 1, 15))
    print("posting_date_validated", current_period.period_code, current_period.status_code)

    first_period = calendar.periods[0]
    second_period = calendar.periods[1]
    close_result = registry.period_control_service.close_period(company.id, first_period.id)
    print("period_closed", close_result.period_code, close_result.status_code)
    reopen_result = registry.period_control_service.reopen_period(company.id, first_period.id)
    print("period_reopened", reopen_result.period_code, reopen_result.status_code)
    close_second = registry.period_control_service.close_period(company.id, second_period.id)
    lock_second = registry.period_control_service.lock_period(company.id, second_period.id)
    print("period_locked", lock_second.period_code, lock_second.status_code)

    with suppress(Exception):
        registry.period_control_service.validate_posting_date(company.id, date(2025, 12, 31))

    try:
        registry.period_control_service.open_period(company.id, second_period.id)
    except PeriodLockedError as exc:
        print("locked_period_status_change_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Locked period ordinary status change was not blocked.")

    accounts = [
        account
        for account in registry.chart_of_accounts_service.list_accounts(company.id, active_only=True)
        if account.allow_manual_posting
    ]
    if len(accounts) < 2:
        raise RuntimeError("At least two manual-posting accounts are required for journal smoke validation.")
    debit_account = accounts[0]
    credit_account = accounts[1]

    try:
        registry.journal_service.create_draft_journal(
            company.id,
            CreateJournalEntryCommand(
                entry_date=date(2026, 1, 15),
                journal_type_code="GENERAL",
                lines=(
                    JournalLineCommand(account_id=debit_account.id, debit_amount=Decimal("50.00")),
                ),
            ),
        )
    except ValidationError as exc:
        print("invalid_lines_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Structurally invalid journal lines were not blocked.")

    unbalanced_draft = registry.journal_service.create_draft_journal(
        company.id,
        CreateJournalEntryCommand(
            entry_date=date(2026, 1, 15),
            journal_type_code="GENERAL",
            reference_text="UNBAL-1",
            description="Unbalanced draft",
            lines=(
                JournalLineCommand(account_id=debit_account.id, debit_amount=Decimal("100.00")),
                JournalLineCommand(account_id=credit_account.id, credit_amount=Decimal("90.00")),
            ),
        ),
    )
    print("unbalanced_draft_saved", unbalanced_draft.id, unbalanced_draft.totals.is_balanced)

    try:
        registry.journal_posting_service.post_journal(company.id, unbalanced_draft.id)
    except ValidationError as exc:
        print("unbalanced_post_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Unbalanced journal was not blocked from posting.")

    balanced_draft = registry.journal_service.update_draft_journal(
        company.id,
        unbalanced_draft.id,
        UpdateJournalEntryCommand(
            entry_date=date(2026, 1, 15),
            journal_type_code="GENERAL",
            reference_text="BAL-1",
            description="Balanced draft",
            lines=(
                JournalLineCommand(account_id=debit_account.id, debit_amount=Decimal("100.00")),
                JournalLineCommand(account_id=credit_account.id, credit_amount=Decimal("100.00")),
            ),
        ),
    )
    print("balanced_draft_updated", balanced_draft.id, balanced_draft.totals.is_balanced)

    registry.period_control_service.close_period(company.id, first_period.id)
    try:
        registry.journal_posting_service.post_journal(company.id, balanced_draft.id)
    except ValidationError as exc:
        print("closed_period_post_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Posting into a closed period was not blocked.")

    registry.period_control_service.reopen_period(company.id, first_period.id)
    post_result = registry.journal_posting_service.post_journal(company.id, balanced_draft.id)
    print("journal_posted", post_result.journal_entry_id, post_result.entry_number, post_result.status_code)

    posted_entry = registry.journal_service.get_journal_entry(company.id, balanced_draft.id)
    print("posted_entry_immutable_status", posted_entry.status_code)

    try:
        registry.journal_service.update_draft_journal(
            company.id,
            posted_entry.id,
            UpdateJournalEntryCommand(
                entry_date=posted_entry.entry_date,
                journal_type_code=posted_entry.journal_type_code,
                reference_text=posted_entry.reference_text,
                description=posted_entry.description,
                lines=(
                    JournalLineCommand(account_id=debit_account.id, debit_amount=Decimal("100.00")),
                    JournalLineCommand(account_id=credit_account.id, credit_amount=Decimal("100.00")),
                ),
            ),
        )
    except ValidationError as exc:
        print("posted_update_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Posted journal was editable through the draft path.")

    locked_period_draft = registry.journal_service.create_draft_journal(
        company.id,
        CreateJournalEntryCommand(
            entry_date=date(2026, 2, 15),
            journal_type_code="GENERAL",
            reference_text="LOCK-1",
            description="Locked period draft",
            lines=(
                JournalLineCommand(account_id=debit_account.id, debit_amount=Decimal("75.00")),
                JournalLineCommand(account_id=credit_account.id, credit_amount=Decimal("75.00")),
            ),
        ),
    )
    try:
        registry.journal_posting_service.post_journal(company.id, locked_period_draft.id)
    except PeriodLockedError as exc:
        print("locked_period_post_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Posting into a locked period was not blocked.")

    registry.company_context_service.clear_active_company()
    main_window = MainWindow(registry)
    main_window.show()
    app.processEvents()

    fiscal_page = _get_page(main_window, nav_ids.FISCAL_PERIODS, FiscalPeriodsPage, app)
    journals_page = _get_page(main_window, nav_ids.JOURNALS, JournalsPage, app)
    print("fiscal_page_no_active", fiscal_page._stack.currentWidget() is fiscal_page._no_active_company_state)
    print("journals_page_no_active", journals_page._stack.currentWidget() is journals_page._no_active_company_state)

    active_company = registry.company_context_service.set_active_company(company.id)
    app.processEvents()
    print("active_company_set", active_company.company_id, active_company.company_name)
    print("fiscal_page_ready", fiscal_page._stack.currentWidget() is fiscal_page._workspace_surface)
    print("journals_page_ready", journals_page._stack.currentWidget() is journals_page._table_surface)

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


def _get_page(main_window: MainWindow, nav_id: str, page_type: type, app: QApplication) -> object:
    main_window._service_registry.navigation_service.navigate(nav_id)  # type: ignore[attr-defined]
    app.processEvents()
    page = main_window.findChild(page_type)
    if page is None:
        raise RuntimeError(f"Page {page_type.__name__} could not be located.")
    return page


if __name__ == "__main__":
    raise SystemExit(main())
