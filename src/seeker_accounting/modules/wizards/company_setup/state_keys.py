"""Stable state-bag keys used across the Company Setup Wizard steps.

Centralized to avoid string-typo bugs. The framework persists this dict to
``wizard_runs.state_payload`` for resumability.
"""
from __future__ import annotations

from typing import Final

# ── Step 1: Company info ─────────────────────────────────────────────────
KEY_COMPANY_ID: Final = "company_id"
KEY_COMPANY_DISPLAY_NAME: Final = "company_display_name"
KEY_COMPANY_LEGAL_NAME: Final = "company_legal_name"
KEY_COMPANY_COUNTRY_CODE: Final = "company_country_code"
KEY_COMPANY_CURRENCY_CODE: Final = "company_currency_code"
KEY_COMPANY_TAX_IDENTIFIER: Final = "company_tax_identifier"

# ── Step 2: Fiscal year ──────────────────────────────────────────────────
KEY_FISCAL_YEAR_ID: Final = "fiscal_year_id"
KEY_FISCAL_YEAR_CODE: Final = "fiscal_year_code"
KEY_FISCAL_YEAR_NAME: Final = "fiscal_year_name"
KEY_FISCAL_YEAR_START: Final = "fiscal_year_start"
KEY_FISCAL_YEAR_END: Final = "fiscal_year_end"
KEY_FISCAL_PERIODS_GENERATED: Final = "fiscal_periods_generated"

# ── Step 3: Chart of Accounts ────────────────────────────────────────────
KEY_COA_SEED_REQUESTED: Final = "coa_seed_requested"
KEY_COA_SEED_TEMPLATE: Final = "coa_seed_template"
KEY_COA_ACCOUNTS_CREATED: Final = "coa_accounts_created"

# ── Step 4: Document sequences ───────────────────────────────────────────
KEY_DOC_SEQ_TYPES_TO_CREATE: Final = "doc_seq_types_to_create"
KEY_DOC_SEQ_CREATED: Final = "doc_seq_created"

# ── Step 5: Tax codes ────────────────────────────────────────────────────
KEY_TAX_CODES_TO_CREATE: Final = "tax_codes_to_create"
KEY_TAX_CODES_CREATED: Final = "tax_codes_created"

# ── Step 6: Account role mappings ────────────────────────────────────────
KEY_ROLE_MAPPING_SELECTIONS: Final = "role_mapping_selections"
KEY_ROLE_MAPPINGS_DEFERRED: Final = "role_mappings_deferred"
KEY_ROLE_MAPPINGS_DEFERRED_LIST: Final = "role_mappings_deferred_list"
KEY_ROLE_MAPPINGS_APPLIED: Final = "role_mappings_applied"
