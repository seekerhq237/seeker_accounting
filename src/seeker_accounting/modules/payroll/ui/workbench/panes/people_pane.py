"""Payroll workbench People pane (Phase 2, slice S3 — P4.S2 integration).

Native employee directory with master list and primary lifecycle actions.

Layout
------
* Action bar — "Hire Employee" (primary), "Edit" (selection-gated),
  "Show inactive" toggle on the far right.
* DataTable — employee list with search, count chip, density toggle.

Integration
-----------
* Hire → opens :class:`EmployeeOnboardingWizardDialog` (P4.S2 Hire-to-Pay BP).
  On a successful completion the pane refreshes its list automatically.
* Edit / double-click → opens :class:`EmployeeHubWindow` via the
  ``child_window_manager`` (legacy hub until P4.S7).

Graceful degradation
--------------------
* No active company → action bar disabled, empty table.
* ``employee_service`` not available → empty table, warn log.
* ``child_window_manager`` missing → fallback to ``hub.show()``.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.employee_dto import EmployeeListItemDTO
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.keyboard_shortcuts import install_shortcut, shortcut_map
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)


# ── Table columns ─────────────────────────────────────────────────────────────

_COLUMNS: list[DataTableColumn] = [
    DataTableColumn(key="employee_number", title="Employee No.", width=110),
    DataTableColumn(key="display_name", title="Name", width=220),
    DataTableColumn(key="department_name", title="Department", width=150),
    DataTableColumn(key="position_name", title="Position", width=150),
    DataTableColumn(key="hire_date", title="Hire Date", width=100),
    DataTableColumn(key="status", title="Status", width=90),
]

# ── Source model ──────────────────────────────────────────────────────────────


class _EmployeeTableModel(QAbstractTableModel):
    """Flat read-only model backed by a list of EmployeeListItemDTO rows."""

    _HEADERS = ("Employee No.", "Name", "Department", "Position", "Hire Date", "Status")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[EmployeeListItemDTO] = []

    # -- Mutator --------------------------------------------------------------

    def load(self, rows: list[EmployeeListItemDTO]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    # -- QAbstractTableModel --------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._HEADERS)

    def data(  # type: ignore[override]
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        row = self._rows[index.row()]
        col = index.column()
        if col == 0:
            return row.employee_number or ""
        if col == 1:
            return row.display_name or ""
        if col == 2:
            return row.department_name or "—"
        if col == 3:
            return row.position_name or "—"
        if col == 4:
            return str(row.hire_date) if row.hire_date else "—"
        if col == 5:
            return "Active" if row.is_active else "Inactive"
        return None

    def headerData(  # type: ignore[override]
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._HEADERS)
        ):
            return self._HEADERS[section]
        return None

    # -- Helper ---------------------------------------------------------------

    def row_dto(self, source_row: int) -> EmployeeListItemDTO | None:
        """Return the DTO for a source-model row index, or None."""
        if 0 <= source_row < len(self._rows):
            return self._rows[source_row]
        return None


# ── Pane ──────────────────────────────────────────────────────────────────────


class PeoplePaneWidget(QFrame):
    """Native People pane for the Payroll Workbench.

    Hosts an employee list (DataTable) with a compact action bar above it.
    The primary entry point to the Hire-to-Pay business process lives here.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollWorkbenchPeoplePane")
        self._sr = service_registry
        self._show_inactive = False
        self._selected_source_rows: list[int] = []

        self._build_ui()
        self.refresh()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        spacing = DEFAULT_TOKENS.spacing

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Action bar.
        self._action_bar = QFrame(self)
        self._action_bar.setObjectName("PeoplePaneActionBar")
        bar_layout = QHBoxLayout(self._action_bar)
        bar_layout.setContentsMargins(
            spacing.dialog_padding,
            spacing.compact_gap,
            spacing.dialog_padding,
            spacing.compact_gap,
        )
        bar_layout.setSpacing(spacing.compact_gap)

        self._hire_btn = QPushButton("Hire Employee", self._action_bar)
        self._hire_btn.setObjectName("PeoplePaneHireBtn")
        self._hire_btn.setAccessibleName("Hire new employee")
        self._hire_btn.setProperty("variant", "primary")
        self._hire_btn.clicked.connect(self._on_hire)
        bar_layout.addWidget(self._hire_btn)

        self._edit_btn = QPushButton("Edit", self._action_bar)
        self._edit_btn.setObjectName("PeoplePaneEditBtn")
        self._edit_btn.setAccessibleName("Edit selected employee")
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        bar_layout.addWidget(self._edit_btn)

        self._terminate_btn = QPushButton("Terminate", self._action_bar)
        self._terminate_btn.setObjectName("PeoplePaneTerminateBtn")
        self._terminate_btn.setEnabled(False)
        self._terminate_btn.clicked.connect(self._on_terminate)
        bar_layout.addWidget(self._terminate_btn)

        self._rehire_btn = QPushButton("Rehire", self._action_bar)
        self._rehire_btn.setObjectName("PeoplePaneRehireBtn")
        self._rehire_btn.setEnabled(False)
        self._rehire_btn.clicked.connect(self._on_rehire)
        bar_layout.addWidget(self._rehire_btn)

        bar_layout.addStretch(1)

        self._inactive_btn = QPushButton("Show inactive", self._action_bar)
        self._inactive_btn.setObjectName("PeoplePaneInactiveToggle")
        self._inactive_btn.setCheckable(True)
        self._inactive_btn.setChecked(False)
        self._inactive_btn.toggled.connect(self._on_inactive_toggled)
        bar_layout.addWidget(self._inactive_btn)

        outer.addWidget(self._action_bar)

        # Employee table.
        self._model = _EmployeeTableModel(self)
        self._table = DataTable(
            columns=_COLUMNS,
            title="",
            selection_mode="single",
            density="comfortable",
            show_count=True,
            empty_state_text=(
                'No employees found. Click "Hire Employee" to add the first employee.'
            ),
            parent=self,
        )
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table.set_model(self._model)
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        outer.addWidget(self._table, 1)

        # ── Keyboard shortcuts (P13.S2) ────────────────────────────────
        _sc = shortcut_map("payroll.people")
        if "hire" in _sc:
            install_shortcut(self, _sc["hire"], self._on_hire)
        if "edit" in _sc:
            install_shortcut(self, _sc["edit"], self._on_edit)
        # Density toggle (P13.S4)
        _tsc = shortcut_map("table")
        if "toggle_density" in _tsc:
            install_shortcut(
                self, _tsc["toggle_density"],
                lambda: self._table.set_density(
                    "comfortable" if self._table.density() == "dense" else "dense"
                ),
            )
        # Tab order
        self.setTabOrder(self._hire_btn, self._edit_btn)
        self.setTabOrder(self._edit_btn, self._rehire_btn)
        self.setTabOrder(self._rehire_btn, self._inactive_btn)

    # ── Public API ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Re-load the employee list from the service."""
        company_id = self._active_company_id()
        has_company = company_id is not None
        self._hire_btn.setEnabled(has_company)

        if not has_company:
            self._model.load([])
            self._update_selection_state([])
            return

        svc = getattr(self._sr, "employee_service", None)
        if svc is None:
            self._model.load([])
            return

        try:
            rows = svc.list_employees(
                company_id,
                active_only=not self._show_inactive,
            )
        except Exception:
            logger.warning("list_employees failed", exc_info=True)
            rows = []

        self._model.load(rows)
        self._update_selection_state([])

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            company = ctx.get_active_company()
        except Exception:
            return None
        return getattr(company, "id", None) if company else None

    def _actor_user_id(self) -> int | None:
        user = getattr(self._sr, "current_user", None)
        if user is None:
            return None
        return getattr(user, "id", None)

    def _update_selection_state(self, source_rows: list[int]) -> None:
        self._selected_source_rows = source_rows
        has_sel = bool(source_rows)
        dto = self._model.row_dto(source_rows[0]) if has_sel else None
        self._edit_btn.setEnabled(has_sel)
        # Terminate: only for active employees
        self._terminate_btn.setEnabled(has_sel and dto is not None and dto.is_active)
        # Rehire: only for inactive employees
        self._rehire_btn.setEnabled(has_sel and dto is not None and not dto.is_active)

    def _selected_dto(self) -> EmployeeListItemDTO | None:
        if not self._selected_source_rows:
            return None
        return self._model.row_dto(self._selected_source_rows[0])

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_selection_changed(self, source_rows: list[int]) -> None:
        self._update_selection_state(source_rows)

    def _on_row_activated(self, source_row: int) -> None:
        dto = self._model.row_dto(source_row)
        if dto is not None:
            self._open_employee_hub(dto.id)

    def _on_hire(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            return
        # Guard: EmployeeOnboardingService must be wired.
        svc = getattr(self._sr, "employee_onboarding_service", None)
        if svc is None:
            logger.warning("employee_onboarding_service not wired; cannot open hire wizard")
            return

        from seeker_accounting.modules.payroll.ui.bp.employee_onboarding_wizard import (
            EmployeeOnboardingWizardDialog,
        )

        dlg = EmployeeOnboardingWizardDialog(
            service_registry=self._sr,
            company_id=company_id,
            actor_user_id=self._actor_user_id(),
            draft_id=None,
            parent=self,
        )
        if dlg.exec() and dlg.created_employee_id is not None:
            self.refresh()

    def _on_edit(self) -> None:
        dto = self._selected_dto()
        if dto is None:
            return
        self._open_employee_hub(dto.id)

    def _on_terminate(self) -> None:
        dto = self._selected_dto()
        company_id = self._active_company_id()
        if dto is None or company_id is None:
            return
        from seeker_accounting.modules.payroll.ui.bp.employee_termination_wizard import (
            TerminateEmployeeWizardDialog,
        )

        if TerminateEmployeeWizardDialog.run(self._sr, company_id, dto, parent=self):
            self.refresh()

    def _on_rehire(self) -> None:
        dto = self._selected_dto()
        company_id = self._active_company_id()
        if dto is None or company_id is None:
            return
        from seeker_accounting.modules.payroll.ui.bp.employee_rehire_wizard import (
            RehireEmployeeWizardDialog,
        )

        if RehireEmployeeWizardDialog.run(self._sr, company_id, dto, parent=self):
            self.refresh()

    def _on_inactive_toggled(self, checked: bool) -> None:
        self._show_inactive = checked
        self.refresh()

    def _open_employee_hub(self, employee_id: int) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            return
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
                win = _factory()
                win.show()
        except Exception:
            logger.warning(
                "EmployeeHubWindow unavailable for employee %s",
                employee_id,
                exc_info=True,
            )
