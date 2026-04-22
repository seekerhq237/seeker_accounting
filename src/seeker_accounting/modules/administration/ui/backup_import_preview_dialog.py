"""BackupImportPreviewDialog — shows conflict summary and lets the user
resolve names before confirming the merge import.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.administration.dto.backup_dto import (
    BackupAnalysisDTO,
    CompanyImportItem,
    MergeDecisionDTO,
    MergeResultDTO,
    UserImportItem,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


# ── Worker ────────────────────────────────────────────────────────────────────

class _MergeWorker(QObject):
    finished = Signal(object)   # MergeResultDTO
    failed = Signal(str)

    def __init__(
        self,
        backup_path: Path,
        password: str,
        decision: MergeDecisionDTO,
        merge_fn: Callable,
    ) -> None:
        super().__init__()
        self._backup_path = backup_path
        self._password = password
        self._decision = decision
        self._merge_fn = merge_fn

    def run(self) -> None:
        try:
            result = self._merge_fn(self._backup_path, self._password, self._decision)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Dialog ────────────────────────────────────────────────────────────────────

class BackupImportPreviewDialog(QDialog):
    """Shows analysis results and collects conflict-resolution decisions
    before performing the actual merge."""

    import_completed = Signal()

    def __init__(
        self,
        analysis: BackupAnalysisDTO,
        backup_path: Path,
        password: str,
        merge_fn: Callable,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._analysis = analysis
        self._backup_path = backup_path
        self._password = password
        self._merge_fn = merge_fn
        self._thread: QThread | None = None
        self._worker: _MergeWorker | None = None

        self.setWindowTitle("Import Backup — Review & Confirm")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(820, 620)
        self.setMinimumSize(640, 480)
        self.setModal(True)
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet("background:#1E3A5F;")
        hr = QHBoxLayout(header)
        hr.setContentsMargins(20, 0, 20, 0)
        title = QLabel("Import Backup — Review Conflicts")
        title.setStyleSheet("font-size:14px;font-weight:600;color:#F9FAFB;")
        hr.addWidget(title)
        hr.addStretch()
        meta_lbl = QLabel(
            f"Exported: {self._analysis.manifest.export_date[:10]}  |  "
            f"Version: {self._analysis.manifest.app_version}"
        )
        meta_lbl.setStyleSheet("font-size:11px;color:#93C5FD;")
        hr.addWidget(meta_lbl)
        root.addWidget(header)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(16)

        # Summary counts
        summary_group = QGroupBox("Backup Contents (Row Counts)")
        sg_layout = QHBoxLayout(summary_group)
        sg_layout.setContentsMargins(12, 8, 12, 8)
        sg_layout.setSpacing(24)
        for key in ["companies", "users", "journal_entries", "fiscal_periods",
                    "customers", "suppliers", "sales_invoices", "employees"]:
            count = self._analysis.record_summary.get(key, 0)
            sg_layout.addWidget(self._mini_stat(key.replace("_", " ").title(), str(count)))
        sg_layout.addStretch()
        body_layout.addWidget(summary_group)

        # Companies table
        body_layout.addWidget(QLabel("<b>Companies to Import</b>"))
        self._company_table = self._build_company_table()
        body_layout.addWidget(self._company_table)

        # Users table
        body_layout.addWidget(QLabel("<b>Users to Import</b>"))
        self._user_table = self._build_user_table()
        body_layout.addWidget(self._user_table)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Status / progress area
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size:11px;color:#6B7280;padding:4px 20px;")
        root.addWidget(self._status_label)

        # Footer buttons
        footer = QWidget()
        footer.setStyleSheet("border-top:1px solid #E5E7EB;")
        fr = QHBoxLayout(footer)
        fr.setContentsMargins(20, 10, 20, 10)
        fr.setSpacing(10)
        fr.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        fr.addWidget(self._cancel_btn)

        self._confirm_btn = QPushButton("Confirm Import")
        self._confirm_btn.setStyleSheet(
            "background:#1E3A5F;color:white;padding:6px 18px;"
            "border-radius:4px;font-weight:600;"
        )
        self._confirm_btn.clicked.connect(self._start_import)
        fr.addWidget(self._confirm_btn)

        root.addWidget(footer)

    @staticmethod
    def _mini_stat(label: str, value: str) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet("font-size:18px;font-weight:700;color:#1E3A5F;")
        lbl_lbl = QLabel(label)
        lbl_lbl.setStyleSheet("font-size:10px;color:#6B7280;")
        l.addWidget(val_lbl)
        l.addWidget(lbl_lbl)
        return w

    def _build_company_table(self) -> QTableWidget:
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Original Legal Name", "Display Name", "Conflict", "Import As (Legal Name)"])
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setAlternatingRowColors(True)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)
        from PySide6.QtWidgets import QHeaderView
        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(2, 80)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self._company_name_edits: dict[int, QLineEdit] = {}

        for row_idx, item in enumerate(self._analysis.companies):
            tbl.insertRow(row_idx)
            tbl.setItem(row_idx, 0, QTableWidgetItem(item.legal_name))
            tbl.setItem(row_idx, 1, QTableWidgetItem(item.display_name))
            conflict_item = QTableWidgetItem("⚠ Yes" if item.conflict else "✓ No")
            conflict_item.setForeground(
                Qt.GlobalColor.red if item.conflict else Qt.GlobalColor.darkGreen
            )
            tbl.setItem(row_idx, 2, conflict_item)

            edit = QLineEdit(item.resolved_name)
            edit.setProperty("src_id", item.src_id)
            tbl.setCellWidget(row_idx, 3, edit)
            self._company_name_edits[item.src_id] = edit

        tbl.setFixedHeight(min(28 * len(self._analysis.companies) + 28, 180))
        return tbl

    def _build_user_table(self) -> QTableWidget:
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Display Name", "Original Username", "Conflict", "Import As (Username)"])
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setAlternatingRowColors(True)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)
        from PySide6.QtWidgets import QHeaderView
        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(2, 80)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self._user_name_edits: dict[int, QLineEdit] = {}

        for row_idx, item in enumerate(self._analysis.users):
            tbl.insertRow(row_idx)
            tbl.setItem(row_idx, 0, QTableWidgetItem(item.display_name))
            tbl.setItem(row_idx, 1, QTableWidgetItem(item.username))
            conflict_item = QTableWidgetItem("⚠ Yes" if item.conflict else "✓ No")
            conflict_item.setForeground(
                Qt.GlobalColor.red if item.conflict else Qt.GlobalColor.darkGreen
            )
            tbl.setItem(row_idx, 2, conflict_item)

            edit = QLineEdit(item.resolved_username)
            edit.setProperty("src_id", item.src_id)
            tbl.setCellWidget(row_idx, 3, edit)
            self._user_name_edits[item.src_id] = edit

        tbl.setFixedHeight(min(28 * len(self._analysis.users) + 28, 200))
        return tbl

    # ── Import execution ──────────────────────────────────────────────────────

    def _collect_decision(self) -> MergeDecisionDTO | None:
        """Validate edits and build a MergeDecisionDTO.  Returns None if invalid."""
        decision = MergeDecisionDTO()

        # Companies
        seen_legal: set[str] = set()
        for src_id, edit in self._company_name_edits.items():
            name = edit.text().strip()
            if not name:
                show_error(self, "Validation", "Company name must not be empty.")
                return None
            if name.lower() in seen_legal:
                show_error(self, "Validation", f"Duplicate company name: '{name}'.")
                return None
            seen_legal.add(name.lower())
            # Find original display_name for this src_id
            display = next(
                (c.display_name for c in self._analysis.companies if c.src_id == src_id),
                name,
            )
            decision.company_names[src_id] = (name, display)

        # Users
        seen_users: set[str] = set()
        for src_id, edit in self._user_name_edits.items():
            username = edit.text().strip()
            if not username:
                show_error(self, "Validation", "Username must not be empty.")
                return None
            if username.lower() in seen_users:
                show_error(self, "Validation", f"Duplicate username: '{username}'.")
                return None
            seen_users.add(username.lower())
            decision.user_names[src_id] = username

        return decision

    def _start_import(self) -> None:
        decision = self._collect_decision()
        if decision is None:
            return

        self._confirm_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._status_label.setText("Importing… please wait.")

        worker = _MergeWorker(self._backup_path, self._password, decision, self._merge_fn)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_import_finished)
        worker.failed.connect(self._on_import_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_import_finished(self, result: MergeResultDTO) -> None:
        msg = (
            f"Import complete.\n\n"
            f"Companies imported: {result.companies_imported}\n"
            f"Users imported: {result.users_imported}\n"
            f"Tables processed: {result.tables_processed}"
        )
        if result.warnings:
            msg += "\n\nWarnings:\n" + "\n".join(f"• {w}" for w in result.warnings)
        show_info(self, "Import Complete", msg)
        self.import_completed.emit()
        self.accept()

    def _on_import_failed(self, error_msg: str) -> None:
        self._confirm_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._status_label.setText("")
        show_error(self, "Import Failed", f"The import could not be completed:\n\n{error_msg}")
