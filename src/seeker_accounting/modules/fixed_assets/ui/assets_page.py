from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.fixed_assets.ui.asset_dialog import AssetDialog
from seeker_accounting.modules.fixed_assets.ui.depreciation_schedule_preview_dialog import (
    DepreciationSchedulePreviewDialog,
)
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_STATUS_LABELS = {
    "draft": "Draft",
    "active": "Active",
    "fully_depreciated": "Fully Depreciated",
    "disposed": "Disposed",
}

_METHOD_LABELS = {
    "straight_line": "Straight Line",
    "reducing_balance": "Reducing Balance",
    "sum_of_years_digits": "Sum of Years Digits",
}

_STATUS_FILTER_OPTIONS = [
    (None, "All Statuses"),
    ("draft", "Draft"),
    ("active", "Active"),
    ("fully_depreciated", "Fully Depreciated"),
    ("disposed", "Disposed"),
]


class AssetsPage(QWidget):
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
        status_filter = self._status_filter_combo.currentData()
        try:
            self._rows = self._service_registry.asset_service.list_assets(
                active_company.company_id,
                status_code=status_filter,
            )
        except Exception as exc:
            self._rows = []
            self._table.setRowCount(0)
            self._stack.setCurrentWidget(self._empty_state)
            show_error(self, "Asset Register", f"Could not load data.\n\n{exc}")
            return
        self._apply_search_filter()
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

        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search assets…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._apply_search_filter)
        layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(card)
        for code, label in _STATUS_FILTER_OPTIONS:
            self._status_filter_combo.addItem(label, code)
        self._status_filter_combo.currentIndexChanged.connect(lambda _: self.reload())
        layout.addWidget(self._status_filter_combo)

        self._new_btn = QPushButton("New Asset", card)
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.clicked.connect(self._on_new)
        layout.addWidget(self._new_btn)

        self._edit_btn = QPushButton("Edit", card)
        self._edit_btn.setProperty("variant", "secondary")
        self._edit_btn.clicked.connect(self._on_edit)
        layout.addWidget(self._edit_btn)

        self._schedule_btn = QPushButton("Preview Schedule", card)
        self._schedule_btn.setProperty("variant", "secondary")
        self._schedule_btn.clicked.connect(self._on_preview_schedule)
        layout.addWidget(self._schedule_btn)

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
        lbl = QLabel("Assets", top)
        lbl.setObjectName("CardTitle")
        tl.addWidget(lbl)
        tl.addStretch(1)
        self._count_label = QLabel(top)
        self._count_label.setObjectName("ToolbarMeta")
        tl.addWidget(self._count_label)
        layout.addWidget(top)

        self._table = QTableWidget(card)
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels((
            "Number", "Name", "Category", "Cap. Date",
            "Cost", "Salvage", "Life", "Method", "Status",
        ))
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
        title = QLabel("No assets yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel(
            "Add assets to the register to track acquisition cost, depreciation, and net book value.",
            card,
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
        summary = QLabel("The asset register is company-scoped.", card)
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

    def _apply_search_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        visible_rows = [
            row for row in self._rows
            if not query
            or query in row.asset_number.lower()
            or query in row.asset_name.lower()
            or query in row.asset_category_code.lower()
            or query in row.asset_category_name.lower()
        ]
        self._populate(visible_rows)
        company = self._active_company()
        self._sync_stack(company, self._rows)

    def _populate(self, rows: list) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for row in rows:
            ri = self._table.rowCount()
            self._table.insertRow(ri)
            num_item = QTableWidgetItem(row.asset_number)
            num_item.setData(Qt.ItemDataRole.UserRole, row.id)
            self._table.setItem(ri, 0, num_item)
            self._table.setItem(ri, 1, QTableWidgetItem(row.asset_name))
            self._table.setItem(ri, 2, QTableWidgetItem(
                f"{row.asset_category_code} — {row.asset_category_name}"
            ))
            self._table.setItem(ri, 3, QTableWidgetItem(str(row.capitalization_date)))

            cost_item = QTableWidgetItem(f"{row.acquisition_cost:,.2f}")
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(ri, 4, cost_item)

            salvage_text = f"{row.salvage_value:,.2f}" if row.salvage_value is not None else "—"
            salvage_item = QTableWidgetItem(salvage_text)
            salvage_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(ri, 5, salvage_item)

            self._table.setItem(ri, 6, QTableWidgetItem(f"{row.useful_life_months} mo"))
            self._table.setItem(ri, 7, QTableWidgetItem(
                _METHOD_LABELS.get(row.depreciation_method_code, row.depreciation_method_code)
            ))
            self._table.setItem(ri, 8, QTableWidgetItem(
                _STATUS_LABELS.get(row.status_code, row.status_code)
            ))
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
            show_error(self, "Asset Register", "Select an active company first.")
            return
        dialog = AssetDialog(
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
        asset_id = item.data(Qt.ItemDataRole.UserRole)
        dialog = AssetDialog(
            self._service_registry, company.company_id, company.company_name,
            asset_id=asset_id, parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _on_preview_schedule(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._table.currentRow()
        if row < 0:
            show_error(self, "Asset Register", "Select an asset to preview its depreciation schedule.")
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        asset_id = item.data(Qt.ItemDataRole.UserRole)
        dialog = DepreciationSchedulePreviewDialog(
            self._service_registry, company.company_id, asset_id, parent=self
        )
        dialog.exec()

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
