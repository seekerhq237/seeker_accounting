from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.fixed_assets.dto.depreciation_dto import DepreciationPostingResultDTO
from seeker_accounting.modules.fixed_assets.models.asset import Asset
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run import AssetDepreciationRun
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_run_repository import (
    AssetDepreciationRunRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_run_line_repository import (
    AssetDepreciationRunLineRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

_ZERO = Decimal("0")

AssetRepositoryFactory = Callable[[Session], AssetRepository]
AssetDepreciationRunRepositoryFactory = Callable[[Session], AssetDepreciationRunRepository]
AssetDepreciationRunLineRepositoryFactory = Callable[[Session], AssetDepreciationRunLineRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class DepreciationPostingService:
    DOCUMENT_TYPE_CODE = "DEPRECIATION_RUN"
    SOURCE_MODULE_CODE = "FIXED_ASSETS"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        asset_repository_factory: AssetRepositoryFactory,
        asset_depreciation_run_repository_factory: AssetDepreciationRunRepositoryFactory,
        asset_depreciation_run_line_repository_factory: AssetDepreciationRunLineRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._asset_repository_factory = asset_repository_factory
        self._asset_depreciation_run_repository_factory = asset_depreciation_run_repository_factory
        self._asset_depreciation_run_line_repository_factory = asset_depreciation_run_line_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._audit_service = audit_service

    def post_run(
        self,
        company_id: int,
        run_id: int,
        actor_user_id: int | None = None,
    ) -> DepreciationPostingResultDTO:
        """Post a draft depreciation run.

        Posting effect per asset:
          DR depreciation_expense_account_id   (from asset category)
          CR accumulated_depreciation_account_id (from asset category)

        Lines are aggregated per category account pair to keep the journal
        clean. A single journal entry is created for the entire run.

        After posting:
          - Run status_code -> posted
          - posted_journal_entry_id, posted_at, posted_by_user_id are set
          - Assets that reach fully_depreciated state are updated
          - Run becomes immutable
        """
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company(uow.session, company_id)

            run_repo = self._asset_depreciation_run_repository_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError(f"Depreciation run {run_id} not found.")
            if run.status_code != "draft":
                raise ValidationError("Only draft depreciation runs can be posted.")
            if not run.lines:
                raise ValidationError("Cannot post an empty depreciation run.")

            # Validate posting period
            fp_repo = self._fiscal_period_repository_factory(uow.session)
            period = fp_repo.get_covering_date(company_id, run.period_end_date)
            if period is None:
                raise ValidationError("Period end date must fall within an existing fiscal period.")
            if period.status_code == "LOCKED":
                raise PeriodLockedError("Cannot post into a locked fiscal period.")
            if period.status_code != "OPEN":
                raise ValidationError("Can only post into an open fiscal period.")

            # Issue run number
            run_number = self._numbering_service.issue_next_number(
                uow.session, company_id=company_id, document_type_code=self.DOCUMENT_TYPE_CODE
            )
            run.run_number = run_number

            # Build journal entry: aggregate by (expense_account_id, accum_depr_account_id)
            # Load line details including category accounts
            asset_repo = self._asset_repository_factory(uow.session)
            line_repo = self._asset_depreciation_run_line_repository_factory(uow.session)
            lines = line_repo.list_by_run(run.id)

            # Collect totals per account pair
            expense_totals: dict[int, Decimal] = {}
            accum_totals: dict[int, Decimal] = {}

            for line in lines:
                asset = asset_repo.get_by_id(company_id, line.asset_id)
                if asset is None or asset.category is None:
                    raise ValidationError(
                        f"Asset {line.asset_id} or its category could not be loaded for posting."
                    )
                exp_acct = asset.category.depreciation_expense_account_id
                acc_acct = asset.category.accumulated_depreciation_account_id
                expense_totals[exp_acct] = expense_totals.get(exp_acct, _ZERO) + line.depreciation_amount
                accum_totals[acc_acct] = accum_totals.get(acc_acct, _ZERO) + line.depreciation_amount

            total_depreciation = sum(expense_totals.values())
            if total_depreciation <= _ZERO:
                raise ValidationError("Depreciation run has no amounts to post.")

            # Verify debits == credits (they will be by construction)
            total_expense = sum(expense_totals.values())
            total_accum = sum(accum_totals.values())
            if total_expense != total_accum:
                raise ValidationError(
                    "Depreciation run has unbalanced totals — this indicates a data integrity issue."
                )

            # Create journal entry
            je_repo = self._journal_entry_repository_factory(uow.session)
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=period.id,
                entry_date=run.period_end_date,
                journal_type_code="DEPRECIATION",
                description=f"Depreciation run {run_number} — period end {run.period_end_date}",
                source_module_code=self.SOURCE_MODULE_CODE,
                source_document_type="DEPRECIATION_RUN",
                source_document_id=run.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_id,
            )
            # Issue journal entry number
            journal_entry.entry_number = self._numbering_service.issue_next_number(
                uow.session, company_id=company_id, document_type_code="JOURNAL_ENTRY"
            )
            uow.session.add(journal_entry)
            uow.session.flush()

            # DR expense accounts
            line_num = 1
            for acct_id, amount in expense_totals.items():
                line_obj = JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    line_number=line_num,
                    account_id=acct_id,
                    debit_amount=amount,
                    credit_amount=_ZERO,
                    line_description="Depreciation expense",
                )
                uow.session.add(line_obj)
                line_num += 1

            # CR accumulated depreciation accounts
            for acct_id, amount in accum_totals.items():
                line_obj = JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    line_number=line_num,
                    account_id=acct_id,
                    debit_amount=_ZERO,
                    credit_amount=amount,
                    line_description="Accumulated depreciation",
                )
                uow.session.add(line_obj)
                line_num += 1

            uow.session.flush()

            now = datetime.utcnow()
            run.status_code = "posted"
            run.posted_journal_entry_id = journal_entry.id
            run.posted_at = now
            run.posted_by_user_id = actor_id
            run_repo.save(run)

            # Update assets that are now fully depreciated
            for line in lines:
                asset = asset_repo.get_by_id(company_id, line.asset_id)
                if asset is not None:
                    salvage = asset.salvage_value if asset.salvage_value is not None else _ZERO
                    # If NBV after this run == salvage, mark fully_depreciated
                    if line.net_book_value_after <= salvage + Decimal("0.000001"):
                        asset.status_code = "fully_depreciated"
                        asset_repo.save(asset)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Depreciation run posting failed due to a data conflict.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import DEPRECIATION_RUN_POSTED
            self._record_audit(company_id, DEPRECIATION_RUN_POSTED, "AssetDepreciationRun", run.id, "Posted depreciation run")
            return DepreciationPostingResultDTO(
                run_id=run.id,
                run_number=run_number,
                company_id=company_id,
                period_end_date=run.period_end_date,
                posted_journal_entry_id=journal_entry.id,
                asset_count=len(lines),
                total_depreciation=total_depreciation,
                posted_at=now,
                posted_by_user_id=actor_id,
            )

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_FIXED_ASSETS
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_FIXED_ASSETS,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
