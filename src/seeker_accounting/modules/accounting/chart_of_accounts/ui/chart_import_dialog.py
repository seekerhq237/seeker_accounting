from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.chart_of_accounts.dto.chart_import_dto import (
    ChartImportPreviewDTO,
    ChartImportResultDTO,
    ChartTemplateProfileDTO,
    ImportChartTemplateCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error


class ChartImportDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._import_result: ChartImportResultDTO | None = None
        self._preview_result: ChartImportPreviewDTO | None = None
        self._built_in_templates: list[ChartTemplateProfileDTO] = []

        super().__init__("Import Chart Template", parent, help_key="dialog.chart_import")
        self.setObjectName("ChartImportDialog")
        self.resize(760, 620)

        intro_label = QLabel(
            "Preview a chart template before import. The default behavior is add-missing-only, so existing account definitions are never overwritten silently.",
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

        self.body_layout.addWidget(self._build_source_section())
        self.body_layout.addWidget(self._build_preview_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Ok
        )

        self._preview_button = self.button_box.button(QDialogButtonBox.StandardButton.Apply)
        if self._preview_button is not None:
            self._preview_button.setText("Preview")
            self._preview_button.setProperty("variant", "secondary")
            self._preview_button.clicked.connect(self._handle_preview)

        self._import_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self._import_button is not None:
            self._import_button.setText("Import Missing Accounts")
            self._import_button.setProperty("variant", "primary")
            self._import_button.clicked.connect(self._handle_import)

        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")

        self._source_kind_combo.currentIndexChanged.connect(self._sync_source_fields)
        self._browse_button.clicked.connect(self._browse_for_file)

        self._load_templates()
        self._sync_source_fields()

    @property
    def import_result(self) -> ChartImportResultDTO | None:
        return self._import_result

    @classmethod
    def import_chart_template(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> ChartImportResultDTO | None:
        dialog = cls(
            service_registry=service_registry,
            company_id=company_id,
            company_name=company_name,
            parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.import_result
        return None

    def _build_source_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Source", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Choose the built-in OHADA template or preview an uploaded CSV/XLSX file before importing missing accounts into the active company chart.",
            card,
        )
        summary.setObjectName("DialogSectionSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._source_kind_combo = QComboBox(card)
        self._source_kind_combo.addItem("Built-In Template", "built_in")
        self._source_kind_combo.addItem("CSV File", "csv")
        self._source_kind_combo.addItem("Excel Workbook", "xlsx")
        grid.addWidget(create_field_block("Source Type", self._source_kind_combo), 0, 0)

        self._built_in_template_combo = QComboBox(card)
        grid.addWidget(create_field_block("Built-In Template", self._built_in_template_combo), 0, 1)

        file_selector = QWidget(card)
        file_selector_layout = QHBoxLayout(file_selector)
        file_selector_layout.setContentsMargins(0, 0, 0, 0)
        file_selector_layout.setSpacing(8)

        self._file_path_edit = QLineEdit(file_selector)
        self._file_path_edit.setPlaceholderText("Choose a .csv or .xlsx chart file")
        file_selector_layout.addWidget(self._file_path_edit, 1)

        self._browse_button = QPushButton("Browse", file_selector)
        self._browse_button.setProperty("variant", "secondary")
        file_selector_layout.addWidget(self._browse_button)

        grid.addWidget(
            create_field_block(
                "File",
                file_selector,
                "Only add-missing-only import is available in this slice.",
            ),
            1,
            0,
            1,
            2,
        )

        layout.addLayout(grid)
        return card

    def _build_preview_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Preview", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Preview shows the import impact before anything is written. Existing accounts stay untouched unless a later explicit overwrite mode is approved.",
            card,
        )
        summary.setObjectName("DialogSectionSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self._preview_text = QPlainTextEdit(card)
        self._preview_text.setReadOnly(True)
        self._preview_text.setFixedHeight(240)
        layout.addWidget(self._preview_text)
        return card

    def _load_templates(self) -> None:
        try:
            self._built_in_templates = self._service_registry.chart_template_import_service.list_built_in_templates()
        except Exception as exc:
            self._set_error(f"Built-in chart templates could not be loaded.\n\n{exc}")
            return

        self._built_in_template_combo.clear()
        for template in self._built_in_templates:
            self._built_in_template_combo.addItem(
                f"{template.display_name}  ({template.row_count} rows)",
                template.template_code,
            )

    def _selected_source_kind(self) -> str:
        value = self._source_kind_combo.currentData()
        return value if isinstance(value, str) else "built_in"

    def _selected_template_code(self) -> str | None:
        value = self._built_in_template_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _sync_source_fields(self) -> None:
        source_kind = self._selected_source_kind()
        is_built_in = source_kind == "built_in"
        self._built_in_template_combo.setEnabled(is_built_in)
        self._file_path_edit.setEnabled(not is_built_in)
        self._browse_button.setEnabled(not is_built_in)

    def _browse_for_file(self) -> None:
        selected_file, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose Chart Template",
            str(Path.cwd()),
            "Chart Files (*.csv *.xlsx);;CSV Files (*.csv);;Excel Files (*.xlsx)",
        )
        if selected_file:
            self._file_path_edit.setText(selected_file)

    def _build_command(self) -> ImportChartTemplateCommand:
        source_kind = self._selected_source_kind()
        if source_kind == "built_in":
            return ImportChartTemplateCommand(
                source_kind="built_in",
                template_code=self._selected_template_code(),
                add_missing_only=True,
            )
        return ImportChartTemplateCommand(
            source_kind=source_kind,
            file_path=self._file_path_edit.text().strip() or None,
            add_missing_only=True,
        )

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return

        self._error_label.setText(message)
        self._error_label.show()

    def _handle_preview(self) -> None:
        self._set_error(None)
        command = self._build_command()

        try:
            self._preview_result = self._service_registry.chart_template_import_service.preview_import(
                self._company_id,
                command,
            )
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Chart Import", str(exc))
            return

        self._preview_text.setPlainText(self._format_preview(self._preview_result))

    def _handle_import(self) -> None:
        self._set_error(None)
        command = self._build_command()

        try:
            self._import_result = self._service_registry.chart_template_import_service.import_add_missing(
                self._company_id,
                command,
            )
        except (ValidationError, ConflictError) as exc:
            self._set_error(str(exc))
            return
        except NotFoundError as exc:
            show_error(self, "Chart Import", str(exc))
            return

        self._preview_text.setPlainText(self._format_import_result(self._import_result))
        self.accept()

    def _format_preview(self, preview: ChartImportPreviewDTO) -> str:
        lines = [
            f"Source: {preview.source_label}",
            f"Template code: {preview.template_code or 'external_import'}",
            f"Source rows: {preview.total_source_rows}",
            f"Normalized rows: {preview.normalized_row_count}",
            f"Importable rows: {preview.importable_count}",
            f"Skipped existing: {preview.skipped_existing_count}",
            f"Conflicts: {preview.conflict_count}",
            f"Duplicate source rows: {preview.duplicate_source_count}",
            f"Invalid rows: {preview.invalid_row_count}",
            "",
            "Mode: Add missing accounts only",
        ]
        if preview.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"- {warning}" for warning in preview.warnings)
        return "\n".join(lines)

    def _format_import_result(self, result: ChartImportResultDTO) -> str:
        lines = [
            f"Source: {result.source_label}",
            f"Template code: {result.template_code or 'external_import'}",
            f"Imported rows: {result.imported_count}",
            f"Skipped existing: {result.skipped_existing_count}",
            f"Conflicts: {result.conflict_count}",
            f"Duplicate source rows: {result.duplicate_source_count}",
            f"Invalid rows: {result.invalid_row_count}",
            "",
            "Mode: Add missing accounts only",
        ]
        if result.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"- {warning}" for warning in result.warnings)
        return "\n".join(lines)
