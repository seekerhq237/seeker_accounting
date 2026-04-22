from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.treasury.dto.bank_statement_commands import (
    CreateManualStatementLineCommand,
    ImportBankStatementCommand,
)
from seeker_accounting.modules.treasury.dto.bank_statement_dto import (
    BankStatementImportBatchDTO,
    BankStatementLineDTO,
    ImportResultDTO,
)
from seeker_accounting.modules.treasury.models.bank_statement_import_batch import BankStatementImportBatch
from seeker_accounting.modules.treasury.models.bank_statement_line import BankStatementLine
from seeker_accounting.modules.treasury.repositories.bank_statement_import_batch_repository import (
    BankStatementImportBatchRepository,
)
from seeker_accounting.modules.treasury.repositories.bank_statement_line_repository import (
    BankStatementLineRepository,
)
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]
BankStatementImportBatchRepositoryFactory = Callable[[Session], BankStatementImportBatchRepository]
BankStatementLineRepositoryFactory = Callable[[Session], BankStatementLineRepository]


class BankStatementService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        bank_statement_import_batch_repository_factory: BankStatementImportBatchRepositoryFactory,
        bank_statement_line_repository_factory: BankStatementLineRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._bank_statement_import_batch_repository_factory = bank_statement_import_batch_repository_factory
        self._bank_statement_line_repository_factory = bank_statement_line_repository_factory
        self._audit_service = audit_service

    def list_statement_lines(
        self,
        company_id: int,
        financial_account_id: int,
        reconciled_only: bool | None = None,
    ) -> list[BankStatementLineDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            line_repo = self._bank_statement_line_repository_factory(uow.session)
            rows = line_repo.list_by_financial_account(
                company_id, financial_account_id, reconciled_only=reconciled_only,
            )
            return [self._to_line_dto(r) for r in rows]

    def list_import_batches(
        self,
        company_id: int,
        financial_account_id: int | None = None,
    ) -> list[BankStatementImportBatchDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            batch_repo = self._bank_statement_import_batch_repository_factory(uow.session)
            rows = batch_repo.list_by_company(company_id, financial_account_id=financial_account_id)
            return [self._to_batch_dto(r) for r in rows]

    def create_manual_statement_line(
        self,
        company_id: int,
        command: CreateManualStatementLineCommand,
    ) -> BankStatementLineDTO:
        if command.debit_amount < Decimal("0.00") or command.credit_amount < Decimal("0.00"):
            raise ValidationError("Debit and credit amounts must not be negative.")
        if command.debit_amount == Decimal("0.00") and command.credit_amount == Decimal("0.00"):
            raise ValidationError("At least one of debit or credit amount must be greater than zero.")
        if not command.description or not command.description.strip():
            raise ValidationError("Statement line description is required.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fa_repo = self._financial_account_repository_factory(uow.session)
            fa = fa_repo.get_by_id(company_id, command.financial_account_id)
            if fa is None:
                raise ValidationError("Financial account must belong to the company.")

            line_repo = self._bank_statement_line_repository_factory(uow.session)
            line = BankStatementLine(
                company_id=company_id,
                financial_account_id=command.financial_account_id,
                import_batch_id=None,
                line_date=command.line_date,
                value_date=command.value_date,
                description=command.description.strip(),
                reference=command.reference,
                debit_amount=command.debit_amount,
                credit_amount=command.credit_amount,
                is_reconciled=False,
            )
            line_repo.add(line)
            uow.commit()
            return self._to_line_dto(line)

    def import_statement(
        self,
        company_id: int,
        command: ImportBankStatementCommand,
        actor_user_id: int | None = None,
    ) -> ImportResultDTO:
        file_path = Path(command.file_path)
        if not file_path.exists():
            raise ValidationError(f"Statement file not found: {command.file_path}")

        suffix = file_path.suffix.lower()
        if suffix != ".csv":
            raise ValidationError(f"Unsupported statement file format: {suffix}. Only CSV is supported.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fa_repo = self._financial_account_repository_factory(uow.session)
            fa = fa_repo.get_by_id(company_id, command.financial_account_id)
            if fa is None:
                raise ValidationError("Financial account must belong to the company.")

            parsed_lines = self._parse_csv(file_path)
            if not parsed_lines:
                raise ValidationError("No valid statement lines found in the file.")

            start_date = min(pl["line_date"] for pl in parsed_lines)
            end_date = max(pl["line_date"] for pl in parsed_lines)

            batch_repo = self._bank_statement_import_batch_repository_factory(uow.session)
            batch = BankStatementImportBatch(
                company_id=company_id,
                financial_account_id=command.financial_account_id,
                file_name=file_path.name,
                import_source="csv",
                statement_start_date=start_date,
                statement_end_date=end_date,
                line_count=len(parsed_lines),
                notes=command.notes,
                imported_by_user_id=actor_user_id,
            )
            batch_repo.add(batch)
            uow.session.flush()

            line_repo = self._bank_statement_line_repository_factory(uow.session)
            for pl in parsed_lines:
                line = BankStatementLine(
                    company_id=company_id,
                    financial_account_id=command.financial_account_id,
                    import_batch_id=batch.id,
                    line_date=pl["line_date"],
                    value_date=pl.get("value_date"),
                    description=pl["description"],
                    reference=pl.get("reference"),
                    debit_amount=pl.get("debit_amount", Decimal("0.00")),
                    credit_amount=pl.get("credit_amount", Decimal("0.00")),
                    is_reconciled=False,
                )
                line_repo.add(line)

            uow.commit()

            return ImportResultDTO(
                batch_id=batch.id,
                lines_imported=len(parsed_lines),
                statement_start_date=start_date,
                statement_end_date=end_date,
            )

    def _parse_csv(self, file_path: Path) -> list[dict]:
        parsed: list[dict] = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):
                line_date_str = (row.get("date") or row.get("Date") or row.get("DATE") or "").strip()
                if not line_date_str:
                    continue

                try:
                    line_date = date.fromisoformat(line_date_str)
                except ValueError:
                    continue

                description = (
                    row.get("description") or row.get("Description") or row.get("DESCRIPTION") or ""
                ).strip()
                if not description:
                    continue

                reference = (row.get("reference") or row.get("Reference") or row.get("REF") or "").strip() or None
                value_date_str = (row.get("value_date") or row.get("Value Date") or "").strip()
                value_date = None
                if value_date_str:
                    try:
                        value_date = date.fromisoformat(value_date_str)
                    except ValueError:
                        pass

                debit = self._parse_amount(row.get("debit") or row.get("Debit") or row.get("DEBIT"))
                credit = self._parse_amount(row.get("credit") or row.get("Credit") or row.get("CREDIT"))

                # Handle single amount column
                if debit == Decimal("0.00") and credit == Decimal("0.00"):
                    amount_str = row.get("amount") or row.get("Amount") or row.get("AMOUNT")
                    if amount_str:
                        amount = self._parse_amount(amount_str)
                        if amount < Decimal("0.00"):
                            debit = abs(amount)
                        elif amount > Decimal("0.00"):
                            credit = amount

                if debit == Decimal("0.00") and credit == Decimal("0.00"):
                    continue

                parsed.append({
                    "line_date": line_date,
                    "value_date": value_date,
                    "description": description,
                    "reference": reference,
                    "debit_amount": debit,
                    "credit_amount": credit,
                })

        return parsed

    def _parse_amount(self, value: str | None) -> Decimal:
        if not value:
            return Decimal("0.00")
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return Decimal("0.00")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal("0.00")

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _to_line_dto(self, row: BankStatementLine) -> BankStatementLineDTO:
        return BankStatementLineDTO(
            id=row.id,
            company_id=row.company_id,
            financial_account_id=row.financial_account_id,
            import_batch_id=row.import_batch_id,
            line_date=row.line_date,
            value_date=row.value_date,
            description=row.description,
            reference=row.reference,
            debit_amount=row.debit_amount,
            credit_amount=row.credit_amount,
            is_reconciled=row.is_reconciled,
            created_at=row.created_at,
        )

    def _to_batch_dto(self, row: BankStatementImportBatch) -> BankStatementImportBatchDTO:
        return BankStatementImportBatchDTO(
            id=row.id,
            company_id=row.company_id,
            financial_account_id=row.financial_account_id,
            file_name=row.file_name,
            import_source=row.import_source,
            statement_start_date=row.statement_start_date,
            statement_end_date=row.statement_end_date,
            line_count=row.line_count,
            notes=row.notes,
            imported_at=row.imported_at,
            imported_by_user_id=row.imported_by_user_id,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_TREASURY
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_TREASURY,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
