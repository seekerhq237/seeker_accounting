from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from seeker_accounting.modules.accounting.fiscal_periods.services.fiscal_calendar_service import (
    FiscalCalendarService,
)
from seeker_accounting.modules.accounting.journals.services.journal_service import JournalService
from seeker_accounting.modules.dashboard.dto.dashboard_dto import (
    DashboardAgingSnapshotDTO,
    DashboardAttentionItemDTO,
    DashboardCashAccountRowDTO,
    DashboardCashLiquidityDTO,
    DashboardCashTrendPointDTO,
    DashboardDataDTO,
    DashboardKpiDeltaDTO,
    DashboardKpiDTO,
    DashboardRecentActivityItemDTO,
)
from seeker_accounting.modules.inventory.services.inventory_valuation_service import (
    InventoryValuationService,
)
from seeker_accounting.modules.purchases.services.purchase_bill_service import PurchaseBillService
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.modules.reporting.services.ap_aging_report_service import APAgingReportService
from seeker_accounting.modules.reporting.services.ar_aging_report_service import ARAgingReportService
from seeker_accounting.modules.reporting.services.treasury_report_service import TreasuryReportService
from seeker_accounting.modules.sales.services.sales_invoice_service import SalesInvoiceService
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.app.navigation import nav_ids

_log = logging.getLogger(__name__)

_MAX_RECENT_ACTIVITY = 15


class DashboardService:
    """Aggregates data from multiple business services for the dashboard page.

    Each section is loaded independently with graceful error handling so that
    a failure in one subsystem doesn't block the rest of the dashboard.
    """

    def __init__(
        self,
        journal_service: JournalService,
        sales_invoice_service: SalesInvoiceService,
        purchase_bill_service: PurchaseBillService,
        ar_aging_report_service: ARAgingReportService,
        ap_aging_report_service: APAgingReportService,
        treasury_report_service: TreasuryReportService,
        fiscal_calendar_service: FiscalCalendarService,
        inventory_valuation_service: InventoryValuationService,
        unit_of_work_factory: UnitOfWorkFactory | None = None,
    ) -> None:
        self._journal_service = journal_service
        self._sales_invoice_service = sales_invoice_service
        self._purchase_bill_service = purchase_bill_service
        self._ar_aging_report_service = ar_aging_report_service
        self._ap_aging_report_service = ap_aging_report_service
        self._treasury_report_service = treasury_report_service
        self._fiscal_calendar_service = fiscal_calendar_service
        self._unit_of_work_factory = unit_of_work_factory
        self._inventory_valuation_service = inventory_valuation_service

    def get_dashboard_data(self, company_id: int, currency_code: str) -> DashboardDataDTO:
        today = date.today()

        # Resolve current fiscal period for date range
        period_start, period_end = self._resolve_current_period_range(company_id, today)

        period_label = self._build_period_label(company_id, today, period_start, period_end)
        kpis = self._load_kpis(company_id, currency_code, today, period_start, period_end)
        kpi_deltas = self._load_kpi_deltas(company_id, today, period_start, period_end, kpis)
        recent_activity = self._load_recent_activity(company_id)
        attention_items = self._load_attention_items(company_id, today)
        ar_aging = self._load_ar_aging(company_id, today)
        ap_aging = self._load_ap_aging(company_id, today)
        cash_liquidity = self._load_cash_liquidity(company_id, period_start, period_end, period_label)

        return DashboardDataDTO(
            kpis=kpis,
            kpi_deltas=kpi_deltas,
            recent_activity=tuple(recent_activity),
            attention_items=tuple(attention_items),
            ar_aging=ar_aging,
            ap_aging=ap_aging,
            cash_liquidity=cash_liquidity,
            as_of_date=today,
            loaded_at=datetime.now(),
            period_label=period_label,
        )

    # ------------------------------------------------------------------
    # Period resolution
    # ------------------------------------------------------------------

    def _resolve_current_period_range(
        self, company_id: int, today: date
    ) -> tuple[date, date]:
        """Return (start, end) of current fiscal period, or calendar month fallback."""
        try:
            period = self._fiscal_calendar_service.get_current_period(company_id, today)
            if period is not None:
                return period.start_date, period.end_date
        except Exception:
            _log.warning("Could not resolve current fiscal period for dashboard", exc_info=True)
        # Fallback to calendar month
        return today.replace(day=1), today

    def _build_period_label(self, company_id: int, today: date, period_start: date, period_end: date) -> str:
        """Build a human-readable period label, e.g. 'Jan 2026' or 'Q1 2026'."""
        try:
            period = self._fiscal_calendar_service.get_current_period(company_id, today)
            if period is not None and hasattr(period, 'period_name') and period.period_name:
                return period.period_name
        except Exception:
            pass
        return period_start.strftime("%b %Y")

    # ------------------------------------------------------------------
    # KPI loading
    # ------------------------------------------------------------------

    def _load_kpis(
        self,
        company_id: int,
        currency_code: str,
        today: date,
        period_start: date,
        period_end: date,
    ) -> DashboardKpiDTO:
        cash_position = self._safe_cash_position(company_id, today)
        receivables_due = self._safe_receivables_total(company_id, today)
        payables_due = self._safe_payables_total(company_id, today)
        month_revenue, month_expenses = self._safe_period_revenue_expenses(company_id, period_start, period_end)
        pending_postings = self._safe_pending_postings_count(company_id)

        return DashboardKpiDTO(
            cash_position=cash_position,
            receivables_due=receivables_due,
            payables_due=payables_due,
            month_revenue=month_revenue,
            month_expenses=month_expenses,
            pending_postings=pending_postings,
            currency_code=currency_code,
        )

    def _safe_cash_position(self, company_id: int, today: date) -> Decimal:
        try:
            return self._gl_balance_by_account_class(
                company_id, class_code="5", date_to=today,
            )
        except Exception:
            _log.warning("Dashboard: cash position unavailable", exc_info=True)
            return Decimal("0.00")

    def _safe_receivables_total(self, company_id: int, today: date) -> Decimal:
        try:
            report_filter = OperationalReportFilterDTO(
                company_id=company_id,
                as_of_date=today,
                posted_only=True,
            )
            report = self._ar_aging_report_service.get_report(report_filter)
            return report.grand_total
        except Exception:
            _log.warning("Dashboard: receivables total unavailable", exc_info=True)
            return Decimal("0.00")

    def _safe_payables_total(self, company_id: int, today: date) -> Decimal:
        try:
            report_filter = OperationalReportFilterDTO(
                company_id=company_id,
                as_of_date=today,
                posted_only=True,
            )
            report = self._ap_aging_report_service.get_report(report_filter)
            return report.grand_total
        except Exception:
            _log.warning("Dashboard: payables total unavailable", exc_info=True)
            return Decimal("0.00")

    def _safe_period_revenue_expenses(
        self, company_id: int, period_start: date, period_end: date
    ) -> tuple[Decimal | None, Decimal | None]:
        try:
            revenue = self._gl_balance_by_account_class(
                company_id, class_code="7",
                date_from=period_start, date_to=period_end,
            )
            expenses = self._gl_balance_by_account_class(
                company_id, class_code="6",
                date_from=period_start, date_to=period_end,
            )
            return abs(revenue), abs(expenses)
        except Exception:
            _log.warning("Dashboard: period revenue/expenses unavailable", exc_info=True)
            return None, None

    # ------------------------------------------------------------------
    # Month-over-month KPI deltas
    # ------------------------------------------------------------------

    def _load_kpi_deltas(
        self,
        company_id: int,
        today: date,
        period_start: date,
        period_end: date,
        current_kpis: DashboardKpiDTO,
    ) -> DashboardKpiDeltaDTO:
        """Compute MoM deltas by comparing current period to the prior period.

        Each delta is a percentage change: (current - prior) / |prior| * 100.
        Returns ``None`` for any component that cannot be computed safely.
        """
        try:
            prior_end = period_start - timedelta(days=1)
            # Approximate prior period as same-length window ending day before current start.
            span_days = max((period_end - period_start).days, 0)
            prior_start = prior_end - timedelta(days=span_days)

            # Revenue / expense deltas from GL class totals.
            prior_revenue, prior_expenses = self._safe_period_revenue_expenses(
                company_id, prior_start, prior_end
            )
            revenue_delta = self._compute_pct_delta(current_kpis.month_revenue, prior_revenue)
            expenses_delta = self._compute_pct_delta(current_kpis.month_expenses, prior_expenses)

            return DashboardKpiDeltaDTO(
                revenue_delta_pct=revenue_delta,
                expenses_delta_pct=expenses_delta,
            )
        except Exception:
            _log.warning("Dashboard: KPI deltas unavailable", exc_info=True)
            return DashboardKpiDeltaDTO()

    @staticmethod
    def _compute_pct_delta(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
        if current is None or prior is None:
            return None
        if prior == Decimal("0"):
            return None
        return ((current - prior) / abs(prior)) * Decimal("100")

    def _safe_pending_postings_count(self, company_id: int) -> int:
        count = 0
        try:
            drafts = self._journal_service.list_journal_entries(company_id, status_code="draft")
            count += len(drafts)
        except Exception:
            _log.warning("Dashboard: draft journals count unavailable", exc_info=True)
        try:
            draft_invoices = self._sales_invoice_service.list_sales_invoices(
                company_id, status_code="draft",
            )
            count += len(draft_invoices)
        except Exception:
            _log.warning("Dashboard: draft invoices count unavailable", exc_info=True)
        try:
            draft_bills = self._purchase_bill_service.list_purchase_bills(
                company_id, status_code="draft",
            )
            count += len(draft_bills)
        except Exception:
            _log.warning("Dashboard: draft bills count unavailable", exc_info=True)
        return count

    # ------------------------------------------------------------------
    # GL balance helper
    # ------------------------------------------------------------------

    def _gl_balance_by_account_class(
        self,
        company_id: int,
        class_code: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Decimal:
        """Sum posted journal entry lines for accounts in the given OHADA class.

        Returns net balance as (total_debit - total_credit).
        """
        if self._unit_of_work_factory is None:
            return Decimal("0.00")

        from sqlalchemy import func, and_, select
        from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
        from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
        from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
        from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass

        with self._unit_of_work_factory() as uow:
            conditions = [
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                AccountClass.code == class_code,
            ]
            if date_from is not None:
                conditions.append(JournalEntry.entry_date >= date_from)
            if date_to is not None:
                conditions.append(JournalEntry.entry_date <= date_to)

            stmt = (
                select(
                    func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("debit"),
                    func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("credit"),
                )
                .select_from(JournalEntryLine)
                .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
                .join(Account, Account.id == JournalEntryLine.account_id)
                .join(AccountClass, AccountClass.id == Account.account_class_id)
                .where(and_(*conditions))
            )
            row = uow.session.execute(stmt).one()

            debit = Decimal(str(row.debit)) if row.debit else Decimal("0")
            credit = Decimal(str(row.credit)) if row.credit else Decimal("0")
            return debit - credit

    # ------------------------------------------------------------------
    # Recent activity
    # ------------------------------------------------------------------

    def _load_recent_activity(self, company_id: int) -> list[DashboardRecentActivityItemDTO]:
        items: list[DashboardRecentActivityItemDTO] = []

        try:
            journals = self._journal_service.list_journal_entries(company_id)
            for j in journals:
                items.append(DashboardRecentActivityItemDTO(
                    entry_date=j.entry_date,
                    document_number=j.entry_number or "—",
                    description=j.description or j.reference_text or "Journal Entry",
                    amount=j.total_debit,
                    status_code=j.status_code,
                    document_type="journal",
                    nav_id=nav_ids.JOURNALS,
                    record_id=j.id,
                ))
        except Exception:
            _log.warning("Dashboard: recent journals unavailable", exc_info=True)

        try:
            invoices = self._sales_invoice_service.list_sales_invoices(company_id)
            for inv in invoices:
                items.append(DashboardRecentActivityItemDTO(
                    entry_date=inv.invoice_date,
                    document_number=inv.invoice_number,
                    description=f"Invoice to {inv.customer_name}",
                    amount=inv.total_amount,
                    status_code=inv.status_code,
                    document_type="invoice",
                    nav_id=nav_ids.SALES_INVOICES,
                    record_id=inv.id,
                ))
        except Exception:
            _log.warning("Dashboard: recent invoices unavailable", exc_info=True)

        try:
            bills = self._purchase_bill_service.list_purchase_bills(company_id)
            for b in bills:
                items.append(DashboardRecentActivityItemDTO(
                    entry_date=b.bill_date,
                    document_number=b.bill_number,
                    description=f"Bill from {b.supplier_name}",
                    amount=b.total_amount,
                    status_code=b.status_code,
                    document_type="bill",
                    nav_id=nav_ids.PURCHASE_BILLS,
                    record_id=b.id,
                ))
        except Exception:
            _log.warning("Dashboard: recent bills unavailable", exc_info=True)

        # Sort by date descending, then take top N
        items.sort(key=lambda x: x.entry_date, reverse=True)
        return items[:_MAX_RECENT_ACTIVITY]

    # ------------------------------------------------------------------
    # Attention items
    # ------------------------------------------------------------------

    def _load_attention_items(self, company_id: int, today: date) -> list[DashboardAttentionItemDTO]:
        items: list[DashboardAttentionItemDTO] = []

        # Draft/unposted journals
        try:
            drafts = self._journal_service.list_journal_entries(company_id, status_code="draft")
            if drafts:
                items.append(DashboardAttentionItemDTO(
                    label=f"{len(drafts)} unposted journal entr{'y' if len(drafts) == 1 else 'ies'}",
                    count=len(drafts),
                    severity="warning",
                    nav_id=nav_ids.JOURNALS,
                    icon_hint="journal",
                ))
        except Exception:
            _log.warning("Dashboard: draft journals attention unavailable", exc_info=True)

        # Overdue invoices
        try:
            invoices = self._sales_invoice_service.list_sales_invoices(
                company_id, status_code="posted",
            )
            overdue = [inv for inv in invoices
                       if inv.due_date < today and inv.payment_status_code != "paid"]
            if overdue:
                total = sum((inv.open_balance_amount for inv in overdue), Decimal("0.00"))
                items.append(DashboardAttentionItemDTO(
                    label=f"{len(overdue)} overdue invoice{'s' if len(overdue) != 1 else ''}",
                    count=len(overdue),
                    severity="danger",
                    nav_id=nav_ids.SALES_INVOICES,
                    icon_hint="invoice",
                ))
        except Exception:
            _log.warning("Dashboard: overdue invoices attention unavailable", exc_info=True)

        # Overdue bills
        try:
            bills = self._purchase_bill_service.list_purchase_bills(
                company_id, status_code="posted",
            )
            overdue_bills = [b for b in bills
                            if b.due_date < today and b.payment_status_code != "paid"]
            if overdue_bills:
                items.append(DashboardAttentionItemDTO(
                    label=f"{len(overdue_bills)} overdue bill{'s' if len(overdue_bills) != 1 else ''}",
                    count=len(overdue_bills),
                    severity="danger",
                    nav_id=nav_ids.PURCHASE_BILLS,
                    icon_hint="bill",
                ))
        except Exception:
            _log.warning("Dashboard: overdue bills attention unavailable", exc_info=True)

        # Low-stock inventory items
        try:
            summary = self._inventory_valuation_service.get_inventory_valuation_summary(company_id)
            if summary.low_stock_item_count > 0:
                items.append(DashboardAttentionItemDTO(
                    label=f"{summary.low_stock_item_count} item{'s' if summary.low_stock_item_count != 1 else ''} low on stock",
                    count=summary.low_stock_item_count,
                    severity="warning",
                    nav_id=nav_ids.STOCK_POSITION,
                    icon_hint="inventory",
                ))
        except Exception:
            _log.warning("Dashboard: low-stock attention unavailable", exc_info=True)

        return items

    # ------------------------------------------------------------------
    # Cash & liquidity
    # ------------------------------------------------------------------

    def _load_cash_liquidity(
        self,
        company_id: int,
        period_start: date,
        period_end: date,
        period_label: str,
    ) -> DashboardCashLiquidityDTO:
        try:
            report_filter = OperationalReportFilterDTO(
                company_id=company_id,
                date_from=period_start,
                date_to=period_end,
                posted_only=True,
            )
            report = self._treasury_report_service.get_report(report_filter)
            account_rows = tuple(
                DashboardCashAccountRowDTO(
                    account_name=row.account_name,
                    account_code=row.account_code,
                    account_type_code=row.account_type_code,
                    closing_balance=row.closing_balance,
                )
                for row in report.account_rows
            )

            # Aggregate movement rows into per-day inflow/outflow trend points.
            daily: dict[date, list[Decimal]] = {}
            for mv in report.movement_rows:
                bucket = daily.setdefault(mv.transaction_date, [Decimal("0"), Decimal("0")])
                bucket[0] += mv.inflow_amount
                bucket[1] += mv.outflow_amount
            trend_points = tuple(
                DashboardCashTrendPointDTO(as_of=d, inflow=vals[0], outflow=vals[1])
                for d, vals in sorted(daily.items(), key=lambda kv: kv[0])
            )

            return DashboardCashLiquidityDTO(
                accounts=account_rows,
                total_balance=report.total_closing,
                total_inflow=report.total_inflow,
                total_outflow=report.total_outflow,
                period_label=period_label,
                trend_points=trend_points,
            )
        except Exception:
            _log.warning("Dashboard: cash liquidity unavailable", exc_info=True)
            return DashboardCashLiquidityDTO(period_label=period_label)

    # ------------------------------------------------------------------
    # Aging snapshots
    # ------------------------------------------------------------------

    def _load_ar_aging(self, company_id: int, today: date) -> DashboardAgingSnapshotDTO:
        try:
            report_filter = OperationalReportFilterDTO(
                company_id=company_id,
                as_of_date=today,
                posted_only=True,
            )
            report = self._ar_aging_report_service.get_report(report_filter)
            return DashboardAgingSnapshotDTO(
                current=report.total_current,
                bucket_1_30=report.total_bucket_1_30,
                bucket_31_60=report.total_bucket_31_60,
                bucket_61_90=report.total_bucket_61_90,
                bucket_91_plus=report.total_bucket_91_plus,
                grand_total=report.grand_total,
            )
        except Exception:
            _log.warning("Dashboard: AR aging unavailable", exc_info=True)
            return DashboardAgingSnapshotDTO()

    def _load_ap_aging(self, company_id: int, today: date) -> DashboardAgingSnapshotDTO:
        try:
            report_filter = OperationalReportFilterDTO(
                company_id=company_id,
                as_of_date=today,
                posted_only=True,
            )
            report = self._ap_aging_report_service.get_report(report_filter)
            return DashboardAgingSnapshotDTO(
                current=report.total_current,
                bucket_1_30=report.total_bucket_1_30,
                bucket_31_60=report.total_bucket_31_60,
                bucket_61_90=report.total_bucket_61_90,
                bucket_91_plus=report.total_bucket_91_plus,
                grand_total=report.grand_total,
            )
        except Exception:
            _log.warning("Dashboard: AP aging unavailable", exc_info=True)
            return DashboardAgingSnapshotDTO()
