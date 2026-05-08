"""PayrollOperationsWorkspace — five-tab payroll operations workspace.

Tabs:
  1. Validation Dashboard  — comprehensive readiness checks for a payroll period
  2. Statutory Packs       — pack version list, rollover preview/execute
  3. Imports               — CSV import for departments, positions, employees
  4. Print                 — payslip and summary report printing
  5. Audit Log             — read-only payroll audit event viewer
"""
from __future__ import annotations

import logging

from datetime import datetime
from decimal import Decimal
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.payroll.dto.payroll_validation_dashboard_dto import ValidationCheckDTO
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_AUDIT_VIEW
from seeker_accounting.modules.payroll.ui.dialogs.payroll_export_dialog import PayrollExportDialog
from seeker_accounting.modules.payroll.ui.dialogs.validation_check_detail_dialog import (
    ValidationCheckDetailDialog,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.styles.inline_styles import text_style
from seeker_accounting.shared.ui.styles.palette import LIGHT_PALETTE as _P

_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

_SEVERITY_COLORS = {
    "error": _P.danger,
    "warning": _P.warning,
    "info": _P.info,
}


_log = logging.getLogger(__name__)


class PayrollOperationsWorkspace(RibbonHostMixin, QWidget):
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
        self._company_label.setStyleSheet(text_style("secondary", font_size="11px"))
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
        self._tabs.addTab(self._packs_tab, "Statutory packs")
        self._tabs.addTab(self._imports_tab, "Imports")
        self._tabs.addTab(self._print_tab, "Print")
        self._tabs.addTab(self._audit_tab, "Audit Log")

        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Selection change hooks for ribbon context swap (validation
        # severity, pack selection, run selection in print tab).
        self._validation_tab._table.selection_changed.connect(
            lambda _: self._notify_ribbon_context_changed()
        )
        self._packs_tab._table.selection_changed.connect(
            lambda _: self._notify_ribbon_context_changed()
        )
        self._print_tab._runs_table.selection_changed.connect(
            lambda _: self._notify_ribbon_context_changed()
        )

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
        self._notify_ribbon_context_changed()

    def _on_tab_changed(self, index: int) -> None:
        self._notify_ribbon_context_changed()
        tab = self._tabs.widget(index)
        if hasattr(tab, "refresh") and self._company_id:
            tab.refresh()

    # ── Ribbon host integration ───────────────────────────────────────────────

    _TAB_VALIDATION = 0
    _TAB_PACKS = 1
    _TAB_IMPORTS = 2
    _TAB_PRINT = 3
    _TAB_AUDIT = 4

    def _selected_validation_severity(self) -> str | None:
        rows = self._validation_tab._table.selected_rows()
        if not rows:
            return None
        item = self._validation_tab._model.item(rows[0], 0)
        if item is None:
            return None
        check = item.data(Qt.ItemDataRole.UserRole)
        return getattr(check, "severity", None)

    def current_ribbon_surface_key(self) -> str | None:
        index = self._tabs.currentIndex()
        if index == self._TAB_VALIDATION:
            severity = self._selected_validation_severity()
            if severity == "error":
                return "payroll_operations.validation.blocker_selected"
            if severity == "warning":
                return "payroll_operations.validation.warning_selected"
            return "payroll_operations.validation.none"
        if index == self._TAB_PACKS:
            return "payroll_operations.packs"
        if index == self._TAB_IMPORTS:
            return "payroll_operations.imports"
        if index == self._TAB_PRINT:
            return "payroll_operations.print"
        if index == self._TAB_AUDIT:
            return "payroll_operations.audit"
        return "payroll_operations"

    def _refresh_active_tab(self) -> None:
        tab = self._tabs.currentWidget()
        if tab is not None and hasattr(tab, "refresh"):
            tab.refresh()

    def _on_open_check_detail(self) -> None:
        self._validation_tab._on_check_double_clicked()

    def _ribbon_commands(self):
        return {
            # Validation
            "payroll_operations.run_assessment":    self._validation_tab.refresh,
            "payroll_operations.open_check_detail": self._on_open_check_detail,
            # Packs
            "payroll_operations.apply_pack":        self._packs_tab._on_apply,
            "payroll_operations.preview_pack":      self._packs_tab._on_preview,
            # Imports
            "payroll_operations.preview_import":    self._imports_tab._on_preview,
            "payroll_operations.execute_import":    self._imports_tab._on_import,
            # Print
            "payroll_operations.print_payslips":    self._print_tab._on_print_payslips,
            "payroll_operations.print_summary":     self._print_tab._on_print_summary,
            "payroll_operations.save_pdf":          self._print_tab._on_save_pdf,
            # Cross-tab
            "payroll_operations.refresh":           self._refresh_active_tab,
        }

    def ribbon_state(self):
        has_company = self._company_id is not None
        check_selected = has_company and self._selected_validation_severity() is not None
        pack_selected = has_company and self._packs_tab._selected_pack_code() is not None
        has_import_file = has_company and bool(getattr(self._imports_tab, "_selected_file", None))
        import_button_enabled = (
            has_import_file and self._imports_tab._btn_import.isEnabled()
        )
        run_selected = has_company and bool(self._print_tab._runs_table.selected_rows())
        return {
            # Validation
            "payroll_operations.run_assessment":    has_company,
            "payroll_operations.open_check_detail": bool(check_selected),
            # Packs
            "payroll_operations.apply_pack":        bool(pack_selected),
            "payroll_operations.preview_pack":      bool(pack_selected),
            # Imports
            "payroll_operations.preview_import":    bool(has_import_file),
            "payroll_operations.execute_import":    bool(import_button_enabled),
            # Print
            "payroll_operations.print_payslips":    bool(run_selected),
            "payroll_operations.print_summary":     bool(run_selected),
            "payroll_operations.save_pdf":          bool(run_selected),
            # Cross-tab
            "payroll_operations.refresh":           True,
        }
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
        self._model = QStandardItemModel(0, 5)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="severity", title="Severity"),
                DataTableColumn(key="category", title="Category"),
                DataTableColumn(key="title", title="Title"),
                DataTableColumn(key="message", title="Message"),
                DataTableColumn(key="entity", title="Entity"),
            ),
            show_search=False,
            parent=self,
        )
        self._table.set_model(self._model)
        self._table.view().doubleClicked.connect(lambda *_: self._on_check_double_clicked())

        hint = QLabel("Double-click a row to see full details and remediation steps.")
        hint.setStyleSheet(text_style("muted", font_size="11px", extra="padding: 1px 0 4px 0"))
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
        except AppError as exc:
            show_error(self, "Validation Error", str(exc))
            return
        except Exception:
            _log.exception("Validation Error")
            show_error(self, "Validation Error", "An unexpected error occurred. See application log for details.")
            return

        # Summary
        if result.is_ready:
            self._summary_label.setText(
                f"<b style='color: {_P.success};'>Ready</b> — "
                f"{result.ready_employee_count}/{result.employee_count} employees ready. "
                f"{result.warning_count} warning(s)."
            )
        else:
            self._summary_label.setText(
                f"<b style='color: {_P.danger};'>Not Ready</b> — "
                f"{result.error_count} error(s), {result.warning_count} warning(s). "
                f"{result.ready_employee_count}/{result.employee_count} employees ready."
            )

        # Table
        self._model.removeRows(0, self._model.rowCount())
        for check in result.checks:
            sev_item = self._make_item(check.severity.upper(), user_data=check)
            sev_item.setForeground(QBrush(QColor(_P.accent_text)))
            self._model.appendRow([
                sev_item,
                self._make_item(check.category.title()),
                self._make_item(check.title),
                self._make_item(check.message),
                self._make_item(check.entity_label or ""),
            ])

    def _on_check_double_clicked(self) -> None:
        rows = self._table.selected_rows()
        if not rows:
            return
        item = self._model.item(rows[0], 0)
        if item is None:
            return
        check = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(check, ValidationCheckDTO):
            return
        dlg = ValidationCheckDetailDialog(check, parent=self)
        dlg.exec()

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item


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
        self._model = QStandardItemModel(0, 5)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="pack_code", title="Pack Code"),
                DataTableColumn(key="display_name", title="Display Name"),
                DataTableColumn(key="country", title="Country"),
                DataTableColumn(key="effective_from", title="Effective From"),
                DataTableColumn(key="status", title="Status"),
            ),
            show_search=False,
            selection_mode="single",
            parent=self,
        )
        self._table.set_model(self._model)
        layout.addWidget(self._table)

        # Actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_rollover_wizard = QPushButton("Rollover Wizard…")
        self._btn_rollover_wizard.setObjectName("PacksTabRolloverWizardBtn")
        self._btn_rollover_wizard.setProperty("variant", "primary")
        self._btn_rollover_wizard.clicked.connect(self._on_rollover_wizard)
        btn_row.addWidget(self._btn_rollover_wizard)

        self._btn_preview = QPushButton("Quick Preview")
        self._btn_preview.clicked.connect(self._on_preview)
        btn_row.addWidget(self._btn_preview)

        self._btn_apply = QPushButton("Quick Apply")
        self._btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self._btn_apply)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Preview result
        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(
            f"font-size: 11px; padding: 6px; background: {_P.secondary_surface}; border-radius: 4px;"
        )
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
        except AppError as exc:
            show_error(self, "Error", str(exc))
            return
        except Exception:
            _log.exception("Error")
            show_error(self, "Error", "An unexpected error occurred. See application log for details.")
            return

        current = next((v for v in versions if v.is_current), None)
        if current:
            self._status_label.setText(f"Current pack: <b>{current.display_name}</b> ({current.pack_code})")
        else:
            self._status_label.setText("No statutory pack is currently applied.")

        self._model.removeRows(0, self._model.rowCount())
        for v in versions:
            status = "Current" if v.is_current else "Available"
            self._model.appendRow([
                self._make_item(v.pack_code),
                self._make_item(v.display_name),
                self._make_item(v.country_code),
                self._make_item(str(v.effective_from)),
                self._make_item(status),
            ])

    def _selected_pack_code(self) -> str | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        item = self._model.item(rows[0], 0)
        return item.text() if item else None

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _on_rollover_wizard(self) -> None:
        if not self._company_id:
            show_info(self, "No Company", "Select an active company first.")
            return
        from seeker_accounting.modules.payroll.ui.dialogs.pack_rollover_wizard import (
            PackRolloverWizardDialog,
        )
        dlg = PackRolloverWizardDialog(
            self._company_id,
            self._registry.payroll_pack_version_service,
            parent=self,
        )
        if dlg.exec() and dlg.was_applied:
            self.refresh()

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
        except AppError as exc:
            show_error(self, "Preview Error", str(exc))
        except Exception:
            _log.exception("Preview Error")
            show_error(self, "Preview Error", "An unexpected error occurred. See application log for details.")

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
        except AppError as exc:
            show_error(self, "Apply Error", str(exc))
        except Exception:
            _log.exception("Apply Error")
            show_error(self, "Apply Error", "An unexpected error occurred. See application log for details.")


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
        self._type_combo.addItem("Payroll components", "payroll_components")
        self._type_combo.addItem("Payroll Rule Sets", "payroll_rule_sets")
        self._type_combo.addItem("Payroll Rule Brackets", "payroll_rule_brackets")
        self._type_combo.addItem("Compensation", "employee_compensation_profiles")
        self._type_combo.addItem("Component assignments", "employee_component_assignments")
        type_row.addWidget(self._type_combo)

        self._btn_browse = QPushButton("Browse CSV…")
        self._btn_browse.clicked.connect(self._browse_file)
        type_row.addWidget(self._btn_browse)
        type_row.addStretch()
        layout.addLayout(type_row)

        self._file_label = QLabel("No file selected")
        self._file_label.setStyleSheet(text_style("secondary", font_size="11px"))
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
        self._model = QStandardItemModel(0, 4)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="row", title="Row"),
                DataTableColumn(key="status", title="Status"),
                DataTableColumn(key="values", title="Values"),
                DataTableColumn(key="issues", title="Issues"),
            ),
            show_search=False,
            parent=self,
        )
        self._table.set_model(self._model)
        layout.addWidget(self._table)

        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.hide()
        layout.addWidget(self._result_label)

        self._selected_file: str | None = None

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

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
        except AppError as exc:
            show_error(self, "Preview Error", str(exc))
            return
        except Exception:
            _log.exception("Preview Error")
            show_error(self, "Preview Error", "An unexpected error occurred. See application log for details.")
            return

        self._model.removeRows(0, self._model.rowCount())
        for pr in result.preview_rows:
            status = "Error" if pr.has_errors else ("Warning" if pr.issues else "OK")
            vals = ", ".join(f"{k}={v}" for k, v in pr.values.items() if v)
            issues = "; ".join(i.message for i in pr.issues)
            self._model.appendRow([
                self._make_item(str(pr.row_number)),
                self._make_item(status),
                self._make_item(vals),
                self._make_item(issues),
            ])

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

        except AppError as exc:
            show_error(self, "Import Error", str(exc))
        except Exception:
            _log.exception("Import Error")
            show_error(self, "Import Error", "An unexpected error occurred. See application log for details.")


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
        self._runs_model = QStandardItemModel(0, 6)
        self._runs_table = DataTable(
            columns=(
                DataTableColumn(key="run_ref", title="Run Ref"),
                DataTableColumn(key="label", title="Label"),
                DataTableColumn(key="period", title="Period"),
                DataTableColumn(key="status", title="Status"),
                DataTableColumn(key="employees", title="Employees"),
                DataTableColumn(key="net_payable", title="Net Payable", is_numeric=True),
            ),
            show_search=False,
            selection_mode="single",
            parent=self,
        )
        self._runs_table.set_model(self._runs_model)
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
        export_lbl.setStyleSheet(text_style("secondary", font_size="11px", font_weight=600))
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

        self._runs_model.removeRows(0, self._runs_model.rowCount())
        for r in runs:
            period = f"{_MONTHS.get(r.period_month, '?')} {r.period_year}"
            self._runs_model.appendRow([
                self._make_item(r.run_reference),
                self._make_item(r.run_label),
                self._make_item(period),
                self._make_item(r.status_code.title()),
                self._make_item(str(r.employee_count)),
                self._make_item(f"{r.total_net_payable:,.2f}"),
            ])

    def _selected_run(self):
        rows = self._runs_table.selected_rows()
        if not rows or not self._company_id:
            return None
        row = rows[0]
        try:
            runs = self._registry.payroll_run_service.list_runs(self._company_id)
            return runs[row] if row < len(runs) else None
        except Exception:
            return None

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

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
        except AppError as exc:
            show_error(self, "Print Error", str(exc))
        except Exception:
            _log.exception("Print Error")
            show_error(self, "Print Error", "An unexpected error occurred. See application log for details.")

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
        except AppError as exc:
            show_error(self, "Print Error", str(exc))
        except Exception:
            _log.exception("Print Error")
            show_error(self, "Print Error", "An unexpected error occurred. See application log for details.")

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
        except AppError as exc:
            show_error(self, "PDF Error", str(exc))
        except Exception:
            _log.exception("PDF Error")
            show_error(self, "PDF Error", "An unexpected error occurred. See application log for details.")

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

        except AppError as exc:
            show_error(self, "Export Error", str(exc))
        except Exception:
            _log.exception("Export Error")
            show_error(self, "Export Error", "An unexpected error occurred. See application log for details.")

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

        self._model = QStandardItemModel(0, 6)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="timestamp", title="Timestamp"),
                DataTableColumn(key="event", title="Event"),
                DataTableColumn(key="module", title="Module"),
                DataTableColumn(key="entity", title="Entity"),
                DataTableColumn(key="description", title="Description"),
                DataTableColumn(key="actor", title="Actor"),
            ),
            show_search=False,
            parent=self,
        )
        self._table.set_model(self._model)
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

        self._model.removeRows(0, self._model.rowCount())
        for ev in events:
            ts = ev.created_at.strftime("%Y-%m-%d %H:%M") if ev.created_at else ""
            entity = f"{ev.entity_type}#{ev.entity_id}" if ev.entity_id else ev.entity_type
            self._model.appendRow([
                self._make_item(ts),
                self._make_item(ev.event_type_code),
                self._make_item(ev.module_code),
                self._make_item(entity),
                self._make_item(ev.description),
                self._make_item(ev.actor_display_name or ""),
            ])

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item


# ══════════════════════════════════════════════════════════════════════════════
# HTML builders for print
# ══════════════════════════════════════════════════════════════════════════════

_PRINT_STYLE = Template("""
<style>
  body { font-family: 'Segoe UI', Arial, Helvetica, sans-serif; font-size: 10pt; color: $text_primary; }
  /* Centered content frame */
  .main { max-width: 86%; margin: 0 auto; }
  /* Company banner */
  .company-banner { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
  .company-banner td { vertical-align: middle; padding: 0; }
  .company-banner .name-cell { font-size: 14pt; font-weight: 700; color: $accent; }
  .company-banner .title-cell { text-align: right; font-size: 10pt; font-weight: 600;
      color: $text_secondary; letter-spacing: 1px; line-height: 1.4; }
  hr.sep { border: none; border-top: 1px solid $border_default; margin: 6px 0; }
  /* Identity cards */
  .identity-row { width: 100%; border-collapse: separate; border-spacing: 12px 0; margin-bottom: 10px; }
  .identity-row > tbody > tr > td { vertical-align: top; width: 50%; padding: 0; }
  .id-card { border: 1px solid $border_default; border-radius: 4px; overflow: hidden; background: $workspace_surface; }
  .identity-header { font-size: 8.5pt; font-weight: 600; color: $accent; background: $accent_soft;
      padding: 5px 10px; letter-spacing: 0.4px; border-bottom: 1px solid $border_default; }
  .id-rows { padding: 6px 14px 8px 14px; }
  .id-row { padding: 1px 0; }
  .id-row-label { display: inline-block; width: 130px; text-align: right; font-size: 7.5pt;
      color: $text_secondary; padding-right: 8px; }
  .id-row-value { font-size: 9pt; font-weight: 600; color: $text_primary; }
  /* Context strip (4-cell) */
  .context-bar { background: $accent_soft; margin-bottom: 14px; border-radius: 3px; }
  .context-bar table { width: 100%; border-collapse: collapse; }
  .context-bar td { padding: 4px 8px; text-align: center; vertical-align: top; }
  .context-bar .ctx-label { font-size: 7.5pt; color: $text_secondary; }
  .context-bar .ctx-value { font-size: 9pt; font-weight: 600; color: $text_primary; }
  .context-bar .ctx-sep { width: 1px; background: $border_default; padding: 0; }
  /* Section headers */
  .section-header { font-size: 9pt; font-weight: 600; color: $accent;
      padding: 2px 0; margin: 10px 0 0 0; border-bottom: 2px solid $accent; }
  h2 { font-size: 12pt; margin-top: 12px; margin-bottom: 4px; color: $accent; }
  table { border-collapse: collapse; width: 100%; margin-top: 4px; font-size: 9pt; }
  td { border-bottom: 1px solid $accent_soft; padding: 3px 10px; text-align: left; }
  td.right { text-align: right; font-variant-numeric: tabular-nums; width: 140px; }
  th { background: $accent; color: $accent_text; padding: 5px 10px; font-size: 8.5pt; font-weight: 600; text-align: left; }
  th.right { text-align: right; }
  .total-row { font-weight: 700; background: $accent_soft; }
  .total-row td { border-top: 2px solid $accent; color: $accent; }
  tr:nth-child(even) { background: $row_alt; }
  /* Bases */
  .bases-strip { margin: 10px 0 14px 0; }
  .bases-strip table { border-collapse: separate; border-spacing: 10px 0; }
  .bases-strip td { background: $accent_soft; border: 1px solid $border_default; border-radius: 3px;
      text-align: center; padding: 8px 12px; width: 33%; }
  .bases-strip .b-label { font-size: 7.5pt; color: $text_secondary; text-transform: uppercase; letter-spacing: 0.5px; }
  .bases-strip .b-value { font-size: 10.5pt; font-weight: 600; color: $accent; }
  /* Net box */
  .net-box { margin: 14px 0; background: $success_bg; border: 1px solid $success_border;
      border-radius: 5px; padding: 2px 0; }
  .net-box table { border-collapse: collapse; }
  .net-box td { padding: 8px 20px; border: none; background: transparent; }
  .net-box .label { font-size: 9pt; color: $success_fg; }
  .net-box .label-main { font-size: 11pt; font-weight: 600; color: $success_fg; }
  .net-box .amount { font-size: 9.5pt; color: $success_fg; font-weight: 600; text-align: right; }
  .net-box .amount-main { font-size: 16pt; font-weight: 700; color: $success_fg; text-align: right; }
  .net-sep { border: none; border-top: 1px solid $success_border; margin: 0; }
  /* Signatures */
  .sig-table { width: 100%; border-collapse: collapse; margin-top: 22px; }
  .sig-table td { width: 33%; padding: 0 12px; text-align: center; vertical-align: bottom;
      font-size: 8pt; color: $text_secondary; border: none; background: transparent; }
  .sig-line { border-top: 1px solid $text_secondary; padding-top: 4px; margin-top: 36px; }
  .section { margin-top: 14px; }
  .page-break { page-break-before: always; }
  .footer { font-size: 7.5pt; color: $text_muted; margin-top: 14px; text-align: right; }
</style>
""").substitute(
    text_primary=_P.text_primary,
    text_secondary=_P.text_secondary,
    text_muted=_P.text_muted,
    workspace_surface=_P.workspace_surface,
    border_default=_P.border_default,
    row_alt=_P.data_table_row_alt,
    accent=_P.accent,
    accent_text=_P.accent_text,
    accent_soft=_P.accent_soft,
    success_bg=_P.status_success_bg,
    success_fg=_P.status_success_fg,
    success_border=_P.status_success_border,
)


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
    parts.append(f'<h1 style="color:{_P.accent}">{data.company_name}</h1>')
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
    parts.append(f'<div class="section"><h3 style="color:{_P.accent}">Summary</h3><table>')
    parts.append(f'<tr><td>Total Gross Earnings</td><td class="right">{data.total_gross_earnings:,.2f}</td></tr>')
    parts.append(f'<tr><td>Total Employee Deductions</td><td class="right">{data.total_deductions:,.2f}</td></tr>')
    parts.append(f'<tr><td>Total Taxes</td><td class="right">{data.total_taxes:,.2f}</td></tr>')
    parts.append(f'<tr class="total-row"><td>Total Net Payable</td><td class="right">{data.total_net_payable:,.2f}</td></tr>')
    parts.append(f'<tr><td>Total Employer Contributions</td><td class="right">{data.total_employer_contributions:,.2f}</td></tr>')
    parts.append(f'<tr class="total-row"><td>Total Employer Cost</td><td class="right">{data.total_employer_cost:,.2f}</td></tr>')
    parts.append("</table></div>")

    parts.append("</body></html>")
    return "".join(parts)
