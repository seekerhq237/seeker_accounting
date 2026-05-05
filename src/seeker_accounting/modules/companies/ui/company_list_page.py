from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_dto import CompanyListItemDTO
from seeker_accounting.modules.companies.ui.company_form_dialog import CompanyFormDialog
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, apply_status_chip_to_column
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


class CompanyListPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._companies: list[CompanyListItemDTO] = []

        self.setObjectName("CompanyListPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_table_surface(), 1)
        root_layout.addWidget(self._build_empty_state())

        self._service_registry.active_company_context.active_company_changed.connect(self._handle_active_company_changed)

        self.reload_companies()

    def reload_companies(self, selected_company_id: int | None = None) -> None:
        try:
            self._companies = self._service_registry.company_service.list_companies()
        except Exception as exc:
            self._companies = []
            self._model.removeRows(0, self._model.rowCount())
            self._table_surface.hide()
            self._empty_state.show()
            self._update_action_state()
            show_error(self, "Companies", f"Company data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state()
        self._restore_selection(selected_company_id)
        self._update_action_state()

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel('Company Directory', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)
        self._new_button = QPushButton("New Company", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Company", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_companies())
        layout.addWidget(self._refresh_button)
        return card

    def _build_table_surface(self) -> QWidget:
        self._table_surface = QFrame(self)
        self._table_surface.setObjectName("PageCard")

        layout = QVBoxLayout(self._table_surface)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = QStandardItemModel(0, 6, self._table_surface)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="display_name", title="Display Name"),
                DataTableColumn(key="legal_name", title="Legal Name"),
                DataTableColumn(key="country", title="Country"),
                DataTableColumn(key="currency", title="Base Currency"),
                DataTableColumn(key="status", title="Status"),
                DataTableColumn(key="updated", title="Updated"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=self._table_surface,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 4)
        self._table.selection_changed.connect(lambda _: self._update_action_state())
        self._table.view().doubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self._table)
        return self._table_surface

    def _build_empty_state(self) -> QWidget:
        self._empty_state = QFrame(self)
        self._empty_state.setObjectName("PageCard")

        layout = QVBoxLayout(self._empty_state)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No companies yet", self._empty_state)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first company to unlock a working operating context in the shell. The page will then keep creation, editing, and active-company switching in one compact workspace.",
            self._empty_state,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(self._empty_state)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create First Company", actions)
        create_button.setProperty("variant", "primary")
        create_button.clicked.connect(self._open_create_dialog)
        actions_layout.addWidget(create_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)
        layout.addWidget(actions)
        layout.addStretch(1)
        return self._empty_state

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())

        for company in self._companies:
            status_text = "active" if company.is_active else "inactive"
            self._model.appendRow([
                self._make_item(company.display_name, user_data=company.id),
                self._make_item(company.legal_name),
                self._make_item(company.country_code),
                self._make_item(company.base_currency_code),
                self._make_item(status_text),
                self._make_item(self._format_timestamp(company.updated_at)),
            ])

        count = len(self._companies)
        self._record_count_label.setText(f"{count} company" if count == 1 else f"{count} companies")

    def _sync_surface_state(self) -> None:
        has_companies = bool(self._companies)
        self._table_surface.setVisible(has_companies)
        self._empty_state.setVisible(not has_companies)

    def _restore_selection(self, selected_company_id: int | None) -> None:
        company_id = selected_company_id
        if company_id is None:
            active_company = self._service_registry.company_context_service.get_active_company()
            if active_company is not None:
                company_id = active_company.company_id

        if company_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, c in enumerate(self._companies) if c.id == company_id), 0
            )

        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._table.view().selectionModel()
        if sm is None:
            return
        sm.select(proxy_index, sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows)
        self._table.view().scrollTo(proxy_index)

    def _selected_company(self) -> CompanyListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        id_item = self._model.item(rows[0], 0)
        if id_item is None:
            return None
        company_id = id_item.data(Qt.ItemDataRole.UserRole)
        for company in self._companies:
            if company.id == company_id:
                return company
        return None

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Companies",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        selected_company = self._selected_company()
        permission_service = self._service_registry.permission_service
        self._new_button.setEnabled(permission_service.has_permission("companies.create"))
        self._edit_button.setEnabled(
            selected_company is not None and permission_service.has_permission("companies.edit")
        )

    def _format_timestamp(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("companies.create"):
            self._show_permission_denied("companies.create")
            return
        company = CompanyFormDialog.create_company(self._service_registry, parent=self)
        if company is None:
            return
        self.reload_companies(selected_company_id=company.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("companies.edit"):
            self._show_permission_denied("companies.edit")
            return
        company = self._selected_company()
        if company is None:
            show_info(self, "Companies", "Select a company to edit.")
            return

        updated_company = CompanyFormDialog.edit_company(self._service_registry, company.id, self)
        if updated_company is None:
            return
        self.reload_companies(selected_company_id=updated_company.id)

    def _on_double_clicked(self, _index) -> None:
        self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self._update_action_state()
