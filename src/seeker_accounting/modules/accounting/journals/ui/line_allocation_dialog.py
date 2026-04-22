from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.contracts_projects.dto.contract_dto import ContractListItemDTO
from seeker_accounting.modules.contracts_projects.dto.project_dto import ProjectListItemDTO
from seeker_accounting.modules.contracts_projects.dto.project_cost_code_dto import ProjectCostCodeListItemDTO
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox


class LineAllocationDialog(BaseDialog):
    """Small modal dialog for allocating a journal line to Contract / Project / Job / Cost Code."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        current_values: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._result: dict | None = None

        super().__init__("Allocate to Contract / Project", parent)
        self.setObjectName("LineAllocationDialog")
        self.resize(420, 320)

        self._contract_options: list[ContractListItemDTO] = []
        self._project_options: list[ProjectListItemDTO] = []
        self._cost_code_options: list[ProjectCostCodeListItemDTO] = []

        self._load_reference_data()

        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 4, 8, 4)
        card_layout.setSpacing(0)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        # Contract
        self._contract_combo = SearchableComboBox(card)
        self._contract_combo.addItem("", None)
        for c in self._contract_options:
            self._contract_combo.addItem(f"{c.contract_number}  {c.contract_title}", c.id)
        grid.addWidget(create_field_block("Contract", self._contract_combo), 0, 0)

        # Project
        self._project_combo = SearchableComboBox(card)
        self._project_combo.addItem("", None)
        for p in self._project_options:
            self._project_combo.addItem(f"{p.project_code}  {p.project_name}", p.id)
        self._project_combo.currentIndexChanged.connect(self._on_project_changed)
        grid.addWidget(create_field_block("Project", self._project_combo), 1, 0)

        # Job (cascaded from project)
        self._job_combo = SearchableComboBox(card)
        self._job_combo.addItem("", None)
        grid.addWidget(create_field_block("Job", self._job_combo), 2, 0)

        # Cost Code
        self._cost_code_combo = SearchableComboBox(card)
        self._cost_code_combo.addItem("", None)
        for cc in self._cost_code_options:
            label = f"{cc.code}  {cc.name}"
            if not cc.is_active:
                label = f"{label}  (inactive)"
            self._cost_code_combo.addItem(label, cc.id)
        grid.addWidget(create_field_block("Cost Code", self._cost_code_combo), 3, 0)

        card_layout.addLayout(grid)
        self.body_layout.addWidget(card)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setProperty("variant", "primary")
        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")
        self.button_box.accepted.connect(self._handle_ok)

        # Restore current values
        if current_values:
            self._set_combo_value(self._contract_combo, current_values.get("contract_id"))
            self._set_combo_value(self._project_combo, current_values.get("project_id"))
            self._on_project_changed()
            self._set_combo_value(self._job_combo, current_values.get("project_job_id"))
            self._set_combo_value(self._cost_code_combo, current_values.get("project_cost_code_id"))

    @property
    def result(self) -> dict | None:
        return self._result

    def _load_reference_data(self) -> None:
        try:
            self._contract_options = self._service_registry.contract_service.list_contracts(self._company_id)
        except Exception:
            self._contract_options = []
        try:
            self._project_options = self._service_registry.project_service.list_projects(self._company_id)
        except Exception:
            self._project_options = []
        try:
            self._cost_code_options = self._service_registry.project_cost_code_service.list_cost_codes(
                self._company_id, active_only=False,
            )
        except Exception:
            self._cost_code_options = []

    def _on_project_changed(self) -> None:
        project_id = self._project_combo.currentData()
        self._job_combo.clear()
        self._job_combo.addItem("", None)
        if isinstance(project_id, int):
            try:
                jobs = self._service_registry.project_structure_service.list_jobs(project_id)
            except Exception:
                jobs = []
            for j in jobs:
                self._job_combo.addItem(f"{j.job_code}  {j.job_name}", j.id)

    def _set_combo_value(self, combo: SearchableComboBox, value: int | None) -> None:
        if value is None:
            combo.setCurrentIndex(0)
            return
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _handle_ok(self) -> None:
        self._result = {
            "contract_id": self._contract_combo.currentData(),
            "project_id": self._project_combo.currentData(),
            "project_job_id": self._job_combo.currentData(),
            "project_cost_code_id": self._cost_code_combo.currentData(),
        }
        self.accept()

    @classmethod
    def get_allocation(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        current_values: dict | None = None,
        parent: QWidget | None = None,
    ) -> dict | None:
        dialog = cls(service_registry, company_id, current_values=current_values, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result
        return None
