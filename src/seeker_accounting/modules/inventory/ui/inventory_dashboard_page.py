"""Inventory Dashboard Page — KPI tiles + mover tables."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.message_boxes import show_error


class _KpiTile(QFrame):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MetricTile")
        self.setProperty("card", True)
        self.setMinimumWidth(160)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        self._lbl = QLabel(label, self)
        self._lbl.setObjectName("MetricCaption")

        self._val = QLabel("—", self)
        self._val.setObjectName("MetricValue")
        self._val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        lay.addWidget(self._lbl)
        lay.addWidget(self._val)

    def set_value(self, text: str) -> None:
        self._val.setText(text)


class InventoryDashboardPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self.setObjectName("InventoryDashboardPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        root.addWidget(self._build_toolbar())

        self._kpi_row = QHBoxLayout()
        self._kpi_row.setSpacing(8)
        kpi_wrap = QWidget(self)
        kpi_wrap.setLayout(self._kpi_row)
        root.addWidget(kpi_wrap)

        self._tile_value = _KpiTile("Total Value", self)
        self._tile_reorder = _KpiTile("Below Reorder", self)
        self._tile_expiring = _KpiTile("Expiring Soon", self)
        self._tile_ageing = _KpiTile("Ageing Stock", self)
        self._tile_grni = _KpiTile("GRNI Balance", self)
        self._tile_draft = _KpiTile("Draft Documents", self)

        for tile in (
            self._tile_value,
            self._tile_reorder,
            self._tile_expiring,
            self._tile_ageing,
            self._tile_grni,
            self._tile_draft,
        ):
            self._kpi_row.addWidget(tile)
        self._kpi_row.addStretch()

        movers_row = QHBoxLayout()
        movers_row.setSpacing(12)
        movers_row.addWidget(self._build_mover_table("top", "Top 5 Movers (last 30 days)"))
        movers_row.addWidget(self._build_mover_table("slow", "Slow Movers (last 90 days)"))
        root.addLayout(movers_row)

        root.addStretch()

        self._service_registry.active_company_context.active_company_changed.connect(
            self._reload
        )
        self._reload()

    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("PageToolbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(8)
        lbl = QLabel("Inventory Dashboard", bar)
        lbl.setObjectName("PageTitle")
        lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        lay.addWidget(lbl)
        lay.addStretch()
        btn = QPushButton("Refresh", bar)
        btn.setFixedHeight(28)
        btn.clicked.connect(self._reload)
        lay.addWidget(btn)
        return bar

    def _build_mover_table(self, attr: str, title: str) -> QWidget:
        card = QFrame(self)
        card.setProperty("card", True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        lbl = QLabel(title, card)
        lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        lay.addWidget(lbl)
        tbl = QTableWidget(0, 3, card)
        tbl.setHorizontalHeaderLabels(["Code", "Name", "Qty"])
        tbl.horizontalHeader().setStretchLastSection(False)
        tbl.horizontalHeader().setSectionResizeMode(1, tbl.horizontalHeader().ResizeMode.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setFixedHeight(160)
        lay.addWidget(tbl)
        setattr(self, f"_{attr}_table", tbl)
        return card

    def _reload(self) -> None:
        active = self._service_registry.active_company_context.get_active_company()
        if active is None:
            return
        svc = self._service_registry.inventory_dashboard_service
        try:
            dto = svc.get_dashboard(active.company_id)
        except Exception as exc:
            show_error(self, "Inventory Dashboard", str(exc))
            return

        kpi = dto.kpis
        self._tile_value.set_value(f"{kpi.total_inventory_value:,.2f}")
        self._tile_reorder.set_value(str(kpi.item_count_below_reorder))
        self._tile_expiring.set_value(str(kpi.item_count_expiring_batches))
        self._tile_ageing.set_value(str(kpi.item_count_ageing_stock))
        self._tile_grni.set_value(f"{kpi.grni_balance:,.2f}")
        self._tile_draft.set_value(str(kpi.draft_document_count))

        self._populate_mover_table(self._top_table, dto.top_movers)
        self._populate_mover_table(self._slow_table, dto.slow_movers)

    def _populate_mover_table(self, table: QTableWidget, rows: list) -> None:
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(row.item_code))
            table.setItem(r, 1, QTableWidgetItem(row.item_name))
            qty_item = QTableWidgetItem(f"{row.quantity_moved:,.4f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, 2, qty_item)
