from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO, CompanyListItemDTO
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, apply_status_chip_to_column


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
        apply_window_size(self, "modules.companies.ui.company.selector.dialog.0")

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

        self._company_model = QStandardItemModel(0, 5, card)
        self._company_model.setHorizontalHeaderLabels(
            ["Display Name", "Legal Name", "Country", "Currency", "Status"]
        )
        self._company_table = DataTable(
            columns=(
                DataTableColumn(key="display_name", title="Display Name"),
                DataTableColumn(key="legal_name", title="Legal Name"),
                DataTableColumn(key="country", title="Country"),
                DataTableColumn(key="currency", title="Currency"),
                DataTableColumn(key="status", title="Status"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._company_table.set_model(self._company_model)
        apply_status_chip_to_column(self._company_table.view(), 4)
        self._company_table.selection_changed.connect(lambda _rows: self._update_selection_state())
        self._company_table.view().doubleClicked.connect(self._handle_item_double_click)
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

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self, active_company: ActiveCompanyDTO | None) -> None:
        self._company_model.removeRows(0, self._company_model.rowCount())
        for company in self._companies:
            display_name_text = company.display_name
            if active_company is not None and active_company.company_id == company.id:
                display_name_text = f"{display_name_text}  (Current)"
            self._company_model.appendRow([
                self._make_item(display_name_text, user_data=company.id),
                self._make_item(company.legal_name),
                self._make_item(company.country_code),
                self._make_item(company.base_currency_code),
                self._make_item("active" if company.is_active else "inactive"),
            ])

    def _select_initial_row(self, active_company: ActiveCompanyDTO | None) -> None:
        preferred_company_id = self._initial_company_id
        if preferred_company_id is None and active_company is not None:
            preferred_company_id = active_company.company_id
        if preferred_company_id is None:
            if self._company_model.rowCount() > 0:
                proxy = self._company_table.view().model()
                if proxy:
                    sm = self._company_table.view().selectionModel()
                    if sm:
                        sm.select(
                            proxy.mapFromSource(self._company_model.index(0, 0)),
                            sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows,
                        )
            return
        target_idx = next(
            (i for i, c in enumerate(self._companies) if c.id == preferred_company_id),
            0,
        )
        proxy = self._company_table.view().model()
        if proxy is None:
            return
        src_index = self._company_model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._company_table.view().selectionModel()
        if sm is None:
            return
        sm.select(proxy_index, sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows)
        self._company_table.view().scrollTo(proxy_index)

    def _selected_company(self) -> CompanyListItemDTO | None:
        rows = self._company_table.selected_rows()
        if not rows:
            return None
        row = rows[0]
        if row < 0 or row >= len(self._companies):
            return None
        return self._companies[row]

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
