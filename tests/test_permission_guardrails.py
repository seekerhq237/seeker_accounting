from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.security.permission_map import (
    build_navigation_denied_message,
    can_access_navigation,
)
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_code_account_mapping_dto import (
    SetTaxCodeAccountMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.services.account_role_mapping_service import (
    AccountRoleMappingService,
)
from seeker_accounting.modules.accounting.reference_data.services.numbering_setup_service import (
    NumberingSetupService,
)
from seeker_accounting.modules.accounting.reference_data.services.reference_data_service import (
    ReferenceDataService,
)
from seeker_accounting.modules.accounting.reference_data.services.tax_setup_service import (
    TaxSetupService,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.purchases.dto.supplier_payment_commands import (
    CreateSupplierPaymentCommand,
    SupplierPaymentAllocationCommand,
)
from seeker_accounting.modules.purchases.services.purchase_bill_service import PurchaseBillService
from seeker_accounting.modules.purchases.services.supplier_payment_service import SupplierPaymentService
from seeker_accounting.modules.sales.dto.customer_receipt_commands import (
    CreateCustomerReceiptCommand,
    CustomerReceiptAllocationCommand,
)
from seeker_accounting.modules.sales.services.customer_receipt_service import CustomerReceiptService
from seeker_accounting.modules.sales.services.sales_invoice_service import SalesInvoiceService
from seeker_accounting.modules.treasury.dto.financial_account_commands import CreateFinancialAccountCommand
from seeker_accounting.modules.treasury.dto.treasury_transaction_commands import (
    CreateTreasuryTransactionCommand,
    TreasuryTransactionLineCommand,
)
from seeker_accounting.modules.treasury.dto.treasury_transfer_commands import CreateTreasuryTransferCommand
from seeker_accounting.modules.treasury.services.financial_account_service import FinancialAccountService
from seeker_accounting.modules.treasury.services.treasury_transaction_service import TreasuryTransactionService
from seeker_accounting.modules.treasury.services.treasury_transfer_posting_service import (
    TreasuryTransferPostingService,
)
from seeker_accounting.modules.treasury.services.treasury_transfer_service import TreasuryTransferService
from seeker_accounting.platform.exceptions import PermissionDeniedError


def _unused_factory(*_args, **_kwargs):  # noqa: ANN001, ANN002
    raise AssertionError("Repository access should not happen when permission is denied first.")


class PermissionGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.permission_service = self._permission_service()

    def _permission_service(self, permissions: tuple[str, ...] = tuple()) -> PermissionService:
        return PermissionService(
            AppContext(
                current_user_id=7,
                current_user_display_name="Test User",
                active_company_id=None,
                active_company_name=None,
                theme_name="light",
                permission_snapshot=permissions,
            )
        )

    def test_permission_service_builds_plain_english_denial_message(self) -> None:
        self.assertEqual(
            self.permission_service.build_denied_message("customers.create"),
            "You do not have permission to create customer records.",
        )

    def test_navigation_policy_denies_inaccessible_routes(self) -> None:
        self.assertFalse(can_access_navigation(self.permission_service, nav_ids.CUSTOMERS))
        self.assertEqual(
            build_navigation_denied_message(self.permission_service, nav_ids.CUSTOMERS),
            "You do not have permission to view customer master records.",
        )

    def test_navigation_policy_allows_access_when_required_permission_exists(self) -> None:
        self.permission_service = self._permission_service(("customers.view",))

        self.assertTrue(can_access_navigation(self.permission_service, nav_ids.CUSTOMERS))

    def test_reference_data_service_fails_closed_without_payment_term_view_permission(self) -> None:
        service = ReferenceDataService(
            unit_of_work_factory=_unused_factory,
            country_repository_factory=_unused_factory,
            currency_repository_factory=_unused_factory,
            account_class_repository_factory=_unused_factory,
            account_type_repository_factory=_unused_factory,
            payment_term_repository_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.list_payment_terms(company_id=1)

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to view payment terms used across customer and supplier workflows.",
        )

    def test_tax_setup_service_fails_closed_without_mapping_manage_permission(self) -> None:
        service = TaxSetupService(
            unit_of_work_factory=_unused_factory,
            tax_code_repository_factory=_unused_factory,
            tax_code_account_mapping_repository_factory=_unused_factory,
            account_repository_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.set_tax_code_account_mapping(
                company_id=1,
                command=SetTaxCodeAccountMappingCommand(
                    tax_code_id=10,
                    sales_account_id=11,
                    purchase_account_id=12,
                    tax_liability_account_id=13,
                    tax_asset_account_id=14,
                ),
            )

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to create and update tax code account mappings.",
        )

    def test_numbering_setup_service_fails_closed_without_preview_permission(self) -> None:
        service = NumberingSetupService(
            unit_of_work_factory=_unused_factory,
            document_sequence_repository_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.preview_document_number(company_id=1, sequence_id=99)

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to preview generated document numbers from a numbering sequence.",
        )

    def test_account_role_mapping_service_fails_closed_without_manage_permission(self) -> None:
        service = AccountRoleMappingService(
            unit_of_work_factory=_unused_factory,
            account_repository_factory=_unused_factory,
            account_role_mapping_repository_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.set_role_mapping(
                company_id=1,
                command=SetAccountRoleMappingCommand(role_code="ar_control", account_id=100),
            )

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to create and update operational account role mappings.",
        )

    def test_sales_invoice_service_fails_closed_without_invoice_view_permission(self) -> None:
        service = SalesInvoiceService(
            unit_of_work_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            customer_repository_factory=_unused_factory,
            currency_repository_factory=_unused_factory,
            account_repository_factory=_unused_factory,
            tax_code_repository_factory=_unused_factory,
            sales_invoice_repository_factory=_unused_factory,
            sales_invoice_line_repository_factory=_unused_factory,
            customer_receipt_allocation_repository_factory=_unused_factory,
            project_dimension_validation_service=None,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.list_sales_invoices(company_id=1)

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to view sales invoices and their status.",
        )

    def test_customer_receipt_service_requires_allocation_permission_for_allocated_receipts(self) -> None:
        service = CustomerReceiptService(
            unit_of_work_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            customer_repository_factory=_unused_factory,
            currency_repository_factory=_unused_factory,
            financial_account_repository_factory=_unused_factory,
            sales_invoice_repository_factory=_unused_factory,
            customer_receipt_repository_factory=_unused_factory,
            customer_receipt_allocation_repository_factory=_unused_factory,
            permission_service=self._permission_service(("sales.receipts.create",)),
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.create_draft_receipt(
                company_id=1,
                command=CreateCustomerReceiptCommand(
                    customer_id=10,
                    financial_account_id=11,
                    receipt_date=date(2026, 1, 15),
                    currency_code="XAF",
                    exchange_rate=None,
                    amount_received=Decimal("2500.00"),
                    reference_number=None,
                    notes=None,
                    allocations=(
                        CustomerReceiptAllocationCommand(
                            sales_invoice_id=12,
                            allocated_amount=Decimal("2500.00"),
                        ),
                    ),
                ),
            )

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to allocate customer receipts against open invoices.",
        )

    def test_purchase_bill_service_fails_closed_without_cancel_permission(self) -> None:
        service = PurchaseBillService(
            unit_of_work_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            supplier_repository_factory=_unused_factory,
            currency_repository_factory=_unused_factory,
            account_repository_factory=_unused_factory,
            tax_code_repository_factory=_unused_factory,
            purchase_bill_repository_factory=_unused_factory,
            purchase_bill_line_repository_factory=_unused_factory,
            supplier_payment_allocation_repository_factory=_unused_factory,
            project_dimension_validation_service=None,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.cancel_draft_bill(company_id=1, bill_id=99)

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to cancel draft purchase bills.",
        )

    def test_supplier_payment_service_requires_allocation_permission_for_allocated_payments(self) -> None:
        service = SupplierPaymentService(
            unit_of_work_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            supplier_repository_factory=_unused_factory,
            currency_repository_factory=_unused_factory,
            financial_account_repository_factory=_unused_factory,
            purchase_bill_repository_factory=_unused_factory,
            supplier_payment_repository_factory=_unused_factory,
            supplier_payment_allocation_repository_factory=_unused_factory,
            permission_service=self._permission_service(("purchases.payments.create",)),
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.create_draft_payment(
                company_id=1,
                command=CreateSupplierPaymentCommand(
                    supplier_id=10,
                    financial_account_id=11,
                    payment_date=date(2026, 1, 15),
                    currency_code="XAF",
                    exchange_rate=None,
                    amount_paid=Decimal("1800.00"),
                    reference_number=None,
                    notes=None,
                    allocations=(
                        SupplierPaymentAllocationCommand(
                            purchase_bill_id=12,
                            allocated_amount=Decimal("1800.00"),
                        ),
                    ),
                ),
            )

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to allocate supplier payments against open purchase bills.",
        )

    def test_financial_account_service_fails_closed_without_create_permission(self) -> None:
        service = FinancialAccountService(
            unit_of_work_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            account_repository_factory=_unused_factory,
            currency_repository_factory=_unused_factory,
            financial_account_repository_factory=_unused_factory,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.create_financial_account(
                company_id=1,
                command=CreateFinancialAccountCommand(
                    account_code="BNK001",
                    name="Main Bank",
                    financial_account_type_code="bank",
                    gl_account_id=100,
                    currency_code="XAF",
                ),
            )

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to create financial account master records.",
        )

    def test_treasury_transaction_service_fails_closed_without_create_permission(self) -> None:
        service = TreasuryTransactionService(
            unit_of_work_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            account_repository_factory=_unused_factory,
            currency_repository_factory=_unused_factory,
            financial_account_repository_factory=_unused_factory,
            treasury_transaction_repository_factory=_unused_factory,
            treasury_transaction_line_repository_factory=_unused_factory,
            project_dimension_validation_service=None,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.create_draft_transaction(
                company_id=1,
                command=CreateTreasuryTransactionCommand(
                    transaction_type_code="cash_receipt",
                    financial_account_id=10,
                    transaction_date=date(2026, 1, 15),
                    currency_code="XAF",
                    lines=(
                        TreasuryTransactionLineCommand(
                            account_id=200,
                            line_description="Cash received",
                            amount=Decimal("1000.00"),
                        ),
                    ),
                ),
            )

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to create draft treasury transactions.",
        )

    def test_treasury_transfer_service_fails_closed_without_create_permission(self) -> None:
        service = TreasuryTransferService(
            unit_of_work_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            financial_account_repository_factory=_unused_factory,
            treasury_transfer_repository_factory=_unused_factory,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.create_draft_transfer(
                company_id=1,
                command=CreateTreasuryTransferCommand(
                    from_financial_account_id=10,
                    to_financial_account_id=11,
                    transfer_date=date(2026, 1, 15),
                    currency_code="XAF",
                    amount=Decimal("750.00"),
                ),
            )

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to create draft inter-account transfers.",
        )

    def test_treasury_transfer_posting_service_fails_closed_without_post_permission(self) -> None:
        service = TreasuryTransferPostingService(
            unit_of_work_factory=_unused_factory,
            app_context=AppContext(
                current_user_id=7,
                current_user_display_name="Test User",
                active_company_id=None,
                active_company_name=None,
                theme_name="light",
                permission_snapshot=tuple(),
            ),
            treasury_transfer_repository_factory=_unused_factory,
            journal_entry_repository_factory=_unused_factory,
            fiscal_period_repository_factory=_unused_factory,
            financial_account_repository_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            numbering_service=None,
            permission_service=self.permission_service,
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.post_transfer(company_id=1, transfer_id=99)

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to post inter-account treasury transfers.",
        )


if __name__ == "__main__":
    unittest.main()
