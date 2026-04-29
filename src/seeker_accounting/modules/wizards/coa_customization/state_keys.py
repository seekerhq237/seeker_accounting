"""State keys for the COA Customization Wizard."""

KEY_APPLY_BASELINE = "apply_baseline"
KEY_BASELINE_TEMPLATE = "baseline_template"

KEY_BASELINE_RESULT_IMPORTED = "baseline_result_imported"
KEY_BASELINE_RESULT_SKIPPED = "baseline_result_skipped"
KEY_BASELINE_RESULT_INVALID = "baseline_result_invalid"
KEY_BASELINE_RESULT_TOTAL = "baseline_result_total"
KEY_BASELINE_RESULT_MESSAGES = "baseline_result_messages"
KEY_BASELINE_APPLIED = "baseline_applied"

# role_code -> account_id (or None to clear)
KEY_ROLE_SELECTIONS = "role_selections"
# role_code -> current account_id (loaded from server, used for diff)
KEY_ROLE_CURRENT = "role_current"

KEY_MAPPINGS_UPDATED_COUNT = "mappings_updated_count"
KEY_MAPPINGS_CLEARED_COUNT = "mappings_cleared_count"
KEY_MAPPINGS_PERSISTED = "mappings_persisted"
