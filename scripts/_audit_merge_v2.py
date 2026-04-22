"""
Re-audit the corrected backup_merge_service.py column lists against actual DB schema.
This reads the ACTUAL file (not hardcoded columns) and compares.
"""
import ast
import re

SRC = "src/seeker_accounting/modules/administration/services/backup_merge_service.py"

# Actual DB schema (from PRAGMA table_info)
DB_SCHEMA = {
    "permissions": ['id', 'code', 'name', 'module_code', 'description'],
    "roles": ['id', 'code', 'name', 'description', 'is_system', 'created_at', 'updated_at'],
    "role_permissions": ['role_id', 'permission_id'],
    "users": ['id', 'username', 'display_name', 'email', 'password_hash', 'last_login_at', 'created_at', 'updated_at', 'is_active', 'must_change_password', 'avatar_storage_path', 'avatar_original_filename', 'avatar_content_type', 'avatar_sha256', 'avatar_updated_at', 'password_changed_at'],
    "companies": ['id', 'legal_name', 'display_name', 'registration_number', 'tax_identifier', 'phone', 'email', 'website', 'address_line_1', 'address_line_2', 'city', 'region', 'country_code', 'base_currency_code', 'created_at', 'updated_at', 'is_active', 'sector_of_operation', 'logo_storage_path', 'logo_original_filename', 'logo_content_type', 'logo_sha256', 'logo_updated_at', 'deleted_at', 'cnps_employer_number'],
    "company_preferences": ['company_id', 'date_format_code', 'number_format_code', 'decimal_places', 'tax_inclusive_default', 'allow_negative_stock', 'default_inventory_cost_method', 'updated_at', 'updated_by_user_id', 'idle_timeout_minutes', 'password_expiry_days'],
    "company_fiscal_defaults": ['company_id', 'fiscal_year_start_month', 'fiscal_year_start_day', 'default_posting_grace_days', 'updated_at'],
    "company_project_preferences": ['company_id', 'allow_projects_without_contract', 'default_budget_control_mode_code', 'default_commitment_control_mode_code', 'budget_warning_percent_threshold', 'require_job_on_cost_posting', 'require_cost_code_on_cost_posting', 'updated_at', 'updated_by_user_id'],
    "user_company_access": ['id', 'user_id', 'company_id', 'role_scope_note', 'is_default_company', 'granted_at', 'granted_by_user_id'],
    "user_roles": ['user_id', 'role_id'],
    "payment_terms": ['id', 'company_id', 'code', 'name', 'days_due', 'description', 'is_active'],
    "tax_codes": ['id', 'company_id', 'code', 'name', 'tax_type_code', 'calculation_method_code', 'rate_percent', 'is_recoverable', 'effective_from', 'effective_to', 'created_at', 'updated_at', 'is_active'],
    "document_sequences": ['id', 'company_id', 'document_type_code', 'prefix', 'suffix', 'next_number', 'padding_width', 'reset_frequency_code', 'created_at', 'updated_at', 'is_active'],
    "accounts": ['id', 'company_id', 'account_code', 'account_name', 'account_class_id', 'account_type_id', 'parent_account_id', 'normal_balance', 'allow_manual_posting', 'is_control_account', 'notes', 'created_at', 'updated_at', 'is_active'],
    "account_role_mappings": ['id', 'company_id', 'role_code', 'account_id', 'updated_at'],
    "tax_code_account_mappings": ['id', 'company_id', 'tax_code_id', 'sales_account_id', 'purchase_account_id', 'tax_liability_account_id', 'tax_asset_account_id', 'updated_at'],
    "ias_income_statement_templates": ['id', 'statement_profile_code', 'template_code', 'template_title', 'description', 'standard_note', 'display_order', 'row_height', 'section_background', 'subtotal_background', 'statement_background', 'amount_font_size', 'label_font_size', 'created_at', 'updated_at', 'is_active'],
    "ias_income_statement_sections": ['id', 'statement_profile_code', 'section_code', 'section_label', 'parent_section_code', 'display_order', 'row_kind_code', 'is_mapping_target', 'created_at', 'updated_at', 'is_active'],
    "ias_income_statement_mappings": ['id', 'company_id', 'statement_profile_code', 'section_code', 'subsection_code', 'account_id', 'sign_behavior_code', 'display_order', 'created_by_user_id', 'updated_by_user_id', 'created_at', 'updated_at', 'is_active'],
    "ias_income_statement_preferences": ['company_id', 'template_code', 'updated_at', 'updated_by_user_id'],
    "fiscal_years": ['id', 'company_id', 'year_code', 'year_name', 'start_date', 'end_date', 'status_code', 'created_at', 'updated_at', 'is_active'],
    "fiscal_periods": ['id', 'company_id', 'fiscal_year_id', 'period_number', 'period_code', 'period_name', 'start_date', 'end_date', 'status_code', 'is_adjustment_period', 'created_at', 'updated_at'],
    "journal_entries": ['id', 'company_id', 'fiscal_period_id', 'entry_number', 'entry_date', 'journal_type_code', 'reference_text', 'description', 'source_module_code', 'source_document_type', 'source_document_id', 'status_code', 'posted_at', 'posted_by_user_id', 'created_by_user_id', 'created_at', 'updated_at', 'transaction_date'],
    "journal_entry_lines": ['id', 'journal_entry_id', 'line_number', 'account_id', 'line_description', 'debit_amount', 'credit_amount', 'created_at', 'updated_at', 'contract_id', 'project_id', 'project_job_id', 'project_cost_code_id'],
    "customer_groups": ['id', 'company_id', 'code', 'name', 'created_at', 'updated_at', 'is_active'],
    "customers": ['id', 'company_id', 'customer_code', 'display_name', 'legal_name', 'customer_group_id', 'payment_term_id', 'tax_identifier', 'phone', 'email', 'address_line_1', 'address_line_2', 'city', 'region', 'country_code', 'credit_limit_amount', 'notes', 'created_at', 'updated_at', 'is_active'],
    "sales_invoices": ['id', 'company_id', 'invoice_number', 'customer_id', 'invoice_date', 'due_date', 'currency_code', 'exchange_rate', 'status_code', 'payment_status_code', 'reference_number', 'notes', 'subtotal_amount', 'tax_amount', 'total_amount', 'posted_journal_entry_id', 'posted_at', 'posted_by_user_id', 'created_at', 'updated_at', 'contract_id', 'project_id'],
    "sales_invoice_lines": ['id', 'sales_invoice_id', 'line_number', 'description', 'quantity', 'unit_price', 'discount_percent', 'discount_amount', 'tax_code_id', 'revenue_account_id', 'line_subtotal_amount', 'line_tax_amount', 'line_total_amount', 'created_at', 'updated_at', 'contract_id', 'project_id', 'project_job_id', 'project_cost_code_id'],
    "customer_receipts": ['id', 'company_id', 'receipt_number', 'customer_id', 'financial_account_id', 'receipt_date', 'currency_code', 'exchange_rate', 'amount_received', 'status_code', 'reference_number', 'notes', 'posted_journal_entry_id', 'posted_at', 'posted_by_user_id', 'created_at', 'updated_at'],
    "customer_receipt_allocations": ['id', 'company_id', 'customer_receipt_id', 'sales_invoice_id', 'allocated_amount', 'allocation_date', 'created_at'],
    "supplier_groups": ['id', 'company_id', 'code', 'name', 'created_at', 'updated_at', 'is_active'],
    "suppliers": ['id', 'company_id', 'supplier_code', 'display_name', 'legal_name', 'supplier_group_id', 'payment_term_id', 'tax_identifier', 'phone', 'email', 'address_line_1', 'address_line_2', 'city', 'region', 'country_code', 'notes', 'created_at', 'updated_at', 'is_active'],
    "purchase_bills": ['id', 'company_id', 'bill_number', 'supplier_bill_reference', 'supplier_id', 'bill_date', 'due_date', 'currency_code', 'exchange_rate', 'status_code', 'payment_status_code', 'notes', 'subtotal_amount', 'tax_amount', 'total_amount', 'posted_journal_entry_id', 'posted_at', 'posted_by_user_id', 'created_at', 'updated_at', 'contract_id', 'project_id'],
    "purchase_bill_lines": ['id', 'purchase_bill_id', 'line_number', 'description', 'quantity', 'unit_cost', 'expense_account_id', 'tax_code_id', 'line_subtotal_amount', 'line_tax_amount', 'line_total_amount', 'created_at', 'updated_at', 'contract_id', 'project_id', 'project_job_id', 'project_cost_code_id'],
    "supplier_payments": ['id', 'company_id', 'payment_number', 'supplier_id', 'financial_account_id', 'payment_date', 'currency_code', 'exchange_rate', 'amount_paid', 'status_code', 'reference_number', 'notes', 'posted_journal_entry_id', 'posted_at', 'posted_by_user_id', 'created_at', 'updated_at'],
    "supplier_payment_allocations": ['id', 'company_id', 'supplier_payment_id', 'purchase_bill_id', 'allocated_amount', 'allocation_date', 'created_at'],
    "financial_accounts": ['id', 'company_id', 'account_code', 'name', 'financial_account_type_code', 'gl_account_id', 'bank_name', 'bank_account_number', 'bank_branch', 'currency_code', 'created_at', 'updated_at', 'is_active'],
    "treasury_transactions": ['id', 'company_id', 'transaction_number', 'transaction_type_code', 'financial_account_id', 'transaction_date', 'currency_code', 'exchange_rate', 'total_amount', 'status_code', 'reference_number', 'description', 'notes', 'posted_journal_entry_id', 'posted_at', 'posted_by_user_id', 'created_at', 'updated_at', 'contract_id', 'project_id'],
    "treasury_transaction_lines": ['id', 'treasury_transaction_id', 'line_number', 'account_id', 'line_description', 'party_type', 'party_id', 'tax_code_id', 'amount', 'created_at', 'updated_at', 'contract_id', 'project_id', 'project_job_id', 'project_cost_code_id'],
    "treasury_transfers": ['id', 'company_id', 'transfer_number', 'from_financial_account_id', 'to_financial_account_id', 'transfer_date', 'currency_code', 'exchange_rate', 'amount', 'status_code', 'reference_number', 'description', 'notes', 'posted_journal_entry_id', 'posted_at', 'posted_by_user_id', 'created_at', 'updated_at'],
    "bank_statement_import_batches": ['id', 'company_id', 'financial_account_id', 'file_name', 'import_source', 'statement_start_date', 'statement_end_date', 'line_count', 'notes', 'imported_at', 'imported_by_user_id'],
    "bank_statement_lines": ['id', 'company_id', 'financial_account_id', 'import_batch_id', 'line_date', 'value_date', 'description', 'reference', 'debit_amount', 'credit_amount', 'is_reconciled', 'created_at'],
    "bank_reconciliation_sessions": ['id', 'company_id', 'financial_account_id', 'statement_end_date', 'statement_ending_balance', 'status_code', 'notes', 'completed_at', 'completed_by_user_id', 'created_at', 'created_by_user_id'],
    "bank_reconciliation_matches": ['id', 'company_id', 'reconciliation_session_id', 'bank_statement_line_id', 'match_entity_type', 'match_entity_id', 'matched_amount', 'created_at'],
    "uom_categories": ['id', 'company_id', 'code', 'name', 'description', 'is_active', 'created_at', 'updated_at'],
    "units_of_measure": ['id', 'company_id', 'code', 'name', 'description', 'is_active', 'created_at', 'updated_at', 'category_id', 'ratio_to_base'],
    "item_categories": ['id', 'company_id', 'code', 'name', 'description', 'is_active', 'created_at', 'updated_at'],
    "inventory_locations": ['id', 'company_id', 'code', 'name', 'description', 'is_active', 'created_at', 'updated_at'],
    "items": ['id', 'company_id', 'item_code', 'item_name', 'item_type_code', 'unit_of_measure_code', 'inventory_cost_method_code', 'inventory_account_id', 'cogs_account_id', 'expense_account_id', 'revenue_account_id', 'purchase_tax_code_id', 'sales_tax_code_id', 'reorder_level_quantity', 'description', 'is_active', 'created_at', 'updated_at', 'unit_of_measure_id', 'item_category_id'],
    "inventory_documents": ['id', 'company_id', 'document_number', 'document_type_code', 'document_date', 'status_code', 'reference_number', 'notes', 'total_value', 'posted_journal_entry_id', 'posted_at', 'posted_by_user_id', 'created_at', 'updated_at', 'location_id', 'contract_id', 'project_id'],
    "inventory_document_lines": ['id', 'inventory_document_id', 'line_number', 'item_id', 'quantity', 'unit_cost', 'line_amount', 'counterparty_account_id', 'line_description', 'created_at', 'contract_id', 'project_id', 'project_job_id', 'project_cost_code_id', 'transaction_uom_id', 'uom_ratio_snapshot', 'base_quantity'],
    "inventory_cost_layers": ['id', 'company_id', 'item_id', 'inventory_document_line_id', 'layer_date', 'quantity_in', 'quantity_remaining', 'unit_cost', 'created_at'],
    "asset_categories": ['id', 'company_id', 'code', 'name', 'asset_account_id', 'accumulated_depreciation_account_id', 'depreciation_expense_account_id', 'default_useful_life_months', 'default_depreciation_method_code', 'is_active', 'created_at', 'updated_at'],
    "assets": ['id', 'company_id', 'asset_number', 'asset_name', 'asset_category_id', 'acquisition_date', 'capitalization_date', 'acquisition_cost', 'salvage_value', 'useful_life_months', 'depreciation_method_code', 'status_code', 'supplier_id', 'purchase_bill_id', 'notes', 'created_at', 'updated_at'],
    "asset_depletion_profiles": ['id', 'company_id', 'asset_id', 'resource_type', 'estimated_total_units', 'unit_description', 'created_at', 'updated_at'],
    "asset_depreciation_runs": ['id', 'company_id', 'run_number', 'run_date', 'period_end_date', 'status_code', 'posted_journal_entry_id', 'posted_at', 'posted_by_user_id', 'created_at'],
    "asset_depreciation_run_lines": ['id', 'asset_depreciation_run_id', 'asset_id', 'depreciation_amount', 'accumulated_depreciation_after', 'net_book_value_after'],
    "asset_depreciation_settings": ['id', 'company_id', 'asset_id', 'declining_factor', 'switch_to_straight_line', 'expected_total_units', 'interest_rate', 'macrs_profile_id', 'macrs_convention_code', 'created_at', 'updated_at'],
    "asset_components": ['id', 'company_id', 'parent_asset_id', 'component_name', 'acquisition_cost', 'salvage_value', 'useful_life_months', 'depreciation_method_code', 'notes', 'is_active', 'created_at', 'updated_at'],
    "asset_usage_records": ['id', 'company_id', 'asset_id', 'usage_date', 'units_used', 'notes', 'created_at'],
    "asset_depreciation_pools": ['id', 'company_id', 'code', 'name', 'pool_type_code', 'depreciation_method_code', 'useful_life_months', 'is_active', 'created_at', 'updated_at'],
    "asset_depreciation_pool_members": ['id', 'pool_id', 'asset_id', 'joined_date', 'left_date'],
    "company_payroll_settings": ['company_id', 'statutory_pack_version_code', 'cnps_regime_code', 'accident_risk_class_code', 'default_pay_frequency_code', 'default_payroll_currency_code', 'overtime_policy_mode_code', 'benefit_in_kind_policy_mode_code', 'payroll_number_prefix', 'payroll_number_padding_width', 'updated_at', 'updated_by_user_id'],
    "departments": ['id', 'company_id', 'code', 'name', 'created_at', 'updated_at', 'is_active'],
    "positions": ['id', 'company_id', 'code', 'name', 'created_at', 'updated_at', 'is_active'],
    "employees": ['id', 'company_id', 'employee_number', 'display_name', 'first_name', 'last_name', 'department_id', 'position_id', 'hire_date', 'termination_date', 'phone', 'email', 'tax_identifier', 'base_currency_code', 'created_at', 'updated_at', 'is_active', 'cnps_number', 'default_payment_account_id'],
    "payroll_components": ['id', 'company_id', 'component_code', 'component_name', 'component_type_code', 'calculation_method_code', 'is_taxable', 'is_pensionable', 'expense_account_id', 'liability_account_id', 'created_at', 'updated_at', 'is_active'],
    "payroll_rule_sets": ['id', 'company_id', 'rule_code', 'rule_name', 'rule_type_code', 'effective_from', 'effective_to', 'calculation_basis_code', 'created_at', 'updated_at', 'is_active'],
    "payroll_rule_brackets": ['id', 'payroll_rule_set_id', 'line_number', 'lower_bound_amount', 'upper_bound_amount', 'rate_percent', 'fixed_amount', 'deduction_amount', 'cap_amount'],
    "employee_compensation_profiles": ['id', 'company_id', 'employee_id', 'profile_name', 'basic_salary', 'currency_code', 'effective_from', 'effective_to', 'notes', 'is_active', 'created_at', 'updated_at', 'number_of_parts'],
    "employee_component_assignments": ['id', 'company_id', 'employee_id', 'component_id', 'override_amount', 'override_rate', 'effective_from', 'effective_to', 'is_active', 'created_at', 'updated_at'],
    "payroll_input_batches": ['id', 'company_id', 'batch_reference', 'period_year', 'period_month', 'status_code', 'description', 'submitted_at', 'approved_at', 'created_at', 'updated_at'],
    "payroll_input_lines": ['id', 'company_id', 'batch_id', 'employee_id', 'component_id', 'input_amount', 'input_quantity', 'notes', 'created_at', 'updated_at'],
    "payroll_runs": ['id', 'company_id', 'run_reference', 'run_label', 'period_year', 'period_month', 'status_code', 'currency_code', 'run_date', 'payment_date', 'notes', 'calculated_at', 'approved_at', 'created_at', 'updated_at', 'posted_at', 'posted_by_user_id', 'posted_journal_entry_id'],
    "payroll_run_employees": ['id', 'company_id', 'run_id', 'employee_id', 'gross_earnings', 'taxable_salary_base', 'tdl_base', 'cnps_contributory_base', 'employer_cost_base', 'net_payable', 'total_earnings', 'total_employee_deductions', 'total_employer_contributions', 'total_taxes', 'status_code', 'calculation_notes', 'created_at', 'updated_at', 'payment_status_code', 'payment_date'],
    "payroll_run_lines": ['id', 'company_id', 'run_id', 'run_employee_id', 'employee_id', 'component_id', 'component_type_code', 'calculation_basis', 'rate_applied', 'component_amount', 'created_at', 'updated_at'],
    "payroll_run_employee_project_allocations": ['id', 'payroll_run_employee_id', 'line_number', 'contract_id', 'project_id', 'project_job_id', 'project_cost_code_id', 'allocation_basis_code', 'allocation_quantity', 'allocation_percent', 'allocated_cost_amount', 'notes', 'created_at'],
    "payroll_payment_records": ['id', 'company_id', 'run_employee_id', 'payment_date', 'amount_paid', 'payment_method_code', 'payment_reference', 'treasury_transaction_id', 'notes', 'created_by_user_id', 'updated_by_user_id', 'created_at', 'updated_at'],
    "payroll_remittance_batches": ['id', 'company_id', 'batch_number', 'payroll_run_id', 'period_start_date', 'period_end_date', 'remittance_authority_code', 'remittance_date', 'amount_due', 'amount_paid', 'status_code', 'reference', 'treasury_transaction_id', 'notes', 'created_by_user_id', 'updated_by_user_id', 'created_at', 'updated_at'],
    "payroll_remittance_lines": ['id', 'payroll_remittance_batch_id', 'line_number', 'payroll_component_id', 'liability_account_id', 'description', 'amount_due', 'amount_paid', 'status_code', 'notes', 'created_at', 'updated_at'],
    "contracts": ['id', 'company_id', 'contract_number', 'contract_title', 'customer_id', 'contract_type_code', 'currency_code', 'exchange_rate', 'base_contract_amount', 'start_date', 'planned_end_date', 'actual_end_date', 'status_code', 'billing_basis_code', 'retention_percent', 'reference_number', 'description', 'approved_at', 'approved_by_user_id', 'created_at', 'updated_at', 'created_by_user_id', 'updated_by_user_id'],
    "contract_change_orders": ['id', 'company_id', 'contract_id', 'change_order_number', 'change_order_date', 'status_code', 'change_type_code', 'description', 'contract_amount_delta', 'days_extension', 'effective_date', 'approved_at', 'approved_by_user_id', 'created_at', 'updated_at'],
    "projects": ['id', 'company_id', 'project_code', 'project_name', 'contract_id', 'customer_id', 'project_type_code', 'project_manager_user_id', 'currency_code', 'exchange_rate', 'start_date', 'planned_end_date', 'actual_end_date', 'status_code', 'budget_control_mode_code', 'notes', 'created_at', 'updated_at', 'created_by_user_id', 'updated_by_user_id'],
    "project_jobs": ['id', 'company_id', 'project_id', 'job_code', 'job_name', 'parent_job_id', 'sequence_number', 'status_code', 'start_date', 'planned_end_date', 'actual_end_date', 'allow_direct_cost_posting', 'notes', 'created_at', 'updated_at'],
    "project_cost_codes": ['id', 'company_id', 'code', 'name', 'cost_code_type_code', 'default_account_id', 'is_active', 'description', 'created_at', 'updated_at'],
    "project_budget_versions": ['id', 'company_id', 'project_id', 'version_number', 'version_name', 'version_type_code', 'status_code', 'base_version_id', 'budget_date', 'revision_reason', 'total_budget_amount', 'approved_at', 'approved_by_user_id', 'created_at', 'updated_at'],
    "project_budget_lines": ['id', 'project_budget_version_id', 'line_number', 'project_job_id', 'project_cost_code_id', 'description', 'quantity', 'unit_rate', 'line_amount', 'start_date', 'end_date', 'notes', 'created_at', 'updated_at'],
    "project_commitments": ['id', 'company_id', 'commitment_number', 'project_id', 'supplier_id', 'commitment_type_code', 'commitment_date', 'required_date', 'currency_code', 'exchange_rate', 'status_code', 'reference_number', 'notes', 'total_amount', 'approved_at', 'approved_by_user_id', 'created_at', 'updated_at'],
    "project_commitment_lines": ['id', 'project_commitment_id', 'line_number', 'project_job_id', 'project_cost_code_id', 'description', 'quantity', 'unit_rate', 'line_amount', 'notes', 'created_at', 'updated_at'],
    "audit_events": ['id', 'company_id', 'event_type_code', 'module_code', 'entity_type', 'entity_id', 'description', 'detail_json', 'actor_user_id', 'actor_display_name', 'created_at'],
}

# Extract column lists from the merge service file
# We parse string literals that look like column names within _copy_table_* calls
with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()

# Extract all column lists by finding list literals in _copy_table_building_map / _copy_table_with_remap calls
# and also in inline SQL statements for special tables (permissions, roles, users, companies, user_roles)

# Parse all string literals that appear in list context within the file
# Simpler: find all table names referenced in the merge and compare column presence

# Find all _copy_table_building_map / _copy_table_with_remap calls
# Pattern: self._copy_table_XXX(\n    src, tgt, "TABLE_NAME",\n    [col_list]
table_pattern = re.compile(
    r'(?:_copy_table_building_map|_copy_table_with_remap)\s*\(\s*'
    r'src\s*,\s*tgt\s*,\s*"(\w+)"\s*,\s*'
    r'\[([^\]]+)\]',
    re.DOTALL
)

# Also find _upsert_global_by_code calls
upsert_pattern = re.compile(
    r'_upsert_global_by_code\s*\(\s*'
    r'src\s*,\s*tgt\s*,\s*"(\w+)"\s*,\s*pk_col\s*=\s*"\w+"\s*,\s*'
    r'columns\s*=\s*\[([^\]]+)\]',
    re.DOTALL
)

# Extract inline SQL columns for special tables
# permissions: SELECT id, code, name, module_code, description FROM permissions
# roles: SELECT id, code, name, description, is_system, created_at, updated_at FROM roles
# users: SELECT id, username, ... FROM users
# companies: SELECT id, legal_name, ... FROM companies
inline_select_pattern = re.compile(
    r'"SELECT\s+([\w, \n]+?)\s+FROM\s+(\w+)"',
    re.DOTALL
)

all_merge_tables: dict[str, set[str]] = {}

# Parse _copy_table* calls
for match in table_pattern.finditer(content):
    table = match.group(1)
    cols_str = match.group(2)
    cols = set(c.strip().strip('"').strip("'") for c in cols_str.split(",") if c.strip().strip('"').strip("'"))
    all_merge_tables[table] = cols

# Parse _upsert_global_by_code calls
for match in upsert_pattern.finditer(content):
    table = match.group(1)
    cols_str = match.group(2)
    cols = set(c.strip().strip('"').strip("'") for c in cols_str.split(",") if c.strip().strip('"').strip("'"))
    all_merge_tables[table] = cols

# Parse inline SELECT statements for special tables
for match in inline_select_pattern.finditer(content):
    cols_raw = match.group(1)
    table = match.group(2)
    if table in ("permissions", "roles", "users", "companies", "user_roles", "role_permissions"):
        cols = set(c.strip() for c in cols_raw.replace("\n", " ").split(",") if c.strip())
        if table in all_merge_tables:
            all_merge_tables[table] |= cols
        else:
            all_merge_tables[table] = cols

# Compare
CRITICAL = []
WARNINGS = []

for table in sorted(set(list(DB_SCHEMA.keys()) + list(all_merge_tables.keys()))):
    db_cols = set(DB_SCHEMA.get(table, []))
    merge_cols = all_merge_tables.get(table, set())
    
    if not merge_cols:
        continue

    phantom = merge_cols - db_cols
    if phantom:
        CRITICAL.append(f"FATAL {table}: merge writes NON-EXISTENT columns: {sorted(phantom)}")
    
    missing = db_cols - merge_cols
    if missing:
        WARNINGS.append(f"SKIP {table}: DB columns NOT in merge: {sorted(missing)}")

print("=" * 80)
print("POST-FIX AUDIT RESULTS")
print("=" * 80)
print()

if CRITICAL:
    print(f"### CRITICAL ({len(CRITICAL)}) ###")
    for c in CRITICAL:
        print(f"  {c}")
    print()
else:
    print("### ZERO CRITICAL ISSUES ###")
    print()

if WARNINGS:
    print(f"### DATA SKIP ({len(WARNINGS)}) ###")
    for w in WARNINGS:
        print(f"  {w}")
else:
    print("### ZERO DATA SKIP ###")

print()
print(f"Tables covered by merge: {len(all_merge_tables)}")
print(f"Tables in DB: {len(DB_SCHEMA)}")

# Check for DB tables not handled at all
not_handled = set(DB_SCHEMA.keys()) - set(all_merge_tables.keys())
if not_handled:
    print(f"\nTables in DB NOT in merge at all: {sorted(not_handled)}")
