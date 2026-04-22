"""Payroll Export Dialog — unified export options for payslips and summaries.

Provides:
- Single payslip PDF export (from run employee detail context)
- Batch payslip PDF export (from run context)
- Summary CSV export
- Summary PDF export

Shows compliance warnings from the output warning service when present.
"""
from __future__ import annotations

import logging

import os
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.message_boxes import show_error, show_info

_log = logging.getLogger(__name__)


class PayrollExportDialog(QDialog):
    """Dialog for exporting payslips and payroll summaries.

    Modes:
    - "payslip": single payslip PDF export
    - "batch": batch payslip PDF export (all employees in a run)
    - "summary": payroll summary export (CSV or PDF)
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        run_id: int,
        *,
        mode: str = "summary",
        run_employee_id: int | None = None,
        run_reference: str = "",
        period_label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._run_id = run_id
        self._run_employee_id = run_employee_id
        self._mode = mode
        self._run_reference = run_reference
        self._period_label = period_label

        self.setWindowTitle(self._dialog_title())
        self.setMinimumWidth(460)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Warning banner ────────────────────────────────────────────
        self._warning_frame = QFrame(self)
        self._warning_frame.setStyleSheet(
            "QFrame { background: #fff8e1; border-left: 3px solid #f9a825; padding: 8px 10px; }"
        )
        self._warning_layout = QVBoxLayout(self._warning_frame)
        self._warning_layout.setContentsMargins(8, 4, 8, 4)
        self._warning_layout.setSpacing(3)
        layout.addWidget(self._warning_frame)
        self._warning_frame.setVisible(False)

        # ── Context info ──────────────────────────────────────────────
        ctx_label = QLabel(
            f"<b>Run:</b> {run_reference} &nbsp;&bull;&nbsp; <b>Period:</b> {period_label}"
        )
        ctx_label.setStyleSheet("font-size: 11px; color: #555;")
        layout.addWidget(ctx_label)

        # ── Format selection ──────────────────────────────────────────
        if mode == "summary":
            fmt_group = QGroupBox("Export Format")
            fmt_layout = QVBoxLayout(fmt_group)
            self._radio_csv = QRadioButton("CSV (spreadsheet-compatible)")
            self._radio_pdf = QRadioButton("PDF (print-ready)")
            self._radio_csv.setChecked(True)
            fmt_layout.addWidget(self._radio_csv)
            fmt_layout.addWidget(self._radio_pdf)
            layout.addWidget(fmt_group)
        else:
            info = QLabel(self._mode_description())
            info.setWordWrap(True)
            info.setStyleSheet("font-size: 11px; color: #444;")
            layout.addWidget(info)

        # ── Buttons ───────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._btn_export = QPushButton("Export")
        self._btn_export.setDefault(True)
        self._btn_export.clicked.connect(self._on_export)
        btn_layout.addWidget(self._btn_export)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_export", dialog=True)

        # Load warnings asynchronously-ish (synchronous but deferred to init end)
        self._load_warnings()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dialog_title(self) -> str:
        if self._mode == "payslip":
            return "Export Payslip PDF"
        if self._mode == "batch":
            return "Export All Payslips as PDF"
        return "Export Payroll Summary"

    def _mode_description(self) -> str:
        if self._mode == "payslip":
            return "Export the selected employee payslip as a PDF document."
        if self._mode == "batch":
            return (
                "Export individual PDF payslips for all included employees in this run. "
                "Each payslip is saved as a separate file in the selected folder."
            )
        return ""

    def _load_warnings(self) -> None:
        try:
            warnings = self._registry.payroll_output_warning_service.get_export_warnings(
                self._company_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        if not warnings:
            return

        self._warning_frame.setVisible(True)
        for w in warnings:
            lbl = QLabel(f"<b>{w.title}:</b> {w.message}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 10px; color: #6d4c00;")
            self._warning_layout.addWidget(lbl)

    def _get_warning_lines(self) -> list[str]:
        """Get warning texts for embedding in exported documents."""
        try:
            warnings = self._registry.payroll_output_warning_service.get_export_warnings(
                self._company_id
            )
            return [f"{w.title}: {w.message}" for w in warnings if w.severity == "warning"]
        except Exception:
            return []

    # ── Export actions ────────────────────────────────────────────────────────

    def _on_export(self) -> None:
        if self._mode == "payslip":
            self._export_single_payslip()
        elif self._mode == "batch":
            self._export_batch_payslips()
        else:
            self._export_summary()

    def _export_single_payslip(self) -> None:
        if self._run_employee_id is None:
            show_error(self, "Export Error", "No employee selected.")
            return

        default_name = f"payslip_{self._run_reference}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Payslip PDF", default_name, "PDF Files (*.pdf)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        try:
            warning_lines = self._get_warning_lines()
            result = self._registry.payroll_export_service.export_payslip_pdf(
                self._company_id,
                self._run_employee_id,
                file_path,
                warning_lines=warning_lines,
            )
            show_info(
                self, "Export Complete",
                f"Payslip exported for {result.employee_display_name}.\n\nSaved to: {result.file_path}",
            )
            self.accept()
        except Exception as exc:
            show_error(self, "Export Failed", f"Could not export payslip:\n{exc}")

    def _export_batch_payslips(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Folder for Payslip PDFs"
        )
        if not output_dir:
            return

        try:
            warning_lines = self._get_warning_lines()
            result = self._registry.payroll_export_service.export_payslip_batch_pdf(
                self._company_id,
                self._run_id,
                output_dir,
                warning_lines=warning_lines,
            )
            msg = f"Exported {len(result.exported)} payslip(s) to:\n{result.output_directory}"
            if result.failed:
                msg += f"\n\n{len(result.failed)} failed:"
                for name, err in result.failed[:5]:
                    msg += f"\n  • {name}: {err}"
                if len(result.failed) > 5:
                    msg += f"\n  … and {len(result.failed) - 5} more"

            if result.failed:
                QMessageBox.warning(self, "Export Partially Complete", msg)
            else:
                show_info(self, "Export Complete", msg)
            self.accept()
        except Exception as exc:
            show_error(self, "Export Failed", f"Could not export payslips:\n{exc}")

    def _export_summary(self) -> None:
        is_csv = hasattr(self, "_radio_csv") and self._radio_csv.isChecked()

        if is_csv:
            default_name = f"payroll_summary_{self._run_reference}.csv"
            file_filter = "CSV Files (*.csv)"
            ext = ".csv"
        else:
            default_name = f"payroll_summary_{self._run_reference}.pdf"
            file_filter = "PDF Files (*.pdf)"
            ext = ".pdf"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Payroll Summary", default_name, file_filter
        )
        if not file_path:
            return
        if not file_path.lower().endswith(ext):
            file_path += ext

        try:
            if is_csv:
                result = self._registry.payroll_export_service.export_summary_csv(
                    self._company_id, self._run_id, file_path
                )
            else:
                warning_lines = self._get_warning_lines()
                result = self._registry.payroll_export_service.export_summary_pdf(
                    self._company_id, self._run_id, file_path,
                    warning_lines=warning_lines,
                )
            show_info(
                self, "Export Complete",
                f"Summary exported ({result.format.upper()}) for {result.employee_count} employees.\n\nSaved to: {result.file_path}",
            )
            self.accept()
        except Exception as exc:
            show_error(self, "Export Failed", f"Could not export summary:\n{exc}")
