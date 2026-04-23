"""
JournalEntryWindow — top-level child window for creating/editing a single
journal entry.

The window embeds the existing :class:`JournalEntryDialog` body as its
content widget (running in *embedded mode* — button box hidden, modal
flag cleared) and paints the ``child:journal_entry`` ribbon surface on
top. All save / post / close actions route through the ribbon; the
dialog's own button box is never shown here.

Architecture note: we intentionally embed the dialog rather than
refactoring its body into a separate widget. The dialog's controls,
validation, guided-resolution coordinator, and save paths are already
correct — wrapping them keeps Slice 1 scope minimal while still
delivering the independent top-level window UX.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.child_windows.child_window_base import (
    ChildWindowBase,
)
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.modules.accounting.journals.dto.journal_dto import (
    JournalEntryDetailDTO,
)
from seeker_accounting.modules.accounting.journals.ui.journal_entry_dialog import (
    JournalEntryDialog,
)
from seeker_accounting.shared.ui.icon_provider import IconProvider


class JournalEntryWindow(ChildWindowBase):
    """Independent top-level window wrapping :class:`JournalEntryDialog`."""

    DOC_TYPE = "journal_entry"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        company_name: str,
        journal_entry_id: int | None,
        icon_provider: IconProvider | None = None,
        parent: QWidget | None = None,
    ) -> None:
        registry = service_registry.ribbon_registry or RibbonRegistry()
        provider = icon_provider or IconProvider(service_registry.theme_manager)
        entity_key: object = journal_entry_id if journal_entry_id is not None else "new"
        title = (
            "New Journal Entry"
            if journal_entry_id is None
            else f"Journal Entry #{journal_entry_id}"
        )

        super().__init__(
            title=title,
            surface_key=RibbonRegistry.child_window_key(self.DOC_TYPE),
            window_key=(self.DOC_TYPE, entity_key),
            registry=registry,
            icon_provider=provider,
            parent=parent,
        )

        self._service_registry = service_registry
        self._journal_entry_id = journal_entry_id

        # Build the body by embedding the dialog in widget mode.
        self._dialog = JournalEntryDialog(
            service_registry,
            company_id=company_id,
            company_name=company_name,
            journal_entry_id=journal_entry_id,
            parent=self,
        )
        self._dialog.enable_embedded_mode()
        self._dialog.saved.connect(self._on_dialog_saved)
        self.set_body(self._dialog)

        # Track dirty state on any user edit signal available. We use a
        # light heuristic here: header line edits + grid row changes mark
        # the window dirty. (The dialog does not currently expose a single
        # dirty signal; wiring it here is additive and cheap.)
        self._install_dirty_tracking()
        self.refresh_ribbon_state()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def handle_ribbon_command(self, command_id: str) -> None:
        if command_id == "journal_entry.save":
            self._command_save()
        elif command_id == "journal_entry.save_and_new":
            self._command_save_and_new()
        elif command_id == "journal_entry.close":
            self.close()
        elif command_id == "journal_entry.delete":
            self._command_delete()
        elif command_id == "journal_entry.post":
            self._command_post()
        elif command_id == "journal_entry.print":
            # Print from an unsaved window is disallowed; saved entries
            # can fall back to the register's print flow for now.
            pass
        # Unknown commands: silent no-op per IRibbonHost contract.

    def ribbon_state(self) -> dict[str, bool]:
        has_saved = self._dialog.saved_entry is not None or self._journal_entry_id is not None
        return {
            "journal_entry.save": not self._dialog._read_only,
            "journal_entry.save_and_new": (
                not self._dialog._read_only and self._journal_entry_id is None
            ),
            "journal_entry.post": has_saved and not self._dialog._read_only,
            "journal_entry.delete": has_saved and not self._dialog._read_only,
            "journal_entry.print": True,
            "journal_entry.close": True,
        }

    # ── Dirty-aware save / close hooks ────────────────────────────────

    def save(self) -> bool:
        return self._command_save()

    def discard(self) -> None:
        return None

    # ── Internals ─────────────────────────────────────────────────────

    def _command_save(self) -> bool:
        result = self._dialog.save_programmatically()
        if result is not None:
            self.set_dirty(False)
            self.refresh_ribbon_state()
            return True
        return False

    def _command_save_and_new(self) -> None:
        if not self._command_save():
            return
        # Close this window (now clean) and let the caller open a fresh one.
        self.close()

    def _command_post(self) -> None:
        entry = self._dialog.saved_entry
        entry_id = entry.id if entry is not None else self._journal_entry_id
        if entry_id is None:
            return
        try:
            self._service_registry.journal_posting_service.post_journal(
                self._dialog._company_id,
                entry_id,
            )
        except Exception as exc:  # surface clearly; service layer already guards
            QMessageBox.warning(self, "Post Journal Entry", str(exc))
            return
        QMessageBox.information(
            self, "Post Journal Entry", "Journal entry posted."
        )
        self.set_dirty(False)
        self.close()

    def _command_delete(self) -> None:
        entry = self._dialog.saved_entry
        entry_id = entry.id if entry is not None else self._journal_entry_id
        if entry_id is None:
            return
        choice = QMessageBox.question(
            self,
            "Delete Draft",
            "Delete this draft journal entry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.journal_service.delete_draft_journal(
                self._dialog._company_id,
                entry_id,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Delete Draft", str(exc))
            return
        self.set_dirty(False)
        self.close()

    def _on_dialog_saved(self, entry: JournalEntryDetailDTO) -> None:
        # After the first successful save, the draft is persisted and owns
        # an id — switch the window key so re-opens via the manager dedupe.
        if self._journal_entry_id is None and entry is not None:
            self._journal_entry_id = entry.id
            new_key = (self.DOC_TYPE, entry.id)
            self._window_key = new_key
            self.setWindowTitle(f"Journal Entry #{entry.id}")
        self.set_dirty(False)
        self.refresh_ribbon_state()

    def _install_dirty_tracking(self) -> None:
        dlg = self._dialog
        header_edits = [
            getattr(dlg, "_reference_edit", None),
            getattr(dlg, "_description_edit", None),
        ]
        for edit in header_edits:
            if edit is not None and hasattr(edit, "textEdited"):
                edit.textEdited.connect(lambda *_: self.set_dirty(True))
        journal_combo = getattr(dlg, "_journal_type_combo", None)
        if journal_combo is not None and hasattr(journal_combo, "currentIndexChanged"):
            journal_combo.currentIndexChanged.connect(lambda *_: self.set_dirty(True))
        txn_date = getattr(dlg, "_transaction_date_edit", None)
        if txn_date is not None and hasattr(txn_date, "dateChanged"):
            txn_date.dateChanged.connect(lambda *_: self.set_dirty(True))
