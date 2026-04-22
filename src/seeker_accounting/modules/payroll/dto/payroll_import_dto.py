from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ImportRowIssueDTO:
    row_number: int
    column: str
    message: str
    severity: str  # error, warning


@dataclass(frozen=True, slots=True)
class ImportPreviewRowDTO:
    row_number: int
    values: dict[str, str]
    issues: tuple[ImportRowIssueDTO, ...]

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


@dataclass(frozen=True, slots=True)
class ImportPreviewResultDTO:
    entity_type: str  # departments, positions, employees, etc.
    file_path: str
    total_rows: int
    valid_rows: int
    error_rows: int
    warning_rows: int
    columns_found: tuple[str, ...]
    columns_expected: tuple[str, ...]
    preview_rows: tuple[ImportPreviewRowDTO, ...]

    @property
    def has_errors(self) -> bool:
        return self.error_rows > 0


@dataclass(frozen=True, slots=True)
class ImportResultDTO:
    entity_type: str
    total_rows: int
    created: int
    skipped: int
    errors: int
    messages: tuple[str, ...]
