from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.fixed_assets.ui.depreciation_run_dialog import DepreciationRunDialog
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    run_document_sequence_preflight,
)


RUN_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="run_number", title="Run Number"),
    DataTableColumn(key="run_date", title="Run Date"),
    DataTableColumn(key="period_end_date", title="Period End"),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="asset_count", title="Assets"),
    DataTableColumn(key="total_depreciation", title="Total Depreciation"),
    DataTableColumn(key="posted_at", title="Posted At"),
)


class DepreciationRunsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._rows = []
        self._pending_resume_payload: ResumeTokenPayload | None = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    def reload(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            self._rows = []
            self._model.removeRows(0, self._model.rowCount())
            self._count_label.setText("")
            self._stack.setCurrentWidget(self._no_company_state)
            return
        try:
            self._rows = self._service_registry.depreciation_run_service.list_depreciation_runs(
                active_company.company_id
            )
        except Exception as exc:
            self._rows = []
            self._model.removeRows(0, self._model.rowCount())
            self._stack.setCurrentWidget(self._empty_state)
            show_error(self, "Depreciation Runs", f"Could not load data.\n\n{exc}")
            return
        self._populate()
        self._sync_stack(active_company, self._rows)
        self._update_count_label()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel('Depreciation Runs', card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._count_label = QLabel(card)
        self._count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._count_label)

        layout.addStretch(1)
        self._new_btn = QPushButton("New Run", card)
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.clicked.connect(self._on_new)
        layout.addWidget(self._new_btn)

        self._open_btn = QPushButton("Open", card)
        self._open_btn.setProperty("variant", "secondary")
        self._open_btn.clicked.connect(self._on_open)
        layout.addWidget(self._open_btn)

        refresh_btn = QPushButton("Refresh", card)
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(self.reload)
        layout.addWidget(refresh_btn)
        return card

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_company_state = self._build_no_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = QStandardItemModel(0, len(RUN_COLUMNS), self)
        self._model.setHorizontalHeaderLabels([c.title for c in RUN_COLUMNS])

        self._table = DataTable(
            columns=RUN_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No depreciation runs to display.",
            parent=card,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 3)
        self._table.row_activated.connect(lambda _r: self._on_open())
        layout.addWidget(self._table)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("No depreciation runs yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel(
            "Create a new depreciation run to compute and post monthly depreciation for active assets.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addStretch(1)
        return card

    def _build_no_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)
        summary = QLabel("Depreciation runs are company-scoped.", card)
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        actions = QWidget(card)
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 4, 0, 0)
        al.addStretch(1)
        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------

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
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _populate(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for row in self._rows:
            assets_item = QStandardItem(str(row.asset_count))
            assets_item.setEditable(False)
            assets_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            posted_text = str(row.posted_at.date()) if row.posted_at else "—"
            items = [
                self._make_item(row.run_number or "(draft)", user_data=row.id),
                self._make_item(row.run_date),
                self._make_item(row.period_end_date),
                self._make_item(row.status_code),
                assets_item,
                self._make_numeric(row.total_depreciation),
                self._make_item(posted_text),
            ]
            self._model.appendRow(items)

    def _update_count_label(self) -> None:
        total = len(self._rows)
        self._count_label.setText(
            f"{total} record" if total == 1 else f"{total} records"
        )

    def _selected_row(self):
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_new(self) -> None:
        company = self._active_company()
        if company is None:
            show_error(self, "Depreciation Runs", "Select an active company first.")
            return
        if not run_document_sequence_preflight(
            self, self._service_registry,
            company.company_id, company.company_name,
            "depreciation_run", nav_ids.DEPRECIATION_RUNS,
        ):
            return
        dialog = DepreciationRunDialog(
            self._service_registry, company.company_id, company.company_name, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # After generating a draft, open it immediately for review/posting
            if dialog._run_id is not None:
                self._open_run(company, dialog._run_id)
            else:
                self.reload()

    def _on_open(self) -> None:
        company = self._active_company()
        if company is None:
            return
        row = self._selected_row()
        if row is None:
            return
        self._open_run(company, row.id)

    def _open_run(self, company: ActiveCompanyDTO, run_id: int) -> None:
        dialog = DepreciationRunDialog(
            self._service_registry, company.company_id, company.company_name,
            run_id=run_id, parent=self,
        )
        dialog.exec()
        self.reload()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _sync_stack(self, company: ActiveCompanyDTO | None, rows: list) -> None:
        if company is None:
            self._stack.setCurrentWidget(self._no_company_state)
        elif rows:
            self._stack.setCurrentWidget(self._table_surface)
        else:
            self._stack.setCurrentWidget(self._empty_state)

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        token_payload = consume_resume_payload_for_workflows(
            context=context,
            service_registry=self._service_registry,
            allowed_workflow_keys=("depreciation_run.preflight", "depreciation_run.post"),
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
        if payload.workflow_key == "depreciation_run.post":
            run_id_raw = payload.payload.get("document_id") if payload.payload else None
            if run_id_raw is not None:
                try:
                    self._open_run(active_company, int(run_id_raw))
                except (TypeError, ValueError):
                    self.reload()
            else:
                self.reload()
            return
        self._on_new()
