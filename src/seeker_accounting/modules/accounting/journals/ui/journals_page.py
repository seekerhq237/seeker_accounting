from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.accounting.journals.dto.journal_dto import JournalEntryListItemDTO
from seeker_accounting.modules.accounting.journals.ui.journal_entry_dialog import JournalEntryDialog
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver
from seeker_accounting.shared.ui.guided_resolution_coordinator import GuidedResolutionCoordinator
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.table_helpers import configure_dense_table
from seeker_accounting.shared.ui.register import RegisterPage


class JournalsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._journal_entries: list[JournalEntryListItemDTO] = []
        self._pending_resume_payload = None

        self.setObjectName("JournalsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        self._populate_action_band(self._register)
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        # The Sage-style ribbon replaces the register's in-page action band.
        # Keep the band populated for any legacy/detached code paths, but hide
        # it visually so ribbon commands are the only user-facing entry point.
        self._register.action_band.hide()

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )

        self.reload_entries()

    def reload_entries(self, selected_journal_entry_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._journal_entries = []
            self._table.setRowCount(0)
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._journal_entries = self._service_registry.journal_service.list_journal_entries(
                active_company.company_id,
                self._status_filter_value(),
            )
        except Exception as exc:
            self._journal_entries = []
            self._table.setRowCount(0)
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Journal", f"Entry data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_journal_entry_id)
        self._update_action_state()

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "DRAFT")
        self._status_filter_combo.addItem("Posted", "POSTED")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_entries())
        strip_layout.addWidget(self._status_filter_combo)

        strip_layout.addStretch(1)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_entries())
        strip_layout.addWidget(self._refresh_button)

    def _populate_action_band(self, register: RegisterPage) -> None:
        band_layout = register.action_band_layout

        self._new_button = QPushButton("New Entry", register.action_band)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        band_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", register.action_band)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        band_layout.addWidget(self._edit_button)

        self._delete_button = QPushButton("Delete Draft", register.action_band)
        self._delete_button.setProperty("variant", "secondary")
        self._delete_button.clicked.connect(self._delete_selected_draft)
        band_layout.addWidget(self._delete_button)

        self._post_button = QPushButton("Post Entry", register.action_band)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_journal)
        band_layout.addWidget(self._post_button)

        self._batch_post_button = QPushButton("Batch Post", register.action_band)
        self._batch_post_button.setProperty("variant", "secondary")
        self._batch_post_button.setToolTip("Post all checked draft entries")
        self._batch_post_button.clicked.connect(self._batch_post_checked)
        band_layout.addWidget(self._batch_post_button)

        band_layout.addStretch(1)

        self._print_button = QPushButton("Print / Export", register.action_band)
        self._print_button.setProperty("variant", "ghost")
        self._print_button.clicked.connect(self._print_selected_entry)
        band_layout.addWidget(self._print_button)

        self._export_list_button = QPushButton("Export List", register.action_band)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._print_entry_list)
        band_layout.addWidget(self._export_list_button)

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_active_company_state = self._build_no_active_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_active_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(container)
        self._table.setObjectName("JournalsTable")
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            (
                "",
                "Txn Date",
                "Reference",
                "Description",
                "Status",
                "Total Debit",
                "Total Credit",
                "Posted At",
            )
        )
        configure_dense_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        self._table.itemChanged.connect(self._on_checkbox_changed)
        self._table.horizontalHeader().sectionClicked.connect(self._handle_header_section_clicked)
        layout.addWidget(self._table)
        return container

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No entries yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first draft entry for the active company, then post it only after the totals balance and the fiscal period stays open.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Entry", actions)
        create_button.setProperty("variant", "primary")
        create_button.clicked.connect(self._open_create_dialog)
        actions_layout.addWidget(create_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    def _build_no_active_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Journals are company-scoped. Choose the active company from the shell before creating or posting accounting entries.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        companies_button = QPushButton("Open Companies", actions)
        companies_button.setProperty("variant", "secondary")
        companies_button.clicked.connect(self._open_companies_workspace)
        actions_layout.addWidget(companies_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _status_filter_value(self) -> str | None:
        value = self._status_filter_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._journal_entries:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for entry in self._journal_entries:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)

            # Column 0 — checkbox; stores entry ID as UserRole
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            chk_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self._table.setItem(row_index, 0, chk_item)

            # Columns 1–7 — data
            values = (
                self._format_optional_date(entry.transaction_date),
                entry.reference_text or "",
                entry.description or "",
                entry.status_code.title(),
                self._format_decimal(entry.total_debit),
                self._format_decimal(entry.total_credit),
                self._format_datetime(entry.posted_at),
            )
            for col_offset, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col_offset in {0, 3, 4, 5, 6}:  # date, status, dr, cr, posted_at
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, col_offset + 1, item)

        self._table.blockSignals(False)
        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 36)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.Stretch)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

    def _restore_selection(self, selected_journal_entry_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_journal_entry_id is None:
            self._table.selectRow(0)
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_journal_entry_id:
                self._table.selectRow(row_index)
                return
        self._table.selectRow(0)

    def _selected_entry(self) -> JournalEntryListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        journal_entry_id = item.data(Qt.ItemDataRole.UserRole)
        for entry in self._journal_entries:
            if entry.id == journal_entry_id:
                return entry
        return None

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected_entry = self._selected_entry()
        has_active_company = active_company is not None

        self._new_button.setEnabled(has_active_company)
        self._edit_button.setEnabled(
            has_active_company and selected_entry is not None and selected_entry.status_code == "DRAFT"
        )
        self._delete_button.setEnabled(
            has_active_company and selected_entry is not None and selected_entry.status_code == "DRAFT"
        )
        self._post_button.setEnabled(
            has_active_company and selected_entry is not None and selected_entry.status_code == "DRAFT"
        )
        self._batch_post_button.setEnabled(
            has_active_company and self._count_checked_drafts() > 0
        )
        self._print_button.setEnabled(has_active_company and selected_entry is not None)
        self._export_list_button.setEnabled(has_active_company and bool(self._journal_entries))

        # Refresh ribbon enablement if a bar is listening for this page.
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ───────────────────────────────────────────────────

    #: Map of ribbon command_id → bound handler. Populated lazily.
    _RIBBON_COMMAND_MAP_ATTR = "_ribbon_command_map"

    def _ribbon_commands(self) -> dict[str, callable]:
        commands = getattr(self, self._RIBBON_COMMAND_MAP_ATTR, None)
        if commands is None:
            from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_handlers
            commands = {
                "journals.new_entry": self._open_create_dialog,
                "journals.edit_draft": self._open_edit_dialog,
                "journals.delete_draft": self._delete_selected_draft,
                "journals.post_entry": self._post_selected_journal,
                "journals.batch_post": self._batch_post_checked,
                "journals.refresh": self.reload_entries,
                "journals.print_entry": self._print_selected_entry,
                "journals.export_list": self._print_entry_list,
                **related_goto_handlers(self._service_registry, "journals"),
            }
            setattr(self, self._RIBBON_COMMAND_MAP_ATTR, commands)
        return commands

    def handle_ribbon_command(self, command_id: str) -> None:
        handler = self._ribbon_commands().get(command_id)
        if handler is None:
            return
        handler()

    def ribbon_state(self) -> dict[str, bool]:
        active_company = self._active_company()
        selected_entry = self._selected_entry()
        has_company = active_company is not None
        has_draft_selection = (
            selected_entry is not None and selected_entry.status_code == "DRAFT"
        )
        has_any_selection = selected_entry is not None
        has_entries = bool(self._journal_entries)
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_state
        return {
            "journals.new_entry": has_company,
            "journals.edit_draft": has_company and has_draft_selection,
            "journals.delete_draft": has_company and has_draft_selection,
            "journals.post_entry": has_company and has_draft_selection,
            "journals.batch_post": has_company and self._count_checked_drafts() > 0,
            "journals.refresh": True,
            "journals.print_entry": has_company and has_any_selection,
            "journals.export_list": has_company and has_entries,
            **related_goto_state("journals"),
        }

    def _notify_ribbon_state_changed(self) -> None:
        """Ask the shell's ribbon bar to re-pull ``ribbon_state`` for us.

        Walks up the parent chain to locate a :class:`MainWindow`-like host
        exposing ``_ribbon_bar``. Silent no-op if the shell has no ribbon
        (e.g. in a standalone smoke test), so this is safe to call freely.
        """

        widget = self.parent()
        while widget is not None:
            ribbon_bar = getattr(widget, "_ribbon_bar", None)
            if ribbon_bar is not None and hasattr(ribbon_bar, "refresh_active_state"):
                ribbon_bar.refresh_active_state()
                return
            widget = widget.parent()

    def _on_checkbox_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_action_state()

    def _handle_header_section_clicked(self, logical_index: int) -> None:
        """Click column-0 header to toggle all checkboxes (select-all / deselect-all)."""
        if logical_index != 0:
            return
        row_count = self._table.rowCount()
        if row_count == 0:
            return
        all_checked = all(
            self._table.item(row, 0) is not None
            and self._table.item(row, 0).checkState() == Qt.CheckState.Checked
            for row in range(row_count)
        )
        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        self._table.blockSignals(True)
        for row in range(row_count):
            item = self._table.item(row, 0)
            if item is not None:
                item.setCheckState(new_state)
        self._table.blockSignals(False)
        self._update_action_state()

    def _count_checked_drafts(self) -> int:
        count = 0
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            entry_id = item.data(Qt.ItemDataRole.UserRole)
            for entry in self._journal_entries:
                if entry.id == entry_id and entry.status_code == "DRAFT":
                    count += 1
                    break
        return count

    def _get_checked_draft_entries(self) -> list[JournalEntryListItemDTO]:
        result: list[JournalEntryListItemDTO] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            entry_id = item.data(Qt.ItemDataRole.UserRole)
            for entry in self._journal_entries:
                if entry.id == entry_id and entry.status_code == "DRAFT":
                    result.append(entry)
                    break
        return result

    def _batch_post_checked(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return

        entries = self._get_checked_draft_entries()
        if not entries:
            show_info(self, "Journal", "No draft entries are checked for batch posting.")
            return

        count = len(entries)
        choice = QMessageBox.question(
            self,
            "Batch Post Entries",
            (
                f"Post {count} checked draft entr{'y' if count == 1 else 'ies'}?\n\n"
                "Posting cannot be undone through ordinary entry editing."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        posted_count = 0
        failures: list[tuple[JournalEntryListItemDTO, Exception]] = []
        last_posted_id: int | None = None

        for entry in entries:
            try:
                result = self._service_registry.journal_posting_service.post_journal(
                    active_company.company_id,
                    entry.id,
                    actor_user_id=self._service_registry.app_context.current_user_id,
                )
                posted_count += 1
                last_posted_id = result.journal_entry_id
            except (ValidationError, NotFoundError, PeriodLockedError) as exc:
                failures.append((entry, exc))

        self.reload_entries(selected_journal_entry_id=last_posted_id)

        if failures:
            lines = [f"Posted {posted_count} of {count} entr{'y' if count == 1 else 'ies'}."]
            lines.append("\nFailed:")
            for failed_entry, exc in failures:
                date_str = self._format_date(failed_entry.entry_date)
                lines.append(f"  \u2022 {date_str}: {exc}")
            show_error(self, "Batch Post", "\n".join(lines))
        else:
            show_info(
                self,
                "Journal",
                f"{posted_count} entr{'y' if posted_count == 1 else 'ies'} posted successfully.",
            )

    def _open_create_dialog(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Journal", "Select an active company before creating entries.")
            return

        journal_entry = JournalEntryDialog.create_journal(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if journal_entry is None:
            return
        self.reload_entries(selected_journal_entry_id=journal_entry.id)

    def _open_edit_dialog(self) -> None:
        active_company = self._active_company()
        entry = self._selected_entry()
        if active_company is None or entry is None:
            show_info(self, "Journal", "Select a draft entry to edit.")
            return
        if entry.status_code != "DRAFT":
            show_info(self, "Journal", "Posted entries open in read-only detail mode.")
            self._open_view_dialog()
            return

        # Route through the ChildWindowManager so editing a journal entry
        # opens an independent top-level window (Sage-style). If the same
        # entry is already open, the manager raises / focuses it instead
        # of instantiating a duplicate.
        manager = getattr(self._service_registry, "child_window_manager", None)
        if manager is not None:
            from seeker_accounting.modules.accounting.journals.ui.journal_entry_window import (
                JournalEntryWindow,
            )

            def _factory() -> JournalEntryWindow:
                return JournalEntryWindow(
                    self._service_registry,
                    company_id=active_company.company_id,
                    company_name=active_company.company_name,
                    journal_entry_id=entry.id,
                )

            window = manager.open_document(
                JournalEntryWindow.DOC_TYPE, entry.id, _factory
            )
            # When the window closes, reload the register so posted/edited
            # entries appear with their current state.
            window.closed.connect(
                lambda *_: self.reload_entries(selected_journal_entry_id=entry.id)
            )
            return

        # Fallback: legacy modal dialog (no shell available).
        updated_entry = JournalEntryDialog.edit_journal(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            journal_entry_id=entry.id,
            parent=self,
        )
        if updated_entry is None:
            return
        self.reload_entries(selected_journal_entry_id=updated_entry.id)

    def _open_view_dialog(self) -> None:
        active_company = self._active_company()
        entry = self._selected_entry()
        if active_company is None or entry is None:
            return
        JournalEntryDialog.view_journal(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            journal_entry_id=entry.id,
            parent=self,
        )

    def _delete_selected_draft(self) -> None:
        active_company = self._active_company()
        entry = self._selected_entry()
        if active_company is None or entry is None:
            show_info(self, "Journal", "Select a draft entry to delete.")
            return

        choice = QMessageBox.question(
            self,
            "Delete Draft Entry",
            f"Delete the draft entry dated {self._format_date(entry.entry_date)}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.journal_service.delete_draft_journal(active_company.company_id, entry.id)
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Journal", str(exc))
            self.reload_entries(selected_journal_entry_id=entry.id)
            return

        self.reload_entries()

    def _post_selected_journal(self) -> None:
        active_company = self._active_company()
        entry = self._selected_entry()
        if active_company is None or entry is None:
            show_info(self, "Journal", "Select a draft entry to post.")
            return

        choice = QMessageBox.question(
            self,
            "Post Entry",
            (
                f"Post the draft entry dated {self._format_date(entry.entry_date)}?\n\n"
                "Posting is controlled and cannot be undone through ordinary entry editing."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._service_registry.journal_posting_service.post_journal(
                active_company.company_id,
                entry.id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Journal", str(exc))
            self.reload_entries(selected_journal_entry_id=entry.id)
            return
        except PeriodLockedError as exc:
            if exc.app_error_code == AppErrorCode.LOCKED_FISCAL_PERIOD:
                coordinator = GuidedResolutionCoordinator(
                    resolver=ErrorResolutionResolver(),
                    workflow_resume_service=self._service_registry.workflow_resume_service,
                    navigation_service=self._service_registry.navigation_service,
                )
                _post_entry_id = entry.id
                result_coord = coordinator.handle_exception(
                    parent=self,
                    error=exc,
                    workflow_key="journal_entry.post",
                    workflow_snapshot=lambda: {"journal_entry_id": _post_entry_id},
                    origin_nav_id=nav_ids.JOURNALS,
                    resolution_context={"company_name": active_company.company_name},
                )
                if result_coord.handled and result_coord.selected_action and result_coord.selected_action.nav_id:
                    return
            show_error(self, "Journal", str(exc))
            self.reload_entries(selected_journal_entry_id=entry.id)
            return

        show_info(
            self,
            "Journal",
            f"Entry {result.entry_number} posted successfully into {result.fiscal_period_code}.",
        )
        self.reload_entries(selected_journal_entry_id=result.journal_entry_id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _format_date(self, value: date) -> str:
        return value.strftime("%Y-%m-%d")

    def _format_optional_date(self, value: date | None) -> str:
        return value.strftime("%Y-%m-%d") if value is not None else ""

    def _format_datetime(self, value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value is not None else ""

    def _format_decimal(self, value: Decimal) -> str:
        return f"{value:.2f}"

    def _handle_item_double_clicked(self, *_args: object) -> None:
        selected_entry = self._selected_entry()
        if selected_entry is None:
            return
        if selected_entry.status_code == "DRAFT":
            self._open_edit_dialog()
            return
        self._open_view_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_entries()

    def set_navigation_context(self, context: dict) -> None:
        resume_token = context.get("resume_token")
        if not isinstance(resume_token, str) or not resume_token:
            return
        token_payload = self._service_registry.workflow_resume_service.consume_token(resume_token)
        if token_payload is None:
            return
        if token_payload.workflow_key not in (
            "journal_entry.create",
            "journal_entry.update",
            "journal_entry.post",
        ):
            return
        self._pending_resume_payload = token_payload
        QTimer.singleShot(0, self._open_from_resume_payload)

    def _open_from_resume_payload(self) -> None:
        payload = self._pending_resume_payload
        if payload is None:
            return
        self._pending_resume_payload = None
        active_company = self._active_company()
        if active_company is None:
            return
        if payload.workflow_key == "journal_entry.post":
            journal_entry_id = payload.payload.get("journal_entry_id") if payload.payload else None
            self.reload_entries(selected_journal_entry_id=journal_entry_id)
            return
        journal_entry = JournalEntryDialog.create_journal(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
            draft_snapshot=payload.payload,
        )
        if journal_entry is None:
            return
        self.reload_entries(selected_journal_entry_id=journal_entry.id)

    # ------------------------------------------------------------------
    # Print / export
    # ------------------------------------------------------------------

    def _print_selected_entry(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        entry = self._selected_entry()
        if entry is None:
            return
        label = entry.entry_number or f"Draft #{entry.id}"
        result = PrintExportDialog.show_dialog(self, f"Journal Entry — {label}")
        if result is None:
            return
        try:
            self._service_registry.journal_entry_print_service.print_journal_entry(
                active_company.company_id, entry.id, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Journal", f"Export failed.\n\n{exc}")

    def _print_entry_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._journal_entries:
            return
        result = PrintExportDialog.show_dialog(self, "Journal Entry Register")
        if result is None:
            return
        try:
            self._service_registry.journal_entry_print_service.print_journal_list(
                active_company.company_id, self._journal_entries, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Journal", f"Export failed.\n\n{exc}")
