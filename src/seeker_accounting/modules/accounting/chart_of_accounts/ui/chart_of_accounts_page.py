from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountListItemDTO
from seeker_accounting.modules.accounting.chart_of_accounts.dto.chart_import_dto import (
    ChartImportResultDTO,
    ChartSeedResultDTO,
)
from seeker_accounting.modules.accounting.chart_of_accounts.ui.account_form_dialog import (
    AccountFormDialog,
)
from seeker_accounting.modules.accounting.chart_of_accounts.ui.chart_import_dialog import (
    ChartImportDialog,
)
from seeker_accounting.modules.accounting.chart_of_accounts.ui.chart_customization_wizard_dialog import (
    ChartCustomizationWizardDialog,
)
from seeker_accounting.modules.accounting.reference_data.ui.account_role_mapping_dialog import (
    AccountRoleMappingDialog,
)
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.register import RegisterPage


class ChartOfAccountsPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._accounts: list[AccountListItemDTO] = []
        self._accounts_by_id: dict[int, AccountListItemDTO] = {}

        self.setObjectName("ChartOfAccountsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        self._populate_action_band(self._register)
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._search_edit.textChanged.connect(self._apply_search_filter)

        self.reload_accounts()

    def reload_accounts(self, selected_account_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._accounts = []
            self._accounts_by_id = {}
            self._tree.clear()
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._accounts = self._service_registry.chart_of_accounts_service.list_accounts(
                active_company.company_id,
                active_only=False,
            )
        except Exception as exc:
            self._accounts = []
            self._accounts_by_id = {}
            self._tree.clear()
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Chart of Accounts", f"Chart data could not be loaded.\n\n{exc}")
            return

        self._accounts_by_id = {account.id: account for account in self._accounts}
        self._populate_tree()
        self._sync_surface_state(active_company)
        self._apply_search_filter()
        self._restore_selection(selected_account_id)
        self._update_action_state()

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._search_edit = QLineEdit(register.toolbar_strip)
        self._search_edit.setPlaceholderText("Search code, name, class, type, or parent…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(280)
        strip_layout.addWidget(self._search_edit)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_accounts())
        strip_layout.addWidget(self._refresh_button)

    def _populate_action_band(self, register: RegisterPage) -> None:
        band_layout = register.action_band_layout

        self._new_button = QPushButton("New Account", register.action_band)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        band_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Account", register.action_band)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        band_layout.addWidget(self._edit_button)

        self._deactivate_button = QPushButton("Deactivate", register.action_band)
        self._deactivate_button.setProperty("variant", "secondary")
        self._deactivate_button.clicked.connect(self._deactivate_selected_account)
        band_layout.addWidget(self._deactivate_button)

        self._wizard_button = QPushButton("Customize Chart", register.action_band)
        self._wizard_button.setProperty("variant", "primary")
        self._wizard_button.clicked.connect(self._open_customization_wizard)
        band_layout.addWidget(self._wizard_button)

        self._seed_button = QPushButton("Seed OHADA Chart", register.action_band)
        self._seed_button.setProperty("variant", "secondary")
        self._seed_button.clicked.connect(self._seed_built_in_chart)
        band_layout.addWidget(self._seed_button)

        self._import_button = QPushButton("Import Template", register.action_band)
        self._import_button.setProperty("variant", "secondary")
        self._import_button.clicked.connect(self._open_import_dialog)
        band_layout.addWidget(self._import_button)

        self._role_mappings_button = QPushButton("Role Mappings", register.action_band)
        self._role_mappings_button.setProperty("variant", "secondary")
        self._role_mappings_button.clicked.connect(self._open_role_mapping_dialog)
        band_layout.addWidget(self._role_mappings_button)

        band_layout.addStretch(1)

        self._export_list_button = QPushButton("Export List", register.action_band)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._print_account_list)
        band_layout.addWidget(self._export_list_button)

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._tree_surface = self._build_tree_surface()
        self._empty_state = self._build_empty_state()
        self._no_active_company_state = self._build_no_active_company_state()
        self._stack.addWidget(self._tree_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_active_company_state)
        return self._stack

    def _build_tree_surface(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tree = QTreeWidget(container)
        self._tree.setObjectName("ChartOfAccountsTree")
        self._tree.setColumnCount(9)
        self._tree.setHeaderLabels(
            (
                "Account Code",
                "Account Name",
                "Class",
                "Type",
                "Normal Balance",
                "Parent",
                "Manual Posting",
                "Control",
                "Status",
            )
        )
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setAllColumnsShowFocus(True)
        self._tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setWordWrap(False)
        self._tree.setIndentation(14)
        self._tree.setTabKeyNavigation(False)
        from seeker_accounting.shared.ui.table_helpers import _NoCellFocusDelegate
        self._tree.setItemDelegate(_NoCellFocusDelegate(self._tree))
        self._tree.setSortingEnabled(False)
        self._tree.itemSelectionChanged.connect(self._update_action_state)
        self._tree.itemDoubleClicked.connect(self._handle_item_double_clicked)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setColumnWidth(1, 380)

        layout.addWidget(self._tree)
        return container

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No accounts yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Start with a built-in OHADA seed, preview an import, or create the first account manually if the company chart is being curated from scratch.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        wizard_button = QPushButton("Customize Chart", actions)
        wizard_button.setProperty("variant", "primary")
        wizard_button.clicked.connect(self._open_customization_wizard)
        actions_layout.addWidget(wizard_button, 0, Qt.AlignmentFlag.AlignLeft)

        seed_button = QPushButton("Seed Built-In OHADA Chart", actions)
        seed_button.setProperty("variant", "secondary")
        seed_button.clicked.connect(self._seed_built_in_chart)
        actions_layout.addWidget(seed_button, 0, Qt.AlignmentFlag.AlignLeft)

        import_button = QPushButton("Import Chart Template", actions)
        import_button.setProperty("variant", "secondary")
        import_button.clicked.connect(self._open_import_dialog)
        actions_layout.addWidget(import_button, 0, Qt.AlignmentFlag.AlignLeft)

        create_button = QPushButton("Create First Account", actions)
        create_button.setProperty("variant", "secondary")
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
            "The chart of accounts is company-scoped. Choose the active company from the shell or return to Companies if setup still needs to be completed first.",
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

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._accounts:
            self._stack.setCurrentWidget(self._tree_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_tree(self) -> None:
        self._tree.setUpdatesEnabled(False)
        self._tree.clear()

        children_by_parent_id: dict[int | None, list[AccountListItemDTO]] = defaultdict(list)
        for account in self._accounts:
            children_by_parent_id[account.parent_account_id].append(account)

        for children in children_by_parent_id.values():
            children.sort(key=lambda row: (row.account_code, row.id))

        def build_item(account: AccountListItemDTO, parent_item: QTreeWidgetItem | None = None) -> None:
            values = (
                account.account_code,
                account.account_name,
                f"{account.account_class_code}  {account.account_class_name}",
                f"{account.account_type_code}  {account.account_type_name}",
                account.normal_balance.title(),
                self._parent_label(account),
                "Yes" if account.allow_manual_posting else "No",
                "Yes" if account.is_control_account else "No",
                "Active" if account.is_active else "Inactive",
            )
            item = QTreeWidgetItem(values)
            item.setData(0, Qt.ItemDataRole.UserRole, account.id)
            for column_index in (4, 6, 7, 8):
                item.setTextAlignment(column_index, Qt.AlignmentFlag.AlignCenter)

            if parent_item is None:
                self._tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            for child in children_by_parent_id.get(account.id, []):
                build_item(child, item)

        for root_account in children_by_parent_id.get(None, []):
            build_item(root_account)

        self._tree.collapseAll()
        self._tree.expandToDepth(0)
        self._tree.setUpdatesEnabled(True)

    def _parent_label(self, account: AccountListItemDTO) -> str:
        if account.parent_account_code is None:
            return ""
        if account.parent_account_name is None:
            return account.parent_account_code
        return f"{account.parent_account_code}  {account.parent_account_name}"

    def _apply_search_filter(self) -> None:
        query = self._search_edit.text().strip().lower()
        visible_count = 0

        def filter_item(item: QTreeWidgetItem) -> bool:
            nonlocal visible_count
            matches = not query or any(query in item.text(column).lower() for column in range(self._tree.columnCount()))
            child_matches = False
            for child_index in range(item.childCount()):
                child_matches = filter_item(item.child(child_index)) or child_matches

            is_visible = matches or child_matches
            item.setHidden(not is_visible)
            if is_visible:
                visible_count += 1
            if query:
                item.setExpanded(child_matches)
            return is_visible

        for root_index in range(self._tree.topLevelItemCount()):
            filter_item(self._tree.topLevelItem(root_index))

        if not query:
            self._tree.collapseAll()
            self._tree.expandToDepth(0)

        total_count = len(self._accounts)
        if query:
            self._record_count_label.setText(f"{visible_count} shown of {total_count} accounts")
        else:
            self._record_count_label.setText(
                f"{total_count} account" if total_count == 1 else f"{total_count} accounts"
            )

        current_item = self._tree.currentItem()
        if current_item is not None and current_item.isHidden():
            replacement_item = self._first_visible_item()
            if replacement_item is None:
                self._tree.clearSelection()
            else:
                self._tree.setCurrentItem(replacement_item)
                self._expand_item_path(replacement_item)

        self._update_action_state()

    def _restore_selection(self, selected_account_id: int | None) -> None:
        if self._tree.topLevelItemCount() == 0:
            return

        if selected_account_id is not None:
            item = self._find_item_by_account_id(selected_account_id)
            if item is not None and not item.isHidden():
                self._tree.setCurrentItem(item)
                self._expand_item_path(item)
                return

        first_visible_item = self._first_visible_item()
        if first_visible_item is not None:
            self._tree.setCurrentItem(first_visible_item)
            self._expand_item_path(first_visible_item)

    def _find_item_by_account_id(self, account_id: int) -> QTreeWidgetItem | None:
        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, Qt.ItemDataRole.UserRole) == account_id:
                return item
            for child_index in range(item.childCount()):
                result = walk(item.child(child_index))
                if result is not None:
                    return result
            return None

        for root_index in range(self._tree.topLevelItemCount()):
            result = walk(self._tree.topLevelItem(root_index))
            if result is not None:
                return result
        return None

    def _first_visible_item(self) -> QTreeWidgetItem | None:
        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if not item.isHidden():
                return item
            for child_index in range(item.childCount()):
                result = walk(item.child(child_index))
                if result is not None:
                    return result
            return None

        for root_index in range(self._tree.topLevelItemCount()):
            result = walk(self._tree.topLevelItem(root_index))
            if result is not None:
                return result
        return None

    def _expand_item_path(self, item: QTreeWidgetItem) -> None:
        current_item = item.parent()
        while current_item is not None:
            current_item.setExpanded(True)
            current_item = current_item.parent()

    def _selected_account(self) -> AccountListItemDTO | None:
        current_item = self._tree.currentItem()
        if current_item is None or current_item.isHidden():
            return None
        account_id = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(account_id, int):
            return None
        return self._accounts_by_id.get(account_id)

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Chart of Accounts",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected_account = self._selected_account()
        has_active_company = active_company is not None
        has_accounts = bool(self._accounts)
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_active_company and permission_service.has_permission("chart.accounts.create")
        )
        self._edit_button.setEnabled(
            selected_account is not None
            and has_active_company
            and permission_service.has_permission("chart.accounts.edit")
        )
        self._deactivate_button.setEnabled(
            selected_account is not None
            and has_active_company
            and selected_account.is_active
            and permission_service.has_permission("chart.accounts.deactivate")
        )
        self._wizard_button.setEnabled(has_active_company)
        self._seed_button.setEnabled(
            has_active_company and permission_service.has_permission("chart.seed")
        )
        self._import_button.setEnabled(
            has_active_company and permission_service.has_permission("chart.import")
        )
        self._role_mappings_button.setEnabled(
            has_active_company
            and has_accounts
            and permission_service.has_any_permission(
                (
                    "reference.account_role_mappings.view",
                    "reference.account_role_mappings.manage",
                    "chart.role_mappings.view",
                    "chart.role_mappings.manage",
                )
            )
        )
        self._export_list_button.setEnabled(has_active_company and has_accounts)
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self):
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_handlers
        return {
            "chart_of_accounts.new": self._open_create_dialog,
            "chart_of_accounts.edit": self._open_edit_dialog,
            "chart_of_accounts.deactivate": self._deactivate_selected_account,
            "chart_of_accounts.wizard": self._open_customization_wizard,
            "chart_of_accounts.seed": self._seed_built_in_chart,
            "chart_of_accounts.import": self._open_import_dialog,
            "chart_of_accounts.role_mappings": self._open_role_mapping_dialog,
            "chart_of_accounts.refresh": self.reload_accounts,
            "chart_of_accounts.export_list": self._print_account_list,
            **related_goto_handlers(self._service_registry, "chart_of_accounts"),
        }

    def ribbon_state(self):
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_state
        return {
            "chart_of_accounts.new": self._new_button.isEnabled(),
            "chart_of_accounts.edit": self._edit_button.isEnabled(),
            "chart_of_accounts.deactivate": self._deactivate_button.isEnabled(),
            "chart_of_accounts.wizard": self._wizard_button.isEnabled(),
            "chart_of_accounts.seed": self._seed_button.isEnabled(),
            "chart_of_accounts.import": self._import_button.isEnabled(),
            "chart_of_accounts.role_mappings": self._role_mappings_button.isEnabled(),
            "chart_of_accounts.refresh": True,
            "chart_of_accounts.export_list": self._export_list_button.isEnabled(),
            **related_goto_state("chart_of_accounts"),
        }

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("chart.accounts.create"):
            self._show_permission_denied("chart.accounts.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Chart of Accounts", "Select an active company before creating accounts.")
            return

        account = AccountFormDialog.create_account(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if account is None:
            return
        self.reload_accounts(selected_account_id=account.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("chart.accounts.edit"):
            self._show_permission_denied("chart.accounts.edit")
            return
        active_company = self._active_company()
        account = self._selected_account()
        if active_company is None or account is None:
            show_info(self, "Chart of Accounts", "Select an account to edit.")
            return

        updated_account = AccountFormDialog.edit_account(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            account_id=account.id,
            parent=self,
        )
        if updated_account is None:
            return
        self.reload_accounts(selected_account_id=updated_account.id)

    def _deactivate_selected_account(self) -> None:
        if not self._service_registry.permission_service.has_permission("chart.accounts.deactivate"):
            self._show_permission_denied("chart.accounts.deactivate")
            return
        active_company = self._active_company()
        account = self._selected_account()
        if active_company is None or account is None:
            show_info(self, "Chart of Accounts", "Select an account to deactivate.")
            return
        if not account.is_active:
            show_info(self, "Chart of Accounts", "The selected account is already inactive.")
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Account",
            f"Deactivate account '{account.account_name}' ({account.account_code}) for {active_company.company_name}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.chart_of_accounts_service.deactivate_account(
                active_company.company_id,
                account.id,
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Chart of Accounts", str(exc))
            self.reload_accounts(selected_account_id=account.id)
            return

        self.reload_accounts(selected_account_id=account.id)

    def _open_customization_wizard(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Chart of Accounts", "Select an active company before opening the chart wizard.")
            return

        result = ChartCustomizationWizardDialog.customize_chart(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is None:
            return

        self.reload_accounts()
        show_info(self, "Chart of Accounts", result.summary)

    def _seed_built_in_chart(self) -> None:
        if not self._service_registry.permission_service.has_permission("chart.seed"):
            self._show_permission_denied("chart.seed")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Chart of Accounts", "Select an active company before seeding the chart.")
            return

        choice = QMessageBox.question(
            self,
            "Seed Built-In OHADA Chart",
            (
                f"Seed the built-in OHADA chart template into {active_company.company_name}?\n\n"
                "Only missing accounts will be added. Existing company accounts will not be overwritten."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._service_registry.chart_seed_service.seed_built_in_chart(
                active_company.company_id
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            show_error(self, "Chart of Accounts", str(exc))
            return

        self.reload_accounts()
        show_info(self, "Chart of Accounts", self._format_seed_result(result))

    def _open_import_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("chart.import"):
            self._show_permission_denied("chart.import")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Chart of Accounts", "Select an active company before importing a chart.")
            return

        result = ChartImportDialog.import_chart_template(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is None:
            return

        self.reload_accounts()
        show_info(self, "Chart of Accounts", self._format_import_result(result))

    def _open_role_mapping_dialog(self) -> None:
        if not self._service_registry.permission_service.has_any_permission(
            (
                "reference.account_role_mappings.view",
                "reference.account_role_mappings.manage",
                "chart.role_mappings.view",
                "chart.role_mappings.manage",
            )
        ):
            self._show_permission_denied("reference.account_role_mappings.view")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Chart of Accounts", "Select an active company before managing account role mappings.")
            return

        AccountRoleMappingDialog.manage_mappings(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _format_seed_result(self, result: ChartSeedResultDTO) -> str:
        lines = [
            f"Template: {result.template_code}",
            f"Imported: {result.imported_count}",
            f"Skipped existing: {result.skipped_existing_count}",
            f"Conflicts: {result.conflict_count}",
            f"Duplicate source rows: {result.duplicate_source_count}",
            f"Invalid rows: {result.invalid_row_count}",
        ]
        if result.messages:
            lines.extend(["", "Notes:"])
            lines.extend(f"- {message}" for message in result.messages)
        return "\n".join(lines)

    def _format_import_result(self, result: ChartImportResultDTO) -> str:
        lines = [
            f"Source: {result.source_label}",
            f"Template code: {result.template_code or 'external_import'}",
            f"Imported: {result.imported_count}",
            f"Skipped existing: {result.skipped_existing_count}",
            f"Conflicts: {result.conflict_count}",
            f"Duplicate source rows: {result.duplicate_source_count}",
            f"Invalid rows: {result.invalid_row_count}",
            "",
            "Mode: Add missing accounts only",
        ]
        if result.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"- {warning}" for warning in result.warnings)
        return "\n".join(lines)

    def _handle_item_double_clicked(self, *_args: object) -> None:
        account = self._selected_account()
        if account is None:
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.ACCOUNT_DETAIL,
            context={"account_id": account.id},
        )

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_accounts()

    # ------------------------------------------------------------------
    # Print / export
    # ------------------------------------------------------------------

    def _print_account_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._accounts:
            return
        result = PrintExportDialog.show_dialog(self, "Chart of Accounts")
        if result is None:
            return
        try:
            self._service_registry.chart_of_accounts_print_service.print_account_list(
                active_company.company_id, self._accounts, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Chart of Accounts", f"Export failed.\n\n{exc}")
