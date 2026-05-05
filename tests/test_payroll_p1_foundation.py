"""Smoke tests for Payroll P1 foundation primitives.

Covers:

- P1.S1: tokens + palette + qss_builder render in both themes.
- P1.S4: CodeLabelRegistry + SeverityPill.
- P1.S2: MoneyInput / RateInput / QuantityInput / CurrencyPicker.
- P1.S5: FieldValidator + LiveValidationPipeline + FormValidationCoordinator.
- P1.S3: InlineIssueBand, FormDialog, ConfirmDialog, SidePanel.
- P1.S7: EmptyState, KpiTile, WorkbenchHeader.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit


class P1FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    # ── P1.S1 — tokens / palette / qss_builder ────────────────────────

    def test_qss_builds_for_both_themes(self) -> None:
        from seeker_accounting.shared.ui.styles.palette import get_palette
        from seeker_accounting.shared.ui.styles.qss_builder import build_stylesheet
        from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

        for name in ("light", "dark"):
            qss = build_stylesheet(get_palette(name), DEFAULT_TOKENS)
            self.assertIn("SeverityPill", qss, f"missing severity rules in {name}")
            self.assertIn("InlineIssueBand", qss)
            self.assertIn("KpiTile", qss)
            self.assertIn("WorkbenchHeader", qss)

    def test_severity_palette_complete(self) -> None:
        from seeker_accounting.shared.ui.styles.palette import (
            DARK_PALETTE,
            LIGHT_PALETTE,
        )

        for pal in (LIGHT_PALETTE, DARK_PALETTE):
            for sev in ("blocker", "error", "warning", "info", "notice"):
                for suffix in ("bg", "fg", "accent"):
                    self.assertTrue(
                        getattr(pal, f"severity_{sev}_{suffix}").startswith("#"),
                        f"{pal.name}.severity_{sev}_{suffix} not set",
                    )

    # ── P1.S4 — registry + severity pill ──────────────────────────────

    def test_code_label_registry_basic(self) -> None:
        from seeker_accounting.shared.ui.components.code_label_registry import (
            CodeLabelRegistry,
        )

        reg = CodeLabelRegistry()
        reg.register("payroll_run_status", "draft", "Draft", tooltip="Unsaved")
        reg.register("payroll_run_status", "POSTED", "Posted", family="success")

        self.assertEqual(reg.label("payroll_run_status", "draft"), "Draft")
        self.assertEqual(reg.label("payroll_run_status", "Draft"), "Draft")  # case-insensitive
        self.assertEqual(reg.tooltip("payroll_run_status", "draft"), "Unsaved")
        self.assertEqual(reg.family("payroll_run_status", "posted"), "success")

        # Missing → fallback label, warning logged once.
        self.assertEqual(reg.label("payroll_run_status", "unknown_code"), "Unknown Code")
        self.assertFalse(reg.has("payroll_run_status", "unknown_code"))

    def test_severity_pill_renders(self) -> None:
        from seeker_accounting.shared.ui.components.severity_pill import (
            SeverityPill,
            highest_severity,
            severity_rank,
        )

        for sev in ("blocker", "error", "warning", "info", "notice"):
            pill = SeverityPill(sev)
            self.assertEqual(pill.severity(), sev)
            self.assertEqual(pill.property("severity"), sev)

        self.assertLess(severity_rank("blocker"), severity_rank("info"))
        self.assertEqual(
            highest_severity(["info", "warning", "error", "notice"]), "error"
        )

    # ── P1.S2 — Decimal-backed inputs ─────────────────────────────────

    def test_money_input_accepts_decimal(self) -> None:
        from seeker_accounting.shared.ui.widgets import MoneyInput

        w = MoneyInput(currency_code="XAF", fraction_digits=0, allow_negative=False)
        self.assertEqual(w.currency(), "XAF")
        w.set_value(Decimal("125000"))
        self.assertEqual(w.value(), Decimal("125000"))
        self.assertTrue(w.is_valid())

        # Reject negatives when allow_negative=False.
        w.set_value(Decimal("-1"))
        self.assertFalse(w.is_valid())

    def test_rate_input_ratio_roundtrip(self) -> None:
        from seeker_accounting.shared.ui.widgets import RateInput

        w = RateInput()
        w.set_value(Decimal("12.5"))
        self.assertEqual(w.value(), Decimal("12.5"))
        self.assertEqual(w.ratio_value(), Decimal("0.125"))

        w.set_ratio_value(Decimal("0.075"))
        self.assertEqual(w.ratio_value(), Decimal("0.075"))

    def test_quantity_input_rejects_zero_when_required(self) -> None:
        from seeker_accounting.shared.ui.widgets import QuantityInput

        w = QuantityInput(allow_zero=False)
        w.set_value(0)
        self.assertFalse(w.is_valid())
        self.assertIn("zero", w.error_reason().lower())

    def test_currency_picker_only_accepts_known_codes(self) -> None:
        from seeker_accounting.shared.ui.widgets import CurrencyOption, CurrencyPicker

        picker = CurrencyPicker()
        picker.set_currencies(
            [
                CurrencyOption("XAF", "Central African CFA franc", 0),
                CurrencyOption("EUR", "Euro", 2),
            ]
        )
        self.assertEqual(picker.currency(), "XAF")
        picker.set_currency("EUR")
        self.assertEqual(picker.currency(), "EUR")
        self.assertEqual(picker.fraction_digits(), 2)
        # Unknown code is ignored, current selection retained.
        picker.set_currency("ZZZ")
        self.assertEqual(picker.currency(), "EUR")

    # ── P1.S5 — validators + pipeline ─────────────────────────────────

    def test_validators(self) -> None:
        from seeker_accounting.shared.ui.validation import (
            DecimalRange,
            MaxLength,
            Required,
        )

        self.assertFalse(Required().validate("").is_valid)
        self.assertTrue(Required().validate("hi").is_valid)
        self.assertTrue(MaxLength(3).validate("abc").is_valid)
        self.assertFalse(MaxLength(3).validate("abcd").is_valid)
        self.assertFalse(
            DecimalRange(minimum=Decimal("0"), allow_negative=False)
            .validate(Decimal("-1"))
            .is_valid
        )

    def test_live_validation_pipeline(self) -> None:
        from seeker_accounting.shared.ui.validation import (
            FormValidationCoordinator,
            LineEditAdapter,
            LiveValidationPipeline,
            MinLength,
            Required,
        )

        line = QLineEdit()
        pipeline = LiveValidationPipeline(
            adapter=LineEditAdapter(line),
            validators=[Required(), MinLength(3)],
            debounce_ms=0,
            validate_on_init=True,
        )
        self.assertFalse(pipeline.is_valid())  # empty
        line.setText("ab")
        pipeline.run_now()
        self.assertFalse(pipeline.is_valid())  # too short
        line.setText("hello")
        pipeline.run_now()
        self.assertTrue(pipeline.is_valid())

        coord = FormValidationCoordinator()
        coord.add(pipeline)
        self.assertTrue(coord.is_valid())
        line.setText("")
        pipeline.run_now()
        self.assertFalse(coord.is_valid())

    # ── P1.S3 — issue band + form / confirm / side panel ──────────────

    def test_inline_issue_band(self) -> None:
        from seeker_accounting.shared.ui.components.inline_issue_band import (
            InlineIssueBand,
            ValidationIssue,
        )

        band = InlineIssueBand()
        self.assertFalse(band.isVisible())
        band.show_message("Boom", severity="error", title="Trouble")
        self.assertTrue(band.isVisible())
        self.assertEqual(band.property("severity"), "error")

        band.show_issues(
            [
                ValidationIssue(severity="warning", message="nudge"),
                ValidationIssue(severity="blocker", message="stop"),
            ]
        )
        self.assertEqual(band.property("severity"), "blocker")

        band.clear()
        self.assertFalse(band.isVisible())

    def test_form_dialog_dirty_and_state(self) -> None:
        from seeker_accounting.shared.ui.components.form_dialog import FormDialog

        dlg = FormDialog("Title", primary_label="Save", secondary_label="Cancel")
        section = dlg.add_section("Identity")
        line = QLineEdit()
        section.addRow("Name", line)

        self.assertEqual(dlg.state(), "clean")
        dlg.mark_dirty()
        self.assertEqual(dlg.state(), "dirty")
        dlg.show_error("Bad input")
        self.assertEqual(dlg.state(), "error")
        dlg.clear_issues()
        # error -> dirty
        self.assertEqual(dlg.state(), "dirty")
        dlg.mark_clean()
        self.assertEqual(dlg.state(), "clean")
        dlg.deleteLater()

    def test_confirm_dialog_typed_gating(self) -> None:
        from seeker_accounting.shared.ui.components.confirm_dialog import ConfirmDialog

        dlg = ConfirmDialog(
            title="Reverse run",
            message="This will counter-post the run.",
            primary_label="Reverse",
            severity="error",
            tier="typed",
            typed_phrase="REVERSE",
            consequences=["Counter-journal posted", "Audit trail recorded"],
        )
        primary = dlg.findChild(type(dlg), "ConfirmDialogPrimaryButton")
        # Not pre-enabled: typed input still empty.
        from PySide6.QtWidgets import QPushButton

        primary_btn = dlg.findChild(QPushButton, "ConfirmDialogPrimaryButton")
        self.assertIsNotNone(primary_btn)
        self.assertFalse(primary_btn.isEnabled())
        typed_input = dlg.findChild(QLineEdit, "ConfirmDialogTypedInput")
        self.assertIsNotNone(typed_input)
        typed_input.setText("REVERSE")
        self.assertTrue(primary_btn.isEnabled())
        dlg.deleteLater()

    def test_side_panel_set_content(self) -> None:
        from PySide6.QtWidgets import QLabel

        from seeker_accounting.shared.ui.components.side_panel import SidePanel

        panel = SidePanel(title="Resolve")
        body = QLabel("Hello")
        panel.set_content(body)
        panel.set_title("Updated")
        # closed signal fires.
        seen: list[bool] = []
        panel.closed.connect(lambda: seen.append(True))
        panel._on_close()
        self.assertEqual(seen, [True])
        panel.deleteLater()

    # ── P1.S7 — empty state / KPI tile / workbench header ─────────────

    def test_empty_state_and_kpi_tile(self) -> None:
        from seeker_accounting.shared.ui.components.workbench_primitives import (
            EmptyState,
            KpiTile,
            KpiTileData,
            WorkbenchHeader,
        )

        empty = EmptyState(
            headline="No payroll runs yet",
            body="Create the first run for this period.",
            primary_label="Create run",
            secondary_label="Import",
            glyph="∅",
        )
        seen_primary: list[bool] = []
        empty.primary_clicked.connect(lambda: seen_primary.append(True))
        # Find the primary button and click it.
        from PySide6.QtWidgets import QPushButton

        for child in empty.findChildren(QPushButton):
            if child.objectName() == "EmptyStatePrimaryButton":
                child.click()
        self.assertEqual(seen_primary, [True])

        tile = KpiTile(
            KpiTileData(
                label="Open run",
                value="XAF 1,250,000",
                trend="up",
                trend_label="+8% vs last month",
                drilldown_id="payroll.run.detail",
            )
        )
        self.assertEqual(tile.property("clickable"), "true")
        seen_drill: list[str] = []
        tile.clicked.connect(lambda nav: seen_drill.append(nav))
        # Simulate.
        tile.clicked.emit("payroll.run.detail")
        self.assertEqual(seen_drill, ["payroll.run.detail"])

        header = WorkbenchHeader()
        header.set_title("Payroll")
        header.set_subtitle("April 2026")
        header.set_breadcrumb("Workbench / Run")
        # No assertions beyond construction; the header is QSS-driven.

    # ── components/__init__ exports ──────────────────────────────────

    def test_components_package_exports(self) -> None:
        import seeker_accounting.shared.ui.components as comp

        for name in (
            "CODE_LABELS",
            "SeverityPill",
            "InlineIssueBand",
            "FormDialog",
            "ConfirmDialog",
            "SidePanel",
            "EmptyState",
            "KpiTile",
            "WorkbenchHeader",
        ):
            self.assertTrue(hasattr(comp, name), f"components missing export: {name}")


if __name__ == "__main__":
    unittest.main()
