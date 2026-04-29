"""Tax compliance dashboard service (T22).

Provides a single read-only ``get_dashboard`` call that aggregates
obligations, returns, payments, and withholding totals for a
company / fiscal year. UI surfaces (dashboard widgets) consume the
resulting :class:`TaxDashboardSnapshotDTO` directly without composing
their own queries.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    OBLIGATION_STATUS_CANCELLED,
    OBLIGATION_STATUS_OPEN,
    OBLIGATION_STATUS_OVERDUE,
    OBLIGATION_STATUS_PAID,
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_FILED,
    TAX_TYPE_VAT,
    WHT_DIRECTION_INBOUND,
    WHT_DIRECTION_OUTBOUND,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    TaxDashboardObligationSummaryDTO,
    TaxDashboardSnapshotDTO,
    TaxDashboardUpcomingObligationDTO,
)
from seeker_accounting.modules.taxation.repositories.tax_obligation_repository import (
    TaxObligationRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_payment_repository import (
    TaxPaymentRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.modules.taxation.repositories.withholding_tax_certificate_repository import (
    WithholdingTaxCertificateRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError


_ZERO = Decimal("0.00")


TaxObligationRepositoryFactory = Callable[[Session], TaxObligationRepository]
TaxReturnRepositoryFactory = Callable[[Session], TaxReturnRepository]
TaxPaymentRepositoryFactory = Callable[[Session], TaxPaymentRepository]
WithholdingTaxCertificateRepositoryFactory = Callable[
    [Session], WithholdingTaxCertificateRepository
]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class TaxDashboardService:
    """Read-only aggregator for the tax compliance dashboard."""

    PERMISSION_VIEW = "taxation.dashboard.view"

    UPCOMING_LIMIT = 10

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        tax_obligation_repository_factory: TaxObligationRepositoryFactory,
        tax_return_repository_factory: TaxReturnRepositoryFactory,
        tax_payment_repository_factory: TaxPaymentRepositoryFactory,
        withholding_tax_certificate_repository_factory: WithholdingTaxCertificateRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_obligation_repository_factory = tax_obligation_repository_factory
        self._tax_return_repository_factory = tax_return_repository_factory
        self._tax_payment_repository_factory = tax_payment_repository_factory
        self._wht_repository_factory = (
            withholding_tax_certificate_repository_factory
        )
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service

    # ---------------- Public ----------------

    def get_dashboard(
        self,
        company_id: int,
        fiscal_year: int,
        *,
        as_of_date: date | None = None,
    ) -> TaxDashboardSnapshotDTO:
        """Return the consolidated tax dashboard snapshot for a year."""
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        if fiscal_year < 2000 or fiscal_year > 2100:
            raise ValidationError(
                f"Fiscal year {fiscal_year} is outside the supported range."
            )
        ref_date = as_of_date or date.today()
        period_start = date(fiscal_year, 1, 1)
        period_end = date(fiscal_year, 12, 31)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            obligation_repo = self._tax_obligation_repository_factory(uow.session)
            return_repo = self._tax_return_repository_factory(uow.session)
            payment_repo = self._tax_payment_repository_factory(uow.session)
            wht_repo = self._wht_repository_factory(uow.session)

            obligations = [
                o
                for o in obligation_repo.list_by_company(company_id)
                if period_start <= o.period_start <= period_end
                or period_start <= o.period_end <= period_end
            ]
            returns = [
                r
                for r in return_repo.list_by_company(company_id)
                if period_start <= r.period_end <= period_end
            ]
            payments = [
                p
                for p in payment_repo.list_by_company(company_id)
                if period_start <= p.payment_date <= period_end
            ]
            wht_inbound = wht_repo.list_by_company(
                company_id,
                direction=WHT_DIRECTION_INBOUND,
                date_from=period_start,
                date_to=period_end,
            )
            wht_outbound = wht_repo.list_by_company(
                company_id,
                direction=WHT_DIRECTION_OUTBOUND,
                date_from=period_start,
                date_to=period_end,
            )

        # Obligation counters
        open_count = 0
        overdue_count = 0
        paid_count = 0
        cancelled_count = 0
        by_type: dict[str, dict[str, int]] = {}
        for ob in obligations:
            bucket = by_type.setdefault(
                ob.tax_type_code, {"open": 0, "overdue": 0, "paid": 0}
            )
            status = ob.status_code
            if status == OBLIGATION_STATUS_PAID:
                paid_count += 1
                bucket["paid"] += 1
            elif status == OBLIGATION_STATUS_CANCELLED:
                cancelled_count += 1
            elif status == OBLIGATION_STATUS_OVERDUE or (
                status == OBLIGATION_STATUS_OPEN and ob.due_date < ref_date
            ):
                overdue_count += 1
                bucket["overdue"] += 1
            else:
                open_count += 1
                bucket["open"] += 1

        # Returns counters
        returns_draft = sum(
            1 for r in returns if r.status_code == RETURN_STATUS_DRAFT
        )
        returns_filed = sum(
            1 for r in returns if r.status_code == RETURN_STATUS_FILED
        )
        returns_settled = sum(
            1
            for r in returns
            if r.status_code == RETURN_STATUS_FILED
            and r.journal_entry_id is not None
        )
        returns_filed_unsettled_vat = sum(
            1
            for r in returns
            if r.tax_type_code == TAX_TYPE_VAT
            and r.status_code == RETURN_STATUS_FILED
            and r.journal_entry_id is None
        )

        # Money totals
        total_payments_ytd = sum((p.amount for p in payments), _ZERO)
        total_due_filed_returns_ytd = sum(
            (
                r.total_due_amount
                for r in returns
                if r.status_code == RETURN_STATUS_FILED
            ),
            _ZERO,
        )
        wht_inbound_total_ytd = sum((c.tax_amount for c in wht_inbound), _ZERO)
        wht_outbound_total_ytd = sum((c.tax_amount for c in wht_outbound), _ZERO)

        # Per-tax-type summary
        by_tax_type = tuple(
            TaxDashboardObligationSummaryDTO(
                tax_type_code=code,
                open_count=counts["open"],
                overdue_count=counts["overdue"],
                paid_count=counts["paid"],
            )
            for code, counts in sorted(by_type.items())
        )

        # Upcoming list — open/overdue obligations sorted by due date
        upcoming_pool = [
            ob
            for ob in obligations
            if ob.status_code
            not in (OBLIGATION_STATUS_PAID, OBLIGATION_STATUS_CANCELLED)
        ]
        upcoming_pool.sort(key=lambda o: (o.due_date, o.id))
        upcoming = tuple(
            TaxDashboardUpcomingObligationDTO(
                obligation_id=ob.id,
                tax_type_code=ob.tax_type_code,
                period_start=ob.period_start,
                period_end=ob.period_end,
                due_date=ob.due_date,
                days_until_due=(ob.due_date - ref_date).days,
                status_code=ob.status_code,
            )
            for ob in upcoming_pool[: self.UPCOMING_LIMIT]
        )

        return TaxDashboardSnapshotDTO(
            company_id=company_id,
            fiscal_year=fiscal_year,
            as_of_date=ref_date,
            total_obligations=len(obligations),
            open_obligations=open_count,
            overdue_obligations=overdue_count,
            paid_obligations=paid_count,
            cancelled_obligations=cancelled_count,
            returns_draft=returns_draft,
            returns_filed=returns_filed,
            returns_settled=returns_settled,
            returns_filed_unsettled_vat=returns_filed_unsettled_vat,
            total_payments_ytd=total_payments_ytd,
            total_due_filed_returns_ytd=total_due_filed_returns_ytd,
            wht_inbound_total_ytd=wht_inbound_total_ytd,
            wht_outbound_total_ytd=wht_outbound_total_ytd,
            by_tax_type=by_tax_type,
            upcoming=upcoming,
        )

    # ---------------- Helpers ----------------

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")
