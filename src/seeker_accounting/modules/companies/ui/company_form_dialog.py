from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand, UpdateCompanyCommand
from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO, ReferenceOptionDTO
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox


class CompanyFormDialog(BaseDialog):
    """Single-page create and edit dialog for companies."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int | None = None,
        create_company_handler: Callable[[CreateCompanyCommand], CompanyDetailDTO] | None = None,
        get_company_handler: Callable[[int], CompanyDetailDTO] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._saved_company: CompanyDetailDTO | None = None
        self._loaded_company: CompanyDetailDTO | None = None
        self._is_create = company_id is None
        self._create_company_handler = create_company_handler or self._service_registry.company_service.create_company
        self._get_company_handler = get_company_handler or self._service_registry.company_service.get_company

        title = "New Organisation" if self._is_create else "Edit Organisation"
        super().__init__(title, parent, help_key="dialog.company_form")
        self.setObjectName("CompanyFormDialog")

        self._countries: list[ReferenceOptionDTO] = []
        self._currencies: list[ReferenceOptionDTO] = []
        self._selected_logo_file_path: str | None = None
        self._existing_logo_storage_path: str | None = None
        self._existing_logo_original_filename: str | None = None
        self._remove_logo_requested = False

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        if self._is_create:
            self._build_create_mode()
            self.resize(580, 600)
        else:
            self._build_edit_mode()
            self.resize(580, 600)

        self._load_reference_options()
        if not self._is_create:
            self._load_company()
        self._sync_button_state()

    @property
    def saved_company(self) -> CompanyDetailDTO | None:
        return self._saved_company

    @classmethod
    def create_company(
        cls,
        service_registry: ServiceRegistry,
        create_company_handler: Callable[[CreateCompanyCommand], CompanyDetailDTO] | None = None,
        get_company_handler: Callable[[int], CompanyDetailDTO] | None = None,
        parent: QWidget | None = None,
    ) -> CompanyDetailDTO | None:
        dialog = cls(
            service_registry=service_registry,
            create_company_handler=create_company_handler,
            get_company_handler=get_company_handler,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_company
        return None

    @classmethod
    def edit_company(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> CompanyDetailDTO | None:
        dialog = cls(service_registry=service_registry, company_id=company_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_company
        return None

    # ---- Create mode (single-page) ----

    def _build_create_mode(self) -> None:
        self.body_layout.addWidget(self._build_logo_field(self))

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self._legal_name_edit = QLineEdit(self)
        self._legal_name_edit.setPlaceholderText("e.g. Seeker Cameroon Ltd")
        grid.addWidget(create_field_block("Legal Name", self._legal_name_edit), 0, 0)

        self._display_name_edit = QLineEdit(self)
        self._display_name_edit.setPlaceholderText("e.g. Seeker Cameroon")
        grid.addWidget(create_field_block("Display Name", self._display_name_edit), 0, 1)

        self._country_combo = SearchableComboBox(self)
        self._country_combo.setObjectName("CompanyCountryCombo")
        grid.addWidget(create_field_block("Country", self._country_combo), 1, 0)

        self._currency_combo = SearchableComboBox(self)
        self._currency_combo.setObjectName("CompanyCurrencyCombo")
        grid.addWidget(create_field_block("Base Currency", self._currency_combo), 1, 1)

        self._tax_identifier_edit = QLineEdit(self)
        self._tax_identifier_edit.setPlaceholderText("Tax ID / NIU")
        grid.addWidget(create_field_block("Tax Identifier (NIU)", self._tax_identifier_edit), 2, 0)

        self._phone_edit = QLineEdit(self)
        self._phone_edit.setPlaceholderText("+237 6XX XXX XXX")
        grid.addWidget(create_field_block("Telephone", self._phone_edit), 2, 1)

        self._email_edit = QLineEdit(self)
        self._email_edit.setPlaceholderText("info@company.cm")
        grid.addWidget(create_field_block("Email", self._email_edit), 3, 0)

        self._sector_edit = QLineEdit(self)
        self._sector_edit.setPlaceholderText("e.g. Manufacturing")
        grid.addWidget(create_field_block("Sector of Operation", self._sector_edit), 3, 1)

        self._city_edit = QLineEdit(self)
        self._city_edit.setPlaceholderText("Douala")
        grid.addWidget(create_field_block("City", self._city_edit), 4, 0)

        self._region_edit = QLineEdit(self)
        self._region_edit.setPlaceholderText("Littoral")
        grid.addWidget(create_field_block("Region", self._region_edit), 4, 1)

        self._cnps_employer_input = QLineEdit(self)
        self._cnps_employer_input.setPlaceholderText("CNPS employer registration number (optional)")
        grid.addWidget(create_field_block("CNPS Employer No.", self._cnps_employer_input), 5, 0)

        self.body_layout.addLayout(grid)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Cancel)
        self._create_button = QPushButton("Create Organisation", self)
        self._create_button.setProperty("variant", "primary")
        self._create_button.clicked.connect(self._handle_create_submit)
        self.button_box.addButton(self._create_button, QDialogButtonBox.ButtonRole.ActionRole)

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

    def _handle_create_submit(self) -> None:
        self._set_error(None)
        command = CreateCompanyCommand(
            legal_name=self._legal_name_edit.text(),
            display_name=self._display_name_edit.text(),
            tax_identifier=self._tax_identifier_edit.text() or None,
            cnps_employer_number=self._cnps_employer_input.text() or None,
            phone=self._phone_edit.text() or None,
            email=self._email_edit.text() or None,
            sector_of_operation=self._sector_edit.text() or None,
            city=self._city_edit.text() or None,
            region=self._region_edit.text() or None,
            country_code=self._selected_code(self._country_combo),
            base_currency_code=self._selected_code(self._currency_combo),
        )
        try:
            self._saved_company = self._create_company_handler(command)
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return

        logo_error = self._persist_logo_changes(self._saved_company.id)
        self._saved_company = self._get_company_handler(self._saved_company.id)
        if logo_error:
            show_error(
                self,
                "Logo Upload Failed",
                f"Organisation details were saved, but the logo could not be stored.\n\n{logo_error}",
            )
        self.accept()

    # ---- Edit mode (single-page) ----

    def _build_edit_mode(self) -> None:
        self.body_layout.addWidget(self._build_logo_field(self))

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self._legal_name_edit = QLineEdit(self)
        self._legal_name_edit.setPlaceholderText("Legal Name")
        grid.addWidget(create_field_block("Legal Name", self._legal_name_edit), 0, 0)

        self._display_name_edit = QLineEdit(self)
        self._display_name_edit.setPlaceholderText("Display Name")
        grid.addWidget(create_field_block("Display Name", self._display_name_edit), 0, 1)

        self._country_combo = SearchableComboBox(self)
        self._country_combo.setObjectName("CompanyCountryCombo")
        grid.addWidget(create_field_block("Country", self._country_combo), 1, 0)

        self._currency_combo = SearchableComboBox(self)
        self._currency_combo.setObjectName("CompanyCurrencyCombo")
        grid.addWidget(create_field_block("Base Currency", self._currency_combo), 1, 1)

        self._tax_identifier_edit = QLineEdit(self)
        self._tax_identifier_edit.setPlaceholderText("Tax ID / NIU")
        grid.addWidget(create_field_block("Tax Identifier (NIU)", self._tax_identifier_edit), 2, 0)

        self._phone_edit = QLineEdit(self)
        self._phone_edit.setPlaceholderText("+237 6XX XXX XXX")
        grid.addWidget(create_field_block("Telephone", self._phone_edit), 2, 1)

        self._email_edit = QLineEdit(self)
        self._email_edit.setPlaceholderText("info@company.cm")
        grid.addWidget(create_field_block("Email", self._email_edit), 3, 0)

        self._sector_edit = QLineEdit(self)
        self._sector_edit.setPlaceholderText("e.g. Manufacturing")
        grid.addWidget(create_field_block("Sector of Operation", self._sector_edit), 3, 1)

        self._city_edit = QLineEdit(self)
        self._city_edit.setPlaceholderText("Douala")
        grid.addWidget(create_field_block("City", self._city_edit), 4, 0)

        self._region_edit = QLineEdit(self)
        self._region_edit.setPlaceholderText("Littoral")
        grid.addWidget(create_field_block("Region", self._region_edit), 4, 1)

        self._cnps_employer_input = QLineEdit(self)
        self._cnps_employer_input.setPlaceholderText("CNPS employer registration number (optional)")
        grid.addWidget(create_field_block("CNPS Employer No.", self._cnps_employer_input), 5, 0)

        self.body_layout.addLayout(grid)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_edit_submit)

        self._save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if self._save_button is not None:
            self._save_button.setText("Save Changes")
            self._save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

    def _handle_edit_submit(self) -> None:
        self._set_error(None)
        if not self._legal_name_edit.text().strip():
            self._set_error("Legal name is required.")
            self._legal_name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not self._display_name_edit.text().strip():
            self._set_error("Display name is required.")
            self._display_name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not self._selected_code(self._country_combo):
            self._set_error("Country is required.")
            return
        if not self._selected_code(self._currency_combo):
            self._set_error("Base currency is required.")
            return

        existing = self._loaded_company
        if existing is None:
            self._set_error("Company details could not be loaded for editing.")
            return

        command = UpdateCompanyCommand(
            legal_name=self._legal_name_edit.text(),
            display_name=self._display_name_edit.text(),
            registration_number=existing.registration_number,
            tax_identifier=self._tax_identifier_edit.text() or None,
            cnps_employer_number=self._cnps_employer_input.text() or None,
            phone=self._phone_edit.text() or None,
            email=self._email_edit.text() or None,
            website=existing.website,
            sector_of_operation=self._sector_edit.text() or None,
            address_line_1=existing.address_line_1,
            address_line_2=existing.address_line_2,
            city=self._city_edit.text() or None,
            region=self._region_edit.text() or None,
            country_code=self._selected_code(self._country_combo),
            base_currency_code=self._selected_code(self._currency_combo),
        )
        try:
            self._saved_company = self._service_registry.company_service.update_company(self._company_id, command)
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Company Not Found", str(exc))
            return

        logo_error = self._persist_logo_changes(self._saved_company.id)
        self._saved_company = self._get_company_handler(self._saved_company.id)
        if logo_error:
            show_error(
                self,
                "Logo Update Failed",
                f"Organisation details were saved, but the logo could not be updated.\n\n{logo_error}",
            )
        self.accept()

    # ---- Shared helpers ----

    def _load_reference_options(self) -> None:
        try:
            self._countries = self._service_registry.company_service.list_available_countries()
            self._currencies = self._service_registry.company_service.list_available_currencies()
        except Exception as exc:
            self._countries = []
            self._currencies = []
            self._set_error(f"Reference data could not be loaded.\n\n{exc}")
            return

        self._country_combo.set_items(
            [(f"{o.code}  {o.name}", o.code) for o in self._countries],
            placeholder="Select country",
        )
        self._currency_combo.set_items(
            [(f"{o.code}  {o.name}", o.code) for o in self._currencies],
            placeholder="Select currency",
        )

        if not self._countries or not self._currencies:
            self._set_error(
                "Reference data is incomplete. Add active countries and currencies before creating or editing companies."
            )

    def _load_company(self) -> None:
        try:
            company = self._get_company_handler(self._company_id or 0)
        except NotFoundError as exc:
            show_error(self, "Company Not Found", str(exc))
            self.reject()
            return

        self._loaded_company = company
        self._existing_logo_storage_path = company.logo_storage_path
        self._existing_logo_original_filename = company.logo_original_filename
        self._legal_name_edit.setText(company.legal_name)
        self._display_name_edit.setText(company.display_name)
        self._tax_identifier_edit.setText(company.tax_identifier or "")
        self._cnps_employer_input.setText(company.cnps_employer_number or "")
        self._phone_edit.setText(company.phone or "")
        self._email_edit.setText(company.email or "")
        self._sector_edit.setText(company.sector_of_operation or "")
        self._city_edit.setText(company.city or "")
        self._region_edit.setText(company.region or "")
        self._country_combo.set_current_value(company.country_code)
        self._currency_combo.set_current_value(company.base_currency_code)
        self._apply_logo_preview(storage_path=company.logo_storage_path)
        self._update_logo_file_name_label()
        self._sync_logo_button_state()

    def _selected_code(self, combo: SearchableComboBox) -> str:
        value = combo.current_value()
        return value if isinstance(value, str) else ""

    def _sync_button_state(self) -> None:
        enabled = bool(self._countries) and bool(self._currencies)
        if self._is_create:
            self._create_button.setEnabled(enabled)
        else:
            if self._save_button is not None:
                self._save_button.setEnabled(enabled)

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def _build_logo_field(self, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        self._logo_preview_label = QLabel("Logo", row)
        self._logo_preview_label.setObjectName("CompanyLogoPreview")
        self._logo_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_preview_label.setFixedSize(72, 72)
        row_layout.addWidget(self._logo_preview_label, 0, Qt.AlignmentFlag.AlignTop)

        controls = QVBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self._logo_file_name_label = QLabel("No logo selected", row)
        self._logo_file_name_label.setObjectName("CompanyLogoFileName")
        self._logo_file_name_label.setWordWrap(True)
        controls.addWidget(self._logo_file_name_label)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self._browse_logo_button = QPushButton("Browse Logo", row)
        self._browse_logo_button.setProperty("variant", "secondary")
        self._browse_logo_button.clicked.connect(self._browse_logo_file)
        button_row.addWidget(self._browse_logo_button)

        self._remove_logo_button = QPushButton("Remove", row)
        self._remove_logo_button.setProperty("variant", "ghost")
        self._remove_logo_button.clicked.connect(self._remove_logo)
        button_row.addWidget(self._remove_logo_button)
        button_row.addStretch(1)

        controls.addLayout(button_row)
        controls.addStretch(1)
        row_layout.addLayout(controls, 1)

        self._sync_logo_button_state()
        return create_field_block(
            "Brand Logo",
            row,
            "Optional. Used in the sidebar identity panel for the active organisation.",
        )

    def _browse_logo_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Organisation Logo",
            "",
            "Image Files (*.png *.jpg *.jpeg *.webp)",
        )
        if not file_path:
            return

        try:
            self._service_registry.company_logo_service.validate_logo_file(file_path)
        except ValidationError as exc:
            self._set_error(str(exc))
            return

        self._set_error(None)
        self._selected_logo_file_path = file_path
        self._remove_logo_requested = False
        self._apply_logo_preview(file_path=file_path)
        self._update_logo_file_name_label()
        self._sync_logo_button_state()

    def _remove_logo(self) -> None:
        if not (self._selected_logo_file_path or self._existing_logo_storage_path):
            return

        self._selected_logo_file_path = None
        self._remove_logo_requested = bool(self._existing_logo_storage_path)
        self._apply_logo_preview()
        self._update_logo_file_name_label()
        self._sync_logo_button_state()

    def _apply_logo_preview(
        self,
        *,
        file_path: str | None = None,
        storage_path: str | None = None,
    ) -> None:
        pixmap = QPixmap()
        if file_path:
            pixmap = QPixmap(file_path)
        elif storage_path:
            resolved_path = self._service_registry.company_logo_service.resolve_logo_path(storage_path)
            if resolved_path is not None:
                pixmap = QPixmap(str(resolved_path))

        if pixmap.isNull():
            self._logo_preview_label.setPixmap(QPixmap())
            self._logo_preview_label.setText("Logo")
            return

        self._logo_preview_label.setText("")
        self._logo_preview_label.setPixmap(
            pixmap.scaled(
                56,
                56,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _update_logo_file_name_label(self) -> None:
        if self._selected_logo_file_path:
            self._logo_file_name_label.setText(Path(self._selected_logo_file_path).name)
            return
        if self._remove_logo_requested:
            self._logo_file_name_label.setText("Logo will be removed")
            return
        if self._existing_logo_original_filename:
            self._logo_file_name_label.setText(self._existing_logo_original_filename)
            return
        self._logo_file_name_label.setText("No logo selected")

    def _sync_logo_button_state(self) -> None:
        if hasattr(self, "_remove_logo_button"):
            self._remove_logo_button.setEnabled(bool(self._selected_logo_file_path or self._existing_logo_storage_path))

    def _persist_logo_changes(self, company_id: int) -> str | None:
        try:
            if self._selected_logo_file_path:
                self._service_registry.company_logo_service.set_logo(company_id, self._selected_logo_file_path)
                refreshed_company = self._get_company_handler(company_id)
                self._existing_logo_storage_path = refreshed_company.logo_storage_path
                self._existing_logo_original_filename = refreshed_company.logo_original_filename
                self._remove_logo_requested = False
                self._selected_logo_file_path = None
                return None

            if self._remove_logo_requested:
                self._service_registry.company_logo_service.clear_logo(company_id)
                self._existing_logo_storage_path = None
                self._existing_logo_original_filename = None
                self._remove_logo_requested = False
                return None

            return None
        except (ValidationError, NotFoundError) as exc:
            return str(exc)
        self._error_label.show()
