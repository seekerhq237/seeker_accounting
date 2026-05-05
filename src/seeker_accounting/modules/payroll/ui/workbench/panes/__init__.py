"""Workbench panes package."""
from __future__ import annotations

from seeker_accounting.modules.payroll.ui.workbench.panes.compensation_pane import (
    CompensationPaneWidget,
)
from seeker_accounting.modules.payroll.ui.workbench.panes.reports_pane import (
    ReportsAuditPaneWidget,
)
from seeker_accounting.modules.payroll.ui.workbench.panes.run_pane import RunPaneWidget
from seeker_accounting.modules.payroll.ui.workbench.panes.setup_pane import (
    SetupPaneWidget,
)
from seeker_accounting.modules.payroll.ui.workbench.panes.statutory_pane import (
    StatutoryPaneWidget,
)

__all__ = [
    "CompensationPaneWidget",
    "ReportsAuditPaneWidget",
    "RunPaneWidget",
    "SetupPaneWidget",
    "StatutoryPaneWidget",
]
