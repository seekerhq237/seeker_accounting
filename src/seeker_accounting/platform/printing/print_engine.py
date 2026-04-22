"""Core print/export rendering engine for Seeker Accounting.

This module owns the rendering step only — transforming prepared content
into output files. It does not assemble document content; module print
data services are responsible for that.

Rendering technologies:
  - PDF:   Qt QPrinter + QTextDocument (HTML → PDF).  No external dependency.
  - Word:  python-docx via WordDocumentBuilder.
  - Excel: openpyxl via ExcelWorkbookBuilder.

Usage:
    engine = PrintEngine()

    # PDF from HTML string
    html = html_builder.wrap_html(body_html, page_size=PageSize.A4)
    engine.render_pdf(html, "/tmp/invoice.pdf", page_size=PageSize.A4)

    # Word document
    doc = engine.make_word_document(page_size=PageSize.A4)
    doc.add_company_header(company_data)
    doc.add_data_table(columns, rows)
    doc.save("/tmp/invoice.docx")

    # Excel workbook
    wb = engine.make_excel_workbook(page_size=PageSize.A4)
    sheet = wb.add_sheet("Invoices")
    sheet.write_document_header(company_data, "Sales Invoices")
    sheet.write_table_header(columns)
    for row in rows:
        sheet.write_table_row(row)
    wb.save("/tmp/invoices.xlsx")
"""
from __future__ import annotations

import os

from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
from seeker_accounting.platform.printing.print_data_protocol import (
    PageOrientation,
    PageSize,
)
from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class PrintEngine:
    """Stateless document rendering engine.

    Can be registered in ServiceRegistry and injected into module print
    data services, or constructed directly when not injected.
    """

    # ── PDF rendering ───────────────────────────────────────────────────────────

    def render_pdf(
        self,
        html_content: str,
        output_path: str,
        *,
        page_size: PageSize = PageSize.A4,
        orientation: PageOrientation = PageOrientation.PORTRAIT,
    ) -> None:
        """Render an HTML string to a PDF file using Qt.

        Uses Qt's QPrinter + QTextDocument pipeline — the same proven
        mechanism as payroll_export_service.  No external PDF library needed.
        """
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize as QtPageSize, QTextDocument
        from PySide6.QtPrintSupport import QPrinter

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(output_path)

        # Page size
        qt_page_size = (
            QtPageSize(QtPageSize.PageSizeId.A4)
            if page_size == PageSize.A4
            else QtPageSize(QtPageSize.PageSizeId.A5)
        )

        # Orientation
        qt_orientation = (
            QPageLayout.Orientation.Landscape
            if orientation == PageOrientation.LANDSCAPE
            else QPageLayout.Orientation.Portrait
        )

        printer.setPageLayout(
            QPageLayout(
                qt_page_size,
                qt_orientation,
                QMarginsF(0, 0, 0, 0),
                QPageLayout.Unit.Millimeter,
            )
        )

        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setHtml(html_content)
        doc.print_(printer)

    # ── Word document ───────────────────────────────────────────────────────────

    def make_word_document(
        self,
        *,
        page_size: PageSize = PageSize.A4,
        orientation: PageOrientation = PageOrientation.PORTRAIT,
    ) -> WordDocumentBuilder:
        """Return a new WordDocumentBuilder pre-configured for the given page setup."""
        return WordDocumentBuilder(page_size=page_size, orientation=orientation)

    # ── Excel workbook ──────────────────────────────────────────────────────────

    def make_excel_workbook(
        self,
        *,
        page_size: PageSize = PageSize.A4,
        orientation: PageOrientation = PageOrientation.PORTRAIT,
    ) -> ExcelWorkbookBuilder:
        """Return a new ExcelWorkbookBuilder pre-configured for the given page setup."""
        return ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
