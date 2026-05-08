from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QTableView

from seeker_accounting.shared.ui.components.status_chip import (
    DEFAULT_FAMILY,
    StatusChip,
    resolve_status_family,
)
from seeker_accounting.shared.ui.components.status_chip_delegate import (
    StatusChipDelegate,
    apply_status_chip_to_column,
)


class StatusChipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_resolve_family_known_values(self) -> None:
        self.assertEqual(resolve_status_family("draft"), "accent")
        self.assertEqual(resolve_status_family("Posted"), "success")
        self.assertEqual(resolve_status_family("CANCELLED"), "danger")
        self.assertEqual(resolve_status_family("on hold"), "warning")
        self.assertEqual(resolve_status_family("in-progress"), "accent")
        self.assertEqual(resolve_status_family("submitted-for-review"), "accent")
        self.assertEqual(resolve_status_family("calculated"), "info")
        self.assertEqual(resolve_status_family("matched"), "success")
        self.assertEqual(resolve_status_family("unmatched"), "warning")

    def test_resolve_family_unknown_and_empty(self) -> None:
        self.assertEqual(resolve_status_family(None), DEFAULT_FAMILY)
        self.assertEqual(resolve_status_family(""), DEFAULT_FAMILY)
        self.assertEqual(resolve_status_family("not_a_real_status"), DEFAULT_FAMILY)

    def test_status_chip_resolves_family_from_status(self) -> None:
        self.assertEqual(StatusChip("draft").family, "accent")
        self.assertEqual(StatusChip("posted").family, "success")
        self.assertEqual(StatusChip("cancelled").family, "danger")
        self.assertEqual(StatusChip(None).family, DEFAULT_FAMILY)

    def test_status_chip_explicit_family_override(self) -> None:
        chip = StatusChip("anything-custom", family="warning")
        self.assertEqual(chip.family, "warning")
        self.assertEqual(chip.property("chipFamily"), "warning")

    def test_status_chip_set_status_updates_state(self) -> None:
        chip = StatusChip("draft")
        self.assertEqual(chip.status, "draft")
        self.assertEqual(chip.property("chipFamily"), "accent")
        chip.set_status("posted")
        self.assertEqual(chip.status, "posted")
        self.assertEqual(chip.family, "success")
        self.assertEqual(chip.property("chipFamily"), "success")
        chip.set_status(None)
        self.assertEqual(chip.family, DEFAULT_FAMILY)

    def test_status_chip_renders_without_error(self) -> None:
        chip = StatusChip("posted")
        chip.resize(120, 20)
        chip.show()
        chip.repaint()
        chip.hide()

    def test_delegate_paints_in_table_view(self) -> None:
        model = QStandardItemModel(3, 1)
        for row, status in enumerate(["draft", "posted", "cancelled"]):
            model.setItem(row, 0, QStandardItem(status))

        view = QTableView()
        view.setModel(model)
        delegate = apply_status_chip_to_column(view, 0)
        self.assertIsInstance(delegate, StatusChipDelegate)

        view.resize(300, 120)
        view.show()
        view.viewport().repaint()
        view.hide()

    def test_delegate_family_role_override(self) -> None:
        family_role = int(Qt.ItemDataRole.UserRole) + 1
        model = QStandardItemModel(1, 1)
        item = QStandardItem("anything")
        item.setData("warning", family_role)
        model.setItem(0, 0, item)

        view = QTableView()
        view.setModel(model)
        delegate = apply_status_chip_to_column(view, 0, family_role=family_role)
        view.resize(200, 60)
        view.show()
        view.viewport().repaint()
        view.hide()

        # Sanity: delegate resolution honors the family role override.
        idx = model.index(0, 0)
        _, family, _ = delegate._resolve(idx)
        self.assertEqual(family, "warning")


if __name__ == "__main__":
    unittest.main()
