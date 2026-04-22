from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.fixed_assets.ui.asset_category_dialog import AssetCategoryDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_METHOD_LABELS = {
    "straight_line": "Straight Line",
    "reducing_balance": "Reducing Balance",
    "sum_of_years_digits": "Sum of Years Digits",
}


class AssetCategoriesPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._rows = []

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    def reload(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            self._rows = []
            self._table.setRowCount(0)
            self._count_label.setText("")
            self._stack.setCurrentWidget(self._no_company_state)
            return
        try:
            self._rows = self._service_registry.asset_category_service.list_asset_categories(
                active_company.company_id
            )
        except Exception as exc:
            self._rows = []
            self._table.setRowCount(0)
            self._stack.setCurrentWidget(self._empty_state)
            show_error(self, "Asset Categories", f"Could not load data.\n\n{exc}")
            return
        self._populate(self._rows)
        self._sync_stack(active_company, self._rows)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        layout.addStretch(1)

        self._new_btn = QPushButton("New Category", card)
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.clicked.connect(self._on_new)
        layout.addWidget(self._new_btn)

        self._edit_btn = QPushButton("Edit", card)
        self._edit_btn.setProperty("variant", "secondary")
        self._edit_btn.clicked.connect(self._on_edit)
        layout.addWidget(self._edit_btn)

        self._deactivate_btn = QPushButton("Deactivate", card)
        self._deactivate_btn.setProperty("variant", "secondary")
        self._deactivate_btn.clicked.connect(self._on_deactivate)
        layout.addWidget(self._deactivate_btn)

        refresh_btn = QPushButton("Refresh", card)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(self.reload)
        layout.addWidget(refresh_btn)
        return card

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_company_state = self._build_no_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        top = QWidget(card)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        lbl = QLabel("Asset Categories", top)
        lbl.setObjectName("CardTitle")
        tl.addWidget(lbl)
        tl.addStretch(1)
        self._count_label = QLabel(top)
        self._count_label.setObjectName("ToolbarMeta")
        tl.addWidget(self._count_label)
        layout.addWidget(top)

        self._table = QTableWidget(card)
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ("Code", "Name", "Asset Account", "Accum. Depr. Account",
             "Depr. Expense Account", "Default Life", "Default Method", "Status")
        )
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(lambda _: self._on_edit())
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("No asset categories yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel(
            "Create asset categories to define account mapping and default depreciation settings.", card
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addStretch(1)
        return card

    def _build_no_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel("Asset categories are company-scoped.", card)
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        actions = QWidget(card)
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 4, 0, 0)
        al.addStretch(1)
        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------

    def _populate(self, rows: list) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for row in rows:
            ri = self._table.rowCount()
            self._table.insertRow(ri)
            code_item = QTableWidgetItem(row.code)
            code_item.setData(Qt.ItemDataRole.UserRole, row.id)
            self._table.setItem(ri, 0, code_item)
            self._table.setItem(ri, 1, QTableWidgetItem(row.name))
            self._table.setItem(ri, 2, QTableWidgetItem(
                f"{row.asset_account_code} — {row.asset_account_name}"
            ))
            self._table.setItem(ri, 3, QTableWidgetItem(
                f"{row.accumulated_depreciation_account_code} — {row.accumulated_depreciation_account_name}"
            ))
            self._table.setItem(ri, 4, QTableWidgetItem(
                f"{row.depreciation_expense_account_code} — {row.depreciation_expense_account_name}"
            ))
            self._table.setItem(ri, 5, QTableWidgetItem(f"{row.default_useful_life_months} mo"))
            self._table.setItem(ri, 6, QTableWidgetItem(
                _METHOD_LABELS.get(row.default_depreciation_method_code, row.default_depreciation_method_code)
            ))
            status_item = QTableWidgetItem("Active" if row.is_active else "Inactive")
            status_item.setData(Qt.ItemDataRole.UserRole + 1, row.is_active)
            self._table.setItem(ri, 7, status_item)
        self._table.resizeColumnsToContents()
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)
        self._table.setSortingEnabled(True)
        count = len(rows)
        self._count_label.setText(f"{count} record" if count == 1 else f"{count} records")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_new(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Asset Categories", "Select an active company first.")
            return
        dialog = AssetCategoryDialog(
            self._service_registry, company.company_id, company.company_name, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _on_edit(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        cat_id = item.data(Qt.ItemDataRole.UserRole)
        dialog = AssetCategoryDialog(
            self._service_registry, company.company_id, company.company_name,
            category_id=cat_id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _on_deactivate(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        cat_id = item.data(Qt.ItemDataRole.UserRole)
        cat_code = item.text()
        reply = QMessageBox.question(
            self, "Deactivate Category",
            f"Deactivate asset category '{cat_code}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.asset_category_service.deactivate_asset_category(
                company.company_id, cat_id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Asset Categories", str(exc))
            return
        self.reload()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_stack(self, company: ActiveCompanyDTO | None, rows: list) -> None:
        if company is None:
            self._stack.setCurrentWidget(self._no_company_state)
        elif rows:
            self._stack.setCurrentWidget(self._table_surface)
        else:
            self._stack.setCurrentWidget(self._empty_state)
