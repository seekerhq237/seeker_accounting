"""Reporting repositories."""

from seeker_accounting.modules.reporting.repositories.ap_aging_report_repository import (  # noqa: F401
    APAgingDocumentRow,
    APAgingReportRepository,
)
from seeker_accounting.modules.reporting.repositories.ar_aging_report_repository import (  # noqa: F401
    ARAgingDocumentRow,
    ARAgingReportRepository,
)
from seeker_accounting.modules.reporting.repositories.customer_statement_repository import (  # noqa: F401
    CustomerStatementMovementRow,
    CustomerStatementRepository,
)
from seeker_accounting.modules.reporting.repositories.general_ledger_report_repository import (  # noqa: F401
    GeneralLedgerReportRepository,
    LedgerLineRow,
)
from seeker_accounting.modules.reporting.repositories.depreciation_report_repository import (  # noqa: F401
    DepreciationReportQueryRow,
    DepreciationReportRepository,
    DepreciationRunDetailQueryRow,
)
from seeker_accounting.modules.reporting.repositories.financial_analysis_chart_repository import (  # noqa: F401
    FinancialAnalysisChartRepository,
    ProfitLossMonthlyActivityRow,
    ProfitLossPeriodActivityRow,
)
from seeker_accounting.modules.reporting.repositories.financial_analysis_repository import (  # noqa: F401
    FinancialAnalysisRepository,
    OperationalPeriodTotalRow,
)
from seeker_accounting.modules.reporting.repositories.fixed_asset_register_repository import (  # noqa: F401
    FixedAssetHistoryQueryRow,
    FixedAssetRegisterQueryRow,
    FixedAssetRegisterRepository,
)
from seeker_accounting.modules.reporting.repositories.ias_balance_sheet_repository import (  # noqa: F401
    IasBalanceSheetAccountRow,
    IasBalanceSheetRepository,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_mapping_repository import (  # noqa: F401
    IasIncomeStatementMappingRepository,
    IasMappingRow,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_repository import (  # noqa: F401
    IasAccountActivityRow,
    IasCompanyAccountRow,
    IasIncomeStatementRepository,
    IasSectionRow,
    IasTemplateRow,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_preference_repository import (  # noqa: F401
    IasIncomeStatementPreferenceRepository,
)
from seeker_accounting.modules.reporting.repositories.ohada_income_statement_repository import (  # noqa: F401
    OhadaAccountActivityRow,
    OhadaChartAccountRow,
    OhadaIncomeStatementRepository,
)
from seeker_accounting.modules.reporting.repositories.ohada_balance_sheet_repository import (  # noqa: F401
    OhadaBalanceSheetAccountRow,
    OhadaBalanceSheetRepository,
)
from seeker_accounting.modules.reporting.repositories.payroll_summary_report_repository import (  # noqa: F401
    PayrollSummaryEmployeeRow,
    PayrollSummaryReportRepository,
    PayrollSummaryRunRow,
    PayrollSummaryStatutoryRow,
)
from seeker_accounting.modules.reporting.repositories.stock_movement_report_repository import (  # noqa: F401
    StockMovementDetailQueryRow,
    StockMovementItemIdentityRow,
    StockMovementReportRepository,
    StockMovementSummaryQueryRow,
)
from seeker_accounting.modules.reporting.repositories.stock_valuation_report_repository import (  # noqa: F401
    StockValuationQueryRow,
    StockValuationReportRepository,
)
from seeker_accounting.modules.reporting.repositories.reporting_workspace_repository import ReportingWorkspaceRepository  # noqa: F401
from seeker_accounting.modules.reporting.repositories.supplier_statement_repository import (  # noqa: F401
    SupplierStatementMovementRow,
    SupplierStatementRepository,
)
from seeker_accounting.modules.reporting.repositories.treasury_report_repository import (  # noqa: F401
    TreasuryMovementSourceRow,
    TreasuryReportRepository,
)
from seeker_accounting.modules.reporting.repositories.trial_balance_report_repository import (  # noqa: F401
    TrialBalanceReportRepository,
    TrialBalanceRow,
)
