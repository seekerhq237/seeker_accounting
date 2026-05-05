"""Tax Dashboard workspace.

Read-only consolidated snapshot for the taxation module (Slice T22).

Architecture: UI surface only — every read goes through
``TaxDashboardService`` via the service registry. The page never opens
its own session or constructs any persistence.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    TaxDashboardSnapshotDTO,
)
from seeker_accounting.platform.exceptions import (
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.message_boxes import show_error


_DASH = "\u2014"


def _money(value: Decimal | float | int | None) -> str:
    if value is None:
        return _DASH
    return f"{Decimal(value):,.2f}"


def _right(item: QStandardItem) -> QStandardItem:
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class TaxDashboardPage(RibbonHostMixin, QWidget):
    """Compact dashboard surface — KPI tiles + per-tax-type + upcoming."""

    KPI_LABELS: tuple[tuple[str, str], ...] = (
        ("Total obligations", "total_obligations"),
        ("Open", "open_obligations"),
        ("Overdue", "overdue_obligations"),
        ("Paid", "paid_obligations"),
        ("Returns drafted", "returns_draft"),
        ("Returns filed", "returns_filed"),
        ("Returns settled", "returns_settled"),
        ("VAT filed (unsettled)", "returns_filed_unsettled_vat"),
    )

    MONEY_LABELS: tuple[tuple[str, str], ...] = (
        ("Payments YTD", "total_payments_ytd"),
        ("Total due (filed) YTD", "total_due_filed_returns_ytd"),
        ("WHT inbound YTD", "wht_inbound_total_ytd"),
        ("WHT outbound YTD", "wht_outbound_total_ytd"),
    )

    BY_TYPE_COLUMNS: tuple[str, ...] = (
        "Tax type",
        "Open",
        "Overdue",
        "Paid",
    )

    UPCOMING_COLUMNS: tuple[str, ...] = (
        "Due date",
        "Tax type",
        "Period start",
        "Period end",
        "Status",
        "Days until due",
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._snapshot: TaxDashboardSnapshotDTO | None = None
        self._kpi_value_labels: dict[str, QLabel] = {}
        self._money_value_labels: dict[str, QLabel] = {}

        self.setObjectName("TaxDashboardPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_action_bar())

        self._stack = QStackedWidget(self)
        self._no_company_card = self._build_no_company_card()
        self._workspace = self._build_workspace()
        self._stack.addWidget(self._no_company_card)
        self._stack.addWidget(self._workspace)
        root.addWidget(self._stack, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    # ── Action bar ────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Tax Dashboard", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._meta_label = QLabel(card)
        self._meta_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._meta_label)

        layout.addStretch(1)

        layout.addWidget(QLabel("Year:", card))
        self._year_spin = QSpinBox(card)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(date.today().year)
        self._year_spin.setFixedWidth(90)
        layout.addWidget(self._year_spin)

        self._apply_button = QPushButton("Apply", card)
        self._apply_button.setProperty("variant", "secondary")
        self._apply_button.clicked.connect(self.reload)
        layout.addWidget(self._apply_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self.reload)
        layout.addWidget(self._refresh_button)

        return card

    # ── No-company state ──────────────────────────────────────────────

    def _build_no_company_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No active company", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        body = QLabel(
            "Select a company from the top context bar to view the tax "
            "compliance dashboard.",
            card,
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)

        return card

    # ── Workspace ─────────────────────────────────────────────────────

    def _build_workspace(self) -> QWidget:
        wrapper = QFrame(self)
        wrapper.setObjectName("PageCard")

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        layout.addWidget(self._build_kpi_section("Counts", self.KPI_LABELS, self._kpi_value_labels))
        layout.addWidget(self._build_kpi_section("Money totals", self.MONEY_LABELS, self._money_value_labels))

        # Per-tax-type breakdown
        by_type_section = QFrame(self)
        by_type_section.setObjectName("DialogSection")
        v = QVBoxLayout(by_type_section)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        h = QLabel("By tax type", by_type_section)
        h.setStyleSheet("font-size: 14px; font-weight: 600; color: #111827;")
        v.addWidget(h)
        self._by_type_model, self._by_type_table = self._build_table(by_type_section, self.BY_TYPE_COLUMNS, min_height=140)
        v.addWidget(self._by_type_table)
        layout.addWidget(by_type_section)

        # Upcoming
        upcoming_section = QFrame(self)
        upcoming_section.setObjectName("DialogSection")
        v2 = QVBoxLayout(upcoming_section)
        v2.setContentsMargins(0, 0, 0, 0)
        v2.setSpacing(6)
        h2 = QLabel("Upcoming obligations (top 10)", upcoming_section)
        h2.setStyleSheet("font-size: 14px; font-weight: 600; color: #111827;")
        v2.addWidget(h2)
        self._upcoming_model, self._upcoming_table = self._build_table(upcoming_section, self.UPCOMING_COLUMNS, min_height=220)
        v2.addWidget(self._upcoming_table)
        layout.addWidget(upcoming_section)

        layout.addStretch(1)
        return wrapper

    def _build_kpi_section(
        self,
        title: str,
        labels: tuple[tuple[str, str], ...],
        store: dict[str, QLabel],
    ) -> QWidget:
        section = QFrame(self)
        section.setObjectName("DialogSection")
        v = QVBoxLayout(section)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        heading = QLabel(title, section)
        heading.setStyleSheet("font-size: 14px; font-weight: 600; color: #111827;")
        v.addWidget(heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for idx, (label_text, key) in enumerate(labels):
            tile = QFrame(section)
            tile.setObjectName("PageCard")
            tile.setProperty("card", True)
            tile.setStyleSheet(
                "QFrame { background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; }"
            )
            t = QVBoxLayout(tile)
            t.setContentsMargins(10, 8, 10, 8)
            t.setSpacing(2)
            cap = QLabel(label_text, tile)
            cap.setStyleSheet("color: #6B7280; font-size: 11px;")
            t.addWidget(cap)
            value = QLabel(_DASH, tile)
            value.setStyleSheet("color: #111827; font-size: 18px; font-weight: 600;")
            t.addWidget(value)
            store[key] = value
            row = idx // 4
            col = idx % 4
            grid.addWidget(tile, row, col)
        v.addLayout(grid)
        return section

    def _build_table(self, parent: QWidget, columns: tuple[str, ...], *, min_height: int) -> tuple[QStandardItemModel, DataTable]:
        model = QStandardItemModel(0, len(columns), self)
        model.setHorizontalHeaderLabels(list(columns))
        dt_columns = tuple(DataTableColumn(key=str(i), title=col) for i, col in enumerate(columns))
        table = DataTable(columns=dt_columns, show_search=False, parent=parent)
        table.set_model(model)
        table.setMinimumHeight(min_height)
        return model, table

    # ── Reload ────────────────────────────────────────────────────────

    def reload(self) -> None:
        active = self._active_company()
        if active is None:
            self._snapshot = None
            self._meta_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_company_card)
            return

        year = int(self._year_spin.value())
        try:
            snapshot = self._service_registry.tax_dashboard_service.get_dashboard(
                active.company_id, year
            )
        except PermissionDeniedError as exc:
            self._snapshot = None
            self._meta_label.setText("Access denied")
            show_error(self, "Tax Dashboard", str(exc))
            self._stack.setCurrentWidget(self._workspace)
            self._render_snapshot()
            return
        except ValidationError as exc:
            self._snapshot = None
            self._meta_label.setText("")
            show_error(self, "Tax Dashboard", str(exc))
            self._stack.setCurrentWidget(self._workspace)
            self._render_snapshot()
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._snapshot = None
            show_error(self, "Tax Dashboard", f"Could not load dashboard.\n\n{exc}")
            self._stack.setCurrentWidget(self._workspace)
            self._render_snapshot()
            return

        self._snapshot = snapshot
        self._meta_label.setText(
            f"Year {snapshot.fiscal_year} \u00b7 as of {snapshot.as_of_date.isoformat()}"
        )
        self._stack.setCurrentWidget(self._workspace)
        self._render_snapshot()

    @staticmethod
    def _make_item(text: str | None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        return item

    def _render_snapshot(self) -> None:
        snap = self._snapshot
        # KPI tiles
        for _, key in self.KPI_LABELS:
            label = self._kpi_value_labels.get(key)
            if label is None:
                continue
            label.setText(str(getattr(snap, key)) if snap else _DASH)
        for _, key in self.MONEY_LABELS:
            label = self._money_value_labels.get(key)
            if label is None:
                continue
            label.setText(_money(getattr(snap, key)) if snap else _DASH)

        # Per-tax-type
        rows = list(snap.by_tax_type) if snap else []
        self._by_type_model.removeRows(0, self._by_type_model.rowCount())
        for item in rows:
            self._by_type_model.appendRow([
                self._make_item(item.tax_type_code),
                _right(self._make_item(str(item.open_count))),
                _right(self._make_item(str(item.overdue_count))),
                _right(self._make_item(str(item.paid_count))),
            ])

        # Upcoming
        upcoming = list(snap.upcoming) if snap else []
        self._upcoming_model.removeRows(0, self._upcoming_model.rowCount())
        for item in upcoming:
            days_item = self._make_item(str(item.days_until_due))
            if item.days_until_due < 0:
                days_item.setForeground(QBrush(QColor("red")))
            self._upcoming_model.appendRow([
                self._make_item(item.due_date.isoformat()),
                self._make_item(item.tax_type_code),
                self._make_item(item.period_start.isoformat()),
                self._make_item(item.period_end.isoformat()),
                self._make_item(item.status_code),
                _right(days_item),
            ])

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self) -> dict:
        return {
            "tax_dashboard.refresh": self.reload,
        }

    def ribbon_state(self) -> dict:
        return {
            "tax_dashboard.refresh": True,
        }

    # ── Helpers ───────────────────────────────────────────────────────

    def _active_company(self):
        return self._service_registry.company_context_service.get_active_company()
