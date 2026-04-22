from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.general_ledger_report_dto import (
    GeneralLedgerAccountDTO,
    GeneralLedgerLineDTO,
    GeneralLedgerReportDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.repositories.general_ledger_report_repository import (
    GeneralLedgerReportRepository,
    LedgerLineRow,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

GeneralLedgerReportRepositoryFactory = Callable[[Session], GeneralLedgerReportRepository]

_ZERO = Decimal("0.00")


class GeneralLedgerReportService:
    """Builds general ledger outputs from posted journal entry lines."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        ledger_repository_factory: GeneralLedgerReportRepositoryFactory,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._ledger_repository_factory = ledger_repository_factory
        self._permission_service = permission_service

    def get_account_ledger(
        self,
        filter_dto: ReportingFilterDTO,
        account_id: int,
    ) -> GeneralLedgerReportDTO:
        self._permission_service.require_permission("reports.general_ledger.view")
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to view the general ledger.")
        if not isinstance(account_id, int) or account_id <= 0:
            raise ValidationError("Select an account to view its ledger.")
        if not filter_dto.posted_only:
            raise ValidationError("General Ledger is limited to posted journals.")
        self._validate_dates(filter_dto.date_from, filter_dto.date_to)

        with self._unit_of_work_factory() as uow:
            repo = self._ledger_repository_factory(uow.session)
            account = repo.get_account(company_id, account_id)
            if account is None:
                raise NotFoundError("The selected account could not be found for this company.")

            opening_debit, opening_credit = repo.sum_opening_amounts(
                company_id=company_id,
                account_id=account_id,
                date_from=filter_dto.date_from,
            )
            lines = repo.list_ledger_lines(
                company_id=company_id,
                account_id=account_id,
                date_from=filter_dto.date_from,
                date_to=filter_dto.date_to,
            )

        dto_account = self._build_account_dto(
            account_id=account.id,
            account_code=account.account_code,
            account_name=account.account_name,
            opening_debit=opening_debit,
            opening_credit=opening_credit,
            lines=lines,
        )

        return GeneralLedgerReportDTO(
            company_id=company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            accounts=(dto_account,),
        )

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_account_dto(
        self,
        account_id: int,
        account_code: str,
        account_name: str,
        opening_debit: Decimal,
        opening_credit: Decimal,
        lines: list[LedgerLineRow],
    ) -> GeneralLedgerAccountDTO:
        running_net = opening_debit - opening_credit
        dto_lines: list[GeneralLedgerLineDTO] = []

        total_debit = _ZERO
        total_credit = _ZERO

        for row in lines:
            running_net += row.debit_amount - row.credit_amount
            total_debit += row.debit_amount
            total_credit += row.credit_amount

            dto_lines.append(
                GeneralLedgerLineDTO(
                    line_id=row.line_id,
                    journal_entry_id=row.journal_entry_id,
                    line_number=row.line_number,
                    entry_date=row.entry_date,
                    entry_number=row.entry_number,
                    reference_text=row.reference_text,
                    journal_description=row.journal_description,
                    line_description=row.line_description,
                    debit_amount=row.debit_amount,
                    credit_amount=row.credit_amount,
                    running_balance=running_net,
                    source_module_code=row.source_module_code,
                    source_document_type=row.source_document_type,
                    source_document_id=row.source_document_id,
                    posted_at=row.posted_at,
                )
            )

        closing_net = running_net
        opening_debit_s, opening_credit_s = self._split_balance(opening_debit - opening_credit)
        closing_debit_s, closing_credit_s = self._split_balance(closing_net)

        return GeneralLedgerAccountDTO(
            account_id=account_id,
            account_code=account_code,
            account_name=account_name,
            opening_debit=opening_debit_s,
            opening_credit=opening_credit_s,
            opening_balance=opening_debit - opening_credit,
            period_debit=total_debit,
            period_credit=total_credit,
            closing_debit=closing_debit_s,
            closing_credit=closing_credit_s,
            closing_balance=closing_net,
            total_debit=total_debit,
            total_credit=total_credit,
            lines=tuple(dto_lines),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_dates(date_from: date | None, date_to: date | None) -> None:
        if date_from and date_to and date_to < date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")

    @staticmethod
    def _split_balance(net_amount: Decimal) -> tuple[Decimal, Decimal]:
        if net_amount >= _ZERO:
            return net_amount, _ZERO
        return _ZERO, abs(net_amount)
