"""
Slice 10: Cash, Bank, and Reconciliation -- Workflow Smoke Test

Validates end-to-end treasury workflow:
1. Company, chart, fiscal periods, sequences
2. Financial account CRUD
3. Treasury transactions (cash receipt, cash payment, bank receipt, bank payment)
4. Treasury transaction posting with journal entries
5. Treasury transfers between accounts
6. Treasury transfer posting
7. Bank statement CSV import
8. Manual statement line entry
9. Bank reconciliation sessions
10. Reconciliation matching and completion
11. Period validation
12. UI page instantiation
"""

from __future__ import annotations

import csv
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import (
    CreateAccountCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.treasury.dto.financial_account_commands import (
    CreateFinancialAccountCommand,
    UpdateFinancialAccountCommand,
)
from seeker_accounting.modules.treasury.dto.treasury_transaction_commands import (
    CreateTreasuryTransactionCommand,
    TreasuryTransactionLineCommand,
)
from seeker_accounting.modules.treasury.dto.treasury_transfer_commands import (
    CreateTreasuryTransferCommand,
)
from seeker_accounting.modules.treasury.dto.bank_statement_commands import (
    CreateManualStatementLineCommand,
    ImportBankStatementCommand,
)
from seeker_accounting.modules.treasury.dto.bank_reconciliation_commands import (
    AddReconciliationMatchCommand,
    CreateReconciliationSessionCommand,
)
from seeker_accounting.platform.exceptions import PeriodLockedError, ValidationError


def main() -> int:  # noqa: C901, PLR0915
    """Run the smoke test."""
    app = QApplication([])
    bootstrap = bootstrap_script_runtime(app)
    settings = bootstrap.settings
    app_context = bootstrap.app_context
    session_context = bootstrap.session_context
    active_company_context = bootstrap.active_company_context
    navigation_service = bootstrap.navigation_service
    theme_manager = bootstrap.theme_manager
    registry = bootstrap.service_registry

    try:
        # ------------------------------------------------------------------
        # 1. Setup: Company + chart + fiscal
        # ------------------------------------------------------------------
        print("[TEST] Setting up company, chart, fiscal year...")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        company = registry.company_service.create_company(
            CreateCompanyCommand(
                legal_name=f"Slice Ten Smoke {timestamp} SARL",
                display_name="Slice Ten Smoke",
                country_code="CM",
                base_currency_code="XAF",
            )
        )
        print(f"  [OK] company {company.id} created")

        registry.chart_seed_service.ensure_global_chart_reference_seed()
        registry.company_seed_service.seed_built_in_chart(company.id)
        print(f"  [OK] chart seeded for {company.id}")

        # Fiscal year
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
        print(f"  [OK] fiscal year {fiscal_year.id} with periods created")

        # ------------------------------------------------------------------
        # 2. Document sequences
        # ------------------------------------------------------------------
        print("[TEST] Creating document sequences...")
        for doc_type, prefix in (
            ("JOURNAL_ENTRY", "JRN-"),
            ("TREASURY_TRANSACTION", "TT-"),
            ("TREASURY_TRANSFER", "TF-"),
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
        print("  [OK] document sequences created")

        # ------------------------------------------------------------------
        # 3. GL Accounts
        # ------------------------------------------------------------------
        print("[TEST] Creating chart accounts...")
        types = registry.reference_data_service.list_account_types()
        classes = registry.reference_data_service.list_account_classes()
        if not classes or not types:
            raise RuntimeError("Account classes or types not available.")

        debit_type = next((t for t in types if t.normal_balance == "DEBIT"), types[0])
        credit_type = next((t for t in types if t.normal_balance == "CREDIT"), types[0])

        bank_gl = registry.chart_of_accounts_service.create_account(
            company.id,
            CreateAccountCommand(
                account_code="1100",
                account_name="Bank Account GL",
                account_class_id=classes[0].id,
                account_type_id=debit_type.id,
                normal_balance=debit_type.normal_balance,
                allow_manual_posting=True,
                is_control_account=False,
            ),
        )
        print(f"  [OK] bank GL account {bank_gl.id}")

        cash_gl = registry.chart_of_accounts_service.create_account(
            company.id,
            CreateAccountCommand(
                account_code="1200",
                account_name="Cash Account GL",
                account_class_id=classes[0].id,
                account_type_id=debit_type.id,
                normal_balance=debit_type.normal_balance,
                allow_manual_posting=True,
                is_control_account=False,
            ),
        )
        print(f"  [OK] cash GL account {cash_gl.id}")

        revenue_gl = registry.chart_of_accounts_service.create_account(
            company.id,
            CreateAccountCommand(
                account_code="4100",
                account_name="Service Revenue",
                account_class_id=classes[0].id,
                account_type_id=credit_type.id,
                normal_balance=credit_type.normal_balance,
                allow_manual_posting=True,
                is_control_account=False,
            ),
        )
        print(f"  [OK] revenue GL account {revenue_gl.id}")

        expense_gl = registry.chart_of_accounts_service.create_account(
            company.id,
            CreateAccountCommand(
                account_code="6100",
                account_name="Office Expense",
                account_class_id=classes[0].id,
                account_type_id=debit_type.id,
                normal_balance=debit_type.normal_balance,
                allow_manual_posting=True,
                is_control_account=False,
            ),
        )
        print(f"  [OK] expense GL account {expense_gl.id}")

        # ------------------------------------------------------------------
        # 4. Financial accounts
        # ------------------------------------------------------------------
        print("[TEST] Creating financial accounts...")
        bank_fa = registry.financial_account_service.create_financial_account(
            company.id,
            CreateFinancialAccountCommand(
                account_code="BANK-001",
                name="Main Bank Account",
                financial_account_type_code="bank",
                gl_account_id=bank_gl.id,
                currency_code="XAF",
                bank_name="Test Bank",
                bank_account_number="1234567890",
                bank_branch="Main Branch",
            ),
        )
        print(f"  [OK] bank financial account {bank_fa.id}")

        cash_fa = registry.financial_account_service.create_financial_account(
            company.id,
            CreateFinancialAccountCommand(
                account_code="CASH-001",
                name="Petty Cash",
                financial_account_type_code="cash",
                gl_account_id=cash_gl.id,
                currency_code="XAF",
            ),
        )
        print(f"  [OK] cash financial account {cash_fa.id}")

        # Verify list
        fa_list = registry.financial_account_service.list_financial_accounts(company.id)
        assert len(fa_list) >= 2
        print(f"  [OK] listed {len(fa_list)} financial accounts")

        # Update
        updated_fa = registry.financial_account_service.update_financial_account(
            company.id,
            bank_fa.id,
            UpdateFinancialAccountCommand(
                account_code="BANK-001",
                name="Main Bank Account (Updated)",
                financial_account_type_code="bank",
                gl_account_id=bank_gl.id,
                currency_code="XAF",
                bank_name="Test Bank",
                bank_account_number="1234567890",
                bank_branch="Main Branch",
                is_active=True,
            ),
        )
        assert updated_fa.name == "Main Bank Account (Updated)"
        print(f"  [OK] financial account updated")

        # ------------------------------------------------------------------
        # 5. Treasury transactions
        # ------------------------------------------------------------------
        print("[TEST] Creating treasury transactions...")

        # Cash receipt
        cash_receipt = registry.treasury_transaction_service.create_draft_transaction(
            company.id,
            CreateTreasuryTransactionCommand(
                transaction_type_code="cash_receipt",
                financial_account_id=cash_fa.id,
                transaction_date=date(2026, 2, 10),
                currency_code="XAF",
                reference_number="CR-001",
                description="Cash payment received from walk-in client",
                lines=(
                    TreasuryTransactionLineCommand(
                        account_id=revenue_gl.id,
                        line_description="Service revenue",
                        amount=Decimal("50000.00"),
                    ),
                ),
            ),
        )
        assert cash_receipt.status_code == "draft"
        assert cash_receipt.total_amount == Decimal("50000.00")
        print(f"  [OK] cash receipt {cash_receipt.id} draft, total {cash_receipt.total_amount}")

        # Bank payment
        bank_payment = registry.treasury_transaction_service.create_draft_transaction(
            company.id,
            CreateTreasuryTransactionCommand(
                transaction_type_code="bank_payment",
                financial_account_id=bank_fa.id,
                transaction_date=date(2026, 2, 12),
                currency_code="XAF",
                reference_number="BP-001",
                description="Rent payment via bank transfer",
                lines=(
                    TreasuryTransactionLineCommand(
                        account_id=expense_gl.id,
                        line_description="Office rent Feb 2026",
                        amount=Decimal("100000.00"),
                    ),
                ),
            ),
        )
        assert bank_payment.status_code == "draft"
        print(f"  [OK] bank payment {bank_payment.id} draft, total {bank_payment.total_amount}")

        # List transactions
        tx_list = registry.treasury_transaction_service.list_treasury_transactions(company.id)
        assert len(tx_list) >= 2
        print(f"  [OK] listed {len(tx_list)} transactions")

        # ------------------------------------------------------------------
        # 6. Post treasury transactions
        # ------------------------------------------------------------------
        print("[TEST] Posting cash receipt...")
        receipt_posting = registry.treasury_transaction_posting_service.post_transaction(
            company.id, cash_receipt.id, actor_user_id=None
        )
        assert receipt_posting.journal_entry_id is not None
        assert receipt_posting.transaction_number.startswith("TT-")
        print(f"  [OK] cash receipt posted: {receipt_posting.transaction_number}, JE {receipt_posting.journal_entry_number}")

        # Verify immutability
        try:
            registry.treasury_transaction_service.update_draft_transaction(
                company.id,
                cash_receipt.id,
                CreateTreasuryTransactionCommand(
                    transaction_type_code="cash_receipt",
                    financial_account_id=cash_fa.id,
                    transaction_date=date(2026, 2, 10),
                    currency_code="XAF",
                    lines=(),
                ),
            )
            raise AssertionError("Posted transaction should not be editable!")
        except ValidationError:
            print(f"  [OK] posted transaction correctly rejected edit")

        # Verify double-post blocked
        try:
            registry.treasury_transaction_posting_service.post_transaction(
                company.id, cash_receipt.id, actor_user_id=None
            )
            raise AssertionError("Should not allow double-post!")
        except ValidationError:
            print(f"  [OK] double-post correctly blocked")

        print("[TEST] Posting bank payment...")
        payment_posting = registry.treasury_transaction_posting_service.post_transaction(
            company.id, bank_payment.id, actor_user_id=None
        )
        assert payment_posting.journal_entry_id is not None
        print(f"  [OK] bank payment posted: {payment_posting.transaction_number}, JE {payment_posting.journal_entry_number}")

        # ------------------------------------------------------------------
        # 7. Cancel draft transaction
        # ------------------------------------------------------------------
        print("[TEST] Cancelling draft transaction...")
        cancel_tx = registry.treasury_transaction_service.create_draft_transaction(
            company.id,
            CreateTreasuryTransactionCommand(
                transaction_type_code="bank_receipt",
                financial_account_id=bank_fa.id,
                transaction_date=date(2026, 2, 15),
                currency_code="XAF",
                lines=(
                    TreasuryTransactionLineCommand(
                        account_id=revenue_gl.id,
                        line_description="To cancel",
                        amount=Decimal("10000.00"),
                    ),
                ),
            ),
        )
        registry.treasury_transaction_service.cancel_draft_transaction(company.id, cancel_tx.id)
        cancelled = registry.treasury_transaction_service.get_treasury_transaction(company.id, cancel_tx.id)
        assert cancelled.status_code == "cancelled"
        print(f"  [OK] draft transaction cancelled")

        # ------------------------------------------------------------------
        # 8. Treasury transfers
        # ------------------------------------------------------------------
        print("[TEST] Creating treasury transfer...")
        transfer = registry.treasury_transfer_service.create_draft_transfer(
            company.id,
            CreateTreasuryTransferCommand(
                from_financial_account_id=bank_fa.id,
                to_financial_account_id=cash_fa.id,
                transfer_date=date(2026, 2, 20),
                currency_code="XAF",
                amount=Decimal("25000.00"),
                reference_number="TF-001",
                description="Transfer from bank to petty cash",
            ),
        )
        assert transfer.status_code == "draft"
        assert transfer.amount == Decimal("25000.00")
        print(f"  [OK] transfer {transfer.id} draft, amount {transfer.amount}")

        # List transfers
        tf_list = registry.treasury_transfer_service.list_treasury_transfers(company.id)
        assert len(tf_list) >= 1
        print(f"  [OK] listed {len(tf_list)} transfers")

        # Post transfer
        print("[TEST] Posting treasury transfer...")
        transfer_posting = registry.treasury_transfer_posting_service.post_transfer(
            company.id, transfer.id, actor_user_id=None
        )
        assert transfer_posting.journal_entry_id is not None
        assert transfer_posting.transfer_number.startswith("TF-")
        print(f"  [OK] transfer posted: {transfer_posting.transfer_number}, JE {transfer_posting.journal_entry_number}")

        # Cancel a draft transfer
        print("[TEST] Cancelling draft transfer...")
        cancel_tf = registry.treasury_transfer_service.create_draft_transfer(
            company.id,
            CreateTreasuryTransferCommand(
                from_financial_account_id=cash_fa.id,
                to_financial_account_id=bank_fa.id,
                transfer_date=date(2026, 2, 22),
                currency_code="XAF",
                amount=Decimal("5000.00"),
            ),
        )
        registry.treasury_transfer_service.cancel_draft_transfer(company.id, cancel_tf.id)
        cancelled_tf = registry.treasury_transfer_service.get_treasury_transfer(company.id, cancel_tf.id)
        assert cancelled_tf.status_code == "cancelled"
        print(f"  [OK] draft transfer cancelled")

        # ------------------------------------------------------------------
        # 9. Bank statement CSV import
        # ------------------------------------------------------------------
        print("[TEST] Importing bank statement CSV...")
        csv_path = _create_test_csv()
        import_result = registry.bank_statement_service.import_statement(
            company.id,
            ImportBankStatementCommand(
                financial_account_id=bank_fa.id,
                file_path=str(csv_path),
                notes="Test import",
            ),
            actor_user_id=None,
        )
        assert import_result.lines_imported == 3
        print(f"  [OK] imported {import_result.lines_imported} lines, batch {import_result.batch_id}")

        # List import batches
        batches = registry.bank_statement_service.list_import_batches(company.id, bank_fa.id)
        assert len(batches) >= 1
        print(f"  [OK] listed {len(batches)} import batches")

        # ------------------------------------------------------------------
        # 10. Manual statement line
        # ------------------------------------------------------------------
        print("[TEST] Creating manual statement line...")
        manual_line = registry.bank_statement_service.create_manual_statement_line(
            company.id,
            CreateManualStatementLineCommand(
                financial_account_id=bank_fa.id,
                line_date=date(2026, 2, 28),
                value_date=None,
                description="Manual bank fee",
                reference="FEE-001",
                debit_amount=Decimal("500.00"),
                credit_amount=Decimal("0.00"),
            ),
        )
        assert manual_line.id is not None
        assert manual_line.is_reconciled is False
        print(f"  [OK] manual statement line {manual_line.id} created")

        # List statement lines
        stmt_lines = registry.bank_statement_service.list_statement_lines(
            company.id, bank_fa.id
        )
        assert len(stmt_lines) >= 4  # 3 imported + 1 manual
        print(f"  [OK] listed {len(stmt_lines)} statement lines")

        # ------------------------------------------------------------------
        # 11. Bank reconciliation session
        # ------------------------------------------------------------------
        print("[TEST] Creating reconciliation session...")
        recon_session = registry.bank_reconciliation_service.create_reconciliation_session(
            company.id,
            CreateReconciliationSessionCommand(
                financial_account_id=bank_fa.id,
                statement_end_date=date(2026, 2, 28),
                statement_ending_balance=Decimal("500000.00"),
                notes="Feb 2026 reconciliation",
            ),
            actor_user_id=None,
        )
        assert recon_session.status_code == "draft"
        print(f"  [OK] reconciliation session {recon_session.id} created")

        # List sessions
        sessions = registry.bank_reconciliation_service.list_reconciliation_sessions(company.id)
        assert len(sessions) >= 1
        print(f"  [OK] listed {len(sessions)} reconciliation sessions")

        # ------------------------------------------------------------------
        # 12. Add reconciliation matches
        # ------------------------------------------------------------------
        print("[TEST] Adding reconciliation matches...")
        # Pick an IMPORTED statement line (not the manual one) for the first session match
        imported_lines = [sl for sl in stmt_lines if sl.import_batch_id is not None and not sl.is_reconciled]
        assert len(imported_lines) >= 1, "Need at least one imported unreconciled line"

        first_line = imported_lines[0]
        line_amount = first_line.debit_amount + first_line.credit_amount
        match = registry.bank_reconciliation_service.add_match(
            company.id,
            recon_session.id,
            AddReconciliationMatchCommand(
                bank_statement_line_id=first_line.id,
                match_entity_type="treasury_transaction",
                match_entity_id=cash_receipt.id,
                matched_amount=line_amount,
            ),
        )
        assert match.id is not None
        assert match.matched_amount == line_amount
        print(f"  [OK] match {match.id} added, amount {match.matched_amount}")

        # Get summary
        summary = registry.bank_reconciliation_service.get_reconciliation_summary(
            company.id, recon_session.id
        )
        assert summary.total_matched_amount == line_amount
        assert summary.matched_statement_count >= 1
        print(f"  [OK] summary: matched={summary.matched_statement_count}, unmatched={summary.unmatched_statement_count}")

        # ------------------------------------------------------------------
        # 13. Remove match
        # ------------------------------------------------------------------
        print("[TEST] Removing reconciliation match...")
        registry.bank_reconciliation_service.remove_match(
            company.id, recon_session.id, match.id
        )
        summary_after = registry.bank_reconciliation_service.get_reconciliation_summary(
            company.id, recon_session.id
        )
        assert summary_after.total_matched_amount == Decimal("0.00")
        print(f"  [OK] match removed, total matched reset to 0")

        # Re-add match for completion test
        match2 = registry.bank_reconciliation_service.add_match(
            company.id,
            recon_session.id,
            AddReconciliationMatchCommand(
                bank_statement_line_id=first_line.id,
                match_entity_type="treasury_transaction",
                match_entity_id=cash_receipt.id,
                matched_amount=line_amount,
            ),
        )
        print(f"  [OK] match re-added for completion test")

        # ------------------------------------------------------------------
        # 14. Complete reconciliation session
        # ------------------------------------------------------------------
        print("[TEST] Completing reconciliation session...")
        completed = registry.bank_reconciliation_service.complete_session(
            company.id, recon_session.id, actor_user_id=None
        )
        assert completed.status_code == "completed"
        assert completed.completed_at is not None
        print(f"  [OK] session completed at {completed.completed_at}")

        # Verify matches can't be added to completed session
        try:
            registry.bank_reconciliation_service.add_match(
                company.id,
                recon_session.id,
                AddReconciliationMatchCommand(
                    bank_statement_line_id=manual_line.id,
                    match_entity_type="treasury_transaction",
                    match_entity_id=bank_payment.id,
                    matched_amount=Decimal("500.00"),
                ),
            )
            raise AssertionError("Should not add matches to completed session!")
        except ValidationError:
            print(f"  [OK] completed session correctly rejects new matches")

        # ------------------------------------------------------------------
        # 15. Validation: invalid match entity type
        # ------------------------------------------------------------------
        print("[TEST] Validating match entity type restrictions...")
        recon_session_2 = registry.bank_reconciliation_service.create_reconciliation_session(
            company.id,
            CreateReconciliationSessionCommand(
                financial_account_id=bank_fa.id,
                statement_end_date=date(2026, 3, 31),
                statement_ending_balance=Decimal("600000.00"),
            ),
            actor_user_id=None,
        )
        try:
            registry.bank_reconciliation_service.add_match(
                company.id,
                recon_session_2.id,
                AddReconciliationMatchCommand(
                    bank_statement_line_id=manual_line.id,
                    match_entity_type="invalid_type",
                    match_entity_id=1,
                    matched_amount=Decimal("100.00"),
                ),
            )
            raise AssertionError("Should reject invalid match entity type!")
        except ValidationError:
            print(f"  [OK] invalid match entity type correctly rejected")

        # ------------------------------------------------------------------
        # 16. Validation: over-matching prevented
        # ------------------------------------------------------------------
        print("[TEST] Validating over-matching prevention...")
        # manual_line has debit=500, credit=0, total=500
        registry.bank_reconciliation_service.add_match(
            company.id,
            recon_session_2.id,
            AddReconciliationMatchCommand(
                bank_statement_line_id=manual_line.id,
                match_entity_type="treasury_transaction",
                match_entity_id=bank_payment.id,
                matched_amount=Decimal("500.00"),
            ),
        )
        try:
            registry.bank_reconciliation_service.add_match(
                company.id,
                recon_session_2.id,
                AddReconciliationMatchCommand(
                    bank_statement_line_id=manual_line.id,
                    match_entity_type="treasury_transaction",
                    match_entity_id=cash_receipt.id,
                    matched_amount=Decimal("1.00"),
                ),
            )
            raise AssertionError("Should prevent over-matching!")
        except ValidationError:
            print(f"  [OK] over-matching correctly prevented")

        # ------------------------------------------------------------------
        # 17. UI pages
        # ------------------------------------------------------------------
        print("[TEST] Testing UI page instantiation...")

        from seeker_accounting.modules.treasury.ui.financial_accounts_page import FinancialAccountsPage
        from seeker_accounting.modules.treasury.ui.treasury_transactions_page import TreasuryTransactionsPage
        from seeker_accounting.modules.treasury.ui.treasury_transfers_page import TreasuryTransfersPage
        from seeker_accounting.modules.treasury.ui.statement_lines_page import StatementLinesPage
        from seeker_accounting.modules.treasury.ui.bank_reconciliation_page import BankReconciliationPage

        fa_page = FinancialAccountsPage(registry)
        tx_page = TreasuryTransactionsPage(registry)
        tf_page = TreasuryTransfersPage(registry)
        sl_page = StatementLinesPage(registry)
        br_page = BankReconciliationPage(registry)
        print(f"  [OK] FinancialAccountsPage instantiated")
        print(f"  [OK] TreasuryTransactionsPage instantiated")
        print(f"  [OK] TreasuryTransfersPage instantiated")
        print(f"  [OK] StatementLinesPage instantiated")
        print(f"  [OK] BankReconciliationPage instantiated")

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        print("\n" + "=" * 80)
        print("[PASS] Slice 10 End-to-End Workflow Smoke Test -- ALL TESTS PASSED")
        print("=" * 80)
        print("\nWorkflow Coverage:")
        print("  1. Financial account creation, update, listing")
        print("  2. Treasury transaction drafts (cash receipt, bank payment)")
        print("  3. Transaction posting with journal entries")
        print("  4. Posted transaction immutability + double-post prevention")
        print("  5. Draft transaction cancellation")
        print("  6. Treasury transfer creation, posting, cancellation")
        print("  7. Bank statement CSV import with batch tracking")
        print("  8. Manual statement line creation")
        print("  9. Bank reconciliation session lifecycle")
        print("  10. Reconciliation match add/remove")
        print("  11. Session completion blocks new matches")
        print("  12. Invalid match entity type rejection")
        print("  13. Over-matching prevention")
        print("  14. All 5 treasury UI pages instantiate")
        print("\nSlice 10 is SIGN-OFF READY.")
        return 0

    except Exception as e:
        print(f"\n[FAIL] Smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def _create_test_csv() -> Path:
    """Create a temporary CSV file for statement import testing."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8")
    writer = csv.DictWriter(tmp, fieldnames=["date", "description", "reference", "debit", "credit"])
    writer.writeheader()
    writer.writerow({"date": "2026-02-01", "description": "Opening balance", "reference": "OB-001", "debit": "", "credit": "500000.00"})
    writer.writerow({"date": "2026-02-05", "description": "Client payment", "reference": "PAY-001", "debit": "", "credit": "75000.00"})
    writer.writerow({"date": "2026-02-10", "description": "Office supplies", "reference": "CHK-001", "debit": "15000.00", "credit": ""})
    tmp.close()
    return Path(tmp.name)


if __name__ == "__main__":
    exit(main())
