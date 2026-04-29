"""Company Tax Profile page.

Single-record-per-company surface. Mirrors the OrganisationSettings
pattern: header card with key fields, a "Modify" button that opens a
focused dialog. The profile drives obligations, returns, and DSF.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.taxation.dto.company_tax_profile_dto import (
    CompanyTaxProfileDTO,
)
from seeker_accounting.modules.taxation.ui.company_tax_profile_dialog import (
    CompanyTaxProfileDialog,
)
from seeker_accounting.platform.exceptions import PermissionDeniedError
from seeker_accounting.shared.ui.message_boxes import show_error


_DASH = "\u2014"


def _human_label(value: str | None) -> str:
    if value is None or value == "":
        return _DASH
    return value.replace("_", " ").title()


def _yesno(value: bool) -> str:
    return "Yes" if value else "No"


def _date_text(value: date | None) -> str:
    if value is None:
        return _DASH
    return value.isoformat()


class CompanyTaxProfilePage(RibbonHostMixin, QWidget):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._profile: CompanyTaxProfileDTO | None = None

        self.setObjectName("CompanyTaxProfilePage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_action_bar())

        self._stack = QStackedWidget(self)
        self._no_company_card = self._build_no_company_card()
        self._detail_card = self._build_detail_card()
        self._stack.addWidget(self._no_company_card)
        self._stack.addWidget(self._detail_card)
        root.addWidget(self._stack, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    # ── Action bar ────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Tax Profile", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._meta_label = QLabel(card)
        self._meta_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._meta_label)

        layout.addStretch(1)

        self._modify_button = QPushButton("Edit Profile", card)
        self._modify_button.setProperty("variant", "primary")
        self._modify_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._modify_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self.reload)
        layout.addWidget(self._refresh_button)

        return card

    # ── Detail card ───────────────────────────────────────────────────

    def _build_detail_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        outer = QVBoxLayout(card)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)

        self._exists_banner = QLabel(card)
        self._exists_banner.setObjectName("PageBanner")
        self._exists_banner.setWordWrap(True)
        self._exists_banner.setStyleSheet(
            "QLabel { background: #FEF3C7; color: #92400E; padding: 8px 12px; "
            "border-radius: 6px; font-size: 12px; }"
        )
        outer.addWidget(self._exists_banner)

        # Header line
        self._title_label = QLabel(card)
        self._title_label.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #111827;"
        )
        outer.addWidget(self._title_label)

        divider = QFrame(card)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #E5E7EB;")
        outer.addWidget(divider)

        # Two-column field grid
        fields_widget = QWidget(card)
        fields_layout = QHBoxLayout(fields_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(40)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        self._niu_row = self._make_field_row("NIU", card)
        self._tax_center_row = self._make_field_row("Tax centre code", card)
        self._segment_row = self._make_field_row("Taxpayer segment", card)
        self._regime_row = self._make_field_row("Tax regime", card)
        self._vat_row = self._make_field_row("VAT liable", card)
        self._vat_from_row = self._make_field_row("VAT effective from", card)
        self._sme_row = self._make_field_row("SME qualified", card)

        left_col.addLayout(self._niu_row[0])
        left_col.addLayout(self._tax_center_row[0])
        left_col.addLayout(self._segment_row[0])
        left_col.addLayout(self._regime_row[0])
        left_col.addLayout(self._vat_row[0])
        left_col.addLayout(self._vat_from_row[0])
        left_col.addLayout(self._sme_row[0])
        left_col.addStretch(1)

        self._cit_rate_row = self._make_field_row("CIT rate profile", card)
        self._cit_inst_row = self._make_field_row("CIT installment profile", card)
        self._dsf_form_row = self._make_field_row("DSF form", card)
        self._dsf_submit_row = self._make_field_row("DSF submission", card)
        self._otp_row = self._make_field_row("OTP enabled", card)
        self._wht_row = self._make_field_row("Default withholding", card)

        right_col.addLayout(self._cit_rate_row[0])
        right_col.addLayout(self._cit_inst_row[0])
        right_col.addLayout(self._dsf_form_row[0])
        right_col.addLayout(self._dsf_submit_row[0])
        right_col.addLayout(self._otp_row[0])
        right_col.addLayout(self._wht_row[0])
        right_col.addStretch(1)

        fields_layout.addLayout(left_col, 1)
        fields_layout.addLayout(right_col, 1)
        outer.addWidget(fields_widget)
        outer.addStretch(1)

        return card

    def _make_field_row(
        self, label_text: str, parent: QWidget
    ) -> tuple[QHBoxLayout, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel(label_text + ":", parent)
        lbl.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; font-weight: 500;"
        )
        lbl.setFixedWidth(160)
        lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        row.addWidget(lbl)

        val = QLabel(_DASH, parent)
        val.setStyleSheet("font-size: 12px; color: #111827;")
        val.setWordWrap(True)
        val.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        row.addWidget(val, 1)

        return row, val

    # ── No-company state ──────────────────────────────────────────────

    def _build_no_company_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No active company", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        body = QLabel(
            "Select a company from the top context bar to view or edit its "
            "tax profile.",
            card,
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)

        return card

    # ── Reload / display ─────────────────────────────────────────────

    def reload(self) -> None:
        active = self._active_company()

        if active is None:
            self._profile = None
            self._meta_label.setText("Select a company")
            self._modify_button.setEnabled(False)
            self._stack.setCurrentWidget(self._no_company_card)
            return

        try:
            profile = (
                self._service_registry.company_tax_profile_service.get_or_default(
                    active.company_id
                )
            )
        except PermissionDeniedError as exc:
            self._profile = None
            self._meta_label.setText("Permission denied")
            self._modify_button.setEnabled(False)
            self._stack.setCurrentWidget(self._no_company_card)
            show_error(self, "Tax Profile", str(exc))
            return
        except Exception as exc:
            self._profile = None
            self._meta_label.setText("Unable to load")
            self._modify_button.setEnabled(False)
            self._stack.setCurrentWidget(self._no_company_card)
            show_error(self, "Tax Profile", f"Could not load profile.\n\n{exc}")
            return

        self._profile = profile
        permission_service = self._service_registry.permission_service
        can_manage = permission_service.has_permission("taxation.profile.manage")
        self._modify_button.setEnabled(can_manage)
        self._render_profile(active.company_name, profile)
        self._stack.setCurrentWidget(self._detail_card)
        self._notify_ribbon_state_changed()

    def _render_profile(
        self, company_name: str, profile: CompanyTaxProfileDTO
    ) -> None:
        self._title_label.setText(company_name)
        if profile.exists:
            self._exists_banner.hide()
            self._meta_label.setText("Configured")
        else:
            self._exists_banner.setText(
                "No tax profile configured for this company yet. "
                "Use Edit Profile to set NIU, regime, VAT liability, and DSF settings."
            )
            self._exists_banner.show()
            self._meta_label.setText("Not configured")

        self._niu_row[1].setText(profile.niu or _DASH)
        self._tax_center_row[1].setText(profile.tax_center_code or _DASH)
        self._segment_row[1].setText(_human_label(profile.taxpayer_segment_code))
        self._regime_row[1].setText(_human_label(profile.tax_regime_code))
        self._vat_row[1].setText(_yesno(profile.is_vat_liable))
        self._vat_from_row[1].setText(_date_text(profile.vat_effective_from))
        self._sme_row[1].setText(_yesno(profile.sme_qualified_flag))

        self._cit_rate_row[1].setText(_human_label(profile.cit_rate_profile_code))
        self._cit_inst_row[1].setText(profile.cit_installment_profile_code or _DASH)
        self._dsf_form_row[1].setText(_human_label(profile.dsf_form_code))
        self._dsf_submit_row[1].setText(
            _human_label(profile.dsf_submission_mode_code)
        )
        self._otp_row[1].setText(_yesno(profile.otp_enabled_flag))
        self._wht_row[1].setText(
            _yesno(profile.default_withholding_applicable_flag)
        )

    # ── Actions ──────────────────────────────────────────────────────

    def _open_edit_dialog(self) -> None:
        active = self._active_company()
        if active is None or self._profile is None:
            return

        dialog = CompanyTaxProfileDialog(
            self._service_registry,
            active.company_id,
            active.company_name,
            self._profile,
            parent=self,
        )
        if dialog.exec() and dialog.saved_profile() is not None:
            self.reload()

    # ── Helpers ──────────────────────────────────────────────────────

    def _active_company(self):
        return self._service_registry.company_context_service.get_active_company()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self) -> dict:
        return {
            "tax_profile.edit": self._open_edit_dialog,
            "tax_profile.refresh": self.reload,
        }

    def ribbon_state(self) -> dict:
        return {
            "tax_profile.edit": self._modify_button.isEnabled(),
            "tax_profile.refresh": True,
        }
