"""Stable state-bag keys for the Month-End Close Wizard."""
from __future__ import annotations

from typing import Final

# Step 1: period selection
KEY_PERIOD_ID: Final = "period_id"
KEY_PERIOD_CODE: Final = "period_code"
KEY_PERIOD_START: Final = "period_start"
KEY_PERIOD_END: Final = "period_end"
KEY_PERIOD_STATUS_CODE: Final = "period_status_code"

# Step 2: drafts check
KEY_DRAFTS_COUNT: Final = "drafts_count"
KEY_DRAFTS_FOR_PERIOD: Final = "drafts_for_period"
KEY_DRAFTS_ACKNOWLEDGED: Final = "drafts_acknowledged"

# Step 3: reconciliation reminders
KEY_RECON_BANK_ACK: Final = "recon_bank_ack"
KEY_RECON_AR_ACK: Final = "recon_ar_ack"
KEY_RECON_AP_ACK: Final = "recon_ap_ack"

# Step 4: close
KEY_CLOSE_CONFIRMED: Final = "close_confirmed"
KEY_CLOSE_RESULT_PERIOD_ID: Final = "close_result_period_id"
KEY_CLOSE_RESULT_NEW_STATUS: Final = "close_result_new_status"
