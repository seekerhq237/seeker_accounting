"""Smoke test — Slice 11b: Sales and Purchase Credit Notes."""
from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, "scripts")

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime

from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import CreateAccountCommand
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import SetAccountRoleMappingCommand
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import CreateDocumentSequenceCommand
from seeker_accounting.modules.accounting.reference_data.dto.tax_code_account_mapping_dto import SetTaxCodeAccountMappingCommand
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import CreateTaxCodeCommand
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.customers.dto.customer_commands import CreateCustomerCommand, CreateCustomerGroupCommand
from seeker_accounting.modules.purchases.dto.purchase_credit_note_commands import (
    CreatePurchaseCreditNoteCommand,
    PurchaseCreditNoteLineCommand,
    UpdatePurchaseCreditNoteCommand,
)
from seeker_accounting.modules.purchases.ui.purchase_credit_notes_page import PurchaseCreditNotesPage
from seeker_accounting.modules.sales.dto.sales_credit_note_commands import (
    CreateSalesCreditNoteCommand,
    SalesCreditNoteLineCommand,
    UpdateSalesCreditNoteCommand,
)
from seeker_accounting.modules.sales.ui.sales_credit_notes_page import SalesCreditNotesPage
from seeker_accounting.modules.suppliers.dto.supplier_commands import CreateSupplierCommand, CreateSupplierGroupCommand
from seeker_accounting.platform.exceptions import ConflictError, ValidationError


PERMISSIONS = (
    "companies.view", "companies.create", "companies.edit", "companies.select_active",
    "fiscal.years.view", "fiscal.years.create", "fiscal.periods.view", "fiscal.periods.create",
    "fiscal.periods.generate",
    "accounts.view", "accounts.create", "accounts.edit",
    "account_role_mappings.view", "account_role_mappings.manage",
    "reference.account_role_mappings.manage",
    "document_sequences.view", "document_sequences.create", "document_sequences.edit",
    "reference.document_sequences.view", "reference.document_sequences.create",
    "reference.document_sequences.edit",
    "tax_codes.view", "tax_codes.create", "tax_codes.edit",
    "reference.tax_codes.view", "reference.tax_codes.create",
    "tax_mappings.view", "tax_mappings.manage",
    "reference.tax_mappings.view", "reference.tax_mappings.manage",
    "customers.view", "customers.create", "customers.edit",
    "customers.groups.view", "customers.groups.create",
    "suppliers.view", "suppliers.create", "suppliers.edit",
    "suppliers.groups.view", "suppliers.groups.create",
    "journals.view", "journals.create",
    "journal_entries.view", "journal_entries.create", "journal_entries.post",
    "sales.credit_notes.view", "sales.credit_notes.create", "sales.credit_notes.edit",
    "sales.credit_notes.post", "sales.credit_notes.cancel", "sales.credit_notes.print",
    "purchases.credit_notes.view", "purchases.credit_notes.create", "purchases.credit_notes.edit",
    "purchases.credit_notes.post", "purchases.credit_notes.cancel", "purchases.credit_notes.print",
    "chart.accounts.view", "chart.accounts.create", "chart.accounts.edit",
    "fiscal.calendar.view", "fiscal.calendar.create",
)


def main() -> int:  # noqa: C901, PLR0915
    """Run smoke test."""
    app = QApplication.instance() or QApplication(sys.argv)
    bootstrap = bootstrap_script_runtime(app, permission_snapshot=PERMISSIONS)
    reg = bootstrap.service_registry
    bootstrap.app_context.current_user_id = 1

    _ensure_country_currency(reg)

    # ── Company
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    company = reg.company_service.create_company(CreateCompanyCommand(
        legal_name=f"CN Smoke {ts} SARL",
        display_name=f"CN Smoke {ts}",
        country_code="CM",
        base_currency_code="XAF",
    ))
    cid = company.id
    print(f"  company created: {cid}")

    # ── Chart seed
    reg.chart_seed_service.ensure_global_chart_reference_seed()
    reg.company_seed_service.seed_built_in_chart(cid)
    print("  chart seeded")

    # ── Reference data: account types/classes
    types = reg.reference_data_service.list_account_types()
    classes = reg.reference_data_service.list_account_classes()
    if not classes or not types:
        raise RuntimeError("Account classes/types not seeded.")
    debit_type = next((t for t in types if t.normal_balance == "DEBIT"), types[0])
    credit_type = next((t for t in types if t.normal_balance == "CREDIT"), types[0])
    cls_id = classes[0].id

    # ── Fiscal year
    fy = reg.fiscal_calendar_service.create_fiscal_year(
        cid,
        CreateFiscalYearCommand(
            year_code="FY2025", year_name="Fiscal Year 2025",
            start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        ),
    )
    reg.fiscal_calendar_service.generate_periods(cid, fy.id, GenerateFiscalPeriodsCommand())
    print("  fiscal year + periods created")

    # ── Document sequences
    for doc_type, prefix in (
        ("JOURNAL_ENTRY", "JRN-"),
    ):
        reg.numbering_setup_service.create_document_sequence(
            cid,
            CreateDocumentSequenceCommand(document_type_code=doc_type, prefix=prefix, next_number=1, padding_width=6),
        )
    print("  document sequences created")

    # ── Accounts
    ar_account = reg.chart_of_accounts_service.create_account(cid, CreateAccountCommand(
        account_code="9901", account_name="AR Control CN Test",
        account_class_id=cls_id, account_type_id=credit_type.id,
        normal_balance=credit_type.normal_balance, allow_manual_posting=True, is_control_account=True,
    ))
    reg.account_role_mapping_service.set_role_mapping(cid, SetAccountRoleMappingCommand(
        role_code="ar_control", account_id=ar_account.id,
    ))

    ap_account = reg.chart_of_accounts_service.create_account(cid, CreateAccountCommand(
        account_code="9902", account_name="AP Control CN Test",
        account_class_id=cls_id, account_type_id=credit_type.id,
        normal_balance=credit_type.normal_balance, allow_manual_posting=True, is_control_account=True,
    ))
    reg.account_role_mapping_service.set_role_mapping(cid, SetAccountRoleMappingCommand(
        role_code="ap_control", account_id=ap_account.id,
    ))

    revenue_account = reg.chart_of_accounts_service.create_account(cid, CreateAccountCommand(
        account_code="9903", account_name="Revenue CN Test",
        account_class_id=cls_id, account_type_id=credit_type.id,
        normal_balance=credit_type.normal_balance, allow_manual_posting=True, is_control_account=False,
    ))
    expense_account = reg.chart_of_accounts_service.create_account(cid, CreateAccountCommand(
        account_code="9904", account_name="Expense CN Test",
        account_class_id=cls_id, account_type_id=debit_type.id,
        normal_balance=debit_type.normal_balance, allow_manual_posting=True, is_control_account=False,
    ))
    vat_liability = reg.chart_of_accounts_service.create_account(cid, CreateAccountCommand(
        account_code="9905", account_name="VAT Output CN Test",
        account_class_id=cls_id, account_type_id=credit_type.id,
        normal_balance=credit_type.normal_balance, allow_manual_posting=True, is_control_account=False,
    ))
    vat_asset = reg.chart_of_accounts_service.create_account(cid, CreateAccountCommand(
        account_code="9906", account_name="VAT Input CN Test",
        account_class_id=cls_id, account_type_id=debit_type.id,
        normal_balance=debit_type.normal_balance, allow_manual_posting=True, is_control_account=False,
    ))
    print("  accounts + role mappings done")

    # ── Tax code
    tax_code = reg.tax_setup_service.create_tax_code(cid, CreateTaxCodeCommand(
        code="VAT19", name="VAT 19%",
        tax_type_code="vat", calculation_method_code="percentage",
        effective_from=date(2025, 1, 1), rate_percent=Decimal("19.00"), is_recoverable=True,
    ))
    reg.tax_setup_service.set_tax_code_account_mapping(cid, SetTaxCodeAccountMappingCommand(
        tax_code_id=tax_code.id,
        tax_liability_account_id=vat_liability.id,
        tax_asset_account_id=vat_asset.id,
    ))
    print("  tax code + mapping done")

    # ── Customer
    cust_grp = reg.customer_service.create_customer_group(cid, CreateCustomerGroupCommand(
        code="CNGP", name="CN Test Group",
    ))
    customer = reg.customer_service.create_customer(cid, CreateCustomerCommand(
        customer_code="CN-CUST-001", display_name="CN Test Customer",
        customer_group_id=cust_grp.id, country_code="CM",
    ))
    print(f"  customer {customer.id} created")

    # ── Supplier
    sup_grp = reg.supplier_service.create_supplier_group(cid, CreateSupplierGroupCommand(
        code="CNSUP", name="CN Supplier Group",
    ))
    supplier = reg.supplier_service.create_supplier(cid, CreateSupplierCommand(
        supplier_code="CN-SUP-001", display_name="CN Test Supplier",
        supplier_group_id=sup_grp.id, country_code="CM",
    ))
    print(f"  supplier {supplier.id} created")

    # ══════════════════════════════════════════════════════════════════
    print("CHECK 1: Create draft sales credit note")
    scn = reg.sales_credit_note_service.create_draft_credit_note(CreateSalesCreditNoteCommand(
        company_id=cid,
        customer_id=customer.id,
        credit_date=date(2025, 3, 15),
        currency_code="XAF",
        exchange_rate=None,
        reason_text="Test reason",
        reference_number="REF-001",
        source_invoice_id=None,
        contract_id=None,
        project_id=None,
        lines=[SalesCreditNoteLineCommand(
            description="Credit for defective goods",
            quantity=Decimal("2"),
            unit_price=Decimal("500.00"),
            discount_percent=None,
            tax_code_id=None,
            revenue_account_id=revenue_account.id,
            contract_id=None, project_id=None, project_job_id=None, project_cost_code_id=None,
        )],
    ))
    assert scn.status_code == "draft", f"Expected draft, got {scn.status_code}"
    assert scn.total_amount == Decimal("1000.00"), f"Expected 1000, got {scn.total_amount}"
    print(f"  SCN created: {scn.credit_number}, total={scn.total_amount}")

    print("CHECK 2: Update draft SCN")
    scn_upd = reg.sales_credit_note_service.update_draft_credit_note(UpdateSalesCreditNoteCommand(
        credit_note_id=scn.id,
        company_id=cid,
        customer_id=customer.id,
        credit_date=date(2025, 3, 16),
        currency_code="XAF",
        exchange_rate=None,
        reason_text="Updated reason",
        reference_number="REF-002",
        source_invoice_id=None,
        contract_id=None,
        project_id=None,
        lines=[SalesCreditNoteLineCommand(
            description="Updated credit",
            quantity=Decimal("3"),
            unit_price=Decimal("400.00"),
            discount_percent=None,
            tax_code_id=None,
            revenue_account_id=revenue_account.id,
            contract_id=None, project_id=None, project_job_id=None, project_cost_code_id=None,
        )],
    ))
    assert scn_upd.total_amount == Decimal("1200.00"), f"Expected 1200, got {scn_upd.total_amount}"
    print(f"  SCN updated: total={scn_upd.total_amount}")

    print("CHECK 3: Post SCN")
    scn_post_result = reg.sales_credit_note_posting_service.post_credit_note(cid, scn.id)
    assert scn_post_result.status_code == "posted", f"Expected posted, got {scn_post_result.status_code}"
    assert scn_post_result.credit_number.startswith("SCN-"), f"Unexpected number: {scn_post_result.credit_number}"
    print(f"  SCN posted: {scn_post_result.credit_number}")

    print("CHECK 4: Posted SCN is immutable (update must raise ConflictError)")
    try:
        reg.sales_credit_note_service.update_draft_credit_note(UpdateSalesCreditNoteCommand(
            credit_note_id=scn.id,
            company_id=cid,
            customer_id=customer.id,
            credit_date=date(2025, 3, 17),
            currency_code="XAF",
            exchange_rate=None,
            reason_text="Should fail",
            reference_number=None,
            source_invoice_id=None,
            contract_id=None,
            project_id=None,
            lines=[],
        ))
        print("  [FAIL] Expected ConflictError but no exception raised")
        return 1
    except ConflictError:
        print("  ConflictError raised correctly")

    print("CHECK 5: Cancel a draft SCN")
    scn2 = reg.sales_credit_note_service.create_draft_credit_note(CreateSalesCreditNoteCommand(
        company_id=cid,
        customer_id=customer.id,
        credit_date=date(2025, 4, 1),
        currency_code="XAF",
        exchange_rate=None,
        reason_text="To cancel",
        reference_number=None,
        source_invoice_id=None,
        contract_id=None,
        project_id=None,
        lines=[SalesCreditNoteLineCommand(
            description="Cancel test",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            discount_percent=None,
            tax_code_id=None,
            revenue_account_id=revenue_account.id,
            contract_id=None, project_id=None, project_job_id=None, project_cost_code_id=None,
        )],
    ))
    reg.sales_credit_note_service.cancel_credit_note(cid, scn2.id)
    cancelled = reg.sales_credit_note_service.get_credit_note(cid, scn2.id)
    assert cancelled.status_code == "cancelled", f"Expected cancelled, got {cancelled.status_code}"
    print(f"  SCN cancelled: {cancelled.credit_number}")

    # ── Purchase Credit Notes
    print("CHECK 6: Create draft PCN")
    pcn = reg.purchase_credit_note_service.create_draft_credit_note(CreatePurchaseCreditNoteCommand(
        company_id=cid,
        supplier_id=supplier.id,
        credit_date=date(2025, 3, 20),
        currency_code="XAF",
        exchange_rate=None,
        reason_text="Overcharge correction",
        supplier_credit_reference="SUPCN-001",
        source_bill_id=None,
        contract_id=None,
        project_id=None,
        lines=[PurchaseCreditNoteLineCommand(
            description="Overcharged service",
            quantity=None,
            unit_cost=None,
            expense_account_id=expense_account.id,
            tax_code_id=None,
            line_subtotal_amount=Decimal("800.00"),
            contract_id=None, project_id=None, project_job_id=None, project_cost_code_id=None,
        )],
    ))
    assert pcn.status_code == "draft", f"Expected draft, got {pcn.status_code}"
    assert pcn.total_amount == Decimal("800.00"), f"Expected 800, got {pcn.total_amount}"
    print(f"  PCN created: {pcn.credit_number}, total={pcn.total_amount}")

    print("CHECK 7: Update draft PCN")
    pcn_upd = reg.purchase_credit_note_service.update_draft_credit_note(UpdatePurchaseCreditNoteCommand(
        credit_note_id=pcn.id,
        company_id=cid,
        supplier_id=supplier.id,
        credit_date=date(2025, 3, 21),
        currency_code="XAF",
        exchange_rate=None,
        reason_text="Updated overcharge",
        supplier_credit_reference="SUPCN-002",
        source_bill_id=None,
        contract_id=None,
        project_id=None,
        lines=[PurchaseCreditNoteLineCommand(
            description="Corrected overcharged service",
            quantity=None,
            unit_cost=None,
            expense_account_id=expense_account.id,
            tax_code_id=None,
            line_subtotal_amount=Decimal("600.00"),
            contract_id=None, project_id=None, project_job_id=None, project_cost_code_id=None,
        )],
    ))
    assert pcn_upd.total_amount == Decimal("600.00"), f"Expected 600, got {pcn_upd.total_amount}"
    print(f"  PCN updated: total={pcn_upd.total_amount}")

    print("CHECK 8: Post PCN")
    pcn_post_result = reg.purchase_credit_note_posting_service.post_credit_note(cid, pcn.id)
    assert pcn_post_result.status_code == "posted", f"Expected posted, got {pcn_post_result.status_code}"
    assert pcn_post_result.credit_number.startswith("PCN-"), f"Unexpected number: {pcn_post_result.credit_number}"
    print(f"  PCN posted: {pcn_post_result.credit_number}")

    print("CHECK 9: Cancel a draft PCN")
    pcn2 = reg.purchase_credit_note_service.create_draft_credit_note(CreatePurchaseCreditNoteCommand(
        company_id=cid,
        supplier_id=supplier.id,
        credit_date=date(2025, 4, 5),
        currency_code="XAF",
        exchange_rate=None,
        reason_text="Cancel test",
        supplier_credit_reference=None,
        source_bill_id=None,
        contract_id=None,
        project_id=None,
        lines=[PurchaseCreditNoteLineCommand(
            description="Cancel test line",
            quantity=None, unit_cost=None,
            expense_account_id=expense_account.id,
            tax_code_id=None,
            line_subtotal_amount=Decimal("100.00"),
            contract_id=None, project_id=None, project_job_id=None, project_cost_code_id=None,
        )],
    ))
    reg.purchase_credit_note_service.cancel_credit_note(cid, pcn2.id)
    pcn2_detail = reg.purchase_credit_note_service.get_credit_note(cid, pcn2.id)
    assert pcn2_detail.status_code == "cancelled", f"Expected cancelled, got {pcn2_detail.status_code}"
    print(f"  PCN cancelled: {pcn2_detail.credit_number}")

    # ── UI offscreen
    print("CHECK 10: SalesCreditNotesPage offscreen")
    try:
        page = SalesCreditNotesPage(reg)
        page.show()
        app.processEvents()
        page.hide()
        print("  SalesCreditNotesPage OK")
    except Exception as e:
        print(f"  [FAIL] SalesCreditNotesPage: {e}")
        return 1

    print("CHECK 11: PurchaseCreditNotesPage offscreen")
    try:
        page = PurchaseCreditNotesPage(reg)
        page.show()
        app.processEvents()
        page.hide()
        print("  PurchaseCreditNotesPage OK")
    except Exception as e:
        print(f"  [FAIL] PurchaseCreditNotesPage: {e}")
        return 1

    print()
    print("RESULT: All checks passed.")
    return 0


def _ensure_country_currency(reg) -> None:
    with reg.session_context.unit_of_work_factory() as uow:
        session = uow.session
        if session.get(Country, "CM") is None:
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if session.get(Currency, "XAF") is None:
            session.add(Currency(code="XAF", name="Central African CFA franc", symbol="FCFA", decimal_places=0, is_active=True))
        uow.commit()


if __name__ == "__main__":
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.exit(main())
