from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.modules.reporting.dto.payroll_summary_report_dto import (
    PayrollSummaryReportDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)
from seeker_accounting.modules.reporting.ui.dialogs.report_print_preview_dialog import (
    ReportPrintPreviewDialog,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_context_strip import (
    ReportingContextStrip,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_empty_state import (
    ReportingEmptyState,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_run_employee_detail_dialog import (
    PayrollRunEmployeeDetailDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_run_posting_detail_dialog import (
    PayrollRunPostingDetailDialog,
)
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table
from seeker_accounting.platform.exceptions import ValidationError

_ZERO = Decimal("0.00")


class PayrollSummaryWindow(QFrame):
    """Focused child window for payroll summary reporting."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | OperationalReportFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._active_company_context = service_registry.active_company_context
        self._report_service = service_registry.payroll_summary_report_service
        self._payroll_run_service = service_registry.payroll_run_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )
        self._current_filter = self._coerce_filter(company_id, initial_filter)
        self._current_report: PayrollSummaryReportDTO | None = None

        self.setObjectName("PayrollSummaryWindow")
        self.setWindowTitle("Payroll Summary")
        self.setMinimumSize(960, 620)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(ReportingContextStrip(self._context_service, service_registry, self))
        root.addWidget(self._build_controls())
        root.addWidget(self._build_summary_strip())
        root.addWidget(self._build_stack(), 1)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._load_runs()
        self._apply_filter_to_controls()
        self._load_report()

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(4)
        eyebrow = QLabel("Operational Reports | Payroll", card)
        eyebrow.setProperty("role", "caption")
        layout.addWidget(eyebrow)
        title = QLabel("Payroll Summary", card)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Posted payroll runs with gross pay, deductions, employer cost, net pay, employee summaries, and statutory visibility.",
            card,
        )
        subtitle.setObjectName("PageSummary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return card

    def _build_controls(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        run_label = QLabel("Run", card)
        run_label.setProperty("role", "caption")
        layout.addWidget(run_label)

        self._run_combo = QComboBox(card)
        self._run_combo.setMinimumWidth(320)
        layout.addWidget(self._run_combo)

        from_label = QLabel("From", card)
        from_label.setProperty("role", "caption")
        layout.addWidget(from_label)

        self._from_edit = QDateEdit(card)
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setFixedWidth(124)
        layout.addWidget(self._from_edit)

        to_label = QLabel("To", card)
        to_label.setProperty("role", "caption")
        layout.addWidget(to_label)

        self._to_edit = QDateEdit(card)
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setFixedWidth(124)
        layout.addWidget(self._to_edit)

        layout.addStretch(1)

        refresh = QPushButton("Refresh", card)
        refresh.setProperty("variant", "primary")
        refresh.clicked.connect(self._on_refresh)
        layout.addWidget(refresh)

        print_btn = QPushButton("Print Preview", card)
        print_btn.setProperty("variant", "secondary")
        print_btn.clicked.connect(self._on_print_preview)
        layout.addWidget(print_btn)
        return card

    def _build_summary_strip(self) -> QWidget:
        strip = QWidget(self)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(8)
        self._summary_values: dict[str, QLabel] = {}
        for key, title in (
            ("gross", "Gross Pay"),
            ("deductions", "Deductions"),
            ("employer_cost", "Employer Cost"),
            ("net", "Net Pay"),
            ("paid", "Paid"),
            ("outstanding", "Outstanding"),
        ):
            card = QFrame(strip)
            card.setObjectName("InfoCard")
            card.setProperty("card", True)
            card.setFixedHeight(34)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(10, 0, 10, 0)
            card_layout.setSpacing(8)
            caption = QLabel(title, card)
            caption.setProperty("role", "caption")
            card_layout.addWidget(caption)
            card_layout.addStretch(1)
            value = QLabel("0.00", card)
            value.setObjectName("InfoCardTitle")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            card_layout.addWidget(value)
            layout.addWidget(card, 1)
            self._summary_values[key] = value
        return strip

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_tab_panel())
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Active Company",
                message="Select an active company before opening payroll summaries.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Payroll Data",
                message="No posted payroll runs were found for the selected filter.",
                parent=self,
            )
        )
        return self._stack

    def _build_tab_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 0, 20, 20)
        tabs = QTabWidget(panel)
        tabs.addTab(self._build_runs_table(tabs), "Runs")
        tabs.addTab(self._build_employees_table(tabs), "Employees")
        tabs.addTab(self._build_statutory_table(tabs), "Statutory")
        layout.addWidget(tabs, 1)
        return panel

    def _build_runs_table(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self._runs_table = QTableWidget(panel)
        self._runs_table.setColumnCount(10)
        self._runs_table.setHorizontalHeaderLabels(
            ["Period", "Run", "Status", "Employees", "Gross", "Deductions", "Employer Cost", "Net", "Paid", "Outstanding"]
        )
        configure_compact_table(self._runs_table)
        self._runs_table.cellDoubleClicked.connect(self._on_run_double_clicked)
        layout.addWidget(self._runs_table, 1)
        return panel

    def _build_employees_table(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self._employees_table = QTableWidget(panel)
        self._employees_table.setColumnCount(5)
        self._employees_table.setHorizontalHeaderLabels(["Employee", "Gross", "Deductions", "Employer Cost", "Net"])
        configure_compact_table(self._employees_table)
        self._employees_table.cellDoubleClicked.connect(self._on_employee_double_clicked)
        layout.addWidget(self._employees_table, 1)
        return panel

    def _build_statutory_table(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self._statutory_table = QTableWidget(panel)
        self._statutory_table.setColumnCount(5)
        self._statutory_table.setHorizontalHeaderLabels(["Authority", "Due", "Remitted", "Outstanding", "Batches"])
        configure_compact_table(self._statutory_table)
        layout.addWidget(self._statutory_table, 1)
        return panel

    def _load_runs(self) -> None:
        company_id = self._active_company_context.company_id or self._current_filter.company_id
        self._run_combo.blockSignals(True)
        self._run_combo.clear()
        self._run_combo.addItem("All Posted Runs", None)
        if isinstance(company_id, int) and company_id > 0:
            for row in self._payroll_run_service.list_runs(company_id, status_code="posted"):
                label = f"{row.run_reference} - {row.run_label} ({row.period_month:02d}/{row.period_year})"
                self._run_combo.addItem(label, row.id)
        self._run_combo.blockSignals(False)

    def _apply_filter_to_controls(self) -> None:
        if self._current_filter.date_from is not None:
            self._from_edit.setDate(QDate(self._current_filter.date_from.year, self._current_filter.date_from.month, self._current_filter.date_from.day))
        if self._current_filter.date_to is not None:
            self._to_edit.setDate(QDate(self._current_filter.date_to.year, self._current_filter.date_to.month, self._current_filter.date_to.day))
        if self._current_filter.payroll_run_id is not None:
            index = self._run_combo.findData(self._current_filter.payroll_run_id)
            if index >= 0:
                self._run_combo.setCurrentIndex(index)

    def _load_report(self) -> None:
        company_id = self._current_filter.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            self._current_report = None
            self._runs_table.setRowCount(0)
            self._employees_table.setRowCount(0)
            self._statutory_table.setRowCount(0)
            self._update_summary(
                PayrollSummaryReportDTO(
                    company_id=0,
                    date_from=self._current_filter.date_from,
                    date_to=self._current_filter.date_to,
                    selected_run_id=self._current_filter.payroll_run_id,
                )
            )
            self._stack.setCurrentIndex(1)
            return
        try:
            report = self._report_service.get_report(self._current_filter)
        except ValidationError as exc:
            show_error(self, "Payroll Summary", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Payroll Summary", str(exc))
            return

        self._current_report = report
        self._update_summary(report)
        if not report.has_data:
            self._runs_table.setRowCount(0)
            self._employees_table.setRowCount(0)
            self._statutory_table.setRowCount(0)
            self._stack.setCurrentIndex(2)
            return
        self._bind_runs(report)
        self._bind_employees(report)
        self._bind_statutory(report)
        self._stack.setCurrentIndex(0)

    def _update_summary(self, report: PayrollSummaryReportDTO) -> None:
        self._summary_values["gross"].setText(self._fmt(report.total_gross_pay))
        self._summary_values["deductions"].setText(self._fmt(report.total_deductions))
        self._summary_values["employer_cost"].setText(self._fmt(report.total_employer_cost))
        self._summary_values["net"].setText(self._fmt(report.total_net_pay))
        self._summary_values["paid"].setText(self._fmt(report.total_paid))
        self._summary_values["outstanding"].setText(self._fmt(report.total_outstanding))

    def _bind_runs(self, report: PayrollSummaryReportDTO) -> None:
        self._runs_table.setRowCount(len(report.run_rows))
        for row_index, row in enumerate(report.run_rows):
            period_item = QTableWidgetItem(f"{row.period_month:02d}/{row.period_year}")
            period_item.setData(Qt.ItemDataRole.UserRole, row.run_id)
            self._runs_table.setItem(row_index, 0, period_item)
            self._runs_table.setItem(row_index, 1, QTableWidgetItem(f"{row.run_reference} - {row.run_label}"))
            self._runs_table.setItem(row_index, 2, QTableWidgetItem(row.status_code.upper()))
            self._runs_table.setItem(row_index, 3, QTableWidgetItem(str(row.employee_count)))
            self._set_amount(self._runs_table, row_index, 4, row.gross_pay)
            self._set_amount(self._runs_table, row_index, 5, row.deductions)
            self._set_amount(self._runs_table, row_index, 6, row.employer_cost)
            self._set_amount(self._runs_table, row_index, 7, row.net_pay)
            self._set_amount(self._runs_table, row_index, 8, row.total_paid)
            self._set_amount(self._runs_table, row_index, 9, row.outstanding_net_pay)

    def _bind_employees(self, report: PayrollSummaryReportDTO) -> None:
        self._employees_table.setRowCount(len(report.employee_rows))
        for row_index, row in enumerate(report.employee_rows):
            employee_item = QTableWidgetItem(f"{row.employee_number} - {row.employee_name}")
            employee_item.setData(Qt.ItemDataRole.UserRole, row.run_employee_id)
            self._employees_table.setItem(row_index, 0, employee_item)
            self._set_amount(self._employees_table, row_index, 1, row.gross_pay)
            self._set_amount(self._employees_table, row_index, 2, row.deductions)
            self._set_amount(self._employees_table, row_index, 3, row.employer_cost)
            self._set_amount(self._employees_table, row_index, 4, row.net_pay)

    def _bind_statutory(self, report: PayrollSummaryReportDTO) -> None:
        self._statutory_table.setRowCount(len(report.statutory_rows))
        for row_index, row in enumerate(report.statutory_rows):
            self._statutory_table.setItem(row_index, 0, QTableWidgetItem(row.authority_label))
            self._set_amount(self._statutory_table, row_index, 1, row.total_due)
            self._set_amount(self._statutory_table, row_index, 2, row.total_remitted)
            self._set_amount(self._statutory_table, row_index, 3, row.outstanding)
            self._statutory_table.setItem(row_index, 4, QTableWidgetItem(str(row.batch_count)))

    def _set_amount(self, table: QTableWidget, row_index: int, column_index: int, amount: Decimal) -> None:
        item = QTableWidgetItem(self._fmt(amount))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_index, column_index, item)

    def _on_refresh(self) -> None:
        run_id = self._run_combo.currentData()
        self._current_filter = OperationalReportFilterDTO(
            company_id=self._active_company_context.company_id,
            date_from=self._to_python_date(self._from_edit.date()),
            date_to=self._to_python_date(self._to_edit.date()),
            payroll_run_id=run_id if isinstance(run_id, int) else None,
            posted_only=True,
        )
        self._load_report()

    def _on_print_preview(self) -> None:
        if self._current_report is None:
            return
        preview = self._report_service.build_print_preview_meta(
            self._current_report,
            self._active_company_context.company_name or "Unknown Company",
        )
        ReportPrintPreviewDialog.show_preview(preview, parent=self)

    def _on_run_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        run_item = self._runs_table.item(row, 0)
        if run_item is None:
            return
        run_id = run_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(run_id, int):
            PayrollRunPostingDetailDialog(self._service_registry, self._current_filter.company_id or 0, run_id, self).exec()

    def _on_employee_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        employee_item = self._employees_table.item(row, 0)
        if employee_item is None:
            return
        run_employee_id = employee_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(run_employee_id, int):
            PayrollRunEmployeeDetailDialog(self._service_registry, self._current_filter.company_id or 0, run_employee_id, self).exec()

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if isinstance(company_id, int) and company_id > 0:
            self._current_filter = OperationalReportFilterDTO(
                company_id=company_id,
                date_from=self._current_filter.date_from,
                date_to=self._current_filter.date_to,
                posted_only=True,
            )
            self._load_runs()
            self._apply_filter_to_controls()
            self._load_report()

    @staticmethod
    def _coerce_filter(
        company_id: int | None,
        initial_filter: ReportingFilterDTO | OperationalReportFilterDTO | None,
    ) -> OperationalReportFilterDTO:
        if isinstance(initial_filter, OperationalReportFilterDTO):
            return OperationalReportFilterDTO(
                company_id=company_id or initial_filter.company_id,
                date_from=initial_filter.date_from,
                date_to=initial_filter.date_to or initial_filter.as_of_date,
                payroll_run_id=initial_filter.payroll_run_id,
                posted_only=True,
            )
        if isinstance(initial_filter, ReportingFilterDTO):
            return OperationalReportFilterDTO(
                company_id=company_id or initial_filter.company_id,
                date_from=initial_filter.date_from,
                date_to=initial_filter.date_to,
                posted_only=True,
            )
        today = date.today()
        return OperationalReportFilterDTO(company_id=company_id, date_from=today.replace(day=1), date_to=today, posted_only=True)

    @staticmethod
    def _to_python_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | OperationalReportFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        window = cls(service_registry, company_id, initial_filter=initial_filter, parent=parent)
        window.show()
