"""Master-data-domain ambient thoughts.

Surfaces gaps and readiness hints when the user is browsing core
reference data (customers, suppliers, chart of accounts).  Every rule
here is purely read-from-navigation — no expensive list queries are
issued.  Pages that implement ``get_ambient_context()`` can supply
richer page-level keys in the future to make these more specific.

Codes produced
--------------
master.suppliers.tax_identifier_missing
    Fired when the nav is on Suppliers and the page context reports that
    the currently-viewed supplier lacks a tax identifier.  Falls back to
    a general reminder if the page does not supply the flag.

master.chart_of_accounts.role_mapping_reminder
    Fires once per session when the user is on the Chart of Accounts or
    Account Role Mappings page, reminding them that role mappings affect
    financial statement completeness.

master.customers.payment_terms_reminder
    Gentle hint when browsing Customers that payment terms drive
    automated due-date logic on invoices.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.shared.dto.ambient_thought_dto import (
    AmbientThoughtContextDTO,
    AmbientThoughtDTO,
)

if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry


_SUPPLIER_NAV = {nav_ids.SUPPLIERS, nav_ids.SUPPLIER_DETAIL}
_CUSTOMER_NAV = {nav_ids.CUSTOMERS, nav_ids.CUSTOMER_DETAIL}
_COA_NAV = {nav_ids.CHART_OF_ACCOUNTS, nav_ids.ACCOUNT_ROLE_MAPPINGS}


class MasterDataThoughtProvider:
    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> list[AmbientThoughtDTO]:
        nav = context.nav_id
        thoughts: list[AmbientThoughtDTO] = []

        # ── Suppliers: tax identifier completeness ────────────────────
        if nav in _SUPPLIER_NAV:
            # Page-context signal: the purchase bill dialog or supplier
            # detail page can set this key when it detects a gap.
            if context.page_value("supplier_tax_details_incomplete") is True:
                thoughts.append(
                    AmbientThoughtDTO(
                        thought_code="master.suppliers.tax_identifier_missing",
                        tone="caution",
                        summary=(
                            "This supplier has no tax identifier — recoverable VAT "
                            "claims may be rejected."
                        ),
                        detail=(
                            "OHADA and most VAT regimes require a valid supplier NIU "
                            "or tax registration number to support input-VAT recovery. "
                            "Add one in the supplier record before posting bills."
                        ),
                        confidence_label="High confidence",
                        relevance=0.9,
                        urgency=0.5,
                        confidence=0.95,
                        importance=0.85,
                        source_kind="rule",
                        nav_id=nav,
                        why_items=(
                            "Supplier tax_identifier field is empty.",
                            "Recoverable VAT requires a valid counterparty identifier.",
                        ),
                    )
                )
            else:
                # General reminder — lower score so it only shows when
                # nothing more urgent is competing.
                thoughts.append(
                    AmbientThoughtDTO(
                        thought_code="master.suppliers.tax_identifier_reminder",
                        tone="hint",
                        summary="Ensure every supplier has a tax identifier for VAT recovery.",
                        detail=(
                            "Input-VAT recovery on supplier bills requires each supplier "
                            "to carry a valid NIU or tax registration number."
                        ),
                        confidence_label="Likely",
                        relevance=0.4,
                        urgency=0.1,
                        confidence=0.7,
                        importance=0.5,
                        source_kind="rule",
                        nav_id=nav,
                        why_items=(
                            "Browsing the Suppliers master list.",
                            "Tax identifier completeness is a common gap in new setups.",
                        ),
                    )
                )

        # ── Customers: payment terms reminder ────────────────────────
        if nav in _CUSTOMER_NAV:
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="master.customers.payment_terms_reminder",
                    tone="hint",
                    summary="Payment terms on customer records drive invoice due-date logic.",
                    detail=(
                        "When a customer has a payment term assigned, Seeker "
                        "auto-calculates invoice due dates. Missing terms leave "
                        "due dates as manual entries, which can drift."
                    ),
                    confidence_label="Watch",
                    relevance=0.35,
                    urgency=0.05,
                    confidence=0.65,
                    importance=0.4,
                    source_kind="rule",
                    nav_id=nav,
                    why_items=(
                        "Browsing the Customers master list.",
                        "Payment terms govern automatic due-date calculation.",
                    ),
                )
            )

        # ── Chart of accounts: role mapping completeness reminder ─────
        if nav in _COA_NAV:
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="master.chart_of_accounts.role_mapping_reminder",
                    tone="hint",
                    summary="Account role mappings control how balances appear in financial statements.",
                    detail=(
                        "Accounts not mapped to a financial statement role may be "
                        "excluded from the Balance Sheet and P&L. Review mappings "
                        "before period-end reporting."
                    ),
                    confidence_label="Watch",
                    relevance=0.5,
                    urgency=0.2,
                    confidence=0.8,
                    importance=0.6,
                    source_kind="rule",
                    nav_id=nav,
                    why_items=(
                        "Viewing the Chart of Accounts or Role Mappings.",
                        "Unmapped accounts are excluded from financial statements.",
                    ),
                )
            )

        return thoughts
