"""Payroll workbench Statutory pane (Phase 2, slice S6).

Two-tab surface covering statutory compliance:

1. **Packs** — available and applied statutory packs (CNPS/IRPP rules).
   "Apply Pack" opens the activation wizard.
2. **Remittances** — remittance batch history with totals.

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
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_remittance_dto import (
    PayrollRemittanceBatchListItemDTO,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, StatusChip
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)


# ── Packs tab ─────────────────────────────────────────────────────────────────

class _PacksTab(QWidget):
    def __init__(self, sr: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = sr

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Available packs section
        avail_title = QLabel("Available statutory packs", self)
        avail_title.setObjectName("SetupCardTitle")
        layout.addWidget(avail_title)

        self._avail_model = _SimpleTextModel(("Pack Code", "Country", "Description"))
        avail_cols = [
            DataTableColumn(key="code", title="Pack Code", width=120),
            DataTableColumn(key="country", title="Country", width=100),
            DataTableColumn(key="desc", title="Description", width=320),
        ]
        self._avail_table = DataTable(columns=avail_cols, parent=self)
        self._avail_table.set_model(self._avail_model)
        self._avail_table.setMaximumHeight(160)
        layout.addWidget(self._avail_table)

        # Apply pack button
        apply_row = QFrame(self)
        apply_layout = QHBoxLayout(apply_row)
        apply_layout.setContentsMargins(0, 0, 0, 0)
        apply_layout.setSpacing(8)

        self._apply_btn = QPushButton("Apply Pack via Activation Wizard…", apply_row)
        self._apply_btn.setObjectName("ApplyPackButton")
        self._apply_btn.setProperty("variant", "primary")
        self._apply_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_btn.clicked.connect(self._open_activation_wizard)
        apply_layout.addWidget(self._apply_btn)
        apply_layout.addStretch(1)
        layout.addWidget(apply_row)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("SetupCardSeparator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Applied pack info
        applied_title = QLabel("Current Applied Pack", self)
        applied_title.setObjectName("SetupCardTitle")
        layout.addWidget(applied_title)

        self._applied_label = QLabel("—", self)
        self._applied_label.setObjectName("SetupKvValue")
        layout.addWidget(self._applied_label)

        layout.addStretch(1)

        self.refresh()

    def refresh(self) -> None:
        # Load available packs
        svc = getattr(self._sr, "payroll_statutory_pack_service", None)
        if svc is not None:
            try:
                packs = svc.list_available_packs()
                rows = []
                for p in packs:
                    rows.append((
                        getattr(p, "pack_code", "") or "",
                        getattr(p, "country_code", "") or "",
                        getattr(p, "display_name", "") or "",
                    ))
                self._avail_model.load(rows)
            except Exception:
                logger.debug("list_available_packs failed", exc_info=True)
        else:
            self._avail_model.load([])

        # Load applied pack from settings
        company_id = self._active_company_id()
        if company_id is None:
            self._applied_label.setText("No active company")
            return

        setup_svc = getattr(self._sr, "payroll_setup_service", None)
        if setup_svc is not None:
            try:
                settings = setup_svc.get_company_payroll_settings(company_id)
                if settings is not None:
                    pack_ver = getattr(settings, "statutory_pack_version_code", None)
                    self._applied_label.setText(pack_ver or "No pack applied yet")
                else:
                    self._applied_label.setText("Not configured")
            except Exception:
                self._applied_label.setText("—")
        else:
            self._applied_label.setText("—")

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            c = ctx.get_active_company()
            return getattr(c, "id", None) if c else None
        except Exception:
            return None

    def _active_company(self) -> Any | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            return ctx.get_active_company()
        except Exception:
            return None

    def _open_activation_wizard(self) -> None:
        company = self._active_company()
        if company is None:
            return
        try:
            from seeker_accounting.modules.payroll.ui.wizards.payroll_activation_wizard import (
                PayrollActivationWizardDialog,
            )
            result = PayrollActivationWizardDialog.run(
                self._sr,
                company_id=company.id,
                company_name=getattr(company, "name", ""),
                parent=self,
            )
            if result is not None:
                self.refresh()
        except Exception:
            logger.warning("PayrollActivationWizardDialog failed", exc_info=True)


# ── Remittances tab ───────────────────────────────────────────────────────────

class _RemittanceTableModel(QAbstractTableModel):
    _HEADERS = ("Batch No.", "Statutory authority", "Period", "Amount Due", "Amount Paid", "Outstanding", "Status")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[PayrollRemittanceBatchListItemDTO] = []

    def load(self, rows: list[PayrollRemittanceBatchListItemDTO]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._rows.sort(key=lambda r: str(r.period_start_date), reverse=True)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.batch_number or ""
            if col == 1:
                return (row.remittance_authority_code or "").upper()
            if col == 2:
                return f"{row.period_start_date} – {row.period_end_date}"
            if col == 3:
                return f"{row.amount_due:,.2f}"
            if col == 4:
                return f"{row.amount_paid:,.2f}"
            if col == 5:
                return f"{row.outstanding:,.2f}"
            if col == 6:
                return (row.status_code or "").replace("_", " ").title()

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (3, 4, 5):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._HEADERS)
        ):
            return self._HEADERS[section]
        return None


class _RemittancesTab(QWidget):
    def __init__(self, sr: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = sr
        self._model = _RemittanceTableModel(self)

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
            DataTableColumn(key="batch_no", title="Batch No.", width=120),
            DataTableColumn(key="authority", title="Statutory authority", width=130),
            DataTableColumn(key="period", title="Period", width=160),
            DataTableColumn(key="due", title="Amount Due", width=120, is_numeric=True),
            DataTableColumn(key="paid", title="Amount Paid", width=120, is_numeric=True),
            DataTableColumn(key="outstanding", title="Outstanding", width=120, is_numeric=True),
            DataTableColumn(key="status", title="Status", width=100),
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

        svc = getattr(self._sr, "payroll_remittance_service", None)
        if svc is None:
            self._model.load([])
            self._count_label.setText("")
            return

        try:
            batches = svc.list_batches(company_id)
        except Exception:
            logger.warning("payroll_remittance_service.list_batches failed", exc_info=True)
            batches = []

        self._model.load(batches)
        n = len(batches)
        self._count_label.setText(f"{n} batch{'es' if n != 1 else ''}")

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            c = ctx.get_active_company()
            return getattr(c, "id", None) if c else None
        except Exception:
            return None


# ── Simple text model ─────────────────────────────────────────────────────────

class _SimpleTextModel(QAbstractTableModel):
    def __init__(self, headers: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._headers = headers
        self._rows: list[tuple[str, ...]] = []

    def load(self, rows: list[tuple[str, ...]]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        r = self._rows[index.row()]
        c = index.column()
        return r[c] if c < len(r) else None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._headers)
        ):
            return self._headers[section]
        return None


# ── Statutory pane ────────────────────────────────────────────────────────────

class StatutoryPaneWidget(QWidget):
    """Native payroll statutory compliance pane for the workbench."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollStatutoryPane")
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
        self._tabs.setObjectName("PayrollStatutoryTabs")
        self._tabs.setDocumentMode(True)

        self._packs_tab = _PacksTab(self._sr, self._tabs)
        self._remittances_tab = _RemittancesTab(self._sr, self._tabs)

        self._tabs.addTab(self._packs_tab, "Packs")
        self._tabs.addTab(self._remittances_tab, "Remittances")

        layout.addWidget(self._tabs, 1)

    def refresh(self) -> None:
        self._packs_tab.refresh()
        self._remittances_tab.refresh()
