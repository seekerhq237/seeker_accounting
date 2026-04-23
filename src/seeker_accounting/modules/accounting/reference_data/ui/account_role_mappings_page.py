from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountLookupDTO
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    AccountRoleMappingDTO,
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


_RETURN_LABEL_BY_WORKFLOW: dict[str, str] = {
    "sales_invoice": "Return to Sales Invoices",
    "purchase_bill": "Return to Purchase Bills",
    "payroll_run": "Return to Payroll Accounting",
}

_RETURN_NAV_BY_WORKFLOW: dict[str, str] = {
    "sales_invoice": nav_ids.SALES_INVOICES,
    "purchase_bill": nav_ids.PURCHASE_BILLS,
    "payroll_run": nav_ids.PAYROLL_ACCOUNTING,
}


class AccountRoleMappingsPage(RibbonHostMixin, QWidget):
    """Standalone workspace page for Account Role Mappings with guided-flow destination support."""

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._mappings: list[AccountRoleMappingDTO] = []
        self._account_lookup_options: list[AccountLookupDTO] = []
        self._can_manage = self._service_registry.permission_service.has_any_permission(
            ("reference.account_role_mappings.manage", "chart.role_mappings.manage")
        )
        self._role_options = self._service_registry.account_role_mapping_service.list_role_options()
        self._resume_context: dict | None = None

        self._build_ui()
        self._connect_signals()
        self.reload_mappings()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 12, 24, 22)
        root.setSpacing(16)

        # Resume banner (hidden by default)
        self._resume_banner = self._build_resume_banner()
        root.addWidget(self._resume_banner)

        # Error label
        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        root.addWidget(self._error_label)

        # Mapping table
        root.addWidget(self._build_mapping_table())

        # Editor section
        root.addWidget(self._build_editor_section())

        root.addStretch(1)

    def _build_resume_banner(self) -> QFrame:
        banner = QFrame(self)
        banner.setObjectName("ResumeBanner")
        banner.setProperty("card", True)

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        self._resume_banner_label = QLabel("", banner)
        self._resume_banner_label.setObjectName("ResumeBannerLabel")
        self._resume_banner_label.setWordWrap(True)
        layout.addWidget(self._resume_banner_label, 1)

        self._return_button = QPushButton("Return", banner)
        self._return_button.setProperty("variant", "primary")
        self._return_button.clicked.connect(self._return_to_origin)
        layout.addWidget(self._return_button)

        dismiss_btn = QPushButton("Dismiss", banner)
        dismiss_btn.setProperty("variant", "ghost")
        dismiss_btn.clicked.connect(self._dismiss_resume_banner)
        layout.addWidget(dismiss_btn)

        banner.setVisible(False)
        return banner

    def _build_mapping_table(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        table_title = QLabel("Role Mappings", card)
        table_title.setObjectName("InfoCardTitle")
        top_row.addWidget(table_title)
        top_row.addStretch(1)
        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        top_row.addWidget(self._refresh_button)
        layout.addLayout(top_row)

        self._table = QTableWidget(card)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(("Role", "Description", "Mapped Account"))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemDoubleClicked.connect(lambda *_: self._account_combo.setFocus())
        layout.addWidget(self._table)
        return card

    def _build_editor_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        editor_title = QLabel("Selected Role", card)
        editor_title.setObjectName("InfoCardTitle")
        layout.addWidget(editor_title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._role_value = QLabel("Select a role mapping", card)
        self._role_value.setObjectName("ValueLabel")
        grid.addWidget(create_field_block("Role", self._role_value), 0, 0)

        self._description_value = QLabel("", card)
        self._description_value.setObjectName("ToolbarMeta")
        self._description_value.setWordWrap(True)
        grid.addWidget(create_field_block("Description", self._description_value), 0, 1)

        self._account_combo = SearchableComboBox(card)
        grid.addWidget(
            create_field_block(
                "Mapped Account",
                self._account_combo,
                "Only accounts from the active company chart are available.",
            ),
            1, 0, 1, 2,
        )

        layout.addLayout(grid)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        self._save_button = QPushButton("Save Mapping", actions)
        self._save_button.setProperty("variant", "primary")
        actions_layout.addWidget(self._save_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._clear_button = QPushButton("Clear Mapping", actions)
        self._clear_button.setProperty("variant", "secondary")
        actions_layout.addWidget(self._clear_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        return card

    def _connect_signals(self) -> None:
        self._service_registry.active_company_context.active_company_changed.connect(self._on_company_changed)
        self._save_button.clicked.connect(self._save_mapping)
        self._clear_button.clicked.connect(self._clear_mapping)
        self._refresh_button.clicked.connect(lambda: self.reload_mappings())
        self._table.itemSelectionChanged.connect(self._sync_editor_state)

    # ------------------------------------------------------------------
    # Company context
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _on_company_changed(self) -> None:
        self.reload_mappings()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def reload_mappings(self, selected_role_code: str | None = None) -> None:
        active = self._active_company()
        if active is None:
            self._mappings = []
            self._table.setRowCount(0)
            self._sync_editor_state()
            return

        self._load_accounts(active.company_id)

        try:
            self._mappings = self._service_registry.account_role_mapping_service.list_role_mappings(
                active.company_id,
            )
        except Exception as exc:
            self._mappings = []
            self._table.setRowCount(0)
            self._set_error(f"Account role mappings could not be loaded.\n\n{exc}")
            return

        self._set_error(None)
        self._populate_table()
        self._restore_selection(selected_role_code)
        self._sync_editor_state()

    def _load_accounts(self, company_id: int) -> None:
        try:
            self._account_lookup_options = (
                self._service_registry.chart_of_accounts_service.list_account_lookup_options(
                    company_id, active_only=True,
                )
            )
        except Exception as exc:
            self._set_error(f"Accounts could not be loaded.\n\n{exc}")
            return

        self._account_combo.set_items(
            [
                (f"{a.account_code}  {a.account_name}", a.id)
                for a in self._account_lookup_options
            ],
            placeholder="No mapped account",
        )

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        role_options_by_code = {o.role_code: o for o in self._role_options}

        for mapping in self._mappings:
            row = self._table.rowCount()
            self._table.insertRow(row)
            role_option = role_options_by_code.get(mapping.role_code)
            desc = role_option.description if role_option else ""

            values = (
                mapping.role_label,
                desc,
                f"{mapping.account_code}  {mapping.account_name}"
                if mapping.account_id is not None
                else "Unmapped",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, mapping.role_code)
                self._table.setItem(row, col, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Stretch)
        self._table.setSortingEnabled(True)

    def _restore_selection(self, selected_role_code: str | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_role_code is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_role_code:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    # ------------------------------------------------------------------
    # Editor sync
    # ------------------------------------------------------------------

    def _selected_mapping(self) -> AccountRoleMappingDTO | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        role_code = item.data(Qt.ItemDataRole.UserRole)
        return next((m for m in self._mappings if m.role_code == role_code), None)

    def _sync_editor_state(self) -> None:
        mapping = self._selected_mapping()
        if mapping is None:
            self._role_value.setText("Select a role mapping")
            self._description_value.setText("")
            self._account_combo.clear_selection()
            self._save_button.setEnabled(False)
            self._clear_button.setEnabled(False)
            return

        role_option = next(
            (o for o in self._role_options if o.role_code == mapping.role_code), None
        )
        self._role_value.setText(role_option.label if role_option else mapping.role_code)
        self._description_value.setText(role_option.description if role_option else "")
        self._account_combo.set_current_value(mapping.account_id)
        self._save_button.setEnabled(self._can_manage)
        self._clear_button.setEnabled(mapping.account_id is not None and self._can_manage)
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ────────────────────────────────────────────────────

    def _ribbon_commands(self) -> dict:
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_handlers
        return {
            "account_role_mappings.refresh": self.reload_mappings,
            **related_goto_handlers(self._service_registry, "account_role_mappings"),
        }

    def ribbon_state(self) -> dict:
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_state
        return {
            "account_role_mappings.refresh": True,
            **related_goto_state("account_role_mappings"),
        }

    # ------------------------------------------------------------------
    # Save / Clear
    # ------------------------------------------------------------------

    def _save_mapping(self) -> None:
        if not self._can_manage:
            self._set_error(
                self._service_registry.permission_service.build_denied_message(
                    "reference.account_role_mappings.manage"
                )
            )
            return
        mapping = self._selected_mapping()
        if mapping is None:
            return
        account_id = self._account_combo.current_value()
        if not isinstance(account_id, int) or account_id <= 0:
            self._set_error("Select an account before saving, or use Clear Mapping.")
            return
        try:
            updated = self._service_registry.account_role_mapping_service.set_role_mapping(
                self._active_company().company_id,  # type: ignore[union-attr]
                SetAccountRoleMappingCommand(role_code=mapping.role_code, account_id=account_id),
            )
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))
            return
        self.reload_mappings(selected_role_code=updated.role_code)

    def _clear_mapping(self) -> None:
        if not self._can_manage:
            self._set_error(
                self._service_registry.permission_service.build_denied_message(
                    "reference.account_role_mappings.manage"
                )
            )
            return
        mapping = self._selected_mapping()
        if mapping is None:
            return
        try:
            self._service_registry.account_role_mapping_service.clear_role_mapping(
                self._active_company().company_id,  # type: ignore[union-attr]
                mapping.role_code,
            )
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))
            return
        self.reload_mappings(selected_role_code=mapping.role_code)

    # ------------------------------------------------------------------
    # Error display
    # ------------------------------------------------------------------

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    # ------------------------------------------------------------------
    # Guided-flow navigation context (destination behavior)
    # ------------------------------------------------------------------

    def set_navigation_context(self, context: dict) -> None:
        resume_token = context.get("resume_token")
        role_mapping_flow = bool(context.get("role_mapping_flow"))
        role_code = context.get("role_code")
        source_workflow = context.get("source_workflow")

        if not resume_token or not role_mapping_flow:
            self._dismiss_resume_banner()
            return

        self._resume_context = dict(context)

        # Build contextual banner message
        role_label = self._role_label_for_code(role_code) if role_code else None
        if role_label:
            message = (
                f"The \u2018{role_label}\u2019 role mapping is required. "
                "Assign the correct account below, then return to your workflow."
            )
        else:
            message = (
                "A required account role mapping is missing. "
                "Assign the correct account below, then return to your workflow."
            )

        self._resume_banner_label.setText(message)
        return_label = _RETURN_LABEL_BY_WORKFLOW.get(source_workflow or "", "Return to Previous")
        self._return_button.setText(return_label)
        self._resume_banner.setVisible(True)

        # Auto-select the missing role after the page paints
        if role_code:
            QTimer.singleShot(0, lambda: self._focus_role(role_code))

    def _role_label_for_code(self, role_code: str) -> str | None:
        opt = next((o for o in self._role_options if o.role_code == role_code), None)
        return opt.label if opt else None

    def _focus_role(self, role_code: str) -> None:
        """Select and scroll to the row for the given role_code."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == role_code:
                self._table.selectRow(row)
                self._table.scrollToItem(item)
                return

    def _return_to_origin(self) -> None:
        if self._resume_context is None:
            return
        source_workflow = self._resume_context.get("source_workflow", "")
        resume_token = self._resume_context.get("resume_token")
        origin_nav_id = _RETURN_NAV_BY_WORKFLOW.get(source_workflow)
        if origin_nav_id and resume_token:
            self._service_registry.navigation_service.navigate(
                origin_nav_id,
                context={"resume_token": resume_token},
            )
        self._dismiss_resume_banner()

    def _dismiss_resume_banner(self) -> None:
        self._resume_context = None
        self._resume_banner.setVisible(False)
