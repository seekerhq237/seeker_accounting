from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import (
    PaymentTermListItemDTO,
    ReferenceOptionDTO,
)
from seeker_accounting.modules.suppliers.dto.supplier_commands import (
    CreateSupplierCommand,
    UpdateSupplierCommand,
)
from seeker_accounting.modules.suppliers.dto.supplier_dto import SupplierDetailDTO, SupplierGroupListItemDTO
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox


class SupplierDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        supplier_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._supplier_id = supplier_id
        self._saved_supplier: SupplierDetailDTO | None = None
        self._groups: list[SupplierGroupListItemDTO] = []
        self._payment_terms: list[PaymentTermListItemDTO] = []
        self._countries: list[ReferenceOptionDTO] = []

        title = "New Supplier" if supplier_id is None else "Edit Supplier"
        super().__init__(title, parent, help_key="dialog.supplier")
        self.setObjectName("SupplierDialog")
        self.resize(780, 620)

        intro_label = QLabel(
            "Capture the supplier once so bills, payments, and statements stay consistent.",
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
        self.body_layout.addWidget(self._build_terms_contact_section())
        self.body_layout.addWidget(self._build_address_notes_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        self._save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if self._save_button is not None:
            self._save_button.setText("Create Supplier" if supplier_id is None else "Save Changes")
            self._save_button.setProperty("variant", "primary")

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._load_reference_data()
        if self._supplier_id is not None:
            self._load_supplier()
        else:
            self._suggest_code()

    @property
    def saved_supplier(self) -> SupplierDetailDTO | None:
        return self._saved_supplier

    @classmethod
    def create_supplier(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> SupplierDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_supplier
        return None

    @classmethod
    def edit_supplier(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        supplier_id: int,
        parent: QWidget | None = None,
    ) -> SupplierDetailDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            supplier_id=supplier_id,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_supplier
        return None

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

        self._supplier_code_edit = QLineEdit(card)
        self._supplier_code_edit.setPlaceholderText("SUP-001")
        grid.addWidget(
            create_field_block(
                "Supplier Code",
                self._supplier_code_edit,
                "Unique within this company. Spaces are removed on save.",
            ),
            0,
            0,
        )

        self._display_name_edit = QLineEdit(card)
        self._display_name_edit.setPlaceholderText("Cameroon Packaging SARL")
        grid.addWidget(
            create_field_block(
                "Display Name",
                self._display_name_edit,
                "Used on bills, payments, and supplier-facing documents.",
            ),
            0,
            1,
        )

        self._legal_name_edit = QLineEdit(card)
        self._legal_name_edit.setPlaceholderText("Registered entity name (optional)")
        grid.addWidget(create_field_block("Legal Name", self._legal_name_edit), 1, 0)

        self._group_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Supplier Group", self._group_combo), 1, 1)

        layout.addLayout(grid)
        return card

    def _build_terms_contact_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Terms And Contact", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._payment_term_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Payment Term", self._payment_term_combo), 0, 0)

        self._country_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Country", self._country_combo), 0, 1)

        self._tax_identifier_edit = QLineEdit(card)
        self._tax_identifier_edit.setPlaceholderText("Optional tax / VAT ID")
        grid.addWidget(create_field_block("Tax Identifier", self._tax_identifier_edit), 1, 0)

        self._phone_edit = QLineEdit(card)
        self._phone_edit.setPlaceholderText("+237...")
        grid.addWidget(create_field_block("Phone", self._phone_edit), 1, 1)

        self._email_edit = QLineEdit(card)
        self._email_edit.setPlaceholderText("ap@supplier.com")
        grid.addWidget(create_field_block("Email", self._email_edit), 2, 0, 1, 2)

        layout.addLayout(grid)
        return card

    def _build_address_notes_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Address And Notes", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._address_1_edit = QLineEdit(card)
        self._address_1_edit.setPlaceholderText("Street, district, or site")
        grid.addWidget(create_field_block("Address Line 1", self._address_1_edit), 0, 0)

        self._address_2_edit = QLineEdit(card)
        self._address_2_edit.setPlaceholderText("Building, suite, or landmark")
        grid.addWidget(create_field_block("Address Line 2", self._address_2_edit), 0, 1)

        self._city_edit = QLineEdit(card)
        self._city_edit.setPlaceholderText("City")
        grid.addWidget(create_field_block("City", self._city_edit), 1, 0)

        self._region_edit = QLineEdit(card)
        self._region_edit.setPlaceholderText("Region / State")
        grid.addWidget(create_field_block("Region", self._region_edit), 1, 1)

        self._active_checkbox = QCheckBox("Supplier is active", card)
        self._active_checkbox.setChecked(True)
        self._active_checkbox.setVisible(self._supplier_id is not None)
        grid.addWidget(self._active_checkbox, 2, 0)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setPlaceholderText("Optional note for operators")
        self._notes_edit.setFixedHeight(92)
        grid.addWidget(create_field_block("Notes", self._notes_edit), 3, 0, 1, 2)

        layout.addLayout(grid)
        return card

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("supplier", self._company_id)
            self._supplier_code_edit.setText(code)
        except Exception:
            pass

    def _load_reference_data(self) -> None:
        try:
            self._groups = self._service_registry.supplier_service.list_supplier_groups(self._company_id, active_only=False)
            self._payment_terms = self._service_registry.reference_data_service.list_payment_terms(
                self._company_id,
                active_only=False,
            )
            self._countries = self._service_registry.reference_data_service.list_active_countries()
        except Exception as exc:
            self._set_error(f"Supplier references could not be loaded.\n\n{exc}")
            return

        self._populate_group_combo()
        self._populate_payment_term_combo()
        self._populate_country_combo()

    def _load_supplier(self) -> None:
        try:
            supplier = self._service_registry.supplier_service.get_supplier(self._company_id, self._supplier_id or 0)
        except NotFoundError as exc:
            show_error(self, "Supplier Not Found", str(exc))
            self.reject()
            return

        self._supplier_code_edit.setText(supplier.supplier_code)
        self._display_name_edit.setText(supplier.display_name)
        self._legal_name_edit.setText(supplier.legal_name or "")
        self._select_combo_data(self._group_combo, supplier.supplier_group_id)
        self._select_combo_data(self._payment_term_combo, supplier.payment_term_id)
        self._tax_identifier_edit.setText(supplier.tax_identifier or "")
        self._phone_edit.setText(supplier.phone or "")
        self._email_edit.setText(supplier.email or "")
        self._address_1_edit.setText(supplier.address_line_1 or "")
        self._address_2_edit.setText(supplier.address_line_2 or "")
        self._city_edit.setText(supplier.city or "")
        self._region_edit.setText(supplier.region or "")
        self._select_combo_data(self._country_combo, supplier.country_code)
        self._notes_edit.setPlainText(supplier.notes or "")
        self._active_checkbox.setChecked(supplier.is_active)

    def _populate_group_combo(self) -> None:
        self._group_combo.set_items(
            [(g.name if g.is_active else f"{g.name} (inactive)", g.id) for g in self._groups],
            placeholder="No group",
        )

    def _populate_payment_term_combo(self) -> None:
        self._payment_term_combo.set_items(
            [(pt.name if pt.is_active else f"{pt.name} (inactive)", pt.id) for pt in self._payment_terms],
            placeholder="No payment term",
        )

    def _populate_country_combo(self) -> None:
        self._country_combo.set_items(
            [(f"{c.code}  {c.name}", c.code) for c in self._countries],
            placeholder="No country",
        )

    def _select_combo_data(self, combo: SearchableComboBox, value: object) -> None:
        combo.set_current_value(value)

    def _selected_int(self, combo: SearchableComboBox) -> int | None:
        value = combo.current_value()
        return value if isinstance(value, int) and value > 0 else None

    def _selected_country_code(self) -> str | None:
        value = self._country_combo.current_value()
        return value if isinstance(value, str) and value else None

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def _handle_submit(self) -> None:
        self._set_error(None)

        supplier_code = self._supplier_code_edit.text().strip()
        display_name = self._display_name_edit.text().strip()
        if not supplier_code:
            self._set_error("Supplier code is required.")
            self._supplier_code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not display_name:
            self._set_error("Display name is required.")
            self._display_name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        payload = {
            "supplier_code": supplier_code,
            "display_name": display_name,
            "legal_name": self._legal_name_edit.text().strip() or None,
            "supplier_group_id": self._selected_int(self._group_combo),
            "payment_term_id": self._selected_int(self._payment_term_combo),
            "tax_identifier": self._tax_identifier_edit.text().strip() or None,
            "phone": self._phone_edit.text().strip() or None,
            "email": self._email_edit.text().strip() or None,
            "address_line_1": self._address_1_edit.text().strip() or None,
            "address_line_2": self._address_2_edit.text().strip() or None,
            "city": self._city_edit.text().strip() or None,
            "region": self._region_edit.text().strip() or None,
            "country_code": self._selected_country_code(),
            "notes": self._notes_edit.toPlainText().strip() or None,
        }

        try:
            if self._supplier_id is None:
                self._saved_supplier = self._service_registry.supplier_service.create_supplier(
                    self._company_id,
                    CreateSupplierCommand(**payload),
                )
            else:
                self._saved_supplier = self._service_registry.supplier_service.update_supplier(
                    self._company_id,
                    self._supplier_id,
                    UpdateSupplierCommand(
                        **payload,
                        is_active=self._active_checkbox.isChecked(),
                    ),
                )
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Supplier Not Found", str(exc))
            return

        self.accept()
