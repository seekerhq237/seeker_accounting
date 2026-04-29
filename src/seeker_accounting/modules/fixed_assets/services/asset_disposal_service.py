"""AssetDisposalService — books the disposal of a fixed asset.

Posts a single balanced journal entry that:
  DR proceeds_account            (cash/receivable)        amount = disposal_amount
  DR accumulated_depreciation    (from asset.category)    amount = accumulated_to_date
  CR asset_cost                  (from asset.category)    amount = acquisition_cost
  DR/CR gain_or_loss_account     amount = plug

Where the plug = NBV - proceeds. If proceeds > NBV → gain (CR gain_or_loss).
If proceeds < NBV → loss (DR gain_or_loss).

After posting:
  - Asset.status_code -> "disposed"
  - Asset.disposal_date / disposal_amount / disposal_reference / disposal_journal_entry_id set
  - Asset becomes immutable for normal edit flows.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy import select
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
from seeker_accounting.modules.fixed_assets.dto.asset_disposal_dto import (
    AssetDisposalResultDTO,
    DisposeAssetCommand,
)
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run import (
    AssetDepreciationRun,
)
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import (
    AssetDepreciationRunLine,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

_ZERO = Decimal("0")
_ONE_MICRO = Decimal("0.000001")

AssetRepositoryFactory = Callable[[Session], AssetRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class AssetDisposalService:
    SOURCE_MODULE_CODE = "FIXED_ASSETS"
    SOURCE_DOCUMENT_TYPE = "ASSET_DISPOSAL"
    JOURNAL_TYPE_CODE = "ASSET_DISPOSAL"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        asset_repository_factory: AssetRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._asset_repository_factory = asset_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._audit_service = audit_service

    def dispose_asset(
        self,
        company_id: int,
        asset_id: int,
        command: DisposeAssetCommand,
        actor_user_id: int | None = None,
    ) -> AssetDisposalResultDTO:
        if command.disposal_amount is None:
            raise ValidationError("Disposal amount is required (use 0 for scrap).")
        proceeds = Decimal(command.disposal_amount)
        if proceeds < _ZERO:
            raise ValidationError("Disposal amount cannot be negative.")
        if command.proceeds_account_id == command.gain_or_loss_account_id:
            raise ValidationError(
                "Proceeds account and gain/loss account must be different."
            )

        with self._unit_of_work_factory() as uow:
            actor_id = (
                actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            )
            self._require_company(uow.session, company_id)

            asset_repo = self._asset_repository_factory(uow.session)
            asset = asset_repo.get_by_id(company_id, asset_id)
            if asset is None:
                raise NotFoundError(f"Asset {asset_id} not found.")
            if asset.status_code == "disposed":
                raise ConflictError("Asset is already disposed.")
            if asset.status_code == "draft":
                raise ValidationError(
                    "Asset is still in draft. Activate the asset before disposing it."
                )
            if asset.category is None:
                raise ValidationError("Asset has no category — cannot determine accounts.")

            # Validate fiscal period for disposal_date
            fp_repo = self._fiscal_period_repository_factory(uow.session)
            period = fp_repo.get_covering_date(company_id, command.disposal_date)
            if period is None:
                raise ValidationError(
                    "Disposal date must fall within an existing fiscal period."
                )
            if period.status_code == "LOCKED":
                raise PeriodLockedError("Cannot post into a locked fiscal period.")
            if period.status_code != "OPEN":
                raise ValidationError("Can only post into an open fiscal period.")

            # Compute accumulated depreciation up to disposal_date from posted runs.
            accumulated = self._compute_accumulated_depreciation(
                uow.session, asset_id, command.disposal_date
            )
            cost = Decimal(asset.acquisition_cost)
            nbv = cost - accumulated
            if nbv < -_ONE_MICRO:
                # Should not happen, but guard against data corruption.
                raise ValidationError(
                    "Asset accumulated depreciation exceeds acquisition cost — data integrity issue."
                )
            if nbv < _ZERO:
                nbv = _ZERO

            asset_cost_account_id = asset.category.asset_account_id
            accum_dep_account_id = asset.category.accumulated_depreciation_account_id
            if asset_cost_account_id is None or accum_dep_account_id is None:
                raise ValidationError(
                    "Asset category is missing the asset cost or accumulated depreciation account."
                )

            # Build journal entry
            je_repo = self._journal_entry_repository_factory(uow.session)
            entry_number = self._numbering_service.issue_next_number(
                uow.session, company_id=company_id, document_type_code="JOURNAL_ENTRY"
            )
            description = (
                f"Disposal of asset {asset.asset_number} ({asset.asset_name})"
            )
            now = datetime.utcnow()
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=period.id,
                entry_date=command.disposal_date,
                journal_type_code=self.JOURNAL_TYPE_CODE,
                description=description,
                source_module_code=self.SOURCE_MODULE_CODE,
                source_document_type=self.SOURCE_DOCUMENT_TYPE,
                source_document_id=asset.id,
                status_code="POSTED",
                posted_at=now,
                posted_by_user_id=actor_id,
                entry_number=entry_number,
                reference_text=command.reference,
            )
            uow.session.add(journal_entry)
            uow.session.flush()

            # Lines:
            #   DR proceeds (if > 0)
            #   DR accumulated_depreciation (if > 0)
            #   CR asset cost
            #   gain/loss plug
            line_no = 1
            lines_to_add: list[JournalEntryLine] = []
            if proceeds > _ZERO:
                lines_to_add.append(
                    JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        line_number=line_no,
                        account_id=command.proceeds_account_id,
                        debit_amount=proceeds,
                        credit_amount=_ZERO,
                        line_description="Disposal proceeds",
                    )
                )
                line_no += 1
            if accumulated > _ZERO:
                lines_to_add.append(
                    JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        line_number=line_no,
                        account_id=accum_dep_account_id,
                        debit_amount=accumulated,
                        credit_amount=_ZERO,
                        line_description="Clear accumulated depreciation",
                    )
                )
                line_no += 1
            lines_to_add.append(
                JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    line_number=line_no,
                    account_id=asset_cost_account_id,
                    debit_amount=_ZERO,
                    credit_amount=cost,
                    line_description="Remove asset cost",
                )
            )
            line_no += 1

            # gain_or_loss = proceeds - NBV
            #   > 0 → gain → CR gain/loss account
            #   < 0 → loss → DR gain/loss account
            gain_or_loss = proceeds - nbv
            if gain_or_loss.copy_abs() > _ONE_MICRO:
                if gain_or_loss > _ZERO:
                    lines_to_add.append(
                        JournalEntryLine(
                            journal_entry_id=journal_entry.id,
                            line_number=line_no,
                            account_id=command.gain_or_loss_account_id,
                            debit_amount=_ZERO,
                            credit_amount=gain_or_loss,
                            line_description="Gain on disposal",
                        )
                    )
                else:
                    lines_to_add.append(
                        JournalEntryLine(
                            journal_entry_id=journal_entry.id,
                            line_number=line_no,
                            account_id=command.gain_or_loss_account_id,
                            debit_amount=-gain_or_loss,
                            credit_amount=_ZERO,
                            line_description="Loss on disposal",
                        )
                    )
                line_no += 1

            for line_obj in lines_to_add:
                uow.session.add(line_obj)
            uow.session.flush()

            # Verify balance
            total_dr = sum(line_obj.debit_amount for line_obj in lines_to_add)
            total_cr = sum(line_obj.credit_amount for line_obj in lines_to_add)
            if (total_dr - total_cr).copy_abs() > _ONE_MICRO:
                raise ValidationError(
                    f"Disposal journal is unbalanced: DR={total_dr} CR={total_cr}."
                )

            # Update asset
            asset.status_code = "disposed"
            asset.disposal_date = command.disposal_date
            asset.disposal_amount = proceeds
            asset.disposal_reference = command.reference
            asset.disposal_journal_entry_id = journal_entry.id
            if command.notes:
                existing_notes = asset.notes or ""
                separator = "\n\n" if existing_notes else ""
                asset.notes = f"{existing_notes}{separator}[Disposal] {command.notes}"
            asset_repo.save(asset)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Asset disposal failed due to a data conflict.") from exc

            self._record_audit(
                company_id,
                asset.id,
                f"Asset {asset.asset_number} disposed for {proceeds} (NBV {nbv}, "
                f"gain/loss {gain_or_loss}).",
            )

            return AssetDisposalResultDTO(
                asset_id=asset.id,
                asset_number=asset.asset_number,
                journal_entry_id=journal_entry.id,
                journal_entry_number=entry_number,
                acquisition_cost=cost,
                accumulated_depreciation=accumulated,
                net_book_value=nbv,
                proceeds=proceeds,
                gain_or_loss_amount=gain_or_loss,
                disposal_date=command.disposal_date,
                posted_at=now,
            )

    def _compute_accumulated_depreciation(
        self, session: Session, asset_id: int, as_of_date
    ) -> Decimal:
        # Find the latest posted depreciation run line for this asset whose run
        # period_end_date is on/before the disposal date.
        stmt = (
            select(AssetDepreciationRunLine.accumulated_depreciation_after)
            .join(
                AssetDepreciationRun,
                AssetDepreciationRunLine.asset_depreciation_run_id == AssetDepreciationRun.id,
            )
            .where(AssetDepreciationRunLine.asset_id == asset_id)
            .where(AssetDepreciationRun.status_code == "posted")
            .where(AssetDepreciationRun.period_end_date <= as_of_date)
            .order_by(AssetDepreciationRun.period_end_date.desc())
            .limit(1)
        )
        result = session.execute(stmt).scalar_one_or_none()
        return Decimal(result) if result is not None else _ZERO

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _record_audit(
        self,
        company_id: int,
        asset_id: int,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import (
            ASSET_DISPOSED,
            MODULE_FIXED_ASSETS,
        )

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=ASSET_DISPOSED,
                    module_code=MODULE_FIXED_ASSETS,
                    entity_type="Asset",
                    entity_id=asset_id,
                    description=description,
                ),
            )
        except Exception:  # noqa: BLE001 — audit must never break business flow
            pass
