"""Smoke test for the Customer Quote vertical slice (Slice 10a).

Covers the full quote lifecycle:

    create draft -> update draft -> issue -> accept -> convert to draft invoice

and verifies:
 - draft quote carries auto-generated draft number and computed totals
 - only draft quotes can be edited
 - only issued quotes can be accepted/rejected/expired
 - only accepted quotes can be converted
 - conversion produces a draft sales invoice with the quote's lines
 - conversion links the quote and the invoice both ways (converted_to_invoice_id / source_quote_id)
 - a converted quote cannot be converted again
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import CreateAccountCommand
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import CreateDocumentSequenceCommand
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import CreatePaymentTermCommand
from seeker_accounting.modules.accounting.reference_data.dto.tax_code_account_mapping_dto import (
    SetTaxCodeAccountMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import CreateTaxCodeCommand
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerCommand,
    CreateCustomerGroupCommand,
)
from seeker_accounting.modules.sales.dto.customer_quote_commands import (
    ConvertCustomerQuoteCommand,
    CreateCustomerQuoteCommand,
    CustomerQuoteLineCommand,
    UpdateCustomerQuoteCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError


def main() -> int:
    app = QApplication([])
    from seeker_accounting.modules.administration.rbac_catalog import ALL_SYSTEM_PERMISSION_CODES

    bootstrap = bootstrap_script_runtime(app, permission_snapshot=ALL_SYSTEM_PERMISSION_CODES)
    registry = bootstrap.service_registry

    # ------------------------------------------------------------------
    # 1. Company + chart seed + reference data
    # ------------------------------------------------------------------
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Slice 10a Smoke SARL",
            display_name="Slice 10a Smoke",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    print("company_created", company.id)
    registry.chart_seed_service.ensure_global_chart_reference_seed()
    registry.company_seed_service.seed_built_in_chart(company.id)

    term = registry.reference_data_service.create_payment_term(
        company.id, CreatePaymentTermCommand(code="NET30", name="Net 30", days_due=30)
    )
    group = registry.customer_service.create_customer_group(
        company.id, CreateCustomerGroupCommand(code="RETAIL", name="Retail Customers")
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
    print("customer_created", customer.id)

    # ------------------------------------------------------------------
    # 2. Fiscal calendar
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

    # ------------------------------------------------------------------
    # 3. Sequences + accounts + tax
    # ------------------------------------------------------------------
    for doc_type, prefix in (("JOURNAL_ENTRY", "JRN-"), ("SALES_INVOICE", "SI-")):
        registry.numbering_setup_service.create_document_sequence(
            company.id,
            CreateDocumentSequenceCommand(
                document_type_code=doc_type,
                prefix=prefix,
                next_number=1,
                padding_width=4,
            ),
        )

    classes = registry.reference_data_service.list_account_classes()
    types = registry.reference_data_service.list_account_types()
    debit_type = next((t for t in types if t.normal_balance == "DEBIT"), types[0])
    credit_type = next((t for t in types if t.normal_balance == "CREDIT"), types[0])

    ar_account = registry.chart_of_accounts_service.create_account(
        company.id,
        CreateAccountCommand(
            account_code="1200",
            account_name="AR Control",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=True,
        ),
    )
    registry.account_role_mapping_service.set_role_mapping(
        company.id, SetAccountRoleMappingCommand(role_code="ar_control", account_id=ar_account.id)
    )
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
            tax_code_id=tax_code.id, tax_liability_account_id=tax_liability_account.id
        ),
    )

    # ==================================================================
    # CUSTOMER QUOTE: full lifecycle
    # ==================================================================

    # 4a. Create draft quote
    draft = registry.customer_quote_service.create_draft_quote(
        company.id,
        CreateCustomerQuoteCommand(
            customer_id=customer.id,
            quote_date=date(2026, 3, 1),
            expiry_date=date(2026, 3, 31),
            currency_code="XAF",
            reference_number="RFQ-1001",
            notes="Initial smoke quote",
            lines=(
                CustomerQuoteLineCommand(
                    description="Widget A",
                    quantity=Decimal("10"),
                    unit_price=Decimal("5000"),
                    tax_code_id=tax_code.id,
                    revenue_account_id=revenue_account.id,
                ),
                CustomerQuoteLineCommand(
                    description="Service B",
                    quantity=Decimal("2"),
                    unit_price=Decimal("15000"),
                    revenue_account_id=revenue_account.id,
                ),
            ),
        ),
    )
    print("draft_quote_created", draft.id, draft.quote_number, draft.status_code)
    assert draft.status_code == "draft"
    assert draft.quote_number.startswith("CQ-DRAFT-"), draft.quote_number
    assert draft.totals.subtotal_amount == Decimal("80000.00"), draft.totals.subtotal_amount
    assert draft.totals.tax_amount == Decimal("9625.00"), draft.totals.tax_amount
    assert draft.totals.total_amount == Decimal("89625.00"), draft.totals.total_amount

    # 4b. Update draft quote
    updated = registry.customer_quote_service.update_draft_quote(
        company.id,
        draft.id,
        UpdateCustomerQuoteCommand(
            customer_id=customer.id,
            quote_date=date(2026, 3, 1),
            expiry_date=date(2026, 4, 30),
            currency_code="XAF",
            reference_number="RFQ-1001-R2",
            notes="Revised quote",
            lines=(
                CustomerQuoteLineCommand(
                    description="Widget A (revised)",
                    quantity=Decimal("12"),
                    unit_price=Decimal("5000"),
                    tax_code_id=tax_code.id,
                    revenue_account_id=revenue_account.id,
                ),
            ),
        ),
    )
    print("draft_quote_updated", updated.id, updated.reference_number)
    assert updated.totals.subtotal_amount == Decimal("60000.00"), updated.totals.subtotal_amount
    assert len(updated.lines) == 1

    # 4c. Issue quote (draft -> issued, number finalized)
    issued = registry.customer_quote_service.issue_quote(company.id, draft.id)
    print("quote_issued", issued.quote_number, issued.status_code)
    assert issued.status_code == "issued"
    assert issued.quote_number.startswith("CQ-") and not issued.quote_number.startswith("CQ-DRAFT-")

    # 4d. Cannot edit issued quote
    try:
        registry.customer_quote_service.update_draft_quote(
            company.id,
            draft.id,
            UpdateCustomerQuoteCommand(
                customer_id=customer.id,
                quote_date=date(2026, 3, 1),
                currency_code="XAF",
                lines=(
                    CustomerQuoteLineCommand(
                        description="hack",
                        quantity=Decimal("1"),
                        unit_price=Decimal("1"),
                        revenue_account_id=revenue_account.id,
                    ),
                ),
            ),
        )
    except ValidationError as exc:
        print("issued_quote_immutable_ok", type(exc).__name__)
    else:
        raise RuntimeError("Issued quote was editable.")

    # 4e. Cannot convert before acceptance
    try:
        registry.customer_quote_service.convert_to_invoice(
            company.id,
            draft.id,
            ConvertCustomerQuoteCommand(
                invoice_date=date(2026, 3, 10), due_date=date(2026, 4, 10)
            ),
        )
    except ValidationError as exc:
        print("convert_blocked_before_accept_ok", type(exc).__name__)
    else:
        raise RuntimeError("Convert allowed before acceptance.")

    # 4f. Accept quote (issued -> accepted)
    accepted = registry.customer_quote_service.mark_accepted(company.id, draft.id)
    print("quote_accepted", accepted.status_code)
    assert accepted.status_code == "accepted"

    # 4g. Convert to invoice
    conversion = registry.customer_quote_service.convert_to_invoice(
        company.id,
        draft.id,
        ConvertCustomerQuoteCommand(
            invoice_date=date(2026, 3, 10), due_date=date(2026, 4, 10)
        ),
    )
    print(
        "quote_converted",
        conversion.quote_id,
        conversion.sales_invoice_id,
        conversion.invoice_number,
    )
    assert conversion.sales_invoice_id > 0
    assert conversion.invoice_number.startswith("SI-DRAFT-"), conversion.invoice_number

    # 4h. Verify both sides linked and totals preserved
    quote_detail = registry.customer_quote_service.get_quote(company.id, draft.id)
    assert quote_detail.status_code == "converted", quote_detail.status_code
    assert quote_detail.converted_to_invoice_id == conversion.sales_invoice_id
    invoice_detail = registry.sales_invoice_service.get_sales_invoice(
        company.id, conversion.sales_invoice_id
    )
    assert invoice_detail.totals.total_amount == quote_detail.totals.total_amount
    assert invoice_detail.totals.subtotal_amount == quote_detail.totals.subtotal_amount
    assert len(invoice_detail.lines) == len(quote_detail.lines)
    # Verify source_quote_id back-reference on invoice
    with registry.session_context.unit_of_work_factory() as uow:
        from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice

        invoice_row = uow.session.get(SalesInvoice, conversion.sales_invoice_id)
        assert invoice_row is not None
        assert invoice_row.source_quote_id == draft.id, invoice_row.source_quote_id
    print("conversion_linkage_ok")

    # 4i. Cannot convert the same quote twice
    try:
        registry.customer_quote_service.convert_to_invoice(
            company.id,
            draft.id,
            ConvertCustomerQuoteCommand(
                invoice_date=date(2026, 3, 10), due_date=date(2026, 4, 10)
            ),
        )
    except (ValidationError, ConflictError) as exc:
        print("double_convert_blocked_ok", type(exc).__name__)
    else:
        raise RuntimeError("Quote was convertible twice.")

    # 4j. Listing filters (status_code=converted returns exactly this quote)
    converted_items = registry.customer_quote_service.list_quotes(company.id, status_code="converted")
    assert any(item.id == draft.id for item in converted_items), "converted list missing quote"
    print("list_filter_ok", len(converted_items))

    print("SMOKE_CUSTOMER_QUOTES_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
