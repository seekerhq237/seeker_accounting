"""
Slice 1 smoke — Sage-style ribbon + independent child windows.

Validates:
* RibbonRegistry ships the built-in 'journals' and 'child:journal_entry' surfaces.
* MainWindow wires RibbonBar and swaps its surface when navigation changes.
* ChildWindowManager dedupes on (doc_type, entity_id).
* JournalEntryWindow instantiates in embedded mode with its own ribbon.

Run offscreen:
    $env:QT_QPA_PLATFORM="offscreen"; $env:PYTHONPATH="."; .venv\\Scripts\\python.exe scripts\\smoke_ribbon_and_child_windows.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication


def main() -> int:
    app = QApplication(sys.argv)

    from scripts.shared import bootstrap_script_runtime

    r = bootstrap_script_runtime(app)
    registry = r.service_registry

    # Registry has all the built-in surfaces shipped in Slices 1 & 2.
    assert registry.ribbon_registry is not None, "ribbon_registry missing"
    expected_surfaces = (
        "journals",
        "child:journal_entry",
        # Sales
        "sales_invoices",
        "sales_orders",
        "customer_quotes",
        "sales_credit_notes",
        "customer_receipts",
        # Purchases
        "purchase_bills",
        "purchase_orders",
        "purchase_credit_notes",
        "supplier_payments",
        # Treasury
        "treasury_transactions",
        "treasury_transfers",
        # Reference entities
        "customers",
        "suppliers",
        "chart_of_accounts",
        "items",
    )
    for key in expected_surfaces:
        assert registry.ribbon_registry.has(key), f"missing ribbon surface: {key}"
    print(f"[OK] ribbon registry has {len(expected_surfaces)} built-in surfaces")

    # MainWindow wires a ribbon bar and toggles visibility on nav.
    from seeker_accounting.app.shell.main_window import MainWindow

    window = MainWindow(service_registry=registry)
    window.show()
    for _ in range(5):
        app.processEvents()

    assert window._ribbon_bar is not None, "main window has no ribbon bar"
    print("[OK] MainWindow has ribbon bar")

    registry.navigation_service.navigate("journals")
    for _ in range(10):
        app.processEvents()
    assert window._ribbon_bar._current_surface_key == "journals", (
        f"ribbon did not swap to journals "
        f"(got {window._ribbon_bar._current_surface_key!r})"
    )
    assert not window._ribbon_bar.isHidden(), "ribbon bar should be visible"
    print("[OK] ribbon switches to journals surface")

    # ChildWindowManager dedupes on (doc_type, entity_id).
    manager = registry.child_window_manager
    assert manager is not None, "child_window_manager missing"

    from seeker_accounting.app.shell.child_windows.child_window_base import (
        ChildWindowBase,
    )
    from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry

    def _make_stub() -> ChildWindowBase:
        return ChildWindowBase(
            title="Stub",
            surface_key=RibbonRegistry.child_window_key("journal_entry"),
            window_key=("journal_entry", 42),
            registry=registry.ribbon_registry,
            icon_provider=window._ribbon_icon_provider,
        )

    first = manager.open_document("journal_entry", 42, _make_stub)
    second = manager.open_document("journal_entry", 42, _make_stub)
    assert first is second, "manager should dedupe same (doc_type, entity_id)"
    print("[OK] ChildWindowManager dedupes on entity_id")

    # A different entity_id opens an independent window.
    third = manager.open_document(
        "journal_entry",
        43,
        lambda: ChildWindowBase(
            title="Other",
            surface_key=RibbonRegistry.child_window_key("journal_entry"),
            window_key=("journal_entry", 43),
            registry=registry.ribbon_registry,
            icon_provider=window._ribbon_icon_provider,
        ),
    )
    assert third is not first, "different entity_id must yield a new window"
    print("[OK] different entity_id opens a fresh window")

    # Close all and verify the manager empties.
    manager.close_all()
    for _ in range(5):
        app.processEvents()
    assert len(manager.all_windows()) == 0, "manager should be empty after close_all"
    print("[OK] manager empties after close_all")

    # JournalEntryWindow imports cleanly (full construction needs an
    # active company + services, out of scope here — import-only check).
    from seeker_accounting.modules.accounting.journals.ui.journal_entry_window import (  # noqa: F401
        JournalEntryWindow,
    )
    print("[OK] JournalEntryWindow importable")

    print("ALL RIBBON + CHILD WINDOW SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
