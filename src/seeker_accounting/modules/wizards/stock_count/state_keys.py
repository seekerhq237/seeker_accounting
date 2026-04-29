"""State keys for the Stock Count Wizard."""

KEY_COUNT_DATE = "count_date"
KEY_LOCATION_ID = "location_id"
KEY_ADJUSTMENT_ACCOUNT_ID = "adjustment_account_id"
KEY_REFERENCE = "reference"
KEY_NOTES = "notes"
# Counts: tuple[dict(item_id, item_code, item_name, system_qty, counted_qty, avg_cost)]
KEY_COUNTS = "counts"

KEY_RESULT_DOCUMENT_ID = "result_document_id"
KEY_RESULT_DOCUMENT_NUMBER = "result_document_number"
KEY_RESULT_VARIANCE_LINES = "result_variance_lines"
KEY_RESULT_JOURNAL_ENTRY_ID = "result_journal_entry_id"
KEY_POSTED = "stock_count_posted"
