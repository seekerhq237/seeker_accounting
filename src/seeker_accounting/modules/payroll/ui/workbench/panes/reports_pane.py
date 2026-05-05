"""Payroll workbench Reports & Audit pane (Phase 2, slice S7).

Two-tab surface:

1. **Reports** — quick-action buttons for common payroll reports:
   payslip printing, run summary, variance report, component summary.
   Each button defers to the relevant report service or dialog.

2. **Audit** — recent payroll module audit events in a read-only table
   (module_code="payroll", limit=200).

Graceful degradation
--------------------
* Any service missing or raising → empty section with calm message.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)


# ── Reports tab ───────────────────────────────────────────────────────────────

class _ReportButton(QFrame):
    """Compact card-style action button for a quick report action."""

    def __init__(
        self,
        title: str,
        description: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ReportActionCard")
        self.setProperty("card", True)
        self.setFixedHeight(DEFAULT_TOKENS.sizes.report_tile_h)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(12)

        text_block = QWidget(self)
        vl = QVBoxLayout(text_block)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(2)
        title_lbl = QLabel(title, text_block)
        title_lbl.setObjectName("ReportActionTitle")
        vl.addWidget(title_lbl)
        desc_lbl = QLabel(description, text_block)
        desc_lbl.setObjectName("ReportActionDesc")
        vl.addWidget(desc_lbl)
        hl.addWidget(text_block, 1)

        self._btn = QPushButton("Open", self)
        self._btn.setObjectName("ReportOpenButton")
        self._btn.setProperty("variant", "secondary")
        self._btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        hl.addWidget(self._btn)

    @property
    def button(self) -> QPushButton:
        return self._btn


class _ReportsTab(QWidget):
    def __init__(self, sr: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = sr

        scroll = QScrollArea(self)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)

        content = QWidget(scroll)
        content.setObjectName("ReportsTabContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        section_title = QLabel("Payroll Reports", content)
        section_title.setObjectName("SetupCardTitle")
        layout.addWidget(section_title)

        # Payslips
        card1 = _ReportButton(
            "Payslip Batch",
            "Generate and print payslips for a payroll run.",
            content,
        )
        card1.button.clicked.connect(self._open_payslip_report)
        layout.addWidget(card1)

        # Run summary
        card2 = _ReportButton(
            "Run Summary",
            "Gross, deductions, net, and statutory totals for a run.",
            content,
        )
        card2.button.clicked.connect(self._open_run_summary)
        layout.addWidget(card2)

        # Variance report
        card3 = _ReportButton(
            "Variance Report",
            "Period-over-period differences per employee and component.",
            content,
        )
        card3.button.clicked.connect(self._open_variance_report)
        layout.addWidget(card3)

        # Component summary
        card4 = _ReportButton(
            "Component Summary",
            "Total amounts per component across all included employees.",
            content,
        )
        card4.button.clicked.connect(self._open_component_summary)
        layout.addWidget(card4)

        layout.addStretch(1)
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll, 1)

    def _navigate_reports(self) -> None:
        nav_svc = getattr(self._sr, "navigation_service", None)
        if nav_svc is not None:
            try:
                from seeker_accounting.app.navigation.nav_ids import REPORTS
                nav_svc.navigate(REPORTS)
                return
            except Exception:
                pass

    def _open_payslip_report(self) -> None:
        try:
            from seeker_accounting.modules.payroll.ui.dialogs.payslip_batch_dialog import (
                PayslipBatchDialog,
            )
            dlg = PayslipBatchDialog(self._sr, parent=self)
            dlg.exec()
        except ImportError:
            self._navigate_reports()
        except Exception:
            logger.warning("PayslipBatchDialog failed", exc_info=True)

    def _open_run_summary(self) -> None:
        try:
            from seeker_accounting.modules.payroll.ui.dialogs.payroll_run_summary_dialog import (
                PayrollRunSummaryDialog,
            )
            dlg = PayrollRunSummaryDialog(self._sr, parent=self)
            dlg.exec()
        except ImportError:
            self._navigate_reports()
        except Exception:
            logger.warning("PayrollRunSummaryDialog failed", exc_info=True)

    def _open_variance_report(self) -> None:
        try:
            from seeker_accounting.modules.payroll.ui.dialogs.payroll_variance_report_dialog import (
                PayrollVarianceReportDialog,
            )
            dlg = PayrollVarianceReportDialog(self._sr, parent=self)
            dlg.exec()
        except ImportError:
            self._navigate_reports()
        except Exception:
            logger.warning("PayrollVarianceReportDialog failed", exc_info=True)

    def _open_component_summary(self) -> None:
        try:
            from seeker_accounting.modules.payroll.ui.dialogs.payroll_component_summary_dialog import (
                PayrollComponentSummaryDialog,
            )
            dlg = PayrollComponentSummaryDialog(self._sr, parent=self)
            dlg.exec()
        except ImportError:
            self._navigate_reports()
        except Exception:
            logger.warning("PayrollComponentSummaryDialog failed", exc_info=True)


# ── Audit tab ─────────────────────────────────────────────────────────────────

class _AuditTableModel(QAbstractTableModel):
    _HEADERS = ("When", "Event", "Entity", "Actor", "Description")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[Any] = []

    def load(self, rows: list[Any]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        row = self._rows[index.row()]
        col = index.column()

        if col == 0:
            ts = getattr(row, "occurred_at", None) or getattr(row, "created_at", None)
            if ts is not None:
                try:
                    return ts.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    return str(ts)
            return "—"
        if col == 1:
            return (getattr(row, "event_type_code", None) or "").replace("_", " ").title()
        if col == 2:
            etype = getattr(row, "entity_type", None) or ""
            eid = getattr(row, "entity_id", None)
            if eid:
                return f"{etype} #{eid}"
            return etype or "—"
        if col == 3:
            uid = getattr(row, "actor_user_id", None)
            return f"User {uid}" if uid else "System"
        if col == 4:
            return getattr(row, "description", None) or ""

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._HEADERS)
        ):
            return self._HEADERS[section]
        return None


class _AuditTab(QWidget):
    def __init__(self, sr: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = sr
        self._model = _AuditTableModel(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame(self)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(8, 6, 8, 6)
        tb.setSpacing(8)
        self._count_label = QLabel("", toolbar)
        self._count_label.setObjectName("WorkbenchPaneCountLabel")
        tb.addWidget(self._count_label)
        tb.addStretch(1)
        refresh_btn = QPushButton("Refresh", toolbar)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        refresh_btn.clicked.connect(self.refresh)
        tb.addWidget(refresh_btn)
        layout.addWidget(toolbar)

        cols = [
            DataTableColumn(key="when", title="When", width=130),
            DataTableColumn(key="event", title="Event", width=180),
            DataTableColumn(key="entity", title="Entity", width=130),
            DataTableColumn(key="actor", title="Actor", width=100),
            DataTableColumn(key="desc", title="Description", width=360),
        ]
        self._table = DataTable(columns=cols, parent=self)
        self._table.set_model(self._model)
        layout.addWidget(self._table, 1)

        self.refresh()

    def refresh(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            self._model.load([])
            self._count_label.setText("No active company")
            return

        svc = getattr(self._sr, "audit_service", None)
        if svc is None:
            self._model.load([])
            self._count_label.setText("")
            return

        try:
            events = svc.list_events(
                company_id,
                module_code="payroll",
                limit=200,
            )
        except Exception:
            logger.warning("audit_service.list_events failed", exc_info=True)
            events = []

        self._model.load(events)
        n = len(events)
        self._count_label.setText(f"{n} event{'s' if n != 1 else ''}")

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            c = ctx.get_active_company()
            return getattr(c, "id", None) if c else None
        except Exception:
            return None


# ── Reports/Audit pane ────────────────────────────────────────────────────────

class ReportsAuditPaneWidget(QWidget):
    """Native payroll reports and audit pane for the workbench."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollReportsAuditPane")
        self._sr = service_registry

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        tok = DEFAULT_TOKENS
        layout.setContentsMargins(
            tok.spacing.page_padding,
            tok.spacing.section_gap,
            tok.spacing.page_padding,
            tok.spacing.section_gap,
        )
        layout.setSpacing(0)

        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("PayrollReportsAuditTabs")
        self._tabs.setDocumentMode(True)

        self._reports_tab = _ReportsTab(self._sr, self._tabs)
        self._audit_tab = _AuditTab(self._sr, self._tabs)

        self._tabs.addTab(self._reports_tab, "Reports")
        self._tabs.addTab(self._audit_tab, "Audit Log")

        layout.addWidget(self._tabs, 1)

    def refresh(self) -> None:
        self._audit_tab.refresh()
