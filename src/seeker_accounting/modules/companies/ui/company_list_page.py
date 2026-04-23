from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from seeker_accounting.modules.companies.dto.company_dto import CompanyListItemDTO
from seeker_accounting.modules.companies.ui.company_form_dialog import CompanyFormDialog
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


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
            self._table.setRowCount(0)
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
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        self._table = QTableWidget(self._table_surface)
        self._table.setObjectName("CompanyListTable")
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ("Display Name", "Legal Name", "Country", "Base Currency", "Status", "Updated")
        )
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
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
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for company in self._companies:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)

            values = (
                company.display_name,
                company.legal_name,
                company.country_code,
                company.base_currency_code,
                "Active" if company.is_active else "Inactive",
                self._format_timestamp(company.updated_at),
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, company.id)
                if column_index == 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, column_index, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        self._table.setSortingEnabled(True)
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
            if self._table.rowCount() > 0:
                self._table.selectRow(0)
            return

        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == company_id:
                self._table.selectRow(row_index)
                return

        if self._table.rowCount() > 0:
            self._table.selectRow(0)

    def _selected_company(self) -> CompanyListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None

        item = self._table.item(current_row, 0)
        if item is None:
            return None

        company_id = item.data(Qt.ItemDataRole.UserRole)
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

    def _handle_item_double_clicked(self, *_args: object) -> None:
        self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self._update_action_state()
