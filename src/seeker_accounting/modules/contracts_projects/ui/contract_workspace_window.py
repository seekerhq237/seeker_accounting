from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.child_windows.child_window_base import ChildWindowBase
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.modules.contracts_projects.dto.contract_change_order_commands import (
    ApproveContractChangeOrderCommand,
    RejectContractChangeOrderCommand,
    SubmitContractChangeOrderCommand,
)
from seeker_accounting.modules.contracts_projects.dto.contract_change_order_dto import (
    ContractChangeOrderListItemDTO,
)
from seeker_accounting.modules.contracts_projects.dto.contract_dto import ContractDetailDTO
from seeker_accounting.modules.contracts_projects.dto.project_dto import ProjectListItemDTO
from seeker_accounting.modules.contracts_projects.ui.contract_change_order_dialog import (
    ContractChangeOrderFormDialog,
)
from seeker_accounting.modules.contracts_projects.ui.contract_form_dialog import ContractFormDialog
from seeker_accounting.modules.contracts_projects.ui.project_form_dialog import ProjectFormDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.message_boxes import show_error


_CO_DRAFT = "draft"
_CO_SUBMITTED = "submitted"


def _fmt_amount(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def _fmt_date(value: datetime | date | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _humanize(code: str | None) -> str:
    if not code:
        return "—"
    return code.replace("_", " ").title()


class ContractWorkspaceWindow(ChildWindowBase):
    """Contract control workspace with tabs for overview, change orders, and projects."""

    DOC_TYPE = "contract_workspace"

    _TAB_OVERVIEW = 0
    _TAB_CHANGE_ORDERS = 1
    _TAB_PROJECTS = 2

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        company_name: str,
        contract_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title="Contract Workspace",
            surface_key=RibbonRegistry.child_window_key(self.DOC_TYPE),
            window_key=(self.DOC_TYPE, contract_id),
            registry=service_registry.ribbon_registry or RibbonRegistry(),
            icon_provider=IconProvider(service_registry.theme_manager),
            parent=parent,
        )
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._contract_id = contract_id
        self._detail: ContractDetailDTO | None = None
        self._value_labels: dict[str, QLabel] = {}
        self._change_orders: list[ContractChangeOrderListItemDTO] = []
        self._projects: list[ProjectListItemDTO] = []

        self.set_body(self._build_body())
        self._reload_detail()

    # ------------------------------------------------------------------
    # Body
    # ------------------------------------------------------------------

    def _build_body(self) -> QWidget:
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hero = QFrame(body)
        hero.setObjectName("DialogSectionCard")
        hero.setProperty("card", True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(4)

        self._hero_title = QLabel("Contract Workspace", hero)
        self._hero_title.setObjectName("DialogSectionTitle")
        hero_layout.addWidget(self._hero_title)

        self._hero_summary = QLabel(hero)
        self._hero_summary.setObjectName("DialogSectionSummary")
        self._hero_summary.setWordWrap(True)
        hero_layout.addWidget(self._hero_summary)
        layout.addWidget(hero)

        self._tabs = QTabWidget(body)
        self._tabs.addTab(self._build_overview_tab(), "Overview")
        self._tabs.addTab(self._build_change_orders_tab(), "Change Orders")
        self._tabs.addTab(self._build_projects_tab(), "Projects")
        self._tabs.currentChanged.connect(self._handle_tab_changed)
        layout.addWidget(self._tabs, 1)
        return body

    def _build_overview_tab(self) -> QWidget:
        wrapper = QWidget(self)
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(12)

        metrics = QFrame(wrapper)
        metrics.setObjectName("DialogSectionCard")
        metrics.setProperty("card", True)
        metrics_layout = QVBoxLayout(metrics)
        metrics_layout.setContentsMargins(18, 16, 18, 18)
        metrics_layout.setSpacing(12)

        metrics_title = QLabel("Commercial Snapshot", metrics)
        metrics_title.setObjectName("DialogSectionTitle")
        metrics_layout.addWidget(metrics_title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        specs = (
            ("number", "Contract Number"),
            ("customer", "Customer"),
            ("type", "Type"),
            ("status", "Status"),
            ("currency", "Currency"),
            ("billing", "Billing Basis"),
            ("start", "Start Date"),
            ("planned_end", "Planned End"),
            ("reference", "Reference"),
            ("retention", "Retention %"),
            ("base_amount", "Base Amount"),
            ("current_amount", "Current Amount"),
            ("approved_delta", "Approved CO Delta"),
            ("approved_by", "Approved By"),
        )
        for index, (key, label_text) in enumerate(specs):
            value = QLabel("—", metrics)
            value.setObjectName("ValueLabel")
            value.setWordWrap(True)
            self._value_labels[key] = value
            grid.addWidget(create_field_block(label_text, value), index // 2, index % 2)
        metrics_layout.addLayout(grid)
        outer.addWidget(metrics)

        notes = QFrame(wrapper)
        notes.setObjectName("DialogSectionCard")
        notes.setProperty("card", True)
        notes_layout = QVBoxLayout(notes)
        notes_layout.setContentsMargins(18, 16, 18, 18)
        notes_layout.setSpacing(12)

        notes_title = QLabel("Description", notes)
        notes_title.setObjectName("DialogSectionTitle")
        notes_layout.addWidget(notes_title)

        self._description_edit = QPlainTextEdit(notes)
        self._description_edit.setReadOnly(True)
        self._description_edit.setMinimumHeight(120)
        notes_layout.addWidget(self._description_edit)
        outer.addWidget(notes, 1)
        return wrapper

    def _build_change_orders_tab(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Change Orders", card)
        title.setObjectName("DialogSectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._co_count_label = QLabel("0 change orders", card)
        self._co_count_label.setObjectName("DialogSectionSummary")
        header.addWidget(self._co_count_label)
        layout.addLayout(header)

        self._co_table = QTableWidget(0, 7, card)
        self._co_table.setHorizontalHeaderLabels(
            ["Number", "Date", "Type", "Amount Delta", "Days", "Status", "Description"]
        )
        self._co_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._co_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._co_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._co_table.verticalHeader().setVisible(False)
        self._co_table.setAlternatingRowColors(True)
        self._co_table.itemSelectionChanged.connect(self.refresh_ribbon_state)
        self._co_table.itemDoubleClicked.connect(self._on_co_double_clicked)
        layout.addWidget(self._co_table, 1)
        return card

    def _build_projects_tab(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Linked Projects", card)
        title.setObjectName("DialogSectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._project_count_label = QLabel("0 projects", card)
        self._project_count_label.setObjectName("DialogSectionSummary")
        header.addWidget(self._project_count_label)
        layout.addLayout(header)

        self._projects_table = QTableWidget(0, 6, card)
        self._projects_table.setHorizontalHeaderLabels(
            ["Code", "Name", "Type", "Status", "Start", "Planned End"]
        )
        self._projects_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._projects_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._projects_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._projects_table.verticalHeader().setVisible(False)
        self._projects_table.setAlternatingRowColors(True)
        self._projects_table.itemSelectionChanged.connect(self.refresh_ribbon_state)
        self._projects_table.itemDoubleClicked.connect(self._on_project_double_clicked)
        layout.addWidget(self._projects_table, 1)
        return card

    # ------------------------------------------------------------------
    # Ribbon
    # ------------------------------------------------------------------

    def handle_ribbon_command(self, command_id: str) -> None:
        dispatch = {
            "contract_workspace.edit": self._open_edit_dialog,
            "contract_workspace.refresh": self._reload_all,
            "contract_workspace.activate": lambda: self._change_status(
                "Activate Contract",
                "Activate contract '{code}'?",
                self._service_registry.contract_service.activate_contract,
            ),
            "contract_workspace.hold": lambda: self._change_status(
                "Put Contract On Hold",
                "Put contract '{code}' on hold?",
                self._service_registry.contract_service.put_contract_on_hold,
            ),
            "contract_workspace.complete": lambda: self._change_status(
                "Complete Contract",
                "Mark contract '{code}' as completed?",
                self._service_registry.contract_service.complete_contract,
            ),
            "contract_workspace.close_record": lambda: self._change_status(
                "Close Contract",
                "Close contract '{code}'?",
                self._service_registry.contract_service.close_contract,
            ),
            "contract_workspace.cancel": lambda: self._change_status(
                "Cancel Contract",
                "Cancel contract '{code}'? This cannot be undone.",
                self._service_registry.contract_service.cancel_contract,
            ),
            "contract_workspace.co_new": self._co_create,
            "contract_workspace.co_edit": self._co_edit,
            "contract_workspace.co_submit": self._co_submit,
            "contract_workspace.co_approve": self._co_approve,
            "contract_workspace.co_reject": self._co_reject,
            "contract_workspace.co_cancel": self._co_cancel,
            "contract_workspace.project_new": self._project_create,
            "contract_workspace.project_open": self._project_open_workspace,
            "contract_workspace.project_edit": self._project_edit,
            "contract_workspace.summary": self._open_contract_summary,
            "contract_workspace.window_close": self.close,
        }
        handler = dispatch.get(command_id)
        if handler is not None:
            handler()

    def ribbon_state(self) -> dict[str, bool]:
        detail = self._detail
        tab_index = self._tabs.currentIndex() if hasattr(self, "_tabs") else self._TAB_OVERVIEW
        on_co_tab = tab_index == self._TAB_CHANGE_ORDERS
        on_projects_tab = tab_index == self._TAB_PROJECTS

        base = {
            "contract_workspace.edit": False,
            "contract_workspace.refresh": True,
            "contract_workspace.activate": False,
            "contract_workspace.hold": False,
            "contract_workspace.complete": False,
            "contract_workspace.close_record": False,
            "contract_workspace.cancel": False,
            "contract_workspace.co_new": False,
            "contract_workspace.co_edit": False,
            "contract_workspace.co_submit": False,
            "contract_workspace.co_approve": False,
            "contract_workspace.co_reject": False,
            "contract_workspace.co_cancel": False,
            "contract_workspace.project_new": False,
            "contract_workspace.project_open": False,
            "contract_workspace.project_edit": False,
            "contract_workspace.summary": True,
            "contract_workspace.window_close": True,
        }

        if detail is None:
            return base

        status = detail.status_code
        base["contract_workspace.edit"] = status not in {"closed", "cancelled"}
        base["contract_workspace.activate"] = status in {"draft", "on_hold"}
        base["contract_workspace.hold"] = status == "active"
        base["contract_workspace.complete"] = status in {"active", "on_hold"}
        base["contract_workspace.close_record"] = status == "completed"
        base["contract_workspace.cancel"] = status in {"draft", "active", "on_hold"}

        co_editable = status not in {"closed", "cancelled"}
        if on_co_tab and co_editable:
            base["contract_workspace.co_new"] = True
            selected_co = self._selected_change_order()
            co_status = selected_co.status_code if selected_co else None
            base["contract_workspace.co_edit"] = co_status == _CO_DRAFT
            base["contract_workspace.co_submit"] = co_status == _CO_DRAFT
            base["contract_workspace.co_approve"] = co_status == _CO_SUBMITTED
            base["contract_workspace.co_reject"] = co_status == _CO_SUBMITTED
            base["contract_workspace.co_cancel"] = co_status in {_CO_DRAFT, _CO_SUBMITTED}

        if on_projects_tab:
            project_editable = status not in {"closed", "cancelled"}
            base["contract_workspace.project_new"] = project_editable
            selected_project = self._selected_project()
            base["contract_workspace.project_open"] = selected_project is not None
            base["contract_workspace.project_edit"] = selected_project is not None
        return base

    def _handle_tab_changed(self, index: int) -> None:
        if index == self._TAB_CHANGE_ORDERS:
            self._reload_change_orders()
        elif index == self._TAB_PROJECTS:
            self._reload_projects()
        self.refresh_ribbon_state()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _reload_all(self) -> None:
        self._reload_detail()

    def _reload_detail(self) -> None:
        try:
            self._detail = self._service_registry.contract_service.get_contract_detail(self._contract_id)
        except NotFoundError as exc:
            show_error(self, "Contract Workspace", str(exc))
            self.close()
            return
        self._populate_detail()
        if hasattr(self, "_tabs"):
            idx = self._tabs.currentIndex()
            if idx == self._TAB_CHANGE_ORDERS:
                self._reload_change_orders()
            elif idx == self._TAB_PROJECTS:
                self._reload_projects()
        self.refresh_ribbon_state()

    def _populate_detail(self) -> None:
        detail = self._detail
        if detail is None:
            return

        self.setWindowTitle(f"{detail.contract_number} - {detail.contract_title}")
        self._hero_title.setText(f"{detail.contract_number} - {detail.contract_title}")
        self._hero_summary.setText(
            "Control workspace for contract lifecycle, change orders, linked projects, and reporting."
        )

        values = {
            "number": detail.contract_number,
            "customer": detail.customer_display_name,
            "type": _humanize(detail.contract_type_code),
            "status": _humanize(detail.status_code),
            "currency": detail.currency_code,
            "billing": _humanize(detail.billing_basis_code),
            "start": _fmt_date(detail.start_date),
            "planned_end": _fmt_date(detail.planned_end_date),
            "reference": detail.reference_number or "—",
            "retention": "—" if detail.retention_percent is None else f"{detail.retention_percent}%",
            "base_amount": _fmt_amount(detail.base_contract_amount),
            "current_amount": _fmt_amount(detail.current_contract_amount),
            "approved_delta": _fmt_amount(detail.approved_change_order_delta_total),
            "approved_by": detail.approved_by_display_name or "—",
        }
        for key, value in values.items():
            self._value_labels[key].setText(value)
        self._description_edit.setPlainText(detail.description or "")

    def _reload_change_orders(self, *, selected_id: int | None = None) -> None:
        try:
            self._change_orders = (
                self._service_registry.contract_change_order_service.list_change_orders(self._contract_id)
            )
        except Exception as exc:  # defensive — surface, do not crash
            self._change_orders = []
            show_error(self, "Change Orders", f"Could not load change orders.\n\n{exc}")

        count = len(self._change_orders)
        self._co_count_label.setText(f"{count} change order{'s' if count != 1 else ''}")
        self._populate_co_table(selected_id=selected_id)
        self.refresh_ribbon_state()

    def _populate_co_table(self, *, selected_id: int | None) -> None:
        table = self._co_table
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for co in self._change_orders:
            row = table.rowCount()
            table.insertRow(row)
            delta_str = "" if co.contract_amount_delta is None else f"{co.contract_amount_delta:,.2f}"
            days_str = "" if co.days_extension is None else str(co.days_extension)
            values = (
                co.change_order_number,
                _fmt_date(co.change_order_date),
                _humanize(co.change_type_code),
                delta_str,
                days_str,
                _humanize(co.status_code),
                (co.description or "")[:80],
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, co.id)
                if col == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col in {2, 4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

        header = table.horizontalHeader()
        for i in range(6):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        table.setSortingEnabled(True)

        if selected_id is not None:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    table.selectRow(row)
                    return
        if table.rowCount() > 0:
            table.selectRow(0)

    def _reload_projects(self, *, selected_id: int | None = None) -> None:
        try:
            all_projects = self._service_registry.project_service.list_projects(self._company_id)
        except Exception as exc:  # defensive
            all_projects = []
            show_error(self, "Projects", f"Could not load projects.\n\n{exc}")

        # Filter to this contract. project_service has no list-by-contract helper yet;
        # round-trip through detail to read contract_id without touching repositories directly.
        linked: list[ProjectListItemDTO] = []
        for project in all_projects:
            try:
                detail = self._service_registry.project_service.get_project_detail(project.id)
            except NotFoundError:
                continue
            if detail.contract_id == self._contract_id:
                linked.append(project)
        self._projects = linked

        count = len(self._projects)
        self._project_count_label.setText(f"{count} project{'s' if count != 1 else ''}")
        self._populate_projects_table(selected_id=selected_id)
        self.refresh_ribbon_state()

    def _populate_projects_table(self, *, selected_id: int | None) -> None:
        table = self._projects_table
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for project in self._projects:
            row = table.rowCount()
            table.insertRow(row)
            values = (
                project.project_code,
                project.project_name,
                _humanize(project.project_type_code),
                _humanize(project.status_code),
                _fmt_date(project.start_date),
                _fmt_date(project.planned_end_date),
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, project.id)
                if col in {2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

        header = table.horizontalHeader()
        for i in range(6):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setSortingEnabled(True)

        if selected_id is not None:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    table.selectRow(row)
                    return
        if table.rowCount() > 0:
            table.selectRow(0)

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def _selected_change_order(self) -> ContractChangeOrderListItemDTO | None:
        if not hasattr(self, "_co_table"):
            return None
        row = self._co_table.currentRow()
        if row < 0:
            return None
        item = self._co_table.item(row, 0)
        if item is None:
            return None
        co_id = item.data(Qt.ItemDataRole.UserRole)
        for co in self._change_orders:
            if co.id == co_id:
                return co
        return None

    def _selected_project(self) -> ProjectListItemDTO | None:
        if not hasattr(self, "_projects_table"):
            return None
        row = self._projects_table.currentRow()
        if row < 0:
            return None
        item = self._projects_table.item(row, 0)
        if item is None:
            return None
        project_id = item.data(Qt.ItemDataRole.UserRole)
        for project in self._projects:
            if project.id == project_id:
                return project
        return None

    # ------------------------------------------------------------------
    # Contract-level actions
    # ------------------------------------------------------------------

    def _open_edit_dialog(self) -> None:
        detail = self._detail
        if detail is None:
            return
        updated = ContractFormDialog.edit_contract(
            self._service_registry,
            company_id=self._company_id,
            company_name=self._company_name,
            contract_id=detail.id,
            parent=self,
        )
        if updated is not None:
            self._reload_detail()

    def _change_status(self, title: str, prompt: str, service_call) -> None:
        detail = self._detail
        if detail is None:
            return
        choice = QMessageBox.question(
            self,
            title,
            prompt.format(code=detail.contract_number),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            service_call(detail.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Contract Workspace", str(exc))
            return
        self._reload_detail()

    def _open_contract_summary(self) -> None:
        self._service_registry.navigation_service.navigate(
            nav_ids.CONTRACT_SUMMARY,
            context={"contract_id": self._contract_id},
        )

    # ------------------------------------------------------------------
    # Change order actions
    # ------------------------------------------------------------------

    def _co_create(self) -> None:
        detail = self._detail
        if detail is None:
            return
        result = ContractChangeOrderFormDialog.create_change_order(
            self._service_registry,
            self._company_id,
            self._contract_id,
            detail.contract_number,
            parent=self,
        )
        if result is not None:
            self._reload_change_orders(selected_id=result.id)

    def _co_edit(self) -> None:
        detail = self._detail
        selected = self._selected_change_order()
        if detail is None or selected is None or selected.status_code != _CO_DRAFT:
            return
        result = ContractChangeOrderFormDialog.edit_change_order(
            self._service_registry,
            self._company_id,
            self._contract_id,
            detail.contract_number,
            change_order_id=selected.id,
            parent=self,
        )
        if result is not None:
            self._reload_change_orders(selected_id=result.id)

    def _co_submit(self) -> None:
        self._co_transition(
            "Submit Change Order",
            "Submit change order '{code}' for approval?",
            lambda co_id: self._service_registry.contract_change_order_service.submit_change_order(
                SubmitContractChangeOrderCommand(change_order_id=co_id)
            ),
            required_status=_CO_DRAFT,
        )

    def _co_approve(self) -> None:
        self._co_transition(
            "Approve Change Order",
            "Approve change order '{code}'?",
            lambda co_id: self._service_registry.contract_change_order_service.approve_change_order(
                ApproveContractChangeOrderCommand(change_order_id=co_id)
            ),
            required_status=_CO_SUBMITTED,
            refresh_detail=True,
        )

    def _co_reject(self) -> None:
        self._co_transition(
            "Reject Change Order",
            "Reject change order '{code}'?",
            lambda co_id: self._service_registry.contract_change_order_service.reject_change_order(
                RejectContractChangeOrderCommand(change_order_id=co_id)
            ),
            required_status=_CO_SUBMITTED,
        )

    def _co_cancel(self) -> None:
        self._co_transition(
            "Cancel Change Order",
            "Cancel change order '{code}'? This cannot be undone.",
            lambda co_id: self._service_registry.contract_change_order_service.cancel_change_order(co_id),
            required_status=None,
        )

    def _co_transition(
        self,
        title: str,
        prompt: str,
        action,
        *,
        required_status: str | None,
        refresh_detail: bool = False,
    ) -> None:
        selected = self._selected_change_order()
        if selected is None:
            return
        if required_status is not None and selected.status_code != required_status:
            return
        choice = QMessageBox.question(
            self, title, prompt.format(code=selected.change_order_number)
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            action(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Change Orders", str(exc))
        self._reload_change_orders(selected_id=selected.id)
        if refresh_detail:
            self._reload_detail()

    def _on_co_double_clicked(self, _item) -> None:
        selected = self._selected_change_order()
        if selected is None:
            return
        if selected.status_code == _CO_DRAFT:
            self._co_edit()

    # ------------------------------------------------------------------
    # Project actions
    # ------------------------------------------------------------------

    def _project_create(self) -> None:
        result = ProjectFormDialog.create_project(
            self._service_registry,
            company_id=self._company_id,
            company_name=self._company_name,
            parent=self,
        )
        if result is not None:
            self._reload_projects(selected_id=result.id)

    def _project_edit(self) -> None:
        selected = self._selected_project()
        if selected is None:
            return
        result = ProjectFormDialog.edit_project(
            self._service_registry,
            company_id=self._company_id,
            company_name=self._company_name,
            project_id=selected.id,
            parent=self,
        )
        if result is not None:
            self._reload_projects(selected_id=result.id)

    def _project_open_workspace(self) -> None:
        selected = self._selected_project()
        if selected is None:
            return
        manager = self._service_registry.child_window_manager
        if manager is None:
            return
        # Local import avoids circular import at module load time.
        from seeker_accounting.modules.contracts_projects.ui.project_workspace_window import (
            ProjectWorkspaceWindow,
        )

        def _factory() -> ProjectWorkspaceWindow:
            return ProjectWorkspaceWindow(
                self._service_registry,
                company_id=self._company_id,
                company_name=self._company_name,
                project_id=selected.id,
            )

        manager.open_document("project_workspace", selected.id, _factory)

    def _on_project_double_clicked(self, _item) -> None:
        self._project_open_workspace()
