"""State keys for the Year-End Close Wizard."""

KEY_FISCAL_YEAR_ID = "fiscal_year_id"
KEY_FISCAL_YEAR_CODE = "fiscal_year_code"

KEY_PERIODS_SNAPSHOT = "periods_snapshot"  # list[dict(id, period_code, status_code)]
KEY_LOCK_CLOSED_PERIODS = "lock_closed_periods"
KEY_PERIODS_LOCKED_COUNT = "periods_locked_count"
KEY_PERIODS_LOCKED_AT_COMMIT = "periods_locked_at_commit"

KEY_YEAR_CLOSED = "year_closed"
