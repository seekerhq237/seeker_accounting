from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.treasury.dto.bank_statement_commands import ImportBankStatementCommand
from seeker_accounting.modules.treasury.dto.bank_statement_dto import ImportResultDTO
from seeker_accounting.platform.exceptions import ValidationError

_log = logging.getLogger(__name__)


class StatementImportDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._saved_result: ImportResultDTO | None = None
        self._selected_file_path: str | None = None

        self.setWindowTitle(f"Import Bank Statement — {company_name}")
        self.setModal(True)
        self.resize(550, 350)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_form_section())

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        self._button_box.accepted.connect(self._handle_submit)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._load_reference_data()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.statement_import")

    @property
    def saved_result(self) -> ImportResultDTO | None:
        return self._saved_result

    @classmethod
    def import_statement(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> ImportResultDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_result
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_form_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self._account_combo = QComboBox(card)
        form.addRow("Financial Account", self._account_combo)

        file_row = QWidget(card)
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(8)

        self._file_path_input = QLineEdit(file_row)
        self._file_path_input.setReadOnly(True)
        self._file_path_input.setPlaceholderText("Select a CSV file...")
        file_layout.addWidget(self._file_path_input, 1)

        browse_button = QPushButton("Browse...", file_row)
        browse_button.clicked.connect(self._browse_file)
        file_layout.addWidget(browse_button)

        form.addRow("CSV File", file_row)

        self._notes_input = QPlainTextEdit(card)
        self._notes_input.setMaximumHeight(50)
        self._notes_input.setPlaceholderText("Optional notes")
        form.addRow("Notes", self._notes_input)

        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            accounts = self._service_registry.financial_account_service.list_financial_accounts(
                self._company_id, active_only=True
            )
            self._account_combo.clear()
            self._account_combo.addItem("-- Select account --", 0)
            for a in accounts:
                self._account_combo.addItem(f"{a.account_code} — {a.name}", a.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Bank Statement CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if file_path:
            self._selected_file_path = file_path
            self._file_path_input.setText(file_path)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        financial_account_id = self._account_combo.currentData()
        if not financial_account_id or financial_account_id == 0:
            self._set_error("Please select a financial account.")
            return

        if not self._selected_file_path:
            self._set_error("Please select a CSV file to import.")
            return

        notes = self._notes_input.toPlainText().strip() or None

        try:
            cmd = ImportBankStatementCommand(
                financial_account_id=financial_account_id,
                file_path=self._selected_file_path,
                notes=notes,
            )
            self._saved_result = self._service_registry.bank_statement_service.import_statement(
                self._company_id, cmd
            )
            self.accept()
        except (ValidationError, Exception) as exc:
            self._set_error(str(exc))

    def _set_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
