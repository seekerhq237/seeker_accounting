"""Reusable shared UI components.

This package collects small, dependency-light widgets and delegates that
can be composed across feature modules without leaking module-specific
behaviour. Components here must depend only on ``shared/`` and never on
``app/`` or ``modules/``.
"""
from __future__ import annotations

from seeker_accounting.shared.ui.components.code_label_registry import (
    CODE_LABELS,
    CodeLabel,
    CodeLabelRegistry,
)
from seeker_accounting.shared.ui.components.command_bar import (
    CommandBar,
    CommandBarItem,
    CommandItem,
    CommandPriority,
    CommandSeparator,
    CommandVariant,
)
from seeker_accounting.shared.ui.components.confirm_dialog import (
    ConfirmDialog,
    ConfirmTier,
    confirm,
)
from seeker_accounting.shared.ui.components.data_table import (
    DataTable,
    DataTableColumn,
)
from seeker_accounting.shared.ui.components.form_dialog import (
    FormDialog,
    FormDialogSection,
    FormState,
)
from seeker_accounting.shared.ui.components.inline_issue_band import (
    InlineIssueBand,
    ValidationIssue,
)
from seeker_accounting.shared.ui.components.severity_pill import (
    DEFAULT_SEVERITY,
    VALID_SEVERITIES,
    Severity,
    SeverityPill,
    highest_severity,
    normalize_severity,
    severity_rank,
)
from seeker_accounting.shared.ui.components.side_panel import SidePanel
from seeker_accounting.shared.ui.components.status_chip import (
    DEFAULT_FAMILY,
    SEMANTIC_STATUS_MAP,
    StatusChip,
    resolve_status_family,
)
from seeker_accounting.shared.ui.components.status_chip_delegate import (
    StatusChipDelegate,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.components.workbench_primitives import (
    EmptyState,
    KpiTile,
    KpiTileData,
    Trend,
    WorkbenchHeader,
)
from seeker_accounting.shared.ui.components.workflow_stepper import (
    WorkflowStep,
    WorkflowStepState,
    WorkflowStepper,
)
from seeker_accounting.shared.ui.components.wizard_shell import (
    WizardShell,
    WizardStepDescriptor,
    WizardStepStatus,
)

__all__ = [
    "CODE_LABELS",
    "CodeLabel",
    "CodeLabelRegistry",
    "CommandBar",
    "CommandBarItem",
    "CommandItem",
    "CommandPriority",
    "CommandSeparator",
    "CommandVariant",
    "ConfirmDialog",
    "ConfirmTier",
    "DataTable",
    "DataTableColumn",
    "DEFAULT_FAMILY",
    "DEFAULT_SEVERITY",
    "EmptyState",
    "FormDialog",
    "FormDialogSection",
    "FormState",
    "InlineIssueBand",
    "KpiTile",
    "KpiTileData",
    "SEMANTIC_STATUS_MAP",
    "Severity",
    "SeverityPill",
    "SidePanel",
    "StatusChip",
    "StatusChipDelegate",
    "Trend",
    "VALID_SEVERITIES",
    "ValidationIssue",
    "WorkbenchHeader",
    "WorkflowStep",
    "WorkflowStepState",
    "WorkflowStepper",
    "WizardShell",
    "WizardStepDescriptor",
    "WizardStepStatus",    "apply_status_chip_to_column",
    "confirm",
    "highest_severity",
    "normalize_severity",
    "resolve_status_family",
    "severity_rank",
]

