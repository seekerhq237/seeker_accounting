from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.inventory.dto.bill_of_material_dto import (
    BomComponentCommand,
    CreateBillOfMaterialCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_import_dto import (
    ApplyInventoryImportJobCommand,
    CreateInventoryImportJobCommand,
    InventoryImportRowCommand,
)
from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand
from seeker_accounting.modules.inventory.dto.item_variant_dto import (
    CreateItemAttributeDefinitionCommand,
    CreateItemVariantCommand,
)
from seeker_accounting.modules.inventory.dto.production_order_dto import BuildProductionDocumentsCommand
from seeker_accounting.modules.inventory.dto.production_order_dto import CreateProductionOrderCommand
from seeker_accounting.modules.inventory.dto.stock_count_dto import (
    ApproveStockCountSessionCommand,
    CreateStockCountPlanCommand,
    EnterStockCountLineCommand,
    StartStockCountSessionCommand,
)
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, apply_status_chip_to_column
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


VARIANT_COLUMNS = (
    DataTableColumn(key="parent", title="Parent ID"),
    DataTableColumn(key="child_code", title="Child SKU"),
    DataTableColumn(key="child_name", title="Name"),
    DataTableColumn(key="attributes", title="Attributes"),
    DataTableColumn(key="status", title="Status"),
)
BOM_COLUMNS = (
    DataTableColumn(key="item", title="Item ID"),
    DataTableColumn(key="version", title="Version"),
    DataTableColumn(key="type", title="Type"),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="components", title="Components"),
)
STOCK_COUNT_COLUMNS = (
    DataTableColumn(key="number", title="Plan #"),
    DataTableColumn(key="date", title="Date"),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="locations", title="Locations"),
)
IMPORT_COLUMNS = (
    DataTableColumn(key="template", title="Template"),
    DataTableColumn(key="source", title="Source"),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="valid", title="Valid"),
    DataTableColumn(key="invalid", title="Invalid"),
    DataTableColumn(key="conflict", title="Conflict"),
)
PRODUCTION_COLUMNS = (
    DataTableColumn(key="number", title="Order #"),
    DataTableColumn(key="date", title="Date"),
    DataTableColumn(key="finished", title="Finished Item"),
    DataTableColumn(key="quantity", title="Qty"),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="issue", title="Issue Doc"),
    DataTableColumn(key="receipt", title="Receipt Doc"),
)


class InventoryOperationsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._bom_ids: list[int] = []
        self._count_plan_ids: list[int] = []
        self._import_ids: list[int] = []
        self._production_ids: list[int] = []
        self.setObjectName("InventoryOperationsPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_tabs(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_args: self.reload()
        )
        self.reload()

    def _build_toolbar(self) -> QWidget:
        toolbar = QFrame(self)
        toolbar.setObjectName("PageToolbar")
        toolbar.setProperty("card", True)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        title = QLabel("Inventory Operations", toolbar)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)
        self._meta_label = QLabel(toolbar)
        self._meta_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._meta_label)
        layout.addStretch(1)
        actions = (
            ("New Attribute", self._create_attribute),
            ("New Variant", self._create_variant),
            ("New BOM", self._create_bom),
            ("Approve BOM", self._approve_selected_bom),
            ("New Count", self._create_stock_count_plan),
            ("Start Count", self._start_selected_stock_count),
            ("Enter Count", self._enter_stock_count_line),
            ("Approve Count", self._approve_stock_count_session),
            ("New Import", self._create_import_job),
            ("Apply Import", self._apply_selected_import),
            ("New Production", self._create_production_order),
        )
        self._action_buttons: list[QPushButton] = []
        for text, slot in actions:
            button = QPushButton(text, toolbar)
            button.setProperty("variant", "ghost")
            button.clicked.connect(slot)
            self._action_buttons.append(button)
            layout.addWidget(button)
        self._build_post_button = QPushButton("Build / Post Production", toolbar)
        self._build_post_button.setProperty("variant", "secondary")
        self._build_post_button.clicked.connect(self._build_and_post_selected_production)
        layout.addWidget(self._build_post_button)
        refresh = QPushButton("Refresh", toolbar)
        refresh.setProperty("variant", "ghost")
        refresh.clicked.connect(self.reload)
        layout.addWidget(refresh)
        return toolbar

    def _build_tabs(self) -> QTabWidget:
        self._tabs = QTabWidget(self)
        self._variant_model, self._variant_table = self._add_table_tab("Variants", VARIANT_COLUMNS, 4)
        self._bom_model, self._bom_table = self._add_table_tab("BOMs", BOM_COLUMNS, 3)
        self._count_model, self._count_table = self._add_table_tab("Stock Counts", STOCK_COUNT_COLUMNS, 2)
        self._import_model, self._import_table = self._add_table_tab("Imports", IMPORT_COLUMNS, 2)
        self._production_model, self._production_table = self._add_table_tab("Production", PRODUCTION_COLUMNS, 4)
        self._bom_table.selection_changed.connect(lambda _rows: self._update_actions())
        self._count_table.selection_changed.connect(lambda _rows: self._update_actions())
        self._import_table.selection_changed.connect(lambda _rows: self._update_actions())
        self._production_table.selection_changed.connect(lambda _rows: self._update_actions())
        return self._tabs

    def _add_table_tab(self, title: str, columns: tuple[DataTableColumn, ...], status_column: int | None):
        container = QFrame(self._tabs)
        container.setObjectName("PageCard")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        model = QStandardItemModel(0, len(columns), self)
        model.setHorizontalHeaderLabels([column.title for column in columns])
        table = DataTable(
            columns=columns,
            show_search=True,
            show_count=True,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No records to display.",
            parent=container,
        )
        table.set_model(model)
        if status_column is not None:
            apply_status_chip_to_column(table.view(), status_column)
        layout.addWidget(table)
        self._tabs.addTab(container, title)
        return model, table

    def reload(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            self._clear_models()
            self._meta_label.setText("Select a company")
            self._update_actions()
            return
        company_id = active_company.company_id
        loaded = 0
        loaded += self._load_variants(company_id)
        loaded += self._load_boms(company_id)
        loaded += self._load_stock_counts(company_id)
        loaded += self._load_imports(company_id)
        loaded += self._load_production(company_id)
        self._meta_label.setText(f"{loaded} operational record" if loaded == 1 else f"{loaded} operational records")
        self._update_actions()

    def _load_variants(self, company_id: int) -> int:
        self._variant_model.removeRows(0, self._variant_model.rowCount())
        try:
            rows = self._service_registry.item_variant_service.list_variants(company_id)
        except Exception as exc:
            self._append_message_row(self._variant_model, len(VARIANT_COLUMNS), str(exc))
            return 0
        for row in rows:
            self._variant_model.appendRow([
                self._item(row.parent_item_id),
                self._item(row.child_item_code, row.id),
                self._item(row.child_item_name),
                self._item(row.attribute_values_json),
                self._item(row.status_code),
            ])
        return len(rows)

    def _load_boms(self, company_id: int) -> int:
        self._bom_model.removeRows(0, self._bom_model.rowCount())
        self._bom_ids = []
        try:
            rows = self._service_registry.bill_of_material_service.list_boms(company_id)
        except Exception as exc:
            self._append_message_row(self._bom_model, len(BOM_COLUMNS), str(exc))
            return 0
        for row in rows:
            self._bom_ids.append(row.id)
            self._bom_model.appendRow([
                self._item(row.item_id, row.id),
                self._item(row.version),
                self._item(row.type_code),
                self._item(row.status_code),
                self._item(len(row.components)),
            ])
        return len(rows)

    def _load_stock_counts(self, company_id: int) -> int:
        self._count_model.removeRows(0, self._count_model.rowCount())
        self._count_plan_ids = []
        try:
            rows = self._service_registry.stock_count_service.list_plans(company_id)
        except Exception as exc:
            self._append_message_row(self._count_model, len(STOCK_COUNT_COLUMNS), str(exc))
            return 0
        for row in rows:
            self._count_plan_ids.append(row.id)
            self._count_model.appendRow([
                self._item(row.plan_number, row.id),
                self._item(row.plan_date.isoformat()),
                self._item(row.status_code),
                self._item(len(row.location_ids)),
            ])
        return len(rows)

    def _load_imports(self, company_id: int) -> int:
        self._import_model.removeRows(0, self._import_model.rowCount())
        self._import_ids = []
        try:
            rows = self._service_registry.inventory_import_service.list_jobs(company_id)
        except Exception as exc:
            self._append_message_row(self._import_model, len(IMPORT_COLUMNS), str(exc))
            return 0
        for row in rows:
            self._import_ids.append(row.id)
            self._import_model.appendRow([
                self._item(row.template_code, row.id),
                self._item(row.source_filename or ""),
                self._item(row.status_code),
                self._numeric(row.valid_rows),
                self._numeric(row.invalid_rows),
                self._numeric(row.conflict_rows),
            ])
        return len(rows)

    def _load_production(self, company_id: int) -> int:
        self._production_model.removeRows(0, self._production_model.rowCount())
        self._production_ids = []
        try:
            rows = self._service_registry.production_order_service.list_orders(company_id)
        except Exception as exc:
            self._append_message_row(self._production_model, len(PRODUCTION_COLUMNS), str(exc))
            return 0
        for row in rows:
            self._production_ids.append(row.id)
            self._production_model.appendRow([
                self._item(row.order_number, row.id),
                self._item(row.order_date.isoformat()),
                self._item(row.finished_item_id),
                self._numeric(row.quantity_to_produce),
                self._item(row.status_code),
                self._item(row.component_issue_document_id or ""),
                self._item(row.finished_receipt_document_id or ""),
            ])
        return len(rows)

    def _create_attribute(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        data = self._json_payload(
            "New Variant Attribute",
            {
                "attribute_code": "COLOR",
                "attribute_name": "Color",
                "item_category_id": None,
                "allowed_values_json": ["Red", "Blue"],
                "sort_order": 10,
            },
        )
        if data is None:
            return
        try:
            self._service_registry.item_variant_service.create_attribute(
                active_company.company_id,
                CreateItemAttributeDefinitionCommand(
                    attribute_code=self._required_text(data, "attribute_code"),
                    attribute_name=self._required_text(data, "attribute_name"),
                    item_category_id=self._optional_int(data, "item_category_id"),
                    allowed_values_json=self._json_text(data.get("allowed_values_json")),
                    sort_order=self._optional_int(data, "sort_order") or 0,
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Variant Attribute", str(exc))
            return
        show_info(self, "Variant Attribute", "Attribute created.")
        self.reload()

    def _create_variant(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        data = self._json_payload(
            "New Variant",
            {
                "parent_item_id": 1,
                "child_item": {
                    "item_code": "ITEM-RED",
                    "item_name": "Item Red",
                    "item_type_code": "inventory",
                    "unit_of_measure_id": 1,
                    "tracking_mode_code": "none",
                    "standard_cost": "0.00",
                },
                "attribute_values": {"COLOR": "Red"},
                "variant_sku_suffix": "RED",
            },
        )
        if data is None:
            return
        try:
            child_item = data.get("child_item")
            if not isinstance(child_item, dict):
                raise ValidationError("Variant child_item must be a JSON object.")
            self._service_registry.item_variant_service.create_variant(
                active_company.company_id,
                CreateItemVariantCommand(
                    parent_item_id=self._required_int(data, "parent_item_id"),
                    child_item=self._create_item_command(child_item),
                    attribute_values_json=self._json_text(data.get("attribute_values") or data.get("attribute_values_json")) or "{}",
                    variant_sku_suffix=self._optional_text(data, "variant_sku_suffix"),
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Variant", str(exc))
            return
        show_info(self, "Variant", "Variant created.")
        self.reload()

    def _create_bom(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        data = self._json_payload(
            "New Bill of Material",
            {
                "item_id": 1,
                "version": "1",
                "type_code": "assembly",
                "effective_from": date.today().isoformat(),
                "overhead_per_unit": "0.00",
                "components": [
                    {"component_item_id": 2, "quantity_per": "1.0000", "scrap_percent": "0", "sequence": 1}
                ],
            },
        )
        if data is None:
            return
        try:
            components = data.get("components") or []
            if not isinstance(components, list):
                raise ValidationError("BOM components must be a JSON array.")
            self._service_registry.bill_of_material_service.create_bom(
                active_company.company_id,
                CreateBillOfMaterialCommand(
                    item_id=self._required_int(data, "item_id"),
                    version=self._required_text(data, "version"),
                    type_code=self._optional_text(data, "type_code") or "assembly",
                    effective_from=self._optional_date(data, "effective_from"),
                    effective_to=self._optional_date(data, "effective_to"),
                    overhead_per_unit=self._optional_decimal(data, "overhead_per_unit"),
                    notes=self._optional_text(data, "notes"),
                    components=tuple(self._bom_component(component) for component in components),
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "BOM", str(exc))
            return
        show_info(self, "BOM", "Bill of material created.")
        self.reload()

    def _approve_selected_bom(self) -> None:
        active_company = self._active_company()
        bom_id = self._selected_id(self._bom_table, self._bom_ids)
        if active_company is None or bom_id is None:
            return
        try:
            self._service_registry.bill_of_material_service.approve_bom(
                active_company.company_id,
                bom_id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "BOM", str(exc))
            return
        show_info(self, "BOM", "Bill of material approved.")
        self.reload()

    def _create_stock_count_plan(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        data = self._json_payload(
            "New Stock Count Plan",
            {"plan_date": date.today().isoformat(), "location_ids": [1], "cycle_class_code": None, "notes": None},
        )
        if data is None:
            return
        try:
            location_ids = data.get("location_ids") or []
            if not isinstance(location_ids, list):
                raise ValidationError("location_ids must be a JSON array.")
            self._service_registry.stock_count_service.create_plan(
                active_company.company_id,
                CreateStockCountPlanCommand(
                    plan_date=self._required_date(data, "plan_date"),
                    location_ids=tuple(int(value) for value in location_ids),
                    cycle_class_code=self._optional_text(data, "cycle_class_code"),
                    item_filter_json=self._json_text(data.get("item_filter_json")),
                    notes=self._optional_text(data, "notes"),
                    created_by_user_id=self._service_registry.app_context.current_user_id,
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Stock Count", str(exc))
            return
        show_info(self, "Stock Count", "Plan created.")
        self.reload()

    def _start_selected_stock_count(self) -> None:
        active_company = self._active_company()
        plan_id = self._selected_id(self._count_table, self._count_plan_ids)
        if active_company is None or plan_id is None:
            return
        data = self._json_payload("Start Stock Count", {"session_date": date.today().isoformat(), "notes": None})
        if data is None:
            return
        try:
            self._service_registry.stock_count_service.start_session(
                active_company.company_id,
                StartStockCountSessionCommand(
                    plan_id=plan_id,
                    session_date=self._required_date(data, "session_date"),
                    notes=self._optional_text(data, "notes"),
                    frozen_by_user_id=self._service_registry.app_context.current_user_id,
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Stock Count", str(exc))
            return
        show_info(self, "Stock Count", "Session started.")
        self.reload()

    def _enter_stock_count_line(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        data = self._json_payload("Enter Count Line", {"line_id": 1, "counted_quantity": "0.0000", "variance_reason_code_id": None, "notes": None})
        if data is None:
            return
        try:
            self._service_registry.stock_count_service.enter_count_line(
                active_company.company_id,
                EnterStockCountLineCommand(
                    line_id=self._required_int(data, "line_id"),
                    counted_quantity=self._required_decimal(data, "counted_quantity"),
                    variance_reason_code_id=self._optional_int(data, "variance_reason_code_id"),
                    counted_by_user_id=self._service_registry.app_context.current_user_id,
                    notes=self._optional_text(data, "notes"),
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Stock Count", str(exc))
            return
        show_info(self, "Stock Count", "Count line saved.")
        self.reload()

    def _approve_stock_count_session(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        data = self._json_payload("Approve Stock Count", {"session_id": 1, "post_adjustments_immediately": False, "notes": None})
        if data is None:
            return
        try:
            self._service_registry.stock_count_service.approve_session(
                active_company.company_id,
                ApproveStockCountSessionCommand(
                    session_id=self._required_int(data, "session_id"),
                    approved_by_user_id=self._service_registry.app_context.current_user_id,
                    notes=self._optional_text(data, "notes"),
                    post_adjustments_immediately=bool(data.get("post_adjustments_immediately", False)),
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Stock Count", str(exc))
            return
        show_info(self, "Stock Count", "Session approved and adjustments generated.")
        self.reload()

    def _create_import_job(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        data = self._json_payload(
            "New Inventory Import Preview",
            {
                "template_code": "items",
                "source_filename": "manual.json",
                "rows": [
                    {"row_number": 1, "status_code": "valid", "normalized_json": {"item_code": "SKU-001", "item_name": "Imported Item", "item_type_code": "inventory", "unit_of_measure_id": 1}}
                ],
            },
        )
        if data is None:
            return
        try:
            rows = data.get("rows") or []
            if not isinstance(rows, list):
                raise ValidationError("Import rows must be a JSON array.")
            self._service_registry.inventory_import_service.create_preview_job(
                active_company.company_id,
                CreateInventoryImportJobCommand(
                    template_code=self._required_text(data, "template_code"),
                    source_filename=self._optional_text(data, "source_filename"),
                    created_by_user_id=self._service_registry.app_context.current_user_id,
                    preview_json=self._json_text(data.get("preview_json")),
                    error_summary=self._optional_text(data, "error_summary"),
                    rows=tuple(self._import_row(row) for row in rows),
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Inventory Import", str(exc))
            return
        show_info(self, "Inventory Import", "Preview job created.")
        self.reload()

    def _apply_selected_import(self) -> None:
        active_company = self._active_company()
        job_id = self._selected_id(self._import_table, self._import_ids)
        if active_company is None or job_id is None:
            return
        data = self._json_payload("Apply Inventory Import", {"post_documents_immediately": False})
        if data is None:
            return
        try:
            self._service_registry.inventory_import_service.mark_applied(
                active_company.company_id,
                ApplyInventoryImportJobCommand(
                    job_id=job_id,
                    applied_by_user_id=self._service_registry.app_context.current_user_id,
                    post_documents_immediately=bool(data.get("post_documents_immediately", False)),
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Inventory Import", str(exc))
            return
        show_info(self, "Inventory Import", "Import applied.")
        self.reload()

    def _create_production_order(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        data = self._json_payload(
            "New Production Order",
            {"bom_id": 1, "order_date": date.today().isoformat(), "quantity_to_produce": "1.0000", "location_id": 1, "notes": None},
        )
        if data is None:
            return
        try:
            self._service_registry.production_order_service.create_order(
                active_company.company_id,
                CreateProductionOrderCommand(
                    bom_id=self._required_int(data, "bom_id"),
                    order_date=self._required_date(data, "order_date"),
                    quantity_to_produce=self._required_decimal(data, "quantity_to_produce"),
                    location_id=self._optional_int(data, "location_id"),
                    notes=self._optional_text(data, "notes"),
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Production", str(exc))
            return
        show_info(self, "Production", "Production order created.")
        self.reload()

    def _build_and_post_selected_production(self) -> None:
        active_company = self._active_company()
        selected_id = self._selected_production_order_id()
        if active_company is None or selected_id is None:
            return
        data = self._json_payload(
            "Build / Post Production",
            {"component_batch_ids": {}, "component_serial_ids": {}, "post_immediately": True},
        )
        if data is None:
            return
        try:
            result = self._service_registry.production_order_service.build_documents(
                active_company.company_id,
                BuildProductionDocumentsCommand(
                    production_order_id=selected_id,
                    post_immediately=bool(data.get("post_immediately", True)),
                    actor_user_id=self._service_registry.app_context.current_user_id,
                    component_batch_ids={int(key): int(value) for key, value in (data.get("component_batch_ids") or {}).items()},
                    component_serial_ids={int(key): tuple(int(item) for item in value) for key, value in (data.get("component_serial_ids") or {}).items()},
                ),
            )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Production", str(exc))
            self.reload()
            return
        show_info(self, "Production", f"Production order {result.order_number} completed.")
        self.reload()

    def _selected_production_order_id(self) -> int | None:
        return self._selected_id(self._production_table, self._production_ids)

    @staticmethod
    def _selected_id(table: DataTable, ids: list[int]) -> int | None:
        rows = table.selected_rows()
        if not rows:
            return None
        index = rows[0]
        if 0 <= index < len(ids):
            return ids[index]
        return None

    def _json_payload(self, title: str, example: dict[str, Any]) -> dict[str, Any] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QFormLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        editor = QPlainTextEdit(dialog)
        editor.setMinimumSize(560, 280)
        editor.setPlainText(json.dumps(example, indent=2))
        layout.addRow(QLabel("JSON", dialog), editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        try:
            payload = json.loads(editor.toPlainText())
        except json.JSONDecodeError as exc:
            show_error(self, title, f"JSON is invalid: {exc}")
            return None
        if not isinstance(payload, dict):
            show_error(self, title, "JSON payload must be an object.")
            return None
        return payload

    def _create_item_command(self, data: dict[str, Any]) -> CreateItemCommand:
        return CreateItemCommand(
            item_code=self._required_text(data, "item_code"),
            item_name=self._required_text(data, "item_name"),
            item_type_code=self._optional_text(data, "item_type_code") or "inventory",
            unit_of_measure_id=self._required_int(data, "unit_of_measure_id"),
            unit_of_measure_code=self._optional_text(data, "unit_of_measure_code") or "UNIT",
            item_category_id=self._optional_int(data, "item_category_id"),
            inventory_cost_method_code=self._optional_text(data, "inventory_cost_method_code"),
            standard_cost=self._optional_decimal(data, "standard_cost"),
            lifecycle_status_code=self._optional_text(data, "lifecycle_status_code") or "active",
            tracking_mode_code=self._optional_text(data, "tracking_mode_code") or "none",
            parent_item_id=self._optional_int(data, "parent_item_id"),
            is_variant=bool(data.get("is_variant", False)),
            attribute_values_json=self._json_text(data.get("attribute_values_json") or data.get("attribute_values")),
            is_sellable=bool(data.get("is_sellable", True)),
            is_purchasable=bool(data.get("is_purchasable", True)),
            is_stockable=bool(data.get("is_stockable", True)),
            ohada_stock_class_code=self._optional_text(data, "ohada_stock_class_code"),
            inventory_account_id=self._optional_int(data, "inventory_account_id"),
            cogs_account_id=self._optional_int(data, "cogs_account_id"),
            expense_account_id=self._optional_int(data, "expense_account_id"),
            revenue_account_id=self._optional_int(data, "revenue_account_id"),
            purchase_tax_code_id=self._optional_int(data, "purchase_tax_code_id"),
            sales_tax_code_id=self._optional_int(data, "sales_tax_code_id"),
            reorder_level_quantity=self._optional_decimal(data, "reorder_level_quantity"),
            description=self._optional_text(data, "description"),
        )

    def _bom_component(self, data: dict[str, Any]) -> BomComponentCommand:
        if not isinstance(data, dict):
            raise ValidationError("BOM component rows must be JSON objects.")
        return BomComponentCommand(
            component_item_id=self._required_int(data, "component_item_id"),
            quantity_per=self._required_decimal(data, "quantity_per"),
            sequence=self._optional_int(data, "sequence"),
            scrap_percent=self._optional_decimal(data, "scrap_percent") or Decimal("0"),
            uom_id=self._optional_int(data, "uom_id"),
            notes=self._optional_text(data, "notes"),
        )

    def _import_row(self, data: dict[str, Any]) -> InventoryImportRowCommand:
        if not isinstance(data, dict):
            raise ValidationError("Import rows must be JSON objects.")
        return InventoryImportRowCommand(
            row_number=self._required_int(data, "row_number"),
            status_code=self._optional_text(data, "status_code") or "valid",
            normalized_json=self._json_text(data.get("normalized_json")),
            error_messages_json=self._json_text(data.get("error_messages_json")),
        )

    @staticmethod
    def _json_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _optional_text(data: dict[str, Any], key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _required_text(self, data: dict[str, Any], key: str) -> str:
        value = self._optional_text(data, key)
        if value is None:
            raise ValidationError(f"'{key}' is required.")
        return value

    @staticmethod
    def _optional_int(data: dict[str, Any], key: str) -> int | None:
        value = data.get(key)
        if value is None or value == "":
            return None
        return int(value)

    def _required_int(self, data: dict[str, Any], key: str) -> int:
        value = self._optional_int(data, key)
        if value is None:
            raise ValidationError(f"'{key}' is required.")
        return value

    @staticmethod
    def _optional_decimal(data: dict[str, Any], key: str) -> Decimal | None:
        value = data.get(key)
        if value is None or value == "":
            return None
        return Decimal(str(value))

    def _required_decimal(self, data: dict[str, Any], key: str) -> Decimal:
        value = self._optional_decimal(data, key)
        if value is None:
            raise ValidationError(f"'{key}' is required.")
        return value

    @staticmethod
    def _optional_date(data: dict[str, Any], key: str) -> date | None:
        value = data.get(key)
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    def _required_date(self, data: dict[str, Any], key: str) -> date:
        value = self._optional_date(data, key)
        if value is None:
            raise ValidationError(f"'{key}' is required.")
        return value

    def _update_actions(self) -> None:
        has_company = self._active_company() is not None
        for button in self._action_buttons:
            button.setEnabled(has_company)
        self._build_post_button.setEnabled(has_company and self._selected_production_order_id() is not None)

    def _clear_models(self) -> None:
        for model in (self._variant_model, self._bom_model, self._count_model, self._import_model, self._production_model):
            model.removeRows(0, model.rowCount())
        self._bom_ids = []
        self._count_plan_ids = []
        self._import_ids = []
        self._production_ids = []

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    @staticmethod
    def _item(value, user_data=None) -> QStandardItem:
        item = QStandardItem("" if value is None else str(value))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _numeric(value) -> QStandardItem:
        if isinstance(value, Decimal):
            text = f"{value:,.4f}".rstrip("0").rstrip(".")
        else:
            text = "" if value is None else f"{value:,}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    @staticmethod
    def _append_message_row(model: QStandardItemModel, column_count: int, message: str) -> None:
        row = [InventoryOperationsPage._item(message)]
        row.extend(InventoryOperationsPage._item("") for _ in range(column_count - 1))
        model.appendRow(row)
