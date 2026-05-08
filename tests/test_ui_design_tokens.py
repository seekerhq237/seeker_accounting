from __future__ import annotations

import re
from pathlib import Path
import unittest

from seeker_accounting.shared.ui.styles.palette import LIGHT_PALETTE
from seeker_accounting.shared.ui.styles.qss_builder import build_stylesheet
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


class UIDesignTokenTests(unittest.TestCase):
    def test_light_palette_uses_distinct_operational_layers(self) -> None:
        self.assertEqual(LIGHT_PALETTE.workspace_surface, "#FFFFFF")
        self.assertEqual(LIGHT_PALETTE.sidebar_surface, "#E8ECF2")
        self.assertNotEqual(LIGHT_PALETTE.sidebar_surface, LIGHT_PALETTE.topbar_surface)
        self.assertNotEqual(LIGHT_PALETTE.table_header, LIGHT_PALETTE.workspace_surface)
        self.assertNotEqual(LIGHT_PALETTE.border_default, "#D6D9DE")

    def test_typography_and_chip_tokens_match_desktop_contract(self) -> None:
        typography = DEFAULT_TOKENS.typography
        sizes = DEFAULT_TOKENS.sizes

        self.assertEqual(typography.size_body, 12)
        self.assertEqual(typography.size_dense, 11)
        self.assertEqual(typography.size_section_title, 14)
        self.assertEqual(typography.size_app_title, 20)
        self.assertEqual(sizes.chip_radius, 2)

    def test_stylesheet_contains_wayfinding_and_wizard_token_rules(self) -> None:
        stylesheet = build_stylesheet(LIGHT_PALETTE, DEFAULT_TOKENS)

        self.assertIn('QPushButton[moduleParent="true"][moduleActive="true"]', stylesheet)
        self.assertIn(f"border-left-color: {LIGHT_PALETTE.accent};", stylesheet)
        self.assertIn("QDialog#WizardHostDialog", stylesheet)
        self.assertIn("QFrame#WizardAdvisorCard[advisorSeverity=\"warning\"]", stylesheet)
        self.assertIn("QWidget#DashboardContainer QFrame#PanelHeader", stylesheet)
        self.assertIn("QFrame#DashboardSetupChecklistRow[complete=\"false\"]", stylesheet)
        self.assertIn("QPushButton#DashboardQuickAction", stylesheet)
        self.assertIn(f"background: {LIGHT_PALETTE.status_warning_bg};", stylesheet)

    def test_stylesheet_contains_shared_runtime_color_primitives(self) -> None:
        stylesheet = build_stylesheet(LIGHT_PALETTE, DEFAULT_TOKENS)

        for selector in (
            "QFrame#MetricTile",
            "QLabel#MetricCaption",
            "QLabel#MetricValue",
            "QFrame#WarningPanel",
            "QFrame#NotesPanel",
            "QLabel#WizardSuccessText",
            "QLabel#WizardMutedText",
            "QLabel#WizardWarningText",
        ):
            self.assertIn(selector, stylesheet)

    def test_runtime_ui_files_do_not_reintroduce_raw_hex_colors(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        raw_hex = re.compile(r"#[0-9A-Fa-f]{3,8}(?![0-9A-Za-z_])")
        files: list[Path] = []
        files.extend((repo_root / "src" / "seeker_accounting" / "app" / "entry").glob("*.py"))
        modules_root = repo_root / "src" / "seeker_accounting" / "modules"
        files.extend(path for path in modules_root.rglob("*.py") if "ui" in path.parts or "wizards" in path.parts)

        offenders: list[str] = []
        for path in sorted(files):
            text = path.read_text(encoding="utf-8")
            if raw_hex.search(text):
                offenders.append(str(path.relative_to(repo_root)))

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()