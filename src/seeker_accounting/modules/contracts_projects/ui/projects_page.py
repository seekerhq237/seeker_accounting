from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.contracts_projects.dto.project_dto import ProjectListItemDTO
from seeker_accounting.modules.contracts_projects.ui.project_cost_code_dialog import ProjectCostCodesDialog
from seeker_accounting.modules.contracts_projects.ui.project_form_dialog import ProjectFormDialog
from seeker_accounting.modules.contracts_projects.ui.project_job_dialog import ProjectJobsDialog
from seeker_accounting.modules.budgeting.ui.budget_version_dialog import BudgetVersionsDialog
from seeker_accounting.modules.job_costing.ui.project_commitment_dialog import ProjectCommitmentsDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class ProjectsPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._projects: list[ProjectListItemDTO] = []

        self.setObjectName("ProjectsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._search_edit.textChanged.connect(self._apply_search_filter)

        self.reload_projects()

    def reload_projects(self, selected_project_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._projects = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._projects = self._service_registry.project_service.list_projects(
                active_company.company_id,
            )
        except Exception as exc:
            self._projects = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Projects", f"Project data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._apply_search_filter()
        self._restore_selection(selected_project_id)
        self._update_action_state()

    # ------------------------------------------------------------------
    # Header and action bar
    # ------------------------------------------------------------------

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Project Directory", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        self._search_edit = QLineEdit(card)
        self._search_edit.setPlaceholderText("Search project code or name")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(220)
        layout.addWidget(self._search_edit)

        layout.addStretch(1)

        self._new_button = QPushButton("New Project", card)
        self._new_button.hide()
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)

        self._edit_button = QPushButton("Edit Project", card)
        self._edit_button.hide()
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)

        self._activate_button = QPushButton("Activate", card)
        self._activate_button.hide()
        self._activate_button.setProperty("variant", "secondary")
        self._activate_button.clicked.connect(self._activate_selected_project)

        self._hold_button = QPushButton("Put On Hold", card)
        self._hold_button.hide()
        self._hold_button.setProperty("variant", "secondary")
        self._hold_button.clicked.connect(self._hold_selected_project)

        self._complete_button = QPushButton("Complete", card)
        self._complete_button.hide()
        self._complete_button.setProperty("variant", "secondary")
        self._complete_button.clicked.connect(self._complete_selected_project)

        self._close_button = QPushButton("Close Project", card)
        self._close_button.hide()
        self._close_button.setProperty("variant", "secondary")
        self._close_button.clicked.connect(self._close_selected_project)

        self._cancel_button = QPushButton("Cancel", card)
        self._cancel_button.hide()
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_project)

        self._jobs_button = QPushButton("Jobs", card)
        self._jobs_button.hide()
        self._jobs_button.setProperty("variant", "secondary")
        self._jobs_button.clicked.connect(self._open_jobs)

        self._cost_codes_button = QPushButton("Cost Codes", card)
        self._cost_codes_button.hide()
        self._cost_codes_button.setProperty("variant", "secondary")
        self._cost_codes_button.clicked.connect(self._open_cost_codes)

        self._budgets_button = QPushButton("Budgets", card)
        self._budgets_button.hide()
        self._budgets_button.setProperty("variant", "secondary")
        self._budgets_button.clicked.connect(self._open_budgets)

        self._commitments_button = QPushButton("Commitments", card)
        self._commitments_button.hide()
        self._commitments_button.setProperty("variant", "secondary")
        self._commitments_button.clicked.connect(self._open_commitments)

        self._open_workspace_button = QPushButton("Open Workspace", card)
        self._open_workspace_button.hide()
        self._open_workspace_button.setProperty("variant", "secondary")
        self._open_workspace_button.clicked.connect(self._open_workspace)

        self._variance_button = QPushButton("Variance", card)
        self._variance_button.hide()
        self._variance_button.setProperty("variant", "secondary")
        self._variance_button.clicked.connect(self._open_variance_analysis)

        self._contract_summary_button = QPushButton("Contract Summary", card)
        self._contract_summary_button.hide()
        self._contract_summary_button.setProperty("variant", "secondary")
        self._contract_summary_button.clicked.connect(self._open_project_contract_summary)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.hide()
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_projects())
        return card

    # ------------------------------------------------------------------
    # Content stack
    # ------------------------------------------------------------------

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_active_company_state = self._build_no_active_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_active_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(card)
        self._table.setObjectName("ProjectsTable")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ("Project Code", "Name", "Contract", "Customer", "Type", "Manager", "Status")
        )
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

        title = QLabel("No projects yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first project for the active company.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Project", actions)
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
            "Projects are company-scoped. Choose the active company from the shell, "
            "or return to Companies if setup still needs to happen first.",
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

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._projects:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    # ------------------------------------------------------------------
    # Table population and search
    # ------------------------------------------------------------------

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for project in self._projects:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (
                project.project_code,
                project.project_name,
                project.contract_number or "",
                project.customer_display_name or "",
                project.project_type_code,
                project.project_manager_display_name or "",
                project.status_code,
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, project.id)
                if column_index in {4, 6}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, column_index, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

    def _apply_search_filter(self) -> None:
        query = self._search_edit.text().strip().lower()
        visible_count = 0
        for row_index in range(self._table.rowCount()):
            matches = not query or any(
                query in (self._table.item(row_index, col).text().lower() if self._table.item(row_index, col) else "")
                for col in range(self._table.columnCount())
            )
            self._table.setRowHidden(row_index, not matches)
            if matches:
                visible_count += 1

        total_count = len(self._projects)
        if query:
            self._record_count_label.setText(f"{visible_count} shown of {total_count} projects")
        else:
            self._record_count_label.setText(
                f"{total_count} project" if total_count == 1 else f"{total_count} projects"
            )
        self._update_action_state()

    def _restore_selection(self, selected_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_id is None:
            self._select_first_visible_row()
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                if not self._table.isRowHidden(row_index):
                    self._table.selectRow(row_index)
                    return
        self._select_first_visible_row()

    def _select_first_visible_row(self) -> None:
        for row_index in range(self._table.rowCount()):
            if not self._table.isRowHidden(row_index):
                self._table.selectRow(row_index)
                return
        self._table.clearSelection()

    def _selected_project(self) -> ProjectListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0 or self._table.isRowHidden(current_row):
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        project_id = item.data(Qt.ItemDataRole.UserRole)
        for project in self._projects:
            if project.id == project_id:
                return project
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_project()
        has_active_company = active_company is not None

        self._new_button.setEnabled(has_active_company)
        self._edit_button.setEnabled(selected is not None and has_active_company)
        self._activate_button.setEnabled(
            selected is not None and has_active_company and selected.status_code == "draft"
        )
        self._cancel_button.setEnabled(
            selected is not None
            and has_active_company
            and selected.status_code in {"draft", "active", "on_hold"}
        )
        self._jobs_button.setEnabled(selected is not None and has_active_company)
        self._cost_codes_button.setEnabled(has_active_company)
        self._budgets_button.setEnabled(selected is not None and has_active_company)
        self._commitments_button.setEnabled(selected is not None and has_active_company)
        self._hold_button.setEnabled(
            selected is not None and has_active_company and selected.status_code == "active"
        )
        self._complete_button.setEnabled(
            selected is not None
            and has_active_company
            and selected.status_code in {"active", "on_hold"}
        )
        self._close_button.setEnabled(
            selected is not None and has_active_company and selected.status_code == "completed"
        )
        self._open_workspace_button.setEnabled(selected is not None and has_active_company)
        self._variance_button.setEnabled(selected is not None and has_active_company)
        self._contract_summary_button.setEnabled(selected is not None and has_active_company)
        self._notify_ribbon_state_changed()

    # ------------------------------------------------------------------
    # Ribbon host
    # ------------------------------------------------------------------

    def _ribbon_commands(self) -> dict[str, object]:
        return {
            "projects.new": self._open_create_dialog,
            "projects.open_workspace": self._open_workspace,
            "projects.edit": self._open_edit_dialog,
            "projects.activate": self._activate_selected_project,
            "projects.hold": self._hold_selected_project,
            "projects.complete": self._complete_selected_project,
            "projects.close_record": self._close_selected_project,
            "projects.cancel": self._cancel_selected_project,
            "projects.jobs": self._open_jobs,
            "projects.budgets": self._open_budgets,
            "projects.commitments": self._open_commitments,
            "projects.cost_code_library": self._open_cost_codes,
            "projects.variance": self._open_variance_analysis,
            "projects.contract_summary": self._open_project_contract_summary,
            "projects.refresh": lambda: self.reload_projects(),
        }

    def ribbon_state(self) -> dict[str, bool]:
        return {
            "projects.new": self._new_button.isEnabled(),
            "projects.open_workspace": self._open_workspace_button.isEnabled(),
            "projects.edit": self._edit_button.isEnabled(),
            "projects.activate": self._activate_button.isEnabled(),
            "projects.hold": self._hold_button.isEnabled(),
            "projects.complete": self._complete_button.isEnabled(),
            "projects.close_record": self._close_button.isEnabled(),
            "projects.cancel": self._cancel_button.isEnabled(),
            "projects.jobs": self._jobs_button.isEnabled(),
            "projects.budgets": self._budgets_button.isEnabled(),
            "projects.commitments": self._commitments_button.isEnabled(),
            "projects.cost_code_library": self._cost_codes_button.isEnabled(),
            "projects.variance": self._variance_button.isEnabled(),
            "projects.contract_summary": self._contract_summary_button.isEnabled(),
            "projects.refresh": True,
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Projects", "Select an active company before creating projects.")
            return
        project = ProjectFormDialog.create_project(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if project is None:
            return
        self.reload_projects(selected_project_id=project.id)

    def _open_edit_dialog(self) -> None:
        active_company = self._active_company()
        selected = self._selected_project()
        if active_company is None or selected is None:
            show_info(self, "Projects", "Select a project to edit.")
            return
        updated = ProjectFormDialog.edit_project(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            project_id=selected.id,
            parent=self,
        )
        if updated is None:
            return
        self.reload_projects(selected_project_id=updated.id)

    def _activate_selected_project(self) -> None:
        self._change_selected_status(
            title="Activate Project",
            prompt="Activate project '{code}'?",
            service_call=self._service_registry.project_service.activate_project,
        )

    def _hold_selected_project(self) -> None:
        self._change_selected_status(
            title="Put Project On Hold",
            prompt="Put project '{code}' on hold?",
            service_call=self._service_registry.project_service.put_project_on_hold,
        )

    def _complete_selected_project(self) -> None:
        self._change_selected_status(
            title="Complete Project",
            prompt="Mark project '{code}' as completed?",
            service_call=self._service_registry.project_service.complete_project,
        )

    def _close_selected_project(self) -> None:
        self._change_selected_status(
            title="Close Project",
            prompt="Close project '{code}'?",
            service_call=self._service_registry.project_service.close_project,
        )

    def _cancel_selected_project(self) -> None:
        self._change_selected_status(
            title="Cancel Project",
            prompt="Cancel project '{code}'? This cannot be undone.",
            service_call=self._service_registry.project_service.cancel_project,
        )

    def _change_selected_status(self, *, title: str, prompt: str, service_call) -> None:
        selected = self._selected_project()
        if selected is None:
            return
        choice = QMessageBox.question(
            self,
            title,
            prompt.format(code=selected.project_code),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            service_call(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Projects", str(exc))
        self.reload_projects(selected_project_id=selected.id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _handle_item_double_clicked(self, *_args: object) -> None:
        self._open_workspace()

    def _open_jobs(self) -> None:
        active_company = self._active_company()
        selected = self._selected_project()
        if active_company is None or selected is None:
            show_info(self, "Projects", "Select a project to manage its jobs.")
            return
        ProjectJobsDialog.manage_jobs(
            self._service_registry,
            company_id=active_company.company_id,
            project_id=selected.id,
            project_code=selected.project_code,
            parent=self,
        )

    def _open_cost_codes(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Projects", "Select an active company first.")
            return
        ProjectCostCodesDialog.manage_cost_codes(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )

    def _open_budgets(self) -> None:
        active_company = self._active_company()
        selected = self._selected_project()
        if active_company is None or selected is None:
            show_info(self, "Projects", "Select a project to manage its budgets.")
            return
        BudgetVersionsDialog.manage_versions(
            self._service_registry,
            company_id=active_company.company_id,
            project_id=selected.id,
            project_code=selected.project_code,
            parent=self,
        )

    def _open_commitments(self) -> None:
        active_company = self._active_company()
        selected = self._selected_project()
        if active_company is None or selected is None:
            show_info(self, "Projects", "Select a project to manage its commitments.")
            return
        ProjectCommitmentsDialog.manage_commitments(
            self._service_registry,
            company_id=active_company.company_id,
            project_id=selected.id,
            project_code=selected.project_code,
            parent=self,
        )

    def _open_workspace(self) -> None:
        active_company = self._active_company()
        selected = self._selected_project()
        if active_company is None or selected is None:
            show_info(self, "Projects", "Select a project to open its workspace.")
            return

        manager = getattr(self._service_registry, "child_window_manager", None)
        if manager is None:
            self._open_edit_dialog()
            return

        from seeker_accounting.modules.contracts_projects.ui.project_workspace_window import (
            ProjectWorkspaceWindow,
        )

        manager.open_document(
            ProjectWorkspaceWindow.DOC_TYPE,
            selected.id,
            lambda: ProjectWorkspaceWindow(
                self._service_registry,
                company_id=active_company.company_id,
                company_name=active_company.company_name,
                project_id=selected.id,
            ),
        )

    def _open_variance_analysis(self) -> None:
        selected = self._selected_project()
        if selected is None:
            show_info(self, "Projects", "Select a project first.")
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.PROJECT_VARIANCE_ANALYSIS,
            context={"project_id": selected.id},
        )

    def _open_project_contract_summary(self) -> None:
        selected = self._selected_project()
        if selected is None:
            show_info(self, "Projects", "Select a project first.")
            return
        try:
            detail = self._service_registry.project_service.get_project_detail(selected.id)
        except NotFoundError as exc:
            show_error(self, "Projects", str(exc))
            return
        if detail.contract_id is None:
            show_info(self, "Projects", "The selected project is not linked to a contract.")
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.CONTRACT_SUMMARY,
            context={"contract_id": detail.contract_id},
        )

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_projects()
