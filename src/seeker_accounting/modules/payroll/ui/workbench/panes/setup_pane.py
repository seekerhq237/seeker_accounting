"""Payroll workbench Setup pane (Phase 2, slice S5).

Tabbed surface covering company payroll configuration:

1. **Settings** — pay frequency, currency, CNPS regime, risk class.
2. **Departments** — list + add/edit (service-backed).
3. **Positions**   — list + add/edit (service-backed).
4. **Components**  — payroll component registry (read + "Manage" button
   that defers to the legacy component dialog).

All reads are gracefully degraded: if a service is missing or raises,
the tab shows an empty/calm placeholder.
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
from seeker_accounting.shared.ui.keyboard_shortcuts import install_shortcut, shortcut_map
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)


# ── Helper: two-column KV row ─────────────────────────────────────────────────

def _kv_row(label: str, value: str, parent: QWidget) -> QWidget:
    row = QFrame(parent)
    row.setObjectName("SetupKvRow")
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 2, 0, 2)
    hl.setSpacing(12)
    lbl = QLabel(label, row)
    lbl.setObjectName("SetupKvLabel")
    lbl.setFixedWidth(DEFAULT_TOKENS.sizes.form_label_w)
    hl.addWidget(lbl)
    val = QLabel(value or "—", row)
    val.setObjectName("SetupKvValue")
    val.setWordWrap(True)
    hl.addWidget(val, 1)
    return row


# ── Generic DataTable model for simple lists ──────────────────────────────────

class _SimpleTableModel(QAbstractTableModel):
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


# ── Settings tab ──────────────────────────────────────────────────────────────

class _SettingsTab(QWidget):
    def __init__(self, sr: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = sr
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(4)
        self._content: QWidget | None = None
        self.refresh()

    def refresh(self) -> None:
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.deleteLater()
            self._content = None

        company_id = self._active_company_id()
        if company_id is None:
            lbl = QLabel("No active company.", self)
            lbl.setObjectName("PaneEmptyLabel")
            self._content = lbl
            self._layout.addWidget(lbl)
            self._layout.addStretch(1)
            return

        svc = getattr(self._sr, "payroll_setup_service", None)
        settings = None
        if svc is not None:
            try:
                settings = svc.get_company_payroll_settings(company_id)
            except Exception:
                logger.debug("get_company_payroll_settings failed", exc_info=True)

        card = QFrame(self)
        card.setObjectName("SetupSettingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 16)
        card_layout.setSpacing(2)

        title = QLabel("Company Payroll Settings", card)
        title.setObjectName("SetupCardTitle")
        card_layout.addWidget(title)

        sep = QFrame(card)
        sep.setObjectName("SetupCardSeparator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        card_layout.addWidget(sep)
        card_layout.addSpacing(6)

        if settings is None:
            not_configured = QLabel(
                "Payroll settings have not been configured yet. "
                "Use the Activation Wizard to set them up.",
                card,
            )
            not_configured.setObjectName("PaneEmptyLabel")
            not_configured.setWordWrap(True)
            card_layout.addWidget(not_configured)
        else:
            pairs = [
                ("Pay Frequency", getattr(settings, "pay_frequency_code", None) or "—"),
                ("Currency", getattr(settings, "currency_code", None) or "—"),
                ("CNPS Regime", getattr(settings, "cnps_regime_code", None) or "—"),
                ("Accident Risk Class", getattr(settings, "accident_risk_class", None) or "—"),
                ("Statutory pack", getattr(settings, "statutory_pack_version_code", None) or "Not applied"),
                ("Probation Days", str(getattr(settings, "probation_days", None) or "—")),
            ]
            for label, value in pairs:
                card_layout.addWidget(_kv_row(label, value, card))

        card_layout.addStretch(1)

        # Activation wizard button
        wizard_btn = QPushButton("Open Activation Wizard…", card)
        wizard_btn.setObjectName("ActivationWizardButton")
        wizard_btn.setProperty("variant", "secondary")
        wizard_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        wizard_btn.clicked.connect(self._open_activation_wizard)
        card_layout.addWidget(wizard_btn)

        self._content = card
        self._layout.addWidget(card)
        self._layout.addStretch(1)

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            company = ctx.get_active_company()
            return getattr(company, "id", None) if company else None
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


# ── Department tab ────────────────────────────────────────────────────────────

class _DepartmentTab(QWidget):
    def __init__(self, sr: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = sr
        self._model = _SimpleTableModel(("Code", "Name", "Active"))
        self._row_ids: list[int] = []

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
        self._new_btn = QPushButton("Manage…", toolbar)
        self._new_btn.setObjectName("DeptTabNewBtn")
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._new_btn.clicked.connect(self._on_manage)
        tb.addWidget(self._new_btn)
        refresh_btn = QPushButton("Refresh", toolbar)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        refresh_btn.clicked.connect(self.refresh)
        tb.addWidget(refresh_btn)
        layout.addWidget(toolbar)

        _sc = shortcut_map("payroll.setup")
        install_shortcut(self, _sc["new_item"], self._on_manage)

        cols = [
            DataTableColumn(key="code", title="Code", width=100),
            DataTableColumn(key="name", title="Name", width=220),
            DataTableColumn(key="active", title="Active", width=70),
        ]
        self._table = DataTable(columns=cols, parent=self)
        self._table.set_model(self._model)
        layout.addWidget(self._table, 1)

        self.refresh()

    def _on_manage(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            return
        ctx = getattr(self._sr, "company_context_service", None)
        company_name = ""
        if ctx is not None:
            try:
                c = ctx.get_active_company()
                company_name = getattr(c, "name", "") or ""
            except Exception:
                pass
        from seeker_accounting.modules.payroll.ui.dialogs.department_dialog import (
            DepartmentManagementDialog,
        )
        dlg = DepartmentManagementDialog(
            service_registry=self._sr,
            company_id=company_id,
            company_name=company_name,
            parent=self,
        )
        dlg.exec()
        self.refresh()

    def refresh(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            self._model.load([])
            self._count_label.setText("No active company")
            return
        svc = getattr(self._sr, "payroll_setup_service", None)
        if svc is None:
            self._model.load([])
            return
        try:
            depts = svc.list_departments(company_id)
        except Exception:
            logger.warning("list_departments failed", exc_info=True)
            self._model.load([])
            self._count_label.setText("Could not load departments")
            return
        rows = []
        for d in depts:
            rows.append((
                getattr(d, "code", "") or "",
                getattr(d, "name", "") or "",
                "Yes" if getattr(d, "is_active", True) else "No",
            ))
        self._model.load(rows)
        self._count_label.setText(f"{len(rows)} department{'s' if len(rows) != 1 else ''}")

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            c = ctx.get_active_company()
            return getattr(c, "id", None) if c else None
        except Exception:
            return None


# ── Position tab ──────────────────────────────────────────────────────────────

class _PositionTab(QWidget):
    def __init__(self, sr: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = sr
        self._model = _SimpleTableModel(("Code", "Name", "Department", "Active"))

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
        self._new_pos_btn = QPushButton("Manage…", toolbar)
        self._new_pos_btn.setObjectName("PosTabNewBtn")
        self._new_pos_btn.setProperty("variant", "primary")
        self._new_pos_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._new_pos_btn.clicked.connect(self._on_manage)
        tb.addWidget(self._new_pos_btn)
        refresh_btn = QPushButton("Refresh", toolbar)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        refresh_btn.clicked.connect(self.refresh)
        tb.addWidget(refresh_btn)
        layout.addWidget(toolbar)

        _sc = shortcut_map("payroll.setup")
        install_shortcut(self, _sc["new_item"], self._on_manage)

        cols = [
            DataTableColumn(key="code", title="Code", width=100),
            DataTableColumn(key="name", title="Name", width=220),
            DataTableColumn(key="dept", title="Department", width=150),
            DataTableColumn(key="active", title="Active", width=70),
        ]
        self._table = DataTable(columns=cols, parent=self)
        self._table.set_model(self._model)
        layout.addWidget(self._table, 1)

        self.refresh()

    def _on_manage(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            return
        ctx = getattr(self._sr, "company_context_service", None)
        company_name = ""
        if ctx is not None:
            try:
                c = ctx.get_active_company()
                company_name = getattr(c, "name", "") or ""
            except Exception:
                pass
        from seeker_accounting.modules.payroll.ui.dialogs.position_dialog import (
            PositionManagementDialog,
        )
        dlg = PositionManagementDialog(
            service_registry=self._sr,
            company_id=company_id,
            company_name=company_name,
            parent=self,
        )
        dlg.exec()
        self.refresh()

    def refresh(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            self._model.load([])
            self._count_label.setText("No active company")
            return
        svc = getattr(self._sr, "payroll_setup_service", None)
        if svc is None:
            self._model.load([])
            return
        try:
            positions = svc.list_positions(company_id)
        except Exception:
            logger.warning("list_positions failed", exc_info=True)
            self._model.load([])
            self._count_label.setText("Could not load positions")
            return
        rows = []
        for p in positions:
            rows.append((
                getattr(p, "code", "") or "",
                getattr(p, "name", "") or "",
                getattr(p, "department_name", None) or getattr(p, "department_code", None) or "—",
                "Yes" if getattr(p, "is_active", True) else "No",
            ))
        self._model.load(rows)
        self._count_label.setText(f"{len(rows)} position{'s' if len(rows) != 1 else ''}")

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            c = ctx.get_active_company()
            return getattr(c, "id", None) if c else None
        except Exception:
            return None


# ── Components tab ────────────────────────────────────────────────────────────

class _ComponentsTab(QWidget):
    def __init__(self, sr: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = sr
        self._model = _SimpleTableModel(("Code", "Name", "Type", "Method", "Taxable", "Pensionable", "Active"))

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
            DataTableColumn(key="code", title="Code", width=100),
            DataTableColumn(key="name", title="Name", width=200),
            DataTableColumn(key="type", title="Type", width=100),
            DataTableColumn(key="method", title="Method", width=110),
            DataTableColumn(key="taxable", title="Taxable", width=70),
            DataTableColumn(key="pensionable", title="Pensionable", width=90),
            DataTableColumn(key="active", title="Active", width=70),
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
        svc = getattr(self._sr, "payroll_component_service", None)
        if svc is None:
            self._model.load([])
            return
        try:
            components = svc.list_components(company_id)
        except Exception:
            logger.warning("list_components failed", exc_info=True)
            self._model.load([])
            self._count_label.setText("Could not load components")
            return
        rows = []
        for c in components:
            rows.append((
                getattr(c, "component_code", "") or "",
                getattr(c, "component_name", "") or "",
                (getattr(c, "component_type_code", "") or "").replace("_", " ").title(),
                (getattr(c, "calculation_method_code", "") or "").replace("_", " ").title(),
                "Yes" if getattr(c, "is_taxable", False) else "No",
                "Yes" if getattr(c, "is_pensionable", False) else "No",
                "Yes" if getattr(c, "is_active", True) else "No",
            ))
        self._model.load(rows)
        self._count_label.setText(f"{len(rows)} component{'s' if len(rows) != 1 else ''}")

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            c = ctx.get_active_company()
            return getattr(c, "id", None) if c else None
        except Exception:
            return None


# ── Setup pane ────────────────────────────────────────────────────────────────

class SetupPaneWidget(QWidget):
    """Native payroll setup pane for the workbench."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollSetupPane")
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
        self._tabs.setObjectName("PayrollSetupTabs")
        self._tabs.setDocumentMode(True)

        self._settings_tab = _SettingsTab(self._sr, self._tabs)
        self._dept_tab = _DepartmentTab(self._sr, self._tabs)
        self._pos_tab = _PositionTab(self._sr, self._tabs)
        self._comp_tab = _ComponentsTab(self._sr, self._tabs)

        self._tabs.addTab(self._settings_tab, "Settings")
        self._tabs.addTab(self._dept_tab, "Departments")
        self._tabs.addTab(self._pos_tab, "Positions")
        self._tabs.addTab(self._comp_tab, "Components")

        layout.addWidget(self._tabs, 1)

    def refresh(self) -> None:
        self._settings_tab.refresh()
        self._dept_tab.refresh()
        self._pos_tab.refresh()
        self._comp_tab.refresh()
