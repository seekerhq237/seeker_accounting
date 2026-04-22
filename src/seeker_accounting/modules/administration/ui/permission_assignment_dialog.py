"""Permission assignment dialog with cascading module-grouped checkboxes."""
from __future__ import annotations

import logging
from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from seeker_accounting.modules.administration.dto.role_commands import AssignRolePermissionsCommand
from seeker_accounting.modules.administration.dto.user_dto import PermissionDTO, RoleDTO
from seeker_accounting.modules.administration.services.role_service import RoleService
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog

logger = logging.getLogger(__name__)

# Display-friendly module names
_MODULE_DISPLAY_NAMES: dict[str, str] = {
    "companies": "Companies",
    "chart": "Chart of Accounts",
    "fiscal": "Fiscal Periods",
    "journals": "Journals",
    "reference": "Reference Data",
    "customers": "Customers",
    "suppliers": "Suppliers",
    "sales": "Sales",
    "purchases": "Purchases",
    "treasury": "Treasury",
    "inventory": "Inventory",
    "assets": "Fixed Assets",
    "contracts": "Contracts & Projects",
    "job_costing": "Job Costing",
    "budgets": "Budgets",
    "reporting": "Reports",
    "management": "Management Reporting",
    "audit": "Audit",
    "administration": "Administration",
    "payroll": "Payroll",
}


class PermissionAssignmentDialog(BaseDialog):
    """Tree-based dialog for assigning permissions to a role.

    Permissions are grouped by ``module_code``.  Module-level items use
    tri-state checkboxes: checking a module selects all its children,
    unchecking clears all.
    """

    _COL_NAME = 0
    _COL_CODE = 1

    def __init__(
        self,
        role_service: RoleService,
        role_dto: RoleDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Permissions — {role_dto.name}", parent, help_key="dialog.permission_assignment")
        self.setObjectName("PermissionAssignmentDialog")
        self.resize(408, 448)

        self._role_service = role_service
        self._role_dto = role_dto
        self._changed = False

        # ── info row ──
        info = QLabel(
            f"Assign permissions to <b>{role_dto.name}</b> ({role_dto.code})",
            self,
        )
        info.setWordWrap(True)
        self.body_layout.addWidget(info)

        # ── select all / clear all ──
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 0, 0, 0)
        select_all_btn = QPushButton("Select All", self)
        select_all_btn.setProperty("variant", "ghost")
        select_all_btn.clicked.connect(self._select_all)
        btn_bar.addWidget(select_all_btn)

        clear_all_btn = QPushButton("Clear All", self)
        clear_all_btn.setProperty("variant", "ghost")
        clear_all_btn.clicked.connect(self._clear_all)
        btn_bar.addWidget(clear_all_btn)
        btn_bar.addStretch(1)
        self.body_layout.addLayout(btn_bar)

        # ── tree ──
        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabels(["Permission"])
        self._tree.header().setStretchLastSection(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemChanged.connect(self._on_item_changed)
        self.body_layout.addWidget(self._tree, 1)

        # ── error label ──
        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        # ── buttons ──
        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        assign_btn = QPushButton("Assign", self)
        assign_btn.setProperty("variant", "primary")
        assign_btn.setDefault(True)
        assign_btn.clicked.connect(self._handle_assign)
        self.button_box.addButton(assign_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setProperty("variant", "secondary")
        cancel_btn.clicked.connect(self.reject)
        self.button_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

        # maps
        self._module_items: dict[str, QTreeWidgetItem] = {}
        self._perm_items: dict[int, QTreeWidgetItem] = {}

        self._load_data()

    @property
    def changed(self) -> bool:
        return self._changed

    # ── Class-level convenience ──────────────────────────────────────

    @classmethod
    def manage(
        cls,
        role_service: RoleService,
        role_dto: RoleDTO,
        parent: QWidget | None = None,
    ) -> bool:
        """Open the dialog.  Returns True if permissions were saved."""
        dlg = cls(role_service=role_service, role_dto=role_dto, parent=parent)
        dlg.exec()
        return dlg.changed

    # ── Data loading ─────────────────────────────────────────────────

    def _load_data(self) -> None:
        try:
            all_perms = self._role_service.list_all_permissions()
            role_detail = self._role_service.get_role(self._role_dto.id)
            assigned_ids = {p.id for p in role_detail.permissions}
        except Exception:
            logger.exception("Failed to load permissions for role %s.", self._role_dto.code)
            self._show_error("Could not load permissions. Please try again.")
            return

        grouped: dict[str, list[PermissionDTO]] = defaultdict(list)
        for p in all_perms:
            grouped[p.module_code].append(p)

        self._tree.blockSignals(True)
        self._tree.clear()
        self._module_items.clear()
        self._perm_items.clear()

        for module_code in sorted(grouped.keys()):
            perms = grouped[module_code]
            display = _MODULE_DISPLAY_NAMES.get(module_code, module_code.replace("_", " ").title())

            module_item = QTreeWidgetItem(self._tree)
            module_item.setText(self._COL_NAME, display)
            module_item.setFlags(
                module_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            module_item.setCheckState(self._COL_NAME, Qt.CheckState.Unchecked)
            self._module_items[module_code] = module_item

            for perm in perms:
                child = QTreeWidgetItem(module_item)
                child.setText(self._COL_NAME, perm.name)
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                state = Qt.CheckState.Checked if perm.id in assigned_ids else Qt.CheckState.Unchecked
                child.setCheckState(self._COL_NAME, state)
                child.setData(self._COL_NAME, Qt.ItemDataRole.UserRole, perm.id)
                self._perm_items[perm.id] = child

        self._tree.blockSignals(False)
        self._tree.expandAll()

    # ── Interaction ──────────────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        # Qt.ItemFlag.ItemIsAutoTristate handles module <-> child propagation
        pass

    def _select_all(self) -> None:
        self._tree.blockSignals(True)
        for module_item in self._module_items.values():
            module_item.setCheckState(self._COL_NAME, Qt.CheckState.Checked)
        self._tree.blockSignals(False)

    def _clear_all(self) -> None:
        self._tree.blockSignals(True)
        for module_item in self._module_items.values():
            module_item.setCheckState(self._COL_NAME, Qt.CheckState.Unchecked)
        self._tree.blockSignals(False)

    def _handle_assign(self) -> None:
        self._error_label.hide()

        selected_ids: list[int] = []
        for perm_id, item in self._perm_items.items():
            if item.checkState(self._COL_NAME) == Qt.CheckState.Checked:
                selected_ids.append(perm_id)

        try:
            self._role_service.assign_permissions(
                AssignRolePermissionsCommand(
                    role_id=self._role_dto.id,
                    permission_ids=tuple(selected_ids),
                )
            )
        except (ValidationError, NotFoundError) as exc:
            self._show_error(str(exc))
            return
        except Exception:
            logger.exception("Unexpected error assigning permissions.")
            self._show_error("An unexpected error occurred. Please try again.")
            return

        self._changed = True
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
