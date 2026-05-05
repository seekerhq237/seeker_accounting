"""Shared empty-state catalog for workbench surfaces.

Feature pages should ask this module for the empty state they need instead of
repeating copy and widget construction locally. The widgets remain presentation
only; navigation and business actions are connected by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.shared.ui.accessibility import set_accessible_metadata
from seeker_accounting.shared.ui.components.workbench_primitives import EmptyState


@dataclass(frozen=True, slots=True)
class EmptyStateSpec:
    key: str
    headline: str
    body: str = ""
    primary_label: str | None = None
    secondary_label: str | None = None
    glyph: str = ""


EMPTY_STATE_LIBRARY: dict[str, EmptyStateSpec] = {
    "generic.no_records": EmptyStateSpec(
        key="generic.no_records",
        headline="No records found",
        body="There is nothing to show for the current company and filters.",
    ),
    "generic.filtered_empty": EmptyStateSpec(
        key="generic.filtered_empty",
        headline="No matches",
        body="Adjust the filters or search text to widen the result set.",
    ),
    "dashboard.no_company": EmptyStateSpec(
        key="dashboard.no_company",
        headline="No company selected",
        body="Select or create a company to view dashboard activity, balances, and setup progress.",
        primary_label="Open Companies",
    ),
    "dashboard.recent_activity": EmptyStateSpec(
        key="dashboard.recent_activity",
        headline="No recent activity",
        body="Posted journals, sales, purchases, receipts, and payments will appear here as work begins.",
    ),
    "dashboard.attention": EmptyStateSpec(
        key="dashboard.attention",
        headline="Nothing requires attention",
        body="Draft postings, overdue documents, and low-stock signals will appear here when action is needed.",
    ),
    "dashboard.cash_movements": EmptyStateSpec(
        key="dashboard.cash_movements",
        headline="No cash movements",
        body="Posted receipts, payments, and bank movements will populate this trend.",
    ),
    "dashboard.financial_accounts": EmptyStateSpec(
        key="dashboard.financial_accounts",
        headline="No financial accounts",
        body="Add cash or bank accounts to see account-level liquidity balances.",
    ),
    "dashboard.setup_complete": EmptyStateSpec(
        key="dashboard.setup_complete",
        headline="Setup checklist complete",
        body="The core company foundation is ready for day-to-day accounting work.",
    ),
    "customers.empty": EmptyStateSpec(
        key="customers.empty",
        headline="No customers yet",
        body="Create customer records before entering sales documents, receipts, and receivables activity.",
        primary_label="Create Customer",
        secondary_label="Manage Groups",
    ),
    "customers.no_company": EmptyStateSpec(
        key="customers.no_company",
        headline="Select an active company first",
        body="Customers are company-scoped. Choose the active company before managing customer records.",
        primary_label="Open Companies",
    ),
    "suppliers.empty": EmptyStateSpec(
        key="suppliers.empty",
        headline="No suppliers yet",
        body="Create supplier records before entering purchase documents, bills, and payable activity.",
        primary_label="Create Supplier",
        secondary_label="Manage Groups",
    ),
    "suppliers.no_company": EmptyStateSpec(
        key="suppliers.no_company",
        headline="Select an active company first",
        body="Suppliers are company-scoped. Choose the active company before managing supplier records.",
        primary_label="Open Companies",
    ),
    "treasury.transactions.empty": EmptyStateSpec(
        key="treasury.transactions.empty",
        headline="No treasury transactions yet",
        body="Create the first cash or bank receipt or payment, then post it when the transaction is complete.",
        primary_label="Create Transaction",
    ),
    "treasury.financial_accounts.empty": EmptyStateSpec(
        key="treasury.financial_accounts.empty",
        headline="No financial accounts yet",
        body="Create cash and bank accounts for the active company before recording treasury activity.",
        primary_label="Create Account",
    ),
    "treasury.no_company": EmptyStateSpec(
        key="treasury.no_company",
        headline="Select an active company first",
        body="Treasury records are company-scoped. Choose the active company before managing cash and bank workflows.",
        primary_label="Open Companies",
    ),
    "projects.empty": EmptyStateSpec(
        key="projects.empty",
        headline="No projects yet",
        body="Create the first project for the active company before tracking budgets, jobs, commitments, and costs.",
        primary_label="Create Project",
    ),
    "projects.no_company": EmptyStateSpec(
        key="projects.no_company",
        headline="Select an active company first",
        body="Projects are company-scoped. Choose the active company before managing project records.",
        primary_label="Open Companies",
    ),
    "inventory.items.empty": EmptyStateSpec(
        key="inventory.items.empty",
        headline="No items yet",
        body="Create inventory items before entering stock movements, sales, or purchase documents.",
        primary_label="Create Item",
    ),
    "inventory.no_company": EmptyStateSpec(
        key="inventory.no_company",
        headline="Select an active company first",
        body="Inventory records are company-scoped. Choose the active company before managing inventory masters and movements.",
        primary_label="Open Companies",
    ),
    "management_reporting.no_selection": EmptyStateSpec(
        key="management_reporting.no_selection",
        headline="Select a record to continue",
        body="Choose the project, contract, account, or period needed to build this analysis.",
    ),
    "management_reporting.no_company": EmptyStateSpec(
        key="management_reporting.no_company",
        headline="Select an active company first",
        body="Management reports are company-scoped. Choose the active company before opening rollups and variance analysis.",
    ),
    "management_reporting.contract_summary.no_selection": EmptyStateSpec(
        key="management_reporting.contract_summary.no_selection",
        headline="Select a contract to continue",
        body="Choose a contract to view its financial summary, project rollup, and trend analysis.",
    ),
    "management_reporting.project_variance.no_selection": EmptyStateSpec(
        key="management_reporting.project_variance.no_selection",
        headline="Select a project to continue",
        body="Choose a project to review budget variance, cost-code performance, and trend analysis.",
    ),
    # ── Payroll empty states (P12.S1) ─────────────────────────────────────
    "payroll.no_company": EmptyStateSpec(
        key="payroll.no_company",
        headline="No active company selected",
        body="Payroll records are company-scoped. Select or create a company to manage employees, runs, and payslips.",
        primary_label="Open Companies",
    ),
    "payroll.runs.empty": EmptyStateSpec(
        key="payroll.runs.empty",
        headline="No payroll runs yet",
        body="Create a payroll run to calculate and approve employee pay for a period.",
        primary_label="New payroll run",
        secondary_label="Learn more",
        glyph="⟳",
    ),
    "payroll.people.empty": EmptyStateSpec(
        key="payroll.people.empty",
        headline="No employees yet",
        body="Hire the first employee to begin building the company headcount. Each employee needs a compensation profile before they can appear in a payroll run.",
        primary_label="Hire employee",
        secondary_label="Learn more",
        glyph="👤",
    ),
    "payroll.people.no_company": EmptyStateSpec(
        key="payroll.people.no_company",
        headline="No active company selected",
        body="Select a company to view and manage employees.",
        primary_label="Open Companies",
    ),
    "payroll.compensation.empty": EmptyStateSpec(
        key="payroll.compensation.empty",
        headline="No compensation records yet",
        body="Add a compensation record to define an employee's basic salary, currency, and effective dates. Every employee needs at least one active compensation record before they can be included in a payroll run.",
        primary_label="New compensation",
        glyph="💰",
    ),
    "payroll.compensation.no_company": EmptyStateSpec(
        key="payroll.compensation.no_company",
        headline="No active company selected",
        body="Select a company to view and manage compensation records.",
        primary_label="Open Companies",
    ),
    "payroll.variable_inputs.empty": EmptyStateSpec(
        key="payroll.variable_inputs.empty",
        headline="No variable inputs for this period",
        body="Variable inputs capture period-specific amounts such as overtime, bonuses, or one-off deductions. Create a batch for the current pay period and add individual input lines.",
        primary_label="New variable input batch",
        glyph="📋",
    ),
    "payroll.statutory.empty": EmptyStateSpec(
        key="payroll.statutory.empty",
        headline="No statutory records configured",
        body="Apply a statutory pack to define the tax rules, CNPS rates, and authority codes that govern payroll calculation in this jurisdiction.",
        primary_label="Apply statutory pack",
        secondary_label="Learn more",
        glyph="📑",
    ),
    "payroll.remittances.empty": EmptyStateSpec(
        key="payroll.remittances.empty",
        headline="No remittances yet",
        body="Remittances record statutory payments made to the tax authority and CNPS. They are created after a payroll run is posted to the general ledger.",
        glyph="🏛",
    ),
    "payroll.reports.empty": EmptyStateSpec(
        key="payroll.reports.empty",
        headline="No payroll reports available",
        body="Payroll reports become available once at least one payroll run has been calculated. Run payroll first, then return here to generate payslips and summaries.",
        glyph="📊",
    ),
    "payroll.setup.components.empty": EmptyStateSpec(
        key="payroll.setup.components.empty",
        headline="No payroll components defined",
        body="Payroll components are the building blocks of every payslip — base salary, allowances, deductions, and statutory contributions. Define at least the basic components before running payroll.",
        primary_label="New payroll component",
        glyph="⚙",
    ),
    "payroll.setup.departments.empty": EmptyStateSpec(
        key="payroll.setup.departments.empty",
        headline="No departments defined",
        body="Departments group employees for reporting and cost allocation. Add the first department to enable cost-centre payroll reporting.",
        primary_label="Add department",
        glyph="🏢",
    ),
    "payroll.setup.positions.empty": EmptyStateSpec(
        key="payroll.setup.positions.empty",
        headline="No positions defined",
        body="Positions represent the job titles in the company. Adding positions lets you pre-fill salary defaults when hiring new employees.",
        primary_label="Add position",
        glyph="📌",
    ),
    "payroll.dashboard.no_actions": EmptyStateSpec(
        key="payroll.dashboard.no_actions",
        headline="No outstanding actions",
        body="The current payroll period is ready. All employees are configured and there are no blocking issues.",
        glyph="✓",
    ),
    "payroll.dashboard.no_activity": EmptyStateSpec(
        key="payroll.dashboard.no_activity",
        headline="No payroll activity yet",
        body="Recent payroll runs will appear here once the first run is created and calculated.",
        glyph="∅",
    ),
}


def get_empty_state_spec(key: str) -> EmptyStateSpec:
    return EMPTY_STATE_LIBRARY.get(key, EMPTY_STATE_LIBRARY["generic.no_records"])


def build_empty_state(key: str, *, parent: QWidget | None = None) -> EmptyState:
    spec = get_empty_state_spec(key)
    widget = EmptyState(
        headline=spec.headline,
        body=spec.body,
        primary_label=spec.primary_label,
        secondary_label=spec.secondary_label,
        glyph=spec.glyph,
        parent=parent,
    )
    widget.setProperty("emptyStateKey", spec.key)
    set_accessible_metadata(widget, spec.headline, spec.body)
    return widget


def audit_empty_state_coverage(required_keys: set[str]) -> tuple[str, ...]:
    return tuple(sorted(key for key in required_keys if key not in EMPTY_STATE_LIBRARY))