from __future__ import annotations

import logging

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.contracts_projects.dto.project_dto import (
    CreateProjectCommand,
    ProjectDetailDTO,
    UpdateProjectCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class ProjectFormDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        project_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._project_id = project_id
        self._saved_project: ProjectDetailDTO | None = None

        title = "New Project" if project_id is None else "Edit Project"
        super().__init__(title, parent, help_key="dialog.project_form")
        self.setObjectName("ProjectFormDialog")
        self.resize(780, 620)

        intro_label = QLabel(
            "Define project master data scoped to the active company. "
            "Optionally link to an existing contract.",
            self,
        )
        intro_label.setObjectName("PageSummary")
        intro_label.setWordWrap(True)
        self.body_layout.addWidget(intro_label)
        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_identity_section())
        self.body_layout.addWidget(self._build_details_section())
        self.body_layout.addWidget(self._build_notes_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Create Project" if project_id is None else "Save Changes")
            save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._load_reference_data()
        if self._project_id is not None:
            self._load_project()
        else:
            self._suggest_code()

    @property
    def saved_project(self) -> ProjectDetailDTO | None:
        return self._saved_project

    @classmethod
    def create_project(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> ProjectDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_project
        return None

    @classmethod
    def edit_project(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        project_id: int,
        parent: QWidget | None = None,
    ) -> ProjectDetailDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            project_id=project_id,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_project
        return None

    # ------------------------------------------------------------------
    # Form sections
    # ------------------------------------------------------------------

    def _build_identity_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Identity", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._project_code_edit = QLineEdit(card)
        self._project_code_edit.setPlaceholderText("PRJ-001")
        grid.addWidget(create_field_block("Project Code", self._project_code_edit), 0, 0)

        self._project_name_edit = QLineEdit(card)
        self._project_name_edit.setPlaceholderText("Project name")
        grid.addWidget(create_field_block("Project Name", self._project_name_edit), 0, 1)

        self._contract_combo = SearchableComboBox(card)
        self._contract_combo.setMaxVisibleItems(18)
        grid.addWidget(create_field_block("Contract", self._contract_combo, "Optional contract linkage."), 1, 0)

        self._customer_combo = SearchableComboBox(card)
        self._customer_combo.setMaxVisibleItems(18)
        grid.addWidget(create_field_block("Customer", self._customer_combo, "Optional if not linked to a contract."), 1, 1)

        self._project_type_combo = QComboBox(card)
        self._project_type_combo.addItem("External", "external")
        self._project_type_combo.addItem("Internal", "internal")
        self._project_type_combo.addItem("Capital", "capital")
        self._project_type_combo.addItem("Administrative", "administrative")
        self._project_type_combo.addItem("Other", "other")
        grid.addWidget(create_field_block("Project Type", self._project_type_combo), 2, 0)

        self._budget_control_combo = QComboBox(card)
        self._budget_control_combo.addItem("No budget control", "")
        self._budget_control_combo.addItem("None", "none")
        self._budget_control_combo.addItem("Warn", "warn")
        self._budget_control_combo.addItem("Hard Stop", "hard_stop")
        grid.addWidget(create_field_block("Budget Control Mode", self._budget_control_combo), 2, 1)

        layout.addLayout(grid)
        return card

    def _build_details_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Dates and Currency", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._currency_combo = SearchableComboBox(card)
        self._currency_combo.setMaxVisibleItems(18)
        grid.addWidget(create_field_block("Currency", self._currency_combo, "Optional project currency."), 0, 0)

        self._start_date_edit = QDateEdit(card)
        self._start_date_edit.setCalendarPopup(True)
        self._start_date_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(create_field_block("Start Date", self._start_date_edit), 1, 0)

        self._planned_end_date_edit = QDateEdit(card)
        self._planned_end_date_edit.setCalendarPopup(True)
        self._planned_end_date_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(create_field_block("Planned End Date", self._planned_end_date_edit), 1, 1)

        layout.addLayout(grid)
        return card

    def _build_notes_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Notes", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setPlaceholderText("Optional project notes")
        self._notes_edit.setFixedHeight(92)
        layout.addWidget(self._notes_edit)

        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("project", self._company_id)
            self._project_code_edit.setText(code)
        except Exception:
            pass

    def _load_reference_data(self) -> None:
        # Contracts
        try:
            contracts = self._service_registry.contract_service.list_contracts(self._company_id)
            self._contract_combo.set_items(
                [(f"{c.contract_number} — {c.contract_title}", c.id) for c in contracts],
                placeholder="-- No contract --",
                placeholder_value=0,
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        # Customers
        try:
            customers = self._service_registry.customer_service.list_customers(
                self._company_id, active_only=True
            )
            self._customer_combo.set_items(
                [(f"{c.customer_code} — {c.display_name}", c.id) for c in customers],
                placeholder="-- No customer --",
                placeholder_value=0,
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        # Currencies
        try:
            currencies = self._service_registry.reference_data_service.list_active_currencies()
            self._currency_combo.set_items(
                [(cur.code, cur.code) for cur in currencies],
                placeholder="-- No currency --",
                placeholder_value="",
            )
            ctx = self._service_registry.active_company_context
            if ctx.base_currency_code:
                self._currency_combo.set_current_value(ctx.base_currency_code)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_project(self) -> None:
        try:
            project = self._service_registry.project_service.get_project_detail(
                self._project_id or 0
            )
        except NotFoundError as exc:
            show_error(self, "Project Not Found", str(exc))
            self.reject()
            return

        self._project_code_edit.setText(project.project_code)
        self._project_name_edit.setText(project.project_name)
        self._contract_combo.set_current_value(project.contract_id or 0)
        self._customer_combo.set_current_value(project.customer_id or 0)
        self._select_combo_data(self._project_type_combo, project.project_type_code)
        self._select_combo_data(
            self._budget_control_combo, project.budget_control_mode_code or ""
        )
        self._currency_combo.set_current_value(project.currency_code or "")
        if project.start_date:
            self._start_date_edit.setDate(project.start_date)
        if project.planned_end_date:
            self._planned_end_date_edit.setDate(project.planned_end_date)
        self._notes_edit.setPlainText(project.notes or "")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _select_combo_data(self, combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _selected_int_or_none(self, combo: SearchableComboBox) -> int | None:
        value = combo.current_value()
        return value if isinstance(value, int) and value > 0 else None

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._set_error(None)

        project_code = self._project_code_edit.text().strip()
        project_name = self._project_name_edit.text().strip()
        if not project_code:
            self._set_error("Project code is required.")
            self._project_code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not project_name:
            self._set_error("Project name is required.")
            self._project_name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        contract_id = self._selected_int_or_none(self._contract_combo)
        customer_id = self._selected_int_or_none(self._customer_combo)
        currency_code = self._currency_combo.current_value() or None
        budget_control = self._budget_control_combo.currentData() or None
        start_date = self._start_date_edit.date().toPython()
        planned_end_date = self._planned_end_date_edit.date().toPython()

        try:
            if self._project_id is None:
                self._saved_project = self._service_registry.project_service.create_project(
                    CreateProjectCommand(
                        company_id=self._company_id,
                        project_code=project_code,
                        project_name=project_name,
                        contract_id=contract_id,
                        customer_id=customer_id,
                        project_type_code=self._project_type_combo.currentData() or "external",
                        currency_code=currency_code,
                        start_date=start_date,
                        planned_end_date=planned_end_date,
                        budget_control_mode_code=budget_control,
                        notes=self._notes_edit.toPlainText().strip() or None,
                    )
                )
            else:
                self._saved_project = self._service_registry.project_service.update_project(
                    self._project_id,
                    UpdateProjectCommand(
                        project_name=project_name,
                        contract_id=contract_id,
                        customer_id=customer_id,
                        project_type_code=self._project_type_combo.currentData() or "external",
                        currency_code=currency_code,
                        start_date=start_date,
                        planned_end_date=planned_end_date,
                        budget_control_mode_code=budget_control,
                        notes=self._notes_edit.toPlainText().strip() or None,
                    ),
                )
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Project Not Found", str(exc))
            return

        self.accept()
