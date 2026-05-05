from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db import model_registry  # noqa: F401
from seeker_accounting.db.base import Base
from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.contracts_projects.dto.contract_commercial_dto import (
    ContractBillingScheduleItemCommand,
    ContractLineCommand,
)
from seeker_accounting.modules.contracts_projects.dto.contract_progress_billing_dto import (
    CreateProgressClaimCommand,
    ProgressClaimLineCommand,
    RecordContractReceiptAllocationCommand,
    RecordCustomerAdvanceCommand,
    ReleaseRetentionCommand,
)
from seeker_accounting.modules.contracts_projects.models.contract import Contract
from seeker_accounting.modules.contracts_projects.models.contract_change_order import ContractChangeOrder
from seeker_accounting.modules.contracts_projects.models.contract_progress_claim_line import ContractProgressClaimLine
from seeker_accounting.modules.contracts_projects.models.contract_retention_movement import ContractRetentionMovement
from seeker_accounting.modules.contracts_projects.repositories.contract_billing_schedule_repository import (
    ContractBillingScheduleRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_change_order_repository import (
    ContractChangeOrderRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_customer_advance_repository import (
    ContractCustomerAdvanceRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_line_repository import ContractLineRepository
from seeker_accounting.modules.contracts_projects.repositories.contract_progress_claim_repository import (
    ContractProgressClaimRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_receipt_allocation_repository import (
    ContractReceiptAllocationRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_repository import ContractRepository
from seeker_accounting.modules.contracts_projects.repositories.contract_retention_movement_repository import (
    ContractRetentionMovementRepository,
)
from seeker_accounting.modules.contracts_projects.services.contract_commercial_service import ContractCommercialService
from seeker_accounting.modules.contracts_projects.services.contract_progress_billing_service import (
    ContractProgressBillingService,
)
from seeker_accounting.modules.customers.models.customer import Customer
from seeker_accounting.platform.exceptions import ValidationError


def _make_session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


class ContractCommercialProgressBillingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._session_factory = _make_session_factory()
        self._unit_of_work_factory = create_unit_of_work_factory(self._session_factory)
        self.company_id, self.contract_id = self._seed_contract()
        self.commercial_service = ContractCommercialService(
            unit_of_work_factory=self._unit_of_work_factory,
            contract_repository_factory=ContractRepository,
            contract_line_repository_factory=ContractLineRepository,
            billing_schedule_repository_factory=ContractBillingScheduleRepository,
            change_order_repository_factory=ContractChangeOrderRepository,
            progress_claim_repository_factory=ContractProgressClaimRepository,
            receipt_allocation_repository_factory=ContractReceiptAllocationRepository,
            advance_repository_factory=ContractCustomerAdvanceRepository,
            retention_movement_repository_factory=ContractRetentionMovementRepository,
        )
        self.progress_service = ContractProgressBillingService(
            unit_of_work_factory=self._unit_of_work_factory,
            contract_repository_factory=ContractRepository,
            progress_claim_repository_factory=ContractProgressClaimRepository,
            advance_repository_factory=ContractCustomerAdvanceRepository,
            retention_movement_repository_factory=ContractRetentionMovementRepository,
            receipt_allocation_repository_factory=ContractReceiptAllocationRepository,
        )

    def test_contract_value_summary_reconciles_lines_change_orders_and_schedule(self) -> None:
        self.commercial_service.replace_contract_lines(
            self.company_id,
            self.contract_id,
            (
                ContractLineCommand(
                    description="Mobilization",
                    quantity=Decimal("1"),
                    unit_rate=Decimal("250.00"),
                ),
                ContractLineCommand(
                    description="Construction works",
                    quantity=Decimal("3"),
                    unit_rate=Decimal("250.00"),
                ),
            ),
        )
        self._add_approved_change_order(Decimal("200.00"))
        self.commercial_service.replace_billing_schedule(
            self.company_id,
            self.contract_id,
            (
                ContractBillingScheduleItemCommand(
                    schedule_type_code="milestone",
                    description="Milestone 1",
                    scheduled_amount=Decimal("600.00"),
                    scheduled_date=date(2026, 1, 31),
                ),
                ContractBillingScheduleItemCommand(
                    schedule_type_code="milestone",
                    description="Milestone 2",
                    scheduled_amount=Decimal("600.00"),
                    scheduled_date=date(2026, 2, 28),
                ),
            ),
        )

        summary = self.commercial_service.get_contract_value_summary(self.company_id, self.contract_id)

        self.assertEqual(summary.original_contract_value, Decimal("1000.00"))
        self.assertEqual(summary.approved_variations, Decimal("200.00"))
        self.assertEqual(summary.current_contract_value, Decimal("1200.00"))
        self.assertEqual(summary.billing_schedule_total, Decimal("1200.00"))
        self.assertTrue(summary.schedule_reconciles_to_contract_value)

    def test_progress_claim_tracks_deductions_advances_receipts_and_retention(self) -> None:
        self.progress_service.record_customer_advance(
            self.company_id,
            RecordCustomerAdvanceCommand(
                contract_id=self.contract_id,
                advance_number="ADV-001",
                advance_date=date(2026, 1, 5),
                advance_amount=Decimal("300.00"),
                received_amount=Decimal("300.00"),
            ),
        )

        claim = self.progress_service.create_progress_claim(
            self.company_id,
            CreateProgressClaimCommand(
                contract_id=self.contract_id,
                claim_number="PC-001",
                claim_date=date(2026, 1, 31),
                certified_amount=Decimal("400.00"),
                vat_amount=Decimal("80.00"),
                retention_percent=Decimal("10.00"),
                advance_recovery_amount=Decimal("50.00"),
                withheld_vat_amount=Decimal("20.00"),
                withholding_tax_amount=Decimal("10.00"),
                lines=(
                    ProgressClaimLineCommand(
                        description="Certified works",
                        quantity=Decimal("1"),
                        unit_rate=Decimal("400.00"),
                    ),
                ),
            ),
        )

        self.assertEqual(claim.current_claim_amount, Decimal("400.00"))
        self.assertEqual(claim.retention_amount, Decimal("40.00"))
        self.assertEqual(claim.net_receivable_amount, Decimal("360.00"))
        self._assert_claim_line_parented(claim.id)

        advance_balance = self.progress_service.get_advance_balance(self.company_id, self.contract_id)
        self.assertEqual(advance_balance.received_advance_amount, Decimal("300.00"))
        self.assertEqual(advance_balance.recovered_advance_amount, Decimal("50.00"))
        self.assertEqual(advance_balance.unrecovered_advance_amount, Decimal("250.00"))

        allocated = self.progress_service.record_receipt_allocation(
            self.company_id,
            RecordContractReceiptAllocationCommand(
                contract_id=self.contract_id,
                progress_claim_id=claim.id,
                allocation_date=date(2026, 2, 10),
                gross_amount=Decimal("480.00"),
                net_receivable_amount=Decimal("360.00"),
                withholding_vat_amount=Decimal("20.00"),
                withholding_tax_amount=Decimal("10.00"),
                retention_amount=Decimal("40.00"),
                advance_recovery_amount=Decimal("50.00"),
            ),
        )
        self.assertEqual(allocated, Decimal("480.00"))

        self._add_open_retention(claim.id, Decimal("40.00"))
        retention_balance = self.progress_service.release_retention(
            self.company_id,
            ReleaseRetentionCommand(
                contract_id=self.contract_id,
                progress_claim_id=claim.id,
                movement_date=date(2026, 3, 15),
                amount=Decimal("15.00"),
            ),
        )
        self.assertEqual(retention_balance.open_retention_amount, Decimal("25.00"))

    def test_receipt_allocation_requires_component_reconciliation(self) -> None:
        with self.assertRaises(ValidationError):
            self.progress_service.record_receipt_allocation(
                self.company_id,
                RecordContractReceiptAllocationCommand(
                    contract_id=self.contract_id,
                    allocation_date=date(2026, 2, 10),
                    gross_amount=Decimal("100.00"),
                    net_receivable_amount=Decimal("80.00"),
                    withholding_vat_amount=Decimal("5.00"),
                ),
            )

    def _seed_contract(self) -> tuple[int, int]:
        with self._session_factory() as session:
            country = Country(code="CM", name="Cameroon")
            currency = Currency(code="XAF", name="Central African CFA franc", symbol="XAF", decimal_places=0)
            company = Company(
                legal_name="Test Contract Company",
                display_name="Test Contract Company",
                registration_number=None,
                tax_identifier=None,
                country_code=country.code,
                base_currency_code=currency.code,
            )
            session.add_all([country, currency, company])
            session.flush()
            customer = Customer(
                company_id=company.id,
                customer_code="CUST-001",
                display_name="Public Works Client",
                legal_name=None,
                country_code=country.code,
            )
            session.add(customer)
            session.flush()
            contract = Contract(
                company_id=company.id,
                contract_number="C-001",
                contract_title="Road Works",
                customer_id=customer.id,
                contract_type_code="fixed_price",
                currency_code=currency.code,
                exchange_rate=None,
                base_contract_amount=Decimal("1000.00"),
                start_date=date(2026, 1, 1),
                planned_end_date=date(2026, 12, 31),
                status_code="active",
                billing_basis_code="milestone",
                retention_percent=Decimal("10.00"),
                reference_number=None,
                description=None,
                created_by_user_id=None,
            )
            session.add(contract)
            session.commit()
            return company.id, contract.id

    def _add_approved_change_order(self, amount: Decimal) -> None:
        with self._session_factory() as session:
            session.add(
                ContractChangeOrder(
                    company_id=self.company_id,
                    contract_id=self.contract_id,
                    change_order_number="CO-001",
                    change_order_date=date(2026, 1, 15),
                    status_code="approved",
                    change_type_code="variation",
                    description="Approved variation",
                    contract_amount_delta=amount,
                    days_extension=None,
                    effective_date=date(2026, 1, 15),
                    approved_at=None,
                    approved_by_user_id=None,
                )
            )
            session.commit()

    def _add_open_retention(self, claim_id: int, amount: Decimal) -> None:
        with self._session_factory() as session:
            session.add(
                ContractRetentionMovement(
                    company_id=self.company_id,
                    contract_id=self.contract_id,
                    progress_claim_id=claim_id,
                    sales_invoice_id=None,
                    customer_receipt_id=None,
                    movement_date=date(2026, 1, 31),
                    due_date=None,
                    movement_type_code="withheld",
                    status_code="open",
                    amount=amount,
                    notes=None,
                )
            )
            session.commit()

    def _assert_claim_line_parented(self, claim_id: int) -> None:
        with self._session_factory() as session:
            line = session.scalar(select(ContractProgressClaimLine))
            self.assertIsNotNone(line)
            assert line is not None
            self.assertEqual(line.progress_claim_id, claim_id)


if __name__ == "__main__":
    unittest.main()
