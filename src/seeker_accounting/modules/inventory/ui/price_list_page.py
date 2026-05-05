"""Price List Page — list price lists, launch dialog to create/edit."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.components.confirm_dialog import confirm
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


class PriceListPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self.setObjectName("PriceListPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_table())

        self._service_registry.active_company_context.active_company_changed.connect(self._reload)
        self._reload()

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("PageToolbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(8)
        lbl = QLabel("Price Lists", bar)
        lbl.setObjectName("PageTitle")
        lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        lay.addWidget(lbl)
        lay.addStretch()
        self._new_btn = QPushButton("+ New Price List", bar)
        self._new_btn.setFixedHeight(28)
        self._new_btn.clicked.connect(self._on_new)
        lay.addWidget(self._new_btn)
        self._edit_btn = QPushButton("Edit", bar)
        self._edit_btn.setFixedHeight(28)
        self._edit_btn.clicked.connect(self._on_edit)
        lay.addWidget(self._edit_btn)
        self._delete_btn = QPushButton("Delete", bar)
        self._delete_btn.setFixedHeight(28)
        self._delete_btn.clicked.connect(self._on_delete)
        lay.addWidget(self._delete_btn)
        return bar

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 4, self)
        self._table.setHorizontalHeaderLabels(["Name", "Currency", "Default?", "Active?"])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, self._table.horizontalHeader().ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._on_edit)
        return self._table

    # ------------------------------------------------------------------
    def _reload(self) -> None:
        active = self._service_registry.active_company_context.get_active_company()
        if active is None:
            self._table.setRowCount(0)
            return
        svc = self._service_registry.price_list_service
        try:
            self._rows = svc.list_all(active.company_id)
        except Exception as exc:
            show_error(self, "Price Lists", str(exc))
            self._rows = []
        self._populate()

    def _populate(self) -> None:
        self._table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            self._table.setItem(r, 0, QTableWidgetItem(row.name))
            self._table.setItem(r, 1, QTableWidgetItem(row.currency_code or ""))
            self._table.setItem(r, 2, QTableWidgetItem("Yes" if row.is_default else ""))
            self._table.setItem(r, 3, QTableWidgetItem("Yes" if row.is_active else ""))
            self._table.item(r, 0).setData(Qt.ItemDataRole.UserRole, row.id)

    def _selected_id(self) -> int | None:
        idx = self._table.currentRow()
        if idx < 0 or idx >= len(self._rows):
            return None
        return self._rows[idx].id

    # ------------------------------------------------------------------
    def _on_new(self) -> None:
        active = self._service_registry.active_company_context.get_active_company()
        if active is None:
            return
        from seeker_accounting.modules.inventory.ui.price_list_dialog import PriceListDialog
        dlg = PriceListDialog(self._service_registry, active.company_id, None, self)
        if dlg.exec():
            self._reload()

    def _on_edit(self) -> None:
        pid = self._selected_id()
        if pid is None:
            return
        active = self._service_registry.active_company_context.get_active_company()
        if active is None:
            return
        from seeker_accounting.modules.inventory.ui.price_list_dialog import PriceListDialog
        dlg = PriceListDialog(self._service_registry, active.company_id, pid, self)
        if dlg.exec():
            self._reload()

    def _on_delete(self) -> None:
        pid = self._selected_id()
        if pid is None:
            return
        if not confirm(parent=self, title="Delete Price List", message="Delete this price list and all its lines?"):
            return
        svc = self._service_registry.price_list_service
        active = self._service_registry.active_company_context.get_active_company()
        if active is None:
            return
        try:
            svc.delete(active.company_id, pid)
            show_info(self, "Deleted", "Price list deleted.")
        except Exception as exc:
            show_error(self, "Delete", str(exc))
        self._reload()
