"""
EH-3B: Account Role Mapping guided blocker — targeted unit tests.

Covers:
- Standalone ACCOUNT_ROLE_MAPPINGS nav ID exists and is registered.
- Structured MISSING_ACCOUNT_ROLE_MAPPING exception carries role_code context.
- Resolver maps the code to a role-aware guided resolution.
- Resolution message names the missing role when role_code is present.
- Resolution message is generic but valid when role_code is absent.
- open_account_role_mappings action targets ACCOUNT_ROLE_MAPPINGS nav ID.
- open_account_role_mappings action carries role_mapping_flow=True in payload.
- open_account_role_mappings action carries role_code in payload when present.
- open_account_role_mappings action carries source_workflow in payload.
- Dismiss action does not require token or nav.
- No create-style action exists (unlike missing-period).
- Resume token round-trips for sales_invoice.post and purchase_bill.post workflows.
- Post path token carries document_id.
- Tokens are one-time use.
- Prior EH-2A/2B/3A guided flows remain stable (regression guards).
"""
from __future__ import annotations

import unittest
from datetime import date

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.navigation.workflow_resume_service import WorkflowResumeService
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.app_exceptions import (
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.exceptions.error_resolution_resolver import (
    ErrorResolutionResolver,
    _ACCOUNT_ROLE_LABELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_missing_role_exc(
    role_code: str = "ar_control",
    company_id: int = 1,
    origin_workflow: str = "sales_invoice",
) -> ValidationError:
    return ValidationError(
        f"The '{role_code}' account role is not mapped.",
        app_error_code=AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING,
        context={
            "company_id": company_id,
            "role_code": role_code,
            "origin_workflow": origin_workflow,
        },
    )


# ---------------------------------------------------------------------------
# 1. Nav ID registration
# ---------------------------------------------------------------------------

class AccountRoleMappingsNavTests(unittest.TestCase):
    def test_account_role_mappings_nav_id_exists(self) -> None:
        self.assertEqual(nav_ids.ACCOUNT_ROLE_MAPPINGS, "account_role_mappings")

    def test_account_role_mappings_in_all_nav_ids(self) -> None:
        self.assertIn(nav_ids.ACCOUNT_ROLE_MAPPINGS, nav_ids.ALL_NAV_IDS)


# ---------------------------------------------------------------------------
# 2. Exception structure
# ---------------------------------------------------------------------------

class MissingRoleMappingExceptionTests(unittest.TestCase):
    def test_exception_carries_structured_code(self) -> None:
        exc = _make_missing_role_exc()
        self.assertEqual(exc.app_error_code, AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING)

    def test_exception_carries_role_code_in_context(self) -> None:
        exc = _make_missing_role_exc(role_code="ap_control")
        self.assertEqual(exc.context["role_code"], "ap_control")

    def test_exception_carries_company_id_in_context(self) -> None:
        exc = _make_missing_role_exc(company_id=42)
        self.assertEqual(exc.context["company_id"], 42)

    def test_exception_carries_origin_workflow_in_context(self) -> None:
        exc = _make_missing_role_exc(origin_workflow="purchase_bill")
        self.assertEqual(exc.context["origin_workflow"], "purchase_bill")

    def test_exception_is_validation_error_type(self) -> None:
        exc = _make_missing_role_exc()
        self.assertIsInstance(exc, ValidationError)


# ---------------------------------------------------------------------------
# 3. Resolver — action structure
# ---------------------------------------------------------------------------

class RoleMappingResolverStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_missing_role_mapping_resolves_to_guided_resolution(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        self.assertIsNotNone(resolution)

    def test_resolution_code_is_missing_account_role_mapping(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING)

    def test_has_exactly_two_actions(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(len(resolution.actions), 2)

    def test_has_open_account_role_mappings_action(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("open_account_role_mappings", action_ids)

    def test_has_dismiss_action(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("dismiss", action_ids)

    def test_no_chart_of_accounts_action(self) -> None:
        """The old open_chart_of_accounts action should be replaced."""
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertNotIn("open_chart_of_accounts", action_ids)

    def test_nav_action_targets_account_role_mappings(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_account_role_mappings")
        self.assertEqual(nav_action.nav_id, nav_ids.ACCOUNT_ROLE_MAPPINGS)

    def test_nav_action_requires_resume_token(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_account_role_mappings")
        self.assertTrue(nav_action.requires_resume_token)

    def test_dismiss_action_does_not_require_token(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        dismiss = next(a for a in resolution.actions if a.action_id == "dismiss")
        self.assertFalse(dismiss.requires_resume_token)
        self.assertIsNone(dismiss.nav_id)


# ---------------------------------------------------------------------------
# 4. Resolver — payload content
# ---------------------------------------------------------------------------

class RoleMappingResolverPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_payload_carries_role_mapping_flow_true(self) -> None:
        exc = _make_missing_role_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_account_role_mappings")
        assert nav_action.payload is not None
        self.assertTrue(nav_action.payload.get("role_mapping_flow"))

    def test_payload_carries_role_code(self) -> None:
        exc = _make_missing_role_exc(role_code="ap_control")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_account_role_mappings")
        assert nav_action.payload is not None
        self.assertEqual(nav_action.payload.get("role_code"), "ap_control")

    def test_payload_carries_source_workflow(self) -> None:
        exc = _make_missing_role_exc(origin_workflow="purchase_bill")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_account_role_mappings")
        assert nav_action.payload is not None
        self.assertEqual(nav_action.payload.get("source_workflow"), "purchase_bill")

    def test_payload_omits_role_code_when_absent(self) -> None:
        exc = ValidationError(
            "Missing role.",
            app_error_code=AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING,
            context={"company_id": 1, "origin_workflow": "sales_invoice"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_account_role_mappings")
        assert nav_action.payload is not None
        self.assertNotIn("role_code", nav_action.payload)


# ---------------------------------------------------------------------------
# 5. Resolver — message content
# ---------------------------------------------------------------------------

class RoleMappingResolverMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_message_mentions_ar_control_label_when_present(self) -> None:
        exc = _make_missing_role_exc(role_code="ar_control")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("AR Control", resolution.message)

    def test_message_mentions_ap_control_label_when_present(self) -> None:
        exc = _make_missing_role_exc(role_code="ap_control")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("AP Control", resolution.message)

    def test_message_mentions_payroll_payable_label(self) -> None:
        exc = _make_missing_role_exc(role_code="payroll_payable")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("Payroll Payable", resolution.message)

    def test_title_includes_role_label_when_present(self) -> None:
        exc = _make_missing_role_exc(role_code="ar_control")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("AR Control", resolution.title)

    def test_generic_message_when_role_code_absent(self) -> None:
        exc = ValidationError(
            "Missing role.",
            app_error_code=AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING,
            context={"company_id": 1},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("account role mapping", resolution.message.lower())

    def test_generic_title_when_role_code_absent(self) -> None:
        exc = ValidationError(
            "Missing role.",
            app_error_code=AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING,
            context={},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(resolution.title, "Account role mapping required")

    def test_account_role_labels_includes_key_roles(self) -> None:
        self.assertIn("ar_control", _ACCOUNT_ROLE_LABELS)
        self.assertIn("ap_control", _ACCOUNT_ROLE_LABELS)
        self.assertIn("payroll_payable", _ACCOUNT_ROLE_LABELS)


# ---------------------------------------------------------------------------
# 6. Resume token round-trip
# ---------------------------------------------------------------------------

class RoleMappingResumeTokenTests(unittest.TestCase):
    def test_sales_invoice_post_token_round_trip(self) -> None:
        service = WorkflowResumeService()
        token = service.create_token(
            workflow_key="sales_invoice.post",
            payload={"document_id": 42},
            origin_nav_id=nav_ids.SALES_INVOICES,
        )
        restored = service.consume_token(token)
        assert restored is not None
        self.assertEqual(restored.workflow_key, "sales_invoice.post")
        self.assertEqual(restored.origin_nav_id, nav_ids.SALES_INVOICES)
        self.assertEqual(restored.payload["document_id"], 42)

    def test_purchase_bill_post_token_round_trip(self) -> None:
        service = WorkflowResumeService()
        token = service.create_token(
            workflow_key="purchase_bill.post",
            payload={"document_id": 99},
            origin_nav_id=nav_ids.PURCHASE_BILLS,
        )
        restored = service.consume_token(token)
        assert restored is not None
        self.assertEqual(restored.workflow_key, "purchase_bill.post")
        self.assertEqual(restored.origin_nav_id, nav_ids.PURCHASE_BILLS)
        self.assertEqual(restored.payload["document_id"], 99)

    def test_token_consumed_exactly_once(self) -> None:
        service = WorkflowResumeService()
        token = service.create_token(
            workflow_key="sales_invoice.post",
            payload={"document_id": 7},
        )
        first = service.consume_token(token)
        self.assertIsNotNone(first)
        second = service.consume_token(token)
        self.assertIsNone(second)


# ---------------------------------------------------------------------------
# 7. Regression guards — prior guided flows unaffected
# ---------------------------------------------------------------------------

class RegressionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_missing_fiscal_period_still_resolves_with_create_action(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 3, 1), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.MISSING_FISCAL_PERIOD)
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("create_fiscal_period", action_ids)
        self.assertIn("open_fiscal_periods", action_ids)

    def test_locked_fiscal_period_still_resolves(self) -> None:
        exc = PeriodLockedError(
            "Locked.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={"fiscal_period_code": "2026-01", "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.LOCKED_FISCAL_PERIOD)
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("open_fiscal_periods", action_ids)
        self.assertNotIn("create_fiscal_period", action_ids)

    def test_missing_document_sequence_still_resolves(self) -> None:
        exc = ValidationError(
            "Missing sequence.",
            app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
            context={"document_type_code": "sales_invoice", "company_id": 1},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.MISSING_DOCUMENT_SEQUENCE)
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("create_document_sequence", action_ids)
        self.assertIn("open_document_sequences", action_ids)


if __name__ == "__main__":
    unittest.main()
