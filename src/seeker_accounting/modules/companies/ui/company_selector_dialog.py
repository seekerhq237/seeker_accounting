from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO, CompanyListItemDTO
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class CompanySelectorDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        initial_company_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Select Active Company", parent, help_key="dialog.company_selector")
        self._service_registry = service_registry
        self._initial_company_id = initial_company_id
        self._selected_active_company: ActiveCompanyDTO | None = None
        self._companies: list[CompanyListItemDTO] = []

        self.setObjectName("CompanySelectorDialog")
        self.resize(700, 400)

        summary_label = QLabel(
            "Choose the active operating context for the current session. Only active companies can be selected.",
            self,
        )
        summary_label.setObjectName("PageSummary")
        summary_label.setWordWrap(True)
        self.body_layout.addWidget(summary_label)

        self._current_context_label = QLabel(self)
        self._current_context_label.setObjectName("ToolbarValue")
        self.body_layout.addWidget(self._current_context_label)

        self._stack = QStackedWidget(self)
        self.body_layout.addWidget(self._stack, 1)

        self._table_page = self._build_table_page()
        self._empty_page = self._build_empty_page()
        self._stack.addWidget(self._table_page)
        self._stack.addWidget(self._empty_page)

        self._selection_hint_label = QLabel(self)
        self._selection_hint_label.setObjectName("ToolbarMeta")
        self._selection_hint_label.setWordWrap(True)
        self.body_layout.addWidget(self._selection_hint_label)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.button_box.accepted.connect(self._apply_selection)

        self._confirm_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self._confirm_button is not None:
            self._confirm_button.setText("Set Active Company")
            self._confirm_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._load_companies()

    @property
    def selected_active_company(self) -> ActiveCompanyDTO | None:
        return self._selected_active_company

    @classmethod
    def select_active_company(
        cls,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
        initial_company_id: int | None = None,
    ) -> ActiveCompanyDTO | None:
        dialog = cls(service_registry=service_registry, initial_company_id=initial_company_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_active_company
        return None

    def _build_table_page(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame(container)
        card.setObjectName("PageCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self._company_table = QTableWidget(card)
        self._company_table.setObjectName("CompanySelectorTable")
        self._company_table.setColumnCount(5)
        self._company_table.setHorizontalHeaderLabels(
            ("Display Name", "Legal Name", "Country", "Currency", "Status")
        )
        configure_compact_table(self._company_table)
        self._company_table.setSortingEnabled(False)
        self._company_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._company_table.itemSelectionChanged.connect(self._update_selection_state)
        self._company_table.itemDoubleClicked.connect(self._handle_item_double_click)
        card_layout.addWidget(self._company_table)

        layout.addWidget(card)
        return container

    def _build_empty_page(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        card = QFrame(container)
        card.setObjectName("PageCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(8)

        title = QLabel("No companies available yet", card)
        title.setObjectName("EmptyStateTitle")
        card_layout.addWidget(title)

        summary = QLabel(
            "Return to the landing page and use Create Organisation to register your first company.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        card_layout.addWidget(summary)

        card_layout.addStretch(1)
        layout.addWidget(card)
        return container

    def _load_companies(self) -> None:
        try:
            self._companies = self._service_registry.company_service.list_companies()
        except Exception as exc:
            self._companies = []
            self._stack.setCurrentWidget(self._empty_page)
            self._selection_hint_label.setText("Company data could not be loaded for selection.")
            if self._confirm_button is not None:
                self._confirm_button.setEnabled(False)
            show_error(self, "Companies", str(exc))
            return

        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            self._current_context_label.setText("No active company")
        else:
            self._current_context_label.setText(
                f"Current active company: {active_company.company_name}  |  {active_company.base_currency_code}"
            )

        if not self._companies:
            self._stack.setCurrentWidget(self._empty_page)
            self._selection_hint_label.setText("The shell will show a clean no-company state until one is created.")
            if self._confirm_button is not None:
                self._confirm_button.setEnabled(False)
            return

        self._stack.setCurrentWidget(self._table_page)
        self._populate_table(active_company)
        self._select_initial_row(active_company)
        self._update_selection_state()

    def _populate_table(self, active_company: ActiveCompanyDTO | None) -> None:
        self._company_table.setRowCount(0)
        for company in self._companies:
            row_index = self._company_table.rowCount()
            self._company_table.insertRow(row_index)

            display_name_text = company.display_name
            if active_company is not None and active_company.company_id == company.id:
                display_name_text = f"{display_name_text}  (Current)"

            values = (
                display_name_text,
                company.legal_name,
                company.country_code,
                company.base_currency_code,
                "Active" if company.is_active else "Inactive",
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, company.id)
                if column_index == 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._company_table.setItem(row_index, column_index, item)

        self._company_table.resizeColumnsToContents()
        header = self._company_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)

    def _select_initial_row(self, active_company: ActiveCompanyDTO | None) -> None:
        preferred_company_id = self._initial_company_id
        if preferred_company_id is None and active_company is not None:
            preferred_company_id = active_company.company_id
        if preferred_company_id is None:
            if self._company_table.rowCount() > 0:
                self._company_table.selectRow(0)
            return

        for row_index in range(self._company_table.rowCount()):
            item = self._company_table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == preferred_company_id:
                self._company_table.selectRow(row_index)
                return

        if self._company_table.rowCount() > 0:
            self._company_table.selectRow(0)

    def _selected_company(self) -> CompanyListItemDTO | None:
        current_row = self._company_table.currentRow()
        if current_row < 0 or current_row >= len(self._companies):
            return None

        current_id_item = self._company_table.item(current_row, 0)
        if current_id_item is None:
            return None

        company_id = current_id_item.data(Qt.ItemDataRole.UserRole)
        for company in self._companies:
            if company.id == company_id:
                return company
        return None

    def _update_selection_state(self) -> None:
        company = self._selected_company()
        if company is None:
            self._selection_hint_label.setText("Select a company to set the session context.")
            if self._confirm_button is not None:
                self._confirm_button.setEnabled(False)
            return

        if not company.is_active:
            self._selection_hint_label.setText("This company is inactive and cannot be set as the active context.")
            if self._confirm_button is not None:
                self._confirm_button.setEnabled(False)
            return

        self._selection_hint_label.setText(
            f"Selected company: {company.display_name}  |  {company.country_code}  |  {company.base_currency_code}"
        )
        if self._confirm_button is not None:
            self._confirm_button.setEnabled(True)

    def _handle_item_double_click(self, *_args: object) -> None:
        if self._confirm_button is not None and self._confirm_button.isEnabled():
            self._apply_selection()

    def _apply_selection(self) -> None:
        company = self._selected_company()
        if company is None:
            return

        try:
            self._selected_active_company = self._service_registry.company_context_service.set_active_company(
                company.id,
                user_id=self._service_registry.app_context.current_user_id,
            )
        except (ValidationError, PermissionDeniedError) as exc:
            show_error(self, "Unable To Set Active Company", str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Company Not Found", str(exc))
            self._load_companies()
            return

        self.accept()
