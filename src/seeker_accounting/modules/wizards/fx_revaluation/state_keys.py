"""State keys for the FX Revaluation Wizard."""

KEY_REVALUATION_DATE = "revaluation_date"
KEY_GAIN_ACCOUNT_ID = "gain_account_id"
KEY_LOSS_ACCOUNT_ID = "loss_account_id"
KEY_REFERENCE = "reference"
# Lines: tuple[dict(account_id, current_book_amount, target_amount, description)]
KEY_LINES = "revaluation_lines"

KEY_RESULT_JE_ID = "result_je_id"
KEY_RESULT_JE_NUMBER = "result_je_number"
KEY_RESULT_GAIN = "result_total_gain"
KEY_RESULT_LOSS = "result_total_loss"
KEY_RESULT_NET = "result_net"
KEY_POSTED = "fx_revaluation_posted"
