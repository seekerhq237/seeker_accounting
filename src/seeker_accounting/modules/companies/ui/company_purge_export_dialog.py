from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CompanyPurgeExportDialog(QDialog):
    """Checkpoint dialog shown before permanently deleting a company's data.

    The user must explicitly choose between exporting data or skipping export.
    The dialog cannot be dismissed via the window close button — every path
    results in deletion proceeding.
    """

    def __init__(self, company_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._company_name = company_name
        self.setWindowTitle("Permanent Data Deletion")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setFixedSize(500, 240)
        self.setModal(True)
        self._build_ui()

    # ── Public factory ────────────────────────────────────────────────────────

    @classmethod
    def confirm(cls, company_name: str, parent: QWidget | None = None) -> None:
        """Show the dialog and block until the user selects an action."""
        dlg = cls(company_name, parent)
        dlg.exec()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        icon_label = QLabel("⚠")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 32px; color: #D97706;")
        root.addWidget(icon_label)

        heading = QLabel(f"Permanently deleting: <b>{self._company_name}</b>")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setWordWrap(True)
        heading.setStyleSheet("font-size: 14px; color: #1F2937;")
        root.addWidget(heading)

        body = QLabel(
            "The 30-day retention window has expired. All data for this company will "
            "be permanently removed. Would you like to export the data first?"
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        body.setStyleSheet("font-size: 12px; color: #6B7280;")
        root.addWidget(body)

        root.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        export_btn = QPushButton("Export Data")
        export_btn.setFixedHeight(36)
        export_btn.setStyleSheet(
            "QPushButton { background: #3B82F6; color: #fff; border: none; "
            "border-radius: 4px; font-size: 13px; padding: 0 20px; }"
            "QPushButton:hover { background: #2563EB; }"
        )
        export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(export_btn)

        delete_btn = QPushButton("Delete Without Export")
        delete_btn.setFixedHeight(36)
        delete_btn.setStyleSheet(
            "QPushButton { background: #EF4444; color: #fff; border: none; "
            "border-radius: 4px; font-size: 13px; padding: 0 20px; }"
            "QPushButton:hover { background: #DC2626; }"
        )
        delete_btn.clicked.connect(self.accept)
        btn_row.addWidget(delete_btn)

        root.addLayout(btn_row)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_export(self) -> None:
        QMessageBox.information(
            self,
            "Export Data",
            "Data export is not yet available in this version.\n\n"
            "This feature is coming soon. The company data will be permanently deleted now.",
        )
        self.accept()

    # ── Prevent dismissal without a choice ────────────────────────────────────

    def closeEvent(self, event):  # noqa: N802
        # Treat window close the same as "Delete Without Export"
        self.accept()
        event.accept()

    def reject(self) -> None:
        # Escape key / system close → accept (proceed with deletion)
        self.accept()
