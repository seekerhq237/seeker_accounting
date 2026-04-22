"""BackupRestorePage — export & import .seekerbackup archives."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.administration.ui.backup_import_preview_dialog import (
    BackupImportPreviewDialog,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


# ── Export worker ─────────────────────────────────────────────────────────────

class _ExportWorker(QObject):
    finished = Signal()
    failed = Signal(str)

    def __init__(self, export_fn, password: str, output_path: Path) -> None:
        super().__init__()
        self._export_fn = export_fn
        self._password = password
        self._output_path = output_path

    def run(self) -> None:
        try:
            self._export_fn(self._password, self._output_path)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Analyse worker ────────────────────────────────────────────────────────────

class _AnalyseWorker(QObject):
    finished = Signal(object)   # BackupAnalysisDTO
    failed = Signal(str)

    def __init__(self, analyse_fn, backup_path: Path, password: str) -> None:
        super().__init__()
        self._analyse_fn = analyse_fn
        self._backup_path = backup_path
        self._password = password

    def run(self) -> None:
        try:
            result = self._analyse_fn(self._backup_path, self._password)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Page ──────────────────────────────────────────────────────────────────────

class BackupRestorePage(QWidget):
    """Full-system backup export and merge import.

    Export — encrypts the entire database + assets into a .seekerbackup file.
    Import — decrypts, analyses conflicts, lets the user resolve them, then
              merges all companies beside the existing ones.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._export_thread: QThread | None = None
        self._export_worker: _ExportWorker | None = None
        self._analyse_thread: QThread | None = None
        self._analyse_worker: _AnalyseWorker | None = None

        self.setObjectName("BackupRestorePage")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(20)

        root.addWidget(self._build_page_header())
        root.addWidget(self._build_export_section())
        root.addWidget(self._build_import_section())
        root.addStretch()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_page_header(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        title = QLabel("Backup & Restore")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Export an encrypted backup of all company data, then safely import it on another machine."
        )
        subtitle.setObjectName("PageSummary")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return widget

    # ── Export section ────────────────────────────────────────────────────────

    def _build_export_section(self) -> QGroupBox:
        group = QGroupBox("Export Backup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)

        desc = QLabel(
            "Creates an AES-256-GCM encrypted archive of the entire database and uploaded files. "
            "You will need the password to restore the backup."
        )
        desc.setWordWrap(True)
        desc.setObjectName("PageSummary")
        layout.addWidget(desc)

        # Output path row
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self._export_path_edit = QLineEdit()
        self._export_path_edit.setPlaceholderText("Choose output file…")
        self._export_path_edit.setReadOnly(True)
        path_row.addWidget(QLabel("Output file:"))
        path_row.addWidget(self._export_path_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._choose_export_file)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        # Password row
        pwd_row = QHBoxLayout()
        pwd_row.setSpacing(6)
        self._export_pwd_edit = QLineEdit()
        self._export_pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._export_pwd_edit.setPlaceholderText("Encryption password")
        pwd_row.addWidget(QLabel("Password:"))
        pwd_row.addWidget(self._export_pwd_edit, 1)

        self._export_pwd_confirm_edit = QLineEdit()
        self._export_pwd_confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._export_pwd_confirm_edit.setPlaceholderText("Confirm password")
        pwd_row.addWidget(QLabel("Confirm:"))
        pwd_row.addWidget(self._export_pwd_confirm_edit, 1)
        layout.addLayout(pwd_row)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch()
        self._export_status_label = QLabel("")
        self._export_status_label.setObjectName("PageSummary")
        action_row.addWidget(self._export_status_label)
        self._export_btn = QPushButton("Export Backup")
        self._export_btn.setProperty("variant", "primary")
        self._export_btn.clicked.connect(self._start_export)
        action_row.addWidget(self._export_btn)
        layout.addLayout(action_row)

        self._check_export_permission(group)
        return group

    def _check_export_permission(self, group: QGroupBox) -> None:
        if not self._service_registry.permission_service.has_permission(
            "administration.backup.export"
        ):
            group.setEnabled(False)
            group.setToolTip("You do not have permission to export backups.")

    # ── Import section ────────────────────────────────────────────────────────

    def _build_import_section(self) -> QGroupBox:
        group = QGroupBox("Import Backup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)

        desc = QLabel(
            "Import a .seekerbackup file. Companies and users in the archive will be merged "
            "alongside the existing data on this machine. You will be shown a conflict summary "
            "before anything is written."
        )
        desc.setWordWrap(True)
        desc.setObjectName("PageSummary")
        layout.addWidget(desc)

        # File path row
        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self._import_path_edit = QLineEdit()
        self._import_path_edit.setPlaceholderText("Select .seekerbackup file…")
        self._import_path_edit.setReadOnly(True)
        file_row.addWidget(QLabel("File:"))
        file_row.addWidget(self._import_path_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._choose_import_file)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # Password row
        pwd_row = QHBoxLayout()
        pwd_row.setSpacing(6)
        self._import_pwd_edit = QLineEdit()
        self._import_pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._import_pwd_edit.setPlaceholderText("Backup password")
        pwd_row.addWidget(QLabel("Password:"))
        pwd_row.addWidget(self._import_pwd_edit, 1)
        pwd_row.addStretch()
        layout.addLayout(pwd_row)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch()
        self._import_status_label = QLabel("")
        self._import_status_label.setObjectName("PageSummary")
        action_row.addWidget(self._import_status_label)
        self._analyse_btn = QPushButton("Analyse Backup")
        self._analyse_btn.setProperty("variant", "primary")
        self._analyse_btn.clicked.connect(self._start_analyse)
        action_row.addWidget(self._analyse_btn)
        layout.addLayout(action_row)

        self._check_import_permission(group)
        return group

    def _check_import_permission(self, group: QGroupBox) -> None:
        if not self._service_registry.permission_service.has_permission(
            "administration.backup.import"
        ):
            group.setEnabled(False)
            group.setToolTip("You do not have permission to import backups.")

    # ── File choosers ─────────────────────────────────────────────────────────

    def _choose_export_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Backup File",
            "",
            "Seeker Backup (*.seekerbackup);;All files (*)",
        )
        if path:
            if not path.endswith(".seekerbackup"):
                path += ".seekerbackup"
            self._export_path_edit.setText(path)

    def _choose_import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Backup File",
            "",
            "Seeker Backup (*.seekerbackup);;All files (*)",
        )
        if path:
            self._import_path_edit.setText(path)

    # ── Export flow ───────────────────────────────────────────────────────────

    def _start_export(self) -> None:
        output_path_str = self._export_path_edit.text().strip()
        password = self._export_pwd_edit.text()
        confirm = self._export_pwd_confirm_edit.text()

        if not output_path_str:
            show_error(self, "Export", "Please choose an output file first.")
            return
        if not password:
            show_error(self, "Export", "Please enter an encryption password.")
            return
        if password != confirm:
            show_error(self, "Export", "Passwords do not match.")
            return

        output_path = Path(output_path_str)
        self._export_btn.setEnabled(False)
        self._export_status_label.setText("Exporting…")

        export_service = self._service_registry.backup_export_service
        worker = _ExportWorker(export_service.export, password, output_path)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_export_finished)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)

        self._export_thread = thread
        self._export_worker = worker
        thread.start()

    def _on_export_finished(self) -> None:
        self._export_btn.setEnabled(True)
        self._export_status_label.setText("")
        path = self._export_path_edit.text()
        show_info(self, "Export Complete", f"Backup exported successfully.\n\n{path}")
        self._export_pwd_edit.clear()
        self._export_pwd_confirm_edit.clear()

    def _on_export_failed(self, error_msg: str) -> None:
        self._export_btn.setEnabled(True)
        self._export_status_label.setText("")
        show_error(self, "Export Failed", f"The backup could not be created:\n\n{error_msg}")

    # ── Import / analyse flow ─────────────────────────────────────────────────

    def _start_analyse(self) -> None:
        backup_path_str = self._import_path_edit.text().strip()
        password = self._import_pwd_edit.text()

        if not backup_path_str:
            show_error(self, "Import", "Please select a .seekerbackup file first.")
            return
        if not password:
            show_error(self, "Import", "Please enter the backup password.")
            return

        backup_path = Path(backup_path_str)
        if not backup_path.exists():
            show_error(self, "Import", "The selected file does not exist.")
            return

        self._analyse_btn.setEnabled(False)
        self._import_status_label.setText("Analysing…")

        analysis_service = self._service_registry.backup_analysis_service
        worker = _AnalyseWorker(analysis_service.analyse, backup_path, password)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_analyse_finished)
        worker.failed.connect(self._on_analyse_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)

        self._analyse_thread = thread
        self._analyse_worker = worker
        self._pending_password = password
        self._pending_backup_path = backup_path
        thread.start()

    def _on_analyse_finished(self, analysis) -> None:
        self._analyse_btn.setEnabled(True)
        self._import_status_label.setText("")
        merge_service = self._service_registry.backup_merge_service
        dlg = BackupImportPreviewDialog(
            analysis=analysis,
            backup_path=self._pending_backup_path,
            password=self._pending_password,
            merge_fn=merge_service.apply_merge,
            parent=self,
        )
        dlg.exec()
        self._import_pwd_edit.clear()

    def _on_analyse_failed(self, error_msg: str) -> None:
        self._analyse_btn.setEnabled(True)
        self._import_status_label.setText("")
        show_error(self, "Analysis Failed", f"Could not read the backup file:\n\n{error_msg}")
