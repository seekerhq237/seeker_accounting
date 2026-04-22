from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.ias_income_statement_mapping_dto import (
    IasIncomeStatementAccountOptionDTO,
    IasIncomeStatementMappingDTO,
    IasIncomeStatementMappingEditorDTO,
    ToggleIasIncomeStatementMappingStateCommand,
    UpsertIasIncomeStatementMappingCommand,
)
from seeker_accounting.modules.reporting.specs.ias_income_statement_spec import (
    IAS_SIGN_BEHAVIOR_INVERTED,
    IAS_SIGN_BEHAVIOR_NORMAL,
    is_relevant_income_statement_account,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class IasIncomeStatementMappingDialog(QDialog):
    """Dense mapping editor for the locked IAS/IFRS income statement builder."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._mapping_service = service_registry.ias_income_statement_mapping_service
        self._company_id = company_id
        self._company_name = company_name
        self._snapshot: IasIncomeStatementMappingEditorDTO | None = None
        self._selected_mapping_id: int | None = None

        self.setWindowTitle("IAS Mapping Editor")
        self.setMinimumSize(960, 620)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(8)
        root.addWidget(self._build_main_area(), 1)
        root.addWidget(self._build_status_bar())

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.reject)
        root.addWidget(button_box)

        self._reload_snapshot()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.ias_income_statement_mapping")

    @classmethod
    def manage_mappings(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, company_name, parent)
        dialog.exec()

    def _build_status_bar(self) -> QWidget:
        bar = QWidget(self)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(4, 0, 4, 2)
        layout.setSpacing(2)

        top_row = QWidget(bar)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        self._summary_label = QLabel(top_row)
        self._summary_label.setObjectName("PageSummary")
        top_layout.addWidget(self._summary_label, 1)

        self._issues_btn = QPushButton("\u26A0", top_row)
        self._issues_btn.setToolTip("View validation issues")
        self._issues_btn.setProperty("variant", "ghost")
        self._issues_btn.setFixedSize(24, 20)
        self._issues_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._issues_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._issues_btn.clicked.connect(self._show_issues_dialog)
        self._issues_btn.hide()
        top_layout.addWidget(self._issues_btn)

        layout.addWidget(top_row)

        self._status_label = QLabel(bar)
        self._status_label.setObjectName("PageSummary")
        layout.addWidget(self._status_label)
        return bar

    def _build_main_area(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_account_panel(), 4)

        right = QWidget(container)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        right_layout.addWidget(self._build_mapping_panel(), 3)
        right_layout.addWidget(self._build_editor_panel(), 2)
        layout.addWidget(right, 6)
        return container

    def _build_account_panel(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Accounts Available", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._account_search = QLineEdit(card)
        self._account_search.setPlaceholderText("Search by account code or account name")
        self._account_search.setClearButtonEnabled(True)
        self._account_search.textChanged.connect(self._filter_account_rows)
        layout.addWidget(create_field_block("Search", self._account_search))

        self._account_selection_label = QLabel("Selected accounts: 0", card)
        self._account_selection_label.setObjectName("PageSummary")
        layout.addWidget(self._account_selection_label)

        self._account_table = QTableWidget(card)
        self._account_table.setColumnCount(5)
        self._account_table.setHorizontalHeaderLabels(
            ("Code", "Account", "Default Sign", "Current Mapping", "Status")
        )
        configure_compact_table(self._account_table)
        self._account_table.setSortingEnabled(False)
        self._account_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._account_table.itemSelectionChanged.connect(self._on_account_selection_changed)
        layout.addWidget(self._account_table, 1)
        return card

    def _build_mapping_panel(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Current Mappings", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._mapping_table = QTableWidget(card)
        self._mapping_table.setColumnCount(5)
        self._mapping_table.setHorizontalHeaderLabels(("Order", "Account", "Mapping", "Sign", "State"))
        configure_compact_table(self._mapping_table)
        self._mapping_table.setSortingEnabled(False)
        self._mapping_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._mapping_table.itemSelectionChanged.connect(self._on_mapping_selection_changed)
        self._mapping_table.cellDoubleClicked.connect(self._on_mapping_double_clicked)
        layout.addWidget(self._mapping_table, 1)
        return card

    def _build_editor_panel(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Mapping Editor", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._section_combo = QComboBox(card)
        self._section_combo.currentIndexChanged.connect(self._on_section_changed)
        grid.addWidget(create_field_block("Section", self._section_combo), 0, 0)

        self._subsection_combo = QComboBox(card)
        self._subsection_combo.setEnabled(False)
        grid.addWidget(create_field_block("Subsection", self._subsection_combo), 0, 1)

        self._sign_combo = QComboBox(card)
        self._sign_combo.addItem("Normal", IAS_SIGN_BEHAVIOR_NORMAL)
        self._sign_combo.addItem("Inverted", IAS_SIGN_BEHAVIOR_INVERTED)
        grid.addWidget(create_field_block("Sign Behavior", self._sign_combo), 1, 0)

        self._default_sign_value = QLabel("Default sign: -", card)
        self._default_sign_value.setObjectName("PageSummary")
        grid.addWidget(create_field_block("Default Sign Suggestion", self._default_sign_value), 1, 1)

        self._display_order_spin = QSpinBox(card)
        self._display_order_spin.setRange(1, 9999)
        self._display_order_spin.setSingleStep(10)
        self._display_order_spin.setValue(10)
        grid.addWidget(create_field_block("Display Order", self._display_order_spin), 2, 0)

        self._active_check = QCheckBox("Active", card)
        self._active_check.setChecked(True)
        grid.addWidget(create_field_block("State", self._active_check), 2, 1)

        layout.addLayout(grid)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        self._save_button = QPushButton("Assign Selected Accounts", actions)
        self._save_button.setProperty("variant", "primary")
        self._save_button.clicked.connect(self._save_mapping)
        actions_layout.addWidget(self._save_button)

        self._toggle_button = QPushButton("Deactivate Mapping", actions)
        self._toggle_button.setProperty("variant", "secondary")
        self._toggle_button.clicked.connect(self._toggle_selected_mapping)
        actions_layout.addWidget(self._toggle_button)

        self._clear_button = QPushButton("Clear Editor", actions)
        self._clear_button.setProperty("variant", "ghost")
        self._clear_button.clicked.connect(self._clear_editor)
        actions_layout.addWidget(self._clear_button)

        self._refresh_button = QPushButton("Refresh", actions)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self._reload_snapshot)
        actions_layout.addWidget(self._refresh_button)
        actions_layout.addStretch(1)
        layout.addWidget(actions)
        return card

    def _reload_snapshot(self, preserve_mapping_id: int | None = None, *_args) -> None:
        if isinstance(preserve_mapping_id, bool):
            preserve_mapping_id = None
        try:
            self._snapshot = self._mapping_service.get_editor_snapshot(self._company_id)
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "IAS Mapping Editor", str(exc))
            return

        self._populate_section_combo()
        self._populate_account_table()
        self._populate_mapping_table()
        self._update_summary_band()

        if preserve_mapping_id is not None:
            self._select_mapping_row(preserve_mapping_id)
        elif self._mapping_table.rowCount() > 0:
            first_mapping = self._snapshot.mappings[0]
            self._select_mapping_row(first_mapping.id)
        else:
            self._clear_editor()

    def _populate_section_combo(self) -> None:
        self._section_combo.blockSignals(True)
        self._section_combo.clear()
        if self._snapshot is not None:
            for section in self._section_options():
                self._section_combo.addItem(section.display_path, section.section_code)
        self._section_combo.blockSignals(False)
        self._on_section_changed()

    def _section_options(self) -> tuple[object, ...]:
        if self._snapshot is None:
            return ()
        return tuple(
            section
            for section in self._snapshot.sections
            if section.is_mapping_target or section.section_code == "OPERATING_EXPENSES"
        )

    def _populate_account_table(self) -> None:
        if self._snapshot is None:
            return
        self._account_table.setRowCount(0)
        for option in self._snapshot.account_options:
            row = self._account_table.rowCount()
            self._account_table.insertRow(row)
            self._set_table_item(self._account_table, row, 0, option.account_code, option.account_id)
            self._set_table_item(self._account_table, row, 1, option.account_name)
            self._set_table_item(self._account_table, row, 2, self._sign_label(option.default_sign_behavior_code))
            self._set_table_item(self._account_table, row, 3, self._current_mapping_label(option))
            self._set_table_item(self._account_table, row, 4, self._account_state_label(option))
        self._account_table.resizeColumnsToContents()
        self._filter_account_rows()

    def _populate_mapping_table(self) -> None:
        if self._snapshot is None:
            return
        self._mapping_table.setRowCount(0)
        for mapping in self._snapshot.mappings:
            row = self._mapping_table.rowCount()
            self._mapping_table.insertRow(row)
            self._set_table_item(self._mapping_table, row, 0, str(mapping.display_order), mapping.id)
            self._set_table_item(self._mapping_table, row, 1, f"{mapping.account_code}  {mapping.account_name}".strip())
            self._set_table_item(self._mapping_table, row, 2, self._mapping_target_label(mapping.section_code, mapping.subsection_code))
            self._set_table_item(self._mapping_table, row, 3, self._sign_label(mapping.sign_behavior_code))
            self._set_table_item(self._mapping_table, row, 4, "Active" if mapping.is_active else "Inactive")
        self._mapping_table.resizeColumnsToContents()

    def _update_summary_band(self) -> None:
        if self._snapshot is None:
            self._summary_label.setText("No mapping snapshot loaded.")
            self._status_label.setText("")
            self._issues_btn.hide()
            return
        issue_counts = self._issue_counts()
        summary = (
            f"{len(self._snapshot.mappings)} mapping rows \u2014 "
            f"{len(self._snapshot.unmapped_relevant_accounts)} unmapped relevant accounts"
        )
        if issue_counts["error"] or issue_counts["warning"]:
            summary = f"{summary} \u2014 {issue_counts['error']} errors, {issue_counts['warning']} warnings"
        else:
            summary = f"{summary} \u2014 No validation issues"
        self._summary_label.setText(summary)
        has_issues = bool(self._snapshot.issues)
        self._issues_btn.setVisible(has_issues)
        if not has_issues:
            self._status_label.setText(
                "Select accounts on the left, choose a section and sign behavior, then save the mapping."
            )

    def _show_issues_dialog(self) -> None:
        if self._snapshot is None or not self._snapshot.issues:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Validation Issues")
        dlg.setModal(True)
        dlg.resize(520, 340)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QLabel(f"{len(self._snapshot.issues)} issue(s) found", dlg)
        header.setObjectName("PageSummary")
        layout.addWidget(header)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        for issue in self._snapshot.issues:
            severity_tag = issue.severity_code.upper()
            row_label = QLabel(f"<b>[{severity_tag}]</b> {issue.message}", content)
            row_label.setWordWrap(True)
            row_label.setTextFormat(Qt.TextFormat.RichText)
            content_layout.addWidget(row_label)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        close_box.rejected.connect(dlg.reject)
        layout.addWidget(close_box)
        dlg.exec()

    def _issue_counts(self) -> dict[str, int]:
        counts = {"error": 0, "warning": 0, "info": 0}
        if self._snapshot is None:
            return counts
        for issue in self._snapshot.issues:
            counts[issue.severity_code] = counts.get(issue.severity_code, 0) + 1
        return counts

    def _selected_account_ids(self) -> tuple[int, ...]:
        ids: list[int] = []
        for index in self._account_table.selectionModel().selectedRows():
            item = self._account_table.item(index.row(), 0)
            if item is None:
                continue
            account_id = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(account_id, int):
                ids.append(account_id)
        return tuple(ids)

    def _selected_mapping(self) -> IasIncomeStatementMappingDTO | None:
        if self._snapshot is None:
            return None
        row = self._mapping_table.currentRow()
        if row < 0:
            return None
        item = self._mapping_table.item(row, 0)
        if item is None:
            return None
        mapping_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(mapping_id, int):
            return None
        return next((mapping for mapping in self._snapshot.mappings if mapping.id == mapping_id), None)

    def _on_account_selection_changed(self) -> None:
        selected_ids = self._selected_account_ids()
        self._account_selection_label.setText(f"Selected accounts: {len(selected_ids)}")
        self._update_default_sign_hint()
        if len(selected_ids) == 1:
            self._sync_editor_to_account(selected_ids[0])

    def _filter_account_rows(self, *_args) -> None:
        if self._snapshot is None:
            return
        needle = self._account_search.text().strip().lower()
        for row, option in enumerate(self._snapshot.account_options):
            visible = not needle or needle in option.account_code.lower() or needle in option.account_name.lower()
            self._account_table.setRowHidden(row, not visible)

    def _on_mapping_selection_changed(self) -> None:
        mapping = self._selected_mapping()
        self._toggle_button.setText("Deactivate Mapping" if mapping is None or mapping.is_active else "Reactivate Mapping")

    def _on_mapping_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        item = self._mapping_table.item(row, 0)
        if item is None:
            return
        mapping_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(mapping_id, int):
            self._load_mapping_into_editor(mapping_id)

    def _load_mapping_into_editor(self, mapping_id: int) -> None:
        if self._snapshot is None:
            return
        mapping = next((item for item in self._snapshot.mappings if item.id == mapping_id), None)
        if mapping is None:
            return
        self._selected_mapping_id = mapping.id
        self._select_section(mapping.section_code)
        self._select_subsection(mapping.subsection_code)
        self._select_sign(mapping.sign_behavior_code)
        self._display_order_spin.setValue(mapping.display_order)
        self._active_check.setChecked(mapping.is_active)
        self._select_account_rows((mapping.account_id,))
        self._update_default_sign_hint(mapping.default_sign_behavior_code)
        self._status_label.setText(f"Loaded mapping for {mapping.account_code} into the editor.")

    def _select_account_rows(self, account_ids: tuple[int, ...]) -> None:
        self._account_table.clearSelection()
        for row in range(self._account_table.rowCount()):
            item = self._account_table.item(row, 0)
            if item is None:
                continue
            account_id = item.data(Qt.ItemDataRole.UserRole)
            if account_id in account_ids:
                self._account_table.selectRow(row)

    def _sync_editor_to_account(self, account_id: int) -> None:
        if self._snapshot is None:
            return
        option = next((item for item in self._snapshot.account_options if item.account_id == account_id), None)
        if option is None:
            return
        if option.mapped_mapping_id is not None:
            mapping = next((item for item in self._snapshot.mappings if item.id == option.mapped_mapping_id), None)
            if mapping is not None:
                self._selected_mapping_id = mapping.id
                self._select_section(mapping.section_code)
                self._select_subsection(mapping.subsection_code)
                self._select_sign(mapping.sign_behavior_code)
                self._display_order_spin.setValue(mapping.display_order)
                self._active_check.setChecked(mapping.is_active)
                self._update_default_sign_hint(mapping.default_sign_behavior_code)
                return
        self._selected_mapping_id = None
        self._select_sign(option.default_sign_behavior_code)
        self._display_order_spin.setValue(10)
        self._active_check.setChecked(True)
        self._update_default_sign_hint(option.default_sign_behavior_code)

    def _select_section(self, section_code: str | None) -> None:
        if section_code is None:
            return
        index = self._section_combo.findData(section_code)
        if index >= 0:
            self._section_combo.blockSignals(True)
            self._section_combo.setCurrentIndex(index)
            self._section_combo.blockSignals(False)
        self._on_section_changed()

    def _select_subsection(self, subsection_code: str | None) -> None:
        self._subsection_combo.blockSignals(True)
        if subsection_code is None:
            if self._subsection_combo.count() > 0:
                self._subsection_combo.setCurrentIndex(0)
            self._subsection_combo.blockSignals(False)
            return
        index = self._subsection_combo.findData(subsection_code)
        if index >= 0:
            self._subsection_combo.setCurrentIndex(index)
        self._subsection_combo.blockSignals(False)

    def _select_sign(self, sign_behavior_code: str | None) -> None:
        index = self._sign_combo.findData(sign_behavior_code or IAS_SIGN_BEHAVIOR_NORMAL)
        self._sign_combo.setCurrentIndex(index if index >= 0 else 0)

    def _on_section_changed(self, _index: int | None = None) -> None:
        section_code = self._section_combo.currentData()
        self._subsection_combo.blockSignals(True)
        self._subsection_combo.clear()
        self._subsection_combo.blockSignals(False)
        self._subsection_combo.setEnabled(False)

        if not isinstance(section_code, str) or self._snapshot is None:
            self._update_default_sign_hint()
            return

        if section_code != "OPERATING_EXPENSES":
            self._update_default_sign_hint()
            return

        subsections = [
            section
            for section in self._snapshot.sections
            if section.parent_section_code == "OPERATING_EXPENSES"
        ]
        self._subsection_combo.blockSignals(True)
        for subsection in subsections:
            self._subsection_combo.addItem(subsection.display_path, subsection.section_code)
        self._subsection_combo.blockSignals(False)
        self._subsection_combo.setEnabled(bool(subsections))
        if self._subsection_combo.count() > 0:
            self._subsection_combo.setCurrentIndex(0)
        self._update_default_sign_hint()

    def _update_default_sign_hint(self, override_sign: str | None = None) -> None:
        suggested = override_sign
        selected_ids = self._selected_account_ids()
        if suggested is None:
            if len(selected_ids) == 1 and self._snapshot is not None:
                option = next(
                    (item for item in self._snapshot.account_options if item.account_id == selected_ids[0]),
                    None,
                )
                if option is not None:
                    suggested = option.default_sign_behavior_code
        if suggested is None and not selected_ids and self._selected_mapping_id is not None and self._snapshot is not None:
            mapping = next((item for item in self._snapshot.mappings if item.id == self._selected_mapping_id), None)
            if mapping is not None:
                suggested = mapping.default_sign_behavior_code
        self._default_sign_value.setText(
            "Default sign: -" if suggested is None else f"Default sign: {self._sign_label(suggested)}"
        )

    def _current_mapping_label(self, option: IasIncomeStatementAccountOptionDTO) -> str:
        if option.mapped_mapping_id is None:
            return "Unmapped"
        label = self._mapping_target_label(option.mapped_section_code, option.mapped_subsection_code)
        if option.mapped_is_active is False:
            return f"Inactive: {label}"
        return label

    def _account_state_label(self, option: IasIncomeStatementAccountOptionDTO) -> str:
        parts = ["Active" if option.is_active else "Inactive"]
        if not option.allow_manual_posting:
            parts.append("Control-only")
        if is_relevant_income_statement_account(
            account_class_code=option.account_class_code,
            account_type_section_code=option.account_type_section_code,
            account_code=option.account_code,
        ):
            parts.append("Relevant")
        return " / ".join(parts)

    def _mapping_target_label(self, section_code: str | None, subsection_code: str | None) -> str:
        if self._snapshot is None or section_code is None:
            return "Unknown"
        section = next((item for item in self._snapshot.sections if item.section_code == section_code), None)
        if section is None:
            return section_code
        if subsection_code:
            subsection = next((item for item in self._snapshot.sections if item.section_code == subsection_code), None)
            if subsection is not None:
                return f"{section.section_label} / {subsection.section_label}"
            return f"{section.section_label} / {subsection_code}"
        return section.section_label

    @staticmethod
    def _sign_label(sign_behavior_code: str | None) -> str:
        code = (sign_behavior_code or IAS_SIGN_BEHAVIOR_NORMAL).strip().lower()
        return "Inverted" if code == IAS_SIGN_BEHAVIOR_INVERTED else "Normal"

    def _save_mapping(self, *_args) -> None:
        selected_ids = self._selected_account_ids()
        if not selected_ids and self._selected_mapping_id is not None and self._snapshot is not None:
            mapping = next((item for item in self._snapshot.mappings if item.id == self._selected_mapping_id), None)
            if mapping is not None:
                selected_ids = (mapping.account_id,)
        if not selected_ids:
            show_info(self, "IAS Mapping Editor", "Select one or more accounts before saving a mapping.")
            return

        section_code = self._section_combo.currentData()
        sign_behavior_code = self._sign_combo.currentData()
        subsection_code = self._subsection_combo.currentData() if self._subsection_combo.isEnabled() else None
        if not isinstance(section_code, str):
            show_error(self, "IAS Mapping Editor", "Select a section before saving.")
            return
        if not isinstance(sign_behavior_code, str):
            show_error(self, "IAS Mapping Editor", "Select a sign behavior before saving.")
            return
        if subsection_code is not None and not isinstance(subsection_code, str):
            subsection_code = None

        try:
            self._mapping_service.upsert_mappings(
                self._company_id,
                UpsertIasIncomeStatementMappingCommand(
                    section_code=section_code,
                    subsection_code=subsection_code,
                    account_ids=selected_ids,
                    sign_behavior_code=sign_behavior_code,
                    display_order=self._display_order_spin.value(),
                    is_active=self._active_check.isChecked(),
                ),
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "IAS Mapping Editor", str(exc))
            return

        self._status_label.setText("Mappings saved successfully.")
        self._reload_snapshot()
        self._select_account_rows(selected_ids)

    def _toggle_selected_mapping(self, *_args) -> None:
        mapping = self._selected_mapping()
        if mapping is None:
            show_info(self, "IAS Mapping Editor", "Select a mapping row to toggle its state.")
            return

        try:
            self._mapping_service.toggle_mapping_state(
                self._company_id,
                ToggleIasIncomeStatementMappingStateCommand(
                    mapping_id=mapping.id,
                    is_active=not mapping.is_active,
                ),
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "IAS Mapping Editor", str(exc))
            return

        self._status_label.setText(
            f"Mapping for {mapping.account_code} is now {'active' if not mapping.is_active else 'inactive'}."
        )
        self._reload_snapshot(preserve_mapping_id=mapping.id)

    def _clear_editor(self, *_args) -> None:
        self._selected_mapping_id = None
        self._account_table.clearSelection()
        self._section_combo.setCurrentIndex(0 if self._section_combo.count() > 0 else -1)
        self._subsection_combo.clear()
        self._subsection_combo.setEnabled(False)
        self._select_sign(IAS_SIGN_BEHAVIOR_NORMAL)
        self._display_order_spin.setValue(10)
        self._active_check.setChecked(True)
        self._account_selection_label.setText("Selected accounts: 0")
        self._update_default_sign_hint()

    def _select_mapping_row(self, mapping_id: int) -> None:
        for row in range(self._mapping_table.rowCount()):
            item = self._mapping_table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == mapping_id:
                self._mapping_table.selectRow(row)
                self._load_mapping_into_editor(mapping_id)
                return

    def _set_table_item(
        self,
        table: QTableWidget,
        row: int,
        column: int,
        text: str,
        user_data: object | None = None,
    ) -> None:
        item = QTableWidgetItem(text)
        if column != 0:
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if user_data is not None:
            item.setData(Qt.ItemDataRole.UserRole, user_data)
        table.setItem(row, column, item)
