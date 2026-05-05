"""Payroll workbench Compensation pane (Phase 2, slice S4).

Shows all employee compensation profiles for the active company.

Layout
------
* Compact toolbar — "New Profile" (primary), "Edit Profile" (selection-gated).
* DataTable — compensation profiles sorted by employee then effective date.

Integration
-----------
* "New Profile"   → opens :class:`CompensationProfileDialog` if available,
                    otherwise shows a minimal inline creation dialog.
* "Edit Profile"  → opens the profile in a dialog for editing.
* Double-click    → same as Edit.

Graceful degradation
--------------------
* No active company → toolbar disabled, empty table.
* ``compensation_profile_service`` missing → empty table, warn-logged.
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
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CompensationProfileListItemDTO,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.keyboard_shortcuts import install_shortcut, shortcut_map
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)

# ── Column definitions ────────────────────────────────────────────────────────

_COLUMNS: list[DataTableColumn] = [
    DataTableColumn(key="employee_number", title="Employee No.", width=110),
    DataTableColumn(key="employee_name", title="Employee", width=200),
    DataTableColumn(key="profile_name", title="Profile", width=160),
    DataTableColumn(key="basic_salary", title="Basic Salary", width=130, is_numeric=True),
    DataTableColumn(key="currency_code", title="Currency", width=80),
    DataTableColumn(key="effective_from", title="Effective From", width=110),
    DataTableColumn(key="effective_to", title="Effective To", width=110),
    DataTableColumn(key="is_active", title="Active", width=70),
]


# ── Table model ───────────────────────────────────────────────────────────────

class _CompensationTableModel(QAbstractTableModel):
    _HEADERS = (
        "Employee No.", "Employee", "Profile", "Basic Salary",
        "Currency", "Effective From", "Effective To", "Active",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[CompensationProfileListItemDTO] = []

    def load(self, rows: list[CompensationProfileListItemDTO]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        # Sort: active first, then by employee, then by effective_from desc
        self._rows.sort(
            key=lambda r: (
                not r.is_active,
                r.employee_display_name or "",
                str(r.effective_from),
            )
        )
        self.endResetModel()

    def row_dto(self, row: int) -> CompensationProfileListItemDTO | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

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
                return row.employee_number or ""
            if col == 1:
                return row.employee_display_name or ""
            if col == 2:
                return row.profile_name or ""
            if col == 3:
                return f"{row.basic_salary:,.2f}" if row.basic_salary else "—"
            if col == 4:
                return row.currency_code or ""
            if col == 5:
                return str(row.effective_from) if row.effective_from else "—"
            if col == 6:
                return str(row.effective_to) if row.effective_to else "Open"
            if col == 7:
                return "Yes" if row.is_active else "No"

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == 3:
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


# ── Compensation pane ─────────────────────────────────────────────────────────

class CompensationPaneWidget(QWidget):
    """Native compensation profile list pane for the workbench."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollCompensationPane")
        self._sr = service_registry
        self._model = _CompensationTableModel(self)

        self._build_ui()
        self.refresh()

    # ── Construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        tok = DEFAULT_TOKENS
        layout.setContentsMargins(
            tok.spacing.page_padding,
            tok.spacing.section_gap,
            tok.spacing.page_padding,
            tok.spacing.section_gap,
        )
        layout.setSpacing(tok.spacing.section_gap)

        # Toolbar
        toolbar = QFrame(self)
        toolbar.setObjectName("WorkbenchPaneToolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(tok.spacing.control_gap)

        self._new_btn = QPushButton("New Profile", toolbar)
        self._new_btn.setObjectName("NewCompensationButton")
        self._new_btn.setAccessibleName("New compensation")
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._new_btn.setEnabled(False)
        self._new_btn.clicked.connect(self._on_new_profile)
        tb_layout.addWidget(self._new_btn)

        self._edit_btn = QPushButton("Edit Profile", toolbar)
        self._edit_btn.setObjectName("EditCompensationButton")
        self._edit_btn.setAccessibleName("Edit selected compensation")
        self._edit_btn.setProperty("variant", "secondary")
        self._edit_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit_profile)
        tb_layout.addWidget(self._edit_btn)

        tb_layout.addStretch(1)

        self._count_label = QLabel("", toolbar)
        self._count_label.setObjectName("WorkbenchPaneCountLabel")
        tb_layout.addWidget(self._count_label)

        layout.addWidget(toolbar)

        # Table
        self._table = DataTable(
            columns=_COLUMNS,
            parent=self,
        )
        self._table.set_model(self._model)
        self._table.setObjectName("CompensationProfileTable")
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_edit_profile)
        layout.addWidget(self._table, 1)

        # ── Keyboard shortcuts (P13.S2) ────────────────────────────────────
        _sc = shortcut_map("payroll.compensation")
        if "new_comp" in _sc:
            install_shortcut(self, _sc["new_comp"], self._on_new_profile)
        if "edit_comp" in _sc:
            install_shortcut(self, _sc["edit_comp"], self._on_edit_profile)        # Density toggle (P13.S4)
        _tsc = shortcut_map("table")
        if "toggle_density" in _tsc:
            install_shortcut(
                self, _tsc["toggle_density"],
                lambda: self._table.set_density(
                    "comfortable" if self._table.density() == "dense" else "dense"
                ),
            )        # Tab order
        self.setTabOrder(self._new_btn, self._edit_btn)

    # ── Active company helpers ─────────────────────────────────────────

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            company = ctx.get_active_company()
            return getattr(company, "id", None) if company else None
        except Exception:
            return None

    # ── Public ────────────────────────────────────────────────────────

    def refresh(self) -> None:
        company_id = self._active_company_id()
        has_company = company_id is not None
        self._new_btn.setEnabled(has_company)
        self._edit_btn.setEnabled(False)

        if not has_company:
            self._model.load([])
            self._count_label.setText("")
            return

        svc = getattr(self._sr, "compensation_profile_service", None)
        if svc is None:
            logger.warning("compensation_profile_service not available")
            self._model.load([])
            self._count_label.setText("")
            return

        try:
            profiles = svc.list_profiles(company_id)
        except Exception:
            logger.warning("compensation_profile_service.list_profiles failed", exc_info=True)
            profiles = []

        self._model.load(profiles)
        n = len(profiles)
        self._count_label.setText(f"{n} profile{'s' if n != 1 else ''}")

    # ── Slot handlers ─────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        has_sel = bool(self._table.selected_rows())
        self._edit_btn.setEnabled(has_sel)

    def _on_new_profile(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            return
        self._open_profile_dialog(company_id, profile_id=None)

    def _on_edit_profile(self) -> None:
        rows = self._table.selected_rows()
        if not rows:
            return
        dto = self._model.row_dto(rows[0])
        if dto is None:
            return
        company_id = self._active_company_id()
        if company_id is None:
            return
        self._open_profile_dialog(company_id, profile_id=dto.id)

    def _open_profile_dialog(self, company_id: int, profile_id: int | None) -> None:
        """Open the compensation profile dialog if available, then refresh."""
        try:
            from seeker_accounting.modules.payroll.ui.dialogs.compensation_profile_dialog import (
                CompensationProfileDialog,
            )
            dlg = CompensationProfileDialog(
                self._sr,
                company_id=company_id,
                profile_id=profile_id,
                parent=self,
            )
            dlg.exec()
            self.refresh()
        except ImportError:
            # Dialog not available; open the employee hub instead when editing.
            if profile_id is not None:
                dto = self._model.row_dto(
                    self._table.selected_rows()[0] if self._table.selected_rows() else -1
                )
                if dto is not None:
                    self._open_employee_hub(company_id, dto.employee_id)
        except Exception:
            logger.warning("CompensationProfileDialog failed", exc_info=True)
            self.refresh()

    def _open_employee_hub(self, company_id: int, employee_id: int) -> None:
        try:
            from seeker_accounting.modules.payroll.ui.employee_hub_window import (
                EmployeeHubWindow,
            )
            manager = getattr(self._sr, "child_window_manager", None)

            def _factory() -> EmployeeHubWindow:
                return EmployeeHubWindow(
                    self._sr,
                    company_id=company_id,
                    employee_id=employee_id,
                )

            if manager is not None:
                manager.open_document(EmployeeHubWindow.DOC_TYPE, employee_id, _factory)
            else:
                _factory().show()
        except Exception:
            logger.warning(
                "EmployeeHubWindow unavailable for employee %s", employee_id, exc_info=True
            )
