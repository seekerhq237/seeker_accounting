"""Login dialog with user-first authentication and scoped company selection."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from seeker_accounting.modules.administration.dto.user_dto import (
    AuthenticatedUserDTO,
    LoginResultDTO,
)
from seeker_accounting.modules.administration.services.user_auth_service import UserAuthService
from seeker_accounting.modules.companies.dto.company_dto import CompanyListItemDTO
from seeker_accounting.modules.companies.services.company_service import CompanyService
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Returned to the caller after a successful login."""

    login_dto: LoginResultDTO
    company: CompanyListItemDTO


class LoginDialog(BaseDialog):
    """User-first login dialog."""

    def __init__(
        self,
        company_service: CompanyService,
        user_auth_service: UserAuthService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Log In", parent, help_key="dialog.login")
        self.setObjectName("LoginDialog")
        self.resize(420, 340)

        self._company_service = company_service
        self._user_auth_service = user_auth_service
        self._result: LoginResult | None = None
        self._authenticated_user: AuthenticatedUserDTO | None = None
        self._companies: list[CompanyListItemDTO] = []
        self._admin_alias_mode: bool = False
        self._pending_password: str = ""

        self._instruction_label = QLabel(
            "Enter your username and password. If you can access more than one organisation, you will choose it next.",
            self,
        )
        self._instruction_label.setWordWrap(True)
        self.body_layout.addWidget(self._instruction_label)

        self._username_edit = QLineEdit(self)
        self._username_edit.setPlaceholderText("Username")
        self.body_layout.addWidget(create_field_block("Username", self._username_edit))

        self._password_edit = QLineEdit(self)
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Password")

        self._toggle_pw_action = QAction("Show", self._password_edit)
        self._toggle_pw_action.setToolTip("Show or hide password")
        self._toggle_pw_action.triggered.connect(self._toggle_password_visibility)
        self._password_edit.addAction(
            self._toggle_pw_action, QLineEdit.ActionPosition.TrailingPosition
        )
        self.body_layout.addWidget(create_field_block("Password", self._password_edit))

        self._company_combo = QComboBox(self)
        self._company_combo.setPlaceholderText("Select an organisation...")
        self._company_block = create_field_block("Organisation", self._company_combo)
        self._company_block.hide()
        self.body_layout.addWidget(self._company_block)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        self._primary_button = QPushButton("Continue", self)
        self._primary_button.setProperty("variant", "primary")
        self._primary_button.setDefault(True)
        self._primary_button.clicked.connect(self._handle_primary_action)
        self.button_box.addButton(self._primary_button, QDialogButtonBox.ButtonRole.AcceptRole)

        self._reset_button = QPushButton("Use Different User", self)
        self._reset_button.setProperty("variant", "secondary")
        self._reset_button.clicked.connect(self._reset_authentication_flow)
        self._reset_button.hide()
        self.button_box.addButton(self._reset_button, QDialogButtonBox.ButtonRole.ActionRole)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setProperty("variant", "secondary")
        cancel_btn.clicked.connect(self.reject)
        self.button_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

        self._password_edit.returnPressed.connect(self._handle_primary_action)
        self._username_edit.returnPressed.connect(self._focus_password)

    @property
    def login_result(self) -> LoginResult | None:
        return self._result

    @classmethod
    def prompt(
        cls,
        company_service: CompanyService,
        user_auth_service: UserAuthService,
        parent: QWidget | None = None,
    ) -> LoginResult | None:
        dialog = cls(
            company_service=company_service,
            user_auth_service=user_auth_service,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.login_result
        return None

    def _focus_password(self) -> None:
        self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _toggle_password_visibility(self) -> None:
        if self._password_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_pw_action.setText("Hide")
        else:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_pw_action.setText("Show")

    def _handle_primary_action(self) -> None:
        if self._authenticated_user is None and not self._admin_alias_mode:
            self._authenticate_user()
            return
        self._complete_login()

    def _authenticate_user(self) -> None:
        self._error_label.hide()

        username = self._username_edit.text().strip()
        if not username:
            self._show_error("Username is required.")
            self._username_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        password = self._password_edit.text()
        if not password:
            self._show_error("Password is required.")
            self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        # Admin alias: show company picker first, authenticate after company is chosen.
        if username.lower() == "admin":
            self._authenticate_admin_alias(password)
            return

        try:
            authenticated_user = self._user_auth_service.authenticate(username=username, password=password)
            companies = self._company_service.list_companies_for_user(authenticated_user.user_id)
        except ValidationError as exc:
            self._show_error(str(exc))
            self._password_edit.clear()
            self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        except Exception:
            logger.exception("Unexpected error during login.")
            self._show_error("An unexpected error occurred. Please try again.")
            return

        if not companies:
            self._show_error("This user does not have access to any active organisation.")
            self._password_edit.clear()
            self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        self._authenticated_user = authenticated_user
        self._companies = companies
        self._password_edit.clear()

        if len(companies) == 1:
            self._complete_login(companies[0])
            return

        self._show_company_picker(
            "Select the organisation you want to work with for this session."
        )

    def _authenticate_admin_alias(self, password: str) -> None:
        """Load all active companies and show the company picker for the 'admin' alias."""
        try:
            companies = self._company_service.list_all_active_companies()
        except Exception:
            logger.exception("Could not load companies for admin alias login.")
            self._show_error("An unexpected error occurred. Please try again.")
            return

        if not companies:
            self._show_error("No active organisations exist.")
            return

        self._pending_password = password
        self._admin_alias_mode = True
        self._companies = companies
        self._password_edit.clear()

        self._show_company_picker(
            "Select the organisation to log in to as administrator."
        )

    def _show_company_picker(self, instruction: str) -> None:
        self._instruction_label.setText(instruction)
        self._company_combo.clear()
        for company in self._companies:
            self._company_combo.addItem(company.display_name, userData=company.id)
        self._company_combo.setCurrentIndex(0)
        self._company_block.show()
        self._reset_button.show()
        self._primary_button.setText("Log In")
        self._username_edit.setEnabled(False)
        self._password_edit.setEnabled(False)
        self._company_combo.setFocus(Qt.FocusReason.OtherFocusReason)

    def _complete_login(self, selected_company: CompanyListItemDTO | None = None) -> None:
        self._error_label.hide()

        if self._authenticated_user is None and not self._admin_alias_mode:
            self._show_error("Please enter your credentials first.")
            return

        company = selected_company or self._selected_company()
        if company is None:
            self._show_error("Please select an organisation.")
            self._company_combo.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        if self._admin_alias_mode:
            self._complete_admin_alias_login(company)
            return

        try:
            login_dto = self._user_auth_service.complete_login(
                user_id=self._authenticated_user.user_id,  # type: ignore[union-attr]
                company_id=company.id,
            )
        except ValidationError as exc:
            self._show_error(str(exc))
            self._reset_authentication_flow()
            self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        except Exception:
            logger.exception("Unexpected error completing login.")
            self._show_error("An unexpected error occurred. Please try again.")
            self._reset_authentication_flow()
            return

        self._result = LoginResult(login_dto=login_dto, company=company)
        self.accept()

    def _complete_admin_alias_login(self, company: CompanyListItemDTO) -> None:
        """Resolve 'admin' alias for the chosen company and authenticate."""
        try:
            login_dto = self._user_auth_service.authenticate_for_company(
                company_id=company.id,
                username="admin",
                password=self._pending_password,
            )
        except ValidationError as exc:
            self._show_error(str(exc))
            self._reset_authentication_flow()
            self._password_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        except Exception:
            logger.exception("Unexpected error during admin alias login.")
            self._show_error("An unexpected error occurred. Please try again.")
            self._reset_authentication_flow()
            return
        finally:
            self._pending_password = ""

        self._result = LoginResult(login_dto=login_dto, company=company)
        self.accept()

    def _selected_company(self) -> CompanyListItemDTO | None:
        company_index = self._company_combo.currentIndex()
        if company_index < 0 or company_index >= len(self._companies):
            return None
        return self._companies[company_index]

    def _reset_authentication_flow(self) -> None:
        self._authenticated_user = None
        self._companies = []
        self._admin_alias_mode = False
        self._pending_password = ""
        self._company_combo.clear()
        self._company_block.hide()
        self._reset_button.hide()
        self._primary_button.setText("Continue")
        self._instruction_label.setText(
            "Enter your username and password. If you can access more than one organisation, you will choose it next."
        )
        self._username_edit.setEnabled(True)
        self._password_edit.setEnabled(True)
        self._password_edit.clear()
        self._username_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
