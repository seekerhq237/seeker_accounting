from __future__ import annotations

from typing import Any, Mapping

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from datetime import date as _date

from seeker_accounting.platform.exceptions.app_exceptions import AppError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.error_resolution import (
    GuidedResolution,
    GuidedResolutionAction,
    GuidedResolutionSeverity,
)


_DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "sales_invoice": "Sales Invoice",
    "customer_receipt": "Customer Receipt",
    "purchase_bill": "Purchase Bill",
    "supplier_payment": "Supplier Payment",
    "treasury_transaction": "Treasury Transaction",
    "treasury_transfer": "Treasury Transfer",
    "inventory_document": "Inventory Document",
    "depreciation_run": "Depreciation Run",
    "journal_entry": "Journal Entry",
    "asset": "Fixed Asset",
    "payroll_run": "Payroll Run",
    "payroll_input_batch": "Payroll Input Batch",
    "payroll_remittance": "Payroll Remittance",
    "contract": "Contract",
    "project": "Project",
}

_ACCOUNT_ROLE_LABELS: dict[str, str] = {
    "ar_control": "AR Control",
    "ap_control": "AP Control",
    "payroll_payable": "Payroll Payable",
    "inventory_control": "Inventory Control",
    "cash_on_hand": "Cash On Hand",
    "petty_cash": "Petty Cash",
    "bank_main": "Main Bank",
    "sales_revenue_default": "Sales Revenue",
    "purchases_expense_default": "Purchases Expense",
}


class ErrorResolutionResolver:
    """Maps structured business exceptions into guided UI resolutions."""

    def resolve(self, error: Exception, context: Mapping[str, Any] | None = None) -> GuidedResolution | None:
        combined_context = self._merge_context(error, context)
        app_error_code = self._extract_app_error_code(error)

        if app_error_code is not None:
            return self._resolution_for_code(app_error_code, error, combined_context)

        fallback_code = self._fallback_code(error)
        if fallback_code is None:
            return None
        return self._resolution_for_code(fallback_code, error, combined_context)

    def _extract_app_error_code(self, error: Exception) -> str | None:
        if isinstance(error, AppError):
            return error.app_error_code
        return None

    def _merge_context(self, error: Exception, context: Mapping[str, Any] | None) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if isinstance(error, AppError):
            merged.update(error.context)
        if context:
            merged.update(context)
        return merged

    def _fallback_code(self, error: Exception) -> str | None:
        if isinstance(error, PeriodLockedError):
            return AppErrorCode.LOCKED_FISCAL_PERIOD
        if isinstance(error, ValidationError):
            text = str(error).lower()
            if "document sequence" in text:
                return AppErrorCode.MISSING_DOCUMENT_SEQUENCE
        return None

    def _resolution_for_code(
        self,
        app_error_code: str,
        error: Exception,
        context: Mapping[str, Any],
    ) -> GuidedResolution | None:
        details = context.get("details")
        debug_details = context.get("debug_details")

        if app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
            raw_type = str(context.get("document_type_code", "")).lower()
            type_label = _DOCUMENT_TYPE_LABELS.get(raw_type) or (
                raw_type.replace("_", " ").title() if raw_type else ""
            )
            if type_label:
                message = (
                    f"No active document sequence is configured for {type_label}. "
                    "Set up a sequence in Document Sequences before continuing."
                )
                create_label = f"Set Up {type_label} Sequence"
            else:
                message = "Set up a document sequence before continuing this workflow."
                create_label = "Set Up Sequence"
            seq_payload: dict[str, Any] = {}
            if raw_type:
                seq_payload["document_type_code"] = raw_type
            create_seq_payload: dict[str, Any] = dict(seq_payload)
            create_seq_payload["open_create_flow"] = True
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="Document sequence required",
                message=message,
                severity=GuidedResolutionSeverity.WARNING,
                actions=[
                    GuidedResolutionAction(
                        action_id="create_document_sequence",
                        label=create_label,
                        nav_id=nav_ids.DOCUMENT_SEQUENCES,
                        requires_resume_token=True,
                        payload=create_seq_payload,
                    ),
                    GuidedResolutionAction(
                        action_id="open_document_sequences",
                        label="Open Document Sequences",
                        nav_id=nav_ids.DOCUMENT_SEQUENCES,
                        requires_resume_token=True,
                        payload=seq_payload or None,
                    ),
                    GuidedResolutionAction(action_id="dismiss", label="Close"),
                ],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.MISSING_FISCAL_PERIOD:
            entry_date = context.get("entry_date")
            company_name = context.get("company_name")
            entry_date_str: str | None = None
            if isinstance(entry_date, _date):
                entry_date_str = entry_date.strftime("%Y-%m-%d")
            elif entry_date:
                entry_date_str = str(entry_date)
            if entry_date_str and company_name:
                message = (
                    f"The date {entry_date_str} is not covered by any fiscal period for {company_name}. "
                    "Create a fiscal period to continue."
                )
            elif entry_date_str:
                message = (
                    f"The date {entry_date_str} is not covered by any fiscal period. "
                    "Create a fiscal period before retrying."
                )
            else:
                message = "The entry date is not covered by any fiscal period. Create a fiscal period before retrying."
            fp_nav_payload: dict[str, Any] = {"source_workflow": context.get("origin_workflow", "journal_entry")}
            if entry_date_str:
                fp_nav_payload["entry_date"] = entry_date_str
            create_fp_payload: dict[str, Any] = dict(fp_nav_payload)
            create_fp_payload["open_create_flow"] = True
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="No fiscal period for this date",
                message=message,
                severity=GuidedResolutionSeverity.WARNING,
                actions=[
                    GuidedResolutionAction(
                        action_id="create_fiscal_period",
                        label="Create Fiscal Period",
                        nav_id=nav_ids.FISCAL_PERIODS,
                        requires_resume_token=True,
                        payload=create_fp_payload,
                    ),
                    GuidedResolutionAction(
                        action_id="open_fiscal_periods",
                        label="Open Fiscal Periods",
                        nav_id=nav_ids.FISCAL_PERIODS,
                        requires_resume_token=True,
                        payload=fp_nav_payload,
                    ),
                    GuidedResolutionAction(action_id="dismiss", label="Cancel"),
                ],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.LOCKED_FISCAL_PERIOD:
            lp_entry_date = context.get("entry_date")
            lp_period_code = context.get("fiscal_period_code")
            lp_period_id = context.get("fiscal_period_id")
            lp_company_name = context.get("company_name")
            lp_entry_date_str: str | None = None
            if isinstance(lp_entry_date, _date):
                lp_entry_date_str = lp_entry_date.strftime("%Y-%m-%d")
            elif lp_entry_date:
                lp_entry_date_str = str(lp_entry_date)
            if lp_period_code and lp_entry_date_str:
                lp_message = (
                    f"Period {lp_period_code} is locked. "
                    f"The entry date {lp_entry_date_str} falls in this period. "
                    "Reopen the period in Fiscal Periods to allow posting."
                )
            elif lp_period_code:
                lp_message = (
                    f"Period {lp_period_code} is locked. "
                    "Reopen the period in Fiscal Periods to allow posting."
                )
            elif lp_entry_date_str:
                lp_message = (
                    f"The fiscal period covering {lp_entry_date_str} is locked. "
                    "Reopen the period in Fiscal Periods to allow posting."
                )
            else:
                lp_message = (
                    "The fiscal period is locked. "
                    "Open Fiscal Periods to review period status before retrying."
                )
            locked_fp_payload: dict[str, Any] = {
                "source_workflow": context.get("origin_workflow", "journal_entry"),
                "locked_period_flow": True,
            }
            if lp_entry_date_str:
                locked_fp_payload["entry_date"] = lp_entry_date_str
            if lp_period_code:
                locked_fp_payload["fiscal_period_code"] = lp_period_code
            if lp_period_id is not None:
                locked_fp_payload["fiscal_period_id"] = lp_period_id
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="Fiscal period is locked",
                message=lp_message,
                severity=GuidedResolutionSeverity.WARNING,
                actions=[
                    GuidedResolutionAction(
                        action_id="open_fiscal_periods",
                        label="Open Fiscal Periods",
                        nav_id=nav_ids.FISCAL_PERIODS,
                        requires_resume_token=True,
                        payload=locked_fp_payload,
                    ),
                    GuidedResolutionAction(action_id="dismiss", label="Close"),
                ],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING:
            arm_role_code = context.get("role_code")
            arm_role_label = _ACCOUNT_ROLE_LABELS.get(arm_role_code, arm_role_code) if arm_role_code else None
            if arm_role_label:
                arm_message = (
                    f"The \u2018{arm_role_label}\u2019 account role is not mapped. "
                    "Open Account Role Mappings to assign the correct account before retrying."
                )
                arm_title = f"Account role mapping required \u2014 {arm_role_label}"
            else:
                arm_message = (
                    "A required account role mapping is missing. "
                    "Open Account Role Mappings to complete the configuration."
                )
                arm_title = "Account role mapping required"
            arm_payload: dict[str, Any] = {
                "source_workflow": context.get("origin_workflow", ""),
                "role_mapping_flow": True,
            }
            if arm_role_code:
                arm_payload["role_code"] = arm_role_code
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title=arm_title,
                message=arm_message,
                severity=GuidedResolutionSeverity.WARNING,
                actions=[
                    GuidedResolutionAction(
                        action_id="open_account_role_mappings",
                        label="Open Account Role Mappings",
                        nav_id=nav_ids.ACCOUNT_ROLE_MAPPINGS,
                        requires_resume_token=True,
                        payload=arm_payload,
                    ),
                    GuidedResolutionAction(action_id="dismiss", label="Close"),
                ],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.MISSING_TAX_CODE_ACCOUNT_MAPPING:
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="Tax code mapping required",
                message="Complete tax code account mappings before continuing.",
                severity=GuidedResolutionSeverity.WARNING,
                actions=[
                    GuidedResolutionAction(
                        action_id="open_tax_codes",
                        label="Open Tax Codes",
                        nav_id=nav_ids.TAX_CODES,
                        requires_resume_token=True,
                    ),
                    GuidedResolutionAction(action_id="dismiss", label="Close"),
                ],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.MISSING_FINANCIAL_ACCOUNT_GL_MAPPING:
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="Financial account mapping required",
                message="Link financial accounts to the required GL accounts before retrying.",
                severity=GuidedResolutionSeverity.WARNING,
                actions=[
                    GuidedResolutionAction(
                        action_id="open_financial_accounts",
                        label="Open Financial Accounts",
                        nav_id=nav_ids.FINANCIAL_ACCOUNTS,
                        requires_resume_token=True,
                    ),
                    GuidedResolutionAction(action_id="dismiss", label="Close"),
                ],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.MISSING_INVENTORY_ACCOUNT_MAPPING:
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="Inventory account mapping required",
                message="Complete inventory account mappings before continuing.",
                severity=GuidedResolutionSeverity.WARNING,
                actions=[
                    GuidedResolutionAction(
                        action_id="open_items",
                        label="Open Items",
                        nav_id=nav_ids.ITEMS,
                        requires_resume_token=True,
                    ),
                    GuidedResolutionAction(action_id="dismiss", label="Close"),
                ],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.MISSING_ASSET_POSTING_ACCOUNT_MAPPING:
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="Asset posting mapping required",
                message="Complete fixed-asset posting account mappings before continuing.",
                severity=GuidedResolutionSeverity.WARNING,
                actions=[
                    GuidedResolutionAction(
                        action_id="open_asset_categories",
                        label="Open Asset Categories",
                        nav_id=nav_ids.ASSET_CATEGORIES,
                        requires_resume_token=True,
                    ),
                    GuidedResolutionAction(action_id="dismiss", label="Close"),
                ],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.REFERENCE_DATA_LOAD_FAILED:
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="Reference data unavailable",
                message="Reference data could not be loaded. Review setup and retry.",
                severity=GuidedResolutionSeverity.ERROR,
                actions=[GuidedResolutionAction(action_id="dismiss", label="Close")],
                details=details,
                debug_details=debug_details,
            )

        if app_error_code == AppErrorCode.UNKNOWN_WORKFLOW_BLOCKER:
            return GuidedResolution(
                resolution_code=app_error_code,
                error_code=app_error_code,
                title="Workflow blocked",
                message="A prerequisite needs attention before this workflow can continue.",
                severity=GuidedResolutionSeverity.WARNING,
                actions=[GuidedResolutionAction(action_id="dismiss", label="Close")],
                details=details or str(error),
                debug_details=debug_details,
            )

        return None
