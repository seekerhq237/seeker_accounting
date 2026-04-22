from __future__ import annotations

from PySide6.QtWidgets import QApplication

from seeker_accounting.app.context.active_company_context import ActiveCompanyContext
from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.app.context.session_context import SessionContext
from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation.navigation_service import NavigationService
from seeker_accounting.app.navigation.workflow_resume_service import WorkflowResumeService
from seeker_accounting.config.settings import AppSettings
from seeker_accounting.db.engine import create_database_engine
from seeker_accounting.db.session import create_session_factory
from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
from seeker_accounting.platform.code_suggestion import CodeSuggestionService, EntityCodeConfig
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_of_accounts_service import (
    ChartOfAccountsService,
)
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_seed_service import (
    ChartSeedService,
)
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_template_import_service import (
    ChartTemplateImportService,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_loader import (
    ChartTemplateLoader,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_year_repository import (
    FiscalYearRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.services.fiscal_calendar_service import (
    FiscalCalendarService,
)
from seeker_accounting.modules.accounting.fiscal_periods.services.period_control_service import (
    PeriodControlService,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_line_repository import (
    JournalEntryLineRepository,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.accounting.journals.services.journal_posting_service import (
    JournalPostingService,
)
from seeker_accounting.modules.accounting.journals.services.journal_service import JournalService
from seeker_accounting.modules.accounting.reference_data.repositories.account_class_repository import (
    AccountClassRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_type_repository import (
    AccountTypeRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.accounting.reference_data.repositories.document_sequence_repository import (
    DocumentSequenceRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.payment_term_repository import (
    PaymentTermRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_account_mapping_repository import (
    TaxCodeAccountMappingRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_repository import TaxCodeRepository
from seeker_accounting.modules.accounting.reference_data.services.account_role_mapping_service import (
    AccountRoleMappingService,
)
from seeker_accounting.modules.accounting.reference_data.services.numbering_setup_service import (
    NumberingSetupService,
)
from seeker_accounting.modules.accounting.reference_data.services.reference_data_service import (
    ReferenceDataService,
)
from seeker_accounting.modules.accounting.reference_data.services.tax_setup_service import TaxSetupService
from seeker_accounting.modules.companies.repositories.company_fiscal_default_repository import (
    CompanyFiscalDefaultRepository,
)
from seeker_accounting.modules.companies.repositories.company_preference_repository import (
    CompanyPreferenceRepository,
)
from seeker_accounting.modules.companies.repositories.company_project_preference_repository import (
    CompanyProjectPreferenceRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.companies.services.company_context_service import CompanyContextService
from seeker_accounting.modules.companies.services.company_logo_service import CompanyLogoService
from seeker_accounting.modules.companies.services.company_project_preference_service import (
    CompanyProjectPreferenceService,
)
from seeker_accounting.modules.companies.services.company_seed_service import CompanySeedService
from seeker_accounting.modules.companies.services.company_service import CompanyService
from seeker_accounting.modules.contracts_projects.repositories.contract_change_order_repository import ContractChangeOrderRepository
from seeker_accounting.modules.contracts_projects.repositories.contract_repository import ContractRepository
from seeker_accounting.modules.contracts_projects.repositories.project_cost_code_repository import ProjectCostCodeRepository
from seeker_accounting.modules.contracts_projects.repositories.project_job_repository import ProjectJobRepository
from seeker_accounting.modules.contracts_projects.repositories.project_repository import ProjectRepository
from seeker_accounting.modules.contracts_projects.services.contract_change_order_service import ContractChangeOrderService
from seeker_accounting.modules.contracts_projects.services.contract_service import ContractService
from seeker_accounting.modules.contracts_projects.services.project_cost_code_service import ProjectCostCodeService
from seeker_accounting.modules.contracts_projects.services.project_service import ProjectService
from seeker_accounting.modules.contracts_projects.services.project_structure_service import ProjectStructureService
from seeker_accounting.modules.budgeting.repositories.project_budget_version_repository import ProjectBudgetVersionRepository
from seeker_accounting.modules.budgeting.repositories.project_budget_line_repository import ProjectBudgetLineRepository
from seeker_accounting.modules.budgeting.services.project_budget_service import ProjectBudgetService
from seeker_accounting.modules.budgeting.services.budget_approval_service import BudgetApprovalService
from seeker_accounting.modules.budgeting.services.budget_control_service import BudgetControlService
from seeker_accounting.modules.job_costing.repositories.project_commitment_repository import ProjectCommitmentRepository
from seeker_accounting.modules.job_costing.repositories.project_commitment_line_repository import (
    ProjectCommitmentLineRepository,
)
from seeker_accounting.modules.job_costing.repositories.project_actuals_query_repository import (
    ProjectActualsQueryRepository,
)
from seeker_accounting.modules.job_costing.repositories.project_profitability_query_repository import (
    ProjectProfitabilityQueryRepository,
)
from seeker_accounting.modules.job_costing.services.project_actual_cost_service import (
    ProjectActualCostService,
)
from seeker_accounting.modules.job_costing.services.project_commitment_service import ProjectCommitmentService
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.modules.job_costing.services.project_profitability_service import (
    ProjectProfitabilityService,
)
from seeker_accounting.modules.management_reporting.repositories.contract_reporting_repository import (
    ContractReportingRepository,
)
from seeker_accounting.modules.management_reporting.repositories.budget_reporting_repository import (
    BudgetReportingRepository,
)
from seeker_accounting.modules.management_reporting.services.contract_reporting_service import (
    ContractReportingService,
)
from seeker_accounting.modules.management_reporting.services.budget_reporting_service import (
    BudgetReportingService,
)
from seeker_accounting.modules.reporting.repositories.general_ledger_report_repository import (
    GeneralLedgerReportRepository,
)
from seeker_accounting.modules.reporting.repositories.ap_aging_report_repository import (
    APAgingReportRepository,
)
from seeker_accounting.modules.reporting.repositories.ar_aging_report_repository import (
    ARAgingReportRepository,
)
from seeker_accounting.modules.reporting.repositories.customer_statement_repository import (
    CustomerStatementRepository,
)
from seeker_accounting.modules.reporting.repositories.depreciation_report_repository import (
    DepreciationReportRepository,
)
from seeker_accounting.modules.reporting.repositories.financial_analysis_chart_repository import (
    FinancialAnalysisChartRepository,
)
from seeker_accounting.modules.reporting.repositories.financial_analysis_repository import (
    FinancialAnalysisRepository,
)
from seeker_accounting.modules.reporting.repositories.fixed_asset_register_repository import (
    FixedAssetRegisterRepository,
)
from seeker_accounting.modules.reporting.repositories.ias_balance_sheet_repository import (
    IasBalanceSheetRepository,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_mapping_repository import (
    IasIncomeStatementMappingRepository,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_repository import (
    IasIncomeStatementRepository,
)
from seeker_accounting.modules.reporting.repositories.ias_income_statement_preference_repository import (
    IasIncomeStatementPreferenceRepository,
)
from seeker_accounting.modules.reporting.repositories.ohada_income_statement_repository import (
    OhadaIncomeStatementRepository,
)
from seeker_accounting.modules.reporting.repositories.ohada_balance_sheet_repository import (
    OhadaBalanceSheetRepository,
)
from seeker_accounting.modules.reporting.repositories.payroll_summary_report_repository import (
    PayrollSummaryReportRepository,
)
from seeker_accounting.modules.reporting.repositories.stock_movement_report_repository import (
    StockMovementReportRepository,
)
from seeker_accounting.modules.reporting.repositories.supplier_statement_repository import (
    SupplierStatementRepository,
)
from seeker_accounting.modules.reporting.repositories.treasury_report_repository import (
    TreasuryReportRepository,
)
from seeker_accounting.modules.reporting.repositories.trial_balance_report_repository import (
    TrialBalanceReportRepository,
)
from seeker_accounting.modules.reporting.services.general_ledger_report_service import (
    GeneralLedgerReportService,
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
from seeker_accounting.modules.reporting.services.ohada_income_statement_service import (
    OhadaIncomeStatementService,
)
from seeker_accounting.modules.reporting.services.balance_sheet_export_service import (
    BalanceSheetExportService,
)
from seeker_accounting.modules.reporting.services.income_statement_export_service import (
    IncomeStatementExportService,
)
from seeker_accounting.modules.reporting.services.ohada_balance_sheet_service import (
    OhadaBalanceSheetService,
)
from seeker_accounting.modules.reporting.services.ohada_period_result_service import (
    OhadaPeriodResultService,
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
from seeker_accounting.modules.customers.repositories.customer_group_repository import (
    CustomerGroupRepository,
)
from seeker_accounting.modules.customers.repositories.customer_repository import CustomerRepository
from seeker_accounting.modules.customers.services.customer_service import CustomerService
from seeker_accounting.modules.parties.services.control_account_foundation_service import (
    ControlAccountFoundationService,
)
from seeker_accounting.modules.sales.repositories.customer_receipt_allocation_repository import (
    CustomerReceiptAllocationRepository,
)
from seeker_accounting.modules.sales.repositories.customer_receipt_repository import CustomerReceiptRepository
from seeker_accounting.modules.sales.repositories.customer_quote_line_repository import CustomerQuoteLineRepository
from seeker_accounting.modules.sales.repositories.customer_quote_repository import CustomerQuoteRepository
from seeker_accounting.modules.sales.repositories.sales_order_repository import SalesOrderRepository
from seeker_accounting.modules.sales.repositories.sales_order_line_repository import SalesOrderLineRepository
from seeker_accounting.modules.sales.repositories.sales_credit_note_repository import SalesCreditNoteRepository
from seeker_accounting.modules.sales.repositories.sales_credit_note_line_repository import SalesCreditNoteLineRepository
from seeker_accounting.modules.sales.repositories.sales_invoice_line_repository import SalesInvoiceLineRepository
from seeker_accounting.modules.sales.repositories.sales_invoice_repository import SalesInvoiceRepository
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
from seeker_accounting.modules.suppliers.repositories.supplier_group_repository import (
    SupplierGroupRepository,
)
from seeker_accounting.modules.purchases.repositories.purchase_bill_repository import PurchaseBillRepository
from seeker_accounting.modules.purchases.repositories.purchase_bill_line_repository import (
    PurchaseBillLineRepository,
)
from seeker_accounting.modules.purchases.repositories.purchase_order_repository import PurchaseOrderRepository
from seeker_accounting.modules.purchases.repositories.purchase_order_line_repository import (
    PurchaseOrderLineRepository,
)
from seeker_accounting.modules.purchases.repositories.purchase_credit_note_repository import PurchaseCreditNoteRepository
from seeker_accounting.modules.purchases.repositories.purchase_credit_note_line_repository import PurchaseCreditNoteLineRepository
from seeker_accounting.modules.purchases.repositories.supplier_payment_allocation_repository import (
    SupplierPaymentAllocationRepository,
)
from seeker_accounting.modules.purchases.repositories.supplier_payment_repository import SupplierPaymentRepository
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
from seeker_accounting.modules.purchases.services.purchase_bill_print_service import PurchaseBillPrintService
from seeker_accounting.modules.purchases.services.supplier_payment_print_service import SupplierPaymentPrintService
from seeker_accounting.modules.accounting.journals.services.journal_entry_print_service import JournalEntryPrintService
from seeker_accounting.modules.accounting.chart_of_accounts.services.chart_of_accounts_print_service import (
    ChartOfAccountsPrintService,
)
from seeker_accounting.modules.customers.services.customer_print_service import CustomerPrintService
from seeker_accounting.modules.suppliers.services.supplier_print_service import SupplierPrintService
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
from seeker_accounting.modules.suppliers.repositories.supplier_group_repository import (
    SupplierGroupRepository,
)
from seeker_accounting.modules.suppliers.repositories.supplier_repository import SupplierRepository
from seeker_accounting.modules.suppliers.services.supplier_service import SupplierService
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.modules.treasury.repositories.treasury_transaction_repository import (
    TreasuryTransactionRepository,
)
from seeker_accounting.modules.treasury.repositories.treasury_transaction_line_repository import (
    TreasuryTransactionLineRepository,
)
from seeker_accounting.modules.treasury.repositories.treasury_transfer_repository import TreasuryTransferRepository
from seeker_accounting.modules.treasury.repositories.bank_statement_import_batch_repository import (
    BankStatementImportBatchRepository,
)
from seeker_accounting.modules.treasury.repositories.bank_statement_line_repository import (
    BankStatementLineRepository,
)
from seeker_accounting.modules.treasury.repositories.bank_reconciliation_session_repository import (
    BankReconciliationSessionRepository,
)
from seeker_accounting.modules.treasury.repositories.bank_reconciliation_match_repository import (
    BankReconciliationMatchRepository,
)
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
from seeker_accounting.modules.inventory.repositories.item_category_repository import ItemCategoryRepository
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import InventoryDocumentRepository
from seeker_accounting.modules.inventory.repositories.inventory_document_line_repository import (
    InventoryDocumentLineRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_cost_layer_repository import (
    InventoryCostLayerRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_location_repository import InventoryLocationRepository
from seeker_accounting.modules.inventory.repositories.unit_of_measure_repository import UnitOfMeasureRepository
from seeker_accounting.modules.inventory.repositories.uom_category_repository import UomCategoryRepository
from seeker_accounting.modules.inventory.services.item_category_service import ItemCategoryService
from seeker_accounting.modules.inventory.services.item_service import ItemService
from seeker_accounting.modules.inventory.services.inventory_document_service import InventoryDocumentService
from seeker_accounting.modules.inventory.services.inventory_location_service import InventoryLocationService
from seeker_accounting.modules.inventory.services.uom_category_service import UomCategoryService
from seeker_accounting.modules.fixed_assets.repositories.asset_category_repository import AssetCategoryRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_repository import AssetRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_run_repository import (
    AssetDepreciationRunRepository,
)
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_run_line_repository import (
    AssetDepreciationRunLineRepository,
)
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
from seeker_accounting.modules.fixed_assets.repositories.depreciation_method_repository import DepreciationMethodRepository
from seeker_accounting.modules.fixed_assets.repositories.macrs_profile_repository import MacrsProfileRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_settings_repository import AssetDepreciationSettingsRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_component_repository import AssetComponentRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_usage_record_repository import AssetUsageRecordRepository
from seeker_accounting.modules.fixed_assets.repositories.asset_depreciation_pool_repository import AssetDepreciationPoolRepository
from seeker_accounting.modules.payroll.repositories.company_payroll_setting_repository import CompanyPayrollSettingRepository
from seeker_accounting.modules.payroll.repositories.department_repository import DepartmentRepository
from seeker_accounting.modules.payroll.repositories.position_repository import PositionRepository
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import PayrollComponentRepository
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import PayrollRuleSetRepository
from seeker_accounting.modules.payroll.services.payroll_setup_service import PayrollSetupService
from seeker_accounting.modules.payroll.services.employee_service import EmployeeService
from seeker_accounting.modules.payroll.services.payroll_component_service import PayrollComponentService
from seeker_accounting.modules.payroll.services.payroll_rule_service import PayrollRuleService
from seeker_accounting.modules.payroll.services.cameroon_payroll_seed_service import CameroonPayrollSeedService
from seeker_accounting.modules.payroll.services.payroll_statutory_pack_service import PayrollStatutoryPackService
from seeker_accounting.modules.payroll.repositories.compensation_profile_repository import CompensationProfileRepository
from seeker_accounting.modules.payroll.repositories.component_assignment_repository import ComponentAssignmentRepository
from seeker_accounting.modules.payroll.repositories.payroll_input_batch_repository import (
    PayrollInputBatchRepository,
    PayrollInputLineRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunRepository,
    PayrollRunEmployeeRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_employee_project_allocation_repository import (
    PayrollRunEmployeeProjectAllocationRepository,
)
from seeker_accounting.modules.payroll.services.compensation_profile_service import CompensationProfileService
from seeker_accounting.modules.payroll.services.component_assignment_service import ComponentAssignmentService
from seeker_accounting.modules.payroll.services.payroll_input_service import PayrollInputService
from seeker_accounting.modules.payroll.services.payroll_validation_service import PayrollValidationService
from seeker_accounting.modules.payroll.services.payroll_calculation_service import PayrollCalculationService
from seeker_accounting.modules.payroll.services.payroll_project_allocation_service import (
    PayrollProjectAllocationService,
)
from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService
from seeker_accounting.modules.payroll.services.payroll_payslip_preview_service import PayrollPayslipPreviewService
from seeker_accounting.modules.payroll.repositories.payroll_payment_record_repository import PayrollPaymentRecordRepository
from seeker_accounting.modules.payroll.repositories.payroll_remittance_repository import (
    PayrollRemittanceBatchRepository,
    PayrollRemittanceLineRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_summary_repository import PayrollSummaryRepository
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
from seeker_accounting.modules.audit.repositories.audit_event_repository import AuditEventRepository
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.administration.services.role_service import RoleService
from seeker_accounting.modules.administration.services.user_auth_service import UserAuthService
from seeker_accounting.modules.administration.repositories.user_repository import UserRepository
from seeker_accounting.modules.administration.repositories.user_role_repository import UserRoleRepository
from seeker_accounting.modules.administration.repositories.user_company_access_repository import (
    UserCompanyAccessRepository,
)
from seeker_accounting.modules.administration.repositories.permission_repository import PermissionRepository
from seeker_accounting.modules.administration.repositories.role_permission_repository import RolePermissionRepository
from seeker_accounting.modules.administration.repositories.role_repository import RoleRepository
from seeker_accounting.modules.administration.repositories.auth_lockout_repository import AuthLockoutRepository
from seeker_accounting.modules.administration.repositories.password_history_repository import PasswordHistoryRepository
from seeker_accounting.modules.inventory.services.inventory_posting_service import InventoryPostingService
from seeker_accounting.modules.inventory.services.inventory_valuation_service import InventoryValuationService
from seeker_accounting.modules.inventory.services.unit_of_measure_service import UnitOfMeasureService
from seeker_accounting.platform.numbering.numbering_service import NumberingService
from seeker_accounting.platform.printing.print_engine import PrintEngine
from seeker_accounting.platform.session.session_idle_watcher_service import SessionIdleWatcherService
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager


def create_app_context(settings: AppSettings) -> AppContext:
    return AppContext(
        current_user_id=None,
        current_user_display_name=settings.current_user_display_name,
        active_company_id=None,
        active_company_name=None,
        theme_name=settings.theme_name,
        permission_snapshot=tuple(),
    )


def create_session_context(settings: AppSettings) -> SessionContext:
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    unit_of_work_factory = create_unit_of_work_factory(session_factory)
    return SessionContext(
        engine=engine,
        session_factory=session_factory,
        unit_of_work_factory=unit_of_work_factory,
    )


def create_active_company_context(app_context: AppContext) -> ActiveCompanyContext:
    context = ActiveCompanyContext(
        company_id=app_context.active_company_id,
        company_name=app_context.active_company_name,
    )
    context.active_company_changed.connect(app_context.set_active_company)
    return context


def create_navigation_service() -> NavigationService:
    return NavigationService()


def create_workflow_resume_service() -> WorkflowResumeService:
    return WorkflowResumeService()


def create_theme_manager(qt_app: QApplication, settings: AppSettings, app_context: AppContext) -> ThemeManager:
    manager = ThemeManager(qt_app=qt_app, default_theme=settings.theme_name)
    manager.theme_changed.connect(app_context.set_theme)
    return manager


def create_session_idle_watcher_service(qt_app: QApplication) -> SessionIdleWatcherService:
    return SessionIdleWatcherService(qt_app=qt_app)


def create_company_context_service(
    app_context: AppContext,
    session_context: SessionContext,
    active_company_context: ActiveCompanyContext,
) -> CompanyContextService:
    return CompanyContextService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        active_company_context=active_company_context,
        company_repository_factory=CompanyRepository,
        user_company_access_repository_factory=UserCompanyAccessRepository,
    )


def create_company_service(
    session_context: SessionContext,
    company_context_service: CompanyContextService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> CompanyService:
    return CompanyService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        company_preference_repository_factory=CompanyPreferenceRepository,
        company_fiscal_default_repository_factory=CompanyFiscalDefaultRepository,
        country_repository_factory=CountryRepository,
        currency_repository_factory=CurrencyRepository,
        company_context_service=company_context_service,
        user_company_access_repository_factory=UserCompanyAccessRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_user_avatar_service(
    settings: AppSettings,
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> "UserAvatarService":
    from seeker_accounting.modules.administration.services.user_avatar_service import UserAvatarService
    from seeker_accounting.modules.administration.repositories.user_repository import UserRepository as _UR
    return UserAvatarService(
        settings=settings,
        unit_of_work_factory=session_context.unit_of_work_factory,
        user_repository_factory=_UR,
        audit_service=audit_service,
    )


def create_company_logo_service(
    settings: AppSettings,
    session_context: SessionContext,
    company_context_service: CompanyContextService,
    audit_service: AuditService | None = None,
) -> CompanyLogoService:
    return CompanyLogoService(
        settings=settings,
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        company_context_service=company_context_service,
        audit_service=audit_service,
    )


def create_system_admin_service(session_context: SessionContext) -> "SystemAdminService":
    from seeker_accounting.modules.companies.services.system_admin_service import SystemAdminService
    from seeker_accounting.modules.companies.repositories.system_admin_credential_repository import (
        SystemAdminCredentialRepository,
    )
    return SystemAdminService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        credential_repository_factory=SystemAdminCredentialRepository,
        auth_lockout_repository_factory=AuthLockoutRepository,
    )


def create_system_admin_company_service(
    session_context: SessionContext,
    company_context_service: CompanyContextService | None = None,
    audit_service: AuditService | None = None,
) -> "SystemAdminCompanyService":
    from seeker_accounting.modules.companies.services.system_admin_company_service import (
        SystemAdminCompanyService,
    )

    return SystemAdminCompanyService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        country_repository_factory=CountryRepository,
        currency_repository_factory=CurrencyRepository,
        company_context_service=company_context_service,
        audit_service=audit_service,
    )


def create_company_purge_service(session_context: SessionContext) -> "CompanyPurgeService":
    from seeker_accounting.modules.companies.services.company_purge_service import CompanyPurgeService
    return CompanyPurgeService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
    )


def create_company_project_preference_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> CompanyProjectPreferenceService:
    return CompanyProjectPreferenceService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_project_preference_repository_factory=CompanyProjectPreferenceRepository,
        company_repository_factory=CompanyRepository,
        audit_service=audit_service,
    )


def create_contract_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ContractService:
    return ContractService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        contract_repository_factory=ContractRepository,
        company_repository_factory=CompanyRepository,
        customer_repository_factory=CustomerRepository,
        currency_repository_factory=CurrencyRepository,
        change_order_repository_factory=ContractChangeOrderRepository,
        audit_service=audit_service,
    )


def create_contract_change_order_service(session_context: SessionContext) -> ContractChangeOrderService:
    return ContractChangeOrderService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        change_order_repository_factory=ContractChangeOrderRepository,
        contract_repository_factory=ContractRepository,
        company_repository_factory=CompanyRepository,
    )


def create_project_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ProjectService:
    return ProjectService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        project_repository_factory=ProjectRepository,
        contract_repository_factory=ContractRepository,
        company_repository_factory=CompanyRepository,
        customer_repository_factory=CustomerRepository,
        currency_repository_factory=CurrencyRepository,
        audit_service=audit_service,
    )


def create_project_structure_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ProjectStructureService:
    return ProjectStructureService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        project_job_repository_factory=ProjectJobRepository,
        project_repository_factory=ProjectRepository,
        audit_service=audit_service,
    )


def create_project_cost_code_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ProjectCostCodeService:
    return ProjectCostCodeService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        project_cost_code_repository_factory=ProjectCostCodeRepository,
        company_repository_factory=CompanyRepository,
        account_repository_factory=AccountRepository,
        audit_service=audit_service,
    )


def create_project_budget_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ProjectBudgetService:
    return ProjectBudgetService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        version_repository_factory=ProjectBudgetVersionRepository,
        line_repository_factory=ProjectBudgetLineRepository,
        project_repository_factory=ProjectRepository,
        project_job_repository_factory=ProjectJobRepository,
        project_cost_code_repository_factory=ProjectCostCodeRepository,
        audit_service=audit_service,
    )


def create_budget_approval_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> BudgetApprovalService:
    return BudgetApprovalService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        version_repository_factory=ProjectBudgetVersionRepository,
        line_repository_factory=ProjectBudgetLineRepository,
        audit_service=audit_service,
    )


def create_budget_control_service(session_context: SessionContext) -> BudgetControlService:
    return BudgetControlService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        version_repository_factory=ProjectBudgetVersionRepository,
        project_repository_factory=ProjectRepository,
    )


def create_project_commitment_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ProjectCommitmentService:
    return ProjectCommitmentService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        commitment_repository_factory=ProjectCommitmentRepository,
        commitment_line_repository_factory=ProjectCommitmentLineRepository,
        project_repository_factory=ProjectRepository,
        supplier_repository_factory=SupplierRepository,
        currency_repository_factory=CurrencyRepository,
        project_job_repository_factory=ProjectJobRepository,
        project_cost_code_repository_factory=ProjectCostCodeRepository,
        audit_service=audit_service,
    )


def create_project_actual_cost_service(session_context: SessionContext) -> ProjectActualCostService:
    return ProjectActualCostService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        project_repository_factory=ProjectRepository,
        actuals_query_repository_factory=ProjectActualsQueryRepository,
    )


def create_project_profitability_service(
    session_context: SessionContext,
) -> ProjectProfitabilityService:
    return ProjectProfitabilityService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        project_repository_factory=ProjectRepository,
        actuals_query_repository_factory=ProjectActualsQueryRepository,
        profitability_query_repository_factory=ProjectProfitabilityQueryRepository,
    )


def create_contract_reporting_service(
    session_context: SessionContext,
) -> ContractReportingService:
    return ContractReportingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        contract_repository_factory=ContractRepository,
        contract_reporting_repository_factory=ContractReportingRepository,
        actuals_query_repository_factory=ProjectActualsQueryRepository,
        profitability_query_repository_factory=ProjectProfitabilityQueryRepository,
    )


def create_budget_reporting_service(
    session_context: SessionContext,
) -> BudgetReportingService:
    return BudgetReportingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        project_repository_factory=ProjectRepository,
        actuals_query_repository_factory=ProjectActualsQueryRepository,
        profitability_query_repository_factory=ProjectProfitabilityQueryRepository,
        budget_reporting_repository_factory=BudgetReportingRepository,
    )


def create_trial_balance_report_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> TrialBalanceReportService:
    return TrialBalanceReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        trial_balance_repository_factory=TrialBalanceReportRepository,
        permission_service=permission_service,
    )


def create_general_ledger_report_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> GeneralLedgerReportService:
    return GeneralLedgerReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        ledger_repository_factory=GeneralLedgerReportRepository,
        permission_service=permission_service,
    )


def create_ar_aging_report_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> ARAgingReportService:
    return ARAgingReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        repository_factory=ARAgingReportRepository,
        permission_service=permission_service,
    )


def create_ap_aging_report_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> APAgingReportService:
    return APAgingReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        repository_factory=APAgingReportRepository,
        permission_service=permission_service,
    )


def create_customer_statement_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> CustomerStatementService:
    return CustomerStatementService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        repository_factory=CustomerStatementRepository,
        permission_service=permission_service,
    )


def create_supplier_statement_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> SupplierStatementService:
    return SupplierStatementService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        repository_factory=SupplierStatementRepository,
        permission_service=permission_service,
    )


def create_payroll_summary_report_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> PayrollSummaryReportService:
    return PayrollSummaryReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        repository_factory=PayrollSummaryReportRepository,
        permission_service=permission_service,
    )


def create_treasury_report_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> TreasuryReportService:
    return TreasuryReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        repository_factory=TreasuryReportRepository,
        permission_service=permission_service,
    )


def create_stock_movement_report_service(
    session_context: SessionContext,
) -> StockMovementReportService:
    return StockMovementReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        stock_movement_report_repository_factory=StockMovementReportRepository,
    )


def create_stock_valuation_report_service(
    session_context: SessionContext,
    inventory_valuation_service: InventoryValuationService,
) -> StockValuationReportService:
    return StockValuationReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        inventory_valuation_service=inventory_valuation_service,
    )


def create_fixed_asset_register_service(
    session_context: SessionContext,
) -> FixedAssetRegisterService:
    return FixedAssetRegisterService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        fixed_asset_register_repository_factory=FixedAssetRegisterRepository,
    )


def create_depreciation_report_service(
    session_context: SessionContext,
) -> DepreciationReportService:
    return DepreciationReportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        depreciation_report_repository_factory=DepreciationReportRepository,
    )


def create_financial_analysis_chart_service(
    session_context: SessionContext,
    ias_balance_sheet_service: IasBalanceSheetService,
) -> FinancialAnalysisChartService:
    return FinancialAnalysisChartService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        financial_analysis_chart_repository_factory=FinancialAnalysisChartRepository,
        ias_balance_sheet_service=ias_balance_sheet_service,
    )


def create_financial_analysis_service(
    session_context: SessionContext,
    ias_balance_sheet_service: IasBalanceSheetService,
    ias_income_statement_service: IasIncomeStatementService,
    ohada_income_statement_service: OhadaIncomeStatementService,
    ar_aging_report_service: ARAgingReportService,
    ap_aging_report_service: APAgingReportService,
    stock_valuation_report_service: StockValuationReportService,
) -> FinancialAnalysisService:
    return FinancialAnalysisService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        financial_analysis_repository_factory=FinancialAnalysisRepository,
        financial_analysis_chart_repository_factory=FinancialAnalysisChartRepository,
        ias_balance_sheet_service=ias_balance_sheet_service,
        ias_income_statement_service=ias_income_statement_service,
        ohada_income_statement_service=ohada_income_statement_service,
        ar_aging_report_service=ar_aging_report_service,
        ap_aging_report_service=ap_aging_report_service,
        stock_valuation_report_service=stock_valuation_report_service,
    )


def create_ratio_analysis_service() -> RatioAnalysisService:
    return RatioAnalysisService()


def create_working_capital_analysis_service() -> WorkingCapitalAnalysisService:
    return WorkingCapitalAnalysisService()


def create_insight_rules_service() -> InsightRulesService:
    return InsightRulesService()


def create_interpretation_service() -> InterpretationService:
    return InterpretationService()


def create_financial_analysis_workspace_service(
    financial_analysis_service: FinancialAnalysisService,
    ratio_analysis_service: RatioAnalysisService,
    working_capital_analysis_service: WorkingCapitalAnalysisService,
    insight_rules_service: InsightRulesService,
    interpretation_service: InterpretationService,
    permission_service: PermissionService,
) -> FinancialAnalysisWorkspaceService:
    return FinancialAnalysisWorkspaceService(
        financial_analysis_service=financial_analysis_service,
        ratio_analysis_service=ratio_analysis_service,
        working_capital_analysis_service=working_capital_analysis_service,
        insight_rules_service=insight_rules_service,
        interpretation_service=interpretation_service,
        permission_service=permission_service,
    )


def create_balance_sheet_template_service() -> BalanceSheetTemplateService:
    return BalanceSheetTemplateService()


def create_ohada_period_result_service(
    session_context: SessionContext,
) -> OhadaPeriodResultService:
    return OhadaPeriodResultService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        ohada_income_statement_repository_factory=OhadaIncomeStatementRepository,
    )


def create_ohada_balance_sheet_service(
    session_context: SessionContext,
    balance_sheet_template_service: BalanceSheetTemplateService,
    ohada_period_result_service: OhadaPeriodResultService,
    permission_service: PermissionService,
) -> OhadaBalanceSheetService:
    return OhadaBalanceSheetService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        ohada_balance_sheet_repository_factory=OhadaBalanceSheetRepository,
        balance_sheet_template_service=balance_sheet_template_service,
        ohada_period_result_service=ohada_period_result_service,
        permission_service=permission_service,
    )


def create_ias_balance_sheet_service(
    session_context: SessionContext,
    balance_sheet_template_service: BalanceSheetTemplateService,
    permission_service: PermissionService,
) -> IasBalanceSheetService:
    return IasBalanceSheetService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        ias_balance_sheet_repository_factory=IasBalanceSheetRepository,
        balance_sheet_template_service=balance_sheet_template_service,
        permission_service=permission_service,
    )


def create_ias_income_statement_template_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> IasIncomeStatementTemplateService:
    return IasIncomeStatementTemplateService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        ias_income_statement_repository_factory=IasIncomeStatementRepository,
        ias_income_statement_preference_repository_factory=IasIncomeStatementPreferenceRepository,
        permission_service=permission_service,
    )


def create_ias_income_statement_mapping_service(
    session_context: SessionContext,
    app_context: AppContext,
    ias_income_statement_template_service: IasIncomeStatementTemplateService,
    permission_service: PermissionService,
) -> IasIncomeStatementMappingService:
    return IasIncomeStatementMappingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        ias_income_statement_repository_factory=IasIncomeStatementRepository,
        ias_income_statement_mapping_repository_factory=IasIncomeStatementMappingRepository,
        ias_income_statement_template_service=ias_income_statement_template_service,
        permission_service=permission_service,
    )


def create_ias_income_statement_service(
    session_context: SessionContext,
    ias_income_statement_mapping_service: IasIncomeStatementMappingService,
    ias_income_statement_template_service: IasIncomeStatementTemplateService,
    permission_service: PermissionService,
) -> IasIncomeStatementService:
    return IasIncomeStatementService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        ias_income_statement_repository_factory=IasIncomeStatementRepository,
        ias_income_statement_mapping_service=ias_income_statement_mapping_service,
        ias_income_statement_template_service=ias_income_statement_template_service,
        permission_service=permission_service,
    )


def create_ohada_income_statement_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> OhadaIncomeStatementService:
    return OhadaIncomeStatementService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        ohada_income_statement_repository_factory=OhadaIncomeStatementRepository,
        permission_service=permission_service,
    )


def create_ohada_income_statement_template_service() -> OhadaIncomeStatementTemplateService:
    return OhadaIncomeStatementTemplateService()


def create_project_dimension_validation_service(
    session_context: SessionContext,
) -> ProjectDimensionValidationService:
    return ProjectDimensionValidationService(
        contract_repository_factory=ContractRepository,
        project_repository_factory=ProjectRepository,
        project_job_repository_factory=ProjectJobRepository,
        project_cost_code_repository_factory=ProjectCostCodeRepository,
    )


def create_reference_data_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> ReferenceDataService:
    return ReferenceDataService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        country_repository_factory=CountryRepository,
        currency_repository_factory=CurrencyRepository,
        account_class_repository_factory=AccountClassRepository,
        account_type_repository_factory=AccountTypeRepository,
        payment_term_repository_factory=PaymentTermRepository,
        company_repository_factory=CompanyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_tax_setup_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> TaxSetupService:
    return TaxSetupService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        tax_code_repository_factory=TaxCodeRepository,
        tax_code_account_mapping_repository_factory=TaxCodeAccountMappingRepository,
        account_repository_factory=AccountRepository,
        company_repository_factory=CompanyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_numbering_setup_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> NumberingSetupService:
    return NumberingSetupService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        document_sequence_repository_factory=DocumentSequenceRepository,
        company_repository_factory=CompanyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_chart_template_import_service(session_context: SessionContext) -> ChartTemplateImportService:
    return ChartTemplateImportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        account_repository_factory=AccountRepository,
        account_class_repository_factory=AccountClassRepository,
        account_type_repository_factory=AccountTypeRepository,
        template_loader=ChartTemplateLoader(),
    )


def create_chart_seed_service(
    session_context: SessionContext,
    chart_template_import_service: ChartTemplateImportService,
) -> ChartSeedService:
    return ChartSeedService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        account_class_repository_factory=AccountClassRepository,
        account_type_repository_factory=AccountTypeRepository,
        chart_template_import_service=chart_template_import_service,
    )


def create_chart_of_accounts_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> ChartOfAccountsService:
    return ChartOfAccountsService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        account_repository_factory=AccountRepository,
        account_class_repository_factory=AccountClassRepository,
        account_type_repository_factory=AccountTypeRepository,
        company_repository_factory=CompanyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_numbering_service() -> NumberingService:
    return NumberingService(
        document_sequence_repository_factory=DocumentSequenceRepository,
    )


def create_account_role_mapping_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> AccountRoleMappingService:
    return AccountRoleMappingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        account_repository_factory=AccountRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
        company_repository_factory=CompanyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_fiscal_calendar_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> FiscalCalendarService:
    return FiscalCalendarService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        fiscal_year_repository_factory=FiscalYearRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        company_repository_factory=CompanyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_period_control_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> PeriodControlService:
    return PeriodControlService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        fiscal_year_repository_factory=FiscalYearRepository,
        company_repository_factory=CompanyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_journal_service(session_context: SessionContext, app_context: AppContext) -> JournalService:
    return JournalService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        journal_entry_repository_factory=JournalEntryRepository,
        journal_entry_line_repository_factory=JournalEntryLineRepository,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        company_repository_factory=CompanyRepository,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
    )


def create_journal_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> JournalPostingService:
    return JournalPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        journal_entry_repository_factory=JournalEntryRepository,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_company_seed_service(chart_seed_service: ChartSeedService) -> CompanySeedService:
    return CompanySeedService(chart_seed_service)


def create_customer_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> CustomerService:
    return CustomerService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        country_repository_factory=CountryRepository,
        payment_term_repository_factory=PaymentTermRepository,
        customer_group_repository_factory=CustomerGroupRepository,
        customer_repository_factory=CustomerRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_supplier_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> SupplierService:
    return SupplierService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        country_repository_factory=CountryRepository,
        payment_term_repository_factory=PaymentTermRepository,
        supplier_group_repository_factory=SupplierGroupRepository,
        supplier_repository_factory=SupplierRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_control_account_foundation_service(
    session_context: SessionContext,
) -> ControlAccountFoundationService:
    return ControlAccountFoundationService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        account_repository_factory=AccountRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
    )


def create_financial_account_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> FinancialAccountService:
    return FinancialAccountService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        account_repository_factory=AccountRepository,
        currency_repository_factory=CurrencyRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_sales_invoice_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> SalesInvoiceService:
    return SalesInvoiceService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        customer_repository_factory=CustomerRepository,
        currency_repository_factory=CurrencyRepository,
        account_repository_factory=AccountRepository,
        tax_code_repository_factory=TaxCodeRepository,
        sales_invoice_repository_factory=SalesInvoiceRepository,
        sales_invoice_line_repository_factory=SalesInvoiceLineRepository,
        customer_receipt_allocation_repository_factory=CustomerReceiptAllocationRepository,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_sales_invoice_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> SalesInvoicePostingService:
    return SalesInvoicePostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        sales_invoice_repository_factory=SalesInvoiceRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
        tax_code_account_mapping_repository_factory=TaxCodeAccountMappingRepository,
        customer_receipt_allocation_repository_factory=CustomerReceiptAllocationRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_sales_order_service(
    session_context: SessionContext,
    sales_invoice_service: SalesInvoiceService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> SalesOrderService:
    return SalesOrderService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        customer_repository_factory=CustomerRepository,
        currency_repository_factory=CurrencyRepository,
        account_repository_factory=AccountRepository,
        tax_code_repository_factory=TaxCodeRepository,
        sales_order_repository_factory=SalesOrderRepository,
        sales_order_line_repository_factory=SalesOrderLineRepository,
        sales_invoice_repository_factory=SalesInvoiceRepository,
        sales_invoice_service=sales_invoice_service,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_sales_credit_note_service(
    session_context: SessionContext,
    app_context: AppContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> SalesCreditNoteService:
    return SalesCreditNoteService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        credit_note_repository_factory=SalesCreditNoteRepository,
        credit_note_line_repository_factory=SalesCreditNoteLineRepository,
        company_repository_factory=CompanyRepository,
        customer_repository_factory=CustomerRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_sales_credit_note_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> SalesCreditNotePostingService:
    return SalesCreditNotePostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        credit_note_repository_factory=SalesCreditNoteRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
        tax_code_account_mapping_repository_factory=TaxCodeAccountMappingRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_customer_quote_service(
    session_context: SessionContext,
    sales_invoice_service: SalesInvoiceService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> CustomerQuoteService:
    return CustomerQuoteService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        customer_repository_factory=CustomerRepository,
        currency_repository_factory=CurrencyRepository,
        account_repository_factory=AccountRepository,
        tax_code_repository_factory=TaxCodeRepository,
        customer_quote_repository_factory=CustomerQuoteRepository,
        customer_quote_line_repository_factory=CustomerQuoteLineRepository,
        sales_invoice_repository_factory=SalesInvoiceRepository,
        sales_invoice_service=sales_invoice_service,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_customer_receipt_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> CustomerReceiptService:
    return CustomerReceiptService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        customer_repository_factory=CustomerRepository,
        currency_repository_factory=CurrencyRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        sales_invoice_repository_factory=SalesInvoiceRepository,
        customer_receipt_repository_factory=CustomerReceiptRepository,
        customer_receipt_allocation_repository_factory=CustomerReceiptAllocationRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_customer_receipt_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    audit_service: AuditService | None = None,
) -> CustomerReceiptPostingService:
    return CustomerReceiptPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        customer_receipt_repository_factory=CustomerReceiptRepository,
        customer_receipt_allocation_repository_factory=CustomerReceiptAllocationRepository,
        sales_invoice_repository_factory=SalesInvoiceRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        audit_service=audit_service,
    )


def create_sales_invoice_print_service(
    print_engine: PrintEngine,
    sales_invoice_service: SalesInvoiceService,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> SalesInvoicePrintService:
    return SalesInvoicePrintService(
        print_engine=print_engine,
        sales_invoice_service=sales_invoice_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_customer_receipt_print_service(
    print_engine: PrintEngine,
    customer_receipt_service: CustomerReceiptService,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> CustomerReceiptPrintService:
    return CustomerReceiptPrintService(
        print_engine=print_engine,
        customer_receipt_service=customer_receipt_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_purchase_bill_print_service(
    print_engine: PrintEngine,
    purchase_bill_service: PurchaseBillService,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> PurchaseBillPrintService:
    return PurchaseBillPrintService(
        print_engine=print_engine,
        purchase_bill_service=purchase_bill_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_supplier_payment_print_service(
    print_engine: PrintEngine,
    supplier_payment_service: SupplierPaymentService,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> SupplierPaymentPrintService:
    return SupplierPaymentPrintService(
        print_engine=print_engine,
        supplier_payment_service=supplier_payment_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_journal_entry_print_service(
    print_engine: PrintEngine,
    journal_service: JournalService,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> JournalEntryPrintService:
    return JournalEntryPrintService(
        print_engine=print_engine,
        journal_service=journal_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_chart_of_accounts_print_service(
    print_engine: PrintEngine,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> ChartOfAccountsPrintService:
    return ChartOfAccountsPrintService(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_customer_print_service(
    print_engine: PrintEngine,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> CustomerPrintService:
    return CustomerPrintService(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_supplier_print_service(
    print_engine: PrintEngine,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> SupplierPrintService:
    return SupplierPrintService(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_financial_account_print_service(
    print_engine: PrintEngine,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> FinancialAccountPrintService:
    return FinancialAccountPrintService(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_treasury_transaction_print_service(
    print_engine: PrintEngine,
    treasury_transaction_service: TreasuryTransactionService,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> TreasuryTransactionPrintService:
    return TreasuryTransactionPrintService(
        print_engine=print_engine,
        treasury_transaction_service=treasury_transaction_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_treasury_transfer_print_service(
    print_engine: PrintEngine,
    treasury_transfer_service: TreasuryTransferService,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> TreasuryTransferPrintService:
    return TreasuryTransferPrintService(
        print_engine=print_engine,
        treasury_transfer_service=treasury_transfer_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_item_print_service(
    print_engine: PrintEngine,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> ItemPrintService:
    return ItemPrintService(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_inventory_document_print_service(
    print_engine: PrintEngine,
    inventory_document_service: InventoryDocumentService,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> InventoryDocumentPrintService:
    return InventoryDocumentPrintService(
        print_engine=print_engine,
        inventory_document_service=inventory_document_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_asset_print_service(
    print_engine: PrintEngine,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> AssetPrintService:
    return AssetPrintService(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_depreciation_run_print_service(
    print_engine: PrintEngine,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> DepreciationRunPrintService:
    return DepreciationRunPrintService(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_audit_log_print_service(
    print_engine: PrintEngine,
    company_service: CompanyService,
    company_logo_service: CompanyLogoService,
) -> AuditLogPrintService:
    return AuditLogPrintService(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )


def create_backup_export_service(
    settings: AppSettings,
    audit_service: AuditService | None = None,
) -> BackupExportService:
    return BackupExportService(settings=settings, audit_service=audit_service)


def create_backup_analysis_service(
    session_context: SessionContext,
) -> BackupAnalysisService:
    return BackupAnalysisService(
        unit_of_work_factory=session_context.unit_of_work_factory,
    )


def create_backup_merge_service(
    session_context: SessionContext,
    settings: AppSettings,
    audit_service: AuditService | None = None,
) -> BackupMergeService:
    return BackupMergeService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        settings=settings,
        audit_service=audit_service,
    )


def create_purchase_bill_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> PurchaseBillService:
    return PurchaseBillService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        supplier_repository_factory=SupplierRepository,
        currency_repository_factory=CurrencyRepository,
        account_repository_factory=AccountRepository,
        tax_code_repository_factory=TaxCodeRepository,
        purchase_bill_repository_factory=PurchaseBillRepository,
        purchase_bill_line_repository_factory=PurchaseBillLineRepository,
        supplier_payment_allocation_repository_factory=SupplierPaymentAllocationRepository,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_purchase_order_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    purchase_bill_service: PurchaseBillService,
    audit_service: AuditService | None = None,
) -> PurchaseOrderService:
    return PurchaseOrderService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        supplier_repository_factory=SupplierRepository,
        currency_repository_factory=CurrencyRepository,
        account_repository_factory=AccountRepository,
        tax_code_repository_factory=TaxCodeRepository,
        purchase_order_repository_factory=PurchaseOrderRepository,
        purchase_order_line_repository_factory=PurchaseOrderLineRepository,
        purchase_bill_repository_factory=PurchaseBillRepository,
        purchase_bill_service=purchase_bill_service,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_purchase_credit_note_service(
    session_context: SessionContext,
    app_context: AppContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> PurchaseCreditNoteService:
    return PurchaseCreditNoteService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        credit_note_repository_factory=PurchaseCreditNoteRepository,
        credit_note_line_repository_factory=PurchaseCreditNoteLineRepository,
        company_repository_factory=CompanyRepository,
        supplier_repository_factory=SupplierRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_purchase_credit_note_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> PurchaseCreditNotePostingService:
    return PurchaseCreditNotePostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        credit_note_repository_factory=PurchaseCreditNoteRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
        tax_code_account_mapping_repository_factory=TaxCodeAccountMappingRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_purchase_bill_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> PurchaseBillPostingService:
    return PurchaseBillPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        purchase_bill_repository_factory=PurchaseBillRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
        tax_code_account_mapping_repository_factory=TaxCodeAccountMappingRepository,
        supplier_payment_allocation_repository_factory=SupplierPaymentAllocationRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_supplier_payment_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> SupplierPaymentService:
    return SupplierPaymentService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        supplier_repository_factory=SupplierRepository,
        currency_repository_factory=CurrencyRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        purchase_bill_repository_factory=PurchaseBillRepository,
        supplier_payment_repository_factory=SupplierPaymentRepository,
        supplier_payment_allocation_repository_factory=SupplierPaymentAllocationRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_supplier_payment_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> SupplierPaymentPostingService:
    return SupplierPaymentPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        supplier_payment_repository_factory=SupplierPaymentRepository,
        supplier_payment_allocation_repository_factory=SupplierPaymentAllocationRepository,
        purchase_bill_repository_factory=PurchaseBillRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_treasury_transaction_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> TreasuryTransactionService:
    return TreasuryTransactionService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        account_repository_factory=AccountRepository,
        currency_repository_factory=CurrencyRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        treasury_transaction_repository_factory=TreasuryTransactionRepository,
        treasury_transaction_line_repository_factory=TreasuryTransactionLineRepository,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_treasury_transaction_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> TreasuryTransactionPostingService:
    return TreasuryTransactionPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        treasury_transaction_repository_factory=TreasuryTransactionRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_treasury_transfer_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> TreasuryTransferService:
    return TreasuryTransferService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        treasury_transfer_repository_factory=TreasuryTransferRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_treasury_transfer_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> TreasuryTransferPostingService:
    return TreasuryTransferPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        treasury_transfer_repository_factory=TreasuryTransferRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_bank_statement_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> BankStatementService:
    return BankStatementService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        bank_statement_import_batch_repository_factory=BankStatementImportBatchRepository,
        bank_statement_line_repository_factory=BankStatementLineRepository,
        audit_service=audit_service,
    )


def create_bank_reconciliation_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> BankReconciliationService:
    return BankReconciliationService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        financial_account_repository_factory=FinancialAccountRepository,
        bank_reconciliation_session_repository_factory=BankReconciliationSessionRepository,
        bank_reconciliation_match_repository_factory=BankReconciliationMatchRepository,
        bank_statement_line_repository_factory=BankStatementLineRepository,
        audit_service=audit_service,
    )


def create_uom_category_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> UomCategoryService:
    return UomCategoryService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        uom_category_repository_factory=UomCategoryRepository,
        audit_service=audit_service,
    )


def create_unit_of_measure_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> UnitOfMeasureService:
    return UnitOfMeasureService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        unit_of_measure_repository_factory=UnitOfMeasureRepository,
        uom_category_repository_factory=UomCategoryRepository,
        audit_service=audit_service,
    )


def create_item_category_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ItemCategoryService:
    return ItemCategoryService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        item_category_repository_factory=ItemCategoryRepository,
        audit_service=audit_service,
    )


def create_inventory_location_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> InventoryLocationService:
    return InventoryLocationService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        inventory_location_repository_factory=InventoryLocationRepository,
        audit_service=audit_service,
    )


def create_item_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ItemService:
    return ItemService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        item_repository_factory=ItemRepository,
        unit_of_measure_repository_factory=UnitOfMeasureRepository,
        item_category_repository_factory=ItemCategoryRepository,
        audit_service=audit_service,
    )


def create_inventory_document_service(session_context: SessionContext) -> InventoryDocumentService:
    return InventoryDocumentService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        item_repository_factory=ItemRepository,
        inventory_document_repository_factory=InventoryDocumentRepository,
        inventory_document_line_repository_factory=InventoryDocumentLineRepository,
        inventory_cost_layer_repository_factory=InventoryCostLayerRepository,
        inventory_location_repository_factory=InventoryLocationRepository,
        unit_of_measure_repository_factory=UnitOfMeasureRepository,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
    )


def create_inventory_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    audit_service: AuditService | None = None,
) -> InventoryPostingService:
    return InventoryPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        company_repository_factory=CompanyRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        inventory_document_repository_factory=InventoryDocumentRepository,
        item_repository_factory=ItemRepository,
        inventory_cost_layer_repository_factory=InventoryCostLayerRepository,
        numbering_service=numbering_service,
        audit_service=audit_service,
    )


def create_inventory_valuation_service(session_context: SessionContext) -> InventoryValuationService:
    return InventoryValuationService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        item_repository_factory=ItemRepository,
        inventory_cost_layer_repository_factory=InventoryCostLayerRepository,
    )


def create_asset_category_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> AssetCategoryService:
    return AssetCategoryService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        asset_category_repository_factory=AssetCategoryRepository,
        account_repository_factory=AccountRepository,
        company_repository_factory=CompanyRepository,
        audit_service=audit_service,
    )


def create_asset_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> AssetService:
    return AssetService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        asset_repository_factory=AssetRepository,
        asset_category_repository_factory=AssetCategoryRepository,
        company_repository_factory=CompanyRepository,
        supplier_repository_factory=SupplierRepository,
        audit_service=audit_service,
    )


def create_depreciation_schedule_service(session_context: SessionContext) -> DepreciationScheduleService:
    return DepreciationScheduleService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        asset_repository_factory=AssetRepository,
        settings_repository_factory=AssetDepreciationSettingsRepository,
        macrs_profile_repository_factory=MacrsProfileRepository,
    )


def create_depreciation_run_service(
    session_context: SessionContext,
    depreciation_schedule_service: DepreciationScheduleService,
    audit_service: AuditService | None = None,
) -> DepreciationRunService:
    return DepreciationRunService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        asset_repository_factory=AssetRepository,
        asset_depreciation_run_repository_factory=AssetDepreciationRunRepository,
        asset_depreciation_run_line_repository_factory=AssetDepreciationRunLineRepository,
        company_repository_factory=CompanyRepository,
        depreciation_schedule_service=depreciation_schedule_service,
        audit_service=audit_service,
    )


def create_depreciation_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    audit_service: AuditService | None = None,
) -> DepreciationPostingService:
    return DepreciationPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        asset_repository_factory=AssetRepository,
        asset_depreciation_run_repository_factory=AssetDepreciationRunRepository,
        asset_depreciation_run_line_repository_factory=AssetDepreciationRunLineRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=numbering_service,
        audit_service=audit_service,
    )


def create_depreciation_method_service(session_context: SessionContext) -> DepreciationMethodService:
    return DepreciationMethodService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        depreciation_method_repository_factory=DepreciationMethodRepository,
        macrs_profile_repository_factory=MacrsProfileRepository,
    )


def create_asset_depreciation_settings_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> AssetDepreciationSettingsService:
    return AssetDepreciationSettingsService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        settings_repository_factory=AssetDepreciationSettingsRepository,
        asset_repository_factory=AssetRepository,
        macrs_profile_repository_factory=MacrsProfileRepository,
        audit_service=audit_service,
    )


def create_asset_component_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> AssetComponentService:
    return AssetComponentService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        component_repository_factory=AssetComponentRepository,
        asset_repository_factory=AssetRepository,
        audit_service=audit_service,
    )


def create_asset_usage_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> AssetUsageService:
    return AssetUsageService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        usage_record_repository_factory=AssetUsageRecordRepository,
        asset_repository_factory=AssetRepository,
        audit_service=audit_service,
    )


def create_asset_depreciation_pool_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> AssetDepreciationPoolService:
    return AssetDepreciationPoolService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        pool_repository_factory=AssetDepreciationPoolRepository,
        asset_repository_factory=AssetRepository,
        company_repository_factory=CompanyRepository,
        audit_service=audit_service,
    )


def create_payroll_setup_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService,
) -> PayrollSetupService:
    return PayrollSetupService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        settings_repository_factory=CompanyPayrollSettingRepository,
        department_repository_factory=DepartmentRepository,
        position_repository_factory=PositionRepository,
        company_repository_factory=CompanyRepository,
        currency_repository_factory=CurrencyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_employee_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> EmployeeService:
    return EmployeeService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        employee_repository_factory=EmployeeRepository,
        department_repository_factory=DepartmentRepository,
        position_repository_factory=PositionRepository,
        company_repository_factory=CompanyRepository,
        currency_repository_factory=CurrencyRepository,
        audit_service=audit_service,
    )


def create_payroll_component_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> PayrollComponentService:
    return PayrollComponentService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        component_repository_factory=PayrollComponentRepository,
        company_repository_factory=CompanyRepository,
        account_repository_factory=AccountRepository,
        audit_service=audit_service,
    )


def create_payroll_rule_service(session_context: SessionContext) -> PayrollRuleService:
    return PayrollRuleService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        rule_set_repository_factory=PayrollRuleSetRepository,
        company_repository_factory=CompanyRepository,
    )


def create_cameroon_payroll_seed_service(session_context: SessionContext) -> CameroonPayrollSeedService:
    return CameroonPayrollSeedService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        component_repository_factory=PayrollComponentRepository,
        rule_set_repository_factory=PayrollRuleSetRepository,
    )


def create_payroll_statutory_pack_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService,
) -> PayrollStatutoryPackService:
    return PayrollStatutoryPackService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        settings_repository_factory=CompanyPayrollSettingRepository,
        component_repository_factory=PayrollComponentRepository,
        rule_set_repository_factory=PayrollRuleSetRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_compensation_profile_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> CompensationProfileService:
    return CompensationProfileService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        profile_repository_factory=CompensationProfileRepository,
        employee_repository_factory=EmployeeRepository,
        company_repository_factory=CompanyRepository,
        audit_service=audit_service,
    )


def create_component_assignment_service(
    session_context: SessionContext,
    audit_service: AuditService | None = None,
) -> ComponentAssignmentService:
    return ComponentAssignmentService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        assignment_repository_factory=ComponentAssignmentRepository,
        employee_repository_factory=EmployeeRepository,
        component_repository_factory=PayrollComponentRepository,
        audit_service=audit_service,
    )


def create_payroll_input_service(
    session_context: SessionContext,
    numbering_service: NumberingService,
) -> PayrollInputService:
    return PayrollInputService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        batch_repository_factory=PayrollInputBatchRepository,
        line_repository_factory=PayrollInputLineRepository,
        employee_repository_factory=EmployeeRepository,
        component_repository_factory=PayrollComponentRepository,
        numbering_service=numbering_service,
    )


def create_payroll_validation_service(session_context: SessionContext) -> PayrollValidationService:
    return PayrollValidationService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        employee_repository_factory=EmployeeRepository,
        profile_repository_factory=CompensationProfileRepository,
        assignment_repository_factory=ComponentAssignmentRepository,
    )


def create_payroll_project_allocation_service(
    session_context: SessionContext,
) -> PayrollProjectAllocationService:
    return PayrollProjectAllocationService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        run_repository_factory=PayrollRunRepository,
        run_employee_repository_factory=PayrollRunEmployeeRepository,
        allocation_repository_factory=PayrollRunEmployeeProjectAllocationRepository,
        project_dimension_validation_service=create_project_dimension_validation_service(session_context),
    )


def create_payroll_run_service(
    session_context: SessionContext,
    calculation_service: PayrollCalculationService,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService,
) -> PayrollRunService:
    return PayrollRunService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        run_repository_factory=PayrollRunRepository,
        run_employee_repository_factory=PayrollRunEmployeeRepository,
        employee_repository_factory=EmployeeRepository,
        profile_repository_factory=CompensationProfileRepository,
        assignment_repository_factory=ComponentAssignmentRepository,
        input_batch_repository_factory=PayrollInputBatchRepository,
        rule_set_repository_factory=PayrollRuleSetRepository,
        calculation_service=calculation_service,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_payroll_payslip_preview_service(
    payroll_run_service: PayrollRunService,
    session_context: SessionContext,
) -> PayrollPayslipPreviewService:
    return PayrollPayslipPreviewService(
        payroll_run_service=payroll_run_service,
        unit_of_work_factory=session_context.unit_of_work_factory,
        employee_repository_factory=EmployeeRepository,
        company_repository_factory=CompanyRepository,
        financial_account_repository_factory=FinancialAccountRepository,
    )


def create_payroll_posting_validation_service(
    session_context: SessionContext,
) -> PayrollPostingValidationService:
    return PayrollPostingValidationService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        run_repository_factory=PayrollRunRepository,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
    )


def create_payroll_posting_service(
    session_context: SessionContext,
    app_context: AppContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService,
) -> PayrollPostingService:
    return PayrollPostingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        run_repository_factory=PayrollRunRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_role_mapping_repository_factory=AccountRoleMappingRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_payroll_payment_tracking_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService,
) -> PayrollPaymentTrackingService:
    return PayrollPaymentTrackingService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        run_repository_factory=PayrollRunRepository,
        run_employee_repository_factory=PayrollRunEmployeeRepository,
        payment_record_repository_factory=PayrollPaymentRecordRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_payroll_remittance_service(
    session_context: SessionContext,
    numbering_service: NumberingService,
    permission_service: PermissionService,
    audit_service: AuditService,
) -> PayrollRemittanceService:
    return PayrollRemittanceService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        batch_repository_factory=PayrollRemittanceBatchRepository,
        line_repository_factory=PayrollRemittanceLineRepository,
        run_repository_factory=PayrollRunRepository,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_payroll_summary_service(
    session_context: SessionContext,
) -> PayrollSummaryService:
    return PayrollSummaryService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        run_repository_factory=PayrollRunRepository,
        summary_repository_factory=PayrollSummaryRepository,
    )


def create_payroll_pack_version_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService,
) -> PayrollPackVersionService:
    return PayrollPackVersionService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repository_factory=CompanyRepository,
        settings_repository_factory=CompanyPayrollSettingRepository,
        component_repository_factory=PayrollComponentRepository,
        rule_set_repository_factory=PayrollRuleSetRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_payroll_validation_dashboard_service(
    session_context: SessionContext,
    permission_service: PermissionService,
) -> PayrollValidationDashboardService:
    return PayrollValidationDashboardService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        settings_repo_factory=CompanyPayrollSettingRepository,
        employee_repo_factory=EmployeeRepository,
        profile_repo_factory=CompensationProfileRepository,
        assignment_repo_factory=ComponentAssignmentRepository,
        component_repo_factory=PayrollComponentRepository,
        rule_set_repo_factory=PayrollRuleSetRepository,
        fiscal_period_repo_factory=FiscalPeriodRepository,
        role_mapping_repo_factory=AccountRoleMappingRepository,
        account_repo_factory=AccountRepository,
        input_batch_repo_factory=PayrollInputBatchRepository,
        payment_record_repo_factory=PayrollPaymentRecordRepository,
        remittance_batch_repo_factory=PayrollRemittanceBatchRepository,
        run_repo_factory=PayrollRunRepository,
        run_employee_repo_factory=PayrollRunEmployeeRepository,
        permission_service=permission_service,
    )


def create_payroll_import_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService,
) -> PayrollImportService:
    return PayrollImportService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        department_repo_factory=DepartmentRepository,
        position_repo_factory=PositionRepository,
        employee_repo_factory=EmployeeRepository,
        component_repo_factory=PayrollComponentRepository,
        rule_set_repo_factory=PayrollRuleSetRepository,
        profile_repo_factory=CompensationProfileRepository,
        assignment_repo_factory=ComponentAssignmentRepository,
        account_repo_factory=AccountRepository,
        currency_repo_factory=CurrencyRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def create_payroll_print_service(
    session_context: SessionContext,
    payslip_preview_service: "PayrollPayslipPreviewService",
    run_service: "PayrollRunService",
    permission_service: PermissionService,
) -> PayrollPrintService:
    return PayrollPrintService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        company_repo_factory=CompanyRepository,
        payslip_preview_service=payslip_preview_service,
        run_service=run_service,
        permission_service=permission_service,
    )


def create_payroll_export_service(
    print_service: PayrollPrintService,
    permission_service: PermissionService,
    audit_service: "AuditService",
    company_logo_service: CompanyLogoService | None = None,
) -> PayrollExportService:
    return PayrollExportService(
        print_service=print_service,
        permission_service=permission_service,
        audit_service=audit_service,
        logo_resolver=company_logo_service.resolve_logo_path if company_logo_service else None,
    )


def create_payroll_output_warning_service(
    session_context: SessionContext,
) -> PayrollOutputWarningService:
    return PayrollOutputWarningService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        settings_repo_factory=CompanyPayrollSettingRepository,
    )


def create_payroll_remittance_deadline_service(
    session_context: SessionContext,
) -> PayrollRemittanceDeadlineService:
    return PayrollRemittanceDeadlineService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        batch_repo_factory=PayrollRemittanceBatchRepository,
    )


def create_audit_service(
    session_context: SessionContext,
    app_context: AppContext,
    permission_service: PermissionService,
) -> AuditService:
    return AuditService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        app_context=app_context,
        audit_event_repository_factory=AuditEventRepository,
        permission_service=permission_service,
    )


def create_permission_service(
    app_context: AppContext,
) -> PermissionService:
    return PermissionService(app_context=app_context)


def create_user_auth_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> UserAuthService:
    return UserAuthService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        user_repository_factory=UserRepository,
        role_repository_factory=RoleRepository,
        user_role_repository_factory=UserRoleRepository,
        user_company_access_repository_factory=UserCompanyAccessRepository,
        permission_repository_factory=PermissionRepository,
        permission_service=permission_service,
        company_repository_factory=CompanyRepository,
        company_preference_repository_factory=CompanyPreferenceRepository,
        password_history_repository_factory=PasswordHistoryRepository,
        auth_lockout_repository_factory=AuthLockoutRepository,
        audit_service=audit_service,
    )


def create_user_session_service(
    session_context: SessionContext,
    app_context: AppContext,
    audit_service: AuditService | None = None,
) -> "UserSessionService":
    from seeker_accounting.modules.administration.repositories.user_session_repository import (
        UserSessionRepository,
    )
    from seeker_accounting.modules.administration.services.user_session_service import (
        UserSessionService,
    )

    return UserSessionService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        user_session_repository_factory=UserSessionRepository,
        app_context=app_context,
        audit_service=audit_service,
    )


def create_role_service(
    session_context: SessionContext,
    permission_service: PermissionService,
    audit_service: AuditService | None = None,
) -> RoleService:
    return RoleService(
        unit_of_work_factory=session_context.unit_of_work_factory,
        role_repository_factory=RoleRepository,
        permission_repository_factory=PermissionRepository,
        role_permission_repository_factory=RolePermissionRepository,
        user_role_repository_factory=UserRoleRepository,
        permission_service=permission_service,
        audit_service=audit_service,
    )


def _register_code_suggestion_entities(svc: CodeSuggestionService) -> None:
    """Register all master-data entities that support smart code suggestion."""
    from seeker_accounting.modules.customers.models.customer import Customer
    from seeker_accounting.modules.suppliers.models.supplier import Supplier
    from seeker_accounting.modules.inventory.models.item import Item
    from seeker_accounting.modules.payroll.models.employee import Employee
    from seeker_accounting.modules.contracts_projects.models.contract import Contract
    from seeker_accounting.modules.contracts_projects.models.project import Project
    from seeker_accounting.modules.contracts_projects.models.project_job import ProjectJob
    from seeker_accounting.modules.contracts_projects.models.project_cost_code import ProjectCostCode
    from seeker_accounting.modules.fixed_assets.models.asset import Asset
    from seeker_accounting.modules.fixed_assets.models.asset_category import AssetCategory
    from seeker_accounting.modules.fixed_assets.models.asset_depreciation_pool import AssetDepreciationPool
    from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount
    from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
    from seeker_accounting.modules.accounting.reference_data.models.payment_term import PaymentTerm

    entities = [
        ("customer", Customer, "customer_code", "company_id", "CUST-"),
        ("supplier", Supplier, "supplier_code", "company_id", "SUP-"),
        ("item", Item, "item_code", "company_id", "ITEM-"),
        ("employee", Employee, "employee_number", "company_id", "EMP"),
        ("contract", Contract, "contract_number", "company_id", "CTR-"),
        ("project", Project, "project_code", "company_id", "PRJ-"),
        ("project_job", ProjectJob, "job_code", "project_id", "JOB-"),
        ("project_cost_code", ProjectCostCode, "code", "company_id", "CC-"),
        ("asset", Asset, "asset_number", "company_id", "AST-"),
        ("asset_category", AssetCategory, "code", "company_id", "ACAT-"),
        ("depreciation_pool", AssetDepreciationPool, "code", "company_id", "DPOOL-"),
        ("financial_account", FinancialAccount, "account_code", "company_id", "FA-"),
        ("tax_code", TaxCode, "code", "company_id", "TAX-"),
        ("payment_term", PaymentTerm, "code", "company_id", "PT-"),
    ]
    for key, model, code_attr, scope_attr, prefix in entities:
        svc.register_entity(key, EntityCodeConfig(
            model_class=model,
            code_attribute=code_attr,
            scope_attribute=scope_attr,
            default_prefix=prefix,
        ))


def create_service_registry(
    settings: AppSettings,
    app_context: AppContext,
    session_context: SessionContext,
    active_company_context: ActiveCompanyContext,
    navigation_service: NavigationService,
    theme_manager: ThemeManager,
    session_idle_watcher_service: SessionIdleWatcherService,
) -> ServiceRegistry:
    workflow_resume_service = create_workflow_resume_service()
    permission_service = create_permission_service(app_context=app_context)
    audit_service = create_audit_service(
        session_context=session_context,
        app_context=app_context,
        permission_service=permission_service,
    )
    user_auth_service = create_user_auth_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    role_service = create_role_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    user_session_service = create_user_session_service(
        session_context=session_context,
        app_context=app_context,
        audit_service=audit_service,
    )
    company_context_service = create_company_context_service(
        app_context=app_context,
        session_context=session_context,
        active_company_context=active_company_context,
    )
    company_service = create_company_service(
        session_context=session_context,
        company_context_service=company_context_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    company_logo_service = create_company_logo_service(
        settings=settings,
        session_context=session_context,
        company_context_service=company_context_service,
        audit_service=audit_service,
    )
    user_avatar_service = create_user_avatar_service(
        settings=settings,
        session_context=session_context,
        audit_service=audit_service,
    )
    company_project_preference_service = create_company_project_preference_service(session_context=session_context, audit_service=audit_service)
    reference_data_service = create_reference_data_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    tax_setup_service = create_tax_setup_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    numbering_setup_service = create_numbering_setup_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    chart_template_import_service = create_chart_template_import_service(session_context=session_context)
    chart_seed_service = create_chart_seed_service(
        session_context=session_context,
        chart_template_import_service=chart_template_import_service,
    )
    chart_of_accounts_service = create_chart_of_accounts_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    numbering_service = create_numbering_service()
    account_role_mapping_service = create_account_role_mapping_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    fiscal_calendar_service = create_fiscal_calendar_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    period_control_service = create_period_control_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    journal_service =create_journal_service(
        session_context=session_context, app_context=app_context,
    )
    journal_posting_service = create_journal_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    company_seed_service = create_company_seed_service(chart_seed_service)
    customer_service = create_customer_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    supplier_service = create_supplier_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    control_account_foundation_service = create_control_account_foundation_service(
        session_context=session_context,
    )
    financial_account_service = create_financial_account_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    sales_invoice_service = create_sales_invoice_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    sales_invoice_posting_service = create_sales_invoice_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    customer_quote_service = create_customer_quote_service(
        session_context=session_context,
        sales_invoice_service=sales_invoice_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    sales_order_service = create_sales_order_service(
        session_context=session_context,
        sales_invoice_service=sales_invoice_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    sales_credit_note_service = create_sales_credit_note_service(
        session_context=session_context,
        app_context=app_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    sales_credit_note_posting_service = create_sales_credit_note_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    customer_receipt_service = create_customer_receipt_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    customer_receipt_posting_service = create_customer_receipt_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        audit_service=audit_service,
    )
    purchase_bill_service = create_purchase_bill_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    purchase_order_service = create_purchase_order_service(
        session_context=session_context,
        permission_service=permission_service,
        purchase_bill_service=purchase_bill_service,
        audit_service=audit_service,
    )
    purchase_credit_note_service = create_purchase_credit_note_service(
        session_context=session_context,
        app_context=app_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    purchase_credit_note_posting_service = create_purchase_credit_note_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    purchase_bill_posting_service = create_purchase_bill_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    supplier_payment_service = create_supplier_payment_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    supplier_payment_posting_service = create_supplier_payment_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    treasury_transaction_service = create_treasury_transaction_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    treasury_transaction_posting_service = create_treasury_transaction_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    treasury_transfer_service = create_treasury_transfer_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    treasury_transfer_posting_service = create_treasury_transfer_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    bank_statement_service =create_bank_statement_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    bank_reconciliation_service =create_bank_reconciliation_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    uom_category_service =create_uom_category_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    unit_of_measure_service =create_unit_of_measure_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    item_category_service =create_item_category_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    inventory_location_service =create_inventory_location_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    item_service =create_item_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    inventory_document_service =create_inventory_document_service(
        session_context=session_context,
    )
    inventory_posting_service = create_inventory_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        audit_service=audit_service,
    )
    inventory_valuation_service = create_inventory_valuation_service(session_context=session_context)
    asset_category_service =create_asset_category_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    asset_service =create_asset_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    depreciation_schedule_service = create_depreciation_schedule_service(session_context=session_context)
    depreciation_run_service = create_depreciation_run_service(
        session_context=session_context,
        depreciation_schedule_service=depreciation_schedule_service,
        audit_service=audit_service,
    )
    depreciation_posting_service = create_depreciation_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        audit_service=audit_service,
    )
    depreciation_method_service = create_depreciation_method_service(session_context=session_context)
    asset_depreciation_settings_service = create_asset_depreciation_settings_service(session_context=session_context, audit_service=audit_service)
    asset_component_service = create_asset_component_service(session_context=session_context, audit_service=audit_service)
    asset_usage_service = create_asset_usage_service(session_context=session_context, audit_service=audit_service)
    asset_depreciation_pool_service = create_asset_depreciation_pool_service(session_context=session_context, audit_service=audit_service)
    payroll_setup_service = create_payroll_setup_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    employee_service = create_employee_service(session_context=session_context, audit_service=audit_service)
    payroll_component_service = create_payroll_component_service(session_context=session_context, audit_service=audit_service)
    payroll_rule_service = create_payroll_rule_service(session_context=session_context)
    cameroon_payroll_seed_service = create_cameroon_payroll_seed_service(session_context=session_context)
    payroll_statutory_pack_service = create_payroll_statutory_pack_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    compensation_profile_service = create_compensation_profile_service(session_context=session_context, audit_service=audit_service)
    component_assignment_service = create_component_assignment_service(session_context=session_context, audit_service=audit_service)
    payroll_input_service = create_payroll_input_service(
        session_context=session_context,
        numbering_service=numbering_service,
    )
    payroll_validation_service = create_payroll_validation_service(session_context=session_context)
    payroll_project_allocation_service = create_payroll_project_allocation_service(
        session_context=session_context,
    )
    payroll_calculation_service = PayrollCalculationService()
    payroll_run_service = create_payroll_run_service(
        session_context=session_context,
        calculation_service=payroll_calculation_service,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    payroll_payslip_preview_service = create_payroll_payslip_preview_service(
        payroll_run_service=payroll_run_service,
        session_context=session_context,
    )
    payroll_posting_validation_service = create_payroll_posting_validation_service(
        session_context=session_context,
    )
    payroll_posting_service = create_payroll_posting_service(
        session_context=session_context,
        app_context=app_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    payroll_payment_tracking_service = create_payroll_payment_tracking_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    payroll_remittance_service = create_payroll_remittance_service(
        session_context=session_context,
        numbering_service=numbering_service,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    payroll_summary_service = create_payroll_summary_service(session_context=session_context)
    payroll_pack_version_service = create_payroll_pack_version_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    payroll_validation_dashboard_service = create_payroll_validation_dashboard_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    payroll_import_service = create_payroll_import_service(
        session_context=session_context,
        permission_service=permission_service,
        audit_service=audit_service,
    )
    # -- Print engine (stateless PDF/Word/Excel renderer) --------------------
    print_engine = PrintEngine()
    payroll_print_service = create_payroll_print_service(
        session_context=session_context,
        payslip_preview_service=payroll_payslip_preview_service,
        run_service=payroll_run_service,
        permission_service=permission_service,
    )
    payroll_export_service = create_payroll_export_service(
        print_service=payroll_print_service,
        permission_service=permission_service,
        audit_service=audit_service,
        company_logo_service=company_logo_service,
    )
    payroll_output_warning_service = create_payroll_output_warning_service(
        session_context=session_context,
    )
    payroll_remittance_deadline_service = create_payroll_remittance_deadline_service(
        session_context=session_context,
    )
    company_project_preference_service = create_company_project_preference_service(session_context=session_context, audit_service=audit_service)
    contract_service =create_contract_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    contract_change_order_service = create_contract_change_order_service(session_context=session_context)
    project_service =create_project_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    project_structure_service = create_project_structure_service(session_context=session_context, audit_service=audit_service)
    project_cost_code_service = create_project_cost_code_service(session_context=session_context, audit_service=audit_service)
    project_budget_service =create_project_budget_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    budget_approval_service =create_budget_approval_service(
        session_context=session_context,
        audit_service=audit_service,
    )
    budget_control_service = create_budget_control_service(session_context=session_context)
    project_commitment_service = create_project_commitment_service(session_context=session_context, audit_service=audit_service)
    project_actual_cost_service = create_project_actual_cost_service(session_context=session_context)
    project_profitability_service = create_project_profitability_service(session_context=session_context)
    contract_reporting_service = create_contract_reporting_service(session_context=session_context)
    budget_reporting_service = create_budget_reporting_service(session_context=session_context)
    balance_sheet_template_service = create_balance_sheet_template_service()
    ias_income_statement_template_service = create_ias_income_statement_template_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    ias_income_statement_mapping_service = create_ias_income_statement_mapping_service(
        session_context=session_context,
        app_context=app_context,
        ias_income_statement_template_service=ias_income_statement_template_service,
        permission_service=permission_service,
    )
    ias_balance_sheet_service = create_ias_balance_sheet_service(
        session_context=session_context,
        balance_sheet_template_service=balance_sheet_template_service,
        permission_service=permission_service,
    )
    ias_income_statement_service = create_ias_income_statement_service(
        session_context=session_context,
        ias_income_statement_mapping_service=ias_income_statement_mapping_service,
        ias_income_statement_template_service=ias_income_statement_template_service,
        permission_service=permission_service,
    )
    trial_balance_report_service = create_trial_balance_report_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    general_ledger_report_service = create_general_ledger_report_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    ar_aging_report_service = create_ar_aging_report_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    ap_aging_report_service = create_ap_aging_report_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    customer_statement_service = create_customer_statement_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    supplier_statement_service = create_supplier_statement_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    payroll_summary_report_service = create_payroll_summary_report_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    treasury_report_service = create_treasury_report_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    stock_movement_report_service = create_stock_movement_report_service(session_context=session_context)
    stock_valuation_report_service = create_stock_valuation_report_service(
        session_context=session_context,
        inventory_valuation_service=inventory_valuation_service,
    )
    fixed_asset_register_service = create_fixed_asset_register_service(session_context=session_context)
    depreciation_report_service = create_depreciation_report_service(session_context=session_context)
    ohada_period_result_service = create_ohada_period_result_service(session_context=session_context)
    ohada_balance_sheet_service = create_ohada_balance_sheet_service(
        session_context=session_context,
        balance_sheet_template_service=balance_sheet_template_service,
        ohada_period_result_service=ohada_period_result_service,
        permission_service=permission_service,
    )
    ohada_income_statement_service = create_ohada_income_statement_service(
        session_context=session_context,
        permission_service=permission_service,
    )
    balance_sheet_export_service = BalanceSheetExportService(
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    income_statement_export_service = IncomeStatementExportService(
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    financial_analysis_chart_service = create_financial_analysis_chart_service(
        session_context=session_context,
        ias_balance_sheet_service=ias_balance_sheet_service,
    )
    financial_analysis_service = create_financial_analysis_service(
        session_context=session_context,
        ias_balance_sheet_service=ias_balance_sheet_service,
        ias_income_statement_service=ias_income_statement_service,
        ohada_income_statement_service=ohada_income_statement_service,
        ar_aging_report_service=ar_aging_report_service,
        ap_aging_report_service=ap_aging_report_service,
        stock_valuation_report_service=stock_valuation_report_service,
    )
    ratio_analysis_service = create_ratio_analysis_service()
    working_capital_analysis_service = create_working_capital_analysis_service()
    insight_rules_service = create_insight_rules_service()
    interpretation_service = create_interpretation_service()
    financial_analysis_workspace_service = create_financial_analysis_workspace_service(
        financial_analysis_service=financial_analysis_service,
        ratio_analysis_service=ratio_analysis_service,
        working_capital_analysis_service=working_capital_analysis_service,
        insight_rules_service=insight_rules_service,
        interpretation_service=interpretation_service,
        permission_service=permission_service,
    )
    ohada_income_statement_template_service = create_ohada_income_statement_template_service()
    project_dimension_validation_service = create_project_dimension_validation_service(session_context=session_context)

    from seeker_accounting.modules.dashboard.services.dashboard_service import DashboardService
    dashboard_service = DashboardService(
        journal_service=journal_service,
        sales_invoice_service=sales_invoice_service,
        purchase_bill_service=purchase_bill_service,
        ar_aging_report_service=ar_aging_report_service,
        ap_aging_report_service=ap_aging_report_service,
        treasury_report_service=treasury_report_service,
        fiscal_calendar_service=fiscal_calendar_service,
        inventory_valuation_service=inventory_valuation_service,
        unit_of_work_factory=session_context.unit_of_work_factory,
    )

    # -- Code suggestion service (smart auto-suggest for entity codes) ------
    code_suggestion_service = CodeSuggestionService(
        unit_of_work_factory=session_context.unit_of_work_factory,
    )
    _register_code_suggestion_entities(code_suggestion_service)

    # -- Print engine (stateless PDF/Word/Excel renderer) --------------------
    print_engine = PrintEngine()
    sales_invoice_print_service = create_sales_invoice_print_service(
        print_engine=print_engine,
        sales_invoice_service=sales_invoice_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    customer_receipt_print_service = create_customer_receipt_print_service(
        print_engine=print_engine,
        customer_receipt_service=customer_receipt_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    purchase_bill_print_service = create_purchase_bill_print_service(
        print_engine=print_engine,
        purchase_bill_service=purchase_bill_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    supplier_payment_print_service = create_supplier_payment_print_service(
        print_engine=print_engine,
        supplier_payment_service=supplier_payment_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    journal_entry_print_service = create_journal_entry_print_service(
        print_engine=print_engine,
        journal_service=journal_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    chart_of_accounts_print_service = create_chart_of_accounts_print_service(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    customer_print_service = create_customer_print_service(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    supplier_print_service = create_supplier_print_service(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    financial_account_print_service = create_financial_account_print_service(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    treasury_transaction_print_service = create_treasury_transaction_print_service(
        print_engine=print_engine,
        treasury_transaction_service=treasury_transaction_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    treasury_transfer_print_service = create_treasury_transfer_print_service(
        print_engine=print_engine,
        treasury_transfer_service=treasury_transfer_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    item_print_service = create_item_print_service(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    inventory_document_print_service = create_inventory_document_print_service(
        print_engine=print_engine,
        inventory_document_service=inventory_document_service,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    asset_print_service = create_asset_print_service(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    depreciation_run_print_service = create_depreciation_run_print_service(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    audit_log_print_service = create_audit_log_print_service(
        print_engine=print_engine,
        company_service=company_service,
        company_logo_service=company_logo_service,
    )
    backup_export_service = create_backup_export_service(settings=settings, audit_service=audit_service)
    backup_analysis_service = create_backup_analysis_service(session_context=session_context)
    backup_merge_service = create_backup_merge_service(
        session_context=session_context,
        settings=settings,
        audit_service=audit_service,
    )

    from seeker_accounting.platform.licensing.license_service import LicenseService
    license_service = LicenseService(settings=settings)

    return ServiceRegistry(
        settings=settings,
        app_context=app_context,
        session_context=session_context,
        active_company_context=active_company_context,
        navigation_service=navigation_service,
        workflow_resume_service=workflow_resume_service,
        theme_manager=theme_manager,
        session_idle_watcher_service=session_idle_watcher_service,
        user_auth_service=user_auth_service,
        user_avatar_service=user_avatar_service,
        user_session_service=user_session_service,
        company_service=company_service,
        company_context_service=company_context_service,
        company_logo_service=company_logo_service,
        company_project_preference_service=company_project_preference_service,
        contract_service=contract_service,
        contract_change_order_service=contract_change_order_service,
        project_service=project_service,
        project_structure_service=project_structure_service,
        project_cost_code_service=project_cost_code_service,
        project_budget_service=project_budget_service,
        budget_approval_service=budget_approval_service,
        budget_control_service=budget_control_service,
        project_commitment_service=project_commitment_service,
        project_actual_cost_service=project_actual_cost_service,
        project_profitability_service=project_profitability_service,
        contract_reporting_service=contract_reporting_service,
        budget_reporting_service=budget_reporting_service,
        stock_movement_report_service=stock_movement_report_service,
        stock_valuation_report_service=stock_valuation_report_service,
        fixed_asset_register_service=fixed_asset_register_service,
        depreciation_report_service=depreciation_report_service,
        financial_analysis_service=financial_analysis_service,
        financial_analysis_chart_service=financial_analysis_chart_service,
        ratio_analysis_service=ratio_analysis_service,
        working_capital_analysis_service=working_capital_analysis_service,
        insight_rules_service=insight_rules_service,
        interpretation_service=interpretation_service,
        financial_analysis_workspace_service=financial_analysis_workspace_service,
        balance_sheet_template_service=balance_sheet_template_service,
        ias_balance_sheet_service=ias_balance_sheet_service,
        ias_income_statement_service=ias_income_statement_service,
        ias_income_statement_mapping_service=ias_income_statement_mapping_service,
        ias_income_statement_template_service=ias_income_statement_template_service,
        trial_balance_report_service=trial_balance_report_service,
        general_ledger_report_service=general_ledger_report_service,
        ar_aging_report_service=ar_aging_report_service,
        ap_aging_report_service=ap_aging_report_service,
        customer_statement_service=customer_statement_service,
        supplier_statement_service=supplier_statement_service,
        payroll_summary_report_service=payroll_summary_report_service,
        treasury_report_service=treasury_report_service,
        ohada_balance_sheet_service=ohada_balance_sheet_service,
        ohada_income_statement_service=ohada_income_statement_service,
        ohada_income_statement_template_service=ohada_income_statement_template_service,
        balance_sheet_export_service=balance_sheet_export_service,
        income_statement_export_service=income_statement_export_service,
        project_dimension_validation_service=project_dimension_validation_service,
        reference_data_service=reference_data_service,
        tax_setup_service=tax_setup_service,
        numbering_setup_service=numbering_setup_service,
        chart_of_accounts_service=chart_of_accounts_service,
        chart_seed_service=chart_seed_service,
        chart_template_import_service=chart_template_import_service,
        account_role_mapping_service=account_role_mapping_service,
        fiscal_calendar_service=fiscal_calendar_service,
        period_control_service=period_control_service,
        journal_service=journal_service,
        journal_posting_service=journal_posting_service,
        company_seed_service=company_seed_service,
        customer_service=customer_service,
        supplier_service=supplier_service,
        control_account_foundation_service=control_account_foundation_service,
        financial_account_service=financial_account_service,
        sales_invoice_service=sales_invoice_service,
        sales_invoice_posting_service=sales_invoice_posting_service,
        customer_quote_service=customer_quote_service,
        sales_order_service=sales_order_service,
        sales_credit_note_service=sales_credit_note_service,
        sales_credit_note_posting_service=sales_credit_note_posting_service,
        customer_receipt_service=customer_receipt_service,
        customer_receipt_posting_service=customer_receipt_posting_service,
        purchase_order_service=purchase_order_service,
        purchase_credit_note_service=purchase_credit_note_service,
        purchase_credit_note_posting_service=purchase_credit_note_posting_service,
        purchase_bill_service=purchase_bill_service,
        purchase_bill_posting_service=purchase_bill_posting_service,
        supplier_payment_service=supplier_payment_service,
        supplier_payment_posting_service=supplier_payment_posting_service,
        treasury_transaction_service=treasury_transaction_service,
        treasury_transaction_posting_service=treasury_transaction_posting_service,
        treasury_transfer_service=treasury_transfer_service,
        treasury_transfer_posting_service=treasury_transfer_posting_service,
        bank_statement_service=bank_statement_service,
        bank_reconciliation_service=bank_reconciliation_service,
        uom_category_service=uom_category_service,
        unit_of_measure_service=unit_of_measure_service,
        item_category_service=item_category_service,
        inventory_location_service=inventory_location_service,
        item_service=item_service,
        inventory_document_service=inventory_document_service,
        inventory_posting_service=inventory_posting_service,
        inventory_valuation_service=inventory_valuation_service,
        asset_category_service=asset_category_service,
        asset_service=asset_service,
        depreciation_schedule_service=depreciation_schedule_service,
        depreciation_run_service=depreciation_run_service,
        depreciation_posting_service=depreciation_posting_service,
        depreciation_method_service=depreciation_method_service,
        asset_depreciation_settings_service=asset_depreciation_settings_service,
        asset_component_service=asset_component_service,
        asset_usage_service=asset_usage_service,
        asset_depreciation_pool_service=asset_depreciation_pool_service,
        payroll_setup_service=payroll_setup_service,
        employee_service=employee_service,
        payroll_component_service=payroll_component_service,
        payroll_rule_service=payroll_rule_service,
        cameroon_payroll_seed_service=cameroon_payroll_seed_service,
        payroll_statutory_pack_service=payroll_statutory_pack_service,
        compensation_profile_service=compensation_profile_service,
        component_assignment_service=component_assignment_service,
        payroll_input_service=payroll_input_service,
        payroll_validation_service=payroll_validation_service,
        payroll_project_allocation_service=payroll_project_allocation_service,
        payroll_run_service=payroll_run_service,
        payroll_payslip_preview_service=payroll_payslip_preview_service,
        payroll_calculation_service=payroll_calculation_service,
        payroll_posting_validation_service=payroll_posting_validation_service,
        payroll_posting_service=payroll_posting_service,
        payroll_payment_tracking_service=payroll_payment_tracking_service,
        payroll_remittance_service=payroll_remittance_service,
        payroll_summary_service=payroll_summary_service,
        payroll_pack_version_service=payroll_pack_version_service,
        payroll_validation_dashboard_service=payroll_validation_dashboard_service,
        payroll_import_service=payroll_import_service,
        payroll_print_service=payroll_print_service,
        payroll_export_service=payroll_export_service,
        payroll_output_warning_service=payroll_output_warning_service,
        payroll_remittance_deadline_service=payroll_remittance_deadline_service,
        dashboard_service=dashboard_service,
        audit_service=audit_service,
        permission_service=permission_service,
        role_service=role_service,
        code_suggestion_service=code_suggestion_service,
        print_engine=print_engine,
        sales_invoice_print_service=sales_invoice_print_service,
        customer_receipt_print_service=customer_receipt_print_service,
        purchase_bill_print_service=purchase_bill_print_service,
        supplier_payment_print_service=supplier_payment_print_service,
        journal_entry_print_service=journal_entry_print_service,
        chart_of_accounts_print_service=chart_of_accounts_print_service,
        customer_print_service=customer_print_service,
        supplier_print_service=supplier_print_service,
        financial_account_print_service=financial_account_print_service,
        treasury_transaction_print_service=treasury_transaction_print_service,
        treasury_transfer_print_service=treasury_transfer_print_service,
        item_print_service=item_print_service,
        inventory_document_print_service=inventory_document_print_service,
        asset_print_service=asset_print_service,
        depreciation_run_print_service=depreciation_run_print_service,
        audit_log_print_service=audit_log_print_service,
        backup_export_service=backup_export_service,
        backup_analysis_service=backup_analysis_service,
        backup_merge_service=backup_merge_service,
        license_service=license_service,
    )
