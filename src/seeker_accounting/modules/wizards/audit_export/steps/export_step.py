"""Step 3 — Export: writes the package and shows the result summary."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.audit.dto.audit_export_dto import AuditExportResultDTO
from seeker_accounting.modules.wizards.audit_export import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.styles.palette import LIGHT_PALETTE as _P


class ExportStep(WizardStep):
    key = "export"
    title = "Write export package"
    subtitle = "Generate the CSV files and manifest in the chosen folder."

    def __init__(self) -> None:
        super().__init__()
        self._status: QLabel | None = None
        self._files_container: QVBoxLayout | None = None
        self._open_button: QPushButton | None = None
        self._context: WizardContext | None = None
        self._state: WizardState | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._status = QLabel(root)
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._status)

        button_row = QHBoxLayout()
        run_button = QPushButton("Run export now", root)
        run_button.clicked.connect(self._on_run_clicked)
        button_row.addWidget(run_button)
        self._open_button = QPushButton("Open output folder", root)
        self._open_button.setEnabled(False)
        self._open_button.clicked.connect(self._on_open_folder)
        button_row.addWidget(self._open_button)
        button_row.addStretch(1)
        outer.addLayout(button_row)

        scroll = QScrollArea(root)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        files_widget = QWidget(scroll)
        self._files_container = QVBoxLayout(files_widget)
        self._files_container.setContentsMargins(0, 0, 0, 0)
        self._files_container.setSpacing(4)
        self._files_container.addStretch(1)
        scroll.setWidget(files_widget)
        outer.addWidget(scroll, 1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        self._context = context
        self._state = state
        if self._status is not None:
            self._status.setText(
                "Click <b>Run export now</b> to write the package. The wizard "
                "will not auto-run so you can review the preview first."
            )
        self._clear_files()
        if self._open_button is not None:
            self._open_button.setEnabled(False)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_RESULT), AuditExportResultDTO):
            return StepValidationResult.fail(
                "Run the export before finishing — the package has not been written yet."
            )
        return StepValidationResult.ok()

    # -------------------------------------------------------------- #

    def _on_run_clicked(self) -> None:
        if self._context is None or self._state is None:
            return
        from_d = self._state.get(K.KEY_FROM_DATE)
        to_d = self._state.get(K.KEY_TO_DATE)
        out_dir = self._state.get(K.KEY_OUTPUT_DIR)
        include_events = bool(self._state.get(K.KEY_INCLUDE_AUDIT_EVENTS, True))
        if not (
            isinstance(from_d, date)
            and isinstance(to_d, date)
            and isinstance(out_dir, str)
            and out_dir
        ):
            if self._status is not None:
                self._status.setText("Cannot run — setup values are missing.")
            return
        company_id = self._context.require_company_id()
        if self._status is not None:
            self._status.setText("Writing export package…")
        try:
            result = self._context.service_registry.audit_export_service.export(
                company_id,
                from_d,
                to_d,
                out_dir,
                include_audit_events=include_events,
            )
        except Exception as exc:  # noqa: BLE001
            if self._status is not None:
                self._status.setText(
                    f"<span style='color:{_P.status_danger_fg};'>Export failed:</span> {exc}"
                )
            return

        self._state[K.KEY_RESULT] = result
        self._render_result(result)
        if self._open_button is not None:
            self._open_button.setEnabled(True)

    def _on_open_folder(self) -> None:
        if self._state is None:
            return
        result = self._state.get(K.KEY_RESULT)
        if not isinstance(result, AuditExportResultDTO):
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(result.output_directory))

    def _render_result(self, result: AuditExportResultDTO) -> None:
        if self._status is not None:
            self._status.setText(
                f"<b>Export complete.</b><br>"
                f"Folder: {result.output_directory}<br>"
                f"Posted journal entries: {result.posted_journal_entry_count:,} · "
                f"lines: {result.posted_journal_line_count:,} · "
                f"audit events: {result.audit_event_count:,}"
            )
        self._clear_files()
        if self._files_container is None:
            return
        for f in result.files:
            row = QLabel(
                f"• <b>{f.relative_name}</b> — {f.row_count:,} rows, "
                f"{_fmt_bytes(f.byte_size)}"
            )
            row.setTextFormat(Qt.TextFormat.RichText)
            self._files_container.insertWidget(self._files_container.count() - 1, row)

    def _clear_files(self) -> None:
        if self._files_container is None:
            return
        while self._files_container.count() > 1:
            item = self._files_container.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()


def _fmt_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"
