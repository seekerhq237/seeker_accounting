from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
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
from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.companies.ui.company_form_dialog import CompanyFormDialog
from seeker_accounting.modules.companies.ui.company_preferences_dialog import CompanyPreferencesDialog
from seeker_accounting.modules.companies.ui.system_admin_auth_dialog import SystemAdminAuthDialog
from seeker_accounting.shared.ui.message_boxes import show_error


class OrganisationSettingsPage(QWidget):
    """Organisation settings page showing the active company detail panel.

    Modifications are gated behind system administrator authentication.
    Company switching is not available here; context is established via login.
    """

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._detail: CompanyDetailDTO | None = None

        self.setObjectName("OrganisationSettingsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_action_bar())

        self._detail_card = self._build_detail_card()
        root_layout.addWidget(self._detail_card)

        self._no_company_card = self._build_no_company_card()
        root_layout.addWidget(self._no_company_card)

        root_layout.addStretch(1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload(),
        )

        self.reload()

    # ── Action bar ──────────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        layout.addStretch(1)

        self._modify_button = QPushButton("Modify Details", card)
        self._modify_button.setProperty("variant", "primary")
        self._modify_button.clicked.connect(self._open_modify_dialog)
        layout.addWidget(self._modify_button)

        self._preferences_button = QPushButton("Company Preferences", card)
        self._preferences_button.setProperty("variant", "secondary")
        self._preferences_button.clicked.connect(self._open_preferences_dialog)
        layout.addWidget(self._preferences_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self.reload)
        layout.addWidget(self._refresh_button)

        return card

    # ── Detail card ─────────────────────────────────────────────────────────

    def _build_detail_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        outer = QVBoxLayout(card)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)

        # Header: logo + primary identity
        header = QHBoxLayout()
        header.setSpacing(20)

        self._logo_label = QLabel(card)
        self._logo_label.setObjectName("OrgLogoDisplay")
        self._logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_label.setFixedSize(96, 96)
        self._logo_label.setText("Logo")
        self._logo_label.setStyleSheet(
            "QLabel { border: 1px solid #E5E7EB; border-radius: 8px; "
            "background: #F9FAFB; color: #9CA3AF; font-size: 11px; }"
        )
        header.addWidget(self._logo_label, 0, Qt.AlignmentFlag.AlignTop)

        identity = QVBoxLayout()
        identity.setSpacing(4)

        self._display_name_label = QLabel(card)
        self._display_name_label.setObjectName("OrgDisplayName")
        self._display_name_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827;")
        self._display_name_label.setWordWrap(True)
        identity.addWidget(self._display_name_label)

        self._legal_name_label = QLabel(card)
        self._legal_name_label.setObjectName("OrgLegalName")
        self._legal_name_label.setStyleSheet("font-size: 13px; color: #6B7280;")
        identity.addWidget(self._legal_name_label)

        self._status_label = QLabel(card)
        self._status_label.setObjectName("OrgStatus")
        self._status_label.setFixedWidth(60)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        identity.addWidget(self._status_label, 0, Qt.AlignmentFlag.AlignLeft)
        identity.addStretch(1)

        header.addLayout(identity, 1)
        outer.addLayout(header)

        # Divider
        divider = QFrame(card)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #E5E7EB;")
        outer.addWidget(divider)

        # Fields: two columns
        fields_widget = QWidget(card)
        fields_layout = QHBoxLayout(fields_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(40)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        self._reg_row = self._make_field_row("Registration No.", card)
        self._tax_row = self._make_field_row("Tax Identifier", card)
        self._country_row = self._make_field_row("Country", card)
        self._currency_row = self._make_field_row("Base Currency", card)
        self._sector_row = self._make_field_row("Sector", card)

        left_col.addLayout(self._reg_row[0])
        left_col.addLayout(self._tax_row[0])
        left_col.addLayout(self._country_row[0])
        left_col.addLayout(self._currency_row[0])
        left_col.addLayout(self._sector_row[0])
        left_col.addStretch(1)

        self._phone_row = self._make_field_row("Phone", card)
        self._email_row = self._make_field_row("Email", card)
        self._website_row = self._make_field_row("Website", card)
        self._address_row = self._make_field_row("Address", card)
        self._city_row = self._make_field_row("City / Region", card)

        right_col.addLayout(self._phone_row[0])
        right_col.addLayout(self._email_row[0])
        right_col.addLayout(self._website_row[0])
        right_col.addLayout(self._address_row[0])
        right_col.addLayout(self._city_row[0])
        right_col.addStretch(1)

        fields_layout.addLayout(left_col, 1)
        fields_layout.addLayout(right_col, 1)

        outer.addWidget(fields_widget)

        return card

    def _make_field_row(self, label_text: str, parent: QWidget) -> tuple[QHBoxLayout, QLabel]:
        """Return (layout, value_label) for a label : value row."""
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel(label_text + ":", parent)
        lbl.setStyleSheet("font-size: 11px; color: #9CA3AF; font-weight: 500;")
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        row.addWidget(lbl)

        val = QLabel("\u2014", parent)
        val.setStyleSheet("font-size: 12px; color: #111827;")
        val.setWordWrap(True)
        val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(val, 1)

        return row, val

    # ── No-company state ────────────────────────────────────────────────────

    def _build_no_company_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No active company", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Organisation settings are not available without an active company context. "
            "Log out and log in to activate a company.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        layout.addStretch(1)
        return card

    # ── Data loading ────────────────────────────────────────────────────────

    def reload(self) -> None:
        active = self._service_registry.company_context_service.get_active_company()
        if active is None:
            self._detail = None
            self._detail_card.hide()
            self._no_company_card.show()
            self._update_action_state()
            return

        try:
            self._detail = self._service_registry.company_service.get_company(active.company_id)
        except Exception as exc:
            self._detail = None
            self._detail_card.hide()
            self._no_company_card.show()
            self._update_action_state()
            show_error(self, "Organisation Settings", f"Company data could not be loaded.\n\n{exc}")
            return

        self._populate_detail(self._detail)
        self._no_company_card.hide()
        self._detail_card.show()
        self._update_action_state()

    def _populate_detail(self, detail: CompanyDetailDTO) -> None:
        self._display_name_label.setText(detail.display_name)
        self._legal_name_label.setText(detail.legal_name)

        if detail.is_active:
            self._status_label.setText("Active")
            self._status_label.setStyleSheet(
                "font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; "
                "background: #D1FAE5; color: #065F46;"
            )
        else:
            self._status_label.setText("Inactive")
            self._status_label.setStyleSheet(
                "font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; "
                "background: #FEE2E2; color: #991B1B;"
            )

        self._reg_row[1].setText(detail.registration_number or "\u2014")
        self._tax_row[1].setText(detail.tax_identifier or "\u2014")
        self._country_row[1].setText(detail.country_code or "\u2014")
        self._currency_row[1].setText(detail.base_currency_code)
        self._sector_row[1].setText(detail.sector_of_operation or "\u2014")

        self._phone_row[1].setText(detail.phone or "\u2014")
        self._email_row[1].setText(detail.email or "\u2014")
        self._website_row[1].setText(detail.website or "\u2014")

        address_parts = [p for p in (detail.address_line_1, detail.address_line_2) if p]
        self._address_row[1].setText(", ".join(address_parts) if address_parts else "\u2014")

        city_parts = [p for p in (detail.city, detail.region) if p]
        self._city_row[1].setText(", ".join(city_parts) if city_parts else "\u2014")

        self._load_logo(detail.logo_storage_path)

    def _load_logo(self, logo_storage_path: str | None) -> None:
        if not logo_storage_path:
            self._logo_label.setPixmap(QPixmap())
            self._logo_label.setText("Logo")
            return

        resolved = self._service_registry.company_logo_service.resolve_logo_path(logo_storage_path)
        if resolved is None:
            self._logo_label.setPixmap(QPixmap())
            self._logo_label.setText("Logo")
            return

        pixmap = QPixmap(str(resolved))
        if pixmap.isNull():
            self._logo_label.setPixmap(QPixmap())
            self._logo_label.setText("Logo")
            return

        self._logo_label.setText("")
        self._logo_label.setPixmap(
            pixmap.scaled(
                84,
                84,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ── Action state ────────────────────────────────────────────────────────

    def _update_action_state(self) -> None:
        has_company = self._detail is not None
        self._modify_button.setEnabled(has_company)
        self._preferences_button.setEnabled(
            has_company
            and self._service_registry.permission_service.has_permission(
                "companies.preferences.manage"
            )
        )

    # ── Dialogs ─────────────────────────────────────────────────────────────

    def _open_modify_dialog(self) -> None:
        """Gate modification behind system administrator authentication."""
        if self._detail is None:
            return

        from seeker_accounting.app.dependency.factories import create_system_admin_service

        system_admin_service = create_system_admin_service(
            self._service_registry.session_context
        )
        authenticated = SystemAdminAuthDialog.authenticate(
            system_admin_service,
            parent=self,
        )
        if not authenticated:
            return

        updated = CompanyFormDialog.edit_company(
            self._service_registry,
            self._detail.id,
            self,
        )
        if updated is not None:
            self.reload()

    def _open_preferences_dialog(self) -> None:
        if self._detail is None:
            return
        if not self._service_registry.permission_service.has_permission(
            "companies.preferences.manage"
        ):
            show_error(
                self,
                "Organisation Settings",
                self._service_registry.permission_service.build_denied_message(
                    "companies.preferences.manage"
                ),
            )
            return

        dialog = CompanyPreferencesDialog(
            service_registry=self._service_registry,
            company_id=self._detail.id,
            company_name=self._detail.display_name,
            parent=self,
        )
        dialog.exec()
        self.reload()
