"""Pro-rata service (Slice T34).

Manages provisional and final VAT pro-rata percentages for mixed-regime
(partial exemption) companies.  The percentage is stored in
``company_pro_rata_history`` by fiscal year.

Usage pattern:
- At year-start or period-setup: call ``set_provisional`` to record the
  expected percentage used for L31 deductions during the year.
- At year-end: call ``finalise`` to record the true pro-rata computed from
  actual taxable / total turnover, and raise an adjustment JE if there is
  a material difference versus the provisional.

The ``company_tax_profile.vat_pro_rata_percent`` always reflects the
current in-force provisional percentage used for live return drafting.
This service keeps the historical record and manages year-end settlement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.models.company_pro_rata_history import (
    CompanyProRataHistory,
)
from seeker_accounting.modules.taxation.repositories.company_pro_rata_history_repository import (
    CompanyProRataHistoryRepository,
)
from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (
    CompanyTaxProfileRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CompanyTaxProfileRepositoryFactory = Callable[[Session], CompanyTaxProfileRepository]
CompanyProRataHistoryRepositoryFactory = Callable[
    [Session], CompanyProRataHistoryRepository
]

_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ProRataHistoryDTO:
    id: int
    company_id: int
    fiscal_year: int
    provisional_pct: Decimal | None
    final_pct: Decimal | None
    adjustment_journal_entry_id: int | None
    notes: str | None


class ProRataService:
    PERMISSION_VIEW = "taxation.returns.view"
    PERMISSION_MANAGE = "taxation.returns.manage"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        company_tax_profile_repository_factory: CompanyTaxProfileRepositoryFactory,
        pro_rata_history_repository_factory: CompanyProRataHistoryRepositoryFactory,
        permission_service: PermissionService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._company_tax_profile_repository_factory = company_tax_profile_repository_factory
        self._pro_rata_history_repository_factory = pro_rata_history_repository_factory
        self._permission_service = permission_service

    # ── Read ────────────────────────────────────────────────────────

    def list_history(self, company_id: int) -> list[ProRataHistoryDTO]:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._pro_rata_history_repository_factory(uow.session)
            records = repo.list_by_company(company_id)
            return [self._to_dto(r) for r in records]

    def get_for_year(
        self, company_id: int, fiscal_year: int
    ) -> ProRataHistoryDTO | None:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._pro_rata_history_repository_factory(uow.session)
            record = repo.get_by_company_year(company_id, fiscal_year)
            return self._to_dto(record) if record else None

    # ── Write ───────────────────────────────────────────────────────

    def set_provisional(
        self,
        company_id: int,
        fiscal_year: int,
        provisional_pct: Decimal,
        notes: str | None = None,
    ) -> ProRataHistoryDTO:
        """Set or update the provisional pro-rata % for a fiscal year.

        Also updates ``company_tax_profile.vat_pro_rata_percent`` to this
        value so that live return drafting picks it up immediately.
        """
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        pct = Decimal(str(provisional_pct)).quantize(Decimal("0.0001"))
        if not (_ZERO <= pct <= Decimal("100.0000")):
            raise ValidationError(
                "Pro-rata percentage must be between 0.00 and 100.00."
            )

        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            history_repo = self._pro_rata_history_repository_factory(uow.session)
            record = history_repo.get_by_company_year(company_id, fiscal_year)
            if record is None:
                record = CompanyProRataHistory(
                    company_id=company_id,
                    fiscal_year=fiscal_year,
                    provisional_pct=pct,
                    notes=notes,
                )
                history_repo.add(record)
            else:
                record.provisional_pct = pct
                if notes is not None:
                    record.notes = notes
                history_repo.save(record)

            # Keep live profile in sync.
            profile_repo = self._company_tax_profile_repository_factory(uow.session)
            profile = profile_repo.get_by_company(company_id)
            if profile is not None:
                profile.vat_pro_rata_percent = pct  # type: ignore[assignment]

            uow.commit()
            return self._to_dto(record)

    def finalise(
        self,
        company_id: int,
        fiscal_year: int,
        final_pct: Decimal,
        notes: str | None = None,
    ) -> ProRataHistoryDTO:
        """Record the year-end final pro-rata %.

        The adjustment JE is intentionally deferred — at this stage we
        record the final percentage and note the discrepancy.  A future
        slice (year-end close workflow) will raise the actual adjusting
        entry.  The ``adjustment_journal_entry_id`` remains NULL until then.
        """
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        pct = Decimal(str(final_pct)).quantize(Decimal("0.0001"))
        if not (_ZERO <= pct <= Decimal("100.0000")):
            raise ValidationError(
                "Final pro-rata percentage must be between 0.00 and 100.00."
            )

        with self._uow_factory() as uow:
            self._require_company(uow.session, company_id)
            history_repo = self._pro_rata_history_repository_factory(uow.session)
            record = history_repo.get_by_company_year(company_id, fiscal_year)
            if record is None:
                record = CompanyProRataHistory(
                    company_id=company_id,
                    fiscal_year=fiscal_year,
                    final_pct=pct,
                    notes=notes,
                )
                history_repo.add(record)
            else:
                record.final_pct = pct
                if notes is not None:
                    record.notes = notes
                history_repo.save(record)

            uow.commit()
            return self._to_dto(record)

    # ── Helpers ─────────────────────────────────────────────────────

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    @staticmethod
    def _to_dto(record: CompanyProRataHistory) -> ProRataHistoryDTO:
        return ProRataHistoryDTO(
            id=record.id,
            company_id=record.company_id,
            fiscal_year=record.fiscal_year,
            provisional_pct=record.provisional_pct,
            final_pct=record.final_pct,
            adjustment_journal_entry_id=record.adjustment_journal_entry_id,
            notes=record.notes,
        )
