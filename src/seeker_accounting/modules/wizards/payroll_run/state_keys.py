"""Stable state-bag keys for the Payroll Run Wizard."""
from __future__ import annotations

from typing import Final

# Step 1: period & label
KEY_PERIOD_YEAR: Final = "period_year"
KEY_PERIOD_MONTH: Final = "period_month"
KEY_RUN_LABEL: Final = "run_label"
KEY_CURRENCY_CODE: Final = "currency_code"
KEY_RUN_DATE: Final = "run_date"
KEY_PAYMENT_DATE: Final = "payment_date"
KEY_NOTES: Final = "notes"
KEY_RUN_ID: Final = "run_id"
KEY_RUN_REFERENCE: Final = "run_reference"
KEY_RUN_STATUS: Final = "run_status"

# Step 2: review employees
KEY_EMPLOYEE_COUNT: Final = "employee_count"
KEY_TOTAL_GROSS: Final = "total_gross"
KEY_TOTAL_NET: Final = "total_net"

# Step 3: approve
KEY_APPROVE_CONFIRMED: Final = "approve_confirmed"

# Step 4: post
KEY_POSTING_DATE: Final = "posting_date"
KEY_POSTING_NARRATION: Final = "posting_narration"
KEY_POSTED_JOURNAL_ENTRY_ID: Final = "posted_journal_entry_id"
KEY_POSTED_ENTRY_NUMBER: Final = "posted_entry_number"
