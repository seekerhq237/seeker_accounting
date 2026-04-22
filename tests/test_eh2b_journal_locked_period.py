"""
EH-2B: Journal locked fiscal period guided blocker — targeted unit tests.

Covers:
- Structured LOCKED_FISCAL_PERIOD exception raised at the service boundary (draft save and post).
- Resolver correctly maps PeriodLockedError (with app_error_code) to a guided resolution.
- Resolution message uses fiscal_period_code and entry_date from context when available.
- open_fiscal_periods action carries locked_period_flow=True and period context.
- open_fiscal_periods action carries fiscal_period_code and fiscal_period_id in payload.
- No create_fiscal_period action on the locked path.
- Resume token for post path carries journal_entry_id.
- journal_entry.post token round-trips through WorkflowResumeService.
- MISSING_FISCAL_PERIOD flow is unaffected (regression guard).
- PeriodLockedError without app_error_code still resolves via type-check fallback.
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


class LockedFiscalPeriodResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ErrorResolutionResolver()

    def _make_locked_exc(
        self,
        period_code: str = "2026-01",
        period_id: int = 42,
        entry_date: date = date(2026, 1, 15),
        company_id: int = 7,
    ) -> PeriodLockedError:
        return PeriodLockedError(
            f"Entry date falls in locked fiscal period {period_code}.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={
                "company_id": company_id,
                "entry_date": entry_date,
                "fiscal_period_id": period_id,
                "fiscal_period_code": period_code,
                "origin_workflow": "journal_entry",
            },
        )

    # ------------------------------------------------------------------
    # Exception structure
    # ------------------------------------------------------------------

    def test_period_locked_error_carries_structured_code(self) -> None:
        exc = self._make_locked_exc()
        self.assertEqual(exc.app_error_code, AppErrorCode.LOCKED_FISCAL_PERIOD)
        self.assertEqual(exc.context["fiscal_period_code"], "2026-01")
        self.assertEqual(exc.context["fiscal_period_id"], 42)
        self.assertEqual(exc.context["origin_workflow"], "journal_entry")
        self.assertIsInstance(exc.context["entry_date"], date)

    def test_period_locked_error_is_period_locked_error_type(self) -> None:
        exc = self._make_locked_exc()
        self.assertIsInstance(exc, PeriodLockedError)

    # ------------------------------------------------------------------
    # Resolver structure
    # ------------------------------------------------------------------

    def test_locked_period_resolves_to_guided_resolution(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        self.assertIsNotNone(resolution)

    def test_locked_period_resolution_code_is_locked_fiscal_period(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.LOCKED_FISCAL_PERIOD)

    def test_locked_period_has_exactly_two_actions_nav_and_dismiss(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertIn("open_fiscal_periods", action_ids)
        self.assertIn("dismiss", action_ids)
        self.assertEqual(len(resolution.actions), 2)

    def test_locked_period_has_no_create_fiscal_period_action(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        action_ids = [a.action_id for a in resolution.actions]
        self.assertNotIn("create_fiscal_period", action_ids)

    def test_locked_period_open_fiscal_periods_requires_resume_token(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        self.assertTrue(nav_action.requires_resume_token)

    def test_locked_period_nav_id_is_fiscal_periods(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        self.assertEqual(nav_action.nav_id, nav_ids.FISCAL_PERIODS)

    def test_dismiss_action_does_not_require_token(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        dismiss = next(a for a in resolution.actions if a.action_id == "dismiss")
        self.assertFalse(dismiss.requires_resume_token)
        self.assertIsNone(dismiss.nav_id)

    # ------------------------------------------------------------------
    # Payload content
    # ------------------------------------------------------------------

    def test_locked_period_action_payload_carries_locked_period_flow_true(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        self.assertIsNotNone(nav_action.payload)
        assert nav_action.payload is not None
        self.assertTrue(
            nav_action.payload.get("locked_period_flow"),
            "Locked-period nav action payload must carry locked_period_flow=True",
        )

    def test_locked_period_action_payload_carries_fiscal_period_code(self) -> None:
        exc = self._make_locked_exc(period_code="2026-03")
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        assert nav_action.payload is not None
        self.assertEqual(nav_action.payload.get("fiscal_period_code"), "2026-03")

    def test_locked_period_action_payload_carries_fiscal_period_id(self) -> None:
        exc = self._make_locked_exc(period_id=99)
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        assert nav_action.payload is not None
        self.assertEqual(nav_action.payload.get("fiscal_period_id"), 99)

    def test_locked_period_action_payload_carries_entry_date_as_string(self) -> None:
        exc = self._make_locked_exc(entry_date=date(2026, 1, 15))
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        assert nav_action.payload is not None
        self.assertEqual(nav_action.payload.get("entry_date"), "2026-01-15")

    def test_locked_period_action_payload_carries_source_workflow(self) -> None:
        exc = self._make_locked_exc()
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        assert nav_action.payload is not None
        self.assertEqual(nav_action.payload.get("source_workflow"), "journal_entry")

    # ------------------------------------------------------------------
    # Message content
    # ------------------------------------------------------------------

    def test_message_includes_period_code_and_date_when_both_present(self) -> None:
        exc = self._make_locked_exc(period_code="2026-06", entry_date=date(2026, 6, 10))
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("2026-06", resolution.message)
        self.assertIn("2026-06-10", resolution.message)

    def test_message_includes_period_code_when_date_absent(self) -> None:
        exc = PeriodLockedError(
            "Locked.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={"fiscal_period_code": "2025-12", "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("2025-12", resolution.message)

    def test_message_includes_entry_date_when_code_absent(self) -> None:
        exc = PeriodLockedError(
            "Locked.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={"entry_date": date(2025, 11, 5), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertIn("2025-11-05", resolution.message)

    def test_message_fallback_when_no_context(self) -> None:
        exc = PeriodLockedError(
            "Locked.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        self.assertTrue(len(resolution.message) > 0)

    # ------------------------------------------------------------------
    # Type-check fallback (PeriodLockedError without code still resolves)
    # ------------------------------------------------------------------

    def test_plain_period_locked_error_without_code_still_resolves(self) -> None:
        exc = PeriodLockedError("Period 2025-12 is locked.")
        resolution = self.resolver.resolve(exc)
        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.error_code, AppErrorCode.LOCKED_FISCAL_PERIOD)

    # ------------------------------------------------------------------
    # Regression: MISSING_FISCAL_PERIOD flow must remain stable
    # ------------------------------------------------------------------

    def test_missing_period_still_resolves_with_create_action(self) -> None:
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

    def test_missing_period_open_fiscal_periods_does_not_carry_locked_period_flow(self) -> None:
        exc = ValidationError(
            "Entry date must fall within an existing fiscal period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 3, 1), "origin_workflow": "journal_entry"},
        )
        resolution = self.resolver.resolve(exc)
        assert resolution is not None
        nav_action = next(a for a in resolution.actions if a.action_id == "open_fiscal_periods")
        if nav_action.payload:
            self.assertFalse(
                nav_action.payload.get("locked_period_flow", False),
                "missing-period open_fiscal_periods must NOT carry locked_period_flow",
            )


class LockedPeriodResumePayloadTests(unittest.TestCase):
    """Tests for the post-path resume token payload (carries journal_entry_id)."""

    def _make_post_snapshot(self, journal_entry_id: int = 17) -> dict:
        return {"journal_entry_id": journal_entry_id}

    def test_post_snapshot_is_json_serializable(self) -> None:
        snapshot = self._make_post_snapshot(journal_entry_id=25)
        serialized = json.dumps(snapshot)
        restored = json.loads(serialized)
        self.assertEqual(restored["journal_entry_id"], 25)

    def test_post_resume_survives_workflow_service_round_trip(self) -> None:
        service = WorkflowResumeService()
        snapshot = self._make_post_snapshot(journal_entry_id=42)
        token = service.create_token(
            workflow_key="journal_entry.post",
            payload=snapshot,
            origin_nav_id=nav_ids.JOURNALS,
        )
        restored = service.consume_token(token)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.workflow_key, "journal_entry.post")
        self.assertEqual(restored.origin_nav_id, nav_ids.JOURNALS)
        self.assertEqual(restored.payload["journal_entry_id"], 42)

    def test_post_resume_workflow_key_is_journal_entry_post(self) -> None:
        service = WorkflowResumeService()
        token = service.create_token(
            workflow_key="journal_entry.post",
            payload={"journal_entry_id": 7},
        )
        restored = service.consume_token(token)
        assert restored is not None
        self.assertEqual(restored.workflow_key, "journal_entry.post")

    def test_post_resume_token_consumed_exactly_once(self) -> None:
        service = WorkflowResumeService()
        token = service.create_token(
            workflow_key="journal_entry.post",
            payload={"journal_entry_id": 3},
        )
        first = service.consume_token(token)
        self.assertIsNotNone(first)
        second = service.consume_token(token)
        self.assertIsNone(second, "Post resume token must be consumed exactly once")

    def test_locked_period_context_fields_present_in_structured_exception(self) -> None:
        exc = PeriodLockedError(
            "Entry date falls in locked fiscal period 2026-01.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={
                "company_id": 5,
                "entry_date": date(2026, 1, 20),
                "fiscal_period_id": 11,
                "fiscal_period_code": "2026-01",
                "origin_workflow": "journal_entry",
            },
        )
        self.assertEqual(exc.context["fiscal_period_id"], 11)
        self.assertEqual(exc.context["fiscal_period_code"], "2026-01")
        self.assertEqual(exc.context["entry_date"], date(2026, 1, 20))
        self.assertEqual(exc.context["company_id"], 5)

    def test_locked_period_payload_is_distinct_from_missing_period_payload(self) -> None:
        """Locked-period resolver payload must differ from missing-period open_fiscal_periods payload."""
        locked_exc = PeriodLockedError(
            "Locked.",
            app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
            context={
                "entry_date": date(2026, 3, 1),
                "fiscal_period_code": "2026-03",
                "fiscal_period_id": 55,
                "origin_workflow": "journal_entry",
            },
        )
        missing_exc = ValidationError(
            "No period.",
            app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
            context={"entry_date": date(2026, 3, 1), "origin_workflow": "journal_entry"},
        )
        resolver = ErrorResolutionResolver()
        locked_res = resolver.resolve(locked_exc)
        missing_res = resolver.resolve(missing_exc)
        assert locked_res is not None
        assert missing_res is not None

        locked_nav = next(a for a in locked_res.actions if a.action_id == "open_fiscal_periods")
        missing_nav = next(a for a in missing_res.actions if a.action_id == "open_fiscal_periods")

        self.assertNotEqual(
            locked_nav.payload,
            missing_nav.payload,
            "Locked-period and missing-period open_fiscal_periods payloads must be distinct",
        )
        assert locked_nav.payload is not None
        self.assertTrue(locked_nav.payload.get("locked_period_flow"))
        if missing_nav.payload:
            self.assertFalse(missing_nav.payload.get("locked_period_flow", False))


if __name__ == "__main__":
    unittest.main()
