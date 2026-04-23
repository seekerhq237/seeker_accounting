from __future__ import annotations

from datetime import date

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
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_dto import (
    FiscalPeriodListItemDTO,
    FiscalYearListItemDTO,
)
from seeker_accounting.modules.accounting.fiscal_periods.ui.fiscal_year_dialog import FiscalYearDialog
from seeker_accounting.modules.accounting.fiscal_periods.ui.fiscal_year_setup_wizard_dialog import (
    FiscalYearSetupWizardDialog,
)
from seeker_accounting.modules.accounting.fiscal_periods.ui.generate_periods_dialog import (
    GeneratePeriodsDialog,
)
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class FiscalPeriodsPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._fiscal_years: list[FiscalYearListItemDTO] = []
        self._periods: list[FiscalPeriodListItemDTO] = []
        self._resume_context: dict | None = None

        self.setObjectName("FiscalPeriodsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        self._resume_banner = self._build_resume_banner()
        root_layout.addWidget(self._resume_banner)
        self._action_bar = self._build_action_bar()
        root_layout.addWidget(self._action_bar)
        self._action_bar.hide()
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )

        self.reload_calendar()

    def reload_calendar(
        self,
        selected_fiscal_year_id: int | None = None,
        selected_fiscal_period_id: int | None = None,
    ) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._fiscal_years = []
            self._periods = []
            self._years_table.setRowCount(0)
            self._periods_table.setRowCount(0)
            self._year_count_label.setText("Select a company")
            self._period_count_label.setText("")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._fiscal_years = self._service_registry.fiscal_calendar_service.list_fiscal_years(
                active_company.company_id
            )
            self._periods = self._service_registry.fiscal_calendar_service.list_periods(active_company.company_id)
        except Exception as exc:
            self._fiscal_years = []
            self._periods = []
            self._years_table.setRowCount(0)
            self._periods_table.setRowCount(0)
            self._year_count_label.setText("Unable to load")
            self._period_count_label.setText("")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Fiscal Periods", f"Fiscal calendar data could not be loaded.\n\n{exc}")
            return

        self._populate_years_table()
        self._restore_year_selection(selected_fiscal_year_id)
        self._populate_periods_table(selected_fiscal_period_id)
        self._sync_surface_state(active_company)
        self._update_action_state()

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        layout.addStretch(1)

        self._new_year_button = QPushButton("New Fiscal Year", card)
        self._new_year_button.setProperty("variant", "primary")
        self._new_year_button.clicked.connect(self._open_create_year_dialog)
        layout.addWidget(self._new_year_button)

        self._generate_periods_button = QPushButton("Generate Periods", card)
        self._generate_periods_button.setProperty("variant", "secondary")
        self._generate_periods_button.clicked.connect(self._open_generate_periods_dialog)
        layout.addWidget(self._generate_periods_button)

        self._open_button = QPushButton("Open Period", card)
        self._open_button.setProperty("variant", "secondary")
        self._open_button.clicked.connect(self._open_selected_period)
        layout.addWidget(self._open_button)

        self._close_button = QPushButton("Close Period", card)
        self._close_button.setProperty("variant", "secondary")
        self._close_button.clicked.connect(self._close_selected_period)
        layout.addWidget(self._close_button)

        self._reopen_button = QPushButton("Reopen Period", card)
        self._reopen_button.setProperty("variant", "secondary")
        self._reopen_button.clicked.connect(self._reopen_selected_period)
        layout.addWidget(self._reopen_button)

        self._lock_button = QPushButton("Lock Period", card)
        self._lock_button.setProperty("variant", "secondary")
        self._lock_button.clicked.connect(self._lock_selected_period)
        layout.addWidget(self._lock_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_calendar())
        layout.addWidget(self._refresh_button)
        return card

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._workspace_surface = self._build_workspace_surface()
        self._empty_state = self._build_empty_state()
        self._no_active_company_state = self._build_no_active_company_state()
        self._stack.addWidget(self._workspace_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_active_company_state)
        return self._stack

    def _build_workspace_surface(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_years_card(), 1)
        layout.addWidget(self._build_periods_card(), 1)
        return container

    def _build_years_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        top_row = QWidget(card)
        top_row_layout = QHBoxLayout(top_row)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(12)

        title = QLabel("Fiscal Years", top_row)
        title.setObjectName("CardTitle")
        top_row_layout.addWidget(title)
        top_row_layout.addStretch(1)

        self._year_count_label = QLabel(top_row)
        self._year_count_label.setObjectName("ToolbarMeta")
        top_row_layout.addWidget(self._year_count_label)
        layout.addWidget(top_row)

        self._years_table = QTableWidget(card)
        self._years_table.setObjectName("FiscalYearsTable")
        self._years_table.setColumnCount(6)
        self._years_table.setHorizontalHeaderLabels(("Code", "Name", "Start", "End", "Status", "Active"))
        configure_compact_table(self._years_table)
        self._years_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._years_table.itemSelectionChanged.connect(self._handle_year_selection_changed)
        layout.addWidget(self._years_table)
        return card

    def _build_periods_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        top_row = QWidget(card)
        top_row_layout = QHBoxLayout(top_row)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(12)

        title = QLabel("Fiscal Periods", top_row)
        title.setObjectName("CardTitle")
        top_row_layout.addWidget(title)
        top_row_layout.addStretch(1)

        self._period_count_label = QLabel(top_row)
        self._period_count_label.setObjectName("ToolbarMeta")
        top_row_layout.addWidget(self._period_count_label)
        layout.addWidget(top_row)

        self._periods_table = QTableWidget(card)
        self._periods_table.setObjectName("FiscalPeriodsTable")
        self._periods_table.setColumnCount(6)
        self._periods_table.setHorizontalHeaderLabels(("No", "Code", "Name", "Start", "End", "Status"))
        configure_compact_table(self._periods_table)
        self._periods_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._periods_table.itemSelectionChanged.connect(self._update_action_state)
        layout.addWidget(self._periods_table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No fiscal years yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first fiscal year for the active company, then generate monthly periods from that controlled calendar boundary.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Fiscal Year", actions)
        create_button.setProperty("variant", "primary")
        create_button.clicked.connect(self._open_create_year_dialog)
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
            "Fiscal years and periods are company-scoped. Choose the active company from the shell before maintaining the accounting calendar.",
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
        if self._fiscal_years:
            self._stack.setCurrentWidget(self._workspace_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_years_table(self) -> None:
        self._years_table.setSortingEnabled(False)
        self._years_table.setRowCount(0)

        for fiscal_year in self._fiscal_years:
            row_index = self._years_table.rowCount()
            self._years_table.insertRow(row_index)
            values = (
                fiscal_year.year_code,
                fiscal_year.year_name,
                self._format_date(fiscal_year.start_date),
                self._format_date(fiscal_year.end_date),
                fiscal_year.status_code.title(),
                "Yes" if fiscal_year.is_active else "No",
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, fiscal_year.id)
                if column_index in {2, 3, 4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._years_table.setItem(row_index, column_index, item)

        self._years_table.resizeColumnsToContents()
        header = self._years_table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        self._years_table.setSortingEnabled(True)

        count = len(self._fiscal_years)
        self._year_count_label.setText(f"{count} fiscal year" if count == 1 else f"{count} fiscal years")

    def _populate_periods_table(self, selected_fiscal_period_id: int | None = None) -> None:
        self._periods_table.setSortingEnabled(False)
        self._periods_table.setRowCount(0)

        selected_year = self._selected_fiscal_year()
        visible_periods = [
            period for period in self._periods if selected_year is not None and period.fiscal_year_id == selected_year.id
        ]

        for period in visible_periods:
            row_index = self._periods_table.rowCount()
            self._periods_table.insertRow(row_index)
            values = (
                str(period.period_number),
                period.period_code,
                period.period_name,
                self._format_date(period.start_date),
                self._format_date(period.end_date),
                period.status_code.title(),
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, period.id)
                if column_index in {0, 3, 4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._periods_table.setItem(row_index, column_index, item)

        self._periods_table.resizeColumnsToContents()
        header = self._periods_table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.Stretch)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        self._periods_table.setSortingEnabled(True)

        count = len(visible_periods)
        self._period_count_label.setText(f"{count} period" if count == 1 else f"{count} periods")
        self._restore_period_selection(selected_fiscal_period_id)

    def _restore_year_selection(self, selected_fiscal_year_id: int | None) -> None:
        if self._years_table.rowCount() == 0:
            return
        if selected_fiscal_year_id is None:
            self._years_table.selectRow(0)
            return
        for row_index in range(self._years_table.rowCount()):
            item = self._years_table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_fiscal_year_id:
                self._years_table.selectRow(row_index)
                return
        self._years_table.selectRow(0)

    def _restore_period_selection(self, selected_fiscal_period_id: int | None) -> None:
        if self._periods_table.rowCount() == 0:
            return
        if selected_fiscal_period_id is None:
            self._periods_table.selectRow(0)
            return
        for row_index in range(self._periods_table.rowCount()):
            item = self._periods_table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_fiscal_period_id:
                self._periods_table.selectRow(row_index)
                return
        self._periods_table.selectRow(0)

    def _selected_fiscal_year(self) -> FiscalYearListItemDTO | None:
        current_row = self._years_table.currentRow()
        if current_row < 0:
            return None
        item = self._years_table.item(current_row, 0)
        if item is None:
            return None
        fiscal_year_id = item.data(Qt.ItemDataRole.UserRole)
        for fiscal_year in self._fiscal_years:
            if fiscal_year.id == fiscal_year_id:
                return fiscal_year
        return None

    def _selected_period(self) -> FiscalPeriodListItemDTO | None:
        current_row = self._periods_table.currentRow()
        if current_row < 0:
            return None
        item = self._periods_table.item(current_row, 0)
        if item is None:
            return None
        fiscal_period_id = item.data(Qt.ItemDataRole.UserRole)
        for fiscal_period in self._periods:
            if fiscal_period.id == fiscal_period_id:
                return fiscal_period
        return None

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Fiscal Periods",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        fiscal_year = self._selected_fiscal_year()
        period = self._selected_period()
        has_active_company = active_company is not None
        has_periods_for_selected_year = any(
            fiscal_year is not None and row.fiscal_year_id == fiscal_year.id for row in self._periods
        )
        permission_service = self._service_registry.permission_service

        self._new_year_button.setEnabled(
            has_active_company and permission_service.has_permission("fiscal.years.create")
        )
        self._generate_periods_button.setEnabled(
            has_active_company
            and fiscal_year is not None
            and not has_periods_for_selected_year
            and permission_service.has_permission("fiscal.periods.generate")
        )
        self._open_button.setEnabled(
            has_active_company
            and period is not None
            and period.status_code == "CLOSED"
            and permission_service.has_permission("fiscal.periods.open")
        )
        self._close_button.setEnabled(
            has_active_company
            and period is not None
            and period.status_code == "OPEN"
            and permission_service.has_permission("fiscal.periods.close")
        )
        self._reopen_button.setEnabled(
            has_active_company
            and period is not None
            and period.status_code == "CLOSED"
            and permission_service.has_permission("fiscal.periods.reopen")
        )
        self._lock_button.setEnabled(
            has_active_company
            and period is not None
            and period.status_code == "CLOSED"
            and permission_service.has_permission("fiscal.periods.lock")
        )
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ────────────────────────────────────────────────────

    def _ribbon_commands(self) -> dict:
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_handlers
        return {
            "fiscal_periods.wizard": self._open_fiscal_year_wizard,
            "fiscal_periods.new_year": self._open_create_year_dialog,
            "fiscal_periods.generate_periods": self._open_generate_periods_dialog,
            "fiscal_periods.open_period": self._open_selected_period,
            "fiscal_periods.close_period": self._close_selected_period,
            "fiscal_periods.reopen_period": self._reopen_selected_period,
            "fiscal_periods.lock_period": self._lock_selected_period,
            "fiscal_periods.refresh": self.reload_calendar,
            **related_goto_handlers(self._service_registry, "fiscal_periods"),
        }

    def ribbon_state(self) -> dict:
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_state
        return {
            "fiscal_periods.wizard": self._new_year_button.isEnabled(),
            "fiscal_periods.new_year": self._new_year_button.isEnabled(),
            "fiscal_periods.generate_periods": self._generate_periods_button.isEnabled(),
            "fiscal_periods.open_period": self._open_button.isEnabled(),
            "fiscal_periods.close_period": self._close_button.isEnabled(),
            "fiscal_periods.reopen_period": self._reopen_button.isEnabled(),
            "fiscal_periods.lock_period": self._lock_button.isEnabled(),
            "fiscal_periods.refresh": True,
            **related_goto_state("fiscal_periods"),
        }

    def _open_fiscal_year_wizard(self) -> None:
        permission_service = self._service_registry.permission_service
        if not permission_service.has_permission("fiscal.years.create"):
            self._show_permission_denied("fiscal.years.create")
            return
        if not permission_service.has_permission("fiscal.periods.generate"):
            self._show_permission_denied("fiscal.periods.generate")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(
                self,
                "Fiscal Periods",
                "Select an active company before launching the fiscal year wizard.",
            )
            return

        result = FiscalYearSetupWizardDialog.run(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is None:
            return
        show_info(self, "Fiscal Periods", result.summary)
        self.reload_calendar(selected_fiscal_year_id=result.fiscal_year.id)

    def _open_create_year_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("fiscal.years.create"):
            self._show_permission_denied("fiscal.years.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Fiscal Periods", "Select an active company before creating fiscal years.")
            return

        fiscal_year = FiscalYearDialog.create_fiscal_year(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if fiscal_year is None:
            return
        self.reload_calendar(selected_fiscal_year_id=fiscal_year.id)

    def _open_generate_periods_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("fiscal.periods.generate"):
            self._show_permission_denied("fiscal.periods.generate")
            return
        active_company = self._active_company()
        fiscal_year = self._selected_fiscal_year()
        if active_company is None or fiscal_year is None:
            show_info(self, "Fiscal Periods", "Select a fiscal year before generating periods.")
            return

        calendar = GeneratePeriodsDialog.generate_periods(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            fiscal_year_id=fiscal_year.id,
            fiscal_year_code=fiscal_year.year_code,
            parent=self,
        )
        if calendar is None:
            return
        show_info(
            self,
            "Fiscal Periods",
            f"Generated {len(calendar.periods)} periods for {calendar.fiscal_year.year_code}.",
        )
        selected_period_id = calendar.periods[0].id if calendar.periods else None
        self.reload_calendar(
            selected_fiscal_year_id=calendar.fiscal_year.id,
            selected_fiscal_period_id=selected_period_id,
        )

    def _open_selected_period(self) -> None:
        self._change_selected_period_status("open")

    def _close_selected_period(self) -> None:
        self._change_selected_period_status("close")

    def _reopen_selected_period(self) -> None:
        self._change_selected_period_status("reopen")

    def _lock_selected_period(self) -> None:
        self._change_selected_period_status("lock")

    def _change_selected_period_status(self, action: str) -> None:
        required_permission = {
            "open": "fiscal.periods.open",
            "close": "fiscal.periods.close",
            "reopen": "fiscal.periods.reopen",
            "lock": "fiscal.periods.lock",
        }[action]
        if not self._service_registry.permission_service.has_permission(required_permission):
            self._show_permission_denied(required_permission)
            return
        active_company = self._active_company()
        period = self._selected_period()
        if active_company is None or period is None:
            show_info(self, "Fiscal Periods", "Select a fiscal period first.")
            return

        choice = QMessageBox.question(
            self,
            f"{action.title()} Period",
            f"{action.title()} period {period.period_code} for {active_company.company_name}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        actor_user_id = self._service_registry.app_context.current_user_id
        try:
            if action == "open":
                result = self._service_registry.period_control_service.open_period(
                    active_company.company_id,
                    period.id,
                    actor_user_id=actor_user_id,
                )
            elif action == "close":
                result = self._service_registry.period_control_service.close_period(
                    active_company.company_id,
                    period.id,
                    actor_user_id=actor_user_id,
                )
            elif action == "reopen":
                result = self._service_registry.period_control_service.reopen_period(
                    active_company.company_id,
                    period.id,
                    actor_user_id=actor_user_id,
                )
            else:
                result = self._service_registry.period_control_service.lock_period(
                    active_company.company_id,
                    period.id,
                    actor_user_id=actor_user_id,
                )
        except (ValidationError, NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Fiscal Periods", str(exc))
            self.reload_calendar(
                selected_fiscal_year_id=period.fiscal_year_id,
                selected_fiscal_period_id=period.id,
            )
            return

        show_info(self, "Fiscal Periods", f"{result.period_code} is now {result.status_code.title()}.")
        self.reload_calendar(
            selected_fiscal_year_id=period.fiscal_year_id,
            selected_fiscal_period_id=period.id,
        )

    def _format_date(self, value: date) -> str:
        return value.strftime("%Y-%m-%d")

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _handle_year_selection_changed(self) -> None:
        self._populate_periods_table()
        self._update_action_state()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_calendar()

    # ── EH-2A: Guided resume support ──────────────────────────────────────────

    def _build_resume_banner(self) -> QFrame:
        banner = QFrame(self)
        banner.setObjectName("GuidedResumeBanner")

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        self._resume_banner_label = QLabel(banner)
        self._resume_banner_label.setObjectName("ResumeBannerMessage")
        self._resume_banner_label.setWordWrap(True)
        layout.addWidget(self._resume_banner_label, 1)

        self._return_to_journal_button = QPushButton("Return to Journal Entry", banner)
        self._return_to_journal_button.setProperty("variant", "primary")
        self._return_to_journal_button.clicked.connect(self._return_to_journal_workflow)
        layout.addWidget(self._return_to_journal_button)

        dismiss_btn = QPushButton("Dismiss", banner)
        dismiss_btn.setProperty("variant", "ghost")
        dismiss_btn.clicked.connect(self._dismiss_resume_banner)
        layout.addWidget(dismiss_btn)

        banner.setVisible(False)
        return banner

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        source_workflow = context.get("source_workflow")
        resume_token = context.get("resume_token")
        entry_date = context.get("entry_date")
        open_create_flow = bool(context.get("open_create_flow"))
        locked_period_flow = bool(context.get("locked_period_flow"))
        fiscal_period_code = context.get("fiscal_period_code")
        if source_workflow != "journal_entry" or not resume_token:
            self._dismiss_resume_banner()
            return
        self._resume_context = dict(context)
        if locked_period_flow:
            if fiscal_period_code and entry_date:
                message = (
                    f"Period {fiscal_period_code} is locked (journal date {entry_date}). "
                    "Select the period below and use Reopen Period, then return to your journal entry."
                )
            elif fiscal_period_code:
                message = (
                    f"Period {fiscal_period_code} is locked. "
                    "Select the period below and use Reopen Period, then return to your journal entry."
                )
            else:
                message = (
                    "The fiscal period for this journal date is locked. "
                    "Select the period and use Reopen Period, then return to your journal entry."
                )
            self._resume_banner_label.setText(message)
            self._resume_banner.setVisible(True)
            QTimer.singleShot(0, self._handle_locked_period_flow)
        else:
            if entry_date:
                message = (
                    f"Opened to create a fiscal period for journal date {entry_date}. "
                    "Create the fiscal year and periods below, then return to your journal entry."
                )
            else:
                message = (
                    "Opened from a journal entry. Create the required fiscal period below, "
                    "then return to complete your journal entry."
                )
            self._resume_banner_label.setText(message)
            self._resume_banner.setVisible(True)

            if open_create_flow:
                QTimer.singleShot(0, self._handle_create_flow)

    def _handle_locked_period_flow(self) -> None:
        """Auto-select the locked fiscal period so the user can clearly see it and reopen it."""
        if self._resume_context is None:
            return
        fiscal_period_id_raw = self._resume_context.get("fiscal_period_id")
        if fiscal_period_id_raw is None:
            return
        try:
            fiscal_period_id = int(fiscal_period_id_raw)
        except (TypeError, ValueError):
            return
        # Find the period and its containing year, then reload with that selection.
        target_period = next((p for p in self._periods if p.id == fiscal_period_id), None)
        if target_period is not None:
            self.reload_calendar(
                selected_fiscal_year_id=target_period.fiscal_year_id,
                selected_fiscal_period_id=fiscal_period_id,
            )

    def _handle_create_flow(self) -> None:
        """Open the best create path for the missing fiscal period, pre-targeted to the journal date."""
        from datetime import date as _date

        if self._resume_context is None:
            return
        active_company = self._active_company()
        if active_company is None:
            return

        target_entry_date: _date | None = None
        entry_date_raw = self._resume_context.get("entry_date")
        if entry_date_raw:
            try:
                target_entry_date = _date.fromisoformat(str(entry_date_raw))
            except ValueError:
                pass

        # Determine whether any existing fiscal year spans the target date.
        covering_year = None
        if target_entry_date is not None:
            for year in self._fiscal_years:
                if year.start_date <= target_entry_date <= year.end_date:
                    covering_year = year
                    break

        if covering_year is None:
            # No fiscal year at all (or none covering this date) — open fiscal year creation pre-filled.
            fiscal_year = (
                FiscalYearDialog.create_fiscal_year_for_date(
                    self._service_registry,
                    company_id=active_company.company_id,
                    company_name=active_company.company_name,
                    target_date=target_entry_date,
                    parent=self,
                )
                if target_entry_date is not None
                else FiscalYearDialog.create_fiscal_year(
                    self._service_registry,
                    company_id=active_company.company_id,
                    company_name=active_company.company_name,
                    parent=self,
                )
            )
            if fiscal_year is None:
                return
            self.reload_calendar(selected_fiscal_year_id=fiscal_year.id)
            # After creating the year, open period generation immediately if the year has no periods.
            selected_year = next((y for y in self._fiscal_years if y.id == fiscal_year.id), None)
            if selected_year is not None:
                has_periods = any(p.fiscal_year_id == selected_year.id for p in self._periods)
                if not has_periods:
                    self._open_generate_periods_for_year(selected_year.id)
        else:
            # A fiscal year covers the date but lacks the target period — select it and open generation.
            has_periods = any(p.fiscal_year_id == covering_year.id for p in self._periods)
            self.reload_calendar(selected_fiscal_year_id=covering_year.id)
            if not has_periods:
                self._open_generate_periods_for_year(covering_year.id)

    def _open_generate_periods_for_year(self, fiscal_year_id: int) -> None:
        """Open the Generate Periods dialog for the given fiscal year id if it is still ungenerated."""
        active_company = self._active_company()
        covering_year_item = next((y for y in self._fiscal_years if y.id == fiscal_year_id), None)
        if active_company is None or covering_year_item is None:
            return
        has_periods = any(p.fiscal_year_id == fiscal_year_id for p in self._periods)
        if has_periods:
            return

        calendar = GeneratePeriodsDialog.generate_periods(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            fiscal_year_id=covering_year_item.id,
            fiscal_year_code=covering_year_item.year_code,
            parent=self,
        )
        if calendar is None:
            return
        selected_period_id = calendar.periods[0].id if calendar.periods else None
        self.reload_calendar(
            selected_fiscal_year_id=calendar.fiscal_year.id,
            selected_fiscal_period_id=selected_period_id,
        )

    def _return_to_journal_workflow(self) -> None:
        if self._resume_context is None:
            return
        resume_token = self._resume_context.get("resume_token")
        self._resume_context = None
        self._resume_banner.setVisible(False)
        self._service_registry.navigation_service.navigate(
            nav_ids.JOURNALS,
            resume_token=resume_token,
        )

    def _dismiss_resume_banner(self) -> None:
        if self._resume_context:
            token = self._resume_context.get("resume_token")
            if token:
                self._service_registry.workflow_resume_service.discard_token(token)
        self._resume_context = None
        self._resume_banner.setVisible(False)
