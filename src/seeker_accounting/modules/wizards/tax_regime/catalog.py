"""Catalog of tax regime / segment / profile options."""
from __future__ import annotations

# (code, label, description) tuples mirror constants in modules/taxation/constants.

TAX_REGIME_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("REAL", "Real regime", "Standard accounting regime: full ledgers, monthly VAT, annual CIT."),
    ("SIMPLIFIED", "Simplified regime", "Smaller turnover thresholds; reduced obligations and simplified DSF."),
    ("LIBERATORY", "Liberatory regime", "Single liberatory tax in lieu of standard taxes; very small businesses."),
)

TAXPAYER_SEGMENT_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("LARGE", "Large enterprise", "Direction Générale des Impôts — large taxpayer center."),
    ("MEDIUM", "Medium enterprise", "Mid-size segment with regional follow-up."),
    ("DIVISIONAL", "Divisional", "Local divisional tax center."),
    ("SPECIALIZED", "Specialized", "Specialized regime / sector-specific."),
)

CIT_RATE_PROFILE_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("STANDARD", "Standard CIT (30% + CAC)", "Default rate of 30% with the additional CAC surcharge."),
    ("SME", "SME CIT (25% + CAC)", "Reduced 25% rate for qualified SMEs."),
    ("EXEMPT", "Exempt", "Exempt from CIT under a specific regime or convention."),
)

DSF_FORM_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("DSF_REAL", "DSF Real", "DSF form for the real regime."),
    ("DSF_SIMPLIFIED", "DSF Simplified", "DSF form for the simplified regime."),
    ("DSF_LIBERATORY", "DSF Liberatory", "DSF form for the liberatory regime."),
    ("NONE", "None", "No DSF filing required (e.g., exempt entities)."),
)

DSF_SUBMISSION_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("EXCEL", "Excel template", "Submitted via the official Excel template."),
    ("API", "API / e-filing", "Submitted via electronic filing API."),
    ("MANUAL", "Manual / paper", "Filed manually at the tax center."),
)
