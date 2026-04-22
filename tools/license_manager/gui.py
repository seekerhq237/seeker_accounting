"""
PySide6 GUI for the Seeker Accounting License Manager.

Standalone desktop tool for issuing, tracking, revoking, verifying,
and exporting Ed25519-signed license keys.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Slot
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .crypto import generate_keypair, sign_license, verify_license
from .ledger import LedgerStore, LicenseRecord

# ══════════════════════════════════════════════════════════════════════════════
#  Constants
# ══════════════════════════════════════════════════════════════════════════════

import sys as _sys

# ── Key path resolution ───────────────────────────────────────────────────────
# The LEDGER (persistent record of issued keys) always lives next to the EXE
# in a 'keys/' sub-folder (or in the project root 'keys/' when running from
# source).  The actual signing keypair (PEM files) may be frozen into the EXE
# itself via PyInstaller datas so they never need to exist on disk externally.

if getattr(_sys, 'frozen', False):
    # Frozen: ledger lives next to the EXE.  Keys live in the _MEIPASS bundle.
    _DEFAULT_KEYS_DIR = Path(_sys.executable).resolve().parent / "keys"
    _FROZEN_KEYS_DIR = Path(_sys._MEIPASS) / "_keys"  # bundled at build time
else:
    # Source: everything lives in the project-root keys/ directory.
    _DEFAULT_KEYS_DIR = Path(__file__).resolve().parent.parent.parent / "keys"
    _FROZEN_KEYS_DIR = None  # not applicable


def _get_signing_key_path(keys_dir: Path, filename: str) -> Path:
    """Return the path to a PEM key file.

    When frozen, PEM files are extracted from the bundle (_MEIPASS).
    When running from source, they live in *keys_dir*.
    """
    if _FROZEN_KEYS_DIR is not None and (_FROZEN_KEYS_DIR / filename).exists():
        return _FROZEN_KEYS_DIR / filename
    return keys_dir / filename
_APP_TITLE = "Seeker License Manager"

_COLUMNS = ["ID", "Customer", "Email", "Edition", "Issued", "Expires", "Status"]
_COL_ID = 0
_COL_CUSTOMER = 1
_COL_EMAIL = 2
_COL_EDITION = 3
_COL_ISSUED = 4
_COL_EXPIRES = 5
_COL_STATUS = 6

_EDITION_MAP = {1: "Standard"}

_STYLESHEET = """
QMainWindow {
    background: #1e1e2e;
}
QToolBar {
    background: #2b2b3c;
    border-bottom: 1px solid #3b3b4f;
    spacing: 6px;
    padding: 4px 8px;
}
QToolBar QToolButton {
    background: transparent;
    color: #cdd6f4;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
}
QToolBar QToolButton:hover {
    background: #3b3b4f;
    border-color: #585b70;
}
QToolBar QToolButton:pressed {
    background: #45475a;
}
QToolBar QLabel {
    color: #a6adc8;
    font-size: 11px;
}
#FilterBar {
    background: #2b2b3c;
    border-bottom: 1px solid #3b3b4f;
    padding: 4px 8px;
}
#FilterBar QLineEdit {
    background: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    min-width: 200px;
}
#FilterBar QLineEdit:focus {
    border-color: #89b4fa;
}
#FilterBar QCheckBox {
    color: #cdd6f4;
    font-size: 12px;
    spacing: 4px;
}
#FilterBar QLabel {
    color: #a6adc8;
    font-size: 11px;
}
QTableWidget {
    background: #1e1e2e;
    alternate-background-color: #232336;
    color: #cdd6f4;
    gridline-color: #3b3b4f;
    border: none;
    font-size: 12px;
    selection-background-color: #45475a;
    selection-color: #cdd6f4;
}
QTableWidget::item {
    padding: 4px 8px;
}
QHeaderView::section {
    background: #2b2b3c;
    color: #a6adc8;
    border: none;
    border-right: 1px solid #3b3b4f;
    border-bottom: 1px solid #3b3b4f;
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
}
QStatusBar {
    background: #2b2b3c;
    color: #a6adc8;
    border-top: 1px solid #3b3b4f;
    font-size: 11px;
    padding: 2px 8px;
}
QDialog {
    background: #1e1e2e;
    color: #cdd6f4;
}
QDialog QLabel {
    color: #cdd6f4;
    font-size: 12px;
}
QDialog QLineEdit, QDialog QPlainTextEdit, QDialog QSpinBox, QDialog QComboBox {
    background: #2b2b3c;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}
QDialog QLineEdit:focus, QDialog QPlainTextEdit:focus, QDialog QSpinBox:focus {
    border-color: #89b4fa;
}
QDialog QGroupBox {
    color: #a6adc8;
    border: 1px solid #3b3b4f;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
}
QDialog QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}
QDialog QPushButton {
    background: #45475a;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 12px;
    min-width: 70px;
}
QDialog QPushButton:hover {
    background: #585b70;
}
QDialog QPushButton:pressed {
    background: #6c7086;
}
QPushButton#PrimaryButton {
    background: #89b4fa;
    color: #1e1e2e;
    border-color: #89b4fa;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover {
    background: #74c7ec;
    border-color: #74c7ec;
}
QPushButton#DangerButton {
    background: #f38ba8;
    color: #1e1e2e;
    border-color: #f38ba8;
    font-weight: 600;
}
QPushButton#DangerButton:hover {
    background: #eba0ac;
    border-color: #eba0ac;
}
QScrollBar:vertical {
    background: #1e1e2e;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _edition_label(edition: int) -> str:
    return _EDITION_MAP.get(edition, f"Edition {edition}")


def _status_label(record: LicenseRecord) -> str:
    today = datetime.date.today()
    if record.status == "revoked":
        return "REVOKED"
    try:
        expires = datetime.date.fromisoformat(record.expires_at)
        if expires < today:
            return "EXPIRED"
    except ValueError:
        pass
    return "ACTIVE"


# ══════════════════════════════════════════════════════════════════════════════
#  Issue License Dialog
# ══════════════════════════════════════════════════════════════════════════════

class IssueDialog(QDialog):
    """Dialog for issuing a new license key."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Issue New License")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        # Customer info
        grp_cust = QGroupBox("Customer")
        gl = QVBoxLayout(grp_cust)
        gl.setSpacing(8)

        self._customer_edit = QLineEdit()
        self._customer_edit.setPlaceholderText("Company or customer name")
        gl.addWidget(QLabel("Name"))
        gl.addWidget(self._customer_edit)

        self._email_edit = QLineEdit()
        self._email_edit.setPlaceholderText("contact@example.com")
        gl.addWidget(QLabel("Email"))
        gl.addWidget(self._email_edit)

        layout.addWidget(grp_cust)

        # License settings
        grp_settings = QGroupBox("License Settings")
        sl = QVBoxLayout(grp_settings)
        sl.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(16)

        self._expiry_spin = QSpinBox()
        self._expiry_spin.setRange(1, 3650)
        self._expiry_spin.setValue(365)
        self._expiry_spin.setSuffix(" days")
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Validity"))
        col1.addWidget(self._expiry_spin)
        row1.addLayout(col1)

        self._edition_combo = QComboBox()
        self._edition_combo.addItem("Standard", 1)
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Edition"))
        col2.addWidget(self._edition_combo)
        row1.addLayout(col2)

        sl.addLayout(row1)
        layout.addWidget(grp_settings)

        # Notes
        grp_notes = QGroupBox("Notes")
        nl = QVBoxLayout(grp_notes)
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setMaximumHeight(60)
        self._notes_edit.setPlaceholderText("Optional internal notes…")
        nl.addWidget(self._notes_edit)
        layout.addWidget(grp_notes)

        # Buttons
        btn_box = QDialogButtonBox()
        self._btn_issue = QPushButton("Issue License")
        self._btn_issue.setObjectName("PrimaryButton")
        btn_cancel = QPushButton("Cancel")
        btn_box.addButton(self._btn_issue, QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton(btn_cancel, QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    @property
    def customer(self) -> str:
        return self._customer_edit.text().strip()

    @property
    def email(self) -> str:
        return self._email_edit.text().strip()

    @property
    def expiry_days(self) -> int:
        return self._expiry_spin.value()

    @property
    def edition(self) -> int:
        return self._edition_combo.currentData()

    @property
    def notes(self) -> str:
        return self._notes_edit.toPlainText().strip()


# ══════════════════════════════════════════════════════════════════════════════
#  License Detail Dialog
# ══════════════════════════════════════════════════════════════════════════════

class DetailDialog(QDialog):
    """Read-only detail view for a single license."""

    def __init__(self, record: LicenseRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"License #{record.id}")
        self.setMinimumWidth(500)
        self._record = record
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        status = _status_label(self._record)
        r = self._record

        # Info grid
        grp = QGroupBox("License Details")
        gl = QVBoxLayout(grp)
        gl.setSpacing(6)

        for label, value in [
            ("ID", str(r.id)),
            ("Customer", r.customer or "—"),
            ("Email", r.email or "—"),
            ("Edition", _edition_label(r.edition)),
            ("Issued", r.issued_at),
            ("Expires", r.expires_at),
            ("Status", status),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(80)
            lbl.setStyleSheet("color: #a6adc8; font-weight: 600;")
            val = QLabel(value)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if label == "Status":
                color = {"ACTIVE": "#a6e3a1", "EXPIRED": "#fab387", "REVOKED": "#f38ba8"}.get(status, "#cdd6f4")
                val.setStyleSheet(f"color: {color}; font-weight: 600;")
            row.addWidget(lbl)
            row.addWidget(val, 1)
            gl.addLayout(row)

        if r.revoked_at:
            row = QHBoxLayout()
            lbl = QLabel("Revoked:")
            lbl.setFixedWidth(80)
            lbl.setStyleSheet("color: #a6adc8; font-weight: 600;")
            row.addWidget(lbl)
            row.addWidget(QLabel(r.revoked_at), 1)
            gl.addLayout(row)

        if r.notes:
            row = QHBoxLayout()
            lbl = QLabel("Notes:")
            lbl.setFixedWidth(80)
            lbl.setStyleSheet("color: #a6adc8; font-weight: 600;")
            row.addWidget(lbl)
            notes_lbl = QLabel(r.notes)
            notes_lbl.setWordWrap(True)
            notes_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(notes_lbl, 1)
            gl.addLayout(row)

        layout.addWidget(grp)

        # Key display
        grp_key = QGroupBox("License Key")
        kl = QVBoxLayout(grp_key)
        self._key_display = QLineEdit(r.key)
        self._key_display.setReadOnly(True)
        self._key_display.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace; font-size: 11px;")
        kl.addWidget(self._key_display)

        btn_copy = QPushButton("Copy Key")
        btn_copy.setObjectName("PrimaryButton")
        btn_copy.setFixedWidth(100)
        btn_copy.clicked.connect(self._copy_key)
        kl.addWidget(btn_copy, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(grp_key)

        # Close
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    @Slot()
    def _copy_key(self) -> None:
        QApplication.clipboard().setText(self._record.key)
        self._key_display.selectAll()


# ══════════════════════════════════════════════════════════════════════════════
#  Verify License Dialog
# ══════════════════════════════════════════════════════════════════════════════

class VerifyDialog(QDialog):
    """Dialog for verifying a license key."""

    def __init__(self, keys_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Verify License Key")
        self.setMinimumWidth(500)
        self._keys_dir = keys_dir
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        layout.addWidget(QLabel("Paste or type a license key to verify:"))

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("SEEKER-...")
        self._key_input.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;")
        layout.addWidget(self._key_input)

        btn_row = QHBoxLayout()
        self._btn_verify = QPushButton("Verify")
        self._btn_verify.setObjectName("PrimaryButton")
        self._btn_verify.clicked.connect(self._on_verify)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_verify)
        layout.addLayout(btn_row)

        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._result_label.setStyleSheet("font-size: 12px; padding: 8px;")
        layout.addWidget(self._result_label)

        layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        self._key_input.returnPressed.connect(self._on_verify)

    @Slot()
    def _on_verify(self) -> None:
        key_string = self._key_input.text().strip()
        if not key_string:
            self._result_label.setStyleSheet("color: #fab387; font-size: 12px; padding: 8px;")
            self._result_label.setText("Please enter a license key.")
            return

        public_key_path = self._keys_dir / "seeker_license_public.pem"
        if not public_key_path.exists():
            self._result_label.setStyleSheet("color: #f38ba8; font-size: 12px; padding: 8px;")
            self._result_label.setText(f"Public key not found at:\n{public_key_path}")
            return

        try:
            payload = verify_license(key_string, public_key_path)
        except ValueError as exc:
            self._result_label.setStyleSheet("color: #f38ba8; font-size: 12px; padding: 8px;")
            self._result_label.setText(f"\u2717  Verification FAILED\n\n{exc}")
            return

        today = datetime.date.today()
        remaining = (payload.expires_at - today).days
        if remaining < 0:
            status_text = f"EXPIRED ({-remaining} day(s) ago)"
            status_color = "#fab387"
        elif remaining == 0:
            status_text = "EXPIRES TODAY"
            status_color = "#fab387"
        else:
            status_text = f"VALID ({remaining} day(s) remaining)"
            status_color = "#a6e3a1"

        self._result_label.setStyleSheet(f"color: {status_color}; font-size: 12px; padding: 8px;")
        self._result_label.setText(
            f"\u2713  Signature verified — key is authentic.\n\n"
            f"Edition : {_edition_label(payload.edition)}\n"
            f"Issued  : {payload.issued_at.isoformat()}\n"
            f"Expires : {payload.expires_at.isoformat()}\n"
            f"Status  : {status_text}"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Notes Dialog
# ══════════════════════════════════════════════════════════════════════════════

class NotesDialog(QDialog):
    """Edit notes on a license record."""

    def __init__(self, record: LicenseRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Notes — License #{record.id}")
        self.setMinimumWidth(400)
        self._build_ui(record)

    def _build_ui(self, record: LicenseRecord) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        layout.addWidget(QLabel(f"License #{record.id} — {record.customer or '(no customer)'}"))

        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setPlainText(record.notes)
        self._notes_edit.setPlaceholderText("Enter notes…")
        self._notes_edit.setMaximumHeight(120)
        layout.addWidget(self._notes_edit)

        btn_box = QDialogButtonBox()
        btn_save = QPushButton("Save")
        btn_save.setObjectName("PrimaryButton")
        btn_cancel = QPushButton("Cancel")
        btn_box.addButton(btn_save, QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton(btn_cancel, QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    @property
    def notes(self) -> str:
        return self._notes_edit.toPlainText().strip()


# ══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ══════════════════════════════════════════════════════════════════════════════

class LicenseManagerWindow(QMainWindow):
    """Main window for the License Manager GUI."""

    def __init__(self, keys_dir: Path | None = None) -> None:
        super().__init__()
        self._keys_dir = (keys_dir or _DEFAULT_KEYS_DIR).resolve()
        self._ledger: LedgerStore | None = None

        self.setWindowTitle(_APP_TITLE)
        self.resize(900, 560)

        self._build_toolbar()
        self._build_filter_bar()
        self._build_table()
        self._build_status_bar()

        self._load_ledger()

    # ── Build UI ──────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Actions")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        self._act_issue = tb.addAction("Issue New")
        self._act_issue.setToolTip("Issue a new license key")
        self._act_issue.triggered.connect(self._on_issue)

        tb.addSeparator()

        self._act_show = tb.addAction("Details")
        self._act_show.setToolTip("Show license details")
        self._act_show.triggered.connect(self._on_show)

        self._act_revoke = tb.addAction("Revoke")
        self._act_revoke.setToolTip("Revoke selected license")
        self._act_revoke.triggered.connect(self._on_revoke)

        self._act_notes = tb.addAction("Notes")
        self._act_notes.setToolTip("Edit notes on selected license")
        self._act_notes.triggered.connect(self._on_notes)

        self._act_export = tb.addAction("Export")
        self._act_export.setToolTip("Export selected license key to .lic file")
        self._act_export.triggered.connect(self._on_export)

        tb.addSeparator()

        self._act_verify = tb.addAction("Verify Key")
        self._act_verify.setToolTip("Verify a license key")
        self._act_verify.triggered.connect(self._on_verify)

        self._act_init_keys = tb.addAction("Init Keys")
        self._act_init_keys.setToolTip("Generate Ed25519 signing keypair")
        self._act_init_keys.triggered.connect(self._on_init_keys)
        # When frozen, the signing key is bundled inside the EXE — keypair
        # generation on disk is meaningless and confusing, so hide the button.
        if getattr(_sys, 'frozen', False):
            self._act_init_keys.setVisible(False)

        tb.addSeparator()

        self._act_refresh = tb.addAction("Refresh")
        self._act_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        self._act_refresh.triggered.connect(self._load_ledger)

        # Keys dir indicator
        spacer = QWidget()
        spacer.setFixedWidth(16)
        tb.addWidget(spacer)
        self._keys_label = QLabel()
        self._keys_label.setStyleSheet("color: #6c7086; font-size: 10px;")
        tb.addWidget(self._keys_label)

        self.addToolBar(tb)

    def _build_filter_bar(self) -> None:
        bar = QWidget()
        bar.setObjectName("FilterBar")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(8, 4, 8, 4)
        hl.setSpacing(12)

        hl.addWidget(QLabel("Search:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter by customer, email, notes…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._apply_filter)
        hl.addWidget(self._search_edit)

        self._active_check = QCheckBox("Active only")
        self._active_check.toggled.connect(self._apply_filter)
        hl.addWidget(self._active_check)

        hl.addStretch()

        # Keys dir button
        btn_dir = QPushButton("Change Keys Dir…")
        btn_dir.setStyleSheet(
            "background: transparent; color: #89b4fa; border: none; font-size: 11px; padding: 2px 6px;"
        )
        btn_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dir.clicked.connect(self._on_change_keys_dir)
        hl.addWidget(btn_dir)

        # Insert filter bar between toolbar and central widget
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        vl.addWidget(bar)

        self._table_container = QWidget()
        self._table_layout = QVBoxLayout(self._table_container)
        self._table_layout.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(self._table_container, 1)

        self.setCentralWidget(container)

    def _build_table(self) -> None:
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(True)

        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(_COL_ID, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_CUSTOMER, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_EMAIL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_EDITION, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_ISSUED, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_EXPIRES, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)

        self._table.doubleClicked.connect(self._on_show)

        self._table_layout.addWidget(self._table)

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    # ── Data loading ──────────────────────────────────────────────────

    @Slot()
    def _load_ledger(self) -> None:
        self._keys_label.setText(f"Keys: {self._keys_dir}")

        try:
            self._ledger = LedgerStore(self._keys_dir)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Ledger Error", str(exc))
            self._ledger = None

        self._apply_filter()

    @Slot()
    def _apply_filter(self) -> None:
        if self._ledger is None:
            self._table.setRowCount(0)
            self._status_bar.showMessage("No ledger loaded")
            return

        query = self._search_edit.text().strip()
        active_only = self._active_check.isChecked()

        if query:
            records = self._ledger.search(query)
        elif active_only:
            records = self._ledger.active_records()
        else:
            records = self._ledger.all_records()

        if active_only and query:
            records = [r for r in records if r.status == "active"]

        self._populate_table(records)

    def _populate_table(self, records: list[LicenseRecord]) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(records))

        today = datetime.date.today()
        total = len(self._ledger.all_records()) if self._ledger else 0

        for row, r in enumerate(records):
            status = _status_label(r)

            id_item = QTableWidgetItem()
            id_item.setData(Qt.ItemDataRole.DisplayRole, r.id)
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_ID, id_item)

            self._table.setItem(row, _COL_CUSTOMER, QTableWidgetItem(r.customer or "—"))
            self._table.setItem(row, _COL_EMAIL, QTableWidgetItem(r.email or "—"))
            self._table.setItem(row, _COL_EDITION, QTableWidgetItem(_edition_label(r.edition)))
            self._table.setItem(row, _COL_ISSUED, QTableWidgetItem(r.issued_at))
            self._table.setItem(row, _COL_EXPIRES, QTableWidgetItem(r.expires_at))

            status_item = QTableWidgetItem(status)
            color = {"ACTIVE": "#a6e3a1", "EXPIRED": "#fab387", "REVOKED": "#f38ba8"}.get(status, "#cdd6f4")
            status_item.setForeground(QColor(color))
            self._table.setItem(row, _COL_STATUS, status_item)

            # Store record id in first column for retrieval
            id_item.setData(Qt.ItemDataRole.UserRole, r.id)

        self._table.setSortingEnabled(True)

        # Stats
        active = sum(1 for r in (self._ledger.all_records() if self._ledger else []) if r.status == "active")
        revoked = total - active
        self._status_bar.showMessage(
            f"  {total} license(s)  |  {active} active  |  {revoked} revoked  |  Showing {len(records)}"
        )

    # ── Selected record helper ────────────────────────────────────────

    def _selected_record(self) -> LicenseRecord | None:
        if self._ledger is None:
            return None
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, _COL_ID)
        if item is None:
            return None
        record_id = item.data(Qt.ItemDataRole.UserRole)
        if record_id is None:
            return None
        return self._ledger.get_by_id(record_id)

    def _require_selection(self) -> LicenseRecord | None:
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, _APP_TITLE, "Select a license first.")
        return record

    # ── Actions ───────────────────────────────────────────────────────

    @Slot()
    def _on_issue(self) -> None:
        private_key_path = _get_signing_key_path(self._keys_dir, "seeker_license_private.pem")
        if not private_key_path.exists():
            QMessageBox.warning(
                self, _APP_TITLE,
                f"Private key not found at:\n{private_key_path}\n\nRun 'Init Keys' first."
            )
            return

        dlg = IssueDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            key_string, issued_date, expires_date = sign_license(
                private_key_path=private_key_path,
                expiry_days=dlg.expiry_days,
                edition=dlg.edition,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Signing Error", f"Failed to sign license:\n{exc}")
            return

        assert self._ledger is not None
        record = self._ledger.add(
            key=key_string,
            customer=dlg.customer,
            email=dlg.email,
            edition=dlg.edition,
            issued_at=issued_date,
            expires_at=expires_date,
            notes=dlg.notes,
        )

        self._apply_filter()

        # Show the issued key
        QApplication.clipboard().setText(record.key)
        QMessageBox.information(
            self, "License Issued",
            f"License #{record.id} issued successfully!\n\n"
            f"Customer: {record.customer or '—'}\n"
            f"Expires: {record.expires_at}\n"
            f"Key length: {len(record.key)} characters\n\n"
            f"The key has been copied to clipboard."
        )

    @Slot()
    def _on_show(self) -> None:
        record = self._require_selection()
        if record is None:
            return
        dlg = DetailDialog(record, self)
        dlg.exec()

    @Slot()
    def _on_revoke(self) -> None:
        record = self._require_selection()
        if record is None:
            return
        if record.status == "revoked":
            QMessageBox.information(self, _APP_TITLE, f"License #{record.id} is already revoked.")
            return

        answer = QMessageBox.question(
            self, "Confirm Revoke",
            f"Revoke license #{record.id}?\n\n"
            f"Customer: {record.customer or '—'}\n"
            f"Email: {record.email or '—'}\n\n"
            "This is a ledger record only. The key will still pass\n"
            "offline validation unless the public key is rotated.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        assert self._ledger is not None
        try:
            self._ledger.revoke(record.id)
        except (KeyError, ValueError) as exc:
            QMessageBox.critical(self, "Revoke Error", str(exc))
            return

        self._apply_filter()

    @Slot()
    def _on_notes(self) -> None:
        record = self._require_selection()
        if record is None:
            return

        dlg = NotesDialog(record, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        assert self._ledger is not None
        try:
            self._ledger.update_notes(record.id, dlg.notes)
        except KeyError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self._apply_filter()

    @Slot()
    def _on_export(self) -> None:
        record = self._require_selection()
        if record is None:
            return

        safe_customer = "".join(
            c if c.isalnum() or c in "-_ " else "" for c in (record.customer or "license")
        ).strip().replace(" ", "_") or "license"
        default_name = f"seeker_license_{record.id}_{safe_customer}.lic"

        path, _ = QFileDialog.getSaveFileName(
            self, "Export License Key", default_name, "License Files (*.lic);;All Files (*)"
        )
        if not path:
            return

        try:
            Path(path).write_text(record.key + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", f"Failed to write file:\n{exc}")
            return

        QMessageBox.information(
            self, "Exported",
            f"License #{record.id} exported to:\n{path}"
        )

    @Slot()
    def _on_verify(self) -> None:
        # Resolve the public key path the same way signing resolves the private key.
        public_key_path = _get_signing_key_path(self._keys_dir, "seeker_license_public.pem")
        dlg = VerifyDialog(public_key_path.parent, self)
        dlg.exec()

    @Slot()
    def _on_init_keys(self) -> None:
        answer = QMessageBox.question(
            self, "Generate Keypair",
            f"Generate a new Ed25519 keypair in:\n{self._keys_dir}\n\n"
            "This is a one-time setup. If keys already exist,\n"
            "the operation will be refused.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            result = generate_keypair(self._keys_dir)
        except FileExistsError as exc:
            QMessageBox.warning(self, "Keys Exist", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to generate keypair:\n{exc}")
            return

        QMessageBox.information(
            self, "Keypair Generated",
            f"Private key: {result.private_key}\n"
            f"Public key: {result.public_key}\n\n"
            f"Public key hex (for key_validator.py):\n{result.public_key_hex}\n\n"
            "IMPORTANT: Keep the private key secure and offline."
        )

    @Slot()
    def _on_change_keys_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Keys Directory", str(self._keys_dir)
        )
        if not path:
            return
        self._keys_dir = Path(path).resolve()
        self._load_ledger()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def run_gui(keys_dir: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(_APP_TITLE)
    app.setStyle("Fusion")
    app.setStyleSheet(_STYLESHEET)

    window = LicenseManagerWindow(keys_dir=keys_dir)
    window.show()

    return app.exec()
