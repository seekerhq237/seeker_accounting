from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.child_windows.child_window_base import ChildWindowBase
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.modules.accounting.journals.ui.journal_entry_dialog import JournalEntryDialog
from seeker_accounting.modules.budgeting.ui.budget_editor_dialog import BudgetEditorDialog
from seeker_accounting.modules.budgeting.ui.budget_version_dialog import BudgetVersionsDialog
from seeker_accounting.modules.contracts_projects.dto.project_dto import ProjectDetailDTO
from seeker_accounting.modules.contracts_projects.ui.project_cost_code_dialog import ProjectCostCodesDialog
from seeker_accounting.modules.contracts_projects.ui.project_form_dialog import ProjectFormDialog
from seeker_accounting.modules.contracts_projects.ui.project_job_dialog import ProjectJobsDialog
from seeker_accounting.modules.job_costing.ui.project_commitment_dialog import ProjectCommitmentsDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


def _fmt_date(value: datetime | date | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _fmt_amount(value: Decimal | int | float | None, currency: str | None = None) -> str:
    if value is None:
        return "—"
    try:
        amount = Decimal(value)
    except Exception:  # pragma: no cover - defensive
        return str(value)
    text = f"{amount:,.2f}"
    return f"{text} {currency}" if currency else text


def _fmt_percent(value: Decimal | float | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{Decimal(value):+.1f}%"
    except Exception:  # pragma: no cover
        return str(value)


def _status_label(code: str | None) -> str:
    if not code:
        return "—"
    return code.replace("_", " ").title()


_STATUS_COLORS = {
    "active":    ("#dcfce7", "#166534"),
    "draft":     ("#e0f2fe", "#075985"),
    "on_hold":   ("#fef3c7", "#92400e"),
    "completed": ("#ede9fe", "#5b21b6"),
    "closed":    ("#e5e7eb", "#374151"),
    "cancelled": ("#fee2e2", "#991b1b"),
    "submitted": ("#e0f2fe", "#075985"),
    "approved":  ("#dcfce7", "#166534"),
    "superseded":("#e5e7eb", "#374151"),
    "inactive":  ("#e5e7eb", "#374151"),
}


def _status_style(code: str | None) -> str:
    bg, fg = _STATUS_COLORS.get((code or "").lower(), ("#e5e7eb", "#374151"))
    return (
        f"padding: 2px 10px; border-radius: 10px; background: {bg}; "
        f"color: {fg}; font-weight: 600;"
    )


class ProjectWorkspaceWindow(ChildWindowBase):
    DOC_TYPE = "project_workspace"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        company_name: str,
        project_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title="Project Workspace",
            surface_key=RibbonRegistry.child_window_key(self.DOC_TYPE),
            window_key=(self.DOC_TYPE, project_id),
            registry=service_registry.ribbon_registry or RibbonRegistry(),
            icon_provider=IconProvider(service_registry.theme_manager),
            parent=parent,
        )
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._project_id = project_id
        self._detail: ProjectDetailDTO | None = None

        # KPI tile value labels keyed by metric
        self._kpi_labels: dict[str, QLabel] = {}
        # Hero facts keyed by name
        self._hero_facts: dict[str, QLabel] = {}

        self.set_body(self._build_body())
        self._reload_detail()

    # ------------------------------------------------------------------ body
    def _build_body(self) -> QWidget:
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        layout.addWidget(self._build_hero())
        layout.addWidget(self._build_kpi_strip())

        grid_host = QFrame(body)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.addWidget(self._build_jobs_card(), 0, 0)
        grid.addWidget(self._build_budgets_card(), 0, 1)
        grid.addWidget(self._build_commitments_card(), 1, 0)
        grid.addWidget(self._build_costs_card(), 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        layout.addWidget(grid_host, 1)

        layout.addWidget(self._build_notes_card())
        return body

    # ------------------------------------------------------------------ hero
    def _build_hero(self) -> QWidget:
        hero = QFrame(self)
        hero.setObjectName("DialogSectionCard")
        hero.setProperty("card", True)
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        self._title_label = QLabel("Project", hero)
        font = self._title_label.font()
        font.setPointSize(max(font.pointSize() + 3, 14))
        font.setBold(True)
        self._title_label.setFont(font)
        title_row.addWidget(self._title_label)

        self._type_chip = QLabel("", hero)
        self._type_chip.setStyleSheet(
            "padding: 2px 8px; border-radius: 8px; background: #eef1f5; "
            "color: #374151; font-weight: 500;"
        )
        title_row.addWidget(self._type_chip)

        self._status_chip = QLabel("", hero)
        title_row.addWidget(self._status_chip)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        facts = QHBoxLayout()
        facts.setSpacing(18)
        fact_specs = (
            ("contract",  "Contract"),
            ("customer",  "Customer"),
            ("manager",   "Manager"),
            ("period",    "Period"),
            ("currency",  "Currency"),
            ("budget_control", "Control"),
        )
        for key, label_text in fact_specs:
            block = QVBoxLayout()
            block.setSpacing(0)
            caption = QLabel(label_text.upper(), hero)
            caption.setStyleSheet("color: #6b7280; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;")
            value = QLabel("—", hero)
            value.setStyleSheet("color: #111827; font-size: 12px;")
            self._hero_facts[key] = value
            block.addWidget(caption)
            block.addWidget(value)
            facts.addLayout(block)
        facts.addStretch(1)
        layout.addLayout(facts)
        return hero

    # ------------------------------------------------------------------ kpi
    def _build_kpi_strip(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("DialogSectionCard")
        frame.setProperty("card", True)
        row = QHBoxLayout(frame)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(12)

        for key, caption in (
            ("budget",     "Approved Budget"),
            ("actual",     "Actual Cost"),
            ("committed",  "Open Commitments"),
            ("exposure",   "Total Exposure"),
            ("remaining",  "Remaining Budget"),
            ("variance",   "Variance %"),
        ):
            tile = self._build_kpi_tile(caption)
            row.addWidget(tile, 1)
            self._kpi_labels[key] = tile.findChild(QLabel, "KpiValue")

        return frame

    def _build_kpi_tile(self, caption: str) -> QWidget:
        tile = QFrame()
        tile.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; }"
        )
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(2)
        cap = QLabel(caption.upper(), tile)
        cap.setStyleSheet("color: #6b7280; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;")
        value = QLabel("—", tile)
        value.setObjectName("KpiValue")
        vf = QFont(value.font())
        vf.setPointSize(max(vf.pointSize() + 4, 15))
        vf.setBold(True)
        value.setFont(vf)
        value.setStyleSheet("color: #111827;")
        layout.addWidget(cap)
        layout.addWidget(value)
        return tile

    # ------------------------------------------------------------------ cards
    def _build_card(self, title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        title_label = QLabel(title, card)
        title_label.setObjectName("DialogSectionTitle")
        header.addWidget(title_label)
        header.addStretch(1)
        outer.addLayout(header)

        return card, outer, header

    def _build_jobs_card(self) -> QWidget:
        card, outer, header = self._build_card("Jobs")
        self._jobs_subtitle = QLabel("0 jobs", card)
        self._jobs_subtitle.setStyleSheet("color: #6b7280; font-size: 11px;")
        header.insertWidget(1, self._jobs_subtitle)

        open_btn = QPushButton("Manage", card)
        open_btn.setProperty("variant", "secondary")
        open_btn.clicked.connect(self._open_jobs)
        header.addWidget(open_btn)

        self._jobs_table = QTableWidget(0, 5, card)
        self._jobs_table.setHorizontalHeaderLabels(["Code", "Name", "Status", "Start", "Planned End"])
        configure_compact_table(self._jobs_table)
        self._jobs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._jobs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._jobs_table.doubleClicked.connect(lambda *_: self._open_jobs())
        self._jobs_table.setMaximumHeight(200)
        outer.addWidget(self._jobs_table)
        return card

    def _build_budgets_card(self) -> QWidget:
        card, outer, header = self._build_card("Budget")
        self._budgets_subtitle = QLabel("No budget", card)
        self._budgets_subtitle.setStyleSheet("color: #6b7280; font-size: 11px;")
        header.insertWidget(1, self._budgets_subtitle)

        self._new_budget_btn = QPushButton("New Budget", card)
        self._new_budget_btn.setProperty("variant", "primary")
        self._new_budget_btn.clicked.connect(self._open_new_budget)
        header.addWidget(self._new_budget_btn)

        self._revise_budget_btn = QPushButton("Revise", card)
        self._revise_budget_btn.setProperty("variant", "primary")
        self._revise_budget_btn.clicked.connect(self._open_revise_budget)
        header.addWidget(self._revise_budget_btn)

        self._manage_versions_btn = QPushButton("Versions", card)
        self._manage_versions_btn.setProperty("variant", "secondary")
        self._manage_versions_btn.setToolTip("Open budget version history")
        self._manage_versions_btn.clicked.connect(self._open_budgets)
        header.addWidget(self._manage_versions_btn)

        # Table shows *lines* of the current approved version (or latest draft fallback)
        self._budgets_table = QTableWidget(0, 5, card)
        self._budgets_table.setHorizontalHeaderLabels(
            ["#", "Job", "Cost Code", "Description", "Amount"]
        )
        configure_compact_table(self._budgets_table)
        self._budgets_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._budgets_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._budgets_table.doubleClicked.connect(lambda *_: self._open_revise_budget())
        self._budgets_table.setMaximumHeight(200)
        outer.addWidget(self._budgets_table)
        return card

    def _build_commitments_card(self) -> QWidget:
        card, outer, header = self._build_card("Commitments")
        self._commitments_subtitle = QLabel("0 commitments", card)
        self._commitments_subtitle.setStyleSheet("color: #6b7280; font-size: 11px;")
        header.insertWidget(1, self._commitments_subtitle)

        open_btn = QPushButton("Manage", card)
        open_btn.setProperty("variant", "secondary")
        open_btn.clicked.connect(self._open_commitments)
        header.addWidget(open_btn)

        self._commitments_table = QTableWidget(0, 5, card)
        self._commitments_table.setHorizontalHeaderLabels(["Number", "Supplier", "Type", "Status", "Total"])
        configure_compact_table(self._commitments_table)
        self._commitments_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._commitments_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._commitments_table.doubleClicked.connect(lambda *_: self._open_commitments())
        self._commitments_table.setMaximumHeight(200)
        outer.addWidget(self._commitments_table)
        return card

    def _build_costs_card(self) -> QWidget:
        card, outer, header = self._build_card("Actual Costs")
        self._costs_subtitle = QLabel("0.00", card)
        self._costs_subtitle.setStyleSheet("color: #6b7280; font-size: 11px;")
        header.insertWidget(1, self._costs_subtitle)

        record_btn = QPushButton("Record Cost", card)
        record_btn.setProperty("variant", "primary")
        record_btn.clicked.connect(self._open_record_cost)
        header.addWidget(record_btn)

        variance_btn = QPushButton("Variance", card)
        variance_btn.setProperty("variant", "secondary")
        variance_btn.clicked.connect(self._open_variance)
        header.addWidget(variance_btn)

        self._costs_table = QTableWidget(0, 2, card)
        self._costs_table.setHorizontalHeaderLabels(["Source", "Amount"])
        configure_compact_table(self._costs_table)
        self._costs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._costs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._costs_table.setMaximumHeight(200)
        outer.addWidget(self._costs_table)
        return card

    def _build_notes_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 8, 14, 10)
        outer.setSpacing(4)

        label = QLabel("Notes", card)
        label.setObjectName("DialogSectionTitle")
        outer.addWidget(label)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setReadOnly(True)
        self._notes_edit.setFixedHeight(60)
        self._notes_edit.setPlaceholderText("No notes recorded for this project.")
        outer.addWidget(self._notes_edit)
        self._notes_card = card
        return card

    # ------------------------------------------------------------------ ribbon
    def handle_ribbon_command(self, command_id: str) -> None:
        if command_id == "project_workspace.edit":
            self._open_edit_dialog()
        elif command_id == "project_workspace.activate":
            self._change_status(
                title="Activate Project",
                prompt="Activate project '{code}'?",
                service_call=self._service_registry.project_service.activate_project,
            )
        elif command_id == "project_workspace.hold":
            self._change_status(
                title="Put Project On Hold",
                prompt="Put project '{code}' on hold?",
                service_call=self._service_registry.project_service.put_project_on_hold,
            )
        elif command_id == "project_workspace.complete":
            self._change_status(
                title="Complete Project",
                prompt="Mark project '{code}' as completed?",
                service_call=self._service_registry.project_service.complete_project,
            )
        elif command_id == "project_workspace.close_record":
            self._change_status(
                title="Close Project",
                prompt="Close project '{code}'?",
                service_call=self._service_registry.project_service.close_project,
            )
        elif command_id == "project_workspace.cancel":
            self._change_status(
                title="Cancel Project",
                prompt="Cancel project '{code}'? This cannot be undone.",
                service_call=self._service_registry.project_service.cancel_project,
            )
        elif command_id == "project_workspace.jobs":
            self._open_jobs()
        elif command_id == "project_workspace.budgets":
            self._open_budgets()
        elif command_id == "project_workspace.new_budget":
            self._open_new_budget()
        elif command_id == "project_workspace.revise_budget":
            self._open_revise_budget()
        elif command_id == "project_workspace.commitments":
            self._open_commitments()
        elif command_id == "project_workspace.cost_code_library":
            self._open_cost_codes()
        elif command_id == "project_workspace.record_cost":
            self._open_record_cost()
        elif command_id == "project_workspace.variance":
            self._open_variance()
        elif command_id == "project_workspace.contract_summary":
            self._open_contract_summary()
        elif command_id == "project_workspace.refresh":
            self._reload_detail()
        elif command_id == "project_workspace.window_close":
            self.close()

    def ribbon_state(self) -> dict[str, bool]:
        detail = self._detail
        if detail is None:
            return {
                "project_workspace.edit": False,
                "project_workspace.activate": False,
                "project_workspace.hold": False,
                "project_workspace.complete": False,
                "project_workspace.close_record": False,
                "project_workspace.cancel": False,
                "project_workspace.jobs": False,
                "project_workspace.budgets": False,
                "project_workspace.new_budget": False,
                "project_workspace.revise_budget": False,
                "project_workspace.commitments": False,
                "project_workspace.cost_code_library": False,
                "project_workspace.record_cost": False,
                "project_workspace.variance": False,
                "project_workspace.contract_summary": False,
                "project_workspace.refresh": True,
                "project_workspace.window_close": True,
            }

        status = detail.status_code
        postable = status in {"active", "on_hold"}
        has_approved_budget = False
        try:
            has_approved_budget = (
                self._service_registry.budget_approval_service.get_current_approved_budget(
                    detail.id
                )
                is not None
            )
        except Exception:
            has_approved_budget = False
        return {
            "project_workspace.edit": status not in {"closed", "cancelled"},
            "project_workspace.activate": status in {"draft", "on_hold"},
            "project_workspace.hold": status == "active",
            "project_workspace.complete": status in {"active", "on_hold"},
            "project_workspace.close_record": status == "completed",
            "project_workspace.cancel": status in {"draft", "active", "on_hold"},
            "project_workspace.jobs": True,
            "project_workspace.budgets": True,
            "project_workspace.new_budget": not has_approved_budget,
            "project_workspace.revise_budget": has_approved_budget,
            "project_workspace.commitments": True,
            "project_workspace.cost_code_library": True,
            "project_workspace.record_cost": postable,
            "project_workspace.variance": True,
            "project_workspace.contract_summary": detail.contract_id is not None,
            "project_workspace.refresh": True,
            "project_workspace.window_close": True,
        }

    # ------------------------------------------------------------------ data
    def _reload_detail(self) -> None:
        try:
            self._detail = self._service_registry.project_service.get_project_detail(self._project_id)
        except NotFoundError as exc:
            show_error(self, "Project Workspace", str(exc))
            self.close()
            return
        self._populate_detail()
        self._populate_jobs()
        self._populate_budgets()
        self._populate_commitments()
        self._populate_costs_and_kpis()
        self.refresh_ribbon_state()

    def _populate_detail(self) -> None:
        detail = self._detail
        if detail is None:
            return

        self.setWindowTitle(f"{detail.project_code} - {detail.project_name}")
        self._title_label.setText(f"{detail.project_code}  ·  {detail.project_name}")
        self._type_chip.setText(_status_label(detail.project_type_code))
        self._status_chip.setText(_status_label(detail.status_code))
        self._status_chip.setStyleSheet(_status_style(detail.status_code))

        period = f"{_fmt_date(detail.start_date)} → {_fmt_date(detail.planned_end_date)}"
        if detail.actual_end_date is not None:
            period = f"{period}  (ended {_fmt_date(detail.actual_end_date)})"
        self._hero_facts["contract"].setText(detail.contract_number or "—")
        self._hero_facts["customer"].setText(detail.customer_display_name or "—")
        self._hero_facts["manager"].setText(detail.project_manager_display_name or "—")
        self._hero_facts["period"].setText(period)
        self._hero_facts["currency"].setText(detail.currency_code or "—")
        self._hero_facts["budget_control"].setText(_status_label(detail.budget_control_mode_code))

        notes = (detail.notes or "").strip()
        self._notes_edit.setPlainText(notes)
        self._notes_card.setVisible(bool(notes))

    def _populate_jobs(self) -> None:
        detail = self._detail
        self._jobs_table.setRowCount(0)
        if detail is None:
            return
        try:
            jobs = self._service_registry.project_structure_service.list_jobs(detail.id)
        except NotFoundError:
            jobs = []
        self._jobs_subtitle.setText(f"{len(jobs)} job{'s' if len(jobs) != 1 else ''}")
        self._jobs_table.setSortingEnabled(False)
        self._jobs_table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            self._jobs_table.setItem(row, 0, QTableWidgetItem(job.job_code or ""))
            self._jobs_table.setItem(row, 1, QTableWidgetItem(job.job_name or ""))
            self._jobs_table.setItem(row, 2, QTableWidgetItem(_status_label(job.status_code)))
            self._jobs_table.setItem(row, 3, QTableWidgetItem(_fmt_date(job.start_date)))
            self._jobs_table.setItem(row, 4, QTableWidgetItem(_fmt_date(job.planned_end_date)))
        self._jobs_table.setSortingEnabled(True)

    def _populate_budgets(self) -> None:
        detail = self._detail
        self._budgets_table.setRowCount(0)
        if detail is None:
            self._budgets_subtitle.setText("No budget")
            self._new_budget_btn.setVisible(True)
            self._revise_budget_btn.setVisible(False)
            return

        currency = detail.currency_code
        svc = self._service_registry.project_budget_service

        try:
            versions = svc.list_versions(detail.id)
        except NotFoundError:
            versions = []

        # Pick the focus version: current approved → else latest draft/submitted → else None
        focus = next((v for v in versions if v.status_code == "approved"), None)
        is_approved_focus = focus is not None
        if focus is None:
            focus = next(
                (v for v in versions if v.status_code in ("draft", "submitted")),
                None,
            )

        # Button enablement
        self._new_budget_btn.setVisible(not versions or all(
            v.status_code in ("superseded", "cancelled") for v in versions
        ))
        self._revise_budget_btn.setVisible(focus is not None)
        self._manage_versions_btn.setVisible(bool(versions))

        if focus is None:
            self._budgets_subtitle.setText("No budget yet — create one to begin")
            return

        # Subtitle
        approved_at = _fmt_date(focus.updated_at) if focus.status_code == "approved" else None
        subtitle_bits = [
            f"v{focus.version_number}",
            _status_label(focus.status_code),
            _fmt_amount(focus.total_budget_amount, currency),
        ]
        if approved_at:
            subtitle_bits.append(f"approved {approved_at}")
        self._budgets_subtitle.setText("  ·  ".join(subtitle_bits))

        # Load lines for this focus version
        try:
            lines = svc.list_lines(focus.id)
        except NotFoundError:
            lines = []

        self._budgets_table.setSortingEnabled(False)
        self._budgets_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            num_item = QTableWidgetItem(str(line.line_number))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._budgets_table.setItem(row, 0, num_item)
            self._budgets_table.setItem(row, 1, QTableWidgetItem(line.project_job_code or "—"))
            self._budgets_table.setItem(
                row, 2, QTableWidgetItem(line.project_cost_code_name or "—")
            )
            self._budgets_table.setItem(row, 3, QTableWidgetItem(line.description or ""))
            amount_item = QTableWidgetItem(_fmt_amount(line.line_amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._budgets_table.setItem(row, 4, amount_item)
        self._budgets_table.setSortingEnabled(True)

    def _populate_commitments(self) -> None:
        detail = self._detail
        self._commitments_table.setRowCount(0)
        if detail is None:
            return
        try:
            commitments = self._service_registry.project_commitment_service.list_commitments(detail.id)
        except NotFoundError:
            commitments = []

        open_total = Decimal("0")
        for c in commitments:
            if c.status_code in {"approved", "submitted"}:
                try:
                    open_total += Decimal(c.total_amount or 0)
                except Exception:
                    pass
        self._commitments_subtitle.setText(
            f"{len(commitments)} · open {_fmt_amount(open_total, detail.currency_code)}"
        )

        self._commitments_table.setSortingEnabled(False)
        self._commitments_table.setRowCount(len(commitments))
        for row, c in enumerate(commitments):
            self._commitments_table.setItem(row, 0, QTableWidgetItem(c.commitment_number or ""))
            self._commitments_table.setItem(row, 1, QTableWidgetItem(c.supplier_name or "—"))
            self._commitments_table.setItem(row, 2, QTableWidgetItem(_status_label(c.commitment_type_code)))
            self._commitments_table.setItem(row, 3, QTableWidgetItem(_status_label(c.status_code)))
            amount_item = QTableWidgetItem(_fmt_amount(c.total_amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._commitments_table.setItem(row, 4, amount_item)
        self._commitments_table.setSortingEnabled(True)

    def _populate_costs_and_kpis(self) -> None:
        detail = self._detail
        self._costs_table.setRowCount(0)
        if detail is None:
            return
        currency = detail.currency_code

        # Cost breakdown by source
        try:
            summary = self._service_registry.project_actual_cost_service.get_actual_cost_summary(
                detail.company_id, detail.id
            )
            source_totals = list(summary.source_totals)
            actual_total = Decimal(summary.total_actual_cost_amount or 0)
        except Exception:  # pragma: no cover - defensive
            source_totals = []
            actual_total = Decimal("0")

        self._costs_subtitle.setText(_fmt_amount(actual_total, currency))
        self._costs_table.setSortingEnabled(False)
        self._costs_table.setRowCount(len(source_totals))
        for row, src in enumerate(source_totals):
            self._costs_table.setItem(row, 0, QTableWidgetItem(src.source_type_label or src.source_type_code))
            amount_item = QTableWidgetItem(_fmt_amount(src.amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._costs_table.setItem(row, 1, amount_item)
        self._costs_table.setSortingEnabled(True)

        # Variance KPIs
        try:
            variance = self._service_registry.budget_reporting_service.get_project_variance_summary(
                detail.company_id, detail.id
            )
            budget = variance.approved_budget_amount
            committed = variance.approved_commitment_amount
            exposure = variance.total_exposure_amount
            remaining = variance.remaining_budget_after_commitments_amount
            variance_pct = variance.variance_percent
            actual = variance.actual_cost_amount
        except Exception:  # pragma: no cover - defensive
            budget = committed = exposure = remaining = actual = None
            variance_pct = None

        self._kpi_labels["budget"].setText(_fmt_amount(budget, currency))
        self._kpi_labels["actual"].setText(_fmt_amount(actual if actual is not None else actual_total, currency))
        self._kpi_labels["committed"].setText(_fmt_amount(committed, currency))
        self._kpi_labels["exposure"].setText(_fmt_amount(exposure, currency))
        self._kpi_labels["remaining"].setText(_fmt_amount(remaining, currency))

        variance_label = self._kpi_labels["variance"]
        variance_label.setText(_fmt_percent(variance_pct))
        if variance_pct is None:
            variance_label.setStyleSheet("color: #111827;")
        else:
            try:
                val = Decimal(variance_pct)
                color = "#166534" if val >= 0 else "#991b1b"
            except Exception:
                color = "#111827"
            variance_label.setStyleSheet(f"color: {color};")

    # ------------------------------------------------------------------ actions
    def _open_edit_dialog(self) -> None:
        detail = self._detail
        if detail is None:
            return
        updated = ProjectFormDialog.edit_project(
            self._service_registry,
            company_id=self._company_id,
            company_name=self._company_name,
            project_id=detail.id,
            parent=self,
        )
        if updated is not None:
            self._reload_detail()

    def _open_jobs(self) -> None:
        detail = self._detail
        if detail is None:
            return
        ProjectJobsDialog.manage_jobs(
            self._service_registry,
            company_id=self._company_id,
            project_id=detail.id,
            project_code=detail.project_code,
            parent=self,
        )
        self._reload_detail()

    def _open_cost_codes(self) -> None:
        ProjectCostCodesDialog.manage_cost_codes(
            self._service_registry,
            company_id=self._company_id,
            company_name=self._company_name,
            parent=self,
        )

    def _open_budgets(self) -> None:
        detail = self._detail
        if detail is None:
            return
        BudgetVersionsDialog.manage_versions(
            self._service_registry,
            company_id=self._company_id,
            project_id=detail.id,
            project_code=detail.project_code,
            parent=self,
        )
        self._reload_detail()

    def _open_new_budget(self) -> None:
        detail = self._detail
        if detail is None:
            return
        result = BudgetEditorDialog.create(
            self._service_registry,
            company_id=self._company_id,
            project_id=detail.id,
            parent=self,
        )
        if result is not None:
            self._reload_detail()

    def _open_revise_budget(self) -> None:
        detail = self._detail
        if detail is None:
            return
        result = BudgetEditorDialog.revise_from_approved(
            self._service_registry,
            company_id=self._company_id,
            project_id=detail.id,
            parent=self,
        )
        if result is not None:
            self._reload_detail()

    def _open_commitments(self) -> None:
        detail = self._detail
        if detail is None:
            return
        ProjectCommitmentsDialog.manage_commitments(
            self._service_registry,
            company_id=self._company_id,
            project_id=detail.id,
            project_code=detail.project_code,
            parent=self,
        )
        self._reload_detail()

    def _open_record_cost(self) -> None:
        detail = self._detail
        if detail is None:
            return
        if detail.status_code not in {"active", "on_hold"}:
            show_info(
                self,
                "Record Cost",
                "Costs can only be recorded while the project is active or on hold.",
            )
            return
        show_info(
            self,
            "Record Cost",
            (
                f"A new journal entry will open. Tag each expense line to project "
                f"'{detail.project_code}' via the line allocation button to charge the cost here."
            ),
        )
        saved = JournalEntryDialog.create_journal(
            self._service_registry,
            self._company_id,
            self._company_name,
            parent=self,
        )
        if saved is not None:
            self._reload_detail()

    def _open_variance(self) -> None:
        self._service_registry.navigation_service.navigate(
            nav_ids.PROJECT_VARIANCE_ANALYSIS,
            context={"project_id": self._project_id},
        )

    def _open_contract_summary(self) -> None:
        detail = self._detail
        if detail is None or detail.contract_id is None:
            show_info(self, "Project Workspace", "This project is not linked to a contract.")
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.CONTRACT_SUMMARY,
            context={"contract_id": detail.contract_id},
        )

    def _change_status(self, *, title: str, prompt: str, service_call) -> None:
        detail = self._detail
        if detail is None:
            return
        choice = QMessageBox.question(
            self,
            title,
            prompt.format(code=detail.project_code),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            service_call(detail.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Project Workspace", str(exc))
            return
        self._reload_detail()
