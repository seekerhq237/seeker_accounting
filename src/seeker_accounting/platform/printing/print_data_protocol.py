"""Shared enums and base data types for the Seeker Accounting print/export system."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum


class PrintFormat(str, Enum):
    PDF = "pdf"
    WORD = "word"
    EXCEL = "excel"

    @property
    def label(self) -> str:
        return {
            PrintFormat.PDF: "PDF Document",
            PrintFormat.WORD: "Word Document",
            PrintFormat.EXCEL: "Excel Spreadsheet",
        }[self]

    @property
    def file_extension(self) -> str:
        return {
            PrintFormat.PDF: "pdf",
            PrintFormat.WORD: "docx",
            PrintFormat.EXCEL: "xlsx",
        }[self]

    @property
    def file_filter(self) -> str:
        return {
            PrintFormat.PDF: "PDF Document (*.pdf)",
            PrintFormat.WORD: "Word Document (*.docx)",
            PrintFormat.EXCEL: "Excel Spreadsheet (*.xlsx)",
        }[self]


class PageSize(str, Enum):
    A4 = "a4"
    A5 = "a5"

    @property
    def label(self) -> str:
        return self.value.upper()

    @property
    def dimensions_mm(self) -> tuple[float, float]:
        """Returns (width_mm, height_mm) in portrait orientation."""
        return {
            PageSize.A4: (210.0, 297.0),
            PageSize.A5: (148.0, 210.0),
        }[self]

    @property
    def body_font_size_pt(self) -> int:
        """Appropriate body font size for this page size."""
        return {PageSize.A4: 10, PageSize.A5: 9}[self]

    @property
    def margin_mm(self) -> float:
        """Recommended page margin for this page size."""
        return {PageSize.A4: 18.0, PageSize.A5: 12.0}[self]


class PageOrientation(str, Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"

    @property
    def label(self) -> str:
        return self.value.capitalize()


@dataclass(frozen=True, slots=True)
class CompanyHeaderData:
    """Company identity data for document headers and footers."""

    name: str
    legal_name: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    phone: str | None = None
    email: str | None = None
    tax_identifier: str | None = None
    registration_number: str | None = None
    logo_path: str | None = None

    @property
    def address_block(self) -> list[str]:
        """Returns non-empty address lines for display."""
        parts: list[str] = []
        if self.address_line_1:
            parts.append(self.address_line_1)
        if self.address_line_2:
            parts.append(self.address_line_2)
        city_line = ", ".join(filter(None, [self.city, self.region]))
        if city_line:
            parts.append(city_line)
        if self.country:
            country = self.country.strip()
            looks_like_country_code = (
                len(country) <= 3
                and country.upper() == country
                and country.replace(" ", "").isalpha()
            )
            if country and (parts or not looks_like_country_code):
                parts.append(country)
        return parts


@dataclass(frozen=True, slots=True)
class PrintExportResult:
    """Result of a print/export dialog interaction."""

    format: PrintFormat
    output_path: str
    page_size: PageSize
    orientation: PageOrientation

    def open_file(self) -> None:
        """Open the exported file with the system default application."""
        if sys.platform == "win32":
            os.startfile(self.output_path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.output_path])
        else:
            subprocess.Popen(["xdg-open", self.output_path])
