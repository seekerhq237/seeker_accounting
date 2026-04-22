from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.fixed_assets.dto.depreciation_commands import CreateDepreciationRunCommand
from seeker_accounting.modules.fixed_assets.dto.depreciation_dto import AssetDepreciationRunDetailDTO
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver
from seeker_accounting.shared.ui.guided_resolution_coordinator import GuidedResolutionCoordinator
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class DepreciationRunDialog(QDialog):
    """Dialog for creating a draft depreciation run and optionally posting it.

    When run_id is None: shows a date picker and generates a new draft on confirm.
    When run_id is provided: loads and displays an existing run with post/cancel actions.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        run_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._run_id = run_id
        self._run_dto: AssetDepreciationRunDetailDTO | None = None
        self._posted = False

        is_new = run_id is None
        self.setWindowTitle(f"{'New Depreciation Run' if is_new else 'Depreciation Run'} — {company_name}")
        self.setModal(True)
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Date pickers (only visible for new run)
        if is_new:
            date_card = QFrame(self)
            date_card.setObjectName("PageCard")
            date_form_layout = QHBoxLayout(date_card)
            date_form_layout.setContentsMargins(8, 4, 8, 4)
            date_form_layout.setSpacing(24)

            run_date_container = QWidget(date_card)
            rdl = QVBoxLayout(run_date_container)
            rdl.setContentsMargins(0, 0, 0, 0)
            rdl.setSpacing(4)
            rdl.addWidget(QLabel("Run Date *", run_date_container))
            self._run_date_input = QDateEdit(run_date_container)
            self._run_date_input.setCalendarPopup(True)
            self._run_date_input.setDate(QDate.currentDate())
            rdl.addWidget(self._run_date_input)
            date_form_layout.addWidget(run_date_container)

            period_end_container = QWidget(date_card)
            pel = QVBoxLayout(period_end_container)
            pel.setContentsMargins(0, 0, 0, 0)
            pel.setSpacing(4)
            pel.addWidget(QLabel("Period End Date *", period_end_container))
            self._period_end_input = QDateEdit(period_end_container)
            self._period_end_input.setCalendarPopup(True)
            self._period_end_input.setDate(QDate.currentDate())
            pel.addWidget(self._period_end_input)
            date_form_layout.addWidget(period_end_container)
            date_form_layout.addStretch(1)
            layout.addWidget(date_card)

        # Run summary card
        self._summary_card = QFrame(self)
        self._summary_card.setObjectName("PageCard")
        sum_layout = QVBoxLayout(self._summary_card)
        sum_layout.setContentsMargins(8, 4, 8, 4)
        sum_layout.setSpacing(6)
        sum_hdr = QLabel("Run Summary", self._summary_card)
        sum_hdr.setObjectName("CardTitle")
        sum_layout.addWidget(sum_hdr)
        kv_row = QWidget(self._summary_card)
        kv_layout = QHBoxLayout(kv_row)
        kv_layout.setContentsMargins(0, 0, 0, 0)
        kv_layout.setSpacing(32)
        self._lbl_run_number = self._make_kv("Run Number", "—")
        self._lbl_run_date = self._make_kv("Run Date", "—")
        self._lbl_period_end = self._make_kv("Period End", "—")
        self._lbl_status = self._make_kv("Status", "—")
        self._lbl_assets = self._make_kv("Assets", "—")
        self._lbl_total = self._make_kv("Total Depreciation", "—")
        for w in (self._lbl_run_number, self._lbl_run_date, self._lbl_period_end,
                  self._lbl_status, self._lbl_assets, self._lbl_total):
            kv_layout.addWidget(w)
        kv_layout.addStretch(1)
        sum_layout.addWidget(kv_row)
        layout.addWidget(self._summary_card)

        # Lines table card
        lines_card = QFrame(self)
        lines_card.setObjectName("PageCard")
        lines_layout = QVBoxLayout(lines_card)
        lines_layout.setContentsMargins(8, 6, 8, 6)
        lines_layout.setSpacing(10)
        lines_hdr = QLabel("Asset Lines", lines_card)
        lines_hdr.setObjectName("CardTitle")
        lines_layout.addWidget(lines_hdr)

        self._table = QTableWidget(lines_card)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels((
            "Asset Number", "Asset Name",
            "Depreciation", "Accum. Depr. After", "NBV After",
        ))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lines_layout.addWidget(self._table)
        layout.addWidget(lines_card, 1)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # Buttons
        if is_new:
            buttons = QDialogButtonBox(self)
            self._generate_btn = buttons.addButton("Generate Draft", QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
            self._generate_btn.clicked.connect(self._on_generate)
            buttons.rejected.connect(self.reject)
        else:
            buttons_widget = QWidget(self)
            btn_layout = QHBoxLayout(buttons_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(8)
            btn_layout.addStretch(1)
            self._post_btn = QPushButton("Post Run", buttons_widget)
            self._post_btn.setProperty("variant", "primary")
            self._post_btn.clicked.connect(self._on_post)
            btn_layout.addWidget(self._post_btn)
            self._cancel_run_btn = QPushButton("Cancel Run", buttons_widget)
            self._cancel_run_btn.setProperty("variant", "secondary")
            self._cancel_run_btn.clicked.connect(self._on_cancel_run)
            btn_layout.addWidget(self._cancel_run_btn)
            close_btn = QPushButton("Close", buttons_widget)
            close_btn.setProperty("variant", "ghost")
            close_btn.clicked.connect(self.reject)
            btn_layout.addWidget(close_btn)
            buttons = buttons_widget

        layout.addWidget(buttons)

        if not is_new:
            self._load_run()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.depreciation_run")

    @property
    def posted(self) -> bool:
        return self._posted

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_kv(self, label: str, value: str) -> QWidget:
        container = QWidget(self)
        lyt = QVBoxLayout(container)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(2)
        lbl = QLabel(label, container)
        lbl.setProperty("role", "caption")
        lyt.addWidget(lbl)
        val = QLabel(value, container)
        val.setObjectName("ToolbarValue")
        val.setProperty("_kv_value", True)
        lyt.addWidget(val)
        return container

    def _set_kv(self, widget: QWidget, value: str) -> None:
        for child in widget.findChildren(QLabel):
            if child.property("_kv_value"):
                child.setText(value)
                return

    def _load_run(self) -> None:
        if self._run_id is None:
            return
        try:
            dto = self._service_registry.depreciation_run_service.get_depreciation_run(
                self._company_id, self._run_id
            )
        except Exception as exc:
            show_error(self, "Depreciation Run", str(exc))
            return
        self._run_dto = dto
        self._refresh_summary(dto)
        self._populate_lines(dto)
        self._sync_buttons(dto)

    def _refresh_summary(self, dto: AssetDepreciationRunDetailDTO) -> None:
        self._set_kv(self._lbl_run_number, dto.run_number or "(unassigned)")
        self._set_kv(self._lbl_run_date, str(dto.run_date))
        self._set_kv(self._lbl_period_end, str(dto.period_end_date))
        self._set_kv(self._lbl_status, dto.status_code.replace("_", " ").title())
        self._set_kv(self._lbl_assets, str(dto.asset_count))
        self._set_kv(self._lbl_total, f"{dto.total_depreciation:,.2f}")

    def _populate_lines(self, dto: AssetDepreciationRunDetailDTO) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for line in dto.lines:
            ri = self._table.rowCount()
            self._table.insertRow(ri)
            self._table.setItem(ri, 0, QTableWidgetItem(line.asset_number))
            self._table.setItem(ri, 1, QTableWidgetItem(line.asset_name))
            for col, val in enumerate((
                line.depreciation_amount,
                line.accumulated_depreciation_after,
                line.net_book_value_after,
            ), start=2):
                item = QTableWidgetItem(f"{val:,.2f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(ri, col, item)
        self._table.resizeColumnsToContents()
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)
        self._table.setSortingEnabled(True)

    def _sync_buttons(self, dto: AssetDepreciationRunDetailDTO) -> None:
        if not hasattr(self, "_post_btn"):
            return
        is_draft = dto.status_code == "draft"
        self._post_btn.setEnabled(is_draft)
        self._cancel_run_btn.setEnabled(is_draft)

    def _on_generate(self) -> None:
        self._error_label.hide()
        run_date: date = self._run_date_input.date().toPython()
        period_end: date = self._period_end_input.date().toPython()
        try:
            dto = self._service_registry.depreciation_run_service.create_run(
                self._company_id,
                CreateDepreciationRunCommand(run_date=run_date, period_end_date=period_end),
            )
        except (ValidationError, Exception) as exc:
            self._show_error(str(exc))
            return
        self._run_dto = dto
        self._run_id = dto.id
        self._refresh_summary(dto)
        self._populate_lines(dto)
        self.accept()

    def _on_post(self) -> None:
        if self._run_dto is None or self._run_id is None:
            return
        if self._run_dto.status_code != "draft":
            show_error(self, "Depreciation Run", "Only draft runs can be posted.")
            return
        reply = QMessageBox.question(
            self, "Post Depreciation Run",
            f"Post depreciation run for period ending {self._run_dto.period_end_date}?\n\n"
            "This will create a journal entry and cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._error_label.hide()
        try:
            self._service_registry.depreciation_posting_service.post_run(
                self._company_id,
                self._run_id,
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
                coordinator = GuidedResolutionCoordinator(
                    resolver=ErrorResolutionResolver(),
                    workflow_resume_service=self._service_registry.workflow_resume_service,
                    navigation_service=self._service_registry.navigation_service,
                )
                result = coordinator.handle_exception(
                    parent=self,
                    error=exc,
                    workflow_key="depreciation_run.post",
                    workflow_snapshot=lambda: {"document_id": self._run_id},
                    origin_nav_id=nav_ids.DEPRECIATION_RUNS,
                    resolution_context={"company_name": self._company_name},
                )
                if result.handled and result.selected_action and result.selected_action.nav_id:
                    self.reject()
                    return
                self._show_error(str(exc))
                return
            self._show_error(str(exc))
            return
        except (ConflictError, Exception) as exc:
            self._show_error(str(exc))
            return
        self._posted = True
        self._load_run()

    def _on_cancel_run(self) -> None:
        if self._run_id is None:
            return
        reply = QMessageBox.question(
            self, "Cancel Run",
            "Cancel this depreciation run? The draft will be marked cancelled.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.depreciation_run_service.cancel_run(
                self._company_id, self._run_id
            )
        except (ValidationError, Exception) as exc:
            self._show_error(str(exc))
            return
        self._load_run()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
