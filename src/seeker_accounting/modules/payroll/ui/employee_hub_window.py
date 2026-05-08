"""EmployeeHubWindow — compact full-window workbench for a payroll employee.

Serves as the single place to inspect and manage everything about an
employee from a payroll point of view:

* Identity & contact (name, employee number, department/position, tax /
  CNPS / payment account).
* Payroll readiness strip (Tax & CNPS, Payment, Compensation, Components)
  driven by the same gap scan used by
  :class:`EmployeePayrollSetupWizardDialog`.
* Compensation profiles (compact table with profile name).
* Recurring component assignments (compact table with friendly type labels).
* YTD earnings summary (current-year totals from posted/approved runs).
* Recent payroll runs (compact table with payment status; double-click to
  open payslip preview). Uses a single JOIN query — no N+1 loading.

Ribbon actions: Edit Employee · Payroll Setup Wizard · Compensation
Change · Assign Component · Queue Correction · Terminate/Rehire · Refresh · Close.

Registered under the child-window key ``child:payroll_employee_hub``.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.child_windows.child_window_base import ChildWindowBase
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.modules.payroll.dto.employee_dto import (
    EmployeeDetailDTO,
    EmployeeListItemDTO,
)
from seeker_accounting.modules.payroll.ui.bp.employee_termination_wizard import (
    TerminateEmployeeWizardDialog,
)
from seeker_accounting.modules.payroll.ui.bp.employee_rehire_wizard import (
    RehireEmployeeWizardDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.component_assignment_dialog import (
    ComponentAssignmentDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.employee_form_dialog import (
    EmployeeFormDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_correction_dialog import (
    PayrollCorrectionDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payslip_preview_dialog import (
    PayslipPreviewDialog,
)
from seeker_accounting.modules.payroll.ui.wizards.compensation_change_wizard import (
    CompensationChangeWizardDialog,
)
from seeker_accounting.modules.payroll.ui.wizards.employee_payroll_setup_wizard import (
    EmployeePayrollSetupWizardDialog,
)
from seeker_accounting.platform.exceptions import (
    AppError,
    NotFoundError,
    PermissionDeniedError,
)
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.components.read_only_table_model import ReadOnlyTableModel
from seeker_accounting.shared.ui.styles.inline_styles import status_chip_style, text_style
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


_log = logging.getLogger(__name__)


_RUN_STATUS_LABELS = {
    "draft": "Draft",
    "calculated": "Calculated",
    "submitted_for_review": "In Review",
    "approved": "Approved",
    "posted": "Posted",
    "reversed": "Reversed",
    "voided": "Voided",
}

_PAYMENT_STATUS_LABELS = {
    "unpaid": "Unpaid",
    "partial": "Partial",
    "paid": "Paid",
}

_COMPONENT_TYPE_LABELS = {
    "earning": "Earning",
    "deduction": "Deduction",
    "employer_contribution": "Employer Contribution",
    "tax": "Tax",
    "informational": "Informational",
}

_MONTHS = (
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# Run statuses to include in YTD summary
_YTD_STATUSES = {"calculated", "submitted_for_review", "approved", "posted"}


class EmployeeHubWindow(ChildWindowBase):
    """Full-window hub for managing a single employee's payroll profile."""

    DOC_TYPE = "payroll_employee_hub"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        employee_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title="Employee Hub",
            surface_key=RibbonRegistry.child_window_key(self.DOC_TYPE),
            window_key=(self.DOC_TYPE, employee_id),
            registry=service_registry.ribbon_registry or RibbonRegistry(),
            icon_provider=IconProvider(service_registry.theme_manager),
            parent=parent,
        )
        self._registry = service_registry
        self._company_id = company_id
        self._employee_id = employee_id
        self._company_name = self._lookup_company_name(company_id)

        self._employee: EmployeeDetailDTO | None = None
        self._gaps: dict[str, bool] = {}
        self._profiles: list = []
        self._assignments: list = []
        # List of (PayrollRunListItemDTO, PayrollRunEmployeeListItemDTO) tuples
        self._recent_runs: list[tuple] = []
        self._pending_corrections_count: int = 0

        self.set_body(self._build_body())
        self._reload()

    # ── Helpers ───────────────────────────────────────────────────────

    def _lookup_company_name(self, company_id: int) -> str:
        try:
            company = self._registry.company_service.get_company(company_id)
            return getattr(company, "company_name", "") or getattr(company, "name", "")
        except Exception:  # noqa: BLE001
            return ""

    def _to_list_item_dto(self, emp: EmployeeDetailDTO) -> EmployeeListItemDTO:
        """Convert EmployeeDetailDTO → EmployeeListItemDTO for wizard calls."""
        return EmployeeListItemDTO(
            id=emp.id,
            company_id=emp.company_id,
            employee_number=emp.employee_number,
            display_name=emp.display_name,
            first_name=emp.first_name,
            last_name=emp.last_name,
            department_id=emp.department_id,
            department_name=emp.department_name,
            position_id=emp.position_id,
            position_name=emp.position_name,
            hire_date=emp.hire_date,
            termination_date=emp.termination_date,
            base_currency_code=emp.base_currency_code,
            is_active=emp.is_active,
        )

    # ── Body layout ───────────────────────────────────────────────────

    def _build_body(self) -> QWidget:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(self._build_hero())
        root.addWidget(self._build_readiness_strip())

        grid_host = QFrame(body)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        grid.addWidget(self._build_identity_card(), 0, 0)
        grid.addWidget(self._build_profiles_card(), 0, 1)
        grid.addWidget(self._build_assignments_card(), 0, 2)
        # Identity card doesn't need as much width as the tables.
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 4)
        root.addWidget(grid_host, 1)

        root.addWidget(self._build_ytd_row())
        root.addWidget(self._build_recent_runs_card())

        return body

    def _build_hero(self) -> QWidget:
        hero = QFrame(self)
        hero.setObjectName("DialogSectionCard")
        hero.setProperty("card", True)
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._name_label = QLabel("Employee", hero)
        f = self._name_label.font()
        f.setPointSize(max(f.pointSize() + 4, 14))
        f.setBold(True)
        self._name_label.setFont(f)
        row.addWidget(self._name_label)

        self._number_chip = QLabel("", hero)
        self._number_chip.setObjectName("ChipNeutral")
        self._number_chip.setStyleSheet(
            status_chip_style("neutral", padding="2px 8px", font_weight=500)
        )
        row.addWidget(self._number_chip)

        self._status_chip = QLabel("", hero)
        self._status_chip.setObjectName("ChipStatus")
        row.addWidget(self._status_chip)
        row.addStretch(1)
        layout.addLayout(row)

        self._subtitle_label = QLabel("", hero)
        self._subtitle_label.setObjectName("DialogSectionSummary")
        layout.addWidget(self._subtitle_label)
        return hero

    def _build_readiness_strip(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("DialogSectionCard")
        frame.setProperty("card", True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        self._readiness_pills: dict[str, QLabel] = {}
        for label_text, key in (
            ("Tax & CNPS",  "tax_cnps"),
            ("Payment",     "payment"),
            ("Compensation","comp"),
            ("Components",  "components"),
        ):
            pill = QLabel(label_text, frame)
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setMinimumWidth(DEFAULT_TOKENS.sizes.nav_pill_min_w)
            self._readiness_pills[key] = pill
            layout.addWidget(pill)
        layout.addStretch(1)

        self._readiness_summary = QLabel("", frame)
        self._readiness_summary.setObjectName("DialogSectionSummary")
        layout.addWidget(self._readiness_summary)
        return frame

    def _build_identity_card(self) -> QWidget:
        card = self._card("Identity & Contact")
        self._identity_grid_host = QFrame(card)
        card.layout().addWidget(self._identity_grid_host)
        return card

    def _build_profiles_card(self) -> QWidget:
        card = self._card("Compensation")
        self._profiles_model = ReadOnlyTableModel(
            ["Name", "From", "Salary", "Currency", "Status"],
            right_align_cols=frozenset({2}),
        )
        self._profiles_table = QTableView(card)
        configure_compact_table(self._profiles_table)
        self._profiles_table.setModel(self._profiles_model)
        hdr = self._profiles_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        card.layout().addWidget(self._profiles_table, 1)
        return card

    def _build_assignments_card(self) -> QWidget:
        card = self._card("Component assignments")
        self._assignments_model = ReadOnlyTableModel(
            ["Payroll component", "Type", "From", "Status"]
        )
        self._assignments_table = QTableView(card)
        configure_compact_table(self._assignments_table)
        self._assignments_table.setModel(self._assignments_model)
        hdr = self._assignments_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        card.layout().addWidget(self._assignments_table, 1)
        return card

    def _build_ytd_row(self) -> QWidget:
        """Compact YTD summary bar shown above the runs table."""
        frame = QFrame(self)
        frame.setObjectName("DialogSectionCard")
        frame.setProperty("card", True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(24)

        self._ytd_year_label = QLabel("YTD", frame)
        self._ytd_year_label.setObjectName("DialogSectionTitle")
        layout.addWidget(self._ytd_year_label)
        layout.addStretch(1)

        for attr, caption in (
            ("_ytd_gross_label", "Gross"),
            ("_ytd_net_label", "Net"),
            ("_ytd_runs_label", "Runs"),
        ):
            col = QVBoxLayout()
            col.setSpacing(1)
            cap = QLabel(caption, frame)
            cap.setStyleSheet(text_style("muted", font_size="10px"))
            cap.setAlignment(Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014", frame)
            val.setObjectName("DialogSectionTitle")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            setattr(self, attr, val)
            col.addWidget(cap)
            col.addWidget(val)
            layout.addLayout(col)

        return frame

    def _build_recent_runs_card(self) -> QWidget:
        card = self._card("Recent payroll runs")
        # Count label on the right side of the card header
        hrow = QHBoxLayout()
        hrow.setContentsMargins(0, 0, 0, 0)
        self._runs_count_label = QLabel("", card)
        self._runs_count_label.setStyleSheet(text_style("muted", font_size="11px"))
        hrow.addStretch(1)
        hrow.addWidget(self._runs_count_label)
        card.layout().addLayout(hrow)

        self._runs_model = ReadOnlyTableModel(
            ["Run", "Period", "Gross", "Net", "Payment", "Status"],
            right_align_cols=frozenset({2, 3}),
        )
        self._runs_table = QTableView(card)
        configure_compact_table(self._runs_table)
        self._runs_table.setModel(self._runs_model)
        hdr = self._runs_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._runs_table.doubleClicked.connect(self._on_runs_table_double_clicked)
        card.layout().addWidget(self._runs_table, 1)
        return card

    def _card(self, title: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(8)
        tlabel = QLabel(title, card)
        tlabel.setObjectName("DialogSectionTitle")
        layout.addWidget(tlabel)
        return card

    # ── Data ──────────────────────────────────────────────────────────

    def _reload(self) -> None:
        try:
            emp = self._registry.employee_service.get_employee(
                self._company_id, self._employee_id,
            )
        except NotFoundError:
            show_error(self, "Employee Hub", "This employee no longer exists.")
            self.close()
            return
        except AppError as exc:
            show_error(self, "Employee Hub", str(exc))
            return
        except Exception:
            _log.exception("Failed to load employee hub for employee=%s", self._employee_id)
            show_error(self, "Employee Hub", "Could not load employee. See application log for details.")
            return
        self._employee = emp
        self.setWindowTitle(f"Employee Hub — {emp.display_name}")
        self._name_label.setText(emp.display_name)
        self._number_chip.setText(emp.employee_number)
        self._number_chip.setStyleSheet(
            status_chip_style("neutral", padding="2px 8px", radius=8)
        )

        active = emp.is_active
        self._status_chip.setText("Active" if active else "Inactive")
        self._status_chip.setStyleSheet(
            status_chip_style(
                "success" if active else "danger",
                padding="2px 10px",
                radius=8,
            )
        )

        dept = emp.department_name or "—"
        pos = emp.position_name or "—"
        company_hint = f" · {self._company_name}" if self._company_name else ""
        self._subtitle_label.setText(
            f"{dept}  ·  {pos}  ·  Hired {emp.hire_date.isoformat()}"
            + (f"  ·  Terminated {emp.termination_date.isoformat()}"
               if emp.termination_date else "")
            + company_hint
        )

        self._load_corrections_count()
        self._refresh_identity_grid()
        self._load_profiles_and_assignments()
        self._scan_gaps()
        self._refresh_readiness()
        self._load_recent_runs()
        self.refresh_ribbon_state()

    def _refresh_identity_grid(self) -> None:
        # Clear the host and rebuild a tight grid.
        old = self._identity_grid_host.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget() if item else None
                if w is not None:
                    w.setParent(None)
            QWidget().setLayout(old)

        grid = QGridLayout(self._identity_grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        emp = self._employee
        assert emp is not None

        acct_label = "—"
        if emp.default_payment_account_id is not None:
            try:
                accts = (
                    self._registry.financial_account_service
                    .list_financial_accounts(self._company_id, active_only=False)
                )
                match = next(
                    (a for a in accts if a.id == emp.default_payment_account_id), None,
                )
                if match is not None:
                    acct_label = match.name
            except Exception:  # noqa: BLE001
                acct_label = f"#{emp.default_payment_account_id}"

        rows: list[tuple[str, str, str]] = [
            ("Email",           emp.email or "—",           "primary"),
            ("Phone",           emp.phone or "—",           "primary"),
            ("Tax ID",          emp.tax_identifier or "—",  "primary"),
            ("CNPS",            emp.cnps_number or "—",     "primary"),
            ("Currency",        emp.base_currency_code,     "primary"),
            ("Payment account", acct_label,                 "primary"),
        ]
        if self._pending_corrections_count > 0:
            rows.append((
                "Pending corrections",
                str(self._pending_corrections_count),
                "warning",
            ))

        label_style = text_style("muted")
        for i, (label, value, role) in enumerate(rows):
            lab = QLabel(label, self._identity_grid_host)
            lab.setStyleSheet(label_style)
            val = QLabel(value, self._identity_grid_host)
            val.setWordWrap(True)
            if role != "primary":
                val.setStyleSheet(text_style(role, font_weight=600))
            grid.addWidget(lab, i, 0)
            grid.addWidget(val, i, 1)
        grid.setColumnStretch(1, 1)

    def _load_profiles_and_assignments(self) -> None:
        try:
            self._profiles = (
                self._registry.compensation_profile_service.list_profiles(
                    self._company_id, employee_id=self._employee_id, active_only=False,
                )
            )
        except Exception:  # noqa: BLE001
            self._profiles = []
        try:
            self._assignments = (
                self._registry.component_assignment_service.list_assignments(
                    self._company_id, employee_id=self._employee_id, active_only=False,
                )
            )
        except Exception:  # noqa: BLE001
            self._assignments = []

        profiles_sorted = sorted(self._profiles, key=lambda x: x.effective_from, reverse=True)
        self._profiles_model.reset_data(
            [
                [
                    p.profile_name,
                    p.effective_from.isoformat(),
                    f"{p.basic_salary:,.2f}",
                    p.currency_code,
                    "Active" if p.is_active else "Inactive",
                ]
                for p in profiles_sorted
            ]
        )

        assignments_sorted = sorted(self._assignments, key=lambda x: x.effective_from, reverse=True)
        self._assignments_model.reset_data(
            [
                [
                    a.component_name,
                    _COMPONENT_TYPE_LABELS.get(a.component_type_code, a.component_type_code),
                    a.effective_from.isoformat(),
                    "Active" if a.is_active else "Inactive",
                ]
                for a in assignments_sorted
            ]
        )

    def _scan_gaps(self) -> None:
        emp = self._employee
        assert emp is not None
        today = date.today()

        tax_missing = not (emp.tax_identifier and emp.cnps_number)
        payment_missing = emp.default_payment_account_id is None

        has_comp = any(
            p.effective_from <= today
            and (p.effective_to is None or p.effective_to >= today)
            and p.is_active
            for p in self._profiles
        )
        has_assignments = any(a.is_active for a in self._assignments)

        self._gaps = {
            "tax_cnps":   tax_missing,
            "payment":    payment_missing,
            "comp":       not has_comp,
            "components": not has_assignments,
        }

    def _load_corrections_count(self) -> None:
        """Load pending corrections count (best-effort; permission failure is silent)."""
        try:
            corrections = self._registry.payroll_correction_service.list_employee_corrections(
                self._company_id, self._employee_id, status_code="pending"
            )
            self._pending_corrections_count = len(corrections)
        except PermissionDeniedError:
            self._pending_corrections_count = 0
        except Exception:  # noqa: BLE001
            self._pending_corrections_count = 0

    def _refresh_readiness(self) -> None:
        labels_map = {
            "tax_cnps":   "Tax & CNPS",
            "payment":    "Payment",
            "comp":       "Compensation",
            "components": "Components",
        }
        for key, pill in self._readiness_pills.items():
            missing = self._gaps.get(key, False)
            badge = "⚠ " if missing else "✓ "
            pill.setText(badge + labels_map[key])
            pill.setStyleSheet(
                status_chip_style(
                    "warning" if missing else "success",
                    padding="4px 10px",
                    radius=8,
                )
            )

        gap_count = sum(1 for v in self._gaps.values() if v)
        self._readiness_summary.setText(
            "Payroll-ready"
            if gap_count == 0
            else f"{gap_count} gap(s) — run Payroll Setup to fill them in."
        )

    def _load_recent_runs(self) -> None:
        """Single-query JOIN to fetch run history for this employee (no N+1)."""
        self._recent_runs = []
        try:
            pairs = self._registry.payroll_run_service.list_employee_run_history(
                self._company_id, self._employee_id, limit=20,
            )
            self._recent_runs = pairs
        except Exception:  # noqa: BLE001
            _log.debug("Could not load run history for employee=%s", self._employee_id)

        # YTD computation: sum for current year, only meaningful statuses
        today = date.today()
        ytd_gross = Decimal("0")
        ytd_net = Decimal("0")
        ytd_run_count = 0
        for run_dto, emp_dto in self._recent_runs:
            if (
                run_dto.period_year == today.year
                and run_dto.status_code in _YTD_STATUSES
            ):
                ytd_gross += emp_dto.gross_earnings
                ytd_net += emp_dto.net_payable
                ytd_run_count += 1

        self._ytd_year_label.setText(f"YTD {today.year}")
        self._ytd_gross_label.setText(f"{ytd_gross:,.0f}" if ytd_run_count else "\u2014")
        self._ytd_net_label.setText(f"{ytd_net:,.0f}" if ytd_run_count else "\u2014")
        self._ytd_runs_label.setText(str(ytd_run_count) if ytd_run_count else "\u2014")

        rows_data = []
        for run_dto, emp_dto in self._recent_runs:
            period_name = _MONTHS[run_dto.period_month] if 1 <= run_dto.period_month <= 12 else ""
            pay_status = _PAYMENT_STATUS_LABELS.get(
                emp_dto.payment_status_code, emp_dto.payment_status_code
            )
            rows_data.append([
                run_dto.run_reference,
                f"{period_name} {run_dto.period_year}",
                f"{emp_dto.gross_earnings:,.2f}",
                f"{emp_dto.net_payable:,.2f}",
                pay_status,
                _RUN_STATUS_LABELS.get(run_dto.status_code, run_dto.status_code),
            ])
        self._runs_model.reset_data(rows_data)

        count = len(self._recent_runs)
        self._runs_count_label.setText(
            f"Last {count} run{'s' if count != 1 else ''}" if count else "No runs"
        )

    # ── Ribbon host ───────────────────────────────────────────────────

    def handle_ribbon_command(self, command_id: str) -> None:  # type: ignore[override]
        dispatch = {
            "payroll_employee_hub.edit":                 self._on_edit,
            "payroll_employee_hub.payroll_setup_wizard": self._on_payroll_setup,
            "payroll_employee_hub.compensation_change":  self._on_compensation_change,
            "payroll_employee_hub.new_assignment":       self._on_new_assignment,
            "payroll_employee_hub.queue_correction":     self._on_queue_correction,
            "payroll_employee_hub.deactivate":           self._on_terminate,
            "payroll_employee_hub.reactivate":           self._on_rehire,
            "payroll_employee_hub.refresh":              self._reload,
            "payroll_employee_hub.close":                self.close,
        }
        handler = dispatch.get(command_id)
        if handler is not None:
            handler()

    def ribbon_state(self) -> dict[str, bool]:  # type: ignore[override]
        loaded = self._employee is not None
        active = bool(self._employee and self._employee.is_active)
        return {
            "payroll_employee_hub.edit":                 loaded,
            "payroll_employee_hub.payroll_setup_wizard": loaded and active,
            "payroll_employee_hub.compensation_change":  loaded and active,
            "payroll_employee_hub.new_assignment":       loaded and active,
            "payroll_employee_hub.queue_correction":     loaded and active,
            "payroll_employee_hub.deactivate":           loaded and active,
            "payroll_employee_hub.reactivate":           loaded and not active,
            "payroll_employee_hub.refresh":              True,
            "payroll_employee_hub.close":                True,
        }

    # ── Command handlers ──────────────────────────────────────────────

    def _on_edit(self) -> None:
        dlg = EmployeeFormDialog(
            self._registry,
            self._company_id,
            self._company_name,
            employee_id=self._employee_id,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_payroll_setup(self) -> None:
        result = EmployeePayrollSetupWizardDialog.run(
            self._registry,
            self._company_id,
            self._company_name,
            employee_id=self._employee_id,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _on_compensation_change(self) -> None:
        result = CompensationChangeWizardDialog.run(
            self._registry,
            self._company_id,
            self._company_name,
            employee_id=self._employee_id,
            parent=self,
        )
        if result is not None:
            self._reload()

    def _on_new_assignment(self) -> None:
        dlg = ComponentAssignmentDialog(
            self._registry,
            self._company_id,
            self._employee_id,
            existing=None,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_queue_correction(self) -> None:
        emp = self._employee
        if emp is None or not emp.is_active:
            return
        today = date.today()
        dlg = PayrollCorrectionDialog(
            self._registry,
            self._company_id,
            employee_id=emp.id,
            employee_label=emp.display_name,
            period_year=today.year,
            period_month=today.month,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_terminate(self) -> None:
        """Open the Termination BP wizard (guided flow with reason capture)."""
        emp = self._employee
        if emp is None or not emp.is_active:
            return
        completed = TerminateEmployeeWizardDialog.run(
            self._registry,
            self._company_id,
            self._to_list_item_dto(emp),
            parent=self,
        )
        if completed:
            self._reload()

    def _on_rehire(self) -> None:
        """Open the Rehire BP wizard (guided flow)."""
        emp = self._employee
        if emp is None or emp.is_active:
            return
        completed = RehireEmployeeWizardDialog.run(
            self._registry,
            self._company_id,
            self._to_list_item_dto(emp),
            parent=self,
        )
        if completed:
            self._reload()

    # ── Runs table interaction ────────────────────────────────────

    def _on_runs_table_double_clicked(self) -> None:
        """Open payslip preview for the double-clicked run row."""
        indexes = self._runs_table.selectedIndexes()
        if not indexes:
            return
        row = indexes[0].row()
        if row < 0 or row >= len(self._recent_runs):
            return
        _run_dto, emp_dto = self._recent_runs[row]
        run_employee_id = emp_dto.id
        try:
            dlg = PayslipPreviewDialog(
                self._registry,
                self._company_id,
                run_employee_id,
                parent=self,
            )
            dlg.exec()
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Payslip Preview", f"Could not open payslip: {exc}")
