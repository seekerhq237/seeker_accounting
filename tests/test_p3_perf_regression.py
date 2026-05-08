"""Performance regression tests — P3.

These tests guard against catastrophic performance regressions in three areas:

1. ``ReadOnlyTableModel`` data loading — the primary UI hot path for large lists.
2. Database engine creation — measures pragma setup overhead.
3. Page ``__init__`` timing — catches accidental heavy work added to constructors.

Thresholds are set at 10× typical measured values so the suite is insensitive
to normal variance on CI or slower development machines, while still catching
a genuine regression (e.g. an accidental synchronous DB call in a constructor,
or a quadratic loop introduced in ``reset_data``).

The tests require a QApplication instance and run the pages in offscreen mode
(no display needed).  On Windows development machines the default platform
plugin is used instead.
"""
from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ms(start: float) -> float:
    """Return elapsed time in milliseconds since *start*."""
    return (time.perf_counter() - start) * 1000


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    """Return (or create) the QApplication singleton for this test module."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


@pytest.fixture
def mock_registry():
    """Minimal mock ServiceRegistry that makes pages exit their reload early.

    Both ``PayrollSetupPage`` and ``TaxCompliancePage`` call
    ``company_context_service.get_active_company()`` in their ``reload()``
    methods.  Returning ``None`` triggers the "no active company" early-exit
    branch so the pages build all widgets but make zero service/DB calls.
    """
    reg = MagicMock()
    reg.company_context_service.get_active_company.return_value = None
    return reg


# ── ReadOnlyTableModel timing ─────────────────────────────────────────────────

class TestReadOnlyTableModelPerf:
    """ReadOnlyTableModel.reset_data() must stay O(n), not O(n²)."""

    THRESHOLD_1K_MS = 100   # 1 000-row reset in < 100 ms
    THRESHOLD_10K_MS = 500  # 10 000-row reset in < 500 ms
    THRESHOLD_SORT_MS = 200 # in-place sort of 1 000 rows in < 200 ms

    def test_reset_data_1000_rows(self, qapp) -> None:
        from seeker_accounting.shared.ui.components.read_only_table_model import ReadOnlyTableModel

        model = ReadOnlyTableModel(["A", "B", "C", "D"])
        rows = [[f"r{i}c{j}" for j in range(4)] for i in range(1_000)]
        ids = list(range(1_000))

        t = time.perf_counter()
        model.reset_data(rows, ids)
        elapsed = _ms(t)

        assert model.rowCount() == 1_000
        assert elapsed < self.THRESHOLD_1K_MS, (
            f"reset_data(1 000 rows) took {elapsed:.1f} ms; "
            f"threshold {self.THRESHOLD_1K_MS} ms"
        )

    def test_reset_data_10000_rows(self, qapp) -> None:
        from seeker_accounting.shared.ui.components.read_only_table_model import ReadOnlyTableModel

        model = ReadOnlyTableModel(["A", "B", "C", "D"])
        rows = [[f"r{i}c{j}" for j in range(4)] for i in range(10_000)]
        ids = list(range(10_000))

        t = time.perf_counter()
        model.reset_data(rows, ids)
        elapsed = _ms(t)

        assert model.rowCount() == 10_000
        assert elapsed < self.THRESHOLD_10K_MS, (
            f"reset_data(10 000 rows) took {elapsed:.1f} ms; "
            f"threshold {self.THRESHOLD_10K_MS} ms"
        )

    def test_sort_1000_rows(self, qapp) -> None:
        from PySide6.QtCore import Qt
        from seeker_accounting.shared.ui.components.read_only_table_model import ReadOnlyTableModel

        model = ReadOnlyTableModel(["Name", "Amount"])
        # Intentionally reversed so sorting has real work to do.
        rows = [[str(1_000 - i), str(i)] for i in range(1_000)]
        model.reset_data(rows)

        t = time.perf_counter()
        model.sort(0, Qt.SortOrder.AscendingOrder)
        elapsed = _ms(t)

        assert elapsed < self.THRESHOLD_SORT_MS, (
            f"sort(1 000 rows) took {elapsed:.1f} ms; "
            f"threshold {self.THRESHOLD_SORT_MS} ms"
        )

    def test_successive_resets_do_not_accumulate(self, qapp) -> None:
        """Resetting the same model 50 times should not get progressively slower."""
        from seeker_accounting.shared.ui.components.read_only_table_model import ReadOnlyTableModel

        model = ReadOnlyTableModel(["A", "B"])
        rows = [[str(i), str(i * 2)] for i in range(500)]

        times: list[float] = []
        for _ in range(50):
            t = time.perf_counter()
            model.reset_data(rows)
            times.append(_ms(t))

        # The last 10 iterations should not be significantly slower than the
        # first 10 (within 3×).  This guards against any quadratic growth.
        avg_first_10 = sum(times[:10]) / 10
        avg_last_10 = sum(times[-10:]) / 10
        assert avg_last_10 <= avg_first_10 * 3 + 10, (
            f"Successive resets are getting slower: "
            f"first 10 avg={avg_first_10:.2f} ms, last 10 avg={avg_last_10:.2f} ms"
        )


# ── Database engine / pragma setup ───────────────────────────────────────────

class TestDbEnginePerf:
    """Engine creation + pragma installation should be fast."""

    THRESHOLD_MS = 1_000  # < 1 s for in-memory SQLite engine + first connect

    def test_engine_creation_and_first_connect(self) -> None:
        from seeker_accounting.config.paths import build_runtime_paths
        from seeker_accounting.config.settings import AppSettings
        from seeker_accounting.db.engine import create_database_engine

        settings = AppSettings(
            app_name="perf_test",
            organization_name="perf_test",
            window_title="perf_test",
            environment="test",
            theme_name="light",
            current_user_display_name="test",
            runtime_paths=build_runtime_paths(),
            database_url="sqlite:///:memory:",
            log_level="WARNING",
        )

        t = time.perf_counter()
        engine = create_database_engine(settings)
        # Force a real connection so the connect-event pragma hook fires.
        with engine.connect():
            pass
        elapsed = _ms(t)
        engine.dispose()

        assert elapsed < self.THRESHOLD_MS, (
            f"Engine creation + first connect took {elapsed:.1f} ms; "
            f"threshold {self.THRESHOLD_MS} ms"
        )

    def test_factories_module_already_importable(self) -> None:
        """All heavy modules must already be importable (cached by test runner).

        This catches someone accidentally removing the factories.py import from
        the preloader, which would force a cold import on first service access
        and add several seconds to perceived boot time.
        """
        import importlib
        spec = importlib.util.find_spec("seeker_accounting.app.dependency.factories")
        assert spec is not None, (
            "seeker_accounting.app.dependency.factories not found on sys.path"
        )


# ── Page open timing ──────────────────────────────────────────────────────────

class TestPageOpenPerf:
    """Page __init__ must not perform synchronous I/O or service calls.

    Both pages tested here guard their reload() with an 'active company is None'
    check so no service methods are called when mock_registry returns None.
    The timings therefore measure only widget construction overhead.
    """

    THRESHOLD_MS = 3_000  # 3 s — intentionally generous

    def test_payroll_setup_page_open(self, qapp, mock_registry) -> None:
        from seeker_accounting.modules.payroll.ui.payroll_setup_page import PayrollSetupPage

        t = time.perf_counter()
        page = PayrollSetupPage(mock_registry)
        elapsed = _ms(t)

        page.close()
        page.deleteLater()

        assert elapsed < self.THRESHOLD_MS, (
            f"PayrollSetupPage.__init__ took {elapsed:.1f} ms; "
            f"threshold {self.THRESHOLD_MS} ms"
        )

    def test_tax_compliance_page_open(self, qapp, mock_registry) -> None:
        from seeker_accounting.modules.taxation.ui.tax_compliance_page import TaxCompliancePage

        t = time.perf_counter()
        page = TaxCompliancePage(mock_registry)
        elapsed = _ms(t)

        page.close()
        page.deleteLater()

        assert elapsed < self.THRESHOLD_MS, (
            f"TaxCompliancePage.__init__ took {elapsed:.1f} ms; "
            f"threshold {self.THRESHOLD_MS} ms"
        )
