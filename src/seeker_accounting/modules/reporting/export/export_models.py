"""Shared data types for financial statement export (PDF / Word / Excel).

This module is fully independent from ``seeker_accounting.platform.printing``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StatementExportFormat(str, Enum):
    PDF = "pdf"
    WORD = "word"
    EXCEL = "excel"

    @property
    def label(self) -> str:
        _labels = {"pdf": "PDF", "word": "Word Document", "excel": "Excel Spreadsheet"}
        return _labels[self.value]

    @property
    def file_extension(self) -> str:
        _ext = {"pdf": ".pdf", "word": ".docx", "excel": ".xlsx"}
        return _ext[self.value]

    @property
    def file_filter(self) -> str:
        _filters = {
            "pdf": "PDF Files (*.pdf)",
            "word": "Word Documents (*.docx)",
            "excel": "Excel Spreadsheets (*.xlsx)",
        }
        return _filters[self.value]


class StatementPageSize(str, Enum):
    A4 = "a4"
    A5 = "a5"

    @property
    def label(self) -> str:
        return {"a4": "A4", "a5": "A5"}[self.value]

    @property
    def dimensions_mm(self) -> tuple[float, float]:
        return {"a4": (210.0, 297.0), "a5": (148.0, 210.0)}[self.value]

    @property
    def margin_mm(self) -> float:
        return {"a4": 18.0, "a5": 12.0}[self.value]

    @property
    def body_font_pt(self) -> int:
        return {"a4": 10, "a5": 9}[self.value]


class StatementPageOrientation(str, Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"

    @property
    def label(self) -> str:
        return self.value.capitalize()


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StatementCompanyInfo:
    """Company identity data for export headers/footers."""

    name: str
    legal_name: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    phone: str | None = None
    email: str | None = None
    tax_identifier: str | None = None
    registration_number: str | None = None
    logo_path: str | None = None

    @property
    def address_block(self) -> list[str]:
        parts: list[str] = []
        if self.address_line_1:
            parts.append(self.address_line_1)
        if self.address_line_2:
            parts.append(self.address_line_2)
        city_region: list[str] = []
        if self.city:
            city_region.append(self.city)
        if self.region:
            city_region.append(self.region)
        if city_region:
            parts.append(", ".join(city_region))
        return parts


@dataclass(frozen=True, slots=True)
class StatementExportResult:
    """Result returned by the export dialog."""

    format: StatementExportFormat
    output_path: str
    page_size: StatementPageSize
    orientation: StatementPageOrientation

    def open_file(self) -> None:
        """Open the exported file with the system default application."""
        path = self.output_path
        if not os.path.isfile(path):
            return
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])  # noqa: S603, S607
        else:
            subprocess.Popen(["xdg-open", path])  # noqa: S603, S607


@dataclass(frozen=True, slots=True)
class StatementExportRow:
    """Normalized row for financial statement rendering.

    Each row represents one line within a table section.
    """

    row_kind: str  # "section", "group", "line", "formula", "subtotal", "subsection", "total"
    indent_level: int
    ref_code: str
    label: str
    amounts: tuple[Decimal | None, ...] = field(default_factory=tuple)
    is_highlight: bool = False


@dataclass(frozen=True, slots=True)
class StatementTableSection:
    """A table section within a financial statement export.

    Each section has its own column headers and rows, enabling different
    parts of a statement to have different structures.  For example, an
    OHADA Balance Sheet has an *Assets* section with five columns (Ref,
    Description, Gross, Amort/Deprec, Net) and a *Liabilities & Equity*
    section with three columns (Ref, Description, Amount).
    """

    heading: str | None = None
    column_headers: tuple[str, ...] = field(default_factory=tuple)
    rows: tuple[StatementExportRow, ...] = field(default_factory=tuple)
    column_widths: tuple[float, ...] | None = None
