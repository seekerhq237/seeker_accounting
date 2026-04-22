"""Payslip preview dialog — renders via QWebEngineView (Chromium).

The HTML is built by PayslipHtmlBuilder and is the single source of truth for
both the live preview and the exported PDF.  What you see here is literally what
will be printed — no layout divergence.

Export: the Export… button opens the format/path picker and routes:
  - PDF   → WebDocumentRenderer.render_pdf()  (Chromium)
  - Word  → PayrollExportService.export_payslip_word()
  - Excel → PayrollExportService.export_payslip_excel()
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry


class PayslipPreviewDialog(QDialog):
    """WYSIWYG payslip preview — Chromium renders the HTML, not Qt widgets."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        run_employee_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._run_employee_id = run_employee_id
        self._print_dto = None
        self._html: str | None = None

        self.setWindowTitle("Payslip Preview")
        self.setModal(True)
        # A4 portrait proportions at 96 dpi ≈ 794 × 1123 px; add chrome for action bar
        self.resize(860, 1020)
        self.setMinimumSize(640, 600)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── WebEngine view ────────────────────────────────────────────────────────────────────────
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self._view = QWebEngineView(self)
            self._view.setMinimumHeight(400)
            outer.addWidget(self._view, 1)
        except Exception as exc:
            self._view = None
            outer.addWidget(QLabel(f"WebEngine not available: {exc}", self), 1)

        # ── Action bar ─────────────────────────────────────────────────────────────────────────────
        btn_bar = QFrame(self)
        btn_bar.setFrameShape(QFrame.Shape.NoFrame)
        btn_bar.setStyleSheet("background: #F3F5F7; border-top: 1px solid #D6E0EA;")
        btn_row = QHBoxLayout(btn_bar)
        btn_row.setContentsMargins(14, 8, 14, 8)
        btn_row.setSpacing(8)
        btn_row.addStretch()

        export_btn = QPushButton("Export…")
        export_btn.setObjectName("PrimaryButton")
        export_btn.setMinimumWidth(100)
        export_btn.setStyleSheet(
            "QPushButton { background: #2F4F6F; color: #ffffff; border: 1px solid #2F4F6F; "
            "border-radius: 4px; padding: 5px 16px; font-weight: 600; }"
            "QPushButton:hover { background: #1E3A5F; border-color: #1E3A5F; }"
            "QPushButton:pressed { background: #1A3356; }"
        )
        export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(export_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("CancelButton")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        outer.addWidget(btn_bar)

        # ── Load content ────────────────────────────────────────────────────────────────────────────
        self._load_payslip()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payslip_preview", dialog=True)

    # ── Content loading ──────────────────────────────────────────────────────────────────────────

    def _load_payslip(self) -> None:
        try:
            print_svc = self._registry.payroll_print_service
            dto = print_svc.get_payslip_data(self._company_id, self._run_employee_id)
            self._print_dto = dto
        except Exception as exc:
            self._show_error(f"Error loading payslip: {exc}")
            return

        self.setWindowTitle(f"Payslip — {self._print_dto.employee_display_name}")

        try:
            from seeker_accounting.modules.payroll.services.payroll_payslip_html_builder import (
                PayslipHtmlBuilder,
            )
            logo_svc = getattr(self._registry, "company_logo_service", None)
            resolver = logo_svc.resolve_logo_path if logo_svc is not None else None
            builder = PayslipHtmlBuilder(logo_resolver=resolver)
            self._html = builder.build(self._print_dto)
        except Exception as exc:
            self._show_error(f"Error building payslip HTML: {exc}")
            return

        if self._view is not None:
            self._view.setHtml(self._html, "about:blank")

    def _show_error(self, message: str) -> None:
        if self._view is not None:
            self._view.setHtml(
                "<body style='font-family:Segoe UI;padding:24px;color:#c0392b'>"
                f"<b>Error</b><p>{message}</p></body>",
                "about:blank",
            )

    # ── Export ──────────────────────────────────────────────────────────────────────────────────

    def _on_export(self) -> None:
        if self._print_dto is None or self._html is None:
            QMessageBox.warning(self, "Export", "No payslip data to export.")
            return

        from seeker_accounting.platform.printing.print_data_protocol import (
            PageOrientation,
            PageSize,
            PrintFormat,
        )
        from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog

        ps = self._print_dto
        emp_no = ps.employee_number or "employee"
        period = (ps.period_label or "payslip").replace(" ", "_").replace("/", "_")
        doc_title = f"Payslip_{emp_no}_{period}"

        result = PrintExportDialog.show_dialog(
            self,
            doc_title,
            default_format=PrintFormat.PDF,
            default_page_size=PageSize.A4,
            default_orientation=PageOrientation.PORTRAIT,
        )
        if result is None:
            return

        output_path = result.output_path

        try:
            if result.format == PrintFormat.PDF:
                from seeker_accounting.platform.printing.web_renderer import WebDocumentRenderer
                renderer = WebDocumentRenderer()
                ok = renderer.render_pdf(
                    self._html,
                    output_path,
                    page_size=result.page_size,
                    orientation=result.orientation,
                    margin_mm=0,  # margins are declared in the @page CSS rule
                )
                if not ok:
                    QMessageBox.critical(
                        self, "Export Failed",
                        "PDF export failed — the document could not be written."
                    )
                    return
            else:
                export_svc = self._registry.payroll_export_service
                if result.format == PrintFormat.WORD:
                    export_svc.export_payslip_word(
                        self._company_id, self._run_employee_id, output_path
                    )
                else:
                    export_svc.export_payslip_excel(
                        self._company_id, self._run_employee_id, output_path
                    )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return

        reply = QMessageBox.question(
            self,
            "Export Complete",
            f"Payslip exported successfully.\n\n{output_path}\n\nOpen file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if sys.platform == "win32":
                    os.startfile(output_path)  # type: ignore[attr-defined]
                else:
                    import subprocess
                    cmd = "open" if sys.platform == "darwin" else "xdg-open"
                    subprocess.call([cmd, output_path])
            except Exception:
                pass
