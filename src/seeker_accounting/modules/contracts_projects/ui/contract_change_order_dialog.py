from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.contracts_projects.dto.contract_change_order_commands import (
    ApproveContractChangeOrderCommand,
    CreateContractChangeOrderCommand,
    RejectContractChangeOrderCommand,
    SubmitContractChangeOrderCommand,
    UpdateContractChangeOrderCommand,
)
from seeker_accounting.modules.contracts_projects.dto.contract_change_order_dto import (
    ContractChangeOrderDetailDTO,
    ContractChangeOrderListItemDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, apply_status_chip_to_column


# ── Change Order Form Dialog ──────────────────────────────────────────────


class ContractChangeOrderFormDialog(BaseDialog):
    """Create or edit a single contract change order."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        contract_number: str,
        change_order_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._contract_id = contract_id
        self._change_order_id = change_order_id
        self._saved: ContractChangeOrderDetailDTO | None = None

        title = "New Change Order" if change_order_id is None else "Edit Change Order"
        super().__init__(title, parent, help_key="dialog.contract_change_order")
        self.setObjectName("ContractChangeOrderFormDialog")
        apply_window_size(self, "modules.contracts.projects.ui.contract.change.order.dialog.0")

        intro = QLabel(
            f"Change order for contract {contract_number}.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_form_section())
        self.body_layout.addWidget(self._build_notes_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)

        save_btn = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setText("Create" if change_order_id is None else "Save Changes")
            save_btn.setProperty("variant", "primary")

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")

        if self._change_order_id is not None:
            self._load_change_order()

    @property
    def saved_change_order(self) -> ContractChangeOrderDetailDTO | None:
        return self._saved

    @classmethod
    def create_change_order(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        contract_number: str,
        parent: QWidget | None = None,
    ) -> ContractChangeOrderDetailDTO | None:
        dialog = cls(
            service_registry, company_id, contract_id, contract_number, parent=parent
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_change_order
        return None

    @classmethod
    def edit_change_order(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        contract_number: str,
        change_order_id: int,
        parent: QWidget | None = None,
    ) -> ContractChangeOrderDetailDTO | None:
        dialog = cls(
            service_registry, company_id, contract_id, contract_number,
            change_order_id=change_order_id, parent=parent,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_change_order
        return None

    # ------------------------------------------------------------------
    # Form sections
    # ------------------------------------------------------------------

    def _build_form_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Change Order Details", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._number_edit = QLineEdit(card)
        self._number_edit.setPlaceholderText("CO-001")
        grid.addWidget(create_field_block("Change Order Number", self._number_edit), 0, 0)

        self._change_type_combo = QComboBox(card)
        self._change_type_combo.addItem("Scope", "scope")
        self._change_type_combo.addItem("Price", "price")
        self._change_type_combo.addItem("Time", "time")
        self._change_type_combo.addItem("Mixed", "mixed")
        grid.addWidget(create_field_block("Change Type", self._change_type_combo), 0, 1)

        self._date_edit = QDateEdit(card)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDate(date.today())
        grid.addWidget(create_field_block("Change Order Date", self._date_edit), 1, 0)

        self._effective_date_edit = QDateEdit(card)
        self._effective_date_edit.setCalendarPopup(True)
        self._effective_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._effective_date_edit.setDate(date.today())
        grid.addWidget(create_field_block("Effective Date", self._effective_date_edit, "Optional"), 1, 1)

        self._amount_delta_edit = QLineEdit(card)
        self._amount_delta_edit.setPlaceholderText("0.00")
        grid.addWidget(
            create_field_block("Amount Delta", self._amount_delta_edit, "Positive or negative. Leave blank for none."),
            2, 0,
        )

        self._days_extension_spin = QSpinBox(card)
        self._days_extension_spin.setMinimum(0)
        self._days_extension_spin.setMaximum(9999)
        self._days_extension_spin.setValue(0)
        self._days_extension_spin.setSpecialValueText("None")
        grid.addWidget(create_field_block("Days Extension", self._days_extension_spin), 2, 1)

        layout.addLayout(grid)
        return card

    def _build_notes_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Description", card)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        self._description_edit = QPlainTextEdit(card)
        self._description_edit.setPlaceholderText("Describe this change order")
        self._description_edit.setFixedHeight(80)
        layout.addWidget(self._description_edit)
        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_change_order(self) -> None:
        try:
            co = self._service_registry.contract_change_order_service.get_change_order_detail(
                self._change_order_id or 0
            )
        except NotFoundError as exc:
            show_error(self, "Not Found", str(exc))
            self.reject()
            return

        self._number_edit.setText(co.change_order_number)
        self._number_edit.setReadOnly(True)
        idx = self._change_type_combo.findData(co.change_type_code)
        if idx >= 0:
            self._change_type_combo.setCurrentIndex(idx)
        if co.change_order_date:
            self._date_edit.setDate(co.change_order_date)
        if co.effective_date:
            self._effective_date_edit.setDate(co.effective_date)
        self._amount_delta_edit.setText(
            "" if co.contract_amount_delta is None else str(co.contract_amount_delta)
        )
        self._days_extension_spin.setValue(co.days_extension or 0)
        self._description_edit.setPlainText(co.description or "")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_decimal(self, text: str, field_name: str) -> Decimal | None:
        text = text.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValidationError(f"{field_name} must be a valid number.") from exc

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._set_error(None)

        number = self._number_edit.text().strip()
        if not number:
            self._set_error("Change order number is required.")
            return

        try:
            amount_delta = self._parse_decimal(self._amount_delta_edit.text(), "Amount delta")
        except ValidationError as exc:
            self._set_error(str(exc))
            return

        change_type = self._change_type_combo.currentData()
        co_date = self._date_edit.date().toPython()
        eff_date = self._effective_date_edit.date().toPython()
        days_ext = self._days_extension_spin.value() or None
        description = self._description_edit.toPlainText().strip() or None

        svc = self._service_registry.contract_change_order_service

        try:
            if self._change_order_id is None:
                result = svc.create_change_order(
                    CreateContractChangeOrderCommand(
                        company_id=self._company_id,
                        contract_id=self._contract_id,
                        change_order_number=number,
                        change_order_date=co_date,
                        change_type_code=change_type,
                        description=description,
                        contract_amount_delta=amount_delta,
                        days_extension=days_ext,
                        effective_date=eff_date,
                    )
                )
            else:
                result = svc.update_change_order(
                    self._change_order_id,
                    UpdateContractChangeOrderCommand(
                        change_order_date=co_date,
                        change_type_code=change_type,
                        description=description,
                        contract_amount_delta=amount_delta,
                        days_extension=days_ext,
                        effective_date=eff_date,
                    ),
                )
            self._saved = result
            self.accept()
        except (ValidationError, NotFoundError) as exc:
            self._set_error(str(exc))


# ── Change Orders List Dialog ─────────────────────────────────────────────


class ContractChangeOrdersDialog(BaseDialog):
    """List and manage change orders for a specific contract."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        contract_number: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"Change Orders — {contract_number}", parent, help_key="dialog.contract_change_order_list")
        self._service_registry = service_registry
        self._company_id = company_id
        self._contract_id = contract_id
        self._contract_number = contract_number
        self._change_orders: list[ContractChangeOrderListItemDTO] = []

        self.setObjectName("ContractChangeOrdersDialog")
        apply_window_size(self, "modules.contracts.projects.ui.contract.change.order.dialog.1")

        self.body_layout.addWidget(self._build_toolbar())
        self.body_layout.addWidget(self._build_table_card(), 1)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        close_btn = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setProperty("variant", "secondary")

        self._reload()

    @classmethod
    def manage_change_orders(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        contract_number: str,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, contract_id, contract_number, parent=parent)
        dialog.exec()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget(self)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._new_button = QPushButton("New Change Order", toolbar)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit", toolbar)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit)
        layout.addWidget(self._edit_button)

        self._submit_button = QPushButton("Submit", toolbar)
        self._submit_button.setProperty("variant", "secondary")
        self._submit_button.clicked.connect(self._submit_selected)
        layout.addWidget(self._submit_button)

        self._approve_button = QPushButton("Approve", toolbar)
        self._approve_button.setProperty("variant", "secondary")
        self._approve_button.clicked.connect(self._approve_selected)
        layout.addWidget(self._approve_button)

        self._reject_button = QPushButton("Reject", toolbar)
        self._reject_button.setProperty("variant", "secondary")
        self._reject_button.clicked.connect(self._reject_selected)
        layout.addWidget(self._reject_button)

        self._cancel_button = QPushButton("Cancel CO", toolbar)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected)
        layout.addWidget(self._cancel_button)

        layout.addStretch(1)

        self._count_label = QLabel(toolbar)
        self._count_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._count_label)

        return toolbar

    def _build_table_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._model = QStandardItemModel(0, 7, card)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="co_num", title="CO #"),
                DataTableColumn(key="date", title="Date"),
                DataTableColumn(key="type", title="Type"),
                DataTableColumn(key="amount_delta", title="Amount Delta", is_numeric=True),
                DataTableColumn(key="days_ext", title="Days Ext."),
                DataTableColumn(key="status", title="Status"),
                DataTableColumn(key="description", title="Description"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 5)
        self._table.selection_changed.connect(lambda _: self._update_action_state())
        self._table.view().doubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self._table)
        return card

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _reload(self, selected_id: int | None = None) -> None:
        svc = self._service_registry.contract_change_order_service
        try:
            self._change_orders = svc.list_change_orders(self._contract_id)
        except Exception as exc:
            self._change_orders = []
            show_error(self, "Change Orders", f"Could not load change orders.\n\n{exc}")

        self._populate_table()
        count = len(self._change_orders)
        self._count_label.setText(f"{count} change order{'s' if count != 1 else ''}")
        self._select_by_id(selected_id)
        self._update_action_state()

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())

        for co in self._change_orders:
            delta_str = "" if co.contract_amount_delta is None else f"{co.contract_amount_delta:,.2f}"
            days_str = "" if co.days_extension is None else str(co.days_extension)
            desc_str = (co.description or "")[:60]
            self._model.appendRow([
                self._make_item(co.change_order_number, user_data=co.id),
                self._make_item(str(co.change_order_date) if co.change_order_date else ""),
                self._make_item(co.change_type_code),
                self._make_item(delta_str),
                self._make_item(days_str),
                self._make_item(co.status_code),
                self._make_item(desc_str),
            ])

    def _select_by_id(self, target_id: int | None) -> None:
        if not self._change_orders:
            return
        if target_id is not None:
            target_idx = next(
                (i for i, co in enumerate(self._change_orders) if co.id == target_id), 0
            )
        else:
            target_idx = 0
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._table.view().selectionModel()
        if sm is None:
            return
        sm.select(proxy_index, sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows)
        self._table.view().scrollTo(proxy_index)

    def _selected_co(self) -> ContractChangeOrderListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        id_item = self._model.item(rows[0], 0)
        if id_item is None:
            return None
        co_id = id_item.data(Qt.ItemDataRole.UserRole)
        for co in self._change_orders:
            if co.id == co_id:
                return co
        return None

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _on_double_clicked(self, _index) -> None:
        self._open_edit()

    def _update_action_state(self) -> None:
        selected = self._selected_co()
        status = selected.status_code if selected else None

        self._edit_button.setEnabled(status == "draft")
        self._submit_button.setEnabled(status == "draft")
        self._approve_button.setEnabled(status == "submitted")
        self._reject_button.setEnabled(status == "submitted")
        self._cancel_button.setEnabled(status in {"draft", "submitted"})

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create(self) -> None:
        result = ContractChangeOrderFormDialog.create_change_order(
            self._service_registry,
            self._company_id,
            self._contract_id,
            self._contract_number,
            parent=self,
        )
        if result is not None:
            self._reload(selected_id=result.id)

    def _open_edit(self) -> None:
        selected = self._selected_co()
        if selected is None or selected.status_code != "draft":
            return
        result = ContractChangeOrderFormDialog.edit_change_order(
            self._service_registry,
            self._company_id,
            self._contract_id,
            self._contract_number,
            change_order_id=selected.id,
            parent=self,
        )
        if result is not None:
            self._reload(selected_id=result.id)

    def _submit_selected(self) -> None:
        selected = self._selected_co()
        if selected is None:
            return
        choice = QMessageBox.question(
            self, "Submit Change Order",
            f"Submit change order '{selected.change_order_number}' for approval?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.contract_change_order_service.submit_change_order(
                SubmitContractChangeOrderCommand(change_order_id=selected.id)
            )
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Change Orders", str(exc))
        self._reload(selected_id=selected.id)

    def _approve_selected(self) -> None:
        selected = self._selected_co()
        if selected is None:
            return
        choice = QMessageBox.question(
            self, "Approve Change Order",
            f"Approve change order '{selected.change_order_number}'?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.contract_change_order_service.approve_change_order(
                ApproveContractChangeOrderCommand(change_order_id=selected.id)
            )
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Change Orders", str(exc))
        self._reload(selected_id=selected.id)

    def _reject_selected(self) -> None:
        selected = self._selected_co()
        if selected is None:
            return
        choice = QMessageBox.question(
            self, "Reject Change Order",
            f"Reject change order '{selected.change_order_number}'?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.contract_change_order_service.reject_change_order(
                RejectContractChangeOrderCommand(change_order_id=selected.id)
            )
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Change Orders", str(exc))
        self._reload(selected_id=selected.id)

    def _cancel_selected(self) -> None:
        selected = self._selected_co()
        if selected is None:
            return
        choice = QMessageBox.question(
            self, "Cancel Change Order",
            f"Cancel change order '{selected.change_order_number}'? This cannot be undone.",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service_registry.contract_change_order_service.cancel_change_order(selected.id)
        except (NotFoundError, ValidationError) as exc:
            show_error(self, "Change Orders", str(exc))
        self._reload(selected_id=selected.id)
