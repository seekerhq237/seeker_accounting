from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.treasury.dto.treasury_transfer_dto import TreasuryTransferListItemDTO
from seeker_accounting.modules.treasury.ui.treasury_transfer_dialog import TreasuryTransferDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, PermissionDeniedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.pager import Pager
from seeker_accounting.shared.ui.register import RegisterPage
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


TREASURY_TRANSFER_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="transfer_number", title="Transfer #"),
    DataTableColumn(key="date", title="Date"),
    DataTableColumn(key="from_account", title="From Account"),
    DataTableColumn(key="to_account", title="To Account"),
    DataTableColumn(key="currency", title="Currency"),
    DataTableColumn(key="amount", title="Amount", is_numeric=True),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="posted_at", title="Posted At"),
)


# Ribbon command ids surfaced from this page.
_CMD_NEW = "treasury_transfers.new"
_CMD_EDIT = "treasury_transfers.edit"
_CMD_CANCEL = "treasury_transfers.cancel"
_CMD_POST = "treasury_transfers.post"
_CMD_REFRESH = "treasury_transfers.refresh"


class TreasuryTransfersPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._transfers: list[TreasuryTransferListItemDTO] = []
        self._total_count: int = 0
        self._pending_resume_payload: ResumeTokenPayload | None = None
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(lambda: self.reload_transfers(reset_page=True))

        self._command_enabled: dict[str, bool] = {
            _CMD_NEW: False,
            _CMD_EDIT: False,
            _CMD_CANCEL: False,
            _CMD_POST: False,
            _CMD_REFRESH: True,
        }

        self.setObjectName("TreasuryTransfersPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        self._populate_action_band(self._register)
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_transfers()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_transfers(
        self,
        selected_transfer_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._transfers = []
            self._total_count = 0
            self._transfers_model.removeRows(0, self._transfers_model.rowCount())
            self._record_count_label.setText("Select a company")
            self._pager.reset()
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        if reset_page:
            self._pager.reset()

        search_text = self._search_input.text().strip() or None
        try:
            page_result = self._service_registry.treasury_transfer_service.list_treasury_transfers_page(
                active_company.company_id,
                status_code=self._status_filter_value(),
                query=search_text,
                page=self._pager.page,
                page_size=self._pager.page_size,
            )
        except Exception as exc:
            self._transfers = []
            self._total_count = 0
            self._transfers_model.removeRows(0, self._transfers_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._pager.reset()
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Treasury Transfers", f"Transfer data could not be loaded.\n\n{exc}")
            return

        self._transfers = list(page_result.items)
        self._total_count = page_result.total_count
        self._pager.apply_result(page_result)
        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_transfer_id)
        self._update_action_state()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._search_input = QLineEdit(register.toolbar_strip)
        self._search_input.setPlaceholderText("Search transfers…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        strip_layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Posted", "posted")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_transfers(reset_page=True))
        strip_layout.addWidget(self._status_filter_combo)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_transfers())
        strip_layout.addWidget(self._refresh_button)

    def _populate_action_band(self, register: RegisterPage) -> None:
        band_layout = register.action_band_layout

        self._new_button = QPushButton("New Transfer", register.action_band)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        band_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", register.action_band)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        band_layout.addWidget(self._edit_button)

        self._cancel_button = QPushButton("Cancel Draft", register.action_band)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_draft)
        band_layout.addWidget(self._cancel_button)

        self._post_button = QPushButton("Post Transfer", register.action_band)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_transfer)
        band_layout.addWidget(self._post_button)

        band_layout.addStretch(1)

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
        layout.setSpacing(4)

        self._transfers_model = QStandardItemModel(0, len(TREASURY_TRANSFER_COLUMNS), self)
        self._transfers_model.setHorizontalHeaderLabels(
            [c.title for c in TREASURY_TRANSFER_COLUMNS]
        )

        self._table = DataTable(
            columns=TREASURY_TRANSFER_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No treasury transfers to display.",
            parent=container,
        )
        self._table.set_model(self._transfers_model)
        self._transfers_status_delegate = apply_status_chip_to_column(
            self._table.view(), 6
        )
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        layout.addWidget(self._table, 1)

        self._pager = Pager(container, default_page_size=100)
        self._pager.page_changed.connect(lambda _p: self.reload_transfers())
        self._pager.page_size_changed.connect(lambda _s: self.reload_transfers(reset_page=True))
        layout.addWidget(self._pager)
        return container

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No treasury transfers yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first draft transfer between financial accounts, "
            "then post when the transfer is confirmed.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Transfer", actions)
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
            "Treasury transfers are company-scoped. Choose the active company before creating or posting transfers.",
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

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _status_filter_value(self) -> str | None:
        value = self._status_filter_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._transfers:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return item

    def _populate_table(self) -> None:
        self._transfers_model.removeRows(0, self._transfers_model.rowCount())
        for transfer in self._transfers:
            items = [
                self._make_item(transfer.transfer_number, user_data=transfer.id),
                self._make_item(self._format_date(transfer.transfer_date)),
                self._make_item(transfer.from_account_name),
                self._make_item(transfer.to_account_name),
                self._make_item(transfer.currency_code),
                self._make_numeric(transfer.amount),
                self._make_item(transfer.status_code),
                self._make_item(self._format_datetime(transfer.posted_at)),
            ]
            self._transfers_model.appendRow(items)

        search_text = self._search_input.text().strip()
        total = self._total_count
        shown = len(self._transfers)
        if search_text:
            self._record_count_label.setText(f"{shown} shown of {total} matches")
        else:
            self._record_count_label.setText(
                f"{total} transfer" if total == 1 else f"{total} transfers"
            )

    def _handle_search_text_changed(self, _text: str) -> None:
        self._search_debounce.start()

    def _apply_search_filter(self) -> None:
        # Search is now handled server-side via reload_transfers. Kept as a
        # no-op for backward compatibility with any external callers.
        return

    def _restore_selection(self, selected_transfer_id: int | None) -> None:
        if not self._transfers:
            return
        if selected_transfer_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, t in enumerate(self._transfers) if t.id == selected_transfer_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._transfers_model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._table.view().selectionModel()
        if sm is None:
            return
        sm.select(
            proxy_index,
            sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows,
        )
        self._table.view().scrollTo(proxy_index)

    def _selected_transfer(self) -> TreasuryTransferListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._transfers):
            return self._transfers[idx]
        return None

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        selected = self._selected_transfer()
        if selected is not None and selected.status_code == "draft":
            self._open_edit_dialog()

    def _set_command_enabled(self, command_id: str, enabled: bool) -> None:
        self._command_enabled[command_id] = bool(enabled)

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_transfer()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"
        perm = self._service_registry.permission_service

        self._set_command_enabled(_CMD_NEW, has_company and perm.has_permission("treasury.transfers.create"))
        self._set_command_enabled(_CMD_EDIT, is_draft and perm.has_permission("treasury.transfers.edit"))
        self._set_command_enabled(_CMD_CANCEL, is_draft and perm.has_permission("treasury.transfers.cancel"))
        self._set_command_enabled(_CMD_POST, is_draft and perm.has_permission("treasury.transfers.post"))
        self._set_command_enabled(_CMD_REFRESH, True)

        # Keep legacy action-band buttons in sync (band is hidden but buttons exist).
        self._new_button.setEnabled(self._command_enabled[_CMD_NEW])
        self._edit_button.setEnabled(self._command_enabled[_CMD_EDIT])
        self._cancel_button.setEnabled(self._command_enabled[_CMD_CANCEL])
        self._post_button.setEnabled(self._command_enabled[_CMD_POST])

        self._notify_ribbon_state_changed()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self):
        return {
            _CMD_NEW: self._open_create_dialog,
            _CMD_EDIT: self._open_edit_dialog,
            _CMD_CANCEL: self._cancel_selected_draft,
            _CMD_POST: self._post_selected_transfer,
            _CMD_REFRESH: self.reload_transfers,
        }

    def ribbon_state(self):
        state = dict(self._command_enabled)
        # Preserve existing ribbon contract: print/export keys exposed but disabled.
        state.setdefault("treasury_transfers.print", False)
        state.setdefault("treasury_transfers.export_list", False)
        return state

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("treasury.transfers.create"):
            self._show_permission_denied("treasury.transfers.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Treasury Transfers", "Select an active company before creating transfers.")
            return
        if not run_document_sequence_preflight(
            self, self._service_registry,
            active_company.company_id, active_company.company_name,
            "treasury_transfer", nav_ids.TREASURY_TRANSFERS,
        ):
            return

        result = TreasuryTransferDialog.create_transfer(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_transfers(selected_transfer_id=result.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("treasury.transfers.edit"):
            self._show_permission_denied("treasury.transfers.edit")
            return
        active_company = self._active_company()
        selected = self._selected_transfer()
        if active_company is None or selected is None:
            show_info(self, "Treasury Transfers", "Select a draft transfer to edit.")
            return
        if selected.status_code != "draft":
            show_info(self, "Treasury Transfers", "Only draft transfers can be edited.")
            return

        result = TreasuryTransferDialog.edit_transfer(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            transfer_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_transfers(selected_transfer_id=result.id)

    def _cancel_selected_draft(self) -> None:
        if not self._service_registry.permission_service.has_permission("treasury.transfers.cancel"):
            self._show_permission_denied("treasury.transfers.cancel")
            return
        active_company = self._active_company()
        selected = self._selected_transfer()
        if active_company is None or selected is None:
            show_info(self, "Treasury Transfers", "Select a draft transfer to cancel.")
            return

        choice = QMessageBox.question(
            self,
            "Cancel Draft Transfer",
            f"Cancel draft transfer {selected.transfer_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.treasury_transfer_service.cancel_draft_transfer(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Treasury Transfers", str(exc))
            self.reload_transfers(selected_transfer_id=selected.id)
            return
        self.reload_transfers()

    def _post_selected_transfer(self) -> None:
        if not self._service_registry.permission_service.has_permission("treasury.transfers.post"):
            self._show_permission_denied("treasury.transfers.post")
            return
        active_company = self._active_company()
        selected = self._selected_transfer()
        if active_company is None or selected is None:
            show_info(self, "Treasury Transfers", "Select a draft transfer to post.")
            return

        choice = QMessageBox.question(
            self,
            "Post Transfer",
            (
                f"Post transfer {selected.transfer_number}?\n\n"
                "Posting creates a journal entry and makes the transfer immutable."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._service_registry.treasury_transfer_posting_service.post_transfer(
                active_company.company_id,
                selected.id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
                handle_document_sequence_error(
                    self, self._service_registry, exc,
                    "treasury_transfer.post",
                    lambda: {"document_id": selected.id},
                    nav_ids.TREASURY_TRANSFERS,
                    active_company.company_name,
                )
                return
            show_error(self, "Treasury Transfers", str(exc))
            self.reload_transfers(selected_transfer_id=selected.id)
            return
        except (NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Treasury Transfers", str(exc))
            self.reload_transfers(selected_transfer_id=selected.id)
            return

        show_info(
            self,
            "Treasury Transfers",
            f"Transfer {result.transfer_number} posted successfully.\n"
            f"Journal entry: {result.journal_entry_number}",
        )
        self.reload_transfers(selected_transfer_id=result.transfer_id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Permission Denied",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_date(self, value: date) -> str:
        return value.strftime("%Y-%m-%d")

    def _format_datetime(self, value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value is not None else ""

    def _format_amount(self, value: Decimal) -> str:
        return f"{value:,.2f}"

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _handle_item_double_clicked(self, *_args: object) -> None:
        # Backward-compatible no-op; double-click is now wired via DataTable.row_activated.
        selected = self._selected_transfer()
        if selected is None:
            return
        if selected.status_code == "draft":
            self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_transfers()

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        token_payload = consume_resume_payload_for_workflows(
            context=context,
            service_registry=self._service_registry,
            allowed_workflow_keys=("treasury_transfer.preflight", "treasury_transfer.post"),
        )
        if token_payload is None:
            self._pending_resume_payload = None
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
        if payload.workflow_key == "treasury_transfer.post":
            document_id = payload.payload.get("document_id") if payload.payload else None
            self.reload_transfers(selected_transfer_id=document_id)
            return
        self._open_create_dialog()
