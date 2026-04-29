"""State keys for the Tax Regime Wizard."""

# Identity / registration
KEY_NIU = "niu"
KEY_TAX_CENTER_CODE = "tax_center_code"
KEY_TAXPAYER_SEGMENT_CODE = "taxpayer_segment_code"
KEY_TAX_REGIME_CODE = "tax_regime_code"

# VAT
KEY_IS_VAT_LIABLE = "is_vat_liable"
KEY_VAT_EFFECTIVE_FROM = "vat_effective_from"

# CIT (corporate income tax)
KEY_CIT_RATE_PROFILE_CODE = "cit_rate_profile_code"
KEY_CIT_INSTALLMENT_PROFILE_CODE = "cit_installment_profile_code"
KEY_SME_QUALIFIED_FLAG = "sme_qualified_flag"

# DSF (annual statistical & fiscal return) + flags
KEY_DSF_FORM_CODE = "dsf_form_code"
KEY_DSF_SUBMISSION_MODE_CODE = "dsf_submission_mode_code"
KEY_OTP_ENABLED_FLAG = "otp_enabled_flag"
KEY_DEFAULT_WITHHOLDING_APPLICABLE_FLAG = "default_withholding_applicable_flag"

KEY_PROFILE_PERSISTED = "profile_persisted"
