"""Shared document workspace primitives (Operational Desktop Phase 3)."""

from seeker_accounting.shared.ui.document.document_workspace import (
    DocumentWorkspace,
    DocumentWorkspaceSpec,
)
from seeker_accounting.shared.ui.document.document_lines_grid import (
    configure_document_lines_grid,
)

__all__ = [
    "DocumentWorkspace",
    "DocumentWorkspaceSpec",
    "configure_document_lines_grid",
]
