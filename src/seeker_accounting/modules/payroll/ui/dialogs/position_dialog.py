from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_setup_commands import (
    CreatePositionCommand,
    PositionDTO,
    UpdatePositionCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_COL_CODE = 0
_COL_NAME = 1
_COL_STATUS = 2


class _PositionFormDialog(QDialog):
    """Simple create / edit form for a single position."""

    def __init__(
        self,
        pos: PositionDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        is_edit = pos is not None
        self.setWindowTitle("Edit Position" if is_edit else "New Position")
        self.setModal(True)
        self.resize(380, 220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        card = QFrame(self)
        card.setObjectName("PageCard")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)
        hdr = QLabel("Position", card)
        hdr.setObjectName("CardTitle")
        form.addRow(hdr)

        self._code_input = QLineEdit(card)
        self._code_input.setPlaceholderText("e.g. MGR")
        self._code_input.setMaxLength(20)
        form.addRow("Code *", self._code_input)

        self._name_input = QLineEdit(card)
        self._name_input.setPlaceholderText("Position title")
        self._name_input.setMaxLength(100)
        form.addRow("Name *", self._name_input)

        if is_edit:
            self._active_cb = QCheckBox("Active", card)
            self._active_cb.setChecked(True)
            form.addRow("Status", self._active_cb)

        layout.addWidget(card)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if is_edit and pos is not None:
            self._code_input.setText(pos.code)
            self._name_input.setText(pos.name)
            if hasattr(self, "_active_cb"):
                self._active_cb.setChecked(pos.is_active)

    def _validate_and_accept(self) -> None:
        self._error_label.hide()
        if not self._code_input.text().strip():
            self._error_label.setText("Code is required.")
            self._error_label.show()
            return
        if not self._name_input.text().strip():
            self._error_label.setText("Name is required.")
            self._error_label.show()
            return
        self.accept()

    @property
    def code(self) -> str:
        return self._code_input.text().strip()

    @property
    def name(self) -> str:
        return self._name_input.text().strip()

    @property
    def is_active(self) -> bool:
        return self._active_cb.isChecked() if hasattr(self, "_active_cb") else True


class PositionManagementDialog(QDialog):
    """List-and-edit dialog for company job positions."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._company_id = company_id

        self.setWindowTitle(f"Manage Positions — {company_name}")
        self.setModal(True)
        self.resize(580, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        self._show_inactive_cb = QCheckBox("Show inactive", self)
        self._show_inactive_cb.stateChanged.connect(self._reload)
        toolbar.addWidget(self._show_inactive_cb)
        toolbar.addStretch()

        self._new_btn = QPushButton("New Position", self)
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.clicked.connect(self._on_new)
        toolbar.addWidget(self._new_btn)

        self._edit_btn = QPushButton("Edit", self)
        self._edit_btn.clicked.connect(self._on_edit)
        toolbar.addWidget(self._edit_btn)

        self._toggle_btn = QPushButton("Toggle Active", self)
        self._toggle_btn.clicked.connect(self._on_toggle_active)
        toolbar.addWidget(self._toggle_btn)

        layout.addLayout(toolbar)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(self)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(("Code", "Title", "Status"))
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(lambda _: self._on_edit())
        configure_compact_table(self._table)
        layout.addWidget(self._table, 1)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_btn.rejected.connect(self.accept)
        layout.addWidget(close_btn)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.position", dialog=True)

        self._reload()

    # ── Data ──────────────────────────────────────────────────────────────────

    def _reload(self) -> None:
        self._error_label.hide()
        active_only = not self._show_inactive_cb.isChecked()
        try:
            rows = self._sr.payroll_setup_service.list_positions(
                self._company_id, active_only=active_only
            )
        except Exception as exc:
            show_error(self, "Positions", str(exc))
            return
        self._populate(rows)

    def _populate(self, rows: list[PositionDTO]) -> None:
        self._table.setRowCount(0)
        for row in rows:
            ri = self._table.rowCount()
            self._table.insertRow(ri)
            code_item = QTableWidgetItem(row.code)
            code_item.setData(Qt.ItemDataRole.UserRole, row.id)
            self._table.setItem(ri, _COL_CODE, code_item)
            self._table.setItem(ri, _COL_NAME, QTableWidgetItem(row.name))
            self._table.setItem(ri, _COL_STATUS, QTableWidgetItem(
                "Active" if row.is_active else "Inactive"
            ))
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)

    def _selected_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, _COL_CODE)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_dto(self) -> PositionDTO | None:
        pos_id = self._selected_id()
        if pos_id is None:
            return None
        try:
            return self._sr.payroll_setup_service.get_position(self._company_id, pos_id)
        except NotFoundError:
            return None

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_new(self) -> None:
        self._error_label.hide()
        sub = _PositionFormDialog(parent=self)
        if sub.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._sr.payroll_setup_service.create_position(
                self._company_id,
                CreatePositionCommand(code=sub.code, name=sub.name),
            )
        except (ValidationError, ConflictError) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        self._reload()

    def _on_edit(self) -> None:
        self._error_label.hide()
        pos = self._selected_dto()
        if pos is None:
            return
        sub = _PositionFormDialog(pos=pos, parent=self)
        if sub.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._sr.payroll_setup_service.update_position(
                self._company_id,
                pos.id,
                UpdatePositionCommand(
                    code=sub.code,
                    name=sub.name,
                    is_active=sub.is_active,
                ),
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        self._reload()

    def _on_toggle_active(self) -> None:
        self._error_label.hide()
        pos = self._selected_dto()
        if pos is None:
            return
        new_active = not pos.is_active
        label = "Activate" if new_active else "Deactivate"
        reply = QMessageBox.question(
            self,
            f"{label} Position",
            f"{label} position '{pos.code} — {pos.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._sr.payroll_setup_service.update_position(
                self._company_id,
                pos.id,
                UpdatePositionCommand(
                    code=pos.code,
                    name=pos.name,
                    is_active=new_active,
                ),
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        self._reload()
