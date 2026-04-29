"""Step 2 — Map account roles to chart of accounts entries."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.coa_customization import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class RoleMappingStep(WizardStep):
    key = "role_mapping"
    title = "Account roles"
    subtitle = "Map system roles (AR control, VAT, retained earnings, etc.) to accounts."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._summary: QLabel | None = None
        self._loaded_once = False
        self._role_codes: list[str] = []
        self._role_labels: dict[str, str] = {}

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._summary = QLabel(
            "Each role maps to a single account. Leaving a role unmapped is allowed "
            "but blocks workflows that need it.",
            root,
        )
        self._summary.setWordWrap(True)
        outer.addWidget(self._summary)

        self._table = QTableWidget(0, 3, root)
        self._table.setHorizontalHeaderLabels(["Role", "Description", "Account"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self._table, 1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if not self._loaded_once:
            self._populate_table(context, state)
            self._loaded_once = True
        else:
            # Re-apply selections from state in case user edited them and came back.
            self._reapply_selections_from_state(state)

    def _populate_table(self, context: WizardContext, state: WizardState) -> None:
        sr = context.service_registry
        company_id = context.require_company_id()
        try:
            role_options = sr.account_role_mapping_service.list_role_options()
        except Exception:
            role_options = []
        try:
            current_mappings = sr.account_role_mapping_service.list_role_mappings(company_id)
        except Exception:
            current_mappings = []
        try:
            account_options = sr.chart_of_accounts_service.list_account_lookup_options(
                company_id, active_only=True
            )
        except Exception:
            account_options = []

        current_by_role: dict[str, int | None] = {
            m.role_code: m.account_id for m in current_mappings
        }

        # Stash a snapshot so confirm step can compute diff
        state[K.KEY_ROLE_CURRENT] = {
            code: int(aid) for code, aid in current_by_role.items() if isinstance(aid, int)
        }
        selections = dict(state.get(K.KEY_ROLE_SELECTIONS) or {})

        self._role_codes = []
        self._role_labels = {}
        if self._table is None:
            return
        self._table.setRowCount(0)

        for option in role_options:
            self._role_codes.append(option.role_code)
            self._role_labels[option.role_code] = option.label
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(option.label))
            self._table.setItem(row, 1, QTableWidgetItem(getattr(option, "description", "") or ""))

            combo = QComboBox()
            combo.addItem("(unmapped)", None)
            for a in account_options:
                if not a.is_active or not a.allow_manual_posting:
                    continue
                combo.addItem(f"{a.account_code} — {a.account_name}", int(a.id))

            # Initial value: state selection wins, else current mapping
            if option.role_code in selections:
                target = selections[option.role_code]
            else:
                target = current_by_role.get(option.role_code)
            if isinstance(target, int):
                idx = combo.findData(target)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._table.setCellWidget(row, 2, combo)

    def _reapply_selections_from_state(self, state: WizardState) -> None:
        if self._table is None:
            return
        selections = dict(state.get(K.KEY_ROLE_SELECTIONS) or {})
        for row, role_code in enumerate(self._role_codes):
            combo = self._table.cellWidget(row, 2)
            if not isinstance(combo, QComboBox):
                continue
            value = selections.get(role_code)
            if isinstance(value, int):
                idx = combo.findData(value)
                combo.setCurrentIndex(idx if idx >= 0 else 0)

    def write_back(self, state: WizardState) -> None:
        if self._table is None:
            return
        selections: dict[str, int | None] = {}
        for row, role_code in enumerate(self._role_codes):
            combo = self._table.cellWidget(row, 2)
            if not isinstance(combo, QComboBox):
                continue
            data = combo.currentData()
            selections[role_code] = int(data) if isinstance(data, int) else None
        state[K.KEY_ROLE_SELECTIONS] = selections

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        sels = state.get(K.KEY_ROLE_SELECTIONS) or {}
        mapped = sum(1 for v in sels.values() if isinstance(v, int))
        return f"{mapped} role(s) mapped." if mapped else "No role mappings selected."
