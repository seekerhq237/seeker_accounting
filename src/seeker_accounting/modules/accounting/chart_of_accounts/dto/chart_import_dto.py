from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ImportChartTemplateCommand:
    source_kind: str
    file_path: str | None = None
    template_code: str | None = None
    add_missing_only: bool = True


@dataclass(frozen=True, slots=True)
class ChartTemplateProfileDTO:
    template_code: str
    display_name: str
    version: str
    description: str
    source_name: str
    source_format: str
    row_count: int
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ChartImportPreviewDTO:
    source_label: str
    template_code: str | None
    add_missing_only: bool
    total_source_rows: int
    normalized_row_count: int
    importable_count: int
    skipped_existing_count: int
    duplicate_source_count: int
    invalid_row_count: int
    conflict_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ChartImportResultDTO:
    source_label: str
    template_code: str | None
    add_missing_only: bool
    total_source_rows: int
    normalized_row_count: int
    imported_count: int
    skipped_existing_count: int
    duplicate_source_count: int
    invalid_row_count: int
    conflict_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ChartSeedResultDTO:
    company_id: int
    template_code: str
    total_template_rows: int
    imported_count: int
    skipped_existing_count: int
    duplicate_source_count: int
    invalid_row_count: int
    conflict_count: int
    messages: tuple[str, ...] = field(default_factory=tuple)
