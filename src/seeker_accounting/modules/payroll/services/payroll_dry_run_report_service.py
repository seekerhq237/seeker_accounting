from __future__ import annotations

import csv
import html
import os
from typing import Callable

from seeker_accounting.modules.payroll.dto.payroll_variance_dto import (
    PayrollDryRunReportResultDTO,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_PRINT
from seeker_accounting.modules.payroll.services.payroll_variance_analysis_service import (
    PayrollVarianceAnalysisService,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService


class PayrollDryRunReportService:
    """Export a pre-posting audit pack from persisted calculation output."""

    def __init__(
        self,
        variance_service: PayrollVarianceAnalysisService,
        permission_service: PermissionService,
    ) -> None:
        self._variance_service = variance_service
        self._permission_service = permission_service

    def export_report(
        self,
        company_id: int,
        run_id: int,
        output_path: str,
        fmt: str = "csv",
    ) -> PayrollDryRunReportResultDTO:
        self._permission_service.require_permission(PAYROLL_PRINT)
        analysis = self._variance_service.analyze_run(company_id, run_id)
        fmt = fmt.lower().strip()
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        if fmt == "csv":
            self._write_csv(analysis, output_path)
        elif fmt in {"html", "pdf"}:
            html_content = self._build_html(analysis)
            if fmt == "html":
                with open(output_path, "w", encoding="utf-8") as handle:
                    handle.write(html_content)
            else:
                self._render_pdf(html_content, output_path)
        else:
            raise ValueError(f"Unsupported dry-run report format: {fmt!r}")
        return PayrollDryRunReportResultDTO(
            file_path=output_path,
            format=fmt,
            run_id=analysis.run_id,
            run_reference=analysis.run_reference,
            warning_count=sum(1 for line in analysis.lines if line.severity_code != "info"),
        )

    @staticmethod
    def _write_csv(analysis: object, output_path: str) -> None:
        with open(output_path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Run", analysis.run_reference])
            writer.writerow(["Prior Run", analysis.prior_run_reference or ""])
            writer.writerow(["Threshold Percent", str(analysis.threshold_percent)])
            writer.writerow([])
            writer.writerow(["Category", "Subject", "Prior", "Current", "Delta", "Delta %", "Severity", "Explanation"])
            for line in analysis.lines:
                writer.writerow([
                    line.category_code,
                    line.subject_label,
                    str(line.prior_amount),
                    str(line.current_amount),
                    str(line.delta_amount),
                    "" if line.delta_percent is None else str(line.delta_percent),
                    line.severity_code,
                    line.explanation,
                ])

    @staticmethod
    def _build_html(analysis: object) -> str:
        rows = []
        for line in analysis.lines:
            rows.append(
                "<tr>"
                f"<td>{html.escape(line.category_code)}</td>"
                f"<td>{html.escape(line.subject_label)}</td>"
                f"<td class='num'>{line.prior_amount:,.2f}</td>"
                f"<td class='num'>{line.current_amount:,.2f}</td>"
                f"<td class='num'>{line.delta_amount:,.2f}</td>"
                f"<td>{html.escape(line.severity_code)}</td>"
                f"<td>{html.escape(line.explanation)}</td>"
                "</tr>"
            )
        return "".join([
            "<!doctype html><html><head><meta charset='utf-8'>",
            "<style>body{font-family:Segoe UI,Arial,sans-serif;font-size:10pt;color:#1F2933;margin:24px;}"
            "h1{font-size:16pt;margin:0 0 4px;}table{border-collapse:collapse;width:100%;}"
            "th{background:#2F4F6F;color:white;text-align:left;padding:6px;}td{border-bottom:1px solid #EAF1F7;padding:5px;}"
            ".num{text-align:right;font-variant-numeric:tabular-nums;}</style></head><body>",
            f"<h1>Payroll Dry-Run Audit Pack - {html.escape(analysis.run_reference)}</h1>",
            f"<p>Prior run: {html.escape(analysis.prior_run_reference or 'None')} | Threshold: {analysis.threshold_percent}%</p>",
            "<table><tr><th>Category</th><th>Subject</th><th>Prior</th><th>Current</th><th>Delta</th><th>Severity</th><th>Explanation</th></tr>",
            *rows,
            "</table></body></html>",
        ])

    @staticmethod
    def _render_pdf(html_content: str, output_path: str) -> None:
        from seeker_accounting.platform.printing.print_data_protocol import PageOrientation, PageSize
        from seeker_accounting.platform.printing.web_renderer import WebDocumentRenderer

        renderer = WebDocumentRenderer()
        ok = renderer.render_pdf(
            html_content,
            output_path,
            page_size=PageSize.A4,
            orientation=PageOrientation.PORTRAIT,
            margin_mm=8,
        )
        if not ok:
            raise RuntimeError(f"Chromium PDF rendering failed for: {output_path}")
