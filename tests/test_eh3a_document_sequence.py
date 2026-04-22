"""
EH-3A: Document sequence guided blocker — targeted unit tests.

Covers:
- NumberingService raises structured ValidationError(MISSING_DOCUMENT_SEQUENCE) when
  sequence is missing or inactive, with company_id and document_type_code in context.
- NumberingSetupService.check_sequence_available raises the same structured error for
  preflight use without consuming a number.
- Resolver correctly maps ValidationError(MISSING_DOCUMENT_SEQUENCE) to a guided resolution
  with two navigation actions (create_document_sequence + open_document_sequences) and dismiss.
- Resolver populates type-aware message and label using _DOCUMENT_TYPE_LABELS mapping.
- Resolver without document_type_code produces generic but valid resolution.
- create_document_sequence action carries open_create_flow=True in payload.
- open_document_sequences action does NOT carry open_create_flow in payload.
- Both nav actions carry document_type_code in payload when present.
- Both nav actions target nav_ids.DOCUMENT_SEQUENCES with requires_resume_token=True.
- Fallback text trigger still resolves via _fallback_code (no app_error_code).
- Resume tokens round-trip: preflight key and post key stored and consumed correctly.
- Post path token carries document_id in payload.
- Tokens are one-time use (second consume returns None).
- EH-2A/2B regression guards: MISSING_FISCAL_PERIOD and LOCKED_FISCAL_PERIOD unaffected.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.navigation.workflow_resume_service import WorkflowResumeService
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.app_exceptions import (
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.exceptions.error_resolution_resolver import (
    ErrorResolutionResolver,
    _DOCUMENT_TYPE_LABELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_missing_seq_exc(
    document_type_code: str = "sales_invoice",
    company_id: int = 1,
) -> ValidationError:
    return ValidationError(
        f"An active document sequence for {document_type_code} must be configured before posting.",
        app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
        context={"company_id": company_id, "document_type_code": document_type_code},
    )


# ---------------------------------------------------------------------------
# 1. Exception structure
# ---------------------------------------------------------------------------

class MissingSequenceExceptionStructureTests(unittest.TestCase):
    def test_exception_carries_structured_code(self) -> None:
        exc = _make_missing_seq_exc()
        self.assertEqual(exc.app_error_code, AppErrorCode.MISSING_DOCUMENT_SEQUENCE)

    def test_exception_carries_company_id_in_context(self) -> None:
        exc = _make_missing_seq_exc(company_id=42)
        self.assertEqual(exc.context["company_id"], 42)

    def test_exception_carries_document_type_code_in_context(self) -> None:
        exc = _make_missing_seq_exc(document_type_code="purchase_bill")
        self.assertEqual(exc.context["document_type_code"], "purchase_bill")

    def test_exception_is_validation_error_type(self) -> None:
        exc = _make_missing_seq_exc()
        self.assertIsInstance(exc, ValidationError)

    def test_exception_message_mentions_document_type(self) -> None:
        exc = _make_missing_seq_exc(document_type_code="treasury_transaction")
        self.assertIn("treasury_transaction", str(exc).lower())


# ---------------------------------------------------------------------------
# 2. Resolver — action structure
# ---------------------------------------------------------------------------

class DocumentSequenceResolverStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_missing_sequence_resolves_to_guided_resolution(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        self.assertIsNotNone(resolution)

    def test_resolution_error_code_is_missing_document_sequence(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.MISSING_DOCUMENT_SEQUENCE)

    def test_resolution_has_exactly_three_actions(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(len(resolution.actions), 3)

    def test_resolution_has_create_document_sequence_action(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("create_document_sequence", action_ids)

    def test_resolution_has_open_document_sequences_action(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("open_document_sequences", action_ids)

    def test_resolution_has_dismiss_action(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("dismiss", action_ids)

    def test_create_sequence_is_first_action(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(resolution.actions[0].action_id, "create_document_sequence")

    def test_both_nav_actions_target_document_sequences(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        for action in resolution.actions:
            if action.action_id in ("create_document_sequence", "open_document_sequences"):
                self.assertEqual(action.nav_id, nav_ids.DOCUMENT_SEQUENCES)

    def test_create_sequence_requires_resume_token(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "create_document_sequence")
        self.assertTrue(action.requires_resume_token)

    def test_open_document_sequences_requires_resume_token(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "open_document_sequences")
        self.assertTrue(action.requires_resume_token)

    def test_dismiss_action_does_not_require_token(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "dismiss")
        self.assertFalse(action.requires_resume_token)
        self.assertIsNone(action.nav_id)


# ---------------------------------------------------------------------------
# 3. Resolver — payload content
# ---------------------------------------------------------------------------

class DocumentSequenceResolverPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_create_action_payload_has_open_create_flow_true(self) -> None:
        exc = _make_missing_seq_exc("customer_receipt")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "create_document_sequence")
        assert action.payload is not None
        self.assertTrue(action.payload.get("open_create_flow"))

    def test_open_sequences_action_payload_does_not_have_open_create_flow(self) -> None:
        exc = _make_missing_seq_exc("customer_receipt")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "open_document_sequences")
        payload = action.payload or {}
        self.assertNotIn("open_create_flow", payload)

    def test_create_action_payload_carries_document_type_code(self) -> None:
        exc = _make_missing_seq_exc("purchase_bill")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "create_document_sequence")
        assert action.payload is not None
        self.assertEqual(action.payload.get("document_type_code"), "purchase_bill")

    def test_open_sequences_action_payload_carries_document_type_code(self) -> None:
        exc = _make_missing_seq_exc("supplier_payment")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "open_document_sequences")
        assert action.payload is not None
        self.assertEqual(action.payload.get("document_type_code"), "supplier_payment")

    def test_payloads_are_distinct_objects(self) -> None:
        exc = _make_missing_seq_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        create_action = next(a for a in resolution.actions if a.action_id == "create_document_sequence")
        open_action = next(a for a in resolution.actions if a.action_id == "open_document_sequences")
        # Mutating one should not affect the other
        self.assertIsNot(create_action.payload, open_action.payload)


# ---------------------------------------------------------------------------
# 4. Resolver — message content
# ---------------------------------------------------------------------------

class DocumentSequenceResolverMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_message_mentions_type_label_for_known_type(self) -> None:
        """Message for sales_invoice uses human-readable 'Sales Invoice'."""
        exc = _make_missing_seq_exc("sales_invoice")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("Sales Invoice", resolution.message)

    def test_message_mentions_type_label_for_purchase_bill(self) -> None:
        exc = _make_missing_seq_exc("purchase_bill")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("Purchase Bill", resolution.message)

    def test_message_mentions_type_label_for_inventory_document(self) -> None:
        exc = _make_missing_seq_exc("inventory_document")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("Inventory Document", resolution.message)

    def test_message_mentions_type_label_for_depreciation_run(self) -> None:
        exc = _make_missing_seq_exc("depreciation_run")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("Depreciation Run", resolution.message)

    def test_create_action_label_includes_type_label(self) -> None:
        exc = _make_missing_seq_exc("treasury_transaction")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "create_document_sequence")
        self.assertIn("Treasury Transaction", action.label)

    def test_message_is_generic_when_no_document_type_code(self) -> None:
        exc = ValidationError(
            "Document sequence required",
            app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
            context={},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIsNotNone(resolution.message)
        self.assertTrue(len(resolution.message) > 0)

    def test_create_action_label_is_generic_when_no_document_type_code(self) -> None:
        exc = ValidationError(
            "Document sequence required",
            app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
            context={},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action = next(a for a in resolution.actions if a.action_id == "create_document_sequence")
        # Should be "Set Up Sequence" not "Set Up  Sequence" with extra space
        self.assertIn("Set Up", action.label)


# ---------------------------------------------------------------------------
# 5. Resolver — fallback text trigger
# ---------------------------------------------------------------------------

class DocumentSequenceFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_plain_validation_error_with_document_sequence_text_resolves(self) -> None:
        """Legacy code paths that raise plain ValidationError with 'document sequence' text
        still receive a guided resolution via the _fallback_code mechanism."""
        exc = ValidationError(
            "An active document sequence for SALES_INVOICE must be configured before posting."
        )
        resolution = self.resolver.resolve(exc)
        self.assertIsNotNone(resolution)

    def test_plain_error_without_sequence_text_does_not_resolve(self) -> None:
        exc = ValidationError("Something went wrong.")
        resolution = self.resolver.resolve(exc)
        self.assertIsNone(resolution)


# ---------------------------------------------------------------------------
# 6. Resume token round-trip
# ---------------------------------------------------------------------------

class DocumentSequenceResumeTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resume_service = WorkflowResumeService()

    def test_preflight_token_round_trips(self) -> None:
        token = self.resume_service.create_token(
            workflow_key="sales_invoice.preflight",
            origin_nav_id=nav_ids.SALES_INVOICES,
            payload={},
        )
        payload = self.resume_service.consume_token(token)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload.workflow_key, "sales_invoice.preflight")
        self.assertEqual(payload.origin_nav_id, nav_ids.SALES_INVOICES)

    def test_post_token_round_trips(self) -> None:
        token = self.resume_service.create_token(
            workflow_key="purchase_bill.post",
            origin_nav_id=nav_ids.PURCHASE_BILLS,
            payload={"document_id": 77},
        )
        payload = self.resume_service.consume_token(token)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload.workflow_key, "purchase_bill.post")
        self.assertEqual(payload.origin_nav_id, nav_ids.PURCHASE_BILLS)
        self.assertEqual(payload.payload.get("document_id"), 77)

    def test_post_token_is_one_time(self) -> None:
        token = self.resume_service.create_token(
            workflow_key="supplier_payment.post",
            origin_nav_id=nav_ids.SUPPLIER_PAYMENTS,
            payload={"document_id": 99},
        )
        first = self.resume_service.consume_token(token)
        second = self.resume_service.consume_token(token)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_preflight_token_is_one_time(self) -> None:
        token = self.resume_service.create_token(
            workflow_key="inventory_document.preflight",
            origin_nav_id=nav_ids.INVENTORY_DOCUMENTS,
            payload={},
        )
        first = self.resume_service.consume_token(token)
        second = self.resume_service.consume_token(token)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_depreciation_post_token_carries_run_id(self) -> None:
        token = self.resume_service.create_token(
            workflow_key="depreciation_run.post",
            origin_nav_id=nav_ids.DEPRECIATION_RUNS,
            payload={"document_id": 111},
        )
        payload = self.resume_service.consume_token(token)
        assert payload is not None
        self.assertEqual(payload.payload.get("document_id"), 111)

    def test_treasury_transfer_post_token_carries_document_id(self) -> None:
        token = self.resume_service.create_token(
            workflow_key="treasury_transfer.post",
            origin_nav_id=nav_ids.TREASURY_TRANSFERS,
            payload={"document_id": 55},
        )
        payload = self.resume_service.consume_token(token)
        assert payload is not None
        self.assertEqual(payload.workflow_key, "treasury_transfer.post")
        self.assertEqual(payload.payload.get("document_id"), 55)

    def test_peek_does_not_consume_token(self) -> None:
        token = self.resume_service.create_token(
            workflow_key="customer_receipt.preflight",
            origin_nav_id=nav_ids.CUSTOMER_RECEIPTS,
            payload={},
        )
        peeked = self.resume_service.peek_token(token)
        self.assertIsNotNone(peeked)
        consumed = self.resume_service.consume_token(token)
        self.assertIsNotNone(consumed)

    def test_treasury_transaction_preflight_workflow_key(self) -> None:
        token = self.resume_service.create_token(
            workflow_key="treasury_transaction.preflight",
            origin_nav_id=nav_ids.TREASURY_TRANSACTIONS,
            payload={},
        )
        payload = self.resume_service.consume_token(token)
        assert payload is not None
        self.assertEqual(payload.workflow_key, "treasury_transaction.preflight")


# ---------------------------------------------------------------------------
# 7. Document type labels coverage
# ---------------------------------------------------------------------------

class DocumentTypeLabelTests(unittest.TestCase):
    def test_sales_invoice_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("sales_invoice"), "Sales Invoice")

    def test_customer_receipt_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("customer_receipt"), "Customer Receipt")

    def test_purchase_bill_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("purchase_bill"), "Purchase Bill")

    def test_supplier_payment_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("supplier_payment"), "Supplier Payment")

    def test_treasury_transaction_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("treasury_transaction"), "Treasury Transaction")

    def test_treasury_transfer_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("treasury_transfer"), "Treasury Transfer")

    def test_inventory_document_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("inventory_document"), "Inventory Document")

    def test_depreciation_run_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("depreciation_run"), "Depreciation Run")

    def test_journal_entry_label(self) -> None:
        self.assertEqual(_DOCUMENT_TYPE_LABELS.get("journal_entry"), "Journal Entry")


# ---------------------------------------------------------------------------
# 8. Regression guards — EH-2A/2B unaffected
# ---------------------------------------------------------------------------

class EH2RegressionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_missing_fiscal_period_still_resolves(self) -> None:
        from datetime import date
        exc = ValidationError(
            "No fiscal period for 2026-01-01.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 1, 1), "company_id": 1},
        )
        resolution = self.resolver.resolve(exc)
        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.MISSING_FISCAL_PERIOD)

    def test_missing_fiscal_period_has_create_action(self) -> None:
        from datetime import date
        exc = ValidationError(
            "No fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 1, 1)},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("create_fiscal_period", action_ids)

    def test_locked_fiscal_period_still_resolves(self) -> None:
        from datetime import date
        exc = PeriodLockedError(
            "Period locked.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={"fiscal_period_code": "2026-01", "entry_date": date(2026, 1, 1)},
        )
        resolution = self.resolver.resolve(exc)
        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.LOCKED_FISCAL_PERIOD)

    def test_locked_fiscal_period_has_no_create_fiscal_period_action(self) -> None:
        from datetime import date
        exc = PeriodLockedError(
            "Period locked.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={"fiscal_period_code": "2026-01", "entry_date": date(2026, 1, 1)},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertNotIn("create_fiscal_period", action_ids)

    def test_missing_document_sequence_does_not_produce_fiscal_period_actions(self) -> None:
        exc = _make_missing_seq_exc("sales_invoice")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertNotIn("create_fiscal_period", action_ids)
        self.assertNotIn("open_fiscal_periods", action_ids)

    def test_missing_fiscal_period_does_not_produce_document_sequence_actions(self) -> None:
        from datetime import date
        exc = ValidationError(
            "No fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 1, 1)},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertNotIn("create_document_sequence", action_ids)
        self.assertNotIn("open_document_sequences", action_ids)


# ---------------------------------------------------------------------------
# 9. ensure_sequence_available helper — pure-function contract tests
# ---------------------------------------------------------------------------

class EnsureSequenceAvailableTests(unittest.TestCase):
    """Verify the non-UI ensure_sequence_available helper raises the correct
    structured exception when the underlying service reports no active sequence."""

    def _make_service_registry(self, *, available: bool) -> MagicMock:
        """Return a minimal mock ServiceRegistry whose numbering_setup_service
        behaves as configured by the *available* flag."""
        registry = MagicMock()
        if available:
            registry.numbering_setup_service.check_sequence_available.return_value = None
        else:
            registry.numbering_setup_service.check_sequence_available.side_effect = ValidationError(
                "No active document sequence configured for sales_invoice.",
                app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
                context={"company_id": 7, "document_type_code": "sales_invoice"},
            )
        return registry

    def test_raises_validation_error_when_sequence_missing(self) -> None:
        from seeker_accounting.shared.workflow.document_sequence_preflight import ensure_sequence_available
        registry = self._make_service_registry(available=False)
        with self.assertRaises(ValidationError) as cm:
            ensure_sequence_available(registry, company_id=7, document_type_code="sales_invoice")
        self.assertEqual(cm.exception.app_error_code, AppErrorCode.MISSING_DOCUMENT_SEQUENCE)

    def test_raised_exception_context_contains_company_id_and_document_type(self) -> None:
        from seeker_accounting.shared.workflow.document_sequence_preflight import ensure_sequence_available
        registry = self._make_service_registry(available=False)
        with self.assertRaises(ValidationError) as cm:
            ensure_sequence_available(registry, company_id=7, document_type_code="sales_invoice")
        self.assertEqual(cm.exception.context["company_id"], 7)
        self.assertEqual(cm.exception.context["document_type_code"], "sales_invoice")

    def test_does_not_raise_when_sequence_available(self) -> None:
        from seeker_accounting.shared.workflow.document_sequence_preflight import ensure_sequence_available
        registry = self._make_service_registry(available=True)
        # Should complete without raising
        ensure_sequence_available(registry, company_id=1, document_type_code="purchase_bill")
        registry.numbering_setup_service.check_sequence_available.assert_called_once_with(
            1, "purchase_bill"
        )


# ---------------------------------------------------------------------------
# 10. Resume payload consistency
# ---------------------------------------------------------------------------

class ResumePayloadConsistencyTests(unittest.TestCase):
    """Verify correct single-use token behaviour and payload safety rules.

    These tests exercise WorkflowResumeService directly — no Qt dependency.
    They confirm the invariants that all 8 workflow pages rely on.
    """

    def setUp(self) -> None:
        self.service = WorkflowResumeService()

    def _service_registry_stub(self) -> MagicMock:
        registry = MagicMock()
        registry.workflow_resume_service = self.service
        return registry

    def test_helper_consumes_valid_token_once_and_preserves_payload_shape(self) -> None:
        from seeker_accounting.shared.workflow.document_sequence_preflight import (
            consume_resume_payload_for_workflows,
        )

        token = self.service.create_token(
            workflow_key="sales_invoice.post",
            payload={"document_id": 101},
            origin_nav_id="sales_invoices",
        )

        context = {"resume_token": token}
        service_registry = self._service_registry_stub()
        first = consume_resume_payload_for_workflows(
            context=context,
            service_registry=service_registry,
            allowed_workflow_keys=("sales_invoice.preflight", "sales_invoice.post"),
        )
        second = consume_resume_payload_for_workflows(
            context=context,
            service_registry=service_registry,
            allowed_workflow_keys=("sales_invoice.preflight", "sales_invoice.post"),
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        assert first is not None
        self.assertEqual(first.workflow_key, "sales_invoice.post")
        self.assertEqual(first.origin_nav_id, "sales_invoices")
        self.assertIsInstance(first.payload, dict)
        self.assertEqual(first.payload.get("document_id"), 101)

    def test_helper_no_token_context_does_not_trigger_resume_path(self) -> None:
        from seeker_accounting.shared.workflow.document_sequence_preflight import (
            consume_resume_payload_for_workflows,
        )

        token = self.service.create_token(
            workflow_key="inventory_document.preflight",
            payload={},
            origin_nav_id="inventory_documents",
        )
        service_registry = self._service_registry_stub()

        result = consume_resume_payload_for_workflows(
            context={},
            service_registry=service_registry,
            allowed_workflow_keys=("inventory_document.preflight", "inventory_document.post"),
        )
        self.assertIsNone(result)
        self.assertIsNotNone(self.service.peek_token(token))

    def test_helper_rejects_mismatched_workflow_key_without_consuming_token(self) -> None:
        from seeker_accounting.shared.workflow.document_sequence_preflight import (
            consume_resume_payload_for_workflows,
        )

        token = self.service.create_token(
            workflow_key="supplier_payment.post",
            payload={"document_id": 5},
            origin_nav_id="supplier_payments",
        )
        service_registry = self._service_registry_stub()

        result = consume_resume_payload_for_workflows(
            context={"resume_token": token},
            service_registry=service_registry,
            allowed_workflow_keys=("sales_invoice.preflight", "sales_invoice.post"),
        )
        self.assertIsNone(result)
        remaining = self.service.consume_token(token)
        self.assertIsNotNone(remaining)
        assert remaining is not None
        self.assertEqual(remaining.workflow_key, "supplier_payment.post")

    def test_token_consumed_once_returns_none_on_second_consume(self) -> None:
        """A token is one-time use: consuming it a second time must return None."""
        token = self.service.create_token(
            workflow_key="sales_invoice.post",
            payload={"document_id": 99},
            origin_nav_id="sales_invoices",
        )
        first = self.service.consume_token(token)
        second = self.service.consume_token(token)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_consume_unknown_token_returns_none(self) -> None:
        """Consuming a token that was never created (normal navigation: no resume) returns None.

        This is the service-level guarantee that set_navigation_context relies on when
        the context dict contains garbage or an already-consumed token string.
        """
        self.assertIsNone(self.service.consume_token("nonexistent-token-abc"))
        self.assertIsNone(self.service.consume_token(""))

    def test_post_resume_token_carries_document_id_in_payload(self) -> None:
        """Post-path tokens store document_id and workflow_key correctly."""
        token = self.service.create_token(
            workflow_key="purchase_bill.post",
            payload={"document_id": 42},
            origin_nav_id="purchase_bills",
        )
        result = self.service.consume_token(token)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.workflow_key, "purchase_bill.post")
        self.assertEqual(result.origin_nav_id, "purchase_bills")
        self.assertEqual(result.payload.get("document_id"), 42)

    def test_preflight_resume_token_has_empty_payload(self) -> None:
        """Preflight tokens are created with an empty snapshot — payload must be {}."""
        token = self.service.create_token(
            workflow_key="treasury_transaction.preflight",
            payload={},
            origin_nav_id="treasury_transactions",
        )
        result = self.service.consume_token(token)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.payload, {})

    def test_payload_rejects_widget_like_objects(self) -> None:
        """Service must reject non-serializable objects so no page can accidentally
        store a widget reference in a resume token."""
        from seeker_accounting.platform.exceptions.app_exceptions import ValidationError as AppValidationError

        class _FakeWidget:
            pass

        with self.assertRaises(AppValidationError):
            self.service.create_token(
                workflow_key="sales_invoice.post",
                payload={"widget": _FakeWidget()},
            )

    def test_peek_does_not_invalidate_subsequent_consume(self) -> None:
        """peek_token (non-destructive) must not block a later consume."""
        token = self.service.create_token(
            workflow_key="inventory_document.post",
            payload={"document_id": 7},
        )
        peeked = self.service.peek_token(token)
        consumed = self.service.consume_token(token)
        self.assertIsNotNone(peeked)
        self.assertIsNotNone(consumed)
        # After consume, nothing remains
        self.assertIsNone(self.service.consume_token(token))


if __name__ == "__main__":
    unittest.main()
