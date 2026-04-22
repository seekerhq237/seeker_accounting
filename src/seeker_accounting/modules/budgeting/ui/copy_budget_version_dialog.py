from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.budgeting.dto.project_budget_commands import (
    CloneProjectBudgetVersionCommand,
)
from seeker_accounting.modules.budgeting.dto.project_budget_dto import (
    ProjectBudgetVersionListItemDTO,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block

_VERSION_TYPE_OPTIONS = (
    ("original", "Original"),
    ("revision", "Revision"),
    ("working", "Working"),
    ("forecast", "Forecast"),
)


class CopyBudgetVersionDialog(BaseDialog):
    """Dialog for configuring a budget version copy before creating it."""

    def __init__(
        self,
        company_id: int,
        project_id: int,
        source: ProjectBudgetVersionListItemDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Copy Budget Version", parent)
        self.setObjectName("CopyBudgetVersionDialog")
        self.resize(520, 430)

        self._company_id = company_id
        self._project_id = project_id
        self._source = source
        self._result_command: CloneProjectBudgetVersionCommand | None = None

        # Source info label
        source_label = QLabel(
            f"Copying from: V{source.version_number} — {source.version_name}",
            self,
        )
        source_label.setObjectName("PageSummary")
        source_label.setWordWrap(True)
        self.body_layout.addWidget(source_label)

        # Inline error label
        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_form_section())
        self.body_layout.addWidget(self._build_reason_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Create Copy")
            ok_btn.setProperty("variant", "primary")

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")

        self.button_box.accepted.connect(self._handle_submit)

    # ------------------------------------------------------------------
    # Form sections
    # ------------------------------------------------------------------

    def _build_form_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("New Version Details", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._name_edit = QLineEdit(card)
        self._name_edit.setText(f"Copy of {self._source.version_name}")
        self._name_edit.setPlaceholderText("e.g. Copy of Original Budget")
        grid.addWidget(create_field_block("Version Name", self._name_edit), 0, 0, 1, 2)

        self._type_combo = QComboBox(card)
        for code, label in _VERSION_TYPE_OPTIONS:
            self._type_combo.addItem(label, code)
        source_type_idx = self._type_combo.findData(self._source.version_type_code)
        if source_type_idx >= 0:
            self._type_combo.setCurrentIndex(source_type_idx)
        grid.addWidget(create_field_block("Version Type", self._type_combo), 1, 0)

        self._budget_date_edit = QDateEdit(card)
        self._budget_date_edit.setCalendarPopup(True)
        self._budget_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._budget_date_edit.setDate(date.today())
        grid.addWidget(create_field_block("Budget Date", self._budget_date_edit), 1, 1)

        layout.addLayout(grid)
        return card

    def _build_reason_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Revision Reason", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._reason_edit = QPlainTextEdit(card)
        self._reason_edit.setPlaceholderText("Optional revision reason or notes")
        self._reason_edit.setPlainText(
            f"Copied from V{self._source.version_number} — {self._source.version_name}"
        )
        self._reason_edit.setFixedHeight(70)
        layout.addWidget(self._reason_edit)
        return card

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

        name = self._name_edit.text().strip()
        if not name:
            self._set_error("Version name is required.")
            return

        self._result_command = CloneProjectBudgetVersionCommand(
            source_version_id=self._source.id,
            company_id=self._company_id,
            project_id=self._project_id,
            version_name=name,
            version_type_code=self._type_combo.currentData(),
            budget_date=self._budget_date_edit.date().toPython(),
            revision_reason=self._reason_edit.toPlainText().strip() or None,
        )
        self.accept()

    # ------------------------------------------------------------------
    # Class-method entry point
    # ------------------------------------------------------------------

    @classmethod
    def copy_version(
        cls,
        company_id: int,
        project_id: int,
        source: ProjectBudgetVersionListItemDTO,
        parent: QWidget | None = None,
    ) -> CloneProjectBudgetVersionCommand | None:
        """Open the dialog and return the assembled command, or None if cancelled."""
        dialog = cls(company_id, project_id, source, parent)
        from PySide6.QtWidgets import QDialog

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog._result_command
        return None
