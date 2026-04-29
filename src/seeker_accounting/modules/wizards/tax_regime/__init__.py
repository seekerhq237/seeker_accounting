"""Tax Regime Wizard — declare VAT/CIT/DSF profile for the active company."""
from seeker_accounting.modules.wizards.tax_regime.wizard import (
    TaxRegimeResult,
    TaxRegimeWizard,
    launch_tax_regime_wizard,
)

__all__ = [
    "TaxRegimeResult",
    "TaxRegimeWizard",
    "launch_tax_regime_wizard",
]
