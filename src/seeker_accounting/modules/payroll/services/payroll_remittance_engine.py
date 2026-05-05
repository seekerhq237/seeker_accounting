"""PayrollRemittanceEngine — auto-derive remittance lines from posted runs.

Phase 5 / P5.S3.

Given a (company, authority, period) tuple, the engine:

1. Finds all approved/posted payroll runs whose period falls within
   the requested window.
2. Sums ``payroll_run_lines.component_amount`` per component, filtered
   by the active component → authority mappings.
3. Applies the per-mapping ``fraction`` (defaults to 1.0) to allow
   partial remittance (e.g. employee-only share of CNPS-PVID).
4. Returns a structured estimate that the remittance batch flow uses
   to seed lines instead of asking the user to type amounts.

This engine is read-only. It does NOT create batches or lines —
those remain the responsibility of :class:`PayrollRemittanceService`.
The engine never crosses module boundaries; it consumes the payroll
data model only.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.payroll.dto.payroll_authority_dto import (
    RemittanceEstimate,
    RemittanceLineEstimate,
    StatutoryReturnBoxDTO,
    StatutoryReturnPrefillDTO,
)
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine
from seeker_accounting.modules.payroll.payroll_permissions import (
    PAYROLL_REMITTANCE_MANAGE,
)
from seeker_accounting.modules.payroll.repositories.payroll_authority_repository import (
    PayrollAuthorityRepository,
    PayrollComponentAuthorityMapRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

# Statuses where component_amount is considered "real" enough to remit.
# Posted is the gold standard; approved is supported for preview workflows
# where finance wants to plan filings before posting.
_QUALIFYING_RUN_STATUSES = frozenset({"approved", "posted"})


class PayrollRemittanceEngine:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authority_repository_factory: Callable[[Session], PayrollAuthorityRepository],
        map_repository_factory: Callable[
            [Session], PayrollComponentAuthorityMapRepository
        ],
        permission_service: PermissionService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._authority_repo_factory = authority_repository_factory
        self._map_repo_factory = map_repository_factory
        self._permission_service = permission_service

    def estimate_for_period(
        self,
        company_id: int,
        *,
        authority_id: int,
        period_year: int,
        period_month: int,
    ) -> RemittanceEstimate:
        """Estimate remittance lines for ``(authority, year, month)``.

        Aggregates approved/posted runs whose ``(period_year, period_month)``
        match the requested period.
        """
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)

        if not (1 <= period_month <= 12):
            raise ValidationError("Period month must be between 1 and 12.")

        period_start = date(period_year, period_month, 1)
        period_end = date(
            period_year,
            period_month,
            calendar.monthrange(period_year, period_month)[1],
        )

        with self._uow_factory() as uow:
            authority = self._authority_repo_factory(uow.session).get_by_id(
                company_id, authority_id,
            )
            if authority is None:
                raise NotFoundError("Authority not found.")

            mappings = self._map_repo_factory(uow.session).list_for_authority(
                company_id, authority_id,
            )
            if not mappings:
                return RemittanceEstimate(
                    authority_id=authority.id,
                    authority_code=authority.code,
                    authority_name=authority.name,
                    period_start_date=period_start,
                    period_end_date=period_end,
                    currency_code="",
                    payroll_run_ids=(),
                    lines=(),
                    total_amount=Decimal("0"),
                    warnings=(
                        "No component → authority mappings exist for this authority. "
                        "Configure mappings in Payroll Setup before auto-seeding.",
                    ),
                )

            # Find qualifying runs for this period.
            run_stmt = (
                select(PayrollRun)
                .where(PayrollRun.company_id == company_id)
                .where(PayrollRun.period_year == period_year)
                .where(PayrollRun.period_month == period_month)
                .where(PayrollRun.status_code.in_(_QUALIFYING_RUN_STATUSES))
                .order_by(PayrollRun.id)
            )
            runs = list(uow.session.scalars(run_stmt).all())
            if not runs:
                return RemittanceEstimate(
                    authority_id=authority.id,
                    authority_code=authority.code,
                    authority_name=authority.name,
                    period_start_date=period_start,
                    period_end_date=period_end,
                    currency_code="",
                    payroll_run_ids=(),
                    lines=(),
                    total_amount=Decimal("0"),
                    warnings=(
                        "No approved or posted payroll runs found for this period.",
                    ),
                )

            currencies = {r.currency_code for r in runs}
            warnings: list[str] = []
            if len(currencies) > 1:
                warnings.append(
                    "Payroll runs in this period span multiple currencies "
                    f"({', '.join(sorted(currencies))}); amounts are summed "
                    "as-is and may need manual reconciliation."
                )
            currency_code = next(iter(currencies))
            run_ids = tuple(r.id for r in runs)

            # Sum component_amount per component_id from qualifying runs.
            run_line_stmt = (
                select(PayrollRunLine)
                .where(PayrollRunLine.company_id == company_id)
                .where(PayrollRunLine.run_id.in_(run_ids))
                .options(selectinload(PayrollRunLine.component))
            )
            run_lines = list(uow.session.scalars(run_line_stmt).all())

            totals_by_component: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
            run_line_ids_by_component: dict[int, list[int]] = defaultdict(list)
            components_seen: dict[int, PayrollComponent] = {}
            for line in run_lines:
                cid = int(line.component_id)
                amount = Decimal(line.component_amount or 0)
                totals_by_component[cid] += amount
                run_line_ids_by_component[cid].append(int(line.id))
                if line.component is not None:
                    components_seen[cid] = line.component

            # Apply mappings.
            estimate_lines: list[RemittanceLineEstimate] = []
            grand_total = Decimal("0")
            for mapping in mappings:
                cid = int(mapping.component_id)
                gross = totals_by_component.get(cid, Decimal("0"))
                if gross == 0:
                    warnings.append(
                        f"No run lines found for component "
                        f"'{mapping.component.component_code if mapping.component else cid}' "
                        "in this period — skipped."
                    )
                    continue
                fraction = Decimal(mapping.fraction or 0)
                amount = (gross * fraction).quantize(Decimal("0.0001"))
                comp = components_seen.get(cid) or mapping.component
                estimate_lines.append(
                    RemittanceLineEstimate(
                        component_id=cid,
                        component_code=comp.component_code if comp is not None else "",
                        component_name=comp.component_name if comp is not None else "",
                        side=mapping.side,
                        line_kind=mapping.line_kind,
                        amount=amount,
                        liability_account_id=(
                            comp.liability_account_id if comp is not None else None
                        ),
                        source_run_line_ids=tuple(run_line_ids_by_component.get(cid, ())),
                    )
                )
                grand_total += amount

            return RemittanceEstimate(
                authority_id=authority.id,
                authority_code=authority.code,
                authority_name=authority.name,
                period_start_date=period_start,
                period_end_date=period_end,
                currency_code=currency_code,
                payroll_run_ids=run_ids,
                lines=tuple(estimate_lines),
                total_amount=grand_total,
                warnings=tuple(warnings),
            )

    def estimate_for_runs(
        self,
        company_id: int,
        *,
        authority_id: int,
        payroll_run_ids: Iterable[int],
    ) -> RemittanceEstimate:
        """Estimate against an explicit set of approved/posted runs.

        Useful when finance picks specific runs (off-cycle, supplemental,
        cross-period adjustments) rather than a calendar month.
        """
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        run_ids = tuple(sorted({int(rid) for rid in payroll_run_ids}))
        if not run_ids:
            raise ValidationError("At least one payroll run id is required.")

        with self._uow_factory() as uow:
            authority = self._authority_repo_factory(uow.session).get_by_id(
                company_id, authority_id,
            )
            if authority is None:
                raise NotFoundError("Authority not found.")

            run_stmt = (
                select(PayrollRun)
                .where(PayrollRun.company_id == company_id)
                .where(PayrollRun.id.in_(run_ids))
            )
            runs = list(uow.session.scalars(run_stmt).all())
            if len(runs) != len(run_ids):
                raise NotFoundError("One or more payroll runs were not found.")

            warnings: list[str] = []
            disqualified = [
                r.run_reference for r in runs
                if r.status_code not in _QUALIFYING_RUN_STATUSES
            ]
            if disqualified:
                warnings.append(
                    f"Runs not in approved/posted state: {', '.join(disqualified)}."
                )
                runs = [r for r in runs if r.status_code in _QUALIFYING_RUN_STATUSES]
            if not runs:
                raise ValidationError(
                    "No qualifying (approved or posted) runs in the supplied set."
                )

            qualifying_ids = tuple(r.id for r in runs)
            currencies = {r.currency_code for r in runs}
            if len(currencies) > 1:
                warnings.append(
                    "Selected runs span multiple currencies "
                    f"({', '.join(sorted(currencies))})."
                )
            currency_code = next(iter(currencies))

            min_year = min(r.period_year for r in runs)
            min_month = min(r.period_month for r in runs if r.period_year == min_year)
            max_year = max(r.period_year for r in runs)
            max_month = max(r.period_month for r in runs if r.period_year == max_year)
            period_start = date(min_year, min_month, 1)
            period_end = date(
                max_year,
                max_month,
                calendar.monthrange(max_year, max_month)[1],
            )

            mappings = self._map_repo_factory(uow.session).list_for_authority(
                company_id, authority_id,
            )

            run_line_stmt = (
                select(PayrollRunLine)
                .where(PayrollRunLine.company_id == company_id)
                .where(PayrollRunLine.run_id.in_(qualifying_ids))
                .options(selectinload(PayrollRunLine.component))
            )
            run_lines = list(uow.session.scalars(run_line_stmt).all())

            totals_by_component: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
            run_line_ids_by_component: dict[int, list[int]] = defaultdict(list)
            components_seen: dict[int, PayrollComponent] = {}
            for line in run_lines:
                cid = int(line.component_id)
                totals_by_component[cid] += Decimal(line.component_amount or 0)
                run_line_ids_by_component[cid].append(int(line.id))
                if line.component is not None:
                    components_seen[cid] = line.component

            estimate_lines: list[RemittanceLineEstimate] = []
            grand_total = Decimal("0")
            for mapping in mappings:
                cid = int(mapping.component_id)
                gross = totals_by_component.get(cid, Decimal("0"))
                if gross == 0:
                    continue
                fraction = Decimal(mapping.fraction or 0)
                amount = (gross * fraction).quantize(Decimal("0.0001"))
                comp = components_seen.get(cid) or mapping.component
                estimate_lines.append(
                    RemittanceLineEstimate(
                        component_id=cid,
                        component_code=comp.component_code if comp is not None else "",
                        component_name=comp.component_name if comp is not None else "",
                        side=mapping.side,
                        line_kind=mapping.line_kind,
                        amount=amount,
                        liability_account_id=(
                            comp.liability_account_id if comp is not None else None
                        ),
                        source_run_line_ids=tuple(run_line_ids_by_component.get(cid, ())),
                    )
                )
                grand_total += amount

            return RemittanceEstimate(
                authority_id=authority.id,
                authority_code=authority.code,
                authority_name=authority.name,
                period_start_date=period_start,
                period_end_date=period_end,
                currency_code=currency_code,
                payroll_run_ids=qualifying_ids,
                lines=tuple(estimate_lines),
                total_amount=grand_total,
                warnings=tuple(warnings),
            )

    # ── Statutory return pre-fill (P5.S5) ─────────────────────────────

    def get_statutory_return_prefill(
        self,
        company_id: int,
        *,
        authority_id: int,
        period_year: int,
        period_month: int,
    ) -> StatutoryReturnPrefillDTO:
        """Build a pre-fill payload for the authority's statutory return.

        Wraps :meth:`estimate_for_period`: each remittance line becomes a
        return "box" carrying its source ``PayrollRunLine`` ids so an
        auditor can drill from any box back to the originating journal
        lines (via ``payroll_run.journal_entry_id`` once posted).

        The current pre-fill maps one box per (component, side, line_kind)
        triple. When a return form requires combined boxes (e.g. CNPS
        quarterly form), a future caller can post-process this DTO into
        the form-specific shape; the source-line trace is preserved.
        """
        estimate = self.estimate_for_period(
            company_id,
            authority_id=authority_id,
            period_year=period_year,
            period_month=period_month,
        )
        boxes = tuple(
            StatutoryReturnBoxDTO(
                box_code=f"{line.component_code}_{line.side}",
                box_label=(
                    f"{line.component_name} ({line.side}, {line.line_kind})"
                ),
                side=line.side,
                line_kind=line.line_kind,
                component_id=line.component_id,
                component_code=line.component_code,
                component_name=line.component_name,
                amount=line.amount,
                source_run_line_ids=line.source_run_line_ids,
            )
            for line in estimate.lines
        )
        return StatutoryReturnPrefillDTO(
            authority_id=estimate.authority_id,
            authority_code=estimate.authority_code,
            authority_name=estimate.authority_name,
            period_start_date=estimate.period_start_date,
            period_end_date=estimate.period_end_date,
            currency_code=estimate.currency_code,
            payroll_run_ids=estimate.payroll_run_ids,
            boxes=boxes,
            total_amount=estimate.total_amount,
            warnings=estimate.warnings,
        )
