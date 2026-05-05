"""Unit tests for the structured exclusion-reason taxonomy (P3.S6)."""
from __future__ import annotations

import unittest

from seeker_accounting.modules.payroll.services.payroll_exclusion_reasons import (
    REASON_CHOICES,
    ExclusionReasonCode,
    format_reason,
    parse_reason,
    reason_label,
)


class ExclusionReasonsTests(unittest.TestCase):
    def test_choices_are_unique_and_complete(self) -> None:
        codes = [c.code for c in REASON_CHOICES]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertSetEqual(set(codes), set(ExclusionReasonCode))

    def test_format_reason_with_note(self) -> None:
        out = format_reason(ExclusionReasonCode.DISPUTE, "Under review by HR")
        self.assertEqual(out, "dispute: Under review by HR")

    def test_format_reason_without_note(self) -> None:
        self.assertEqual(
            format_reason(ExclusionReasonCode.UNPAID_LEAVE, None),
            "unpaid_leave",
        )
        self.assertEqual(
            format_reason(ExclusionReasonCode.UNPAID_LEAVE, "   "),
            "unpaid_leave",
        )

    def test_parse_round_trip(self) -> None:
        stored = format_reason(ExclusionReasonCode.OTHER, "ad-hoc")
        code, note = parse_reason(stored)
        self.assertEqual(code, "other")
        self.assertEqual(note, "ad-hoc")

    def test_parse_bare_code(self) -> None:
        code, note = parse_reason("off_cycle")
        self.assertEqual(code, "off_cycle")
        self.assertEqual(note, "")

    def test_parse_legacy_free_text(self) -> None:
        code, note = parse_reason("personal reason")
        self.assertIsNone(code)
        self.assertEqual(note, "personal reason")

    def test_parse_empty(self) -> None:
        self.assertEqual(parse_reason(None), (None, ""))
        self.assertEqual(parse_reason(""), (None, ""))

    def test_reason_label_structured(self) -> None:
        self.assertEqual(
            reason_label("dispute: HR review"),
            "Pay dispute / under review — HR review",
        )

    def test_reason_label_bare(self) -> None:
        self.assertEqual(reason_label("unpaid_leave"), "On unpaid leave")

    def test_reason_label_legacy(self) -> None:
        self.assertEqual(reason_label("personal"), "personal")


if __name__ == "__main__":
    unittest.main()
