from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seeker_accounting.modules.payroll.ui.i18n import (
    payroll_locale,
    payroll_locale_scope,
    set_payroll_locale,
    tr,
)


class PayrollP11TerminologyTests(unittest.TestCase):
    def test_glossary_exists_with_canonical_terms(self) -> None:
        glossary = Path("docs/payroll_glossary.md")
        self.assertTrue(glossary.exists())
        text = glossary.read_text(encoding="utf-8")
        for term in (
            "Payroll run",
            "Payroll component",
            "Compensation",
            "Variable input",
            "Statutory authority",
            "Remittance",
        ):
            self.assertIn(term, text)

    def test_translation_scaffold_switches_payroll_strings(self) -> None:
        set_payroll_locale("en")
        self.assertEqual(tr("Payroll run"), "Payroll run")
        with payroll_locale_scope("fr"):
            self.assertEqual(payroll_locale(), "fr")
            self.assertEqual(tr("Payroll run"), "Cycle de paie")
            self.assertEqual(tr("Statutory authority"), "Autorité statutaire")
        self.assertEqual(payroll_locale(), "en")

    def test_workbench_pane_registry_uses_active_payroll_locale(self) -> None:
        from seeker_accounting.modules.payroll.ui.workbench.workbench_panes import (
            PANE_COMPENSATION,
            PANE_RUN,
            build_workbench_panes,
        )

        with payroll_locale_scope("fr"):
            panes = {pane.key: pane for pane in build_workbench_panes()}
            self.assertEqual(panes[PANE_RUN].label, "Cycles de paie")
            self.assertEqual(panes[PANE_COMPENSATION].label, "Rémunération")

    def test_terminology_checker_catches_rejected_ui_terms(self) -> None:
        from scripts.check_payroll_terminology import check_paths

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_payroll_ui.py"
            path.write_text('TITLE = "Payroll Run"\nLABEL = "Variable Input Batch"\n', encoding="utf-8")
            findings = check_paths([path])
        self.assertGreaterEqual(len(findings), 2)
        self.assertTrue(any(f.code == "PAYROLL_RUN_CASE" for f in findings))
        self.assertTrue(any(f.code == "INPUT_BATCH_UI" for f in findings))

    def test_payroll_module_has_no_rejected_terms(self) -> None:
        from scripts.check_payroll_terminology import DEFAULT_SCAN_ROOT, check_paths

        findings = check_paths([DEFAULT_SCAN_ROOT])
        self.assertEqual([], [finding.format() for finding in findings])


if __name__ == "__main__":
    unittest.main()