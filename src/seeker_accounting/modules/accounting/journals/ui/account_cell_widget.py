"""AccountCellWidget — compound account-selection cell for the journal entry grid.

Layout per cell: [ … pick-btn ] [ account-code QLineEdit ]

The account *name* is displayed in a separate adjacent read-only model column
managed by the grid.  This widget is responsible only for code input and
picker-dialog launch.

Confirmed account data is broadcast via ``account_confirmed(account_id, code, name)``.
``account_id == 0`` means no valid account is set (code not found or cleared).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountLookupDTO
from seeker_accounting.modules.accounting.journals.ui.account_picker_dialog import AccountPickerDialog


class AccountCellWidget(QWidget):
    """Compound in-cell widget: a browse button plus an account-code field.

    Signals
    -------
    account_confirmed(account_id: int, code: str, name: str)
        Emitted when the user confirms an account (via code entry or picker).
        ``account_id == 0`` when the typed code is not found in the chart.
    """

    account_confirmed = Signal(int, str, str)

    def __init__(
        self,
        accounts_by_code: dict[str, tuple[int, str]],
        account_options: list[AccountLookupDTO],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._accounts_by_code = accounts_by_code
        self._account_options = account_options
        self._current_account_id: int = 0
        self._read_only = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(2)

        # ── Picker button ─────────────────────────────────────────────
        self._pick_btn = QPushButton("…", self)
        self._pick_btn.setFixedSize(22, 22)
        self._pick_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pick_btn.setToolTip("Browse and select account")
        self._pick_btn.setObjectName("AccountPickButton")
        self._pick_btn.clicked.connect(self._open_picker)
        layout.addWidget(self._pick_btn)

        # ── Code field ────────────────────────────────────────────────
        self._code_edit = QLineEdit(self)
        self._code_edit.setPlaceholderText("Code")
        self._code_edit.setMaxLength(20)
        layout.addWidget(self._code_edit, 1)

        self._code_edit.editingFinished.connect(self._on_code_committed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def code_edit(self) -> QLineEdit:
        """Expose the inner QLineEdit for event-filter installation and focus."""
        return self._code_edit

    def set_account(
        self,
        account_id: int,
        code: str,
        name: str,
        *,
        emit: bool = True,
    ) -> None:
        """Populate the widget with a known account.  Pass ``emit=False`` during
        initial row population to avoid spurious model writes."""
        self._current_account_id = account_id
        self._code_edit.blockSignals(True)
        self._code_edit.setText(code)
        self._code_edit.blockSignals(False)
        # valid = account found OR field intentionally blank
        self._set_valid_style(account_id > 0 or not code)
        if emit:
            self.account_confirmed.emit(account_id, code, name)

    def current_account_id(self) -> int:
        return self._current_account_id

    def set_read_only(self, read_only: bool) -> None:
        self._read_only = read_only
        self._code_edit.setReadOnly(read_only)
        self._pick_btn.setEnabled(not read_only)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_valid_style(self, valid: bool) -> None:
        if valid:
            self._code_edit.setStyleSheet("")
        else:
            self._code_edit.setStyleSheet(
                "QLineEdit { border: 1px solid #E53E3E; background: #FFF5F5; }"
            )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_code_committed(self) -> None:
        """Called when the code field loses focus or the user presses Return."""
        if self._read_only:
            return

        code = self._code_edit.text().strip().upper()

        if not code:
            self._current_account_id = 0
            self._set_valid_style(True)
            self.account_confirmed.emit(0, "", "")
            return

        # Normalise to uppercase in-place
        self._code_edit.blockSignals(True)
        self._code_edit.setText(code)
        self._code_edit.blockSignals(False)

        match = self._accounts_by_code.get(code)
        if match:
            account_id, name = match
            self._current_account_id = account_id
            self._set_valid_style(True)
            self.account_confirmed.emit(account_id, code, name)
        else:
            self._current_account_id = 0
            self._set_valid_style(False)
            self.account_confirmed.emit(0, code, "")

    def _open_picker(self) -> None:
        if self._read_only:
            return
        result = AccountPickerDialog.pick_account(
            account_options=self._account_options,
            parent=self.window(),
        )
        if result is not None:
            account_id, code, name = result
            self._current_account_id = account_id
            self._code_edit.blockSignals(True)
            self._code_edit.setText(code)
            self._code_edit.blockSignals(False)
            self._set_valid_style(True)
            self.account_confirmed.emit(account_id, code, name)
