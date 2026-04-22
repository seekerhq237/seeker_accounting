from __future__ import annotations

import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.payroll.dto.payroll_posting_dto import (
    PostPayrollRunCommand,
    PayrollPostingValidationResultDTO,
)
from seeker_accounting.shared.ui.message_boxes import show_error

_SEVERITY_ICONS = {"error": "✖", "warning": "⚠"}


class PayrollPostRunDialog(QDialog):
    """Validate and post a payroll run to the GL.

    Step 1 (on open): runs validation and shows results.
    Step 2 (on OK): if no blocking errors, confirms and calls post_run.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        run_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._run_id = run_id
        self._posting_result = None

        self.setWindowTitle("Post Payroll Run to GL")
        self.setMinimumSize(580, 500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(12)

        # Posting date
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Posting Date:"))
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        today = datetime.date.today()
        self._date_edit.setDate(QDate(today.year, today.month, today.day))
        date_row.addWidget(self._date_edit)
        date_row.addStretch()
        layout.addLayout(date_row)

        # Narration
        layout.addWidget(QLabel("Narration (optional):"))
        self._narration = QTextEdit()
        self._narration.setMaximumHeight(48)
        self._narration.setPlaceholderText("Leave blank for auto-generated narration")
        layout.addWidget(self._narration)

        # Validation heading
        self._validation_label = QLabel("Validation Results")
        self._validation_label.setStyleSheet("font-weight: 600; font-size: 11px;")
        layout.addWidget(self._validation_label)

        self._issue_list = QListWidget()
        self._issue_list.setAlternatingRowColors(True)
        self._issue_list.setFixedHeight(160)
        layout.addWidget(self._issue_list)

        self._run_validation_btn_row = QHBoxLayout()
        self._validate_btn = QPushButton("Run Validation")
        self._validate_btn.clicked.connect(self._run_validation)
        self._run_validation_btn_row.addWidget(self._validate_btn)
        self._run_validation_btn_row.addStretch()
        layout.addLayout(self._run_validation_btn_row)

        # Quick-fix navigation buttons (shown when relevant validation errors exist)
        self._quickfix_row = QHBoxLayout()
        self._quickfix_row.setSpacing(8)
        quickfix_label = QLabel("Quick fix:")
        quickfix_label.setStyleSheet("font-size: 11px; color: #666;")
        self._quickfix_row.addWidget(quickfix_label)

        self._btn_open_role_mappings = QPushButton("Open Account Role Mappings")
        self._btn_open_role_mappings.setFixedHeight(24)
        self._btn_open_role_mappings.setStyleSheet("font-size: 11px;")
        self._btn_open_role_mappings.clicked.connect(self._go_to_role_mappings)
        self._quickfix_row.addWidget(self._btn_open_role_mappings)

        self._btn_open_payroll_setup = QPushButton("Open Payroll Components")
        self._btn_open_payroll_setup.setFixedHeight(24)
        self._btn_open_payroll_setup.setStyleSheet("font-size: 11px;")
        self._btn_open_payroll_setup.clicked.connect(self._go_to_payroll_setup)
        self._quickfix_row.addWidget(self._btn_open_payroll_setup)

        self._btn_open_fiscal_periods = QPushButton("Open Fiscal Periods")
        self._btn_open_fiscal_periods.setFixedHeight(24)
        self._btn_open_fiscal_periods.setStyleSheet("font-size: 11px;")
        self._btn_open_fiscal_periods.clicked.connect(self._go_to_fiscal_periods)
        self._quickfix_row.addWidget(self._btn_open_fiscal_periods)

        self._quickfix_row.addStretch()
        layout.addLayout(self._quickfix_row)
        # Start all hidden
        self._btn_open_role_mappings.hide()
        self._btn_open_payroll_setup.hide()
        self._btn_open_fiscal_periods.hide()
        quickfix_label.hide()
        self._quickfix_label = quickfix_label

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._status_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_post)
        self._buttons.rejected.connect(self.reject)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Post to GL")
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self._buttons)

        self._validation_result: PayrollPostingValidationResultDTO | None = None

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_post_run", dialog=True)

        self._run_validation()

    def _run_validation(self) -> None:
        self._issue_list.clear()
        self._hide_quickfix_buttons()
        posting_date = self._date_edit.date().toPython()
        try:
            result = self._registry.payroll_posting_validation_service.validate(
                self._company_id, self._run_id, posting_date
            )
        except Exception as exc:
            self._status_label.setText(f"Validation error: {exc}")
            return

        self._validation_result = result
        if not result.issues:
            self._issue_list.addItem("✔ No issues found. Ready to post.")
        for issue in result.issues:
            icon = _SEVERITY_ICONS.get(issue.severity, "•")
            self._issue_list.addItem(f"{icon} [{issue.severity.upper()}] {issue.message}")

        if result.has_errors:
            self._status_label.setText(
                f"❌ {result.error_count} blocking error(s). Resolve before posting."
            )
            self._status_label.setStyleSheet("color: #c0392b; font-size: 11px;")
            self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            self._show_relevant_quickfix_buttons(result)
        else:
            self._status_label.setText(
                f"✔ Ready to post {result.run_reference} ({result.period_label})."
            )
            self._status_label.setStyleSheet("color: #1a7a2e; font-size: 11px;")
            self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def _hide_quickfix_buttons(self) -> None:
        self._quickfix_label.hide()
        self._btn_open_role_mappings.hide()
        self._btn_open_payroll_setup.hide()
        self._btn_open_fiscal_periods.hide()

    def _show_relevant_quickfix_buttons(self, result: PayrollPostingValidationResultDTO) -> None:
        codes = {issue.issue_code for issue in result.issues}
        any_shown = False
        if codes & {"PAYROLL_PAYABLE_NOT_MAPPED", "PAYROLL_PAYABLE_INACTIVE", "PAYROLL_PAYABLE_CONTROL_ACCOUNT"}:
            self._btn_open_role_mappings.show()
            any_shown = True
        if codes & {"MISSING_EXPENSE_ACCOUNT", "MISSING_LIABILITY_ACCOUNT", "EXPENSE_ACCOUNT_INVALID", "LIABILITY_ACCOUNT_INVALID"}:
            self._btn_open_payroll_setup.show()
            any_shown = True
        if codes & {"NO_FISCAL_PERIOD", "PERIOD_LOCKED", "PERIOD_NOT_OPEN"}:
            self._btn_open_fiscal_periods.show()
            any_shown = True
        if any_shown:
            self._quickfix_label.show()

    def _go_to_role_mappings(self) -> None:
        from seeker_accounting.modules.accounting.reference_data.ui.account_role_mapping_dialog import (
            AccountRoleMappingDialog,
        )
        company_name = self._registry.app_context.active_company_name or ""
        AccountRoleMappingDialog.manage_mappings(
            self._registry, self._company_id, company_name, self
        )
        self._run_validation()

    def _go_to_payroll_setup(self) -> None:
        self._registry.navigation_service.navigate(nav_ids.PAYROLL_SETUP)
        self.reject()

    def _go_to_fiscal_periods(self) -> None:
        self._registry.navigation_service.navigate(nav_ids.FISCAL_PERIODS)
        self.reject()

    def _on_post(self) -> None:
        if self._validation_result is None or self._validation_result.has_errors:
            show_error(self, "Post Payroll Run", "Cannot post until all validation errors are resolved.")
            return
        posting_date = self._date_edit.date().toPython()
        narration = self._narration.toPlainText().strip() or None
        try:
            result = self._registry.payroll_posting_service.post_run(
                self._company_id,
                PostPayrollRunCommand(
                    run_id=self._run_id,
                    posting_date=posting_date,
                    narration=narration,
                ),
            )
            self._posting_result = result
            self.accept()
        except Exception as exc:
            show_error(self, "Post Payroll Run", str(exc))

    @property
    def posting_result(self):
        return self._posting_result
