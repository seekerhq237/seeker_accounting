from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.fixed_assets.ui.asset_category_dialog import AssetCategoryDialog
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error

_METHOD_LABELS = {
    "straight_line": "Straight Line",
    "reducing_balance": "Reducing Balance",
    "sum_of_years_digits": "Sum of Years Digits",
}


CATEGORY_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="code", title="Code"),
    DataTableColumn(key="name", title="Name"),
    DataTableColumn(key="asset_account", title="Asset Account"),
    DataTableColumn(key="accum_account", title="Accum. Depr. Account"),
    DataTableColumn(key="expense_account", title="Depr. Expense Account"),
    DataTableColumn(key="default_life", title="Default Life"),
    DataTableColumn(key="default_method", title="Default Method"),
    DataTableColumn(key="status", title="Status"),
)


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
            self._model.removeRows(0, self._model.rowCount())
            self._count_label.setText("")
            self._stack.setCurrentWidget(self._no_company_state)
            self._update_action_state()
            return
        try:
            self._rows = self._service_registry.asset_category_service.list_asset_categories(
                active_company.company_id
            )
        except Exception as exc:
            self._rows = []
            self._model.removeRows(0, self._model.rowCount())
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Asset Categories", f"Could not load data.\n\n{exc}")
            return
        self._populate()
        self._sync_stack(active_company, self._rows)
        self._update_count_label()
        self._update_action_state()

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Asset Categories",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        company = self._active_company()
        has_company = company is not None
        has_selection = self._selected_row() is not None
        perm = self._service_registry.permission_service
        self._new_btn.setEnabled(has_company and perm.has_permission("assets.categories.create"))
        self._edit_btn.setEnabled(
            has_company and has_selection and perm.has_permission("assets.categories.edit")
        )
        self._deactivate_btn.setEnabled(
            has_company and has_selection and perm.has_permission("assets.categories.deactivate")
        )

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

        self._model = QStandardItemModel(0, len(CATEGORY_COLUMNS), self)
        self._model.setHorizontalHeaderLabels([c.title for c in CATEGORY_COLUMNS])

        self._table = DataTable(
            columns=CATEGORY_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No asset categories to display.",
            parent=card,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 7)
        self._table.selection_changed.connect(lambda _r: self._update_action_state())
        self._table.row_activated.connect(lambda _r: self._on_edit())
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

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _populate(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for row in self._rows:
            life_item = QStandardItem(f"{row.default_useful_life_months} mo")
            life_item.setEditable(False)
            life_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            items = [
                self._make_item(row.code, user_data=row.id),
                self._make_item(row.name),
                self._make_item(f"{row.asset_account_code} — {row.asset_account_name}"),
                self._make_item(
                    f"{row.accumulated_depreciation_account_code} — {row.accumulated_depreciation_account_name}"
                ),
                self._make_item(
                    f"{row.depreciation_expense_account_code} — {row.depreciation_expense_account_name}"
                ),
                life_item,
                self._make_item(
                    _METHOD_LABELS.get(
                        row.default_depreciation_method_code, row.default_depreciation_method_code
                    )
                ),
                self._make_item("active" if row.is_active else "inactive"),
            ]
            self._model.appendRow(items)

    def _update_count_label(self) -> None:
        total = len(self._rows)
        self._count_label.setText(
            f"{total} record" if total == 1 else f"{total} records"
        )

    def _selected_row(self):
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_new(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Asset Categories", "Select an active company first.")
            return
        if not self._service_registry.permission_service.has_permission("assets.categories.create"):
            self._show_permission_denied("assets.categories.create")
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
        row = self._selected_row()
        if row is None:
            return
        if not self._service_registry.permission_service.has_permission("assets.categories.edit"):
            self._show_permission_denied("assets.categories.edit")
            return
        dialog = AssetCategoryDialog(
            self._service_registry, company.company_id, company.company_name,
            category_id=row.id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _on_deactivate(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._selected_row()
        if row is None:
            return
        if not self._service_registry.permission_service.has_permission("assets.categories.deactivate"):
            self._show_permission_denied("assets.categories.deactivate")
            return
        reply = QMessageBox.question(
            self, "Deactivate Category",
            f"Deactivate asset category '{row.code}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.asset_category_service.deactivate_asset_category(
                company.company_id, row.id
            )
        except PermissionDeniedError:
            self._show_permission_denied("assets.categories.deactivate")
            return
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
