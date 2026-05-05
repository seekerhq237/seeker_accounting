"""Reorder Planning Page — profiles table + suggestions panel."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.components.confirm_dialog import confirm
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


class ReorderPlanningPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self.setObjectName("ReorderPlanningPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        left_panel = self._build_profiles_panel()
        right_panel = self._build_suggestions_panel()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

        self._service_registry.active_company_context.active_company_changed.connect(self._reload)
        self._reload()

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("PageToolbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(8)
        lbl = QLabel("Reorder Planning", bar)
        lbl.setObjectName("PageTitle")
        lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        lay.addWidget(lbl)
        lay.addStretch()
        self._suggest_btn = QPushButton("Generate Suggestions", bar)
        self._suggest_btn.setFixedHeight(28)
        self._suggest_btn.clicked.connect(self._on_generate)
        lay.addWidget(self._suggest_btn)
        return bar

    def _build_profiles_panel(self) -> QWidget:
        frame = QFrame(self)
        frame.setProperty("card", True)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Reorder Profiles", frame))
        hdr.addStretch()
        new_btn = QPushButton("+ Add", frame)
        new_btn.setFixedHeight(24)
        new_btn.clicked.connect(self._on_new_profile)
        del_btn = QPushButton("Delete", frame)
        del_btn.setFixedHeight(24)
        del_btn.clicked.connect(self._on_delete_profile)
        hdr.addWidget(new_btn)
        hdr.addWidget(del_btn)
        lay.addLayout(hdr)

        self._profiles_table = QTableWidget(0, 4, frame)
        self._profiles_table.setHorizontalHeaderLabels(["Item", "Location", "Min Qty", "Max Qty"])
        self._profiles_table.horizontalHeader().setSectionResizeMode(0, self._profiles_table.horizontalHeader().ResizeMode.Stretch)
        self._profiles_table.verticalHeader().setVisible(False)
        self._profiles_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._profiles_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._profiles_table.setAlternatingRowColors(True)
        lay.addWidget(self._profiles_table)
        return frame

    def _build_suggestions_panel(self) -> QWidget:
        frame = QFrame(self)
        frame.setProperty("card", True)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(QLabel("Purchase Suggestions", frame))

        self._suggestions_table = QTableWidget(0, 5, frame)
        self._suggestions_table.setHorizontalHeaderLabels(
            ["Item Code", "Item Name", "On Hand", "On Order", "Suggest Qty"]
        )
        self._suggestions_table.horizontalHeader().setSectionResizeMode(1, self._suggestions_table.horizontalHeader().ResizeMode.Stretch)
        self._suggestions_table.verticalHeader().setVisible(False)
        self._suggestions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._suggestions_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._suggestions_table.setAlternatingRowColors(True)
        lay.addWidget(self._suggestions_table)
        return frame

    # ------------------------------------------------------------------
    def _reload(self) -> None:
        active = self._service_registry.active_company_context.get_active_company()
        if active is None:
            self._profiles_table.setRowCount(0)
            self._suggestions_table.setRowCount(0)
            return
        svc = self._service_registry.reorder_planning_service
        try:
            self._profiles = svc.list_profiles(active.company_id)
        except Exception as exc:
            show_error(self, "Reorder Planning", str(exc))
            self._profiles = []
        self._populate_profiles()

    def _populate_profiles(self) -> None:
        self._profiles_table.setRowCount(len(self._profiles))
        for r, p in enumerate(self._profiles):
            self._profiles_table.setItem(r, 0, QTableWidgetItem(str(p.item_id)))
            self._profiles_table.setItem(r, 1, QTableWidgetItem(str(p.location_id or "All")))
            qty_min = QTableWidgetItem(str(p.min_qty))
            qty_min.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            qty_max = QTableWidgetItem(str(p.max_qty or ""))
            qty_max.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._profiles_table.setItem(r, 2, qty_min)
            self._profiles_table.setItem(r, 3, qty_max)
            self._profiles_table.item(r, 0).setData(Qt.ItemDataRole.UserRole, p.id)

    def _on_generate(self) -> None:
        active = self._service_registry.active_company_context.get_active_company()
        if active is None:
            return
        svc = self._service_registry.reorder_planning_service
        try:
            suggestions = svc.generate_suggestions(active.company_id)
        except Exception as exc:
            show_error(self, "Generate Suggestions", str(exc))
            return

        self._suggestions_table.setRowCount(len(suggestions))
        for r, s in enumerate(suggestions):
            self._suggestions_table.setItem(r, 0, QTableWidgetItem(s.item_code))
            self._suggestions_table.setItem(r, 1, QTableWidgetItem(s.item_name))
            for col, val in enumerate([s.on_hand_qty, s.on_order_qty, s.suggested_order_qty], 2):
                item = QTableWidgetItem(f"{val:,.4f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._suggestions_table.setItem(r, col, item)

    def _on_new_profile(self) -> None:
        show_info(self, "Add Profile", "Use item detail page to add a reorder profile for an item.")

    def _on_delete_profile(self) -> None:
        row = self._profiles_table.currentRow()
        if row < 0 or row >= len(self._profiles):
            return
        profile = self._profiles[row]
        active = self._service_registry.active_company_context.get_active_company()
        if active is None:
            return
        if not confirm(parent=self, title="Delete Profile", message="Delete this reorder profile?"):
            return
        svc = self._service_registry.reorder_planning_service
        try:
            svc.delete_profile(active.company_id, profile.id)
        except Exception as exc:
            show_error(self, "Delete", str(exc))
        self._reload()
