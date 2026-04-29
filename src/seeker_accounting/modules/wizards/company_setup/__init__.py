"""Company Setup Wizard.

End-to-end guided onboarding for a new company:

1. Company info  (creates the company)
2. Fiscal year + monthly periods
3. Chart of Accounts  (OHADA seed)
4. Default document sequences
5. Default tax codes
6. Account role mappings  (optional — deferred to dedicated UI when blank)
7. Review & finish

Each step is service-driven. The wizard reuses existing services without
re-implementing logic — its job is orchestration plus assistant guidance.
"""
from seeker_accounting.modules.wizards.company_setup.wizard import (
    CompanySetupWizard,
    CompanySetupResult,
    launch_company_setup_wizard,
)

__all__ = [
    "CompanySetupWizard",
    "CompanySetupResult",
    "launch_company_setup_wizard",
]
