"""Unit tests for the payroll run state machine (Phase 3 / P3.S1)."""
from __future__ import annotations

import unittest

from seeker_accounting.modules.payroll.services.payroll_run_state import (
    PayrollRunStateMachine,
    PayrollRunStatus,
    SIDE_STATES,
    STATUS_LABELS,
    TIMELINE_ORDER,
)


class PayrollRunStateMachineTests(unittest.TestCase):
    SM = PayrollRunStateMachine

    # ── transition table ─────────────────────────────────────────────

    def test_draft_can_calculate_or_void(self) -> None:
        allowed = self.SM.allowed_transitions("draft")
        self.assertIn("calculated", allowed)
        self.assertIn("voided", allowed)
        self.assertNotIn("approved", allowed)
        self.assertNotIn("posted", allowed)

    def test_calculated_allows_recalc_approve_void(self) -> None:
        allowed = self.SM.allowed_transitions("calculated")
        self.assertEqual(allowed, frozenset({"calculated", "submitted_for_review", "approved", "voided"}))

    def test_approved_only_to_posted(self) -> None:
        self.assertEqual(self.SM.allowed_transitions("approved"), frozenset({"posted"}))

    def test_posted_only_to_reversed(self) -> None:
        self.assertEqual(self.SM.allowed_transitions("posted"), frozenset({"reversed"}))

    def test_terminal_states(self) -> None:
        self.assertTrue(self.SM.is_terminal("voided"))
        self.assertTrue(self.SM.is_terminal("reversed"))
        for s in ("draft", "calculated", "approved", "posted"):
            self.assertFalse(self.SM.is_terminal(s), s)

    def test_unknown_status_has_no_transitions(self) -> None:
        self.assertEqual(self.SM.allowed_transitions("bogus"), frozenset())

    # ── action gating ─────────────────────────────────────────────────

    def test_can_calculate_only_in_draft_or_calculated(self) -> None:
        for s, expected in [
            ("draft", True),
            ("calculated", True),
            ("approved", False),
            ("posted", False),
            ("voided", False),
            ("reversed", False),
        ]:
            self.assertEqual(self.SM.can_calculate(s), expected, s)

    def test_can_approve_only_when_calculated(self) -> None:
        for s in ("draft", "approved", "posted", "voided", "reversed"):
            self.assertFalse(self.SM.can_approve(s), s)
        self.assertTrue(self.SM.can_approve("calculated"))

    def test_can_void_blocked_after_approval(self) -> None:
        self.assertTrue(self.SM.can_void("draft"))
        self.assertTrue(self.SM.can_void("calculated"))
        for s in ("approved", "posted", "voided", "reversed"):
            self.assertFalse(self.SM.can_void(s), s)

    def test_can_post_only_when_approved(self) -> None:
        self.assertTrue(self.SM.can_post("approved"))
        for s in ("draft", "calculated", "posted", "voided", "reversed"):
            self.assertFalse(self.SM.can_post(s), s)

    def test_can_reverse_only_when_posted(self) -> None:
        self.assertTrue(self.SM.can_reverse("posted"))
        for s in ("draft", "calculated", "approved", "voided", "reversed"):
            self.assertFalse(self.SM.can_reverse(s), s)

    def test_can_edit_inclusion_only_when_calculated(self) -> None:
        self.assertTrue(self.SM.can_edit_inclusion("calculated"))
        for s in ("draft", "approved", "posted", "voided", "reversed"):
            self.assertFalse(self.SM.can_edit_inclusion(s), s)

    def test_immutable_when_posted_or_reversed(self) -> None:
        self.assertTrue(self.SM.is_immutable("posted"))
        self.assertTrue(self.SM.is_immutable("reversed"))
        for s in ("draft", "calculated", "approved", "voided"):
            self.assertFalse(self.SM.is_immutable(s), s)

    # ── presentation ──────────────────────────────────────────────────

    def test_status_labels_complete(self) -> None:
        for s in PayrollRunStatus:
            self.assertIn(s.value, STATUS_LABELS, s)
            self.assertTrue(STATUS_LABELS[s.value])

    def test_primary_action_targets(self) -> None:
        self.assertEqual(
            self.SM.primary_action("draft").target_state, "calculated",
        )
        self.assertEqual(
            self.SM.primary_action("calculated").target_state, "approved",
        )
        self.assertEqual(
            self.SM.primary_action("approved").target_state, "posted",
        )
        action = self.SM.primary_action("posted")
        assert action is not None
        self.assertEqual(action.target_state, "reversed")
        self.assertTrue(action.is_destructive)
        self.assertIsNone(self.SM.primary_action("voided"))
        self.assertIsNone(self.SM.primary_action("reversed"))

    def test_timeline_and_side_states_disjoint(self) -> None:
        self.assertEqual(set(TIMELINE_ORDER) & set(SIDE_STATES), set())
        self.assertEqual(
            set(TIMELINE_ORDER) | set(SIDE_STATES),
            {s.value for s in PayrollRunStatus},
        )

    def test_can_transition_consistency(self) -> None:
        # Pure consistency: can_transition is the membership test on
        # allowed_transitions.
        for s in PayrollRunStatus:
            for t in PayrollRunStatus:
                expected = t.value in self.SM.allowed_transitions(s.value)
                self.assertEqual(
                    self.SM.can_transition(s.value, t.value),
                    expected,
                    f"{s.value}->{t.value}",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
