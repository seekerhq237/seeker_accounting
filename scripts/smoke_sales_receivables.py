from __future__ import annotations

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
    CreateAccountCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import (
    CreatePaymentTermCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_code_account_mapping_dto import (
    SetTaxCodeAccountMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import (
    CreateTaxCodeCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerCommand,
    CreateCustomerGroupCommand,
)
from seeker_accounting.modules.sales.dto.customer_receipt_commands import (
    CreateCustomerReceiptCommand,
    CustomerReceiptAllocationCommand,
    UpdateCustomerReceiptCommand,
)
from seeker_accounting.modules.sales.dto.sales_invoice_commands import (
    CreateSalesInvoiceCommand,
    SalesInvoiceLineCommand,
    UpdateSalesInvoiceCommand,
)
from seeker_accounting.modules.sales.ui.customer_receipts_page import CustomerReceiptsPage
from seeker_accounting.modules.sales.ui.sales_invoices_page import SalesInvoicesPage
from seeker_accounting.modules.treasury.dto.financial_account_commands import (
    CreateFinancialAccountCommand,
)
from seeker_accounting.platform.exceptions import PeriodLockedError, ValidationError


def main() -> int:  # noqa: C901, PLR0915
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

    # ------------------------------------------------------------------
    # 1. Company + chart seed + foundational reference data
    # ------------------------------------------------------------------
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Slice Eight Smoke SARL",
            display_name="Slice Eight Smoke",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    print("company_created", company.id, company.display_name)

    registry.chart_seed_service.ensure_global_chart_reference_seed()
    registry.company_seed_service.seed_built_in_chart(company.id)
    print("chart_seeded", company.id)

    term = registry.reference_data_service.create_payment_term(
        company.id,
        CreatePaymentTermCommand(code="NET30", name="Net 30", days_due=30),
    )

    group = registry.customer_service.create_customer_group(
        company.id,
        CreateCustomerGroupCommand(code="RETAIL", name="Retail Customers"),
    )

    customer = registry.customer_service.create_customer(
        company.id,
        CreateCustomerCommand(
            customer_code="CUST-001",
            display_name="Douala Retail Shop",
            customer_group_id=group.id,
            payment_term_id=term.id,
            country_code="CM",
        ),
    )
    print("customer_created", customer.id, customer.customer_code)

    # ------------------------------------------------------------------
    # 2. Fiscal year + periods
    # ------------------------------------------------------------------
    fiscal_year = registry.fiscal_calendar_service.create_fiscal_year(
        company.id,
        CreateFiscalYearCommand(
            year_code="FY2026",
            year_name="Fiscal Year 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        ),
    )
    registry.fiscal_calendar_service.generate_periods(
        company.id, fiscal_year.id, GenerateFiscalPeriodsCommand()
    )
    print("fiscal_year_and_periods_created", fiscal_year.id)

    # ------------------------------------------------------------------
    # 3. Document sequences
    # ------------------------------------------------------------------
    for doc_type, prefix in (
        ("JOURNAL_ENTRY", "JRN-"),
        ("SALES_INVOICE", "SI-"),
        ("CUSTOMER_RECEIPT", "CR-"),
    ):
        registry.numbering_setup_service.create_document_sequence(
            company.id,
            CreateDocumentSequenceCommand(
                document_type_code=doc_type,
                prefix=prefix,
                next_number=1,
                padding_width=4,
            ),
        )
    print("document_sequences_created")

    # ------------------------------------------------------------------
    # 4. Accounts (AR control, revenue, tax liability, bank GL)
    # ------------------------------------------------------------------
    accounts = registry.chart_of_accounts_service.list_accounts(company.id, active_only=True)
    types = registry.reference_data_service.list_account_types()
    classes = registry.reference_data_service.list_account_classes()
    if not classes or not types:
        raise RuntimeError("Account classes or types not available.")
    debit_type = next((t for t in types if t.normal_balance == "DEBIT"), types[0])
    credit_type = next((t for t in types if t.normal_balance == "CREDIT"), types[0])

    ar_account = registry.chart_of_accounts_service.create_account(
        company.id,
        CreateAccountCommand(
            account_code="1200",
            account_name="Accounts Receivable Control",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=True,
        ),
    )
    registry.account_role_mapping_service.set_role_mapping(
        company.id,
        SetAccountRoleMappingCommand(role_code="ar_control", account_id=ar_account.id),
    )
    print("ar_control_mapped", ar_account.id)

    revenue_account = registry.chart_of_accounts_service.create_account(
        company.id,
        CreateAccountCommand(
            account_code="4100",
            account_name="Sales Revenue",
            account_class_id=classes[0].id,
            account_type_id=credit_type.id,
            normal_balance=credit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    print("revenue_account_created", revenue_account.id)

    tax_liability_account = registry.chart_of_accounts_service.create_account(
        company.id,
        CreateAccountCommand(
            account_code="2300",
            account_name="VAT Output",
            account_class_id=classes[0].id,
            account_type_id=credit_type.id,
            normal_balance=credit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )

    bank_gl_account = registry.chart_of_accounts_service.create_account(
        company.id,
        CreateAccountCommand(
            account_code="1100",
            account_name="Bank Current Account",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    print("tax_and_bank_accounts_created", tax_liability_account.id, bank_gl_account.id)

    # ------------------------------------------------------------------
    # 5. Tax code + account mapping
    # ------------------------------------------------------------------
    tax_code = registry.tax_setup_service.create_tax_code(
        company.id,
        CreateTaxCodeCommand(
            code="VAT19",
            name="VAT 19.25%",
            tax_type_code="VAT",
            calculation_method_code="PERCENTAGE",
            rate_percent=Decimal("19.25"),
            effective_from=date(2026, 1, 1),
        ),
    )
    registry.tax_setup_service.set_tax_code_account_mapping(
        company.id,
        SetTaxCodeAccountMappingCommand(
            tax_code_id=tax_code.id,
            tax_liability_account_id=tax_liability_account.id,
        ),
    )
    print("tax_code_and_mapping_created", tax_code.id)

    # ------------------------------------------------------------------
    # 6. Financial account (for customer receipts)
    # ------------------------------------------------------------------
    fa = registry.financial_account_service.create_financial_account(
        company.id,
        CreateFinancialAccountCommand(
            account_code="BANK-001",
            name="Main Bank Account",
            financial_account_type_code="bank",
            gl_account_id=bank_gl_account.id,
            currency_code="XAF",
            bank_name="UBA",
        ),
    )
    print("financial_account_created", fa.id)

    # ==================================================================
    # SALES INVOICE: full lifecycle
    # ==================================================================

    # 7a. Create draft invoice
    draft_invoice = registry.sales_invoice_service.create_draft_invoice(
        company.id,
        CreateSalesInvoiceCommand(
            customer_id=customer.id,
            invoice_date=date(2026, 3, 15),
            due_date=date(2026, 4, 15),
            currency_code="XAF",
            reference_number="PO-1001",
            notes="First smoke invoice",
            lines=(
                SalesInvoiceLineCommand(
                    description="Widget A",
                    quantity=Decimal("10"),
                    unit_price=Decimal("5000"),
                    tax_code_id=tax_code.id,
                    revenue_account_id=revenue_account.id,
                ),
                SalesInvoiceLineCommand(
                    description="Service B",
                    quantity=Decimal("2"),
                    unit_price=Decimal("15000"),
                    revenue_account_id=revenue_account.id,
                ),
            ),
        ),
    )
    print("draft_invoice_created", draft_invoice.id, draft_invoice.invoice_number)
    assert draft_invoice.status_code == "draft", f"Expected draft, got {draft_invoice.status_code}"
    assert draft_invoice.invoice_number.startswith("SI-DRAFT-"), draft_invoice.invoice_number
    assert draft_invoice.totals.subtotal_amount == Decimal("80000"), draft_invoice.totals.subtotal_amount
    print("draft_invoice_totals_ok", draft_invoice.totals.subtotal_amount, draft_invoice.totals.tax_amount, draft_invoice.totals.total_amount)

    # 7b. Update draft invoice
    updated_invoice = registry.sales_invoice_service.update_draft_invoice(
        company.id,
        draft_invoice.id,
        UpdateSalesInvoiceCommand(
            customer_id=customer.id,
            invoice_date=date(2026, 3, 15),
            due_date=date(2026, 4, 15),
            currency_code="XAF",
            reference_number="PO-1001-REV",
            notes="Updated smoke invoice",
            lines=(
                SalesInvoiceLineCommand(
                    description="Widget A (revised)",
                    quantity=Decimal("10"),
                    unit_price=Decimal("5000"),
                    tax_code_id=tax_code.id,
                    revenue_account_id=revenue_account.id,
                ),
                SalesInvoiceLineCommand(
                    description="Service B",
                    quantity=Decimal("2"),
                    unit_price=Decimal("15000"),
                    revenue_account_id=revenue_account.id,
                ),
            ),
        ),
    )
    print("draft_invoice_updated", updated_invoice.id, updated_invoice.reference_number)

    # 7c. Post invoice
    post_result = registry.sales_invoice_posting_service.post_invoice(company.id, draft_invoice.id)
    print(
        "invoice_posted",
        post_result.invoice_number,
        post_result.journal_entry_number,
        post_result.payment_status_code,
    )
    assert post_result.invoice_number.startswith("SI-"), post_result.invoice_number
    assert not post_result.invoice_number.startswith("SI-DRAFT"), post_result.invoice_number
    assert post_result.payment_status_code == "unpaid", post_result.payment_status_code
    assert post_result.open_balance_amount == updated_invoice.totals.total_amount

    # 7d. Verify posted invoice is immutable
    try:
        registry.sales_invoice_service.update_draft_invoice(
            company.id,
            draft_invoice.id,
            UpdateSalesInvoiceCommand(
                customer_id=customer.id,
                invoice_date=date(2026, 3, 15),
                due_date=date(2026, 4, 15),
                currency_code="XAF",
                lines=(
                    SalesInvoiceLineCommand(
                        description="Hacked line",
                        quantity=Decimal("1"),
                        unit_price=Decimal("1"),
                        revenue_account_id=revenue_account.id,
                    ),
                ),
            ),
        )
    except ValidationError as exc:
        print("posted_invoice_immutable", type(exc).__name__)
    else:
        raise RuntimeError("Posted invoice was editable through draft workflow.")

    # 7e. Verify double-post blocked
    try:
        registry.sales_invoice_posting_service.post_invoice(company.id, draft_invoice.id)
    except ValidationError as exc:
        print("double_post_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Double-posting was not blocked.")

    # 7f. List invoices
    all_invoices = registry.sales_invoice_service.list_sales_invoices(company.id)
    print("invoices_listed", len(all_invoices))
    posted_list = registry.sales_invoice_service.list_sales_invoices(company.id, status_code="posted")
    print("posted_invoices_listed", len(posted_list))

    # 7g. Cancel a second draft
    cancel_target = registry.sales_invoice_service.create_draft_invoice(
        company.id,
        CreateSalesInvoiceCommand(
            customer_id=customer.id,
            invoice_date=date(2026, 3, 20),
            due_date=date(2026, 4, 20),
            currency_code="XAF",
            lines=(
                SalesInvoiceLineCommand(
                    description="Cancel me",
                    quantity=Decimal("1"),
                    unit_price=Decimal("1000"),
                    revenue_account_id=revenue_account.id,
                ),
            ),
        ),
    )
    registry.sales_invoice_service.cancel_draft_invoice(company.id, cancel_target.id)
    cancelled = registry.sales_invoice_service.get_sales_invoice(company.id, cancel_target.id)
    print("invoice_cancelled", cancelled.status_code)
    assert cancelled.status_code == "cancelled"

    # ==================================================================
    # CUSTOMER RECEIPT: full lifecycle
    # ==================================================================

    posted_invoice = registry.sales_invoice_service.get_sales_invoice(company.id, draft_invoice.id)
    total_amount = posted_invoice.totals.total_amount

    # 8a. Create draft receipt with partial allocation
    partial_amount = (total_amount / 2).quantize(Decimal("1"))
    draft_receipt = registry.customer_receipt_service.create_draft_receipt(
        company.id,
        CreateCustomerReceiptCommand(
            customer_id=customer.id,
            financial_account_id=fa.id,
            receipt_date=date(2026, 3, 25),
            currency_code="XAF",
            amount_received=partial_amount,
            reference_number="REC-001",
            notes="Partial payment",
            allocations=(
                CustomerReceiptAllocationCommand(
                    sales_invoice_id=draft_invoice.id,
                    allocated_amount=partial_amount,
                ),
            ),
        ),
    )
    print("draft_receipt_created", draft_receipt.id, draft_receipt.receipt_number)
    assert draft_receipt.status_code == "draft"
    assert draft_receipt.receipt_number.startswith("CR-DRAFT-")

    # 8b. Update draft receipt
    updated_receipt = registry.customer_receipt_service.update_draft_receipt(
        company.id,
        draft_receipt.id,
        UpdateCustomerReceiptCommand(
            customer_id=customer.id,
            financial_account_id=fa.id,
            receipt_date=date(2026, 3, 25),
            currency_code="XAF",
            amount_received=partial_amount,
            reference_number="REC-001-REV",
            notes="Updated partial",
            allocations=(
                CustomerReceiptAllocationCommand(
                    sales_invoice_id=draft_invoice.id,
                    allocated_amount=partial_amount,
                ),
            ),
        ),
    )
    print("draft_receipt_updated", updated_receipt.id, updated_receipt.reference_number)

    # 8c. Post receipt (partial payment)
    receipt_post = registry.customer_receipt_posting_service.post_receipt(company.id, draft_receipt.id)
    print(
        "receipt_posted",
        receipt_post.receipt_number,
        receipt_post.journal_entry_number,
        receipt_post.allocated_amount,
    )
    assert receipt_post.receipt_number.startswith("CR-"), receipt_post.receipt_number
    assert not receipt_post.receipt_number.startswith("CR-DRAFT"), receipt_post.receipt_number

    # 8d. Verify invoice is now "partial"
    inv_after_partial = registry.sales_invoice_service.get_sales_invoice(company.id, draft_invoice.id)
    print("invoice_payment_status_after_partial", inv_after_partial.payment_status_code)
    assert inv_after_partial.payment_status_code == "partial", inv_after_partial.payment_status_code

    # 8e. Posted receipt immutability
    try:
        registry.customer_receipt_service.update_draft_receipt(
            company.id,
            draft_receipt.id,
            UpdateCustomerReceiptCommand(
                customer_id=customer.id,
                financial_account_id=fa.id,
                receipt_date=date(2026, 3, 25),
                currency_code="XAF",
                amount_received=Decimal("999"),
                allocations=(),
            ),
        )
    except ValidationError as exc:
        print("posted_receipt_immutable", type(exc).__name__)
    else:
        raise RuntimeError("Posted receipt was editable.")

    # 8f. Second receipt to fully pay the invoice
    remaining = total_amount - partial_amount
    full_receipt = registry.customer_receipt_service.create_draft_receipt(
        company.id,
        CreateCustomerReceiptCommand(
            customer_id=customer.id,
            financial_account_id=fa.id,
            receipt_date=date(2026, 3, 28),
            currency_code="XAF",
            amount_received=remaining,
            allocations=(
                CustomerReceiptAllocationCommand(
                    sales_invoice_id=draft_invoice.id,
                    allocated_amount=remaining,
                ),
            ),
        ),
    )
    full_post = registry.customer_receipt_posting_service.post_receipt(company.id, full_receipt.id)
    print("full_receipt_posted", full_post.receipt_number)

    inv_after_full = registry.sales_invoice_service.get_sales_invoice(company.id, draft_invoice.id)
    print("invoice_payment_status_after_full", inv_after_full.payment_status_code)
    assert inv_after_full.payment_status_code == "paid", inv_after_full.payment_status_code

    # 8g. List receipts
    all_receipts = registry.customer_receipt_service.list_customer_receipts(company.id)
    print("receipts_listed", len(all_receipts))

    # 8h. Cancel a draft receipt
    cancel_receipt = registry.customer_receipt_service.create_draft_receipt(
        company.id,
        CreateCustomerReceiptCommand(
            customer_id=customer.id,
            financial_account_id=fa.id,
            receipt_date=date(2026, 3, 30),
            currency_code="XAF",
            amount_received=Decimal("1000"),
            allocations=(),
        ),
    )
    registry.customer_receipt_service.cancel_draft_receipt(company.id, cancel_receipt.id)
    cancelled_r = registry.customer_receipt_service.get_customer_receipt(company.id, cancel_receipt.id)
    print("receipt_cancelled", cancelled_r.status_code)
    assert cancelled_r.status_code == "cancelled"

    # 8i. list_allocatable_invoices
    open_invoices = registry.customer_receipt_service.list_allocatable_invoices(
        company.id, customer.id
    )
    print("allocatable_invoices", len(open_invoices))

    # ==================================================================
    # PERIOD VALIDATION: posting into closed/locked period
    # ==================================================================
    # Create a draft in March, then close March's period
    period_test_invoice = registry.sales_invoice_service.create_draft_invoice(
        company.id,
        CreateSalesInvoiceCommand(
            customer_id=customer.id,
            invoice_date=date(2026, 3, 10),
            due_date=date(2026, 4, 10),
            currency_code="XAF",
            lines=(
                SalesInvoiceLineCommand(
                    description="Period test",
                    quantity=Decimal("1"),
                    unit_price=Decimal("1000"),
                    revenue_account_id=revenue_account.id,
                ),
            ),
        ),
    )

    periods = registry.fiscal_calendar_service.list_periods(company.id, fiscal_year_id=fiscal_year.id)
    march_period = next(p for p in periods if p.period_number == 3)
    registry.period_control_service.close_period(company.id, march_period.id)

    try:
        registry.sales_invoice_posting_service.post_invoice(company.id, period_test_invoice.id)
    except ValidationError as exc:
        print("closed_period_post_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Posting into a closed period was not blocked.")

    registry.period_control_service.reopen_period(company.id, march_period.id)
    registry.period_control_service.close_period(company.id, march_period.id)
    registry.period_control_service.lock_period(company.id, march_period.id)

    try:
        registry.sales_invoice_posting_service.post_invoice(company.id, period_test_invoice.id)
    except PeriodLockedError as exc:
        print("locked_period_post_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Posting into a locked period was not blocked.")

    # ==================================================================
    # UI: offscreen boot and workspace navigation
    # ==================================================================
    registry.company_context_service.clear_active_company()
    main_window = MainWindow(registry)
    main_window.show()
    app.processEvents()

    invoices_page = _get_page(main_window, nav_ids.SALES_INVOICES, SalesInvoicesPage, app)
    receipts_page = _get_page(main_window, nav_ids.CUSTOMER_RECEIPTS, CustomerReceiptsPage, app)
    print("invoices_page_no_active", invoices_page._stack.currentWidget() is invoices_page._no_active_company_state)
    print("receipts_page_no_active", receipts_page._stack.currentWidget() is receipts_page._no_active_company_state)

    active = registry.company_context_service.set_active_company(company.id)
    app.processEvents()
    print("active_company_set", active.company_id, active.company_name)
    print("invoices_page_ready", invoices_page._stack.currentWidget() is invoices_page._table_surface)
    print("receipts_page_ready", receipts_page._stack.currentWidget() is receipts_page._table_surface)

    main_window.close()
    app.quit()

    print("\n=== SLICE 8 SMOKE VALIDATION PASSED ===")
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
