from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.reporting.dto.comparative_analysis_dto import (
    ComparativeAnalysisDTO,
    ComparativeMetricDTO,
)
from seeker_accounting.modules.reporting.dto.financial_analysis_chart_dto import (
    FinancialAnalysisChartReportDTO,
    FinancialAnalysisFilterDTO,
    FinancialAnalysisViewDTO,
    FinancialChartDetailDTO,
    FinancialChartDetailRowDTO,
    FinancialChartPointDTO,
    FinancialChartSeriesDTO,
    FinancialChartTableRowDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.repositories.financial_analysis_chart_repository import (
    FinancialAnalysisChartRepository,
    ProfitLossMonthlyActivityRow,
    ProfitLossPeriodActivityRow,
)
from seeker_accounting.modules.reporting.services.ias_balance_sheet_service import (
    IasBalanceSheetService,
)
from seeker_accounting.modules.reporting.specs.ias_income_statement_spec import (
    compute_natural_amount,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FinancialAnalysisChartRepositoryFactory = Callable[[Session], FinancialAnalysisChartRepository]

_ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class _MonthBucket:
    start_date: date
    end_date: date
    label: str


@dataclass(frozen=True, slots=True)
class _ProfitLossMetrics:
    revenue: Decimal
    expense: Decimal
    profit: Decimal


@dataclass(frozen=True, slots=True)
class _BalanceSnapshot:
    as_of_date: date
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    current_assets: Decimal
    non_current_assets: Decimal
    current_liabilities: Decimal
    non_current_liabilities: Decimal
    cash_equivalents: Decimal
    has_classified_activity: bool
    warnings: tuple[str, ...]


class FinancialAnalysisChartService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        financial_analysis_chart_repository_factory: FinancialAnalysisChartRepositoryFactory,
        ias_balance_sheet_service: IasBalanceSheetService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._financial_analysis_chart_repository_factory = financial_analysis_chart_repository_factory
        self._ias_balance_sheet_service = ias_balance_sheet_service

    def get_report(
        self,
        filter_dto: FinancialAnalysisFilterDTO,
    ) -> FinancialAnalysisChartReportDTO:
        self._validate_filter(filter_dto)
        comparison_period = self._prior_period(filter_dto.date_from, filter_dto.date_to)
        month_buckets = self._month_buckets(filter_dto.date_from, filter_dto.date_to)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, filter_dto.company_id)
            repo = self._financial_analysis_chart_repository_factory(uow.session)
            monthly_rows = repo.list_monthly_profit_loss_activity(
                filter_dto.company_id,
                filter_dto.date_from,
                filter_dto.date_to,
            )
            current_period_rows = repo.list_period_profit_loss_activity(
                filter_dto.company_id,
                filter_dto.date_from,
                filter_dto.date_to,
            )
            prior_period_rows = (
                repo.list_period_profit_loss_activity(
                    filter_dto.company_id,
                    comparison_period[0],
                    comparison_period[1],
                )
                if comparison_period is not None
                else []
            )

        revenue_by_month, expense_by_month = self._build_monthly_profit_loss_maps(monthly_rows)
        income_trend_view = self._build_income_trend_view(month_buckets, revenue_by_month, expense_by_month)
        income_compare_view = self._build_income_comparison_view(
            current_period_rows=current_period_rows,
            prior_period_rows=prior_period_rows,
            current_period=(filter_dto.date_from, filter_dto.date_to),
            prior_period=comparison_period,
        )

        top_level_warnings: list[str] = []
        balance_view = self._build_balance_view(
            company_id=filter_dto.company_id,
            current_period=(filter_dto.date_from, filter_dto.date_to),
            prior_period=comparison_period,
        )
        if balance_view.warnings:
            top_level_warnings.extend(balance_view.warnings)

        cash_view = self._build_cash_view(
            company_id=filter_dto.company_id,
            buckets=month_buckets,
            revenue_by_month=revenue_by_month,
            expense_by_month=expense_by_month,
        )
        if cash_view.warnings:
            top_level_warnings.extend(cash_view.warnings)

        return FinancialAnalysisChartReportDTO(
            company_id=filter_dto.company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            views=(
                income_trend_view,
                income_compare_view,
                balance_view,
                cash_view,
            ),
            warnings=tuple(dict.fromkeys(top_level_warnings)),
        )

    def get_chart_detail(
        self,
        filter_dto: FinancialAnalysisFilterDTO,
        detail_key: str,
    ) -> FinancialChartDetailDTO:
        self._validate_filter(filter_dto)
        parts = (detail_key or "").split("|")
        if not parts:
            raise ValidationError("No chart detail key was supplied.")

        if parts[0] == "pl" and len(parts) == 4:
            return self._profit_loss_detail(
                company_id=filter_dto.company_id,
                measure_code=parts[1],
                date_from=date.fromisoformat(parts[2]),
                date_to=date.fromisoformat(parts[3]),
                detail_key=detail_key,
            )
        if parts[0] == "bs" and len(parts) == 3:
            return self._balance_detail(
                company_id=filter_dto.company_id,
                line_code=parts[1],
                as_of_date=date.fromisoformat(parts[2]),
                detail_key=detail_key,
            )
        if parts[0] == "cash" and len(parts) == 3:
            return self._balance_detail(
                company_id=filter_dto.company_id,
                line_code=parts[1],
                as_of_date=date.fromisoformat(parts[2]),
                detail_key=detail_key,
            )
        raise ValidationError("The selected chart element cannot be drilled into.")

    def build_print_preview_meta(
        self,
        view_dto: FinancialAnalysisViewDTO,
        company_name: str,
        filter_dto: FinancialAnalysisFilterDTO,
    ) -> PrintPreviewMetaDTO:
        rows = [
            PrintPreviewRowDTO(
                row_type="line",
                reference_code=None,
                label=row.label,
                amount_text=self._fmt(row.current_value),
                secondary_amount_text=self._fmt(row.prior_value),
                tertiary_amount_text=self._fmt(row.variance_value),
            )
            for row in view_dto.table_rows
        ]
        return PrintPreviewMetaDTO(
            report_title=f"Financial Analysis | {view_dto.title}",
            company_name=company_name,
            period_label=self._period_label(filter_dto.date_from, filter_dto.date_to),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=view_dto.subtitle,
            amount_headers=view_dto.table_headers,
            rows=tuple(rows),
        )

    def _build_income_trend_view(
        self,
        month_buckets: list[_MonthBucket],
        revenue_by_month: dict[tuple[int, int], Decimal],
        expense_by_month: dict[tuple[int, int], Decimal],
    ) -> FinancialAnalysisViewDTO:
        revenue_points: list[FinancialChartPointDTO] = []
        expense_points: list[FinancialChartPointDTO] = []
        profit_points: list[FinancialChartPointDTO] = []
        table_rows: list[FinancialChartTableRowDTO] = []

        for bucket in month_buckets:
            period_key = (bucket.start_date.year, bucket.start_date.month)
            revenue = revenue_by_month.get(period_key, _ZERO)
            expense = expense_by_month.get(period_key, _ZERO)
            profit = (revenue - expense).quantize(Decimal("0.01"))
            revenue_points.append(
                FinancialChartPointDTO(
                    label=bucket.label,
                    value=revenue,
                    detail_key=self._pl_detail_key("revenue", bucket.start_date, bucket.end_date),
                )
            )
            expense_points.append(
                FinancialChartPointDTO(
                    label=bucket.label,
                    value=expense,
                    detail_key=self._pl_detail_key("expense", bucket.start_date, bucket.end_date),
                )
            )
            profit_points.append(
                FinancialChartPointDTO(
                    label=bucket.label,
                    value=profit,
                    detail_key=self._pl_detail_key("profit", bucket.start_date, bucket.end_date),
                )
            )
            table_rows.append(
                FinancialChartTableRowDTO(
                    key=bucket.start_date.isoformat(),
                    label=bucket.label,
                    current_value=revenue,
                    prior_value=expense,
                    variance_value=profit,
                )
            )

        return FinancialAnalysisViewDTO(
            view_key="income_trend",
            title="Income Statement Trend",
            subtitle="Revenue, total expenses, and profit for period by month.",
            chart_type="line",
            series=(
                FinancialChartSeriesDTO("revenue", "Revenue", "accent", tuple(revenue_points)),
                FinancialChartSeriesDTO("expense", "Expenses", "danger", tuple(expense_points)),
                FinancialChartSeriesDTO("profit", "Profit", "success", tuple(profit_points)),
            ),
            table_rows=tuple(table_rows),
            table_headers=("Revenue", "Expenses", "Profit"),
            empty_state_message="No posted profit-or-loss activity was found in the selected period.",
        )

    def _build_income_comparison_view(
        self,
        *,
        current_period_rows: list[ProfitLossPeriodActivityRow],
        prior_period_rows: list[ProfitLossPeriodActivityRow],
        current_period: tuple[date | None, date | None],
        prior_period: tuple[date, date] | None,
    ) -> FinancialAnalysisViewDTO:
        current_metrics = self._period_metrics(current_period_rows)
        prior_metrics = self._period_metrics(prior_period_rows) if prior_period is not None else None
        current_label = self._period_label(*current_period)
        prior_label = self._period_label(*prior_period) if prior_period is not None else "No prior period"
        series = [
            FinancialChartSeriesDTO(
                "current_period",
                current_label,
                "accent",
                (
                    FinancialChartPointDTO("Revenue", current_metrics.revenue, self._pl_detail_key("revenue", *current_period)),
                    FinancialChartPointDTO("Expenses", current_metrics.expense, self._pl_detail_key("expense", *current_period)),
                    FinancialChartPointDTO("Profit", current_metrics.profit, self._pl_detail_key("profit", *current_period)),
                ),
            )
        ]
        if prior_metrics is not None and prior_period is not None:
            series.append(
                FinancialChartSeriesDTO(
                    "prior_period",
                    prior_label,
                    "warning",
                    (
                        FinancialChartPointDTO("Revenue", prior_metrics.revenue, self._pl_detail_key("revenue", *prior_period)),
                        FinancialChartPointDTO("Expenses", prior_metrics.expense, self._pl_detail_key("expense", *prior_period)),
                        FinancialChartPointDTO("Profit", prior_metrics.profit, self._pl_detail_key("profit", *prior_period)),
                    ),
                )
            )

        table_rows = tuple(
            self._comparison_table_row(
                key=key,
                label=label,
                current_value=current_value,
                prior_value=prior_value,
            )
            for key, label, current_value, prior_value in (
                ("revenue", "Revenue", current_metrics.revenue, prior_metrics.revenue if prior_metrics else None),
                ("expense", "Expenses", current_metrics.expense, prior_metrics.expense if prior_metrics else None),
                ("profit", "Profit for Period", current_metrics.profit, prior_metrics.profit if prior_metrics else None),
            )
        )

        comparative = ComparativeAnalysisDTO(
            current_label=current_label,
            prior_label=prior_label,
            metrics=tuple(
                ComparativeMetricDTO(
                    key=row.key,
                    label=row.label,
                    current_value=row.current_value,
                    prior_value=row.prior_value,
                    variance_value=row.variance_value,
                    variance_percent=self._variance_percent(row.current_value, row.prior_value),
                )
                for row in table_rows
            ),
            limitation_message=None if prior_period is not None else "Prior-period comparison is unavailable without a complete current period.",
        )

        return FinancialAnalysisViewDTO(
            view_key="income_comparison",
            title="Income Comparison",
            subtitle="Current period versus the immediately preceding comparable period.",
            chart_type="grouped_bar",
            series=tuple(series),
            table_rows=table_rows,
            table_headers=(current_label, prior_label, "Variance"),
            comparative=comparative,
            warnings=(
                (comparative.limitation_message,)
                if comparative.limitation_message is not None
                else ()
            ),
        )

    def _build_balance_view(
        self,
        *,
        company_id: int,
        current_period: tuple[date | None, date | None],
        prior_period: tuple[date, date] | None,
    ) -> FinancialAnalysisViewDTO:
        current_as_of = current_period[1] or current_period[0]
        if current_as_of is None:
            return FinancialAnalysisViewDTO(
                view_key="balance_composition",
                title="Balance Sheet Composition",
                subtitle="Current versus prior composition of assets, liabilities, and equity.",
                chart_type="grouped_bar",
                warnings=("Select at least one reporting date to build balance-sheet analysis.",),
                empty_state_message="No statement date is available.",
            )

        current_snapshot = self._balance_snapshot(company_id, current_as_of)
        prior_snapshot = self._balance_snapshot(company_id, prior_period[1]) if prior_period is not None else None
        current_label = self._as_of_label(current_as_of)
        prior_label = self._as_of_label(prior_period[1]) if prior_period is not None else "No prior snapshot"

        series = [
            FinancialChartSeriesDTO(
                "current_balance",
                current_label,
                "accent",
                (
                    FinancialChartPointDTO("Assets", current_snapshot.total_assets, self._bs_detail_key("TOTAL_ASSETS", current_snapshot.as_of_date)),
                    FinancialChartPointDTO("Liabilities", current_snapshot.total_liabilities, self._bs_detail_key("TOTAL_LIABILITIES", current_snapshot.as_of_date)),
                    FinancialChartPointDTO("Equity", current_snapshot.total_equity, self._bs_detail_key("TOTAL_EQUITY", current_snapshot.as_of_date)),
                ),
            )
        ]
        if prior_snapshot is not None:
            series.append(
                FinancialChartSeriesDTO(
                    "prior_balance",
                    prior_label,
                    "warning",
                    (
                        FinancialChartPointDTO("Assets", prior_snapshot.total_assets, self._bs_detail_key("TOTAL_ASSETS", prior_snapshot.as_of_date)),
                        FinancialChartPointDTO("Liabilities", prior_snapshot.total_liabilities, self._bs_detail_key("TOTAL_LIABILITIES", prior_snapshot.as_of_date)),
                        FinancialChartPointDTO("Equity", prior_snapshot.total_equity, self._bs_detail_key("TOTAL_EQUITY", prior_snapshot.as_of_date)),
                    ),
                )
            )

        table_rows = (
            self._comparison_table_row("current_assets", "Current assets", current_snapshot.current_assets, prior_snapshot.current_assets if prior_snapshot else None),
            self._comparison_table_row("non_current_assets", "Non-current assets", current_snapshot.non_current_assets, prior_snapshot.non_current_assets if prior_snapshot else None),
            self._comparison_table_row("current_liabilities", "Current liabilities", current_snapshot.current_liabilities, prior_snapshot.current_liabilities if prior_snapshot else None),
            self._comparison_table_row("non_current_liabilities", "Non-current liabilities", current_snapshot.non_current_liabilities, prior_snapshot.non_current_liabilities if prior_snapshot else None),
            self._comparison_table_row("equity", "Equity", current_snapshot.total_equity, prior_snapshot.total_equity if prior_snapshot else None),
        )

        warnings = list(current_snapshot.warnings)
        if prior_snapshot is not None:
            warnings.extend(prior_snapshot.warnings)
        if prior_snapshot is None:
            warnings.append("Prior-period balance-sheet comparison is unavailable without a complete current period.")

        return FinancialAnalysisViewDTO(
            view_key="balance_composition",
            title="Balance Sheet Composition",
            subtitle="Assets, liabilities, and equity with current versus non-current support rows.",
            chart_type="grouped_bar",
            series=tuple(series),
            table_rows=table_rows,
            table_headers=(current_label, prior_label, "Variance"),
            warnings=tuple(dict.fromkeys(warnings)),
            empty_state_message="No posted balance-sheet activity was classified for the selected date.",
        )

    def _build_cash_view(
        self,
        *,
        company_id: int,
        buckets: list[_MonthBucket],
        revenue_by_month: dict[tuple[int, int], Decimal],
        expense_by_month: dict[tuple[int, int], Decimal],
    ) -> FinancialAnalysisViewDTO:
        cash_points: list[FinancialChartPointDTO] = []
        revenue_points: list[FinancialChartPointDTO] = []
        expense_points: list[FinancialChartPointDTO] = []
        table_rows: list[FinancialChartTableRowDTO] = []
        warnings: list[str] = []

        for bucket in buckets:
            snapshot = self._balance_snapshot(company_id, bucket.end_date)
            warnings.extend(snapshot.warnings)
            period_key = (bucket.start_date.year, bucket.start_date.month)
            revenue = revenue_by_month.get(period_key, _ZERO)
            expense = expense_by_month.get(period_key, _ZERO)
            cash_points.append(
                FinancialChartPointDTO(
                    label=bucket.label,
                    value=snapshot.cash_equivalents,
                    detail_key=self._cash_detail_key("CASH_EQUIVALENTS", bucket.end_date),
                )
            )
            revenue_points.append(
                FinancialChartPointDTO(
                    label=bucket.label,
                    value=revenue,
                    detail_key=self._pl_detail_key("revenue", bucket.start_date, bucket.end_date),
                )
            )
            expense_points.append(
                FinancialChartPointDTO(
                    label=bucket.label,
                    value=expense,
                    detail_key=self._pl_detail_key("expense", bucket.start_date, bucket.end_date),
                )
            )
            table_rows.append(
                FinancialChartTableRowDTO(
                    key=bucket.start_date.isoformat(),
                    label=bucket.label,
                    current_value=snapshot.cash_equivalents,
                    prior_value=revenue,
                    variance_value=expense,
                )
            )

        return FinancialAnalysisViewDTO(
            view_key="cash_revenue_expense",
            title="Cash, Revenue, and Expense Trend",
            subtitle="Month-end cash equivalents alongside monthly revenue and expense totals.",
            chart_type="line",
            series=(
                FinancialChartSeriesDTO("cash", "Cash Balance", "accent", tuple(cash_points)),
                FinancialChartSeriesDTO("revenue", "Revenue", "success", tuple(revenue_points)),
                FinancialChartSeriesDTO("expense", "Expenses", "danger", tuple(expense_points)),
            ),
            table_rows=tuple(table_rows),
            table_headers=("Cash Balance", "Revenue", "Expenses"),
            warnings=tuple(dict.fromkeys(warnings)),
            empty_state_message="No cash-equivalent balances or profit-and-loss activity were found for the selected months.",
        )

    def _profit_loss_detail(
        self,
        *,
        company_id: int,
        measure_code: str,
        date_from: date,
        date_to: date,
        detail_key: str,
    ) -> FinancialChartDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._financial_analysis_chart_repository_factory(uow.session)
            rows = repo.list_period_profit_loss_activity(company_id, date_from, date_to)

        detail_rows = self._build_profit_loss_detail_rows(rows, measure_code)
        total_amount = sum((row.amount for row in detail_rows), _ZERO)
        return FinancialChartDetailDTO(
            company_id=company_id,
            detail_key=detail_key,
            title=self._profit_loss_detail_title(measure_code),
            subtitle=self._period_label(date_from, date_to),
            date_from=date_from,
            date_to=date_to,
            total_amount=total_amount,
            rows=tuple(detail_rows),
        )

    def _balance_detail(
        self,
        *,
        company_id: int,
        line_code: str,
        as_of_date: date,
        detail_key: str,
    ) -> FinancialChartDetailDTO:
        filter_dto = ReportingFilterDTO(
            company_id=company_id,
            date_from=None,
            date_to=as_of_date,
            posted_only=True,
        )

        if line_code == "TOTAL_LIABILITIES":
            current_detail = self._ias_balance_sheet_service.get_line_detail(
                filter_dto,
                "TOTAL_CURRENT_LIABILITIES",
            )
            non_current_detail = self._ias_balance_sheet_service.get_line_detail(
                filter_dto,
                "TOTAL_NON_CURRENT_LIABILITIES",
            )
            detail_rows = [
                FinancialChartDetailRowDTO(
                    account_id=row.account_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    amount=row.amount,
                    note=row.line_label,
                )
                for row in (*current_detail.accounts, *non_current_detail.accounts)
            ]
            total_amount = sum((row.amount for row in detail_rows), _ZERO)
            title = "Total Liabilities"
        else:
            detail = self._ias_balance_sheet_service.get_line_detail(filter_dto, line_code)
            detail_rows = [
                FinancialChartDetailRowDTO(
                    account_id=row.account_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    amount=row.amount,
                    note=row.contribution_kind_code.replace("_", " ").title(),
                )
                for row in detail.accounts
            ]
            total_amount = detail.amount
            title = detail.line_label

        return FinancialChartDetailDTO(
            company_id=company_id,
            detail_key=detail_key,
            title=title,
            subtitle=self._as_of_label(as_of_date),
            date_from=None,
            date_to=as_of_date,
            total_amount=total_amount,
            rows=tuple(sorted(detail_rows, key=lambda row: (abs(row.amount), row.account_code), reverse=True)),
        )

    def _build_monthly_profit_loss_maps(
        self,
        rows: list[ProfitLossMonthlyActivityRow],
    ) -> tuple[dict[tuple[int, int], Decimal], dict[tuple[int, int], Decimal]]:
        revenue_by_month: dict[tuple[int, int], Decimal] = {}
        expense_by_month: dict[tuple[int, int], Decimal] = {}
        for row in rows:
            classification = self._profit_loss_classification(row.account_class_code, row.account_type_section_code)
            if classification is None:
                continue
            amount = compute_natural_amount(
                total_debit=row.total_debit,
                total_credit=row.total_credit,
                normal_balance=row.normal_balance,
            )
            period_key = (row.period_year, row.period_month)
            if classification == "revenue":
                revenue_by_month[period_key] = (revenue_by_month.get(period_key, _ZERO) + amount).quantize(Decimal("0.01"))
            else:
                expense_by_month[period_key] = (expense_by_month.get(period_key, _ZERO) + amount).quantize(Decimal("0.01"))
        return revenue_by_month, expense_by_month

    def _period_metrics(self, rows: list[ProfitLossPeriodActivityRow]) -> _ProfitLossMetrics:
        revenue = _ZERO
        expense = _ZERO
        for row in rows:
            classification = self._profit_loss_classification(row.account_class_code, row.account_type_section_code)
            if classification is None:
                continue
            amount = compute_natural_amount(
                total_debit=row.total_debit,
                total_credit=row.total_credit,
                normal_balance=row.normal_balance,
            )
            if classification == "revenue":
                revenue += amount
            else:
                expense += amount
        return _ProfitLossMetrics(
            revenue=revenue.quantize(Decimal("0.01")),
            expense=expense.quantize(Decimal("0.01")),
            profit=(revenue - expense).quantize(Decimal("0.01")),
        )

    def _build_profit_loss_detail_rows(
        self,
        rows: list[ProfitLossPeriodActivityRow],
        measure_code: str,
    ) -> list[FinancialChartDetailRowDTO]:
        detail_rows: list[FinancialChartDetailRowDTO] = []
        for row in rows:
            classification = self._profit_loss_classification(row.account_class_code, row.account_type_section_code)
            if classification is None:
                continue
            natural_amount = compute_natural_amount(
                total_debit=row.total_debit,
                total_credit=row.total_credit,
                normal_balance=row.normal_balance,
            )
            if measure_code == "revenue" and classification != "revenue":
                continue
            if measure_code == "expense" and classification != "expense":
                continue
            amount = natural_amount
            note = classification.title()
            if measure_code == "profit":
                amount = natural_amount if classification == "revenue" else -natural_amount
                note = "Revenue" if classification == "revenue" else "Expense"
            detail_rows.append(
                FinancialChartDetailRowDTO(
                    account_id=row.account_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    amount=amount.quantize(Decimal("0.01")),
                    note=note,
                )
            )
        return sorted(detail_rows, key=lambda row: (abs(row.amount), row.account_code), reverse=True)

    def _balance_snapshot(self, company_id: int, as_of_date: date) -> _BalanceSnapshot:
        filter_dto = ReportingFilterDTO(
            company_id=company_id,
            date_from=None,
            date_to=as_of_date,
            posted_only=True,
        )
        report = self._ias_balance_sheet_service.get_statement(filter_dto)
        line_map = {
            line.code: (line.amount or _ZERO)
            for line in report.lines
        }
        return _BalanceSnapshot(
            as_of_date=as_of_date,
            total_assets=line_map.get("TOTAL_ASSETS", _ZERO),
            total_liabilities=(
                line_map.get("TOTAL_CURRENT_LIABILITIES", _ZERO)
                + line_map.get("TOTAL_NON_CURRENT_LIABILITIES", _ZERO)
            ).quantize(Decimal("0.01")),
            total_equity=line_map.get("TOTAL_EQUITY", _ZERO),
            current_assets=line_map.get("TOTAL_CURRENT_ASSETS", _ZERO),
            non_current_assets=line_map.get("TOTAL_NON_CURRENT_ASSETS", _ZERO),
            current_liabilities=line_map.get("TOTAL_CURRENT_LIABILITIES", _ZERO),
            non_current_liabilities=line_map.get("TOTAL_NON_CURRENT_LIABILITIES", _ZERO),
            cash_equivalents=line_map.get("CASH_EQUIVALENTS", _ZERO),
            has_classified_activity=report.has_classified_activity,
            warnings=tuple(warning.message for warning in report.warnings),
        )

    def _comparison_table_row(
        self,
        key: str,
        label: str,
        current_value: Decimal,
        prior_value: Decimal | None,
    ) -> FinancialChartTableRowDTO:
        variance_value = None if prior_value is None else (current_value - prior_value).quantize(Decimal("0.01"))
        return FinancialChartTableRowDTO(
            key=key,
            label=label,
            current_value=current_value,
            prior_value=prior_value,
            variance_value=variance_value,
        )

    def _validate_filter(self, filter_dto: FinancialAnalysisFilterDTO) -> None:
        if filter_dto.company_id <= 0:
            raise ValidationError("Select an active company before running financial analysis.")
        if filter_dto.date_from and filter_dto.date_to and filter_dto.date_to < filter_dto.date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} was not found.")

    @staticmethod
    def _profit_loss_classification(
        account_class_code: str | None,
        account_type_section_code: str | None,
    ) -> str | None:
        section_code = (account_type_section_code or "").strip().upper()
        if section_code in {"REVENUE", "OTHER_REVENUE"} or account_class_code == "7":
            return "revenue"
        if section_code in {"EXPENSE", "OTHER_EXPENSE"} or account_class_code in {"6", "8"}:
            return "expense"
        return None

    @staticmethod
    def _month_buckets(date_from: date | None, date_to: date | None) -> list[_MonthBucket]:
        if date_from is None and date_to is None:
            today = date.today()
            date_from = today.replace(day=1)
            date_to = today
        elif date_from is None:
            date_from = date_to.replace(day=1) if date_to else date.today().replace(day=1)
        elif date_to is None:
            date_to = date_from

        cursor = date(date_from.year, date_from.month, 1)
        terminal = date(date_to.year, date_to.month, 1)
        buckets: list[_MonthBucket] = []
        while cursor <= terminal:
            next_month = date(
                cursor.year + (1 if cursor.month == 12 else 0),
                1 if cursor.month == 12 else cursor.month + 1,
                1,
            )
            month_end = next_month - timedelta(days=1)
            buckets.append(
                _MonthBucket(
                    start_date=max(cursor, date_from),
                    end_date=min(month_end, date_to),
                    label=cursor.strftime("%b %Y"),
                )
            )
            cursor = next_month
        return buckets

    @staticmethod
    def _prior_period(date_from: date | None, date_to: date | None) -> tuple[date, date] | None:
        if date_from is None or date_to is None:
            return None
        period_days = (date_to - date_from).days
        prior_end = date_from - timedelta(days=1)
        prior_start = prior_end - timedelta(days=period_days)
        return prior_start, prior_end

    @staticmethod
    def _variance_percent(current_value: Decimal | None, prior_value: Decimal | None) -> Decimal | None:
        if current_value is None or prior_value in {None, _ZERO}:
            return None
        return (((current_value - prior_value) / prior_value) * Decimal("100")).quantize(Decimal("0.01"))

    @staticmethod
    def _period_label(date_from: date | None, date_to: date | None) -> str:
        if date_from is None and date_to is None:
            return "All periods"
        if date_from is None:
            return f"Up to {date_to.strftime('%d %b %Y')}" if date_to else "All periods"
        if date_to is None:
            return f"From {date_from.strftime('%d %b %Y')}"
        return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"

    @staticmethod
    def _as_of_label(as_of_date: date) -> str:
        return f"As at {as_of_date.strftime('%d %b %Y')}"

    @staticmethod
    def _profit_loss_detail_title(measure_code: str) -> str:
        labels = {
            "revenue": "Revenue Detail",
            "expense": "Expense Detail",
            "profit": "Profit Bridge Detail",
        }
        return labels.get(measure_code, "Chart Detail")

    @staticmethod
    def _pl_detail_key(measure_code: str, date_from: date | None, date_to: date | None) -> str | None:
        if date_from is None or date_to is None:
            return None
        return f"pl|{measure_code}|{date_from.isoformat()}|{date_to.isoformat()}"

    @staticmethod
    def _bs_detail_key(line_code: str, as_of_date: date) -> str:
        return f"bs|{line_code}|{as_of_date.isoformat()}"

    @staticmethod
    def _cash_detail_key(line_code: str, as_of_date: date) -> str:
        return f"cash|{line_code}|{as_of_date.isoformat()}"

    @staticmethod
    def _fmt(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return f"{value:,.2f}"
