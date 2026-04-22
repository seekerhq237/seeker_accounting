from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.reporting.dto.ap_aging_report_dto import APAgingReportDTO
from seeker_accounting.modules.reporting.dto.ar_aging_report_dto import ARAgingReportDTO
from seeker_accounting.modules.reporting.dto.ias_balance_sheet_dto import IasBalanceSheetReportDTO
from seeker_accounting.modules.reporting.dto.ias_income_statement_dto import IasIncomeStatementReportDTO
from seeker_accounting.modules.reporting.dto.ohada_income_statement_dto import OhadaIncomeStatementReportDTO
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import OperationalReportFilterDTO
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.dto.stock_valuation_report_dto import (
    StockValuationReportDTO,
    StockValuationReportFilterDTO,
)
from seeker_accounting.modules.reporting.repositories.financial_analysis_chart_repository import (
    FinancialAnalysisChartRepository,
    ProfitLossMonthlyActivityRow,
)
from seeker_accounting.modules.reporting.repositories.financial_analysis_repository import (
    FinancialAnalysisRepository,
    OperationalPeriodTotalRow,
)
from seeker_accounting.modules.reporting.services.ap_aging_report_service import APAgingReportService
from seeker_accounting.modules.reporting.services.ar_aging_report_service import ARAgingReportService
from seeker_accounting.modules.reporting.services.ias_balance_sheet_service import IasBalanceSheetService
from seeker_accounting.modules.reporting.services.ias_income_statement_service import (
    IasIncomeStatementService,
)
from seeker_accounting.modules.reporting.services.ohada_income_statement_service import (
    OhadaIncomeStatementService,
)
from seeker_accounting.modules.reporting.services.stock_valuation_report_service import (
    StockValuationReportService,
)
from seeker_accounting.modules.reporting.specs.financial_analysis_spec import to_amount
from seeker_accounting.modules.reporting.specs.ias_income_statement_spec import compute_natural_amount
from seeker_accounting.platform.exceptions import ValidationError

FinancialAnalysisRepositoryFactory = Callable[[Session], FinancialAnalysisRepository]
FinancialAnalysisChartRepositoryFactory = Callable[[Session], FinancialAnalysisChartRepository]

_ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class BalanceAnalysisBasis:
    as_of_date: date | None
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    current_assets: Decimal
    current_liabilities: Decimal
    cash_equivalents: Decimal
    inventories: Decimal
    receivables: Decimal
    current_tax_assets: Decimal
    other_current_assets: Decimal
    payables: Decimal
    current_borrowings: Decimal
    non_current_borrowings: Decimal
    non_current_liabilities: Decimal


@dataclass(frozen=True, slots=True)
class IncomeAnalysisBasis:
    basis_code: str
    revenue: Decimal | None
    gross_profit: Decimal | None
    cost_of_sales: Decimal | None
    operating_profit: Decimal | None
    operating_expenses: Decimal | None
    net_profit: Decimal | None
    finance_income: Decimal | None
    finance_costs: Decimal | None
    limitation_messages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MonthlyProfitabilitySnapshot:
    label: str
    start_date: date
    end_date: date
    revenue: Decimal
    expenses: Decimal
    profit: Decimal


@dataclass(frozen=True, slots=True)
class MonthlyBalanceSnapshot:
    label: str
    as_of_date: date
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    current_assets: Decimal
    current_liabilities: Decimal
    inventories: Decimal
    receivables: Decimal
    payables: Decimal
    cash_equivalents: Decimal


@dataclass(frozen=True, slots=True)
class FinancialAnalysisSnapshot:
    company_id: int
    date_from: date | None
    date_to: date | None
    current_filter: ReportingFilterDTO
    prior_filter: ReportingFilterDTO | None
    current_balance_sheet_report: IasBalanceSheetReportDTO
    prior_balance_sheet_report: IasBalanceSheetReportDTO | None
    current_ias_income_report: IasIncomeStatementReportDTO
    prior_ias_income_report: IasIncomeStatementReportDTO | None
    current_ohada_income_report: OhadaIncomeStatementReportDTO
    prior_ohada_income_report: OhadaIncomeStatementReportDTO | None
    current_ar_aging_report: ARAgingReportDTO
    prior_ar_aging_report: ARAgingReportDTO | None
    current_ap_aging_report: APAgingReportDTO
    prior_ap_aging_report: APAgingReportDTO | None
    current_stock_valuation_report: StockValuationReportDTO
    current_balance_basis: BalanceAnalysisBasis
    prior_balance_basis: BalanceAnalysisBasis | None
    current_income_basis: IncomeAnalysisBasis
    prior_income_basis: IncomeAnalysisBasis | None
    sales_total: Decimal
    prior_sales_total: Decimal | None
    purchase_total: Decimal
    prior_purchase_total: Decimal | None
    monthly_profitability: tuple[MonthlyProfitabilitySnapshot, ...]
    monthly_balances: tuple[MonthlyBalanceSnapshot, ...]
    monthly_sales_totals: tuple[OperationalPeriodTotalRow, ...]
    monthly_purchase_totals: tuple[OperationalPeriodTotalRow, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]


class FinancialAnalysisService:
    """Assembles the shared financial truth snapshot consumed by Slice 14H services."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        financial_analysis_repository_factory: FinancialAnalysisRepositoryFactory,
        financial_analysis_chart_repository_factory: FinancialAnalysisChartRepositoryFactory,
        ias_balance_sheet_service: IasBalanceSheetService,
        ias_income_statement_service: IasIncomeStatementService,
        ohada_income_statement_service: OhadaIncomeStatementService,
        ar_aging_report_service: ARAgingReportService,
        ap_aging_report_service: APAgingReportService,
        stock_valuation_report_service: StockValuationReportService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._financial_analysis_repository_factory = financial_analysis_repository_factory
        self._financial_analysis_chart_repository_factory = financial_analysis_chart_repository_factory
        self._ias_balance_sheet_service = ias_balance_sheet_service
        self._ias_income_statement_service = ias_income_statement_service
        self._ohada_income_statement_service = ohada_income_statement_service
        self._ar_aging_report_service = ar_aging_report_service
        self._ap_aging_report_service = ap_aging_report_service
        self._stock_valuation_report_service = stock_valuation_report_service

    def get_snapshot(self, filter_dto: ReportingFilterDTO) -> FinancialAnalysisSnapshot:
        self._validate_filter(filter_dto)
        current_filter = ReportingFilterDTO(
            company_id=filter_dto.company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            posted_only=True,
        )
        prior_period = self._prior_period(filter_dto.date_from, filter_dto.date_to)
        prior_filter = (
            ReportingFilterDTO(
                company_id=filter_dto.company_id,
                date_from=prior_period[0],
                date_to=prior_period[1],
                posted_only=True,
            )
            if prior_period is not None
            else None
        )

        current_balance = self._ias_balance_sheet_service.get_statement(current_filter)
        prior_balance = self._ias_balance_sheet_service.get_statement(prior_filter) if prior_filter else None
        current_ias_income = self._ias_income_statement_service.get_statement(current_filter)
        prior_ias_income = self._ias_income_statement_service.get_statement(prior_filter) if prior_filter else None
        current_ohada_income = self._ohada_income_statement_service.get_statement(current_filter)
        prior_ohada_income = self._ohada_income_statement_service.get_statement(prior_filter) if prior_filter else None

        current_operational_filter = OperationalReportFilterDTO(
            company_id=filter_dto.company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            as_of_date=filter_dto.date_to or filter_dto.date_from,
            posted_only=True,
        )
        prior_operational_filter = (
            OperationalReportFilterDTO(
                company_id=filter_dto.company_id,
                date_from=prior_filter.date_from,
                date_to=prior_filter.date_to,
                as_of_date=prior_filter.date_to,
                posted_only=True,
            )
            if prior_filter is not None
            else None
        )

        current_ar = self._ar_aging_report_service.get_report(current_operational_filter)
        prior_ar = self._ar_aging_report_service.get_report(prior_operational_filter) if prior_operational_filter else None
        current_ap = self._ap_aging_report_service.get_report(current_operational_filter)
        prior_ap = self._ap_aging_report_service.get_report(prior_operational_filter) if prior_operational_filter else None
        current_stock = self._stock_valuation_report_service.get_report(
            StockValuationReportFilterDTO(
                company_id=filter_dto.company_id or 0,
                as_of_date=filter_dto.date_to or filter_dto.date_from,
            )
        )

        with self._unit_of_work_factory() as uow:
            repo = self._financial_analysis_repository_factory(uow.session)
            chart_repo = self._financial_analysis_chart_repository_factory(uow.session)
            sales_total = repo.sum_posted_sales_invoices(filter_dto.company_id or 0, filter_dto.date_from, filter_dto.date_to)
            prior_sales_total = (
                repo.sum_posted_sales_invoices(filter_dto.company_id or 0, prior_filter.date_from, prior_filter.date_to)
                if prior_filter is not None
                else None
            )
            purchase_total = repo.sum_posted_purchase_bills(filter_dto.company_id or 0, filter_dto.date_from, filter_dto.date_to)
            prior_purchase_total = (
                repo.sum_posted_purchase_bills(filter_dto.company_id or 0, prior_filter.date_from, prior_filter.date_to)
                if prior_filter is not None
                else None
            )
            monthly_sales_totals = tuple(
                repo.list_monthly_sales_invoice_totals(filter_dto.company_id or 0, filter_dto.date_from, filter_dto.date_to)
            )
            monthly_purchase_totals = tuple(
                repo.list_monthly_purchase_bill_totals(filter_dto.company_id or 0, filter_dto.date_from, filter_dto.date_to)
            )
            monthly_profit_rows = chart_repo.list_monthly_profit_loss_activity(
                filter_dto.company_id or 0,
                filter_dto.date_from,
                filter_dto.date_to,
            )

        current_balance_basis = self._build_balance_basis(current_balance)
        prior_balance_basis = self._build_balance_basis(prior_balance) if prior_balance else None
        current_income_basis = self._build_income_basis(current_ias_income, current_ohada_income)
        prior_income_basis = (
            self._build_income_basis(prior_ias_income, prior_ohada_income)
            if prior_ias_income is not None and prior_ohada_income is not None
            else None
        )
        monthly_profitability = tuple(self._build_monthly_profitability(filter_dto.date_from, filter_dto.date_to, monthly_profit_rows))
        monthly_balances = tuple(self._build_monthly_balances(filter_dto.company_id or 0, filter_dto.date_from, filter_dto.date_to))

        warnings: list[str] = []
        limitations: list[str] = []
        warnings.extend(warning.message for warning in current_balance.warnings)
        warnings.extend(issue.message for issue in current_ias_income.issues)
        warnings.extend(warning.message for warning in current_ohada_income.warnings)
        warnings.extend(warning.message for warning in current_ar.warnings)
        warnings.extend(warning.message for warning in current_ap.warnings)
        warnings.extend(warning.message for warning in current_stock.warnings)
        limitations.extend(current_income_basis.limitation_messages)
        if prior_filter is None:
            limitations.append("Prior-period comparison is unavailable without both a start and end date.")
        if len(monthly_balances) <= 1:
            limitations.append("Monthly trend depth is limited because the selected period spans a single month.")

        return FinancialAnalysisSnapshot(
            company_id=filter_dto.company_id or 0,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            current_filter=current_filter,
            prior_filter=prior_filter,
            current_balance_sheet_report=current_balance,
            prior_balance_sheet_report=prior_balance,
            current_ias_income_report=current_ias_income,
            prior_ias_income_report=prior_ias_income,
            current_ohada_income_report=current_ohada_income,
            prior_ohada_income_report=prior_ohada_income,
            current_ar_aging_report=current_ar,
            prior_ar_aging_report=prior_ar,
            current_ap_aging_report=current_ap,
            prior_ap_aging_report=prior_ap,
            current_stock_valuation_report=current_stock,
            current_balance_basis=current_balance_basis,
            prior_balance_basis=prior_balance_basis,
            current_income_basis=current_income_basis,
            prior_income_basis=prior_income_basis,
            sales_total=sales_total,
            prior_sales_total=prior_sales_total,
            purchase_total=purchase_total,
            prior_purchase_total=prior_purchase_total,
            monthly_profitability=monthly_profitability,
            monthly_balances=monthly_balances,
            monthly_sales_totals=monthly_sales_totals,
            monthly_purchase_totals=monthly_purchase_totals,
            warnings=tuple(dict.fromkeys(warnings)),
            limitations=tuple(dict.fromkeys(limitations)),
        )

    def _build_balance_basis(self, report: IasBalanceSheetReportDTO | None) -> BalanceAnalysisBasis | None:
        if report is None:
            return None
        line_map = {line.code: to_amount(line.amount) for line in report.lines}
        return BalanceAnalysisBasis(
            as_of_date=report.statement_date,
            total_assets=line_map.get("TOTAL_ASSETS", _ZERO),
            total_liabilities=(
                line_map.get("TOTAL_NON_CURRENT_LIABILITIES", _ZERO)
                + line_map.get("TOTAL_CURRENT_LIABILITIES", _ZERO)
            ).quantize(Decimal("0.01")),
            total_equity=line_map.get("TOTAL_EQUITY", _ZERO),
            current_assets=line_map.get("TOTAL_CURRENT_ASSETS", _ZERO),
            current_liabilities=line_map.get("TOTAL_CURRENT_LIABILITIES", _ZERO),
            cash_equivalents=line_map.get("CASH_EQUIVALENTS", _ZERO),
            inventories=line_map.get("INVENTORIES", _ZERO),
            receivables=line_map.get("TRADE_OTHER_RECEIVABLES", _ZERO),
            current_tax_assets=line_map.get("CURRENT_TAX_ASSETS", _ZERO),
            other_current_assets=line_map.get("OTHER_CURRENT_ASSETS", _ZERO),
            payables=line_map.get("CL_TRADE_OTHER_PAYABLES", _ZERO),
            current_borrowings=line_map.get("CL_BORROWINGS", _ZERO),
            non_current_borrowings=line_map.get("NCL_BORROWINGS", _ZERO),
            non_current_liabilities=line_map.get("TOTAL_NON_CURRENT_LIABILITIES", _ZERO),
        )

    def _build_income_basis(
        self,
        ias_report: IasIncomeStatementReportDTO,
        ohada_report: OhadaIncomeStatementReportDTO,
    ) -> IncomeAnalysisBasis:
        ias_map = {line.code: to_amount(line.signed_amount) for line in ias_report.lines}
        ohada_map = {line.code: to_amount(line.signed_amount) for line in ohada_report.lines}
        limitations: list[str] = []
        has_ias_mapping_basis = ias_report.has_mappings and not any(
            issue.issue_code == "no_mappings" for issue in ias_report.issues
        )
        if has_ias_mapping_basis:
            return IncomeAnalysisBasis(
                basis_code="ias",
                revenue=ias_map.get("REV"),
                gross_profit=ias_map.get("GROSS_PROFIT"),
                cost_of_sales=ias_map.get("COS"),
                operating_profit=ias_map.get("OPERATING_PROFIT"),
                operating_expenses=ias_map.get("OPERATING_EXPENSES"),
                net_profit=ias_map.get("PROFIT_FOR_PERIOD"),
                finance_income=ias_map.get("FIN_INCOME"),
                finance_costs=ias_map.get("FIN_COSTS"),
                limitation_messages=(),
            )
        limitations.append(
            "IAS income-statement mappings are incomplete, so gross margin and cost-of-sales-based metrics remain unavailable."
        )
        limitations.append(
            "Profitability uses OHADA turnover and result lines where IAS section mapping was not safely available."
        )
        return IncomeAnalysisBasis(
            basis_code="ohada_fallback",
            revenue=ohada_map.get("XB"),
            gross_profit=None,
            cost_of_sales=None,
            operating_profit=ohada_map.get("XE"),
            operating_expenses=None,
            net_profit=ohada_map.get("XI"),
            finance_income=ohada_map.get("TK"),
            finance_costs=ohada_map.get("RM"),
            limitation_messages=tuple(limitations),
        )

    def _build_monthly_profitability(
        self,
        date_from: date | None,
        date_to: date | None,
        rows: list[ProfitLossMonthlyActivityRow],
    ) -> list[MonthlyProfitabilitySnapshot]:
        revenue_map: dict[tuple[int, int], Decimal] = {}
        expense_map: dict[tuple[int, int], Decimal] = {}
        for row in rows:
            classification = self._profit_loss_classification(row.account_class_code, row.account_type_section_code)
            if classification is None:
                continue
            natural_amount = compute_natural_amount(
                total_debit=row.total_debit,
                total_credit=row.total_credit,
                normal_balance=row.normal_balance,
            )
            key = (row.period_year, row.period_month)
            if classification == "revenue":
                revenue_map[key] = (revenue_map.get(key, _ZERO) + natural_amount).quantize(Decimal("0.01"))
            else:
                expense_map[key] = (expense_map.get(key, _ZERO) + natural_amount).quantize(Decimal("0.01"))
        snapshots: list[MonthlyProfitabilitySnapshot] = []
        for bucket in self._month_buckets(date_from, date_to):
            key = (bucket[0].year, bucket[0].month)
            revenue = revenue_map.get(key, _ZERO)
            expenses = expense_map.get(key, _ZERO)
            snapshots.append(
                MonthlyProfitabilitySnapshot(
                    label=bucket[2],
                    start_date=bucket[0],
                    end_date=bucket[1],
                    revenue=revenue,
                    expenses=expenses,
                    profit=(revenue - expenses).quantize(Decimal("0.01")),
                )
            )
        return snapshots

    def _build_monthly_balances(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[MonthlyBalanceSnapshot]:
        snapshots: list[MonthlyBalanceSnapshot] = []
        for _, bucket_end, label in self._month_buckets(date_from, date_to):
            report = self._ias_balance_sheet_service.get_statement(
                ReportingFilterDTO(company_id=company_id, date_from=None, date_to=bucket_end, posted_only=True)
            )
            basis = self._build_balance_basis(report)
            if basis is None:
                continue
            snapshots.append(
                MonthlyBalanceSnapshot(
                    label=label,
                    as_of_date=bucket_end,
                    total_assets=basis.total_assets,
                    total_liabilities=basis.total_liabilities,
                    total_equity=basis.total_equity,
                    current_assets=basis.current_assets,
                    current_liabilities=basis.current_liabilities,
                    inventories=basis.inventories,
                    receivables=basis.receivables,
                    payables=basis.payables,
                    cash_equivalents=basis.cash_equivalents,
                )
            )
        return snapshots

    @staticmethod
    def _profit_loss_classification(
        account_class_code: str | None,
        account_type_section_code: str | None,
    ) -> str | None:
        normalized_section = (account_type_section_code or "").strip().upper()
        if normalized_section in {"REVENUE", "OTHER_REVENUE"} or account_class_code == "7":
            return "revenue"
        if normalized_section in {"EXPENSE", "OTHER_EXPENSE"} or account_class_code in {"6", "8"}:
            return "expense"
        return None

    @staticmethod
    def _month_buckets(date_from: date | None, date_to: date | None) -> list[tuple[date, date, str]]:
        if date_from is None and date_to is None:
            today = date.today()
            date_from = today.replace(day=1)
            date_to = today
        elif date_from is None:
            if date_to is None:
                date_from = date.today().replace(day=1)
                date_to = date.today()
            else:
                date_from = date_to.replace(day=1)
        elif date_to is None:
            date_to = date_from
        cursor = date(date_from.year, date_from.month, 1)
        terminal = date(date_to.year, date_to.month, 1)
        buckets: list[tuple[date, date, str]] = []
        while cursor <= terminal:
            next_month = date(cursor.year + (1 if cursor.month == 12 else 0), 1 if cursor.month == 12 else cursor.month + 1, 1)
            month_end = next_month - timedelta(days=1)
            buckets.append((max(cursor, date_from), min(month_end, date_to), cursor.strftime("%b %Y")))
            cursor = next_month
        return buckets

    @staticmethod
    def _prior_period(date_from: date | None, date_to: date | None) -> tuple[date, date] | None:
        if date_from is None or date_to is None or date_to < date_from:
            return None
        span_days = (date_to - date_from).days
        prior_end = date_from - timedelta(days=1)
        prior_start = prior_end - timedelta(days=span_days)
        return prior_start, prior_end

    @staticmethod
    def _validate_filter(filter_dto: ReportingFilterDTO) -> None:
        if not isinstance(filter_dto.company_id, int) or filter_dto.company_id <= 0:
            raise ValidationError("Select an active company before opening financial analysis.")
        if filter_dto.date_from and filter_dto.date_to and filter_dto.date_to < filter_dto.date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")
