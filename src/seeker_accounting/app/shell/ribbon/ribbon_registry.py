"""
RibbonRegistry — catalogue of ribbon surfaces keyed by context string.

Context strings are:

* navigation ids (e.g. ``"journals"``) for pages hosted in the main workspace
* ``"child:<kind>"`` (e.g. ``"child:journal_entry"``) for top-level child
  document windows

Modules register their surfaces by calling :meth:`RibbonRegistry.register`.
Slice 1 ships the built-in Journals register surface and the Journal Entry
child-window surface.
"""

from __future__ import annotations

from seeker_accounting.app.shell.ribbon.ribbon_models import (
    RibbonButtonDef,
    RibbonDividerDef,
    RibbonSurfaceDef,
)


# ── Related-page navigation spec ──────────────────────────────────────
#
# Each accounting surface exposes a small "Related" group at the end of
# its ribbon — shortcuts that jump to pages which are genuinely related
# (share data, live in the same setup flow, or are commonly used
# together). Kept deliberately tight (2–3 links per surface) so the
# ribbons stay focused and don't turn into a module-wide jump list.
#
# Shape: ``surface_key → tuple of (target_nav_id, label, icon_name)``.

RELATED_PAGES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "chart_of_accounts": (
        ("journals", "Journals", "file_text"),
        ("fiscal_periods", "Fiscal Periods", "clock"),
        ("tax_codes", "Tax Codes", "file_text"),
    ),
    "journals": (
        ("chart_of_accounts", "Chart of Accounts", "layout_grid"),
        ("fiscal_periods", "Fiscal Periods", "clock"),
    ),
    "fiscal_periods": (
        ("journals", "Journals", "file_text"),
        ("chart_of_accounts", "Chart of Accounts", "layout_grid"),
    ),
    "payment_terms": (
        ("tax_codes", "Tax Codes", "file_text"),
        ("document_sequences", "Document Sequences", "file_text"),
    ),
    "tax_codes": (
        ("chart_of_accounts", "Chart of Accounts", "layout_grid"),
        ("account_role_mappings", "Role Mappings", "list_checks"),
        ("payment_terms", "Payment Terms", "clock"),
    ),
    "document_sequences": (
        ("payment_terms", "Payment Terms", "clock"),
        ("tax_codes", "Tax Codes", "file_text"),
    ),
    "account_role_mappings": (
        ("chart_of_accounts", "Chart of Accounts", "layout_grid"),
        ("tax_codes", "Tax Codes", "file_text"),
    ),
}


def related_goto_command_id(surface_key: str, target_nav_id: str) -> str:
    """Canonical command id for a 'jump to related page' ribbon button."""
    return f"{surface_key}.goto_{target_nav_id}"


class RibbonRegistry:
    """In-memory registry. Not thread-safe — UI-thread access only."""

    def __init__(self) -> None:
        self._surfaces: dict[str, RibbonSurfaceDef] = {}
        self._register_built_in()

    # ── Public API ────────────────────────────────────────────────────

    def register(self, surface: RibbonSurfaceDef) -> None:
        self._surfaces[surface.surface_key] = surface

    def get(self, surface_key: str) -> RibbonSurfaceDef | None:
        return self._surfaces.get(surface_key)

    def has(self, surface_key: str) -> bool:
        return surface_key in self._surfaces

    @staticmethod
    def child_window_key(kind: str) -> str:
        """Canonical surface key for a child-window kind (e.g. ``journal_entry``)."""
        return f"child:{kind}"

    # ── Built-in surfaces ─────────────────────────────────────────────

    def _register_built_in(self) -> None:
        # Journals register (main workspace)
        self.register(
            RibbonSurfaceDef(
                surface_key="journals",
                items=(
                    RibbonButtonDef(
                        command_id="journals.new_entry",
                        label="New Entry",
                        icon_name="plus",
                        tooltip="Create a new draft journal entry",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="journals.edit_draft",
                        label="Edit Draft",
                        icon_name="edit",
                        tooltip="Edit the selected draft entry",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="journals.delete_draft",
                        label="Delete Draft",
                        icon_name="trash",
                        tooltip="Delete the selected draft entry",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_crud"),
                    RibbonButtonDef(
                        command_id="journals.post_entry",
                        label="Post Entry",
                        icon_name="check_square",
                        tooltip="Post the selected draft entry",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="journals.batch_post",
                        label="Batch Post",
                        icon_name="list_checks",
                        tooltip="Post all checked draft entries",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_posting"),
                    RibbonButtonDef(
                        command_id="journals.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the entry list",
                    ),
                    RibbonButtonDef(
                        command_id="journals.print_entry",
                        label="Print",
                        icon_name="printer",
                        tooltip="Print the selected entry",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="journals.export_list",
                        label="Export List",
                        icon_name="download",
                        tooltip="Export the entry register",
                        default_enabled=False,
                    ),
                ),
            )
        )

        # Journal Entry child-window ribbon
        self.register(
            RibbonSurfaceDef(
                surface_key=self.child_window_key("journal_entry"),
                items=(
                    RibbonButtonDef(
                        command_id="journal_entry.save",
                        label="Save",
                        icon_name="save",
                        tooltip="Save changes",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="journal_entry.save_and_new",
                        label="Save & New",
                        icon_name="plus",
                        tooltip="Save this entry and start a fresh one",
                        default_enabled=True,
                    ),
                    RibbonDividerDef(key="after_save"),
                    RibbonButtonDef(
                        command_id="journal_entry.post",
                        label="Post",
                        icon_name="check_square",
                        tooltip="Post this entry",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="journal_entry.delete",
                        label="Delete",
                        icon_name="trash",
                        tooltip="Delete this draft entry",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_post"),
                    RibbonButtonDef(
                        command_id="journal_entry.print",
                        label="Print",
                        icon_name="printer",
                        tooltip="Print this entry",
                    ),
                    RibbonDividerDef(key="before_close"),
                    RibbonButtonDef(
                        command_id="journal_entry.close",
                        label="Close",
                        icon_name="x",
                        tooltip="Close the entry window",
                    ),
                ),
            )
        )

        # ── Contracts / Projects registers + workspaces ───────────────
        self.register(
            RibbonSurfaceDef(
                surface_key="contracts",
                items=(
                    RibbonButtonDef(
                        command_id="contracts.new",
                        label="New Contract",
                        icon_name="plus",
                        tooltip="Create a new contract",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="contracts.open_workspace",
                        label="Open Workspace",
                        icon_name="layout_grid",
                        tooltip="Open the selected contract workspace",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contracts.edit",
                        label="Edit Basics",
                        icon_name="edit",
                        tooltip="Edit the selected contract",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_start"),
                    RibbonButtonDef(
                        command_id="contracts.activate",
                        label="Activate",
                        icon_name="check_square",
                        tooltip="Activate the selected contract",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contracts.hold",
                        label="Put On Hold",
                        icon_name="clock",
                        tooltip="Move the selected contract to on-hold",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contracts.complete",
                        label="Complete",
                        icon_name="check_square",
                        tooltip="Mark the selected contract as completed",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contracts.close_record",
                        label="Close Contract",
                        icon_name="lock",
                        tooltip="Close the selected contract",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contracts.cancel",
                        label="Cancel",
                        icon_name="x",
                        tooltip="Cancel the selected contract",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_lifecycle"),
                    RibbonButtonDef(
                        command_id="contracts.change_orders",
                        label="Change Orders",
                        icon_name="list_checks",
                        tooltip="Manage change orders for the selected contract",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contracts.summary",
                        label="Contract Summary",
                        icon_name="file_text",
                        tooltip="Open the contract summary report for the selection",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_analysis"),
                    RibbonButtonDef(
                        command_id="contracts.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the contract register",
                    ),
                ),
            )
        )

        self.register(
            RibbonSurfaceDef(
                surface_key="projects",
                items=(
                    RibbonButtonDef(
                        command_id="projects.new",
                        label="New Project",
                        icon_name="plus",
                        tooltip="Create a new project",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="projects.open_workspace",
                        label="Open Workspace",
                        icon_name="layout_grid",
                        tooltip="Open the selected project workspace",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.edit",
                        label="Edit Basics",
                        icon_name="edit",
                        tooltip="Edit the selected project",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_start"),
                    RibbonButtonDef(
                        command_id="projects.activate",
                        label="Activate",
                        icon_name="check_square",
                        tooltip="Activate the selected project",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.hold",
                        label="Put On Hold",
                        icon_name="clock",
                        tooltip="Move the selected project to on-hold",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.complete",
                        label="Complete",
                        icon_name="check_square",
                        tooltip="Mark the selected project as completed",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.close_record",
                        label="Close Project",
                        icon_name="lock",
                        tooltip="Close the selected project",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.cancel",
                        label="Cancel",
                        icon_name="x",
                        tooltip="Cancel the selected project",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_lifecycle"),
                    RibbonButtonDef(
                        command_id="projects.jobs",
                        label="Jobs",
                        icon_name="list_checks",
                        tooltip="Manage jobs for the selected project",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.budgets",
                        label="Budgets",
                        icon_name="file_text",
                        tooltip="Manage budget versions for the selected project",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.commitments",
                        label="Commitments",
                        icon_name="file_text",
                        tooltip="Manage commitments for the selected project",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.cost_code_library",
                        label="Cost Code Library",
                        icon_name="list_checks",
                        tooltip="Open the company cost code library",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_workbenches"),
                    RibbonButtonDef(
                        command_id="projects.variance",
                        label="Variance",
                        icon_name="file_text",
                        tooltip="Open project variance analysis for the selection",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="projects.contract_summary",
                        label="Contract Summary",
                        icon_name="file_text",
                        tooltip="Open the linked contract summary for the selection",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_analysis"),
                    RibbonButtonDef(
                        command_id="projects.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the project register",
                    ),
                ),
            )
        )

        self.register(
            RibbonSurfaceDef(
                surface_key=self.child_window_key("contract_workspace"),
                items=(
                    RibbonButtonDef(
                        command_id="contract_workspace.edit",
                        label="Edit Basics",
                        icon_name="edit",
                        tooltip="Edit this contract",
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload this contract workspace",
                    ),
                    RibbonDividerDef(key="after_record"),
                    RibbonButtonDef(
                        command_id="contract_workspace.activate",
                        label="Activate",
                        icon_name="check_square",
                        tooltip="Activate this contract",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.hold",
                        label="Put On Hold",
                        icon_name="clock",
                        tooltip="Put this contract on hold",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.complete",
                        label="Complete",
                        icon_name="check_square",
                        tooltip="Mark this contract as completed",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.close_record",
                        label="Close Contract",
                        icon_name="lock",
                        tooltip="Close this contract",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.cancel",
                        label="Cancel",
                        icon_name="x",
                        tooltip="Cancel this contract",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_lifecycle"),
                    RibbonButtonDef(
                        command_id="contract_workspace.co_new",
                        label="New CO",
                        icon_name="plus",
                        tooltip="Create a new change order for this contract",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.co_edit",
                        label="Edit CO",
                        icon_name="edit",
                        tooltip="Edit the selected draft change order",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.co_submit",
                        label="Submit CO",
                        icon_name="upload",
                        tooltip="Submit the selected draft change order",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.co_approve",
                        label="Approve CO",
                        icon_name="check_square",
                        tooltip="Approve the selected submitted change order",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.co_reject",
                        label="Reject CO",
                        icon_name="x",
                        tooltip="Reject the selected submitted change order",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.co_cancel",
                        label="Cancel CO",
                        icon_name="x",
                        tooltip="Cancel the selected change order",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_change_orders"),
                    RibbonButtonDef(
                        command_id="contract_workspace.project_new",
                        label="New Project",
                        icon_name="plus",
                        tooltip="Create a new project linked to this contract",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.project_open",
                        label="Open Project",
                        icon_name="layout_grid",
                        tooltip="Open the selected project in its own workspace",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="contract_workspace.project_edit",
                        label="Edit Project",
                        icon_name="edit",
                        tooltip="Edit the selected project",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_projects"),
                    RibbonButtonDef(
                        command_id="contract_workspace.summary",
                        label="Contract Summary",
                        icon_name="file_text",
                        tooltip="Open the contract summary report for this contract",
                    ),
                    RibbonDividerDef(key="before_close"),
                    RibbonButtonDef(
                        command_id="contract_workspace.window_close",
                        label="Close Window",
                        icon_name="x",
                        tooltip="Close this workspace window",
                    ),
                ),
            )
        )

        self.register(
            RibbonSurfaceDef(
                surface_key=self.child_window_key("project_workspace"),
                items=(
                    RibbonButtonDef(
                        command_id="project_workspace.edit",
                        label="Edit Basics",
                        icon_name="edit",
                        tooltip="Edit this project",
                    ),
                    RibbonDividerDef(key="after_record"),
                    RibbonButtonDef(
                        command_id="project_workspace.activate",
                        label="Activate",
                        icon_name="check_square",
                        tooltip="Activate this project",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.hold",
                        label="Put On Hold",
                        icon_name="clock",
                        tooltip="Put this project on hold",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.complete",
                        label="Complete",
                        icon_name="check_square",
                        tooltip="Mark this project as completed",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.close_record",
                        label="Close Project",
                        icon_name="lock",
                        tooltip="Close this project",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.cancel",
                        label="Cancel",
                        icon_name="x",
                        tooltip="Cancel this project",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_lifecycle"),
                    RibbonButtonDef(
                        command_id="project_workspace.jobs",
                        label="Jobs",
                        icon_name="list_checks",
                        tooltip="Manage jobs for this project",
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.budgets",
                        label="Budgets",
                        icon_name="file_text",
                        tooltip="Manage budget versions for this project",
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.new_budget",
                        label="New Budget",
                        icon_name="plus",
                        tooltip="Create a new budget with lines in one workspace",
                        variant="primary",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.revise_budget",
                        label="Revise Budget",
                        icon_name="edit",
                        tooltip="Clone the current approved budget into a new draft for revision",
                        variant="primary",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.commitments",
                        label="Commitments",
                        icon_name="file_text",
                        tooltip="Manage commitments for this project",
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.cost_code_library",
                        label="Cost Code Library",
                        icon_name="list_checks",
                        tooltip="Open the company cost code library",
                    ),
                    RibbonDividerDef(key="after_workbenches"),
                    RibbonButtonDef(
                        command_id="project_workspace.record_cost",
                        label="Record Cost",
                        icon_name="plus",
                        tooltip="Record a cost journal entry and tag it to this project",
                        variant="primary",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.variance",
                        label="Variance",
                        icon_name="file_text",
                        tooltip="Open project variance analysis",
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.contract_summary",
                        label="Contract Summary",
                        icon_name="file_text",
                        tooltip="Open the linked contract summary",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="project_workspace.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload this project workspace",
                    ),
                    RibbonDividerDef(key="before_close"),
                    RibbonButtonDef(
                        command_id="project_workspace.window_close",
                        label="Close Window",
                        icon_name="x",
                        tooltip="Close this workspace window",
                    ),
                ),
            )
        )

        # ── Sales registers ────────────────────────────────────────────
        self._register_document_register(
            surface_key="sales_invoices",
            prefix="sales_invoices",
            new_label="New Invoice",
            new_tooltip="Create a new draft sales invoice",
            edit_label="Edit Draft",
            edit_tooltip="Edit the selected draft invoice",
            cancel_label="Cancel Draft",
            cancel_tooltip="Cancel the selected draft invoice",
            post_label="Post Invoice",
            post_tooltip="Post the selected draft invoice",
            print_label="Print / Export",
            print_tooltip="Print or export the selected invoice",
        )
        self._register_document_register(
            surface_key="sales_orders",
            prefix="sales_orders",
            new_label="New Order",
            new_tooltip="Create a new sales order",
            edit_label="Edit Order",
            edit_tooltip="Edit the selected order",
            cancel_label="Cancel Order",
            cancel_tooltip="Cancel the selected order",
            post_label="Confirm Order",
            post_tooltip="Confirm the selected order",
            print_label="Print / Export",
            print_tooltip="Print or export the selected order",
        )
        self._register_document_register(
            surface_key="customer_quotes",
            prefix="customer_quotes",
            new_label="New Quote",
            new_tooltip="Create a new customer quote",
            edit_label="Edit Quote",
            edit_tooltip="Edit the selected quote",
            cancel_label="Cancel Quote",
            cancel_tooltip="Cancel the selected quote",
            post_label="Send Quote",
            post_tooltip="Mark the selected quote as sent",
            print_label="Print / Export",
            print_tooltip="Print or export the selected quote",
        )
        self._register_document_register(
            surface_key="sales_credit_notes",
            prefix="sales_credit_notes",
            new_label="New Credit Note",
            new_tooltip="Create a new draft credit note",
            edit_label="Edit Draft",
            edit_tooltip="Edit the selected draft credit note",
            cancel_label="Cancel Draft",
            cancel_tooltip="Cancel the selected draft credit note",
            post_label="Post Credit Note",
            post_tooltip="Post the selected draft credit note",
            print_label="Print / Export",
            print_tooltip="Print or export the selected credit note",
        )
        self._register_document_register(
            surface_key="customer_receipts",
            prefix="customer_receipts",
            new_label="New Receipt",
            new_tooltip="Record a new customer receipt",
            edit_label="Edit Draft",
            edit_tooltip="Edit the selected draft receipt",
            cancel_label="Cancel Draft",
            cancel_tooltip="Cancel the selected draft receipt",
            post_label="Post Receipt",
            post_tooltip="Post the selected draft receipt",
            print_label="Print / Export",
            print_tooltip="Print or export the selected receipt",
        )

        # ── Purchases registers ────────────────────────────────────────
        self._register_document_register(
            surface_key="purchase_bills",
            prefix="purchase_bills",
            new_label="New Bill",
            new_tooltip="Create a new draft supplier bill",
            edit_label="Edit Draft",
            edit_tooltip="Edit the selected draft bill",
            cancel_label="Cancel Draft",
            cancel_tooltip="Cancel the selected draft bill",
            post_label="Post Bill",
            post_tooltip="Post the selected draft bill",
            print_label="Print / Export",
            print_tooltip="Print or export the selected bill",
        )
        self._register_document_register(
            surface_key="purchase_orders",
            prefix="purchase_orders",
            new_label="New Order",
            new_tooltip="Create a new purchase order",
            edit_label="Edit Order",
            edit_tooltip="Edit the selected order",
            cancel_label="Cancel Order",
            cancel_tooltip="Cancel the selected order",
            post_label="Confirm Order",
            post_tooltip="Confirm the selected order",
            print_label="Print / Export",
            print_tooltip="Print or export the selected order",
        )
        self._register_document_register(
            surface_key="purchase_credit_notes",
            prefix="purchase_credit_notes",
            new_label="New Credit Note",
            new_tooltip="Create a new draft supplier credit note",
            edit_label="Edit Draft",
            edit_tooltip="Edit the selected draft credit note",
            cancel_label="Cancel Draft",
            cancel_tooltip="Cancel the selected draft credit note",
            post_label="Post Credit Note",
            post_tooltip="Post the selected draft credit note",
            print_label="Print / Export",
            print_tooltip="Print or export the selected credit note",
        )
        self._register_document_register(
            surface_key="supplier_payments",
            prefix="supplier_payments",
            new_label="New Payment",
            new_tooltip="Record a new supplier payment",
            edit_label="Edit Draft",
            edit_tooltip="Edit the selected draft payment",
            cancel_label="Cancel Draft",
            cancel_tooltip="Cancel the selected draft payment",
            post_label="Post Payment",
            post_tooltip="Post the selected draft payment",
            print_label="Print / Export",
            print_tooltip="Print or export the selected payment",
        )

        # ── Treasury registers ─────────────────────────────────────────
        self._register_document_register(
            surface_key="treasury_transactions",
            prefix="treasury_transactions",
            new_label="New Transaction",
            new_tooltip="Record a new treasury transaction",
            edit_label="Edit Draft",
            edit_tooltip="Edit the selected draft transaction",
            cancel_label="Cancel Draft",
            cancel_tooltip="Cancel the selected draft transaction",
            post_label="Post Transaction",
            post_tooltip="Post the selected draft transaction",
            print_label="Print / Export",
            print_tooltip="Print or export the selected transaction",
        )
        self._register_document_register(
            surface_key="treasury_transfers",
            prefix="treasury_transfers",
            new_label="New Transfer",
            new_tooltip="Record a new treasury transfer",
            edit_label="Edit Draft",
            edit_tooltip="Edit the selected draft transfer",
            cancel_label="Cancel Draft",
            cancel_tooltip="Cancel the selected draft transfer",
            post_label="Post Transfer",
            post_tooltip="Post the selected draft transfer",
            print_label="Print / Export",
            print_tooltip="Print or export the selected transfer",
        )

        # ── Reference entity registers ─────────────────────────────────
        self._register_entity_register(
            surface_key="customers",
            prefix="customers",
            new_label="New Customer",
            edit_label="Edit Customer",
            deactivate_label="Deactivate",
        )
        self._register_entity_register(
            surface_key="suppliers",
            prefix="suppliers",
            new_label="New Supplier",
            edit_label="Edit Supplier",
            deactivate_label="Deactivate",
        )
        self._register_entity_register(
            surface_key="items",
            prefix="items",
            new_label="New Item",
            edit_label="Edit Item",
            deactivate_label="Deactivate",
        )

        # Chart of Accounts has extra actions: Seed / Import / Role Mappings.
        self.register(
            RibbonSurfaceDef(
                surface_key="chart_of_accounts",
                items=(
                    RibbonButtonDef(
                        command_id="chart_of_accounts.new",
                        label="New Account",
                        icon_name="plus",
                        tooltip="Create a new account",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="chart_of_accounts.edit",
                        label="Edit Account",
                        icon_name="edit",
                        tooltip="Edit the selected account",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="chart_of_accounts.deactivate",
                        label="Deactivate",
                        icon_name="x",
                        tooltip="Deactivate the selected account",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_crud"),
                    RibbonButtonDef(
                        command_id="chart_of_accounts.wizard",
                        label="Customize Chart",
                        icon_name="wand",
                        tooltip="Launch the guided chart setup and mapping wizard",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="chart_of_accounts.seed",
                        label="Seed OHADA",
                        icon_name="file_text",
                        tooltip="Seed the built-in OHADA chart template",
                    ),
                    RibbonButtonDef(
                        command_id="chart_of_accounts.import",
                        label="Import Template",
                        icon_name="download",
                        tooltip="Import a chart template file",
                    ),
                    RibbonButtonDef(
                        command_id="chart_of_accounts.role_mappings",
                        label="Role Mappings",
                        icon_name="list_checks",
                        tooltip="Manage account role mappings",
                    ),
                    RibbonDividerDef(key="after_setup"),
                    RibbonButtonDef(
                        command_id="chart_of_accounts.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the chart",
                    ),
                    RibbonButtonDef(
                        command_id="chart_of_accounts.export_list",
                        label="Export List",
                        icon_name="download",
                        tooltip="Export the chart list",
                        default_enabled=False,
                    ),
                ),
            )
        )

        # ── Accounting reference / setup pages ─────────────────────────

        self.register(
            RibbonSurfaceDef(
                surface_key="fiscal_periods",
                items=(
                    RibbonButtonDef(
                        command_id="fiscal_periods.wizard",
                        label="Fiscal Year Wizard",
                        icon_name="wand",
                        tooltip="Guided setup — create a fiscal year and generate its periods in one flow",
                        variant="primary",
                    ),
                    RibbonDividerDef(key="after_wizard"),
                    RibbonButtonDef(
                        command_id="fiscal_periods.new_year",
                        label="New Fiscal Year",
                        icon_name="plus",
                        tooltip="Create a new fiscal year",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="fiscal_periods.generate_periods",
                        label="Generate Periods",
                        icon_name="list_checks",
                        tooltip="Generate periods for the selected fiscal year",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_year"),
                    RibbonButtonDef(
                        command_id="fiscal_periods.open_period",
                        label="Open Period",
                        icon_name="unlock",
                        tooltip="Re-open the selected closed period",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="fiscal_periods.close_period",
                        label="Close Period",
                        icon_name="lock",
                        tooltip="Close the selected open period",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="fiscal_periods.reopen_period",
                        label="Reopen Period",
                        icon_name="unlock",
                        tooltip="Reopen the selected closed period",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="fiscal_periods.lock_period",
                        label="Lock Period",
                        icon_name="lock",
                        tooltip="Lock the selected period — no further posting allowed",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_actions"),
                    RibbonButtonDef(
                        command_id="fiscal_periods.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the fiscal calendar",
                    ),
                ),
            )
        )

        self._register_entity_register(
            surface_key="payment_terms",
            prefix="payment_terms",
            new_label="New Terms",
            edit_label="Edit Terms",
            deactivate_label="Deactivate",
        )

        self.register(
            RibbonSurfaceDef(
                surface_key="tax_codes",
                items=(
                    RibbonButtonDef(
                        command_id="tax_codes.new",
                        label="New Tax Code",
                        icon_name="plus",
                        tooltip="Create a new tax code",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="tax_codes.edit",
                        label="Edit Tax Code",
                        icon_name="edit",
                        tooltip="Edit the selected tax code",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="tax_codes.deactivate",
                        label="Deactivate",
                        icon_name="x",
                        tooltip="Deactivate the selected tax code",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_crud"),
                    RibbonButtonDef(
                        command_id="tax_codes.account_mappings",
                        label="Account Mappings",
                        icon_name="list_checks",
                        tooltip="Configure tax account mappings",
                    ),
                    RibbonDividerDef(key="after_mappings"),
                    RibbonButtonDef(
                        command_id="tax_codes.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the tax code list",
                    ),
                    RibbonButtonDef(
                        command_id="tax_codes.export_list",
                        label="Export List",
                        icon_name="download",
                        tooltip="Export the tax code list",
                        default_enabled=False,
                    ),
                ),
            )
        )

        self.register(
            RibbonSurfaceDef(
                surface_key="document_sequences",
                items=(
                    RibbonButtonDef(
                        command_id="document_sequences.new",
                        label="New Sequence",
                        icon_name="plus",
                        tooltip="Create a new document sequence",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="document_sequences.edit",
                        label="Edit Sequence",
                        icon_name="edit",
                        tooltip="Edit the selected sequence",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="document_sequences.preview",
                        label="Preview Number",
                        icon_name="eye",
                        tooltip="Preview the next number this sequence will generate",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="document_sequences.deactivate",
                        label="Deactivate",
                        icon_name="x",
                        tooltip="Deactivate the selected sequence",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_crud"),
                    RibbonButtonDef(
                        command_id="document_sequences.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the sequence list",
                    ),
                ),
            )
        )

        self.register(
            RibbonSurfaceDef(
                surface_key="account_role_mappings",
                items=(
                    RibbonButtonDef(
                        command_id="account_role_mappings.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload account role mappings",
                    ),
                ),
            )
        )

        # Payroll sub-context surfaces (Slice P1 — Setup + Calculation).
        self._register_payroll_surfaces()

        # Decorate accounting surfaces with their "Related" navigation group.
        for surface_key in RELATED_PAGES:
            self._append_related_links(surface_key)

    # ── Payroll surfaces ──────────────────────────────────────────────

    def _register_payroll_surfaces(self) -> None:
        """Register tab-scoped ribbon surfaces for the payroll workspaces.

        Surface keys follow ``<nav_id>.<tab_subkey>[.<selection_variant>]``
        so each tab — and, where useful, each selection state — can
        swap to its own ribbon. Slice P1 covers ``payroll_setup`` and
        ``payroll_calculation``; accounting and operations surfaces are
        registered in later slices.

        The command ids below must match the ``_ribbon_commands`` maps in
        the corresponding pages — changes on one side require matching
        changes on the other.
        """

        # ── payroll_setup / Company Settings ──────────────────────────
        settings_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_setup.activation_wizard",
                label="Activation Wizard",
                icon_name="zap",
                tooltip="Activate payroll for this company in a guided flow",
                variant="primary",
            ),
            RibbonDividerDef(key="after_wizard"),
            RibbonButtonDef(
                command_id="payroll_setup.configure_settings",
                label="Configure Settings",
                icon_name="settings",
                tooltip="Edit company payroll configuration",
            ),
            RibbonButtonDef(
                command_id="payroll_setup.apply_pack",
                label="Apply Statutory Pack",
                icon_name="file_text",
                tooltip="Seed components and rules from a statutory pack",
            ),
            RibbonDividerDef(key="after_primary"),
            RibbonButtonDef(
                command_id="payroll_setup.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload payroll setup",
            ),
            RibbonDividerDef(key="before_related"),
            RibbonButtonDef(
                command_id="payroll_setup.open_calculation",
                label="Payroll Runs",
                icon_name="calculator",
                tooltip="Open the payroll calculation workspace",
            ),
            RibbonButtonDef(
                command_id="payroll_setup.open_validation",
                label="Validation",
                icon_name="list_checks",
                tooltip="Open the payroll validation workspace",
            ),
        )
        self.register(RibbonSurfaceDef(surface_key="payroll_setup.settings", items=settings_items))
        # Nav-id level fallback — used when no tab is active yet.
        self.register(RibbonSurfaceDef(surface_key="payroll_setup", items=settings_items))

        # ── payroll_setup / Employees (variants by selection) ─────────
        employees_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_setup.open_employee_hub",
                label="Employee Hub",
                icon_name="user",
                tooltip="Open the full-window hub for the selected employee",
                variant="primary",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_hub"),
            RibbonButtonDef(
                command_id="payroll_setup.hire_employee_wizard",
                label="Hire Employee",
                icon_name="user_plus",
                tooltip="Hire a new employee with a guided wizard",
            ),
            RibbonButtonDef(
                command_id="payroll_setup.employee_payroll_setup_wizard",
                label="Payroll Setup",
                icon_name="wand",
                tooltip="Adaptive wizard that fills in missing payroll setup for the selected employee",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_wizard"),
            RibbonButtonDef(
                command_id="payroll_setup.new_employee",
                label="New Employee",
                icon_name="user_plus",
                tooltip="Create a new employee record (expert form)",
            ),
            RibbonButtonDef(
                command_id="payroll_setup.edit_employee",
                label="Edit",
                icon_name="edit",
                tooltip="Edit the selected employee",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_setup.deactivate_employee",
                label="Deactivate",
                icon_name="user_x",
                tooltip="Deactivate the selected employee",
                variant="danger",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_crud"),
            RibbonButtonDef(
                command_id="payroll_setup.compensation_change_wizard",
                label="Compensation Change",
                icon_name="trending_up",
                tooltip="Record a salary / profile change for the selected employee",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_comp_change"),
            RibbonButtonDef(
                command_id="payroll_setup.manage_departments",
                label="Departments",
                icon_name="layout_grid",
                tooltip="Manage departments",
            ),
            RibbonButtonDef(
                command_id="payroll_setup.manage_positions",
                label="Positions",
                icon_name="list_checks",
                tooltip="Manage positions",
            ),
            RibbonDividerDef(key="after_reference"),
            RibbonButtonDef(
                command_id="payroll_setup.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload the employee list",
            ),
        )
        for variant in ("none", "active", "inactive"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_setup.employees.{variant}",
                    items=employees_items,
                )
            )

        # ── payroll_setup / Payroll Components (variants by selection) ─
        components_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_setup.new_component",
                label="New Component",
                icon_name="plus",
                tooltip="Create a new payroll component",
                variant="primary",
            ),
            RibbonButtonDef(
                command_id="payroll_setup.edit_component",
                label="Edit",
                icon_name="edit",
                tooltip="Edit the selected component",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_setup.deactivate_component",
                label="Deactivate",
                icon_name="x",
                tooltip="Deactivate the selected component",
                variant="danger",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_crud"),
            RibbonButtonDef(
                command_id="payroll_setup.apply_pack",
                label="Apply Statutory Pack",
                icon_name="file_text",
                tooltip="Seed components from a statutory pack",
            ),
            RibbonDividerDef(key="before_refresh"),
            RibbonButtonDef(
                command_id="payroll_setup.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload the component list",
            ),
        )
        for variant in ("none", "selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_setup.components.{variant}",
                    items=components_items,
                )
            )

        # ── payroll_setup / Payroll Rules (variants by selection) ─────
        rules_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_setup.new_rule_set",
                label="New Rule Set",
                icon_name="plus",
                tooltip="Create a new payroll rule set",
                variant="primary",
            ),
            RibbonButtonDef(
                command_id="payroll_setup.edit_rule_set",
                label="Edit",
                icon_name="edit",
                tooltip="Edit the selected rule set",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_setup.edit_brackets",
                label="Brackets",
                icon_name="list_checks",
                tooltip="Edit brackets for the selected rule set",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_setup.deactivate_rule_set",
                label="Deactivate",
                icon_name="x",
                tooltip="Deactivate the selected rule set",
                variant="danger",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_crud"),
            RibbonButtonDef(
                command_id="payroll_setup.apply_pack",
                label="Apply Statutory Pack",
                icon_name="file_text",
                tooltip="Seed rules from a statutory pack",
            ),
            RibbonDividerDef(key="before_refresh"),
            RibbonButtonDef(
                command_id="payroll_setup.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload the rule list",
            ),
        )
        for variant in ("none", "selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_setup.rules.{variant}",
                    items=rules_items,
                )
            )

        # ── payroll_calculation / Compensation Profiles ───────────────
        profiles_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_calculation.new_profile",
                label="New Profile",
                icon_name="plus",
                tooltip="Create a new compensation profile",
                variant="primary",
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.edit_profile",
                label="Edit",
                icon_name="edit",
                tooltip="Edit the selected profile",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.toggle_profile",
                label="Toggle Active",
                icon_name="toggle_left",
                tooltip="Toggle the active state of the selected profile",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_crud"),
            RibbonButtonDef(
                command_id="payroll_calculation.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload profiles",
            ),
            RibbonDividerDef(key="before_related"),
            RibbonButtonDef(
                command_id="payroll_calculation.open_setup",
                label="Payroll Setup",
                icon_name="settings",
                tooltip="Open the payroll setup workspace",
            ),
        )
        for variant in ("none", "selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_calculation.profiles.{variant}",
                    items=profiles_items,
                )
            )
        # Nav-id level fallback for the calculation workspace.
        self.register(RibbonSurfaceDef(surface_key="payroll_calculation", items=profiles_items))

        # ── payroll_calculation / Recurring Components ────────────────
        assignments_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_calculation.new_assignment",
                label="Assign Component",
                icon_name="plus",
                tooltip="Assign a recurring component to an employee",
                variant="primary",
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.edit_assignment",
                label="Edit",
                icon_name="edit",
                tooltip="Edit the selected assignment",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.toggle_assignment",
                label="Toggle Active",
                icon_name="toggle_left",
                tooltip="Toggle the active state of the selected assignment",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_crud"),
            RibbonButtonDef(
                command_id="payroll_calculation.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload assignments",
            ),
        )
        for variant in ("none", "selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_calculation.assignments.{variant}",
                    items=assignments_items,
                )
            )

        # ── payroll_calculation / Variable Inputs ─────────────────────
        inputs_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_calculation.new_batch",
                label="New Batch",
                icon_name="plus",
                tooltip="Start a new variable input batch",
                variant="primary",
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.open_batch",
                label="Open Batch",
                icon_name="folder_open",
                tooltip="Open the selected batch",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_crud"),
            RibbonButtonDef(
                command_id="payroll_calculation.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload batches",
            ),
        )
        for variant in ("none", "selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_calculation.inputs.{variant}",
                    items=inputs_items,
                )
            )

        # ── payroll_calculation / Payroll Runs (variants by selection) ─
        runs_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_calculation.payroll_run_wizard",
                label="Payroll Run Wizard",
                icon_name="wand",
                tooltip="Guided payroll run: create, calculate, approve",
                variant="primary",
            ),
            RibbonDividerDef(key="after_wizard_run"),
            RibbonButtonDef(
                command_id="payroll_calculation.new_run",
                label="New Run",
                icon_name="plus",
                tooltip="Create a new payroll run (expert fast path)",
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.calculate_run",
                label="Calculate",
                icon_name="calculator",
                tooltip="Calculate the selected run",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.approve_run",
                label="Approve",
                icon_name="check_square",
                tooltip="Approve the selected calculated run",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.void_run",
                label="Void",
                icon_name="x",
                tooltip="Void the selected run",
                variant="danger",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_lifecycle"),
            RibbonButtonDef(
                command_id="payroll_calculation.employee_detail",
                label="Employee Detail",
                icon_name="user",
                tooltip="Open employee result detail for the selected row",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_calculation.project_allocations",
                label="Project Allocations",
                icon_name="layout_grid",
                tooltip="Edit project allocations for the selected employee",
                default_enabled=False,
            ),
            RibbonDividerDef(key="before_refresh"),
            RibbonButtonDef(
                command_id="payroll_calculation.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload runs",
            ),
        )
        for variant in ("none", "run_selected", "employee_selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_calculation.runs.{variant}",
                    items=runs_items,
                )
            )

        # ── Child window: payroll input batch workbench (P2) ──────────
        self.register(
            RibbonSurfaceDef(
                surface_key=self.child_window_key("payroll_input_batch"),
                items=(
                    RibbonButtonDef(
                        command_id="payroll_input_batch.add_line",
                        label="Add Line",
                        icon_name="plus",
                        tooltip="Add a new input line",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="payroll_input_batch.edit_line",
                        label="Edit Line",
                        icon_name="edit",
                        tooltip="Edit the selected line",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="payroll_input_batch.delete_line",
                        label="Delete Line",
                        icon_name="x",
                        tooltip="Delete the selected line",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_lines"),
                    RibbonButtonDef(
                        command_id="payroll_input_batch.approve",
                        label="Approve Batch",
                        icon_name="check_square",
                        tooltip="Approve and lock this batch",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="payroll_input_batch.void",
                        label="Void Batch",
                        icon_name="x",
                        tooltip="Void this batch",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="before_utility"),
                    RibbonButtonDef(
                        command_id="payroll_input_batch.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the batch",
                    ),
                    RibbonButtonDef(
                        command_id="payroll_input_batch.close",
                        label="Close",
                        icon_name="x",
                        tooltip="Close this window",
                    ),
                ),
            )
        )

        # ── Child window: employee hub (P7c) ──────────────────────────
        self.register(
            RibbonSurfaceDef(
                surface_key=self.child_window_key("payroll_employee_hub"),
                items=(
                    RibbonButtonDef(
                        command_id="payroll_employee_hub.edit",
                        label="Edit Employee",
                        icon_name="edit",
                        tooltip="Edit the employee's identity and contact details",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="payroll_employee_hub.payroll_setup_wizard",
                        label="Payroll Setup",
                        icon_name="wand",
                        tooltip="Run the adaptive payroll setup wizard",
                    ),
                    RibbonButtonDef(
                        command_id="payroll_employee_hub.compensation_change",
                        label="Compensation Change",
                        icon_name="trending_up",
                        tooltip="Record a salary or profile change",
                    ),
                    RibbonButtonDef(
                        command_id="payroll_employee_hub.new_assignment",
                        label="Assign Component",
                        icon_name="plus",
                        tooltip="Assign a recurring payroll component",
                    ),
                    RibbonDividerDef(key="after_actions"),
                    RibbonButtonDef(
                        command_id="payroll_employee_hub.deactivate",
                        label="Deactivate",
                        icon_name="user_x",
                        tooltip="Deactivate this employee",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id="payroll_employee_hub.reactivate",
                        label="Reactivate",
                        icon_name="check",
                        tooltip="Reactivate this employee",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="before_utility"),
                    RibbonButtonDef(
                        command_id="payroll_employee_hub.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload employee data",
                    ),
                    RibbonButtonDef(
                        command_id="payroll_employee_hub.close",
                        label="Close",
                        icon_name="x",
                        tooltip="Close this window",
                    ),
                ),
            )
        )

        # ── Child window: payroll run employee detail (P2) ────────────
        self.register(
            RibbonSurfaceDef(
                surface_key=self.child_window_key("payroll_run_employee"),
                items=(
                    RibbonButtonDef(
                        command_id="payroll_run_employee.payslip_preview",
                        label="Payslip Preview",
                        icon_name="file_text",
                        tooltip="Preview the payslip for this employee",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id="payroll_run_employee.project_allocations",
                        label="Project Allocations",
                        icon_name="layout_grid",
                        tooltip="Edit project allocations for this employee",
                    ),
                    RibbonDividerDef(key="after_review"),
                    RibbonButtonDef(
                        command_id="payroll_run_employee.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload detail",
                    ),
                    RibbonButtonDef(
                        command_id="payroll_run_employee.close",
                        label="Close",
                        icon_name="x",
                        tooltip="Close this window",
                    ),
                ),
            )
        )

        # Payroll accounting + operations surfaces (Slice P6).
        self._register_payroll_accounting_surfaces()
        self._register_payroll_operations_surfaces()

    # ── Payroll accounting surfaces (P6a) ─────────────────────────────

    def _register_payroll_accounting_surfaces(self) -> None:
        """Tab-scoped ribbon surfaces for ``payroll_accounting``.

        Four tab families: Posting, Employee Payments, Remittances, Summary.
        Command ids mirror the ``_ribbon_commands`` map on
        :class:`PayrollAccountingWorkspace`.
        """

        # ── Posting (variants by run selection/status) ────────────────
        posting_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_accounting.post_to_gl",
                label="Post to GL",
                icon_name="check_square",
                tooltip="Post the selected approved/calculated run to the GL",
                variant="primary",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_accounting.posting_detail",
                label="Posting Detail",
                icon_name="file_text",
                tooltip="Open posting detail for the selected posted run",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_primary"),
            RibbonButtonDef(
                command_id="payroll_accounting.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload runs",
            ),
            RibbonDividerDef(key="before_related"),
            RibbonButtonDef(
                command_id="payroll_accounting.open_calculation",
                label="Payroll Runs",
                icon_name="calculator",
                tooltip="Open the payroll calculation workspace",
            ),
            RibbonButtonDef(
                command_id="payroll_accounting.open_validation",
                label="Validation",
                icon_name="list_checks",
                tooltip="Open payroll validation",
            ),
        )
        for variant in ("none", "postable_run", "posted_run"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_accounting.posting.{variant}",
                    items=posting_items,
                )
            )

        # ── Employee Payments (variants by run/employee selection) ────
        payments_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_accounting.record_payment",
                label="Record Payment",
                icon_name="check_square",
                tooltip="Record a net-pay settlement for the selected employee",
                variant="primary",
                default_enabled=False,
            ),
            RibbonDividerDef(key="after_primary"),
            RibbonButtonDef(
                command_id="payroll_accounting.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload payments",
            ),
        )
        for variant in ("none", "run_selected", "employee_selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_accounting.payments.{variant}",
                    items=payments_items,
                )
            )

        # ── Remittances (variants by batch selection) ─────────────────
        remittances_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_accounting.remittance_wizard",
                label="Remittance Wizard",
                icon_name="wand",
                tooltip="Guided remittance batch creation (DGI / CNPS / Other)",
                variant="primary",
            ),
            RibbonDividerDef(key="after_wizard"),
            RibbonButtonDef(
                command_id="payroll_accounting.new_batch",
                label="New Batch",
                icon_name="plus",
                tooltip="Create a remittance batch (expert form)",
            ),
            RibbonButtonDef(
                command_id="payroll_accounting.open_batch",
                label="Open Batch",
                icon_name="folder",
                tooltip="Open the selected draft batch",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_accounting.add_line",
                label="Add Line",
                icon_name="plus",
                tooltip="Add a line to the selected batch",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_accounting.cancel_batch",
                label="Cancel Batch",
                icon_name="x",
                tooltip="Cancel the selected batch",
                variant="danger",
                default_enabled=False,
            ),
            RibbonDividerDef(key="before_refresh"),
            RibbonButtonDef(
                command_id="payroll_accounting.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload remittance batches",
            ),
        )
        for variant in ("none", "batch_selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_accounting.remittances.{variant}",
                    items=remittances_items,
                )
            )

        # ── Summary ───────────────────────────────────────────────────
        summary_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_accounting.open_full_summary",
                label="Full Summary",
                icon_name="file_text",
                tooltip="Open the full period summary dialog",
                variant="primary",
            ),
            RibbonDividerDef(key="before_refresh"),
            RibbonButtonDef(
                command_id="payroll_accounting.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload summary",
            ),
        )
        self.register(
            RibbonSurfaceDef(surface_key="payroll_accounting.summary", items=summary_items)
        )

        # Nav-id level fallback — used when no tab is active yet.
        self.register(
            RibbonSurfaceDef(surface_key="payroll_accounting", items=posting_items)
        )

    # ── Payroll operations surfaces (P6b) ─────────────────────────────

    def _register_payroll_operations_surfaces(self) -> None:
        """Tab-scoped ribbon surfaces for ``payroll_operations``.

        Five tab families: Validation, Statutory Packs, Imports, Print,
        Audit Log. Command ids mirror the ``_ribbon_commands`` map on
        :class:`PayrollOperationsWorkspace`.
        """

        # ── Validation (variants by severity selection) ───────────────
        validation_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_operations.run_assessment",
                label="Run Assessment",
                icon_name="list_checks",
                tooltip="Run validation for the selected period",
                variant="primary",
            ),
            RibbonButtonDef(
                command_id="payroll_operations.open_check_detail",
                label="Open Detail",
                icon_name="file_text",
                tooltip="Open detail for the selected validation check",
                default_enabled=False,
            ),
            RibbonDividerDef(key="before_refresh"),
            RibbonButtonDef(
                command_id="payroll_operations.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Refresh the current tab",
            ),
        )
        for variant in ("none", "blocker_selected", "warning_selected"):
            self.register(
                RibbonSurfaceDef(
                    surface_key=f"payroll_operations.validation.{variant}",
                    items=validation_items,
                )
            )

        # ── Statutory Packs ───────────────────────────────────────────
        packs_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_operations.apply_pack",
                label="Apply Pack",
                icon_name="check_square",
                tooltip="Apply the selected statutory pack",
                variant="primary",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_operations.preview_pack",
                label="Preview Rollover",
                icon_name="file_text",
                tooltip="Preview the rollover impact",
                default_enabled=False,
            ),
            RibbonDividerDef(key="before_refresh"),
            RibbonButtonDef(
                command_id="payroll_operations.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload packs",
            ),
        )
        self.register(
            RibbonSurfaceDef(surface_key="payroll_operations.packs", items=packs_items)
        )

        # ── Imports ───────────────────────────────────────────────────
        imports_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_operations.preview_import",
                label="Preview Import",
                icon_name="file_text",
                tooltip="Preview the selected import file",
                variant="primary",
            ),
            RibbonButtonDef(
                command_id="payroll_operations.execute_import",
                label="Execute Import",
                icon_name="check_square",
                tooltip="Execute the selected import",
                default_enabled=False,
            ),
        )
        self.register(
            RibbonSurfaceDef(surface_key="payroll_operations.imports", items=imports_items)
        )

        # ── Print ─────────────────────────────────────────────────────
        print_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_operations.print_payslips",
                label="Print Payslips",
                icon_name="file_text",
                tooltip="Print payslips for the selected run",
                variant="primary",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_operations.print_summary",
                label="Print Summary",
                icon_name="file_text",
                tooltip="Print the summary report",
                default_enabled=False,
            ),
            RibbonButtonDef(
                command_id="payroll_operations.save_pdf",
                label="Save PDF",
                icon_name="file_text",
                tooltip="Save as PDF",
                default_enabled=False,
            ),
            RibbonDividerDef(key="before_refresh"),
            RibbonButtonDef(
                command_id="payroll_operations.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload runs",
            ),
        )
        self.register(
            RibbonSurfaceDef(surface_key="payroll_operations.print", items=print_items)
        )

        # ── Audit Log ─────────────────────────────────────────────────
        # Blueprint calls for an ``export_audit`` primary; the underlying
        # export handler is not yet wired, so the ribbon exposes Refresh
        # only for now. Export will be added alongside the audit export
        # service in a later slice.
        audit_items: tuple[RibbonButtonDef | RibbonDividerDef, ...] = (
            RibbonButtonDef(
                command_id="payroll_operations.refresh",
                label="Refresh",
                icon_name="refresh",
                tooltip="Reload audit entries",
                variant="primary",
            ),
        )
        self.register(
            RibbonSurfaceDef(surface_key="payroll_operations.audit", items=audit_items)
        )

        # Nav-id level fallback.
        self.register(
            RibbonSurfaceDef(surface_key="payroll_operations", items=validation_items)
        )

    def _append_related_links(self, surface_key: str) -> None:
        """Append a divider + goto buttons to an already-registered surface.

        The target page's nav id and label come from :data:`RELATED_PAGES`.
        Safe no-op if the surface is not registered or has no related spec.
        """
        spec = RELATED_PAGES.get(surface_key)
        if not spec:
            return
        surface = self._surfaces.get(surface_key)
        if surface is None:
            return
        extra: list[RibbonButtonDef | RibbonDividerDef] = [
            RibbonDividerDef(key="before_related"),
        ]
        for target_nav_id, label, icon_name in spec:
            extra.append(
                RibbonButtonDef(
                    command_id=related_goto_command_id(surface_key, target_nav_id),
                    label=label,
                    icon_name=icon_name,
                    tooltip=f"Open {label}",
                )
            )
        self._surfaces[surface_key] = RibbonSurfaceDef(
            surface_key=surface.surface_key,
            items=tuple(surface.items) + tuple(extra),
        )

    def _register_document_register(
        self,
        *,
        surface_key: str,
        prefix: str,
        new_label: str,
        new_tooltip: str,
        edit_label: str,
        edit_tooltip: str,
        cancel_label: str,
        cancel_tooltip: str,
        post_label: str,
        post_tooltip: str,
        print_label: str,
        print_tooltip: str,
    ) -> None:
        """Register a document-register surface (New / Edit / Cancel / Post / Print)."""
        self.register(
            RibbonSurfaceDef(
                surface_key=surface_key,
                items=(
                    RibbonButtonDef(
                        command_id=f"{prefix}.new",
                        label=new_label,
                        icon_name="plus",
                        tooltip=new_tooltip,
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id=f"{prefix}.edit",
                        label=edit_label,
                        icon_name="edit",
                        tooltip=edit_tooltip,
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id=f"{prefix}.cancel",
                        label=cancel_label,
                        icon_name="x",
                        tooltip=cancel_tooltip,
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_crud"),
                    RibbonButtonDef(
                        command_id=f"{prefix}.post",
                        label=post_label,
                        icon_name="check_square",
                        tooltip=post_tooltip,
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_posting"),
                    RibbonButtonDef(
                        command_id=f"{prefix}.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the list",
                    ),
                    RibbonButtonDef(
                        command_id=f"{prefix}.print",
                        label=print_label,
                        icon_name="printer",
                        tooltip=print_tooltip,
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id=f"{prefix}.export_list",
                        label="Export List",
                        icon_name="download",
                        tooltip="Export the register list",
                        default_enabled=False,
                    ),
                ),
            )
        )

    def _register_entity_register(
        self,
        *,
        surface_key: str,
        prefix: str,
        new_label: str,
        edit_label: str,
        deactivate_label: str,
    ) -> None:
        """Register a reference-entity surface (New / Edit / Deactivate / Refresh / Export)."""
        self.register(
            RibbonSurfaceDef(
                surface_key=surface_key,
                items=(
                    RibbonButtonDef(
                        command_id=f"{prefix}.new",
                        label=new_label,
                        icon_name="plus",
                        tooltip=f"Create a new {surface_key.rstrip('s').replace('_', ' ')} record",
                        variant="primary",
                    ),
                    RibbonButtonDef(
                        command_id=f"{prefix}.edit",
                        label=edit_label,
                        icon_name="edit",
                        tooltip="Edit the selected record",
                        default_enabled=False,
                    ),
                    RibbonButtonDef(
                        command_id=f"{prefix}.deactivate",
                        label=deactivate_label,
                        icon_name="x",
                        tooltip="Deactivate the selected record",
                        variant="danger",
                        default_enabled=False,
                    ),
                    RibbonDividerDef(key="after_crud"),
                    RibbonButtonDef(
                        command_id=f"{prefix}.refresh",
                        label="Refresh",
                        icon_name="refresh",
                        tooltip="Reload the list",
                    ),
                    RibbonButtonDef(
                        command_id=f"{prefix}.export_list",
                        label="Export List",
                        icon_name="download",
                        tooltip="Export the list",
                        default_enabled=False,
                    ),
                ),
            )
        )
