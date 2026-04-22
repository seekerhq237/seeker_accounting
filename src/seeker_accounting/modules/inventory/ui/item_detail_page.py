"""ItemDetailPage — full inventory item workspace with stock position and configuration.

Navigated to via:
    navigation_service.navigate(nav_ids.ITEM_DETAIL, context={"item_id": <int>})
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.inventory.dto.item_dto import ItemDetailDTO
from seeker_accounting.modules.reporting.dto.stock_movement_report_dto import (
    StockMovementDetailRowDTO,
    StockMovementItemDetailDTO,
    StockMovementReportFilterDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.shared.ui.entity_detail.entity_detail_page import EntityDetailPage
from seeker_accounting.shared.ui.entity_detail.money_bar import MoneyBarItem
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_MOVEMENT_LOOKBACK_DAYS = 180
_DOC_TYPE_LABELS = {
    "receipt": "Receipt",
    "issue": "Issue",
    "transfer_in": "Transfer In",
    "transfer_out": "Transfer Out",
    "adjustment": "Adjustment",
    "opening_balance": "Opening",
}

_DECIMAL_FMT = "{:,.4f}"
_CURRENCY_FMT = "{:,.0f}"


def _fmt_qty(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return _DECIMAL_FMT.format(value).rstrip("0").rstrip(".")


def _fmt_amount(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return _CURRENCY_FMT.format(value)


class ItemDetailPage(EntityDetailPage):
    """Full detail workspace for a single inventory item."""

    _back_nav_id = nav_ids.ITEMS
    _back_label = "Back to Items"

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(service_registry, parent)
        self.setObjectName("ItemDetailPage")

        self._item_id: int | None = None
        self._item: ItemDetailDTO | None = None
        self._category_name: str | None = None
        self._movements: StockMovementItemDetailDTO | None = None

        # Action buttons
        self._edit_button = QPushButton("Edit Item", self)
        self._edit_button.setObjectName("SecondaryButton")
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.clicked.connect(self._open_edit_dialog)
        self._action_row_layout.addWidget(self._edit_button)

        # Build tabs
        self._info_tab = self._build_info_tab()
        self._movements_tab = self._build_movements_tab()
        self._initialize_tabs()

        self._set_actions_enabled(False)

    # ── Tab construction ──────────────────────────────────────────────

    def _build_tabs(self) -> list[tuple[str, QWidget]]:
        return [
            ("Movements", self._movements_tab),
            ("Info", self._info_tab),
        ]

    def _build_info_tab(self) -> QWidget:
        container = QFrame()
        container.setObjectName("EntityInfoTab")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # General section
        general_title = QLabel("General", container)
        general_title.setObjectName("EntityInfoSectionTitle")
        layout.addWidget(general_title)

        def _row(label_text: str, attr_name: str) -> None:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)

            lbl = QLabel(label_text, row_widget)
            lbl.setObjectName("EntityInfoLabel")
            lbl.setFixedWidth(180)
            row_layout.addWidget(lbl)

            val = QLabel("—", row_widget)
            val.setObjectName("EntityInfoValue")
            val.setWordWrap(True)
            row_layout.addWidget(val, 1)
            layout.addWidget(row_widget)
            setattr(self, attr_name, val)

        _row("Item Code", "_info_code")
        _row("Item Name", "_info_name")
        _row("Item Type", "_info_type")
        _row("Unit of Measure", "_info_uom")
        _row("Category", "_info_category")
        _row("Cost Method", "_info_cost_method")
        _row("Reorder Level", "_info_reorder_level")
        _row("Description", "_info_description")

        # Accounting section
        sep = QFrame(container)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("EntityInfoSeparator")
        layout.addWidget(sep)

        accounting_title = QLabel("Accounting Mappings", container)
        accounting_title.setObjectName("EntityInfoSectionTitle")
        layout.addWidget(accounting_title)

        _row("Inventory Account", "_info_inventory_account")
        _row("COGS Account", "_info_cogs_account")
        _row("Expense Account", "_info_expense_account")
        _row("Revenue Account", "_info_revenue_account")
        _row("Created", "_info_created")
        layout.addStretch(1)

        return container

    def _build_movements_tab(self) -> QWidget:
        container = QFrame()
        container.setObjectName("EntityInfoTab")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Summary row
        summary_row = QWidget(container)
        summary_layout = QHBoxLayout(summary_row)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(24)

        def _summary_cell(label_text: str, attr: str) -> None:
            cell = QWidget(summary_row)
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)
            lbl = QLabel(label_text, cell)
            lbl.setObjectName("EntityInfoLabel")
            cell_layout.addWidget(lbl)
            val = QLabel("—", cell)
            val.setObjectName("EntityInfoValue")
            cell_layout.addWidget(val)
            summary_layout.addWidget(cell)
            setattr(self, attr, val)

        _summary_cell("Opening Qty", "_mv_opening")
        _summary_cell("Total In", "_mv_inward")
        _summary_cell("Total Out", "_mv_outward")
        _summary_cell("Closing Qty", "_mv_closing")
        summary_layout.addStretch(1)
        self._mv_period_label = QLabel("—", summary_row)
        self._mv_period_label.setObjectName("EntityInfoLabel")
        summary_layout.addWidget(self._mv_period_label)

        layout.addWidget(summary_row)

        # Movements table
        self._movements_table = QTableWidget(container)
        self._movements_table.setObjectName("DashboardActivityTable")
        self._movements_table.setColumnCount(8)
        self._movements_table.setHorizontalHeaderLabels((
            "Date", "Document #", "Type", "Location",
            "Qty In", "Qty Out", "Running Qty", "Line Amount",
        ))
        configure_compact_table(self._movements_table)

        hdr = self._movements_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        self._movements_empty = QLabel("No stock movements for this item in the last 180 days.", container)
        self._movements_empty.setObjectName("DashboardEmptyLabel")
        self._movements_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._movements_empty.setMinimumHeight(60)

        layout.addWidget(self._movements_table, 1)
        layout.addWidget(self._movements_empty)
        self._movements_empty.setVisible(False)

        return container

    # ── Navigation context ────────────────────────────────────────────

    def set_navigation_context(self, context: dict) -> None:
        item_id = context.get("item_id")
        if not isinstance(item_id, int):
            return
        self._item_id = item_id
        self._load_data()

    # ── Data loading ──────────────────────────────────────────────────

    def _load_data(self) -> None:
        if self._item_id is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        company_id = active_company.company_id

        try:
            self._item = self._service_registry.item_service.get_item(
                company_id, self._item_id
            )
        except NotFoundError:
            show_error(self, "Item Detail", "Item not found.")
            self._navigate_back()
            return
        except Exception as exc:
            show_error(self, "Item Detail", f"Failed to load item: {exc}")
            return

        # Load stock position (best-effort — only relevant for stock items)
        stock_position = None
        is_stock_item = self._item.item_type_code in ("STOCK", "STOCKED")
        if is_stock_item:
            try:
                stock_position = self._service_registry.inventory_valuation_service.get_stock_position(
                    company_id, self._item_id
                )
            except Exception as exc:
                _log.debug("Could not load stock position for item %s: %s", self._item_id, exc)

        # Resolve category name (best-effort)
        self._category_name = None
        if self._item.item_category_id:
            try:
                category = self._service_registry.item_category_service.get_item_category(
                    company_id, self._item.item_category_id
                )
                self._category_name = category.name
            except Exception:
                _log.debug("Could not load category for item %s", self._item_id, exc_info=True)

        # Load stock movements (best-effort, only stock items)
        self._movements = None
        if is_stock_item:
            try:
                today = date.today()
                movements_filter = StockMovementReportFilterDTO(
                    company_id=company_id,
                    date_from=today - timedelta(days=_MOVEMENT_LOOKBACK_DAYS),
                    date_to=today,
                    item_id=self._item_id,
                )
                self._movements = self._service_registry.stock_movement_report_service.get_item_detail(
                    movements_filter, self._item_id
                )
            except Exception:
                _log.warning("Could not load stock movements for item %s", self._item_id, exc_info=True)

        self._populate_header()
        self._populate_money_bar(stock_position)
        self._populate_info_tab()
        self._populate_movements_tab()
        self._set_actions_enabled(True)

    # ── Population ────────────────────────────────────────────────────

    def _populate_header(self) -> None:
        item = self._item
        if item is None:
            return
        parts = [p for p in [item.item_type_code, item.unit_of_measure_code] if p]
        subtitle = f"{item.item_code}  ·  " + "  ·  ".join(parts) if parts else item.item_code
        self._set_header(
            title=item.item_name,
            subtitle=subtitle,
            status_label="Active" if item.is_active else "Inactive",
            is_active=item.is_active,
        )

    def _populate_money_bar(self, stock_position: object | None) -> None:
        item = self._item
        if item is None:
            return

        items: list[MoneyBarItem] = []

        if stock_position is not None:
            qty = getattr(stock_position, "quantity_on_hand", None)
            val = getattr(stock_position, "total_value", None)
            avg_cost = getattr(stock_position, "weighted_average_cost", None)
            is_low = getattr(stock_position, "is_low_stock", False)

            items.append(MoneyBarItem(
                label="Stock on Hand",
                value=f"{_fmt_qty(qty)} {item.unit_of_measure_code}",
                tone="danger" if is_low else "success",
            ))
            items.append(MoneyBarItem(
                label="Total Value",
                value=_fmt_amount(val),
                tone="neutral",
            ))
            items.append(MoneyBarItem(
                label="Avg Unit Cost",
                value=_fmt_amount(avg_cost),
                tone="neutral",
            ))
        else:
            items.append(MoneyBarItem(
                label="Item Type",
                value=item.item_type_code.replace("_", " ").title(),
                tone="neutral",
            ))

        if item.reorder_level_quantity is not None:
            items.append(MoneyBarItem(
                label="Reorder Level",
                value=f"{_fmt_qty(item.reorder_level_quantity)} {item.unit_of_measure_code}",
                tone="neutral",
            ))

        self._set_money_bar(items)

    def _populate_info_tab(self) -> None:
        item = self._item
        if item is None:
            return

        def _or_dash(val: str | None) -> str:
            return val or "—"

        self._info_code.setText(_or_dash(item.item_code))
        self._info_name.setText(_or_dash(item.item_name))
        self._info_type.setText(item.item_type_code.replace("_", " ").title() if item.item_type_code else "—")
        self._info_uom.setText(_or_dash(item.unit_of_measure_code))
        self._info_category.setText(self._category_name or "—")
        self._info_cost_method.setText(
            item.inventory_cost_method_code.replace("_", " ").title()
            if item.inventory_cost_method_code else "—"
        )
        self._info_reorder_level.setText(
            f"{_fmt_qty(item.reorder_level_quantity)} {item.unit_of_measure_code}"
            if item.reorder_level_quantity is not None else "—"
        )
        self._info_description.setText(_or_dash(item.description))

        # Accounting mappings (IDs only — no service to reverse-lookup names here)
        def _acct(account_id: int | None) -> str:
            return f"Account #{account_id}" if account_id else "—"

        self._info_inventory_account.setText(_acct(item.inventory_account_id))
        self._info_cogs_account.setText(_acct(item.cogs_account_id))
        self._info_expense_account.setText(_acct(item.expense_account_id))
        self._info_revenue_account.setText(_acct(item.revenue_account_id))
        self._info_created.setText(item.created_at.strftime("%d %b %Y %H:%M"))

    def _populate_movements_tab(self) -> None:
        today = date.today()
        date_from = today - timedelta(days=_MOVEMENT_LOOKBACK_DAYS)
        self._mv_period_label.setText(
            f"{date_from.strftime('%d %b %Y')}  –  {today.strftime('%d %b %Y')}"
        )

        table = self._movements_table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        mv = self._movements
        if mv is None or not mv.rows:
            self._mv_opening.setText("—")
            self._mv_inward.setText("—")
            self._mv_outward.setText("—")
            self._mv_closing.setText("—")
            table.setVisible(False)
            self._movements_empty.setVisible(True)
            return

        table.setVisible(True)
        self._movements_empty.setVisible(False)

        uom = self._item.unit_of_measure_code if self._item else ""
        self._mv_opening.setText(f"{_fmt_qty(mv.opening_quantity)} {uom}".strip())
        self._mv_inward.setText(f"{_fmt_qty(mv.inward_quantity)} {uom}".strip())
        self._mv_outward.setText(f"{_fmt_qty(mv.outward_quantity)} {uom}".strip())
        closing_qty = getattr(mv, "closing_quantity", None)
        if closing_qty is None:
            # Derive if DTO does not expose closing_quantity
            closing_qty = mv.opening_quantity + mv.inward_quantity - mv.outward_quantity
        self._mv_closing.setText(f"{_fmt_qty(closing_qty)} {uom}".strip())

        for row_idx, line in enumerate(mv.rows):
            table.insertRow(row_idx)

            date_cell = QTableWidgetItem(line.document_date.strftime("%d %b %Y"))
            date_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row_idx, 0, date_cell)

            table.setItem(row_idx, 1, QTableWidgetItem(line.document_number or "—"))

            type_text = _DOC_TYPE_LABELS.get(line.document_type_code, line.document_type_code.replace("_", " ").title())
            table.setItem(row_idx, 2, QTableWidgetItem(type_text))

            loc_text = line.location_name or line.location_code or "—"
            table.setItem(row_idx, 3, QTableWidgetItem(loc_text))

            inward_text = _fmt_qty(line.inward_quantity) if line.inward_quantity else "—"
            inward_cell = QTableWidgetItem(inward_text)
            inward_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 4, inward_cell)

            outward_text = _fmt_qty(line.outward_quantity) if line.outward_quantity else "—"
            outward_cell = QTableWidgetItem(outward_text)
            outward_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 5, outward_cell)

            running_cell = QTableWidgetItem(_fmt_qty(line.running_quantity))
            running_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 6, running_cell)

            amount_text = _fmt_amount(line.line_amount) if line.line_amount is not None else "—"
            amount_cell = QTableWidgetItem(amount_text)
            amount_cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 7, amount_cell)

        table.setSortingEnabled(True)

    # ── Actions ───────────────────────────────────────────────────────

    def _set_actions_enabled(self, enabled: bool) -> None:
        self._edit_button.setEnabled(enabled)

    def _open_edit_dialog(self) -> None:
        if self._item is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        from seeker_accounting.modules.inventory.ui.item_dialog import ItemDialog
        updated = ItemDialog.edit_item(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            item_id=self._item.id,
            parent=self,
        )
        if updated is not None:
            self._load_data()
