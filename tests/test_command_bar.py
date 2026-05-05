"""Offscreen smoke tests for :class:`CommandBar`."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from seeker_accounting.shared.ui.components.command_bar import (
    CommandBar,
    CommandItem,
    CommandSeparator,
)


def _items() -> list[object]:
    return [
        CommandItem(
            command_id="new",
            label="New",
            icon_name="plus",
            shortcut="Ctrl+N",
            variant="primary",
            priority="primary",
            group="create",
        ),
        CommandSeparator(),
        CommandItem(
            command_id="edit",
            label="Edit",
            icon_name="",
            priority="secondary",
            group="actions",
        ),
        CommandItem(
            command_id="duplicate",
            label="Duplicate",
            priority="secondary",
            group="actions",
        ),
        CommandItem(
            command_id="archive",
            label="Archive Selected",
            priority="secondary",
            group="actions",
        ),
        CommandItem(
            command_id="show_inactive",
            label="Show inactive",
            priority="secondary",
            checkable=True,
            checked=False,
            group="view",
        ),
        CommandItem(
            command_id="export_csv",
            label="Export to CSV",
            priority="overflow",
            group="data",
        ),
        CommandItem(
            command_id="export_pdf",
            label="Export to PDF",
            priority="overflow",
            group="data",
        ),
    ]


class CommandBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _build(self) -> CommandBar:
        bar = CommandBar(_items())
        bar.resize(1200, 36)
        bar.show()
        QApplication.processEvents()
        return bar

    def test_wide_layout_keeps_secondary_items_visible(self) -> None:
        bar = self._build()
        try:
            primary_btn = self._button(bar, "new")
            self.assertTrue(primary_btn.isVisible())
            self.assertEqual(primary_btn.property("primary"), "true")
            self.assertEqual(primary_btn.text(), "New")

            for cid in ("edit", "duplicate", "archive", "show_inactive"):
                self.assertTrue(
                    self._button(bar, cid).isVisible(),
                    f"{cid} should be visible at 1200px",
                )

            # Overflow button must still be visible because there are
            # `priority='overflow'` items.
            self.assertTrue(bar._overflow_button.isVisible())
            actions = bar._overflow_menu.actions()
            action_texts = [a.text() for a in actions if not a.isSeparator()]
            self.assertIn("Export to CSV", action_texts)
            self.assertIn("Export to PDF", action_texts)
        finally:
            bar.deleteLater()

    def test_narrow_layout_pushes_secondary_to_overflow(self) -> None:
        bar = self._build()
        try:
            bar.setFixedWidth(200)
            QApplication.processEvents()

            primary_btn = self._button(bar, "new")
            self.assertTrue(primary_btn.isVisible(), "primary stays visible when narrow")

            # At least one secondary item should be hidden / in overflow.
            secondary_visible = sum(
                1
                for cid in ("edit", "duplicate", "archive", "show_inactive")
                if self._button(bar, cid).isVisible()
            )
            self.assertLess(
                secondary_visible,
                4,
                "narrow width should demote at least one secondary item",
            )

            # Overflow button must be present and openable.
            self.assertTrue(bar._overflow_button.isVisible())
            menu = bar._overflow_menu
            self.assertGreater(len([a for a in menu.actions() if not a.isSeparator()]), 0)
        finally:
            bar.deleteLater()

    def test_set_enablement_disables_button(self) -> None:
        bar = self._build()
        try:
            bar.set_enablement({"edit": False})
            self.assertFalse(self._button(bar, "edit").isEnabled())
            bar.set_enablement({"edit": True})
            self.assertTrue(self._button(bar, "edit").isEnabled())
        finally:
            bar.deleteLater()

    def test_set_checked_emits_no_signal_but_updates_state(self) -> None:
        bar = self._build()
        toggled: list[tuple[str, bool]] = []
        bar.command_toggled.connect(lambda cid, ch: toggled.append((cid, ch)))
        try:
            bar.set_checked("show_inactive", True)
            self.assertTrue(self._button(bar, "show_inactive").isChecked())
            # set_checked must NOT re-emit command_toggled (programmatic update).
            self.assertEqual(toggled, [])
        finally:
            bar.deleteLater()

    def test_user_toggle_emits_command_toggled(self) -> None:
        bar = self._build()
        toggled: list[tuple[str, bool]] = []
        bar.command_toggled.connect(lambda cid, ch: toggled.append((cid, ch)))
        try:
            self._button(bar, "show_inactive").click()
            QApplication.processEvents()
            self.assertEqual(toggled, [("show_inactive", True)])
        finally:
            bar.deleteLater()

    def test_click_emits_command_activated(self) -> None:
        bar = self._build()
        activated: list[str] = []
        bar.command_activated.connect(activated.append)
        try:
            self._button(bar, "new").click()
            QApplication.processEvents()
            self.assertEqual(activated, ["new"])
        finally:
            bar.deleteLater()

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _button(bar: CommandBar, command_id: str):
        entry = bar._find(command_id)
        assert entry is not None, f"missing entry for {command_id}"
        assert entry.button is not None, f"entry for {command_id} has no button"
        return entry.button


if __name__ == "__main__":
    unittest.main()
