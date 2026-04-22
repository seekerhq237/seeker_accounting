"""Payroll Print Service — assembles data for printable payslips and summary reports.

This service collects the data. Rendering (HTML generation, QPrinter) lives in the UI layer.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_PRINT
from seeker_accounting.modules.payroll.dto.payroll_print_dto import (
    PayrollSummaryPrintDataDTO,
    PayslipPrintDataDTO,
)
from seeker_accounting.modules.payroll.services.payroll_payslip_preview_service import (
    PayrollPayslipPreviewService,
)
from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService
from seeker_accounting.platform.exceptions import NotFoundError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]

_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


class PayrollPrintService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repo_factory: CompanyRepositoryFactory,
        payslip_preview_service: PayrollPayslipPreviewService,
        run_service: PayrollRunService,
        permission_service: PermissionService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._company_repo_factory = company_repo_factory
        self._payslip_service = payslip_preview_service
        self._run_service = run_service
        self._permission_service = permission_service

    def get_payslip_data(
        self, company_id: int, run_employee_id: int
    ) -> PayslipPrintDataDTO:
        """Assemble printable payslip data for one employee."""
        self._permission_service.require_permission(PAYROLL_PRINT)
        company_name = self._get_company_name(company_id)
        company_detail = self._get_company_detail(company_id)
        preview = self._payslip_service.get_payslip_preview(company_id, run_employee_id)

        detail = self._run_service.get_run_employee_detail(company_id, run_employee_id)
        run = self._run_service.get_run(company_id, detail.run_id)
        currency_code = run.currency_code or self._get_company_currency_code(company_id)

        # Build company address string
        addr_parts = [
            p for p in [company_detail.address_line_1, company_detail.address_line_2]
            if p
        ]
        company_address = ", ".join(addr_parts) if addr_parts else None

        return PayslipPrintDataDTO(
            company_name=company_name,
            company_tax_identifier=company_detail.tax_identifier,
            company_address=company_address,
            company_city=company_detail.city,
            company_phone=company_detail.phone,
            company_logo_storage_path=getattr(company_detail, 'logo_storage_path', None),
            employee_number=preview.employee_number,
            employee_display_name=preview.employee_display_name,
            employee_position=preview.employee_position_name,
            employee_department=preview.employee_department_name,
            employee_hire_date=preview.employee_hire_date,
            employee_nif=preview.employee_nif,
            employee_cnps_number=preview.employee_cnps_number,
            company_cnps_employer_number=preview.company_cnps_employer_number,
            payment_account_name=preview.payment_account_name,
            payment_account_type=preview.payment_account_type,
            payment_account_reference=preview.payment_account_reference,
            period_label=preview.period_label,
            period_year=preview.period_year,
            period_month=preview.period_month,
            payment_date=preview.payment_date,
            run_reference=preview.run_reference,
            currency_code=currency_code,
            earnings=tuple(
                (l.component_name, l.component_amount)
                for l in preview.earnings_section.lines
            ),
            deductions=tuple(
                (l.component_name, l.component_amount)
                for l in preview.deductions_section.lines
            ),
            taxes=tuple(
                (l.component_name, l.component_amount)
                for l in preview.taxes_section.lines
            ),
            employer_contributions=tuple(
                (l.component_name, l.component_amount)
                for l in preview.employer_contributions_section.lines
            ),
            gross_earnings=preview.gross_earnings,
            total_deductions=preview.deductions_section.subtotal,
            total_taxes=preview.taxes_section.subtotal,
            net_payable=preview.net_payable,
            employer_cost=preview.employer_cost_base,
            total_employer_contributions=preview.employer_contributions_section.subtotal,
            taxable_salary_base=preview.taxable_salary_base,
            cnps_contributory_base=preview.cnps_contributory_base,
            tdl_base=preview.tdl_base,
        )

    def get_payslip_batch_data(
        self,
        company_id: int,
        run_id: int,
        run_employee_ids: tuple[int, ...] | None = None,
    ) -> list[PayslipPrintDataDTO]:
        """Assemble payslip data for multiple employees in a run."""
        self._permission_service.require_permission(PAYROLL_PRINT)
        employees = self._run_service.list_run_employees(company_id, run_id)
        if run_employee_ids:
            employees = [e for e in employees if e.id in run_employee_ids]

        return [
            self.get_payslip_data(company_id, emp.id)
            for emp in employees
        ]

    def get_summary_data(
        self, company_id: int, run_id: int
    ) -> PayrollSummaryPrintDataDTO:
        """Assemble printable payroll run summary data."""
        self._permission_service.require_permission(PAYROLL_PRINT)
        company_name = self._get_company_name(company_id)
        run = self._run_service.get_run(company_id, run_id)
        employees = self._run_service.list_run_employees(company_id, run_id)

        period_label = f"{_MONTHS.get(run.period_month, str(run.period_month))} {run.period_year}"

        total_gross = Decimal("0")
        total_ded = Decimal("0")
        total_tax = Decimal("0")
        total_net = Decimal("0")
        total_employer = Decimal("0")

        emp_lines: list[tuple[str, str, Decimal, Decimal, Decimal]] = []
        for emp in employees:
            ded_tax = emp.total_employee_deductions + emp.total_taxes
            total_gross += emp.gross_earnings
            total_ded += emp.total_employee_deductions
            total_tax += emp.total_taxes
            total_net += emp.net_payable
            total_employer += emp.employer_cost_base - emp.gross_earnings
            emp_lines.append((
                emp.employee_number,
                emp.employee_display_name,
                emp.gross_earnings,
                ded_tax,
                emp.net_payable,
            ))

        return PayrollSummaryPrintDataDTO(
            company_name=company_name,
            run_reference=run.run_reference,
            run_label=run.run_label,
            period_label=period_label,
            currency_code=run.currency_code,
            employee_count=len(employees),
            total_gross_earnings=total_gross,
            total_deductions=total_ded,
            total_taxes=total_tax,
            total_net_payable=total_net,
            total_employer_contributions=total_employer,
            total_employer_cost=total_gross + total_employer,
            employee_lines=tuple(emp_lines),
        )

    def _get_company_name(self, company_id: int) -> str:
        with self._uow_factory() as uow:
            repo = self._company_repo_factory(uow.session)
            company = repo.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company {company_id} not found.")
            return company.display_name

    def _get_company_detail(self, company_id: int):
        with self._uow_factory() as uow:
            repo = self._company_repo_factory(uow.session)
            company = repo.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company {company_id} not found.")
            return company

    def _get_company_currency_code(self, company_id: int) -> str:
        with self._uow_factory() as uow:
            repo = self._company_repo_factory(uow.session)
            company = repo.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company {company_id} not found.")
            return company.base_currency_code
