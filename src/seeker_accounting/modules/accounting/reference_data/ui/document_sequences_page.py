from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    DocumentSequenceListItemDTO,
    DocumentSequencePreviewDTO,
)
from seeker_accounting.modules.accounting.reference_data.ui.document_sequence_dialog import (
    DocumentSequenceDialog,
)
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.app.shell.ribbon import RibbonHostMixin


DOCUMENT_SEQUENCE_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="document_type", title="Document Type"),
    DataTableColumn(key="prefix", title="Prefix"),
    DataTableColumn(key="next_number", title="Next Number", is_numeric=True),
    DataTableColumn(key="padding_width", title="Padding Width", is_numeric=True),
    DataTableColumn(key="reset_frequency", title="Reset Frequency"),
    DataTableColumn(key="status", title="Status"),
)


class DocumentSequencesPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._sequences: list[DocumentSequenceListItemDTO] = []
        self._resume_context: dict | None = None

        self.setObjectName("DocumentSequencesPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._action_bar = self._build_action_bar()
        root_layout.addWidget(self._action_bar)
        self._action_bar.hide()
        self._resume_banner = self._build_resume_banner()
        root_layout.addWidget(self._resume_banner)
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )

        self.reload_document_sequences()

    def reload_document_sequences(self, selected_sequence_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._sequences = []
            self._sequences_model.removeRows(0, self._sequences_model.rowCount())
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._sequences = self._service_registry.numbering_setup_service.list_document_sequences(
                active_company.company_id
            )
        except Exception as exc:
            self._sequences = []
            self._sequences_model.removeRows(0, self._sequences_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Document Sequences", f"Document sequences could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_sequence_id)
        self._update_action_state()

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Document Sequences", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._record_count_label = QLabel(card)
        self._record_count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._record_count_label)

        layout.addStretch(1)

        self._new_button = QPushButton("New Sequence", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Sequence", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._preview_button = QPushButton("Preview Number", card)
        self._preview_button.setProperty("variant", "secondary")
        self._preview_button.clicked.connect(self._preview_selected_sequence)
        layout.addWidget(self._preview_button)

        self._deactivate_button = QPushButton("Deactivate", card)
        self._deactivate_button.setProperty("variant", "secondary")
        self._deactivate_button.clicked.connect(self._deactivate_selected_sequence)
        layout.addWidget(self._deactivate_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_document_sequences())
        layout.addWidget(self._refresh_button)
        return card

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
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sequences_model = QStandardItemModel(0, len(DOCUMENT_SEQUENCE_COLUMNS), self)
        self._sequences_model.setHorizontalHeaderLabels([c.title for c in DOCUMENT_SEQUENCE_COLUMNS])

        self._table = DataTable(
            columns=DOCUMENT_SEQUENCE_COLUMNS,
            show_search=True,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No document sequences to display.",
            parent=card,
        )
        self._table.set_model(self._sequences_model)
        self._sequences_status_delegate = apply_status_chip_to_column(self._table.view(), 5)
        self._table.selection_changed.connect(self._update_action_state)
        self._table.row_activated.connect(self._on_row_activated)
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No document sequences yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first numbering definition for the active company to establish a clean sequence baseline before operational documents arrive.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Sequence", actions)
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
            "Document sequences are company-scoped. Select the active company from the shell or return to Companies if setup is still incomplete.",
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

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._sequences:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    @staticmethod
    def _make_item(text, *, user_data: object | None = None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _populate_table(self) -> None:
        self._sequences_model.removeRows(0, self._sequences_model.rowCount())
        for sequence in self._sequences:
            items = [
                self._make_item(sequence.document_type_code, user_data=sequence.id),
                self._make_item(sequence.prefix or ""),
                self._make_item(str(sequence.next_number)),
                self._make_item(str(sequence.padding_width)),
                self._make_item(sequence.reset_frequency_code or ""),
                self._make_item("active" if sequence.is_active else "inactive"),
            ]
            self._sequences_model.appendRow(items)

        count = len(self._sequences)
        self._record_count_label.setText(f"{count} sequence" if count == 1 else f"{count} sequences")

    def _restore_selection(self, selected_sequence_id: int | None) -> None:
        if not self._sequences:
            return
        if selected_sequence_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, s in enumerate(self._sequences) if s.id == selected_sequence_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._sequences_model.index(target_idx, 0)
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

    def _selected_sequence(self) -> DocumentSequenceListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        row_index = rows[0]
        if row_index < 0 or row_index >= len(self._sequences):
            return None
        return self._sequences[row_index]

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Document Sequences",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected_sequence = self._selected_sequence()
        has_active_company = active_company is not None
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_active_company and permission_service.has_permission("reference.document_sequences.create")
        )
        self._edit_button.setEnabled(
            selected_sequence is not None
            and has_active_company
            and permission_service.has_permission("reference.document_sequences.edit")
        )
        self._preview_button.setEnabled(
            selected_sequence is not None
            and has_active_company
            and permission_service.has_permission("reference.document_sequences.preview")
        )
        self._deactivate_button.setEnabled(
            selected_sequence is not None
            and has_active_company
            and selected_sequence.is_active
            and permission_service.has_permission("reference.document_sequences.deactivate")
        )
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ────────────────────────────────────────────────────

    def _ribbon_commands(self) -> dict:
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_handlers
        return {
            "document_sequences.new": self._open_create_dialog,
            "document_sequences.edit": self._open_edit_dialog,
            "document_sequences.preview": self._preview_selected_sequence,
            "document_sequences.deactivate": self._deactivate_selected_sequence,
            "document_sequences.refresh": self.reload_document_sequences,
            **related_goto_handlers(self._service_registry, "document_sequences"),
        }

    def ribbon_state(self) -> dict:
        from seeker_accounting.app.shell.ribbon.ribbon_nav import related_goto_state
        return {
            "document_sequences.new": self._new_button.isEnabled(),
            "document_sequences.edit": self._edit_button.isEnabled(),
            "document_sequences.preview": self._preview_button.isEnabled(),
            "document_sequences.deactivate": self._deactivate_button.isEnabled(),
            "document_sequences.refresh": True,
            **related_goto_state("document_sequences"),
        }

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.document_sequences.create"):
            self._show_permission_denied("reference.document_sequences.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Document Sequences", "Select an active company before creating sequences.")
            return

        sequence = DocumentSequenceDialog.create_sequence(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if sequence is None:
            return
        self.reload_document_sequences(selected_sequence_id=sequence.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.document_sequences.edit"):
            self._show_permission_denied("reference.document_sequences.edit")
            return
        active_company = self._active_company()
        sequence = self._selected_sequence()
        if active_company is None or sequence is None:
            show_info(self, "Document Sequences", "Select a sequence to edit.")
            return

        updated_sequence = DocumentSequenceDialog.edit_sequence(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            sequence_id=sequence.id,
            parent=self,
        )
        if updated_sequence is None:
            return
        self.reload_document_sequences(selected_sequence_id=updated_sequence.id)

    def _deactivate_selected_sequence(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.document_sequences.deactivate"):
            self._show_permission_denied("reference.document_sequences.deactivate")
            return
        active_company = self._active_company()
        sequence = self._selected_sequence()
        if active_company is None or sequence is None:
            show_info(self, "Document Sequences", "Select a sequence to deactivate.")
            return
        if not sequence.is_active:
            show_info(self, "Document Sequences", "The selected sequence is already inactive.")
            return

        choice = QMessageBox.question(
            self,
            "Deactivate Document Sequence",
            (
                f"Deactivate the {sequence.document_type_code} sequence for "
                f"{active_company.company_name}?"
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.numbering_setup_service.deactivate_document_sequence(
                active_company.company_id,
                sequence.id,
            )
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Document Sequences", str(exc))
            self.reload_document_sequences()
            return

        self.reload_document_sequences(selected_sequence_id=sequence.id)

    def _preview_selected_sequence(self) -> None:
        if not self._service_registry.permission_service.has_permission("reference.document_sequences.preview"):
            self._show_permission_denied("reference.document_sequences.preview")
            return
        active_company = self._active_company()
        sequence = self._selected_sequence()
        if active_company is None or sequence is None:
            show_info(self, "Document Sequences", "Select a sequence to preview.")
            return

        try:
            preview = self._service_registry.numbering_setup_service.preview_document_number(
                active_company.company_id,
                sequence.id,
            )
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Document Sequences", str(exc))
            self.reload_document_sequences()
            return

        self._show_preview(preview)

    def _show_preview(self, preview: DocumentSequencePreviewDTO) -> None:
        show_info(
            self,
            "Preview Document Number",
            (
                f"Document type: {preview.document_type_code}\n"
                f"Next number: {preview.next_number}\n\n"
                f"Preview: {preview.preview_number}"
            ),
        )

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _on_row_activated(self, _row: int) -> None:
        self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_document_sequences()

    # ------------------------------------------------------------------
    # Resume banner and guided-return support
    # ------------------------------------------------------------------

    def _build_resume_banner(self) -> QFrame:
        banner = QFrame(self)
        banner.setObjectName("GuidedResumeBanner")

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        self._resume_banner_label = QLabel(banner)
        self._resume_banner_label.setObjectName("ResumeBannerMessage")
        self._resume_banner_label.setWordWrap(True)
        layout.addWidget(self._resume_banner_label, 1)

        self._return_to_workflow_button = QPushButton("Return to Workflow", banner)
        self._return_to_workflow_button.setProperty("variant", "primary")
        self._return_to_workflow_button.clicked.connect(self._handle_return_to_workflow)
        layout.addWidget(self._return_to_workflow_button)

        dismiss_btn = QPushButton("Dismiss", banner)
        dismiss_btn.setProperty("variant", "ghost")
        dismiss_btn.clicked.connect(self._dismiss_resume_banner)
        layout.addWidget(dismiss_btn)

        banner.setVisible(False)
        return banner

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        resume_token = context.get("resume_token")
        document_type_code = str(context.get("document_type_code", "")).lower()
        open_create_flow = bool(context.get("open_create_flow"))

        if not resume_token:
            self._dismiss_resume_banner()
            return

        self._resume_context = dict(context)

        if document_type_code:
            from seeker_accounting.platform.exceptions.error_resolution_resolver import _DOCUMENT_TYPE_LABELS
            label = _DOCUMENT_TYPE_LABELS.get(document_type_code) or document_type_code.replace("_", " ").title()
            if open_create_flow:
                message = (
                    f"Opened to create a {label} document sequence. "
                    "Set up the numbering definition below, then return to continue your workflow."
                )
            else:
                message = (
                    f"Opened to configure document sequences for {label}. "
                    "Create or activate the sequence below, then return to continue your workflow."
                )
        else:
            message = (
                "Opened from another workflow. Configure the required document sequence, "
                "then return to continue."
            )

        self._resume_banner_label.setText(message)
        self._resume_banner.setVisible(True)

        if open_create_flow:
            QTimer.singleShot(0, self._handle_create_flow)

    def _handle_create_flow(self) -> None:
        """Open a pre-targeted create dialog for the document type from the resume context."""
        if self._resume_context is None:
            return
        active_company = self._active_company()
        if active_company is None:
            return
        document_type_code = str(self._resume_context.get("document_type_code", "")).lower()
        if document_type_code:
            sequence = DocumentSequenceDialog.create_sequence_for_type(
                self._service_registry,
                company_id=active_company.company_id,
                company_name=active_company.company_name,
                document_type_code=document_type_code,
                parent=self,
            )
        else:
            sequence = DocumentSequenceDialog.create_sequence(
                self._service_registry,
                company_id=active_company.company_id,
                company_name=active_company.company_name,
                parent=self,
            )
        if sequence is not None:
            self.reload_document_sequences(selected_sequence_id=sequence.id)

    def _handle_return_to_workflow(self) -> None:
        if self._resume_context is None:
            return
        resume_token = self._resume_context.get("resume_token")
        if not resume_token:
            self._dismiss_resume_banner()
            return
        token_data = self._service_registry.workflow_resume_service.peek_token(str(resume_token))
        self._resume_context = None
        self._resume_banner.setVisible(False)
        if token_data and token_data.origin_nav_id:
            self._service_registry.navigation_service.navigate(
                token_data.origin_nav_id,
                resume_token=str(resume_token),
            )

    def _dismiss_resume_banner(self) -> None:
        if self._resume_context:
            token = self._resume_context.get("resume_token")
            if token:
                self._service_registry.workflow_resume_service.discard_token(str(token))
        self._resume_context = None
        self._resume_banner.setVisible(False)
