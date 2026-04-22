"""Chromium-based document renderer using QWebEnginePage.

Replaces the QPrinter + QTextDocument pipeline for PDF generation.
Using Chromium's own PDF engine produces pixel-perfect output that is
faithful to the HTML/CSS layout, with proper text, columns, and tables —
identical to what Edge/Chrome would produce.

Usage (PDF export):
    renderer = WebDocumentRenderer()
    renderer.render_pdf(html_string, "/path/output.pdf", PageSize.A4)

Usage (interactive preview):
    renderer = WebDocumentRenderer()
    view = renderer.make_preview_view(html_string, parent=self)
    layout.addWidget(view)

Usage (physical printer):
    renderer = WebDocumentRenderer()
    renderer.print_to_printer(html_string, printer, PageSize.A4)

Thread safety: All methods must be called from the main Qt thread.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from seeker_accounting.platform.printing.print_data_protocol import (
    PageOrientation,
    PageSize,
)

if TYPE_CHECKING:
    from PySide6.QtPrintSupport import QPrinter
    from PySide6.QtWidgets import QWidget


class WebDocumentRenderer:
    """Stateless Chromium-based document renderer.

    Can be registered in ServiceRegistry and injected where needed,
    or constructed directly.
    """

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_page_layout(
        page_size: PageSize,
        orientation: PageOrientation,
        margin_mm: float | None = None,
    ):
        """Build a QPageLayout for the given size and orientation."""
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize as QtPageSize

        qt_id = (
            QtPageSize.PageSizeId.A4
            if page_size == PageSize.A4
            else QtPageSize.PageSizeId.A5
        )
        qt_size = QtPageSize(qt_id)
        qt_orient = (
            QPageLayout.Orientation.Landscape
            if orientation == PageOrientation.LANDSCAPE
            else QPageLayout.Orientation.Portrait
        )

        if margin_mm is None:
            margin_mm = page_size.margin_mm

        return QPageLayout(
            qt_size,
            qt_orient,
            QMarginsF(margin_mm, margin_mm, margin_mm, margin_mm),
            QPageLayout.Unit.Millimeter,
        )

    # ── PDF export ─────────────────────────────────────────────────────────────

    def render_pdf(
        self,
        html_content: str,
        output_path: str,
        *,
        page_size: PageSize = PageSize.A4,
        orientation: PageOrientation = PageOrientation.PORTRAIT,
        margin_mm: float | None = None,
    ) -> bool:
        """Render an HTML string to a PDF file using Chromium.

        Blocks the current thread (spins a local QEventLoop) until the PDF
        is written.  Must be called from the main Qt thread.

        Returns True on success, False on failure.
        """
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWebEngineCore import QWebEnginePage

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        page_layout = self._make_page_layout(page_size, orientation, margin_mm)

        loop = QEventLoop()
        result: list[bool] = [False]

        page = QWebEnginePage()

        def _on_load_finished(ok: bool) -> None:
            if not ok:
                loop.quit()
                return
            page.printToPdf(output_path, page_layout)

        def _on_pdf_finished(path: str, success: bool) -> None:
            result[0] = success
            loop.quit()

        page.loadFinished.connect(_on_load_finished)
        page.pdfPrintingFinished.connect(_on_pdf_finished)

        # Resolve relative resources — use a data: URL for pure-HTML docs
        page.setHtml(html_content, "about:blank")

        loop.exec()

        return result[0]

    # ── preview widget ─────────────────────────────────────────────────────────

    def make_preview_view(
        self,
        html_content: str,
        parent: QWidget | None = None,
    ):
        """Return a QWebEngineView pre-loaded with the given HTML.

        The returned view is ready to embed in any layout.
        """
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView(parent)
        view.setHtml(html_content, "about:blank")
        return view

    def update_preview(self, view, html_content: str) -> None:
        """Replace the HTML content of an existing QWebEngineView."""
        view.setHtml(html_content, "about:blank")

    # ── physical printer ───────────────────────────────────────────────────────

    def print_to_printer(
        self,
        html_content: str,
        printer,
        *,
        page_size: PageSize = PageSize.A4,
        orientation: PageOrientation = PageOrientation.PORTRAIT,
    ) -> bool:
        """Render HTML to a physical printer via Chromium's print pipeline.

        Caller is responsible for configuring QPrinter (paper, copies, etc.)
        before calling this method.  Returns True on success.
        """
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWebEngineCore import QWebEnginePage

        loop = QEventLoop()
        result: list[bool] = [False]

        page = QWebEnginePage()

        def _on_load_finished(ok: bool) -> None:
            if not ok:
                loop.quit()
                return
            page.print(printer)

        def _on_print_finished(success: bool) -> None:
            result[0] = success
            loop.quit()

        page.loadFinished.connect(_on_load_finished)
        page.printFinished.connect(_on_print_finished)

        page.setHtml(html_content, "about:blank")
        loop.exec()

        return result[0]
