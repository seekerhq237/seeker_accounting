from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
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
from seeker_accounting.platform.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


PROJECT_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="project_code", title="Project Code"),
    DataTableColumn(key="project_name", title="Name"),
    DataTableColumn(key="contract_number", title="Contract"),
    DataTableColumn(key="customer", title="Customer"),
    DataTableColumn(key="project_type", title="Type"),
    DataTableColumn(key="manager", title="Manager"),
    DataTableColumn(key="status", title="Status"),
)


# Ribbon command ids surfaced from this page.
_CMD_NEW = "projects.new"
_CMD_OPEN_WORKSPACE = "projects.open_workspace"
_CMD_EDIT = "projects.edit"
_CMD_ACTIVATE = "projects.activate"
_CMD_HOLD = "projects.hold"
_CMD_COMPLETE = "projects.complete"
_CMD_CLOSE = "projects.close_record"
_CMD_CANCEL = "projects.cancel"
_CMD_JOBS = "projects.jobs"
_CMD_BUDGETS = "projects.budgets"
_CMD_COMMITMENTS = "projects.commitments"
_CMD_COST_CODES = "projects.cost_code_library"
_CMD_VARIANCE = "projects.variance"
_CMD_CONTRACT_SUMMARY = "projects.contract_summary"
_CMD_REFRESH = "projects.refresh"


class ProjectsPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._projects: list[ProjectListItemDTO] = []

        # Per-command ribbon enablement. Mirrors the shell ribbon state.
        self._command_enabled: dict[str, bool] = {
            _CMD_NEW: False,
            _CMD_OPEN_WORKSPACE: False,
            _CMD_EDIT: False,
            _CMD_ACTIVATE: False,
            _CMD_HOLD: False,
            _CMD_COMPLETE: False,
            _CMD_CLOSE: False,
            _CMD_CANCEL: False,
            _CMD_JOBS: False,
            _CMD_BUDGETS: False,
            _CMD_COMMITMENTS: False,
            _CMD_COST_CODES: False,
            _CMD_VARIANCE: False,
            _CMD_CONTRACT_SUMMARY: False,
            _CMD_REFRESH: True,
        }

        self.setObjectName("ProjectsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self._search_edit.textChanged.connect(self._projects_table.set_search_text)
        self._search_edit.textChanged.connect(
            lambda _t: self._update_record_count_label()
        )

        self.reload_projects()

    def reload_projects(self, selected_project_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._projects = []
            self._populate_table()
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
            self._populate_table()
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Projects", f"Project data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._update_record_count_label()
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

        self._projects_model = QStandardItemModel(0, len(PROJECT_COLUMNS), self)
        self._projects_model.setHorizontalHeaderLabels([c.title for c in PROJECT_COLUMNS])

        self._projects_table = DataTable(
            columns=PROJECT_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text=(
                "No projects yet. Use the ribbon's New Project to create the first one."
            ),
            parent=card,
        )
        self._projects_table.set_model(self._projects_model)
        self._projects_status_delegate = apply_status_chip_to_column(
            self._projects_table.view(), 6
        )
        self._projects_table.selection_changed.connect(self._on_selection_changed)
        self._projects_table.row_activated.connect(self._on_row_activated)

        layout.addWidget(self._projects_table)
        return card

    def _build_empty_state(self) -> QWidget:
        state = build_empty_state("projects.empty", parent=self)
        state.primary_clicked.connect(self._open_create_dialog)
        return state

    def _build_no_active_company_state(self) -> QWidget:
        state = build_empty_state("projects.no_company", parent=self)
        state.primary_clicked.connect(self._open_companies_workspace)
        return state

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Permission Denied",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

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

    @staticmethod
    def _make_item(text: str, *, user_data: object | None = None) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self) -> None:
        self._projects_model.removeRows(0, self._projects_model.rowCount())
        for project in self._projects:
            items = [
                self._make_item(project.project_code, user_data=project.id),
                self._make_item(project.project_name),
                self._make_item(project.contract_number or ""),
                self._make_item(project.customer_display_name or ""),
                self._make_item(project.project_type_code),
                self._make_item(project.project_manager_display_name or ""),
                self._make_item(project.status_code),
            ]
            self._projects_model.appendRow(items)

    def _update_record_count_label(self) -> None:
        total_count = len(self._projects)
        query = self._search_edit.text().strip()
        if query:
            proxy = self._projects_table.view().model()
            visible = proxy.rowCount() if proxy is not None else 0
            self._record_count_label.setText(
                f"{visible} shown of {total_count} projects"
            )
        else:
            self._record_count_label.setText(
                f"{total_count} project" if total_count == 1 else f"{total_count} projects"
            )

    def _restore_selection(self, selected_id: int | None) -> None:
        if not self._projects:
            return
        if selected_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, p in enumerate(self._projects) if p.id == selected_id),
                0,
            )

        proxy = self._projects_table.view().model()
        if proxy is None:
            return
        src_index = self._projects_model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._projects_table.view().selectionModel()
        if sm is None:
            return
        sm.select(
            proxy_index,
            sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows,
        )
        self._projects_table.view().scrollTo(proxy_index)

    def _selected_project(self) -> ProjectListItemDTO | None:
        rows = self._projects_table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._projects):
            return self._projects[idx]
        return None

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        if self._selected_project() is not None:
            self._open_workspace()

    def _set_command_enabled(self, command_id: str, enabled: bool) -> None:
        self._command_enabled[command_id] = bool(enabled)

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_project()
        has_active_company = active_company is not None
        has_selection = selected is not None and has_active_company
        perm = self._service_registry.permission_service
        can_create = perm.has_permission("projects.create")
        can_edit = perm.has_permission("projects.edit")
        can_close = perm.has_permission("projects.close")

        self._set_command_enabled(_CMD_NEW, has_active_company and can_create)
        self._set_command_enabled(_CMD_EDIT, has_selection and can_edit)
        self._set_command_enabled(
            _CMD_ACTIVATE,
            has_selection and selected.status_code == "draft" and can_edit,
        )
        self._set_command_enabled(
            _CMD_HOLD,
            has_selection and selected.status_code == "active" and can_edit,
        )
        self._set_command_enabled(
            _CMD_COMPLETE,
            has_selection and selected.status_code in {"active", "on_hold"} and can_edit,
        )
        self._set_command_enabled(
            _CMD_CLOSE,
            has_selection and selected.status_code == "completed" and can_close,
        )
        self._set_command_enabled(
            _CMD_CANCEL,
            has_selection and selected.status_code in {"draft", "active", "on_hold"} and can_edit,
        )
        self._set_command_enabled(_CMD_JOBS, has_selection)
        self._set_command_enabled(_CMD_BUDGETS, has_selection)
        self._set_command_enabled(_CMD_COMMITMENTS, has_selection)
        self._set_command_enabled(_CMD_COST_CODES, has_active_company)
        self._set_command_enabled(_CMD_OPEN_WORKSPACE, has_selection)
        self._set_command_enabled(_CMD_VARIANCE, has_selection)
        self._set_command_enabled(_CMD_CONTRACT_SUMMARY, has_selection)
        self._set_command_enabled(_CMD_REFRESH, True)

        self._notify_ribbon_state_changed()

    # ------------------------------------------------------------------
    # Ribbon host
    # ------------------------------------------------------------------

    def _ribbon_commands(self) -> dict[str, object]:
        return {
            _CMD_NEW: self._open_create_dialog,
            _CMD_OPEN_WORKSPACE: self._open_workspace,
            _CMD_EDIT: self._open_edit_dialog,
            _CMD_ACTIVATE: self._activate_selected_project,
            _CMD_HOLD: self._hold_selected_project,
            _CMD_COMPLETE: self._complete_selected_project,
            _CMD_CLOSE: self._close_selected_project,
            _CMD_CANCEL: self._cancel_selected_project,
            _CMD_JOBS: self._open_jobs,
            _CMD_BUDGETS: self._open_budgets,
            _CMD_COMMITMENTS: self._open_commitments,
            _CMD_COST_CODES: self._open_cost_codes,
            _CMD_VARIANCE: self._open_variance_analysis,
            _CMD_CONTRACT_SUMMARY: self._open_project_contract_summary,
            _CMD_REFRESH: lambda: self.reload_projects(),
        }

    def ribbon_state(self) -> dict[str, bool]:
        return dict(self._command_enabled)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("projects.create"):
            self._show_permission_denied("projects.create")
            return
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
        if not self._service_registry.permission_service.has_permission("projects.edit"):
            self._show_permission_denied("projects.edit")
            return
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
        if not self._service_registry.permission_service.has_permission("projects.edit"):
            self._show_permission_denied("projects.edit")
            return
        self._change_selected_status(
            title="Activate Project",
            prompt="Activate project '{code}'?",
            service_call=self._service_registry.project_service.activate_project,
        )

    def _hold_selected_project(self) -> None:
        if not self._service_registry.permission_service.has_permission("projects.edit"):
            self._show_permission_denied("projects.edit")
            return
        self._change_selected_status(
            title="Put Project On Hold",
            prompt="Put project '{code}' on hold?",
            service_call=self._service_registry.project_service.put_project_on_hold,
        )

    def _complete_selected_project(self) -> None:
        if not self._service_registry.permission_service.has_permission("projects.edit"):
            self._show_permission_denied("projects.edit")
            return
        self._change_selected_status(
            title="Complete Project",
            prompt="Mark project '{code}' as completed?",
            service_call=self._service_registry.project_service.complete_project,
        )

    def _close_selected_project(self) -> None:
        if not self._service_registry.permission_service.has_permission("projects.close"):
            self._show_permission_denied("projects.close")
            return
        self._change_selected_status(
            title="Close Project",
            prompt="Close project '{code}'?",
            service_call=self._service_registry.project_service.close_project,
        )

    def _cancel_selected_project(self) -> None:
        if not self._service_registry.permission_service.has_permission("projects.edit"):
            self._show_permission_denied("projects.edit")
            return
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
