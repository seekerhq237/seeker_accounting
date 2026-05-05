"""Withholding-tax certificates workspace.

Single-table workspace for the inbound/outbound certificate register
(Slice T13). Filters drive the underlying ``list_certificates`` call;
totals show the aggregate for the active filter (excluding voided).

Architecture: UI surface only — every read/write goes through
``WithholdingTaxCertificateService`` via the service registry. The
page never opens its own session or constructs any persistence.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.taxation.constants import (
    WHT_DIRECTION_INBOUND,
    WHT_DIRECTION_OUTBOUND,
    WHT_STATUS_ISSUED,
    WHT_STATUS_RECEIVED,
    WHT_STATUS_VOIDED,
)
from seeker_accounting.modules.taxation.dto.withholding_tax_certificate_dto import (
    WithholdingTaxCertificateDTO,
)
from seeker_accounting.modules.taxation.ui.withholding_certificates_dialogs import (
    EditWithholdingCertificateDialog,
    LinkWithholdingCertificateDialog,
    RecordWithholdingCertificateDialog,
    VoidWithholdingCertificateDialog,
)
from seeker_accounting.platform.exceptions import (
    PermissionDeniedError,
)
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error


_DASH = "\u2014"


def _money(value: Decimal | float | int | None) -> str:
    if value is None:
        return _DASH
    return f"{Decimal(value):,.2f}"


def _date_text(value: date | None) -> str:
    if value is None:
        return _DASH
    return value.isoformat()


_DIRECTION_FILTER_OPTIONS: tuple[tuple[str | None, str], ...] = (
    (None, "All directions"),
    (WHT_DIRECTION_INBOUND, "Inbound (received)"),
    (WHT_DIRECTION_OUTBOUND, "Outbound (issued)"),
)

_STATUS_FILTER_OPTIONS: tuple[tuple[str | None, str], ...] = (
    (None, "All statuses"),
    (WHT_STATUS_RECEIVED, "Received"),
    (WHT_STATUS_ISSUED, "Issued"),
    (WHT_STATUS_VOIDED, "Voided"),
)


class WithholdingCertificatesPage(RibbonHostMixin, QWidget):
    COLUMNS: tuple[DataTableColumn, ...] = (
        DataTableColumn(key="direction", title="Direction"),
        DataTableColumn(key="date", title="Date"),
        DataTableColumn(key="number", title="Number"),
        DataTableColumn(key="counterparty", title="Counterparty"),
        DataTableColumn(key="niu", title="NIU"),
        DataTableColumn(key="status", title="Status"),
        DataTableColumn(key="taxable_base", title="Taxable base", is_numeric=True),
        DataTableColumn(key="tax_amount", title="Tax amount", is_numeric=True),
        DataTableColumn(key="source_je", title="Source JE"),
        DataTableColumn(key="notes", title="Notes"),
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._certificates: list[WithholdingTaxCertificateDTO] = []

        self.setObjectName("WithholdingCertificatesPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_action_bar())

        self._stack = QStackedWidget(self)
        self._no_company_card = self._build_no_company_card()
        self._workspace = self._build_workspace()
        self._stack.addWidget(self._no_company_card)
        self._stack.addWidget(self._workspace)
        root.addWidget(self._stack, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    # ── Action bar ────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Withholding Certificates", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._meta_label = QLabel(card)
        self._meta_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._meta_label)

        layout.addStretch(1)

        self._record_button = QPushButton("Record", card)
        self._record_button.setProperty("variant", "primary")
        self._record_button.clicked.connect(self._handle_record)
        layout.addWidget(self._record_button)

        self._edit_button = QPushButton("Edit", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._handle_edit)
        layout.addWidget(self._edit_button)

        self._void_button = QPushButton("Void", card)
        self._void_button.setProperty("variant", "secondary")
        self._void_button.clicked.connect(self._handle_void)
        layout.addWidget(self._void_button)

        self._link_button = QPushButton("Link JE…", card)
        self._link_button.setProperty("variant", "secondary")
        self._link_button.setToolTip(
            "Link this certificate to a posted journal entry "
            "(typically the supplier-payment JE)."
        )
        self._link_button.clicked.connect(self._handle_link)
        layout.addWidget(self._link_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self.reload)
        layout.addWidget(self._refresh_button)

        return card

    # ── No-company state ──────────────────────────────────────────────

    def _build_no_company_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No active company", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        body = QLabel(
            "Select a company from the top context bar to manage the "
            "withholding-tax certificate register.",
            card,
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)
        return card

    # ── Workspace ─────────────────────────────────────────────────────

    def _build_workspace(self) -> QWidget:
        wrapper = QFrame(self)
        wrapper.setObjectName("PageCard")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Filter bar ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        filter_row.addWidget(QLabel("Direction:"))
        self._direction_filter = QComboBox(wrapper)
        for code, label in _DIRECTION_FILTER_OPTIONS:
            self._direction_filter.addItem(label, code)
        self._direction_filter.currentIndexChanged.connect(lambda *_: self.reload())
        filter_row.addWidget(self._direction_filter)

        filter_row.addSpacing(8)
        filter_row.addWidget(QLabel("Status:"))
        self._status_filter = QComboBox(wrapper)
        for code, label in _STATUS_FILTER_OPTIONS:
            self._status_filter.addItem(label, code)
        self._status_filter.currentIndexChanged.connect(lambda *_: self.reload())
        filter_row.addWidget(self._status_filter)

        filter_row.addSpacing(8)
        filter_row.addWidget(QLabel("From:"))
        self._date_from = QDateEdit(wrapper)
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        today = date.today()
        self._date_from.setDate(QDate(today.year, 1, 1))
        self._date_from.dateChanged.connect(lambda *_: self.reload())
        filter_row.addWidget(self._date_from)

        filter_row.addWidget(QLabel("To:"))
        self._date_to = QDateEdit(wrapper)
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.setDate(QDate(today.year, 12, 31))
        self._date_to.dateChanged.connect(lambda *_: self.reload())
        filter_row.addWidget(self._date_to)

        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        # ── Table ──
        self._model = QStandardItemModel(0, len(self.COLUMNS), wrapper)
        self._model.setHorizontalHeaderLabels([c.title for c in self.COLUMNS])

        self._table = DataTable(
            columns=self.COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No certificates match the current filters.",
            parent=wrapper,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 5)
        self._table.selection_changed.connect(lambda _rows: self._update_action_state())
        layout.addWidget(self._table, 1)

        # ── Totals footer ──
        self._totals_label = QLabel(wrapper)
        self._totals_label.setObjectName("PageSummary")
        layout.addWidget(self._totals_label)

        return wrapper

    # ── Lifecycle ─────────────────────────────────────────────────────

    def _active_company(self):
        return self._service_registry.company_context_service.get_active_company()

    def reload(self) -> None:
        active = self._active_company()
        if active is None:
            self._certificates = []
            self._meta_label.setText("Select a company")
            self._set_actions_enabled(record=False, edit=False, void=False)
            self._stack.setCurrentWidget(self._no_company_card)
            return

        direction = self._direction_filter.currentData()
        status = self._status_filter.currentData()
        d_from = self._date_from.date().toPython()
        d_to = self._date_to.date().toPython()

        try:
            self._certificates = (
                self._service_registry.withholding_tax_certificate_service
                .list_certificates(
                    active.company_id,
                    direction=direction,
                    status_code=status,
                    date_from=d_from,
                    date_to=d_to,
                )
            )
        except PermissionDeniedError:
            self._certificates = []
            self._meta_label.setText("Permission denied")
            self._set_actions_enabled(record=False, edit=False, void=False)
            self._stack.setCurrentWidget(self._workspace)
            self._populate_table()
            self._update_totals_footer()
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._certificates = []
            show_error(
                self,
                "Withholding Certificates",
                f"Could not load certificates.\n\n{exc}",
            )

        self._populate_table()
        self._update_totals_footer()
        self._meta_label.setText(f"{len(self._certificates)} certificate(s)")
        self._update_action_state()
        self._stack.setCurrentWidget(self._workspace)

    # ── Populate ──────────────────────────────────────────────────────

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
        self._model.removeRows(0, self._model.rowCount())
        for c in self._certificates:
            if c.source_document_type == "journal_entry" and c.source_document_id:
                je_text = f"JE #{c.source_document_id}"
            else:
                je_text = ""
            notes_text = (c.notes or "").splitlines()[0] if c.notes else ""
            self._model.appendRow(
                [
                    self._make_item(c.direction, user_data=c.id),
                    self._make_item(_date_text(c.certificate_date)),
                    self._make_item(c.certificate_number),
                    self._make_item(c.counterparty_name),
                    self._make_item(c.counterparty_niu or ""),
                    self._make_item(c.status_code),
                    self._make_numeric(c.taxable_base),
                    self._make_numeric(c.tax_amount),
                    self._make_item(je_text),
                    self._make_item(notes_text),
                ]
            )

    def _update_totals_footer(self) -> None:
        active_rows = [c for c in self._certificates if c.status_code != WHT_STATUS_VOIDED]
        inbound = [c for c in active_rows if c.direction == WHT_DIRECTION_INBOUND]
        outbound = [c for c in active_rows if c.direction == WHT_DIRECTION_OUTBOUND]

        def _sum_amount(rows):
            total = Decimal("0.00")
            for r in rows:
                total += Decimal(r.tax_amount or 0)
            return total

        def _sum_base(rows):
            total = Decimal("0.00")
            for r in rows:
                total += Decimal(r.taxable_base or 0)
            return total

        text = (
            f"Inbound: {len(inbound)} certs \u00b7 base {_money(_sum_base(inbound))} "
            f"\u00b7 tax {_money(_sum_amount(inbound))}    "
            f"Outbound: {len(outbound)} certs \u00b7 base {_money(_sum_base(outbound))} "
            f"\u00b7 tax {_money(_sum_amount(outbound))}    "
            f"(voided rows excluded)"
        )
        self._totals_label.setText(text)

    # ── Selection / state ─────────────────────────────────────────────

    def _selected_certificate(self) -> WithholdingTaxCertificateDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._certificates):
            return self._certificates[idx]
        return None

    def _set_actions_enabled(self, *, record: bool, edit: bool, void: bool, link: bool = False) -> None:
        self._record_button.setEnabled(record)
        self._edit_button.setEnabled(edit)
        self._void_button.setEnabled(void)
        self._link_button.setEnabled(link)

    def _update_action_state(self) -> None:
        active = self._active_company()
        if active is None:
            self._set_actions_enabled(record=False, edit=False, void=False)
            return

        perm = self._service_registry.permission_service
        can_manage = perm.has_permission("taxation.withholding.manage")

        selected = self._selected_certificate()
        can_edit = (
            can_manage
            and selected is not None
            and selected.status_code != WHT_STATUS_VOIDED
        )
        can_void = can_edit  # same condition

        self._set_actions_enabled(
            record=can_manage,
            edit=can_edit,
            void=can_void,
            link=can_edit,
        )

    # ── Handlers ──────────────────────────────────────────────────────

    def _handle_record(self) -> None:
        active = self._active_company()
        if active is None:
            return
        dialog = RecordWithholdingCertificateDialog(
            self._service_registry, active.company_id, self
        )
        if dialog.exec():
            self.reload()

    def _handle_edit(self) -> None:
        active = self._active_company()
        if active is None:
            return
        selected = self._selected_certificate()
        if selected is None:
            return
        dialog = EditWithholdingCertificateDialog(
            self._service_registry, active.company_id, selected, self
        )
        if dialog.exec():
            self.reload()

    def _handle_void(self) -> None:
        active = self._active_company()
        if active is None:
            return
        selected = self._selected_certificate()
        if selected is None:
            return
        dialog = VoidWithholdingCertificateDialog(
            self._service_registry, active.company_id, selected, self
        )
        if dialog.exec():
            self.reload()

    def _handle_link(self) -> None:
        active = self._active_company()
        if active is None:
            return
        selected = self._selected_certificate()
        if selected is None:
            return
        dialog = LinkWithholdingCertificateDialog(
            self._service_registry, active.company_id, selected, self
        )
        if dialog.exec():
            self.reload()
