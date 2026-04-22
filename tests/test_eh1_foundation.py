from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.navigation.workflow_resume_service import WorkflowResumeService
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.app_exceptions import PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.error_resolution import (
    GuidedResolutionAction,
    GuidedResolutionSeverity,
)
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver


class StructuredExceptionCompatibilityTests(unittest.TestCase):
    def test_existing_exception_usage_remains_valid(self) -> None:
        error = ValidationError("Plain validation failure")

        self.assertEqual(str(error), "Plain validation failure")
        self.assertIsNone(error.app_error_code)
        self.assertEqual(error.context, {})

    def test_structured_exception_fields_are_available(self) -> None:
        error = ValidationError(
            "Document sequence missing",
            app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
            context={"document_type_code": "PAYROLL_RUN"},
        )

        self.assertEqual(error.app_error_code, AppErrorCode.MISSING_DOCUMENT_SEQUENCE)
        self.assertEqual(error.context["document_type_code"], "PAYROLL_RUN")


class ErrorResolutionResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_resolves_structured_document_sequence_error(self) -> None:
        error = ValidationError(
            "Missing setup",
            app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
            context={"details": "Payroll run sequence is missing."},
        )

        resolution = self.resolver.resolve(error)

        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.MISSING_DOCUMENT_SEQUENCE)
        self.assertEqual(resolution.severity, GuidedResolutionSeverity.WARNING)
        self.assertEqual(resolution.actions[0].nav_id, nav_ids.DOCUMENT_SEQUENCES)

    def test_resolves_fallback_document_sequence_pattern(self) -> None:
        error = ValidationError("An active document sequence must be configured before posting.")

        resolution = self.resolver.resolve(error)

        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.MISSING_DOCUMENT_SEQUENCE)

    def test_returns_none_for_non_guided_errors(self) -> None:
        resolution = self.resolver.resolve(RuntimeError("Unrelated runtime issue"))
        self.assertIsNone(resolution)

    def test_resolver_does_not_match_generic_fiscal_period_text(self) -> None:
        # A ValidationError whose text mentions "fiscal period" but is NOT a
        # PeriodLockedError should NOT be matched. The brittle text fallback was
        # removed; only the document-sequence pattern and PeriodLockedError type
        # check remain in _fallback_code.
        error = ValidationError("No fiscal period is configured for this date.")
        resolution = self.resolver.resolve(error)
        self.assertIsNone(resolution)

    def test_period_locked_error_resolves_via_type_check(self) -> None:
        error = PeriodLockedError("Period 2025-12 is locked.")
        resolution = self.resolver.resolve(error)
        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.LOCKED_FISCAL_PERIOD)


class WorkflowResumeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WorkflowResumeService()

    def test_create_get_consume_discard(self) -> None:
        token = self.service.create_token(
            workflow_key="sales.invoice.create",
            origin_nav_id=nav_ids.SALES_INVOICES,
            payload={"draft_id": 19, "line_count": 3},
        )

        peeked = self.service.get_token(token)
        self.assertIsNotNone(peeked)
        assert peeked is not None
        self.assertEqual(peeked.workflow_key, "sales.invoice.create")
        self.assertEqual(peeked.payload["line_count"], 3)

        consumed = self.service.consume_token(token)
        self.assertIsNotNone(consumed)
        assert consumed is not None
        self.assertEqual(consumed.origin_nav_id, nav_ids.SALES_INVOICES)

        self.assertIsNone(self.service.get_token(token))
        self.assertFalse(self.service.discard_token(token))

    def test_rejects_non_serializable_payload(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.create_token(
                workflow_key="payroll.run",
                payload={"bad": object()},
            )

    def test_consume_token_is_one_time_only(self) -> None:
        token = self.service.create_token(
            workflow_key="test.workflow",
            payload={"x": 1},
        )

        first = self.service.consume_token(token)
        self.assertIsNotNone(first)

        second = self.service.consume_token(token)
        self.assertIsNone(second)

    def test_payload_survives_normalization_for_date_decimal_uuid(self) -> None:
        doc_id = uuid4()
        token = self.service.create_token(
            workflow_key="test.workflow",
            payload={
                "created_on": date(2026, 1, 15),
                "amount": Decimal("1500.75"),
                "doc_ref": doc_id,
            },
        )

        restored = self.service.get_token(token)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.payload["created_on"], "2026-01-15")
        self.assertEqual(restored.payload["amount"], "1500.75")
        self.assertEqual(restored.payload["doc_ref"], str(doc_id))

    def test_consume_returns_isolated_copy(self) -> None:
        token = self.service.create_token(
            workflow_key="test.workflow",
            payload={"nested": {"count": 5}},
        )

        # peek — mutate the returned copy
        peeked = self.service.get_token(token)
        assert peeked is not None
        peeked.payload["nested"]["count"] = 999

        # consume — original payload should be unaffected
        consumed = self.service.consume_token(token)
        assert consumed is not None
        self.assertEqual(consumed.payload["nested"]["count"], 5)


class GuidedResolutionActionModelTests(unittest.TestCase):
    def test_default_flags(self) -> None:
        action = GuidedResolutionAction(action_id="dismiss", label="Close")

        self.assertTrue(action.close_dialog)
        self.assertFalse(action.requires_resume_token)
        self.assertIsNone(action.nav_id)


if __name__ == "__main__":
    unittest.main()
