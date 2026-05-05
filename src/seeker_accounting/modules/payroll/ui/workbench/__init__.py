"""Phase 2 Payroll Workbench package.

A single-page consolidation of the four legacy payroll surfaces
(Setup / Calculation / Accounting / Operations). See
``docs/payroll_ux_remediation_plan.md`` Phase 2 for the locked
direction.
"""
from __future__ import annotations

from seeker_accounting.modules.payroll.ui.workbench.payroll_workbench_page import (
    PayrollWorkbenchPage,
)

__all__ = ["PayrollWorkbenchPage"]
