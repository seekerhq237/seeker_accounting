from __future__ import annotations

from dataclasses import dataclass

from seeker_accounting.app.context.active_company_context import ActiveCompanyContext
from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.app.context.session_context import SessionContext
from seeker_accounting.app.navigation.navigation_service import NavigationService
from seeker_accounting.app.navigation.workflow_resume_service import WorkflowResumeService
from seeker_accounting.config.settings import AppSettings
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_of_accounts_service import (
    ChartOfAccountsService,
)
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_seed_service import (
    ChartSeedService,
)
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_template_import_service import (
    ChartTemplateImportService,
)
from seeker_accounting.modules.accounting.fiscal_periods.services.fiscal_calendar_service import (
    FiscalCalendarService,
)
from seeker_accounting.modules.accounting.fiscal_periods.services.period_control_service import (
    PeriodControlService,
)
from seeker_accounting.modules.accounting.journals.services.journal_posting_service import (
    JournalPostingService,
)
from seeker_accounting.modules.accounting.journals.services.journal_service import JournalService
from seeker_accounting.modules.accounting.reference_data.services.numbering_setup_service import (
    NumberingSetupService,
)
from seeker_accounting.modules.accounting.reference_data.services.account_role_mapping_service import (
    AccountRoleMappingService,
)
from seeker_accounting.modules.accounting.reference_data.services.reference_data_service import (
    ReferenceDataService,
)
from seeker_accounting.modules.accounting.reference_data.services.tax_setup_service import TaxSetupService
from seeker_accounting.modules.companies.services.company_context_service import CompanyContextService
from seeker_accounting.modules.companies.services.company_logo_service import CompanyLogoService
from seeker_accounting.modules.companies.services.company_project_preference_service import CompanyProjectPreferenceService
from seeker_accounting.modules.companies.services.company_seed_service import CompanySeedService
from seeker_accounting.modules.companies.services.company_service import CompanyService
from seeker_accounting.modules.contracts_projects.services.contract_change_order_service import ContractChangeOrderService
from seeker_accounting.modules.contracts_projects.services.contract_service import ContractService
from seeker_accounting.modules.contracts_projects.services.project_cost_code_service import ProjectCostCodeService
from seeker_accounting.modules.contracts_projects.services.project_service import ProjectService
from seeker_accounting.modules.contracts_projects.services.project_structure_service import ProjectStructureService
from seeker_accounting.modules.budgeting.services.project_budget_service import ProjectBudgetService
from seeker_accounting.modules.budgeting.services.budget_approval_service import BudgetApprovalService
from seeker_accounting.modules.budgeting.services.budget_control_service import BudgetControlService
from seeker_accounting.modules.job_costing.services.project_commitment_service import ProjectCommitmentService
from seeker_accounting.modules.job_costing.services.project_actual_cost_service import (
    ProjectActualCostService,
)
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.modules.job_costing.services.project_profitability_service import (
    ProjectProfitabilityService,
)
from seeker_accounting.modules.management_reporting.services.contract_reporting_service import (
    ContractReportingService,
)
from seeker_accounting.modules.management_reporting.services.budget_reporting_service import (
    BudgetReportingService,
)
from seeker_accounting.modules.reporting.services.general_ledger_report_service import (
    GeneralLedgerReportService,
)
from seeker_accounting.modules.reporting.services.balance_sheet_export_service import (
    BalanceSheetExportService,
)
from seeker_accounting.modules.reporting.services.income_statement_export_service import (
    IncomeStatementExportService,
)
from seeker_accounting.modules.reporting.services.ap_aging_report_service import (
    APAgingReportService,
)
from seeker_accounting.modules.reporting.services.ar_aging_report_service import (
    ARAgingReportService,
)
from seeker_accounting.modules.reporting.services.depreciation_report_service import (
    DepreciationReportService,
)
from seeker_accounting.modules.reporting.services.balance_sheet_template_service import (
    BalanceSheetTemplateService,
)
from seeker_accounting.modules.reporting.services.customer_statement_service import (
    CustomerStatementService,
)
from seeker_accounting.modules.reporting.services.financial_analysis_service import (
    FinancialAnalysisService,
)
from seeker_accounting.modules.reporting.services.financial_analysis_chart_service import (
    FinancialAnalysisChartService,
)
from seeker_accounting.modules.reporting.services.financial_analysis_workspace_service import (
    FinancialAnalysisWorkspaceService,
)
from seeker_accounting.modules.reporting.services.fixed_asset_register_service import (
    FixedAssetRegisterService,
)
from seeker_accounting.modules.reporting.services.ias_balance_sheet_service import (
    IasBalanceSheetService,
)
from seeker_accounting.modules.reporting.services.ias_income_statement_mapping_service import (
    IasIncomeStatementMappingService,
)
from seeker_accounting.modules.reporting.services.ias_income_statement_service import (
    IasIncomeStatementService,
)
from seeker_accounting.modules.reporting.services.ias_income_statement_template_service import (
    IasIncomeStatementTemplateService,
)
from seeker_accounting.modules.reporting.services.insight_rules_service import (
    InsightRulesService,
)
from seeker_accounting.modules.reporting.services.interpretation_service import (
    InterpretationService,
)
from seeker_accounting.modules.reporting.services.ohada_balance_sheet_service import (
    OhadaBalanceSheetService,
)
from seeker_accounting.modules.reporting.services.ohada_income_statement_service import (
    OhadaIncomeStatementService,
)
from seeker_accounting.modules.reporting.services.ohada_income_statement_template_service import (
    OhadaIncomeStatementTemplateService,
)
from seeker_accounting.modules.reporting.services.payroll_summary_report_service import (
    PayrollSummaryReportService,
)
from seeker_accounting.modules.reporting.services.ratio_analysis_service import (
    RatioAnalysisService,
)
from seeker_accounting.modules.reporting.services.supplier_statement_service import (
    SupplierStatementService,
)
from seeker_accounting.modules.reporting.services.stock_movement_report_service import (
    StockMovementReportService,
)
from seeker_accounting.modules.reporting.services.stock_valuation_report_service import (
    StockValuationReportService,
)
from seeker_accounting.modules.reporting.services.treasury_report_service import (
    TreasuryReportService,
)
from seeker_accounting.modules.reporting.services.trial_balance_report_service import (
    TrialBalanceReportService,
)
from seeker_accounting.modules.reporting.services.working_capital_analysis_service import (
    WorkingCapitalAnalysisService,
)
from seeker_accounting.modules.customers.services.customer_service import CustomerService
from seeker_accounting.modules.parties.services.control_account_foundation_service import (
    ControlAccountFoundationService,
)
from seeker_accounting.modules.purchases.services.purchase_bill_posting_service import (
    PurchaseBillPostingService,
)
from seeker_accounting.modules.purchases.services.purchase_bill_service import PurchaseBillService
from seeker_accounting.modules.purchases.services.purchase_order_service import PurchaseOrderService
from seeker_accounting.modules.purchases.services.purchase_credit_note_service import PurchaseCreditNoteService
from seeker_accounting.modules.purchases.services.purchase_credit_note_posting_service import PurchaseCreditNotePostingService
from seeker_accounting.modules.purchases.services.supplier_payment_posting_service import (
    SupplierPaymentPostingService,
)
from seeker_accounting.modules.purchases.services.supplier_payment_service import SupplierPaymentService
from seeker_accounting.modules.sales.services.customer_receipt_posting_service import CustomerReceiptPostingService
from seeker_accounting.modules.sales.services.customer_receipt_print_service import CustomerReceiptPrintService
from seeker_accounting.modules.sales.services.customer_receipt_service import CustomerReceiptService
from seeker_accounting.modules.sales.services.customer_quote_service import CustomerQuoteService
from seeker_accounting.modules.sales.services.sales_order_service import SalesOrderService
from seeker_accounting.modules.sales.services.sales_credit_note_service import SalesCreditNoteService
from seeker_accounting.modules.sales.services.sales_credit_note_posting_service import SalesCreditNotePostingService
from seeker_accounting.modules.sales.services.sales_invoice_posting_service import SalesInvoicePostingService
from seeker_accounting.modules.sales.services.sales_invoice_print_service import SalesInvoicePrintService
from seeker_accounting.modules.sales.services.sales_invoice_service import SalesInvoiceService
from seeker_accounting.modules.suppliers.services.supplier_service import SupplierService
from seeker_accounting.modules.suppliers.services.supplier_print_service import SupplierPrintService
from seeker_accounting.modules.purchases.services.purchase_bill_print_service import PurchaseBillPrintService
from seeker_accounting.modules.purchases.services.supplier_payment_print_service import SupplierPaymentPrintService
from seeker_accounting.modules.accounting.journals.services.journal_entry_print_service import JournalEntryPrintService
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_of_accounts_print_service import (
    ChartOfAccountsPrintService,
)
from seeker_accounting.modules.customers.services.customer_print_service import CustomerPrintService
from seeker_accounting.modules.treasury.services.financial_account_print_service import FinancialAccountPrintService
from seeker_accounting.modules.treasury.services.treasury_transaction_print_service import TreasuryTransactionPrintService
from seeker_accounting.modules.treasury.services.treasury_transfer_print_service import TreasuryTransferPrintService
from seeker_accounting.modules.inventory.services.item_print_service import ItemPrintService
from seeker_accounting.modules.inventory.services.inventory_document_print_service import InventoryDocumentPrintService
from seeker_accounting.modules.fixed_assets.services.asset_print_service import AssetPrintService
from seeker_accounting.modules.fixed_assets.services.depreciation_run_print_service import DepreciationRunPrintService
from seeker_accounting.modules.audit.services.audit_log_print_service import AuditLogPrintService
from seeker_accounting.modules.administration.services.backup_export_service import BackupExportService
from seeker_accounting.modules.administration.services.backup_analysis_service import BackupAnalysisService
from seeker_accounting.modules.administration.services.backup_merge_service import BackupMergeService
from seeker_accounting.platform.licensing.license_service import LicenseService
from seeker_accounting.modules.treasury.services.financial_account_service import FinancialAccountService
from seeker_accounting.modules.treasury.services.treasury_transaction_service import TreasuryTransactionService
from seeker_accounting.modules.treasury.services.treasury_transaction_posting_service import (
    TreasuryTransactionPostingService,
)
from seeker_accounting.modules.treasury.services.treasury_transfer_service import TreasuryTransferService
from seeker_accounting.modules.treasury.services.treasury_transfer_posting_service import (
    TreasuryTransferPostingService,
)
from seeker_accounting.modules.treasury.services.bank_statement_service import BankStatementService
from seeker_accounting.modules.treasury.services.bank_reconciliation_service import BankReconciliationService
from seeker_accounting.modules.inventory.services.item_category_service import ItemCategoryService
from seeker_accounting.modules.inventory.services.item_service import ItemService
from seeker_accounting.modules.inventory.services.inventory_document_service import InventoryDocumentService
from seeker_accounting.modules.inventory.services.inventory_location_service import InventoryLocationService
from seeker_accounting.modules.inventory.services.inventory_posting_service import InventoryPostingService
from seeker_accounting.modules.inventory.services.inventory_valuation_service import InventoryValuationService
from seeker_accounting.modules.inventory.services.unit_of_measure_service import UnitOfMeasureService
from seeker_accounting.modules.inventory.services.uom_category_service import UomCategoryService
from seeker_accounting.modules.fixed_assets.services.asset_category_service import AssetCategoryService
from seeker_accounting.modules.fixed_assets.services.asset_service import AssetService
from seeker_accounting.modules.fixed_assets.services.depreciation_schedule_service import DepreciationScheduleService
from seeker_accounting.modules.fixed_assets.services.depreciation_run_service import DepreciationRunService
from seeker_accounting.modules.fixed_assets.services.depreciation_posting_service import DepreciationPostingService
from seeker_accounting.modules.fixed_assets.services.depreciation_method_service import DepreciationMethodService
from seeker_accounting.modules.fixed_assets.services.asset_depreciation_settings_service import AssetDepreciationSettingsService
from seeker_accounting.modules.fixed_assets.services.asset_component_service import AssetComponentService
from seeker_accounting.modules.fixed_assets.services.asset_usage_service import AssetUsageService
from seeker_accounting.modules.fixed_assets.services.asset_depreciation_pool_service import AssetDepreciationPoolService
from seeker_accounting.modules.payroll.services.payroll_setup_service import PayrollSetupService
from seeker_accounting.modules.payroll.services.employee_service import EmployeeService
from seeker_accounting.modules.payroll.services.payroll_component_service import PayrollComponentService
from seeker_accounting.modules.payroll.services.payroll_rule_service import PayrollRuleService
from seeker_accounting.modules.payroll.services.cameroon_payroll_seed_service import CameroonPayrollSeedService
from seeker_accounting.modules.payroll.services.payroll_statutory_pack_service import PayrollStatutoryPackService
from seeker_accounting.modules.payroll.services.compensation_profile_service import CompensationProfileService
from seeker_accounting.modules.payroll.services.component_assignment_service import ComponentAssignmentService
from seeker_accounting.modules.payroll.services.payroll_input_service import PayrollInputService
from seeker_accounting.modules.payroll.services.payroll_validation_service import PayrollValidationService
from seeker_accounting.modules.payroll.services.payroll_project_allocation_service import (
    PayrollProjectAllocationService,
)
from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService
from seeker_accounting.modules.payroll.services.payroll_payslip_preview_service import PayrollPayslipPreviewService
from seeker_accounting.modules.payroll.services.payroll_calculation_service import PayrollCalculationService
from seeker_accounting.modules.payroll.services.payroll_posting_validation_service import PayrollPostingValidationService
from seeker_accounting.modules.payroll.services.payroll_posting_service import PayrollPostingService
from seeker_accounting.modules.payroll.services.payroll_payment_tracking_service import PayrollPaymentTrackingService
from seeker_accounting.modules.payroll.services.payroll_remittance_service import PayrollRemittanceService
from seeker_accounting.modules.payroll.services.payroll_summary_service import PayrollSummaryService
from seeker_accounting.modules.payroll.services.payroll_pack_version_service import PayrollPackVersionService
from seeker_accounting.modules.payroll.services.payroll_validation_dashboard_service import PayrollValidationDashboardService
from seeker_accounting.modules.payroll.services.payroll_import_service import PayrollImportService
from seeker_accounting.modules.payroll.services.payroll_print_service import PayrollPrintService
from seeker_accounting.modules.payroll.services.payroll_export_service import PayrollExportService
from seeker_accounting.modules.payroll.services.payroll_output_warning_service import PayrollOutputWarningService
from seeker_accounting.modules.payroll.services.payroll_remittance_deadline_service import PayrollRemittanceDeadlineService
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.dashboard.services.dashboard_service import DashboardService
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.administration.services.role_service import RoleService
from seeker_accounting.modules.administration.services.user_auth_service import UserAuthService
from seeker_accounting.modules.administration.services.user_avatar_service import UserAvatarService
from seeker_accounting.modules.administration.services.user_session_service import UserSessionService
from seeker_accounting.platform.code_suggestion import CodeSuggestionService
from seeker_accounting.platform.printing.print_engine import PrintEngine
from seeker_accounting.platform.session.session_idle_watcher_service import SessionIdleWatcherService
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager


@dataclass(slots=True)
class ServiceRegistry:
    settings: AppSettings
    app_context: AppContext
    session_context: SessionContext
    active_company_context: ActiveCompanyContext
    navigation_service: NavigationService
    workflow_resume_service: WorkflowResumeService
    theme_manager: ThemeManager
    session_idle_watcher_service: SessionIdleWatcherService
    user_auth_service: UserAuthService
    user_avatar_service: UserAvatarService
    user_session_service: UserSessionService
    company_service: CompanyService
    company_context_service: CompanyContextService
    company_logo_service: CompanyLogoService
    company_project_preference_service: CompanyProjectPreferenceService
    contract_service: ContractService
    contract_change_order_service: ContractChangeOrderService
    project_service: ProjectService
    project_structure_service: ProjectStructureService
    project_cost_code_service: ProjectCostCodeService
    project_budget_service: ProjectBudgetService
    budget_approval_service: BudgetApprovalService
    budget_control_service: BudgetControlService
    project_commitment_service: ProjectCommitmentService
    project_actual_cost_service: ProjectActualCostService
    project_profitability_service: ProjectProfitabilityService
    contract_reporting_service: ContractReportingService
    budget_reporting_service: BudgetReportingService
    stock_movement_report_service: StockMovementReportService
    stock_valuation_report_service: StockValuationReportService
    fixed_asset_register_service: FixedAssetRegisterService
    depreciation_report_service: DepreciationReportService
    financial_analysis_service: FinancialAnalysisService
    financial_analysis_chart_service: FinancialAnalysisChartService
    ratio_analysis_service: RatioAnalysisService
    working_capital_analysis_service: WorkingCapitalAnalysisService
    insight_rules_service: InsightRulesService
    interpretation_service: InterpretationService
    financial_analysis_workspace_service: FinancialAnalysisWorkspaceService
    balance_sheet_template_service: BalanceSheetTemplateService
    ias_balance_sheet_service: IasBalanceSheetService
    ias_income_statement_service: IasIncomeStatementService
    ias_income_statement_mapping_service: IasIncomeStatementMappingService
    ias_income_statement_template_service: IasIncomeStatementTemplateService
    trial_balance_report_service: TrialBalanceReportService
    general_ledger_report_service: GeneralLedgerReportService
    ar_aging_report_service: ARAgingReportService
    ap_aging_report_service: APAgingReportService
    customer_statement_service: CustomerStatementService
    supplier_statement_service: SupplierStatementService
    payroll_summary_report_service: PayrollSummaryReportService
    treasury_report_service: TreasuryReportService
    ohada_balance_sheet_service: OhadaBalanceSheetService
    ohada_income_statement_service: OhadaIncomeStatementService
    ohada_income_statement_template_service: OhadaIncomeStatementTemplateService
    balance_sheet_export_service: BalanceSheetExportService
    income_statement_export_service: IncomeStatementExportService
    project_dimension_validation_service: ProjectDimensionValidationService
    reference_data_service: ReferenceDataService
    tax_setup_service: TaxSetupService
    numbering_setup_service: NumberingSetupService
    chart_of_accounts_service: ChartOfAccountsService
    chart_seed_service: ChartSeedService
    chart_template_import_service: ChartTemplateImportService
    account_role_mapping_service: AccountRoleMappingService
    fiscal_calendar_service: FiscalCalendarService
    period_control_service: PeriodControlService
    journal_service: JournalService
    journal_posting_service: JournalPostingService
    company_seed_service: CompanySeedService
    customer_service: CustomerService
    supplier_service: SupplierService
    control_account_foundation_service: ControlAccountFoundationService
    financial_account_service: FinancialAccountService
    sales_invoice_service: SalesInvoiceService
    sales_invoice_posting_service: SalesInvoicePostingService
    customer_quote_service: CustomerQuoteService
    sales_order_service: SalesOrderService
    sales_credit_note_service: SalesCreditNoteService
    sales_credit_note_posting_service: SalesCreditNotePostingService
    customer_receipt_service: CustomerReceiptService
    customer_receipt_posting_service: CustomerReceiptPostingService
    purchase_order_service: PurchaseOrderService
    purchase_credit_note_service: PurchaseCreditNoteService
    purchase_credit_note_posting_service: PurchaseCreditNotePostingService
    purchase_bill_service: PurchaseBillService
    purchase_bill_posting_service: PurchaseBillPostingService
    supplier_payment_service: SupplierPaymentService
    supplier_payment_posting_service: SupplierPaymentPostingService
    treasury_transaction_service: TreasuryTransactionService
    treasury_transaction_posting_service: TreasuryTransactionPostingService
    treasury_transfer_service: TreasuryTransferService
    treasury_transfer_posting_service: TreasuryTransferPostingService
    bank_statement_service: BankStatementService
    bank_reconciliation_service: BankReconciliationService
    uom_category_service: UomCategoryService
    unit_of_measure_service: UnitOfMeasureService
    item_category_service: ItemCategoryService
    inventory_location_service: InventoryLocationService
    item_service: ItemService
    inventory_document_service: InventoryDocumentService
    inventory_posting_service: InventoryPostingService
    inventory_valuation_service: InventoryValuationService
    asset_category_service: AssetCategoryService
    asset_service: AssetService
    depreciation_schedule_service: DepreciationScheduleService
    depreciation_run_service: DepreciationRunService
    depreciation_posting_service: DepreciationPostingService
    depreciation_method_service: DepreciationMethodService
    asset_depreciation_settings_service: AssetDepreciationSettingsService
    asset_component_service: AssetComponentService
    asset_usage_service: AssetUsageService
    asset_depreciation_pool_service: AssetDepreciationPoolService
    payroll_setup_service: PayrollSetupService
    employee_service: EmployeeService
    payroll_component_service: PayrollComponentService
    payroll_rule_service: PayrollRuleService
    cameroon_payroll_seed_service: CameroonPayrollSeedService
    payroll_statutory_pack_service: PayrollStatutoryPackService
    compensation_profile_service: CompensationProfileService
    component_assignment_service: ComponentAssignmentService
    payroll_input_service: PayrollInputService
    payroll_validation_service: PayrollValidationService
    payroll_project_allocation_service: PayrollProjectAllocationService
    payroll_run_service: PayrollRunService
    payroll_payslip_preview_service: PayrollPayslipPreviewService
    payroll_calculation_service: PayrollCalculationService
    payroll_posting_validation_service: PayrollPostingValidationService
    payroll_posting_service: PayrollPostingService
    payroll_payment_tracking_service: PayrollPaymentTrackingService
    payroll_remittance_service: PayrollRemittanceService
    payroll_summary_service: PayrollSummaryService
    payroll_pack_version_service: PayrollPackVersionService
    payroll_validation_dashboard_service: PayrollValidationDashboardService
    payroll_import_service: PayrollImportService
    payroll_print_service: PayrollPrintService
    payroll_export_service: PayrollExportService
    payroll_output_warning_service: PayrollOutputWarningService
    payroll_remittance_deadline_service: PayrollRemittanceDeadlineService
    dashboard_service: DashboardService
    audit_service: AuditService
    permission_service: PermissionService
    role_service: RoleService
    code_suggestion_service: CodeSuggestionService
    print_engine: PrintEngine
    sales_invoice_print_service: SalesInvoicePrintService
    customer_receipt_print_service: CustomerReceiptPrintService
    purchase_bill_print_service: PurchaseBillPrintService
    supplier_payment_print_service: SupplierPaymentPrintService
    journal_entry_print_service: JournalEntryPrintService
    chart_of_accounts_print_service: ChartOfAccountsPrintService
    customer_print_service: CustomerPrintService
    supplier_print_service: SupplierPrintService
    financial_account_print_service: FinancialAccountPrintService
    treasury_transaction_print_service: TreasuryTransactionPrintService
    treasury_transfer_print_service: TreasuryTransferPrintService
    item_print_service: ItemPrintService
    inventory_document_print_service: InventoryDocumentPrintService
    asset_print_service: AssetPrintService
    depreciation_run_print_service: DepreciationRunPrintService
    audit_log_print_service: AuditLogPrintService
    backup_export_service: BackupExportService
    backup_analysis_service: BackupAnalysisService
    backup_merge_service: BackupMergeService
    license_service: LicenseService

