"""PayrollOperationsWorkspace — five-tab payroll operations workspace.

Tabs:
  1. Validation Dashboard  — comprehensive readiness checks for a payroll period
  2. Statutory Packs       — pack version list, rollover preview/execute
  3. Imports               — CSV import for departments, positions, employees
  4. Print                 — payslip and summary report printing
  5. Audit Log             — read-only payroll audit event viewer
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_validation_dashboard_dto import ValidationCheckDTO
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_AUDIT_VIEW
from seeker_accounting.modules.payroll.ui.dialogs.payroll_export_dialog import PayrollExportDialog
from seeker_accounting.modules.payroll.ui.dialogs.validation_check_detail_dialog import (
    ValidationCheckDetailDialog,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

_SEVERITY_COLORS = {
    "error": "#dc3545",
    "warning": "#fd7e14",
    "info": "#0d6efd",
}


class PayrollOperationsWorkspace(QWidget):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        stack: QStackedWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._stack = stack
        self._company_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Topbar ────────────────────────────────────────────────────────────
        topbar = QHBoxLayout()
        topbar.setContentsMargins(16, 8, 16, 8)
        topbar.setSpacing(10)

        title = QLabel("Payroll Operations")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        topbar.addWidget(title)
        topbar.addStretch()

        self._company_label = QLabel("No company selected")
        self._company_label.setStyleSheet("color: #666; font-size: 11px;")
        topbar.addWidget(self._company_label)
        root.addLayout(topbar)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        self._validation_tab = _ValidationTab(service_registry, self)
        self._packs_tab = _StatutoryPacksTab(service_registry, self)
        self._imports_tab = _ImportsTab(service_registry, self)
        self._print_tab = _PrintTab(service_registry, self)
        self._audit_tab = _AuditTab(service_registry, self)

        self._tabs.addTab(self._validation_tab, "Validation")
        self._tabs.addTab(self._packs_tab, "Statutory Packs")
        self._tabs.addTab(self._imports_tab, "Imports")
        self._tabs.addTab(self._print_tab, "Print")
        self._tabs.addTab(self._audit_tab, "Audit Log")

        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Auto-select company
        ctx = service_registry.app_context
        if ctx.active_company_id:
            self._set_company(ctx.active_company_id, ctx.active_company_name or "")

    # ── Company selection ─────────────────────────────────────────────────────

    def _set_company(self, company_id: int, company_name: str) -> None:
        self._company_id = company_id
        self._company_label.setText(company_name)
        self._validation_tab.set_company(company_id)
        self._packs_tab.set_company(company_id)
        self._imports_tab.set_company(company_id)
        self._print_tab.set_company(company_id)
        self._audit_tab.set_company(company_id)

    def _on_tab_changed(self, index: int) -> None:
        tab = self._tabs.widget(index)
        if hasattr(tab, "refresh") and self._company_id:
            tab.refresh()


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Validation Dashboard
# ══════════════════════════════════════════════════════════════════════════════


class _ValidationTab(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Period selector
        period_row = QHBoxLayout()
        period_row.setSpacing(8)
        period_row.addWidget(QLabel("Year:"))
        self._year_combo = QComboBox()
        now = datetime.now()
        for y in range(now.year - 2, now.year + 2):
            self._year_combo.addItem(str(y), y)
        self._year_combo.setCurrentText(str(now.year))
        period_row.addWidget(self._year_combo)

        period_row.addWidget(QLabel("Month:"))
        self._month_combo = QComboBox()
        for m, label in _MONTHS.items():
            self._month_combo.addItem(label, m)
        self._month_combo.setCurrentIndex(now.month - 1)
        period_row.addWidget(self._month_combo)

        self._btn_run = QPushButton("Run Assessment")
        self._btn_run.clicked.connect(self.refresh)
        period_row.addWidget(self._btn_run)
        period_row.addStretch()
        layout.addLayout(period_row)

        # Summary
        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet("font-size: 12px; padding: 4px;")
        layout.addWidget(self._summary_label)

        # Results table
        self._table = QTableWidget()
        cols = ["Severity", "Category", "Title", "Message", "Entity"]
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        configure_compact_table(self._table)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(self._on_check_double_clicked)

        hint = QLabel("Double-click a row to see full details and remediation steps.")
        hint.setStyleSheet("color: #888; font-size: 11px; padding: 1px 0 4px 0;")
        layout.addWidget(hint)
        layout.addWidget(self._table)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        if not self._company_id:
            return
        try:
            result = self._registry.payroll_validation_dashboard_service.run_full_assessment(
                self._company_id,
                self._year_combo.currentData(),
                self._month_combo.currentData(),
            )
        except Exception as exc:
            show_error(self, "Validation Error", str(exc))
            return

        # Summary
        if result.is_ready:
            self._summary_label.setText(
                f"<b style='color: #28a745;'>Ready</b> — "
                f"{result.ready_employee_count}/{result.employee_count} employees ready. "
                f"{result.warning_count} warning(s)."
            )
        else:
            self._summary_label.setText(
                f"<b style='color: #dc3545;'>Not Ready</b> — "
                f"{result.error_count} error(s), {result.warning_count} warning(s). "
                f"{result.ready_employee_count}/{result.employee_count} employees ready."
            )

        # Table
        self._table.setRowCount(len(result.checks))
        for row, check in enumerate(result.checks):
            color = _SEVERITY_COLORS.get(check.severity, "#333")
            sev_item = QTableWidgetItem(check.severity.upper())
            sev_item.setForeground(Qt.GlobalColor.white)
            sev_item.setData(Qt.ItemDataRole.UserRole, check)
            self._table.setItem(row, 0, sev_item)

            self._table.setItem(row, 1, QTableWidgetItem(check.category.title()))
            self._table.setItem(row, 2, QTableWidgetItem(check.title))
            self._table.setItem(row, 3, QTableWidgetItem(check.message))
            self._table.setItem(row, 4, QTableWidgetItem(check.entity_label or ""))

    def _on_check_double_clicked(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        check = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(check, ValidationCheckDTO):
            return
        dlg = ValidationCheckDetailDialog(check, parent=self)
        dlg.exec()


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Statutory Packs
# ══════════════════════════════════════════════════════════════════════════════


class _StatutoryPacksTab(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Packs table
        self._table = QTableWidget()
        cols = ["Pack Code", "Display Name", "Country", "Effective From", "Status"]
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        configure_compact_table(self._table)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self._table)

        # Actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_preview = QPushButton("Preview Rollover")
        self._btn_preview.clicked.connect(self._on_preview)
        btn_row.addWidget(self._btn_preview)

        self._btn_apply = QPushButton("Apply Selected Pack")
        self._btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self._btn_apply)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Preview result
        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet("font-size: 11px; padding: 6px; background: #f8f9fa; border-radius: 4px;")
        self._preview_label.hide()
        layout.addWidget(self._preview_label)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        if not self._company_id:
            return
        self._preview_label.hide()
        try:
            versions = self._registry.payroll_pack_version_service.list_available_versions(
                self._company_id
            )
        except Exception as exc:
            show_error(self, "Error", str(exc))
            return

        current = next((v for v in versions if v.is_current), None)
        if current:
            self._status_label.setText(f"Current pack: <b>{current.display_name}</b> ({current.pack_code})")
        else:
            self._status_label.setText("No statutory pack is currently applied.")

        self._table.setRowCount(len(versions))
        for row, v in enumerate(versions):
            self._table.setItem(row, 0, QTableWidgetItem(v.pack_code))
            self._table.setItem(row, 1, QTableWidgetItem(v.display_name))
            self._table.setItem(row, 2, QTableWidgetItem(v.country_code))
            self._table.setItem(row, 3, QTableWidgetItem(str(v.effective_from)))
            status = "Current" if v.is_current else "Available"
            self._table.setItem(row, 4, QTableWidgetItem(status))

    def _selected_pack_code(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.text() if item else None

    def _on_preview(self) -> None:
        pack_code = self._selected_pack_code()
        if not pack_code or not self._company_id:
            show_info(self, "Select Pack", "Select a pack version to preview.")
            return
        try:
            preview = self._registry.payroll_pack_version_service.preview_rollover(
                self._company_id, pack_code
            )
            self._preview_label.setText(
                f"<b>Preview:</b> {preview.message}<br>"
                f"Components to create: {preview.components_to_create}, "
                f"Rule sets to create: {preview.rule_sets_to_create}"
            )
            self._preview_label.show()
        except Exception as exc:
            show_error(self, "Preview Error", str(exc))

    def _on_apply(self) -> None:
        pack_code = self._selected_pack_code()
        if not pack_code or not self._company_id:
            show_info(self, "Select Pack", "Select a pack version to apply.")
            return

        confirm = QMessageBox.question(
            self,
            "Apply Pack",
            f"Apply pack '{pack_code}' to this company?\n\n"
            "Existing components and rules will not be overwritten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._registry.payroll_pack_version_service.execute_rollover(
                self._company_id, pack_code
            )
            show_info(self, "Pack Applied", result.message)
            self.refresh()
        except Exception as exc:
            show_error(self, "Apply Error", str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Imports
# ══════════════════════════════════════════════════════════════════════════════


class _ImportsTab(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Import type selector
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        type_row.addWidget(QLabel("Import Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItem("Departments", "departments")
        self._type_combo.addItem("Positions", "positions")
        self._type_combo.addItem("Employees", "employees")
        self._type_combo.addItem("Payroll Components", "payroll_components")
        self._type_combo.addItem("Payroll Rule Sets", "payroll_rule_sets")
        self._type_combo.addItem("Payroll Rule Brackets", "payroll_rule_brackets")
        self._type_combo.addItem("Compensation Profiles", "employee_compensation_profiles")
        self._type_combo.addItem("Component Assignments", "employee_component_assignments")
        type_row.addWidget(self._type_combo)

        self._btn_browse = QPushButton("Browse CSV…")
        self._btn_browse.clicked.connect(self._browse_file)
        type_row.addWidget(self._btn_browse)
        type_row.addStretch()
        layout.addLayout(type_row)

        self._file_label = QLabel("No file selected")
        self._file_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self._file_label)

        # Preview / Import buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._btn_preview = QPushButton("Preview")
        self._btn_preview.clicked.connect(self._on_preview)
        self._btn_preview.setEnabled(False)
        action_row.addWidget(self._btn_preview)

        self._btn_import = QPushButton("Import")
        self._btn_import.clicked.connect(self._on_import)
        self._btn_import.setEnabled(False)
        action_row.addWidget(self._btn_import)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Preview / result table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Row", "Status", "Values", "Issues"])
        configure_compact_table(self._table)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)

        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.hide()
        layout.addWidget(self._result_label)

        self._selected_file: str | None = None

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if file_path:
            self._selected_file = file_path
            self._file_label.setText(file_path)
            self._btn_preview.setEnabled(True)
            self._btn_import.setEnabled(False)

    def _on_preview(self) -> None:
        if not self._company_id or not self._selected_file:
            return
        entity_type = self._type_combo.currentData()
        try:
            result = self._registry.payroll_import_service.preview(
                self._company_id, entity_type, self._selected_file
            )
        except Exception as exc:
            show_error(self, "Preview Error", str(exc))
            return

        self._table.setRowCount(len(result.preview_rows))
        for row_idx, pr in enumerate(result.preview_rows):
            self._table.setItem(row_idx, 0, QTableWidgetItem(str(pr.row_number)))
            status = "Error" if pr.has_errors else ("Warning" if pr.issues else "OK")
            self._table.setItem(row_idx, 1, QTableWidgetItem(status))
            vals = ", ".join(f"{k}={v}" for k, v in pr.values.items() if v)
            self._table.setItem(row_idx, 2, QTableWidgetItem(vals))
            issues = "; ".join(i.message for i in pr.issues)
            self._table.setItem(row_idx, 3, QTableWidgetItem(issues))

        self._result_label.setText(
            f"Total: {result.total_rows} rows — "
            f"Valid: {result.valid_rows}, Errors: {result.error_rows}, Warnings: {result.warning_rows}"
        )
        self._result_label.show()
        self._btn_import.setEnabled(not result.has_errors)

    def _on_import(self) -> None:
        if not self._company_id or not self._selected_file:
            return
        entity_type = self._type_combo.currentData()

        confirm = QMessageBox.question(
            self,
            "Confirm Import",
            f"Import {entity_type} from the selected CSV file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._registry.payroll_import_service.execute_import(
                self._company_id, entity_type, self._selected_file
            )
            msg = (
                f"Import complete.\n"
                f"Created: {result.created}\n"
                f"Skipped (existing): {result.skipped}\n"
                f"Errors: {result.errors}"
            )
            if result.messages:
                msg += "\n\nDetails:\n" + "\n".join(result.messages[:20])
            show_info(self, "Import Result", msg)

        except Exception as exc:
            show_error(self, "Import Error", str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Print
# ══════════════════════════════════════════════════════════════════════════════


class _PrintTab(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Select a payroll run to print payslips or summary report."))

        # Runs table
        self._runs_table = QTableWidget()
        cols = ["Run Ref", "Label", "Period", "Status", "Employees", "Net Payable"]
        self._runs_table.setColumnCount(len(cols))
        self._runs_table.setHorizontalHeaderLabels(cols)
        configure_compact_table(self._runs_table)
        self._runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._runs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self._runs_table)

        # Print buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_payslips = QPushButton("Print Payslips")
        self._btn_payslips.clicked.connect(self._on_print_payslips)
        btn_row.addWidget(self._btn_payslips)

        self._btn_summary = QPushButton("Print Summary")
        self._btn_summary.clicked.connect(self._on_print_summary)
        btn_row.addWidget(self._btn_summary)

        self._btn_pdf = QPushButton("Save as PDF")
        self._btn_pdf.clicked.connect(self._on_save_pdf)
        btn_row.addWidget(self._btn_pdf)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Export buttons
        export_row = QHBoxLayout()
        export_row.setSpacing(8)
        export_lbl = QLabel("Export:")
        export_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #555;")
        export_row.addWidget(export_lbl)

        self._btn_export_payslip = QPushButton("Export Payslips\u2026")
        self._btn_export_payslip.setToolTip("Export payslips for all employees — choose PDF, Word, or Excel")
        self._btn_export_payslip.clicked.connect(self._on_export_payslips_format)
        export_row.addWidget(self._btn_export_payslip)

        self._btn_export_batch = QPushButton("All Payslips PDF")
        self._btn_export_batch.setToolTip("Export individual payslip PDFs for all employees in selected run")
        self._btn_export_batch.clicked.connect(lambda: self._on_export("batch"))
        export_row.addWidget(self._btn_export_batch)

        self._btn_export_summary_csv = QPushButton("Summary CSV")
        self._btn_export_summary_csv.setToolTip("Export payroll summary as CSV spreadsheet")
        self._btn_export_summary_csv.clicked.connect(lambda: self._on_export("summary"))
        export_row.addWidget(self._btn_export_summary_csv)

        self._btn_export_summary_pdf = QPushButton("Summary PDF")
        self._btn_export_summary_pdf.setToolTip("Export payroll summary as professional PDF")
        self._btn_export_summary_pdf.clicked.connect(lambda: self._on_export("summary_pdf"))
        export_row.addWidget(self._btn_export_summary_pdf)
        export_row.addStretch()
        layout.addLayout(export_row)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        if not self._company_id:
            return
        try:
            runs = self._registry.payroll_run_service.list_runs(self._company_id)
        except Exception:
            runs = []

        self._runs_table.setRowCount(len(runs))
        for row, r in enumerate(runs):
            self._runs_table.setItem(row, 0, QTableWidgetItem(r.run_reference))
            self._runs_table.setItem(row, 1, QTableWidgetItem(r.run_label))
            period = f"{_MONTHS.get(r.period_month, '?')} {r.period_year}"
            self._runs_table.setItem(row, 2, QTableWidgetItem(period))
            self._runs_table.setItem(row, 3, QTableWidgetItem(r.status_code.title()))
            self._runs_table.setItem(row, 4, QTableWidgetItem(str(r.employee_count)))
            net_item = QTableWidgetItem(f"{r.total_net_payable:,.2f}")
            net_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._runs_table.setItem(row, 5, net_item)

    def _selected_run(self):
        row = self._runs_table.currentRow()
        if row < 0 or not self._company_id:
            return None
        try:
            runs = self._registry.payroll_run_service.list_runs(self._company_id)
            return runs[row] if row < len(runs) else None
        except Exception:
            return None

    def _on_print_payslips(self) -> None:
        run = self._selected_run()
        if not run or not self._company_id:
            show_info(self, "Select Run", "Select a payroll run first.")
            return
        try:
            payslips = self._registry.payroll_print_service.get_payslip_batch_data(
                self._company_id, run.id
            )
            if not payslips:
                show_info(self, "No Data", "No payslip data found for this run.")
                return
            html = _build_payslips_html(payslips)
            self._print_html(html)
        except Exception as exc:
            show_error(self, "Print Error", str(exc))

    def _on_print_summary(self) -> None:
        run = self._selected_run()
        if not run or not self._company_id:
            show_info(self, "Select Run", "Select a payroll run first.")
            return
        try:
            data = self._registry.payroll_print_service.get_summary_data(
                self._company_id, run.id
            )
            html = _build_summary_html(data)
            self._print_html(html)
        except Exception as exc:
            show_error(self, "Print Error", str(exc))

    def _on_save_pdf(self) -> None:
        run = self._selected_run()
        if not run or not self._company_id:
            show_info(self, "Select Run", "Select a payroll run first.")
            return
        try:
            data = self._registry.payroll_print_service.get_summary_data(
                self._company_id, run.id
            )
            html = _build_summary_html(data)

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save PDF", f"payroll_summary_{run.run_reference}.pdf", "PDF Files (*.pdf)"
            )
            if not file_path:
                return

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(file_path)
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)
            show_info(self, "Saved", f"PDF saved to {file_path}")
        except Exception as exc:
            show_error(self, "PDF Error", str(exc))

    def _on_export_payslips_format(self) -> None:
        """Export payslips for a run — opens format/path selector then exports."""
        from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
        from seeker_accounting.platform.printing.print_data_protocol import (
            PageOrientation,
            PageSize,
            PrintFormat,
        )

        run = self._selected_run()
        if not run or not self._company_id:
            show_info(self, "Select Run", "Select a payroll run first.")
            return

        period = f"{_MONTHS.get(run.period_month, '?')} {run.period_year}"
        safe_period = period.replace(" ", "_")
        doc_title = f"Payslips_{run.run_reference}_{safe_period}"

        result = PrintExportDialog.show_dialog(
            self,
            doc_title,
            default_format=PrintFormat.PDF,
            default_page_size=PageSize.A4,
            default_orientation=PageOrientation.PORTRAIT,
        )
        if result is None:
            return

        fmt = result.format.value  # "pdf" / "word" / "excel"

        try:
            export_svc = self._registry.payroll_export_service

            if fmt == "excel":
                # Excel: single multi-sheet workbook — ask for file path
                import os
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                start_dir = desktop if os.path.isdir(desktop) else os.path.expanduser("~")
                default_name = f"payslips_{run.run_reference}.xlsx"
                file_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Excel Workbook",
                    os.path.join(start_dir, default_name),
                    "Excel Workbook (*.xlsx)",
                )
                if not file_path:
                    return
                if not file_path.lower().endswith(".xlsx"):
                    file_path += ".xlsx"
                batch_result = export_svc.export_payslip_batch_to_format(
                    self._company_id, run.id, file_path, fmt
                )
                exported_count = len(batch_result.exported)
                failed_count = len(batch_result.failed)
                if batch_result.failed:
                    msgs = "\n".join(
                        f"  {name}: {err}" for name, err in batch_result.failed[:5]
                    )
                    show_error(
                        self,
                        "Partial Export",
                        f"Exported {exported_count} payslips.\n"
                        f"Failed {failed_count}:\n{msgs}",
                    )
                else:
                    show_info(
                        self,
                        "Export Complete",
                        f"Exported {exported_count} payslips to:\n{file_path}",
                    )

            else:
                # PDF / Word: individual files — ask for output directory
                import os
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                start_dir = desktop if os.path.isdir(desktop) else os.path.expanduser("~")
                out_dir = QFileDialog.getExistingDirectory(
                    self,
                    f"Choose Output Folder for {result.format.label} Payslips",
                    start_dir,
                )
                if not out_dir:
                    return
                batch_result = export_svc.export_payslip_batch_to_format(
                    self._company_id, run.id, out_dir, fmt
                )
                exported_count = len(batch_result.exported)
                failed_count = len(batch_result.failed)
                if batch_result.failed:
                    msgs = "\n".join(
                        f"  {name}: {err}" for name, err in batch_result.failed[:5]
                    )
                    show_error(
                        self,
                        "Partial Export",
                        f"Exported {exported_count} files.\n"
                        f"Failed {failed_count}:\n{msgs}",
                    )
                else:
                    show_info(
                        self,
                        "Export Complete",
                        f"Exported {exported_count} payslips to:\n{out_dir}",
                    )

        except Exception as exc:
            show_error(self, "Export Error", str(exc))

    def _on_export(self, export_mode: str) -> None:
        """Open the export dialog for the selected run."""
        run = self._selected_run()
        if not run or not self._company_id:
            show_info(self, "Select Run", "Select a payroll run first.")
            return
        period = f"{_MONTHS.get(run.period_month, '?')} {run.period_year}"

        if export_mode == "summary_pdf":
            # Summary PDF — use summary mode but pre-select PDF
            dlg = PayrollExportDialog(
                self._registry, self._company_id, run.id,
                mode="summary", run_reference=run.run_reference, period_label=period,
                parent=self,
            )
            if hasattr(dlg, "_radio_pdf"):
                dlg._radio_pdf.setChecked(True)
            dlg.exec()
        elif export_mode == "payslip":
            # For single payslip, we don't have a specific employee selected in the print tab.
            # Use batch mode instead, which is more useful from this context.
            dlg = PayrollExportDialog(
                self._registry, self._company_id, run.id,
                mode="batch", run_reference=run.run_reference, period_label=period,
                parent=self,
            )
            dlg.exec()
        else:
            dlg = PayrollExportDialog(
                self._registry, self._company_id, run.id,
                mode=export_mode, run_reference=run.run_reference, period_label=period,
                parent=self,
            )
            dlg.exec()

    def _print_html(self, html: str) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 5 — Audit Log
# ══════════════════════════════════════════════════════════════════════════════


class _AuditTab(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(QLabel("Module:"))
        self._module_combo = QComboBox()
        self._module_combo.addItem("All Modules", "")
        self._module_combo.addItem("Payroll", "payroll")
        filter_row.addWidget(self._module_combo)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self.refresh)
        filter_row.addWidget(self._btn_refresh)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self._table = QTableWidget()
        cols = ["Timestamp", "Event", "Module", "Entity", "Description", "Actor"]
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        configure_compact_table(self._table)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        if not self._company_id:
            return
        module_code = self._module_combo.currentData() or None
        try:
            events = self._registry.audit_service.list_events(
                self._company_id,
                module_code=module_code,
                limit=200,
                required_permission_code=PAYROLL_AUDIT_VIEW,
            )
        except Exception:
            events = []

        self._table.setRowCount(len(events))
        for row, ev in enumerate(events):
            ts = ev.created_at.strftime("%Y-%m-%d %H:%M") if ev.created_at else ""
            self._table.setItem(row, 0, QTableWidgetItem(ts))
            self._table.setItem(row, 1, QTableWidgetItem(ev.event_type_code))
            self._table.setItem(row, 2, QTableWidgetItem(ev.module_code))
            entity = f"{ev.entity_type}#{ev.entity_id}" if ev.entity_id else ev.entity_type
            self._table.setItem(row, 3, QTableWidgetItem(entity))
            self._table.setItem(row, 4, QTableWidgetItem(ev.description))
            self._table.setItem(row, 5, QTableWidgetItem(ev.actor_display_name or ""))


# ══════════════════════════════════════════════════════════════════════════════
# HTML builders for print
# ══════════════════════════════════════════════════════════════════════════════

_PRINT_STYLE = """
<style>
  body { font-family: 'Segoe UI', Arial, Helvetica, sans-serif; font-size: 10pt; color: #1F2933; }
  /* Centered content frame */
  .main { max-width: 86%; margin: 0 auto; }
  /* Company banner */
  .company-banner { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
  .company-banner td { vertical-align: middle; padding: 0; }
  .company-banner .name-cell { font-size: 14pt; font-weight: 700; color: #2F4F6F; }
  .company-banner .title-cell { text-align: right; font-size: 10pt; font-weight: 600;
      color: #6E859B; letter-spacing: 1px; line-height: 1.4; }
  hr.sep { border: none; border-top: 1px solid #D6E0EA; margin: 6px 0; }
  /* Identity cards */
  .identity-row { width: 100%; border-collapse: separate; border-spacing: 12px 0; margin-bottom: 10px; }
  .identity-row > tbody > tr > td { vertical-align: top; width: 50%; padding: 0; }
  .id-card { border: 1px solid #D6E0EA; border-radius: 4px; overflow: hidden; background: #fff; }
  .identity-header { font-size: 8.5pt; font-weight: 600; color: #2F4F6F; background: #EAF1F7;
      padding: 5px 10px; letter-spacing: 0.4px; border-bottom: 1px solid #D6E0EA; }
  .id-rows { padding: 6px 14px 8px 14px; }
  .id-row { padding: 1px 0; }
  .id-row-label { display: inline-block; width: 130px; text-align: right; font-size: 7.5pt;
      color: #6B7280; padding-right: 8px; }
  .id-row-value { font-size: 9pt; font-weight: 600; color: #1F2933; }
  /* Context strip (4-cell) */
  .context-bar { background: #EAF1F7; margin-bottom: 14px; border-radius: 3px; }
  .context-bar table { width: 100%; border-collapse: collapse; }
  .context-bar td { padding: 4px 8px; text-align: center; vertical-align: top; }
  .context-bar .ctx-label { font-size: 7.5pt; color: #6B7280; }
  .context-bar .ctx-value { font-size: 9pt; font-weight: 600; color: #1F2933; }
  .context-bar .ctx-sep { width: 1px; background: #D6E0EA; padding: 0; }
  /* Section headers */
  .section-header { font-size: 9pt; font-weight: 600; color: #2F4F6F;
      padding: 2px 0; margin: 10px 0 0 0; border-bottom: 2px solid #2F4F6F; }
  h2 { font-size: 12pt; margin-top: 12px; margin-bottom: 4px; color: #2F4F6F; }
  table { border-collapse: collapse; width: 100%; margin-top: 4px; font-size: 9pt; }
  td { border-bottom: 1px solid #EAF1F7; padding: 3px 10px; text-align: left; }
  td.right { text-align: right; font-variant-numeric: tabular-nums; width: 140px; }
  th { background: #2F4F6F; color: #fff; padding: 5px 10px; font-size: 8.5pt; font-weight: 600; text-align: left; }
  th.right { text-align: right; }
  .total-row { font-weight: 700; background: #EAF1F7; }
  .total-row td { border-top: 2px solid #2F4F6F; color: #2F4F6F; }
  tr:nth-child(even) { background: #F6F8FB; }
  /* Bases */
  .bases-strip { margin: 10px 0 14px 0; }
  .bases-strip table { border-collapse: separate; border-spacing: 10px 0; }
  .bases-strip td { background: #EAF1F7; border: 1px solid #D6E0EA; border-radius: 3px;
      text-align: center; padding: 8px 12px; width: 33%; }
  .bases-strip .b-label { font-size: 7.5pt; color: #6B7280; text-transform: uppercase; letter-spacing: 0.5px; }
  .bases-strip .b-value { font-size: 10.5pt; font-weight: 600; color: #2F4F6F; }
  /* Net box */
  .net-box { margin: 14px 0; background: #EDF7F1; border: 1px solid #C3DFD0;
      border-radius: 5px; padding: 2px 0; }
  .net-box table { border-collapse: collapse; }
  .net-box td { padding: 8px 20px; border: none; background: transparent; }
  .net-box .label { font-size: 9pt; color: #2E7D4F; }
  .net-box .label-main { font-size: 11pt; font-weight: 600; color: #2E7D4F; }
  .net-box .amount { font-size: 9.5pt; color: #2E7D4F; font-weight: 600; text-align: right; }
  .net-box .amount-main { font-size: 16pt; font-weight: 700; color: #2E7D4F; text-align: right; }
  .net-sep { border: none; border-top: 1px solid #C3DFD0; margin: 0; }
  /* Signatures */
  .sig-table { width: 100%; border-collapse: collapse; margin-top: 22px; }
  .sig-table td { width: 33%; padding: 0 12px; text-align: center; vertical-align: bottom;
      font-size: 8pt; color: #6B7280; border: none; background: transparent; }
  .sig-line { border-top: 1px solid #6E859B; padding-top: 4px; margin-top: 36px; }
  .section { margin-top: 14px; }
  .page-break { page-break-before: always; }
  .footer { font-size: 7.5pt; color: #9CA3AF; margin-top: 14px; text-align: right; }
</style>
"""


def _id_field_html(label: str, value: str | None) -> str:
    import html as _html
    v = _html.escape(value) if value else "&mdash;"
    return (
        f'<div class="id-row">'
        f'<span class="id-row-label">{_html.escape(label)}:</span>'
        f'<span class="id-row-value">{v}</span>'
        f'</div>'
    )


def _build_payslips_html(payslips: list) -> str:
    import html as _html
    parts = [f"<html><head>{_PRINT_STYLE}</head><body>"]
    for idx, ps in enumerate(payslips):
        if idx > 0:
            parts.append('<div class="page-break"></div>')

        parts.append('<div class="main">')

        # ── Company banner ────────────────────────────────────────────────
        parts.append('<table class="company-banner"><tr>')
        parts.append(f'<td class="name-cell">{_html.escape(ps.company_name)}</td>')
        parts.append('<td class="title-cell">BULLETIN DE PAIE<br/>PAYSLIP</td>')
        parts.append('</tr></table>')
        parts.append('<hr class="sep"/>')

        # ── Identity cards — Employer | Employee ──────────────────────────
        parts.append('<table class="identity-row"><tr>')

        parts.append('<td><div class="id-card">')
        parts.append('<div class="identity-header">EMPLOYER / EMPLOYEUR</div>')
        parts.append('<div class="id-rows">')
        parts.append(_id_field_html("Company", ps.company_name))
        parts.append(_id_field_html("Address / Adresse", ps.company_address))
        parts.append(_id_field_html("City / Ville", ps.company_city))
        parts.append(_id_field_html("Tax ID / NIU", ps.company_tax_identifier))
        parts.append(_id_field_html("CNPS Employer No.", ps.company_cnps_employer_number))
        parts.append(_id_field_html("Phone / Tél.", ps.company_phone))
        parts.append('</div></div></td>')

        parts.append('<td><div class="id-card">')
        parts.append('<div class="identity-header">EMPLOYEE / EMPLOY&Eacute;(E)</div>')
        parts.append('<div class="id-rows">')
        parts.append(_id_field_html("Name / Nom", ps.employee_display_name))
        parts.append(_id_field_html("Employee No. / Matricule", ps.employee_number))
        parts.append(_id_field_html("Job Title / Fonction", ps.employee_position))
        parts.append(_id_field_html("Department", ps.employee_department))
        parts.append(_id_field_html("Tax ID / NIF", ps.employee_nif))
        parts.append(_id_field_html("CNPS No.", ps.employee_cnps_number))
        hire_str = ps.employee_hire_date.strftime("%d/%m/%Y") if ps.employee_hire_date else None
        parts.append(_id_field_html("Hire Date / Date d'Embauche", hire_str))
        parts.append('</div></div></td>')

        parts.append('</tr></table>')

        # ── Context strip (4-cell) ────────────────────────────────────────
        pay_date = ps.payment_date.strftime("%d/%m/%Y") if ps.payment_date else "—"
        ctx_cells = [
            ("Pay Period", _html.escape(ps.period_label)),
            ("Payment Date", _html.escape(pay_date)),
            ("Run Reference", _html.escape(ps.run_reference)),
            ("Currency", _html.escape(ps.currency_code)),
        ]
        parts.append('<div class="context-bar"><table><tr>')
        for i, (cl, cv) in enumerate(ctx_cells):
            if i > 0:
                parts.append('<td class="ctx-sep"></td>')
            parts.append(f'<td><span class="ctx-label">{cl}</span><br/><span class="ctx-value">{cv}</span></td>')
        parts.append('</tr></table></div>')

        # Earnings
        parts.append('<div class="section-header">EARNINGS / RÉMUNÉRATIONS</div><table>')
        for name, amount in ps.earnings:
            parts.append(f'<tr><td>{_html.escape(name)}</td><td class="right">{amount:,.2f}</td></tr>')
        parts.append(f'<tr class="total-row"><td>Gross Earnings / Salaire Brut</td><td class="right">{ps.gross_earnings:,.2f}</td></tr>')
        parts.append("</table>")

        # Bases mini-blocks
        parts.append('<div class="bases-strip"><table><tr>')
        parts.append(f'<td><span class="b-label">CNPS BASE</span><br/><span class="b-value">{ps.cnps_contributory_base:,.2f}</span></td>')
        parts.append(f'<td><span class="b-label">TAXABLE BASE (IRPP)</span><br/><span class="b-value">{ps.taxable_salary_base:,.2f}</span></td>')
        parts.append(f'<td><span class="b-label">TDL BASE</span><br/><span class="b-value">{ps.tdl_base:,.2f}</span></td>')
        parts.append('</tr></table></div>')

        # Deductions
        parts.append('<div class="section-header">EMPLOYEE DEDUCTIONS / RETENUES SALARIALES</div><table>')
        for name, amount in ps.deductions:
            parts.append(f'<tr><td>{_html.escape(name)}</td><td class="right">{amount:,.2f}</td></tr>')
        parts.append(f'<tr class="total-row"><td>Total Deductions / Total Retenues</td><td class="right">{ps.total_deductions:,.2f}</td></tr>')
        parts.append("</table>")

        # Taxes
        parts.append('<div class="section-header">TAXES / IMPÔTS</div><table>')
        for name, amount in ps.taxes:
            parts.append(f'<tr><td>{_html.escape(name)}</td><td class="right">{amount:,.2f}</td></tr>')
        parts.append(f'<tr class="total-row"><td>Total Taxes</td><td class="right">{ps.total_taxes:,.2f}</td></tr>')
        parts.append("</table>")

        # Net box with separator
        net_taxable = ps.taxable_salary_base - ps.total_deductions
        parts.append('<div class="net-box"><table>')
        parts.append(f'<tr><td class="label">Net Taxable Pay / Salaire Net Imposable</td><td class="amount">{net_taxable:,.2f}</td></tr>')
        parts.append('</table><hr class="net-sep"/><table>')
        parts.append(f'<tr><td class="label-main">NET PAYABLE / SALAIRE NET À PAYER</td><td class="amount-main">{ps.net_payable:,.2f}</td></tr>')
        parts.append('</table></div>')

        # Employer contributions
        if ps.employer_contributions:
            parts.append('<div class="section-header">EMPLOYER CHARGES / CHARGES PATRONALES</div><table>')
            for name, amount in ps.employer_contributions:
                parts.append(f'<tr><td>{_html.escape(name)}</td><td class="right">{amount:,.2f}</td></tr>')
            parts.append("</table>")

        # Signature block
        parts.append('<hr class="sep" style="margin-top:18px"/>')
        parts.append('<table class="sig-table"><tr>')
        for sig in ("Prepared by / Établi par", "Approved by / Approuvé par", "Employee / Employé(e)"):
            parts.append(f'<td><div class="sig-line">{_html.escape(sig)}</div></td>')
        parts.append('</tr></table>')

        parts.append('</div>')  # close .main

    parts.append("</body></html>")
    return "".join(parts)


def _build_summary_html(data) -> str:
    parts = [f"<html><head>{_PRINT_STYLE}</head><body>"]
    parts.append(f'<h1 style="color:#2F4F6F">{data.company_name}</h1>')
    parts.append(f'<h2>Payroll Summary — {data.period_label}</h2>')
    parts.append(f'<div class="context-bar"><b>Run:</b> {data.run_reference} ({data.run_label})')
    parts.append(f' &nbsp;&bull;&nbsp; <b>Employees:</b> {data.employee_count}')
    parts.append(f' &nbsp;&bull;&nbsp; <b>Currency:</b> {data.currency_code}</div>')

    # Employee detail table
    parts.append("<table>")
    parts.append('<tr><th>No.</th><th>Name</th><th class="right">Gross</th>')
    parts.append(f'<th class="right">Deductions &amp; Taxes</th><th class="right">Net Pay</th>')
    parts.append("</tr>")
    for emp_no, name, gross, ded_tax, net in data.employee_lines:
        parts.append(
            f'<tr><td>{emp_no}</td><td>{name}</td>'
            f'<td class="right">{gross:,.2f}</td>'
            f'<td class="right">{ded_tax:,.2f}</td>'
            f'<td class="right">{net:,.2f}</td></tr>'
        )
    parts.append(
        f'<tr class="total-row"><td colspan="2"><b>TOTALS</b></td>'
        f'<td class="right"><b>{data.total_gross_earnings:,.2f}</b></td>'
        f'<td class="right"><b>{(data.total_deductions + data.total_taxes):,.2f}</b></td>'
        f'<td class="right"><b>{data.total_net_payable:,.2f}</b></td></tr>'
    )
    parts.append("</table>")

    # Summary box
    parts.append('<div class="section"><h3 style="color:#2F4F6F">Summary</h3><table>')
    parts.append(f'<tr><td>Total Gross Earnings</td><td class="right">{data.total_gross_earnings:,.2f}</td></tr>')
    parts.append(f'<tr><td>Total Employee Deductions</td><td class="right">{data.total_deductions:,.2f}</td></tr>')
    parts.append(f'<tr><td>Total Taxes</td><td class="right">{data.total_taxes:,.2f}</td></tr>')
    parts.append(f'<tr class="total-row"><td>Total Net Payable</td><td class="right">{data.total_net_payable:,.2f}</td></tr>')
    parts.append(f'<tr><td>Total Employer Contributions</td><td class="right">{data.total_employer_contributions:,.2f}</td></tr>')
    parts.append(f'<tr class="total-row"><td>Total Employer Cost</td><td class="right">{data.total_employer_cost:,.2f}</td></tr>')
    parts.append("</table></div>")

    parts.append("</body></html>")
    return "".join(parts)
