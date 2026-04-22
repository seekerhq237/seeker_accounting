"""
EH-2A / EH-2A.1: Journal fiscal-period guided blocker — targeted unit tests.

Covers:
- Structured MISSING_FISCAL_PERIOD exception produced at the service boundary.
- Resolver correctly maps the code to a two-action guided resolution.
- Resolution message uses date and company name from context when available.
- create_fiscal_period action carries open_create_flow=True and entry_date.
- open_fiscal_periods action does NOT carry open_create_flow.
- LOCKED_FISCAL_PERIOD remains distinct (no create_fiscal_period action).
- Journal snapshot structure is serializable and round-trips through WorkflowResumeService.
- Resume token is consumed exactly once (one-time guarantee).
- Stale / unknown tokens are handled safely.
"""
from __future__ import annotations

import json
import unittest
from datetime import date

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.navigation.workflow_resume_service import WorkflowResumeService
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.app_exceptions import (
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver


class MissingFiscalPeriodResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def test_structured_exception_carries_missing_period_code(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={
                "company_id": 7,
                "entry_date": date(2026, 3, 10),
                "origin_workflow": "journal_entry",
            },
        )
        self.assertEqual(exc.app_error_code, AppErrorCode.MISSING_FISCAL_PERIOD)
        self.assertEqual(exc.context["company_id"], 7)
        self.assertEqual(exc.context["origin_workflow"], "journal_entry")

    def test_missing_period_resolves_to_two_navigation_actions_and_dismiss(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 1, 15), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)

        self.assertIsNotNone(resolution)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("create_fiscal_period", action_ids)
        self.assertIn("open_fiscal_periods", action_ids)
        self.assertIn("dismiss", action_ids)
        self.assertEqual(resolution.error_code, AppErrorCode.MISSING_FISCAL_PERIOD)

    def test_both_navigation_actions_require_resume_token(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 1, 15), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None

        for action in resolution.actions:
            if action.action_id in ("create_fiscal_period", "open_fiscal_periods"):
                self.assertTrue(action.requires_resume_token, f"{action.action_id} must require_resume_token")
                self.assertEqual(action.nav_id, nav_ids.FISCAL_PERIODS)

    def test_dismiss_action_does_not_require_token_or_nav(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 1, 15), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None

        dismiss = next(a for a in resolution.actions if a.action_id == "dismiss")
        self.assertFalse(dismiss.requires_resume_token)
        self.assertIsNone(dismiss.nav_id)

    def test_message_includes_date_and_company_when_both_available(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 1, 15), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc, context={"company_name": "Acme Corp"})
        assert resolution is not None

        self.assertIn("2026-01-15", resolution.message)
        self.assertIn("Acme Corp", resolution.message)

    def test_message_includes_date_when_company_absent(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 3, 1), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None

        self.assertIn("2026-03-01", resolution.message)

    def test_action_payload_contains_source_workflow_and_entry_date(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 3, 1), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None

        create_action = next(a for a in resolution.actions if a.action_id == "create_fiscal_period")
        self.assertIsNotNone(create_action.payload)
        assert create_action.payload is not None
        self.assertEqual(create_action.payload.get("source_workflow"), "journal_entry")
        self.assertEqual(create_action.payload.get("entry_date"), "2026-03-01")

    def test_create_fiscal_period_action_carries_open_create_flow_true(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 3, 1), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None

        create_action = next(a for a in resolution.actions if a.action_id == "create_fiscal_period")
        assert create_action.payload is not None
        self.assertTrue(
            create_action.payload.get("open_create_flow"),
            "create_fiscal_period payload must carry open_create_flow=True",
        )

    def test_open_fiscal_periods_action_does_not_carry_open_create_flow(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 3, 1), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None

        open_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        # open_fiscal_periods is the general landing action and must NOT trigger the auto-create flow
        if open_action.payload:
            self.assertFalse(
                open_action.payload.get("open_create_flow", False),
                "open_fiscal_periods must NOT carry open_create_flow",
            )

    def test_two_actions_have_distinct_payloads(self) -> None:
        """create_fiscal_period and open_fiscal_periods must carry different payloads."""
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 5, 20), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None

        create_action = next(a for a in resolution.actions if a.action_id == "create_fiscal_period")
        open_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        self.assertNotEqual(
            create_action.payload,
            open_action.payload,
            "The two navigation actions must carry different payloads",
        )

    def test_locked_period_resolution_is_distinct_no_create_action(self) -> None:
        exc = PeriodLockedError("Period 2025-12 is locked.")
        resolution = self.resolver.resolve(exc)

        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.LOCKED_FISCAL_PERIOD)
        action_ids = [a.action_id for a in resolution.actions]
        self.assertNotIn("create_fiscal_period", action_ids)
        self.assertIn("open_fiscal_periods", action_ids)

    def test_plain_validation_error_without_code_does_not_resolve(self) -> None:
        exc = ValidationError("Some unrelated validation failure.")
        resolution = self.resolver.resolve(exc)
        self.assertIsNone(resolution)


class JournalSnapshotPayloadTests(unittest.TestCase):
    """Tests that the journal draft snapshot structure is serializable and restorable."""

    def _make_snapshot(self) -> dict:
        return {
            "entry_date": date(2026, 3, 10).isoformat(),
            "journal_type_code": "GENERAL",
            "reference": "TEST-2026-001",
            "description": "Opening balance for new period",
            "lines": [
                {
                    "account_id": 101,
                    "line_description": "Cash account",
                    "debit_amount": "5000.00",
                    "credit_amount": "0.00",
                },
                {
                    "account_id": 301,
                    "line_description": None,
                    "debit_amount": "0.00",
                    "credit_amount": "5000.00",
                },
            ],
        }

    def test_snapshot_is_json_serializable(self) -> None:
        snapshot = self._make_snapshot()
        serialized = json.dumps(snapshot)
        restored = json.loads(serialized)
        self.assertEqual(restored["entry_date"], "2026-03-10")
        self.assertEqual(restored["journal_type_code"], "GENERAL")
        self.assertEqual(len(restored["lines"]), 2)
        self.assertEqual(restored["lines"][0]["debit_amount"], "5000.00")
        self.assertIsNone(restored["lines"][1]["line_description"])

    def test_snapshot_survives_resume_service_round_trip(self) -> None:
        service = WorkflowResumeService()
        snapshot = self._make_snapshot()

        token = service.create_token(
            workflow_key="journal_entry.create",
            payload=snapshot,
            origin_nav_id=nav_ids.JOURNALS,
        )
        restored = service.consume_token(token)

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.workflow_key, "journal_entry.create")
        self.assertEqual(restored.origin_nav_id, nav_ids.JOURNALS)
        self.assertEqual(restored.payload["entry_date"], "2026-03-10")
        self.assertEqual(restored.payload["journal_type_code"], "GENERAL")
        self.assertEqual(len(restored.payload["lines"]), 2)
        self.assertEqual(restored.payload["lines"][0]["account_id"], 101)

    def test_snapshot_with_null_fields_survives_round_trip(self) -> None:
        service = WorkflowResumeService()
        snapshot = {
            "entry_date": "2026-04-01",
            "journal_type_code": "ADJUSTMENT",
            "reference": None,
            "description": None,
            "lines": [
                {"account_id": 5, "line_description": None, "debit_amount": "100.00", "credit_amount": "0.00"},
                {"account_id": 9, "line_description": None, "debit_amount": "0.00", "credit_amount": "100.00"},
            ],
        }
        token = service.create_token(workflow_key="journal_entry.create", payload=snapshot)
        restored = service.consume_token(token)
        assert restored is not None
        self.assertIsNone(restored.payload["reference"])
        self.assertIsNone(restored.payload["description"])

    def test_resume_token_consumed_only_once(self) -> None:
        service = WorkflowResumeService()
        token = service.create_token(
            workflow_key="journal_entry.create",
            payload={"entry_date": "2026-03-10", "journal_type_code": "GENERAL", "lines": []},
        )
        first = service.consume_token(token)
        self.assertIsNotNone(first)

        second = service.consume_token(token)
        self.assertIsNone(second, "Resume token must be consumed exactly once")

    def test_stale_resume_token_returns_none_safely(self) -> None:
        service = WorkflowResumeService()
        result = service.consume_token("nonexistent_token_abc123")
        self.assertIsNone(result)

    def test_discard_unknown_token_returns_false(self) -> None:
        service = WorkflowResumeService()
        discarded = service.discard_token("totally_fake_token")
        self.assertFalse(discarded)

    def test_discard_clears_token_before_consume(self) -> None:
        service = WorkflowResumeService()
        token = service.create_token(
            workflow_key="journal_entry.create",
            payload={"entry_date": "2026-03-10", "journal_type_code": "GENERAL", "lines": []},
        )
        discarded = service.discard_token(token)
        self.assertTrue(discarded)
        result = service.consume_token(token)
        self.assertIsNone(result, "Token should not be available after discard")


if __name__ == "__main__":
    unittest.main()
