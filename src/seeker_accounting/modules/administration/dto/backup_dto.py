"""DTOs for the backup/restore feature."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CompanyImportItem:
    """One company found in the backup archive."""

    src_id: int
    legal_name: str
    display_name: str
    conflict: bool
    """True when a company with the same legal_name already exists in the target DB."""
    resolved_name: str
    """The name that will be used on import (may have ' (Imported)' suffix already)."""


@dataclass(frozen=True, slots=True)
class UserImportItem:
    """One user found in the backup archive."""

    src_id: int
    username: str
    display_name: str
    conflict: bool
    """True when a user with the same username already exists in the target DB."""
    resolved_username: str
    """The username that will be used on import."""


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """Parsed from manifest.json inside the .seekerbackup file."""

    app_version: str
    export_date: str
    salt_hex: str
    nonce_hex: str


@dataclass(frozen=True, slots=True)
class BackupAnalysisDTO:
    """Result of analysing a backup archive before performing an import."""

    manifest: BackupManifest
    companies: tuple[CompanyImportItem, ...]
    users: tuple[UserImportItem, ...]
    record_summary: dict[str, int]
    """Approximate per-table row counts from the backup DB (informational)."""


@dataclass
class MergeDecisionDTO:
    """Carries the user's conflict-resolution decisions into the merge engine."""

    # Maps src_id → resolved legal_name/display_name pair
    company_names: dict[int, tuple[str, str]] = field(default_factory=dict)
    """src_id → (resolved_legal_name, resolved_display_name)"""

    # Maps src_id → resolved username
    user_names: dict[int, str] = field(default_factory=dict)
    """src_id → resolved_username"""


@dataclass(frozen=True, slots=True)
class MergeResultDTO:
    """Summary returned after a completed merge."""

    companies_imported: int
    users_imported: int
    tables_processed: int
    warnings: tuple[str, ...]
