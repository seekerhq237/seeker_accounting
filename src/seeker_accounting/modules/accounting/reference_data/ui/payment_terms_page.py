from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import PaymentTermListItemDTO
from seeker_accounting.modules.accounting.reference_data.ui.payment_term_dialog import PaymentTermDialog
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class PaymentTermsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._payment_terms: list[PaymentTermListItemDTO] = []

        self.setObjectName("PaymentTermsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )

        self.reload_payment_terms()

    def reload_payment_terms(self, selected_payment_term_id: int | None = None) -> None:
        if not self._service_registry.permission_service.has_permission("reference.payment_terms.view"):
            self._payment_terms = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Access denied")
            self._stack.setCurrentWidget(self._access_denied_state)
            self._update_action_state()
            return

        active_company = self._active_company()

        if active_company is None:
            self._payment_terms = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._payment_terms = self._service_registry.reference_data_service.list_payment_terms(
                active_company.company_id
            )
        except Exception as exc:
            self._payment_terms = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Payment Terms", f"Payment terms could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_payment_term_id)
        self._update_action_state()

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Payment Terms", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)

        self._new_button = QPushButton("New Payment Term", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Payment Term", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._deactivate_button = QPushButton("Deactivate", card)
        self._deactivate_button.setProperty("variant", "secondary")
        self._deactivate_button.clicked.connect(self._deactivate_selected_payment_term)
        layout.addWidget(self._deactivate_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_payment_terms())
        layout.addWidget(self._refresh_button)
        return card

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_active_company_state = self._build_no_active_company_state()
        self._access_denied_state = self._build_access_denied_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_active_company_state)
        self._stack.addWidget(self._access_denied_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(card)
        self._table.setObjectName("PaymentTermsTable")
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(("Code", "Name", "Days Due", "Status"))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No payment terms yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first term for the active company so invoices and bills can use a consistent due-rule reference.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Payment Term", actions)
        create_button.setProperty("variant", "primary")
        create_button.clicked.connect(self._open_create_dialog)
        actions_layout.addWidget(create_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    def _build_no_active_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Payment terms are company-scoped. Choose the active company from the shell or jump back to Companies if one still needs to be created.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        companies_button = QPushButton("Open Companies", actions)
        companies_button.setProperty("variant", "secondary")
        companies_button.clicked.connect(self._open_companies_workspace)
        actions_layout.addWidget(companies_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    def _build_access_denied_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        title = QLabel("Access denied", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "You do not have permission to view payment terms. Contact your administrator to request access.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        layout.addStretch(1)
        return card

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._payment_terms:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for payment_term in self._payment_terms:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)

            values = (
                payment_term.code,
                payment_term.name,
                str(payment_term.days_due),
                "Active" if payment_term.is_active else "Inactive",
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, payment_term.id)
                if column_index in {2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, column_index, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._payment_terms)
        self._record_count_label.setText(f"{count} payment term" if count == 1 else f"{count} payment terms")

    def _restore_selection(self, selected_payment_term_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return

        if selected_payment_term_id is None:
            self._table.selectRow(0)
            return

        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_payment_term_id:
                self._table.selectRow(row_index)
                return

        self._table.selectRow(0)

    def _selected_payment_term(self) -> PaymentTermListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None

        item = self._table.item(current_row, 0)
        if item is None:
            return None

        payment_term_id = item.data(Qt.ItemDataRole.UserRole)
        for payment_term in self._payment_terms:
            if payment_term.id == payment_term_id:
                return payment_term
        return None

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Payment Terms",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected_payment_term = self._selected_payment_term()
        has_active_company = active_company is not None
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_active_company and permission_service.has_permission("reference.payment_terms.create")
        )
        self._edit_button.setEnabled(
            selected_payment_term is not None
            and has_active_company
            and permission_service.has_permission("reference.payment_terms.edit")
        )
        self._deactivate_button.setEnabled(
            selected_payment_term is not None
            and has_active_company
            and selected_payment_term.is_active
            and permission_service.has_permission("reference.payment_terms.deactivate")
        )

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.payment_terms.create"):
            self._show_permission_denied("reference.payment_terms.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Payment Terms", "Select an active company before creating payment terms.")
            return

        payment_term = PaymentTermDialog.create_payment_term(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if payment_term is None:
            return
        self.reload_payment_terms(selected_payment_term_id=payment_term.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.payment_terms.edit"):
            self._show_permission_denied("reference.payment_terms.edit")
            return
        active_company = self._active_company()
        payment_term = self._selected_payment_term()
        if active_company is None or payment_term is None:
            show_info(self, "Payment Terms", "Select a payment term to edit.")
            return

        updated_payment_term = PaymentTermDialog.edit_payment_term(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            payment_term_id=payment_term.id,
            parent=self,
        )
        if updated_payment_term is None:
            return
        self.reload_payment_terms(selected_payment_term_id=updated_payment_term.id)

    def _deactivate_selected_payment_term(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.payment_terms.deactivate"):
            self._show_permission_denied("reference.payment_terms.deactivate")
            return
        active_company = self._active_company()
        payment_term = self._selected_payment_term()
        if active_company is None or payment_term is None:
            show_info(self, "Payment Terms", "Select a payment term to deactivate.")
            return
        if not payment_term.is_active:
            show_info(self, "Payment Terms", "The selected payment term is already inactive.")
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Payment Term",
            f"Deactivate payment term '{payment_term.name}' ({payment_term.code}) for {active_company.company_name}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.reference_data_service.deactivate_payment_term(
                active_company.company_id,
                payment_term.id,
            )
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Payment Terms", str(exc))
            self.reload_payment_terms()
            return

        self.reload_payment_terms(selected_payment_term_id=payment_term.id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _handle_item_double_clicked(self, *_args: object) -> None:
        self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_payment_terms()
