from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.payroll.dto.payroll_variance_dto import (
    CalcStepDTO,
    PayrollVarianceAnalysisDTO,
    PayrollVarianceLineDTO,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_AUDIT_VIEW
from seeker_accounting.modules.payroll.repositories.company_payroll_setting_repository import (
    CompanyPayrollSettingRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_calculation_trace_repository import (
    PayrollCalculationTraceRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunEmployeeRepository,
    PayrollRunRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError

RunRepositoryFactory = Callable[[Session], PayrollRunRepository]
RunEmployeeRepositoryFactory = Callable[[Session], PayrollRunEmployeeRepository]
TraceRepositoryFactory = Callable[[Session], PayrollCalculationTraceRepository]
SettingRepositoryFactory = Callable[[Session], CompanyPayrollSettingRepository]


class PayrollVarianceAnalysisService:
    """Compare one calculated run against the closest prior comparable run."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        run_repository_factory: RunRepositoryFactory,
        run_employee_repository_factory: RunEmployeeRepositoryFactory,
        trace_repository_factory: TraceRepositoryFactory,
        setting_repository_factory: SettingRepositoryFactory,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._run_repo_factory = run_repository_factory
        self._run_employee_repo_factory = run_employee_repository_factory
        self._trace_repo_factory = trace_repository_factory
        self._setting_repo_factory = setting_repository_factory
        self._permission_service = permission_service

    def analyze_run(self, company_id: int, run_id: int) -> PayrollVarianceAnalysisDTO:
        if self._permission_service is not None:
            self._permission_service.require_permission(PAYROLL_AUDIT_VIEW)
        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            current = run_repo.get_by_id(company_id, run_id)
            if current is None:
                raise NotFoundError("Payroll run not found.")
            prior = self._find_prior_run(run_repo, company_id, current)
            setting = self._setting_repo_factory(uow.session).get_by_company(company_id)
            threshold = Decimal(str(getattr(setting, "variance_threshold_percent", 10) or 10))
            current_rows = self._run_employee_repo_factory(uow.session).list_with_lines_by_run(
                company_id, current.id
            )
            prior_rows = (
                self._run_employee_repo_factory(uow.session).list_with_lines_by_run(company_id, prior.id)
                if prior is not None else []
            )
            lines = self._build_variance_lines(current_rows, prior_rows, threshold)
            return PayrollVarianceAnalysisDTO(
                run_id=current.id,
                run_reference=current.run_reference,
                prior_run_id=prior.id if prior else None,
                prior_run_reference=prior.run_reference if prior else None,
                threshold_percent=threshold,
                lines=tuple(lines),
            )

    def list_calc_steps(self, company_id: int, run_employee_id: int) -> tuple[CalcStepDTO, ...]:
        if self._permission_service is not None:
            self._permission_service.require_permission(PAYROLL_AUDIT_VIEW)
        with self._uow_factory() as uow:
            rows = self._trace_repo_factory(uow.session).list_by_run_employee(
                company_id, run_employee_id
            )
            return tuple(
                CalcStepDTO(
                    id=row.id,
                    sequence_number=row.sequence_number,
                    stage_code=row.stage_code,
                    component_id=row.component_id,
                    component_code=row.component.component_code if row.component else None,
                    component_name=row.component.component_name if row.component else None,
                    formula_code=row.formula_code,
                    input_json=row.input_json,
                    output_json=row.output_json,
                    amount=Decimal(str(row.amount)),
                    created_at=getattr(row, "created_at", None),
                )
                for row in rows
            )

    @staticmethod
    def _find_prior_run(run_repo: PayrollRunRepository, company_id: int, current: object) -> object | None:
        runs = run_repo.list_by_company(company_id)
        current_key = (current.period_year, current.period_month, current.run_sequence, current.id)
        candidates = []
        for run in runs:
            if run.id == current.id:
                continue
            if run.currency_code != current.currency_code:
                continue
            if getattr(run, "run_type_code", "regular") != getattr(current, "run_type_code", "regular"):
                continue
            if run.status_code not in ("calculated", "submitted_for_review", "approved", "posted", "reversed"):
                continue
            key = (run.period_year, run.period_month, getattr(run, "run_sequence", 1), run.id)
            if key < current_key:
                candidates.append(run)
        candidates.sort(key=lambda r: (r.period_year, r.period_month, getattr(r, "run_sequence", 1), r.id), reverse=True)
        return candidates[0] if candidates else None

    def _build_variance_lines(
        self,
        current_rows: list[object],
        prior_rows: list[object],
        threshold: Decimal,
    ) -> list[PayrollVarianceLineDTO]:
        current_totals = self._totals(current_rows)
        prior_totals = self._totals(prior_rows)
        lines = [
            self._line("summary", "gross", "Gross earnings", prior_totals["gross"], current_totals["gross"], threshold),
            self._line("summary", "net", "Net payable", prior_totals["net"], current_totals["net"], threshold),
            self._line("summary", "employees", "Included employees", prior_totals["employees"], current_totals["employees"], threshold),
        ]

        current_components = self._component_totals(current_rows)
        prior_components = self._component_totals(prior_rows)
        for component_key in sorted(set(current_components) | set(prior_components)):
            prior_amount, label = prior_components.get(component_key, (Decimal("0"), component_key))
            current_amount, label = current_components.get(component_key, (Decimal("0"), label))
            lines.append(
                self._line("component", component_key, label, prior_amount, current_amount, threshold)
            )
        return lines

    @staticmethod
    def _totals(rows: list[object]) -> dict[str, Decimal]:
        included = [row for row in rows if getattr(row, "status_code", None) == "included"]
        return {
            "gross": sum((Decimal(str(row.gross_earnings)) for row in included), Decimal("0")),
            "net": sum((Decimal(str(row.net_payable)) for row in included), Decimal("0")),
            "employees": Decimal(len(included)),
        }

    @staticmethod
    def _component_totals(rows: list[object]) -> dict[str, tuple[Decimal, str]]:
        totals: dict[str, tuple[Decimal, str]] = {}
        for row in rows:
            if getattr(row, "status_code", None) != "included":
                continue
            for line in getattr(row, "lines", []) or []:
                component = getattr(line, "component", None)
                code = component.component_code if component else f"component_{line.component_id}"
                label = component.component_name if component else code
                amount = Decimal(str(line.component_amount))
                previous, _ = totals.get(code, (Decimal("0"), label))
                totals[code] = (previous + amount, label)
        return totals

    @staticmethod
    def _line(
        category: str,
        code: str,
        label: str,
        prior: Decimal,
        current: Decimal,
        threshold: Decimal,
    ) -> PayrollVarianceLineDTO:
        delta = current - prior
        pct = None if prior == Decimal("0") else (delta / prior * Decimal("100"))
        severity = "info"
        if prior == Decimal("0") and current != Decimal("0"):
            severity = "warning"
        elif pct is not None and abs(pct) >= threshold:
            severity = "warning"
        explanation = "No prior amount to compare." if prior == 0 else f"Change is {delta:,.2f}."
        if pct is not None:
            explanation = f"Change is {delta:,.2f} ({pct:+.2f}%)."
        return PayrollVarianceLineDTO(
            category_code=category,
            subject_code=code,
            subject_label=label,
            prior_amount=prior,
            current_amount=current,
            delta_amount=delta,
            delta_percent=pct,
            severity_code=severity,
            explanation=explanation,
        )
