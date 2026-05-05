"""AccountDetailPage — full account workspace showing configuration and context.

Navigated to via:
    navigation_service.navigate(nav_ids.ACCOUNT_DETAIL, context={"account_id": <int>})
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountDetailDTO
from seeker_accounting.modules.reporting.dto.general_ledger_report_dto import (
    GeneralLedgerAccountDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.shared.ui.entity_detail.entity_detail_page import EntityDetailPage
from seeker_accounting.shared.ui.entity_detail.money_bar import MoneyBarItem
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

_log = logging.getLogger(__name__)

_LEDGER_LOOKBACK_DAYS = 180


class AccountDetailPage(EntityDetailPage):
    """Full detail workspace for a single chart of accounts entry."""

    _back_nav_id = nav_ids.CHART_OF_ACCOUNTS
    _back_label = "Back to Chart of Accounts"

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(service_registry, parent)
        self.setObjectName("AccountDetailPage")

        self._account_id: int | None = None
        self._account: AccountDetailDTO | None = None
        self._ledger_data: GeneralLedgerAccountDTO | None = None

        # Action buttons
        self._edit_button = QPushButton("Edit Account", self)
        self._edit_button.setObjectName("SecondaryButton")
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.clicked.connect(self._open_edit_dialog)
        self._action_row_layout.addWidget(self._edit_button)

        # Build tabs
        self._info_tab = self._build_info_tab()
        self._ledger_tab = self._build_ledger_tab()
        self._initialize_tabs()

        self._set_actions_enabled(False)

    # ── Tab construction ──────────────────────────────────────────────

    def _build_tabs(self) -> list[tuple[str, QWidget]]:
        return [
            ("Ledger", self._ledger_tab),
            ("Info", self._info_tab),
        ]

    def _build_info_tab(self) -> QWidget:
        container = QFrame()
        container.setObjectName("EntityInfoTab")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        def _row(label_text: str, attr_name: str) -> None:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)

            lbl = QLabel(label_text, row_widget)
            lbl.setObjectName("EntityInfoLabel")
            lbl.setFixedWidth(180)
            row_layout.addWidget(lbl)

            val = QLabel("—", row_widget)
            val.setObjectName("EntityInfoValue")
            val.setWordWrap(True)
            row_layout.addWidget(val, 1)
            layout.addWidget(row_widget)
            setattr(self, attr_name, val)

        _row("Account Code", "_info_code")
        _row("Account Name", "_info_name")
        _row("Account Class", "_info_class")
        _row("Account Type", "_info_type")
        _row("Normal Balance", "_info_normal_balance")
        _row("Parent Account", "_info_parent")
        _row("Manual Posting", "_info_manual_posting")
        _row("Control Account", "_info_control")
        _row("Notes", "_info_notes")
        _row("Created", "_info_created")
        layout.addStretch(1)

        return container

    def _build_ledger_tab(self) -> QWidget:
        container = QFrame()
        container.setObjectName("EntityInfoTab")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header row: account balance summary
        summary_row = QWidget(container)
        summary_layout = QHBoxLayout(summary_row)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(24)

        def _summary_cell(label_text: str, attr: str) -> None:
            cell = QWidget(summary_row)
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)
            lbl = QLabel(label_text, cell)
            lbl.setObjectName("EntityInfoLabel")
            cell_layout.addWidget(lbl)
            val = QLabel("—", cell)
            val.setObjectName("EntityInfoValue")
            cell_layout.addWidget(val)
            summary_layout.addWidget(cell)
            setattr(self, attr, val)

        _summary_cell("Opening Balance", "_ledger_opening")
        _summary_cell("Period Debit", "_ledger_period_debit")
        _summary_cell("Period Credit", "_ledger_period_credit")
        _summary_cell("Closing Balance", "_ledger_closing")
        summary_layout.addStretch(1)

        self._ledger_period_label = QLabel("—", summary_row)
        self._ledger_period_label.setObjectName("EntityInfoLabel")
        summary_layout.addWidget(self._ledger_period_label)

        layout.addWidget(summary_row)

        # Ledger lines table
        self._ledger_model = QStandardItemModel(0, 6, container)
        self._ledger_model.setHorizontalHeaderLabels(
            ["Date", "Entry #", "Description", "Debit", "Credit", "Balance"]
        )
        self._ledger_table = DataTable(
            columns=(
                DataTableColumn(key="date", title="Date"),
                DataTableColumn(key="entry", title="Entry #"),
                DataTableColumn(key="desc", title="Description"),
                DataTableColumn(key="debit", title="Debit"),
                DataTableColumn(key="credit", title="Credit"),
                DataTableColumn(key="balance", title="Balance"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=container,
        )
        self._ledger_table.set_model(self._ledger_model)

        hdr = self._ledger_table.view().horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self._ledger_table.view().doubleClicked.connect(self._on_ledger_line_double_clicked)

        self._ledger_empty = QLabel("No posted journal lines for this account in the last 180 days.", container)
        self._ledger_empty.setObjectName("DashboardEmptyLabel")
        self._ledger_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ledger_empty.setMinimumHeight(60)

        layout.addWidget(self._ledger_table, 1)
        layout.addWidget(self._ledger_empty)
        self._ledger_empty.setVisible(False)

        return container

    # ── Navigation context ────────────────────────────────────────────

    def set_navigation_context(self, context: dict) -> None:
        account_id = context.get("account_id")
        if not isinstance(account_id, int):
            return
        self._account_id = account_id
        self._load_data()

    # ── Data loading ──────────────────────────────────────────────────

    def _load_data(self) -> None:
        if self._account_id is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        try:
            self._account = self._service_registry.chart_of_accounts_service.get_account(
                active_company.company_id, self._account_id
            )
        except NotFoundError:
            show_error(self, "Account Detail", "Account not found.")
            self._navigate_back()
            return
        except AppError as exc:
            show_error(self, "Account Detail", f"Failed to load account: {exc}")
            return
        except Exception:
            _log.exception("Account Detail")
            show_error(self, "Account Detail", "An unexpected error occurred. See application log for details.")
            return

        # Load ledger (best-effort — don't fail the whole page if ledger unavailable)
        self._ledger_data = None
        try:
            today = date.today()
            date_from = today - timedelta(days=_LEDGER_LOOKBACK_DAYS)
            filter_dto = ReportingFilterDTO(
                company_id=active_company.company_id,
                date_from=date_from,
                date_to=today,
                posted_only=True,
            )
            ledger_report = self._service_registry.general_ledger_report_service.get_account_ledger(
                filter_dto, self._account_id
            )
            if ledger_report.accounts:
                self._ledger_data = ledger_report.accounts[0]
        except Exception:
            _log.warning("Account detail: ledger unavailable", exc_info=True)

        self._populate_header()
        self._populate_money_bar()
        self._populate_info_tab()
        self._populate_ledger()
        self._set_actions_enabled(True)

    # ── Population ────────────────────────────────────────────────────

    def _populate_header(self) -> None:
        a = self._account
        if a is None:
            return
        subtitle = f"{a.account_code}  ·  {a.account_type_name}  ·  {a.account_class_name}"
        self._set_header(
            title=a.account_name,
            subtitle=subtitle,
            status_label="Active" if a.is_active else "Inactive",
            is_active=a.is_active,
        )

    def _populate_money_bar(self) -> None:
        a = self._account
        if a is None:
            return
        normal_balance = a.normal_balance.title() if a.normal_balance else "—"

        items = [
            MoneyBarItem(label="Normal Balance", value=normal_balance, tone="neutral"),
        ]

        # Show closing balance if we have ledger data
        ledger = self._ledger_data
        if ledger is not None:
            balance = ledger.closing_balance
            items.append(MoneyBarItem(
                label="Closing Balance",
                value=f"{balance:,.0f}",
                tone="info",
            ))
            items.append(MoneyBarItem(
                label="Posted Lines",
                value=str(len(ledger.lines)),
                tone="neutral",
            ))

        items.append(MoneyBarItem(
            label="Manual Posting",
            value="Yes" if a.allow_manual_posting else "No",
            tone="info" if a.allow_manual_posting else "neutral",
        ))
        items.append(MoneyBarItem(
            label="Control Account",
            value="Yes" if a.is_control_account else "No",
            tone="warning" if a.is_control_account else "neutral",
        ))
        self._set_money_bar(items)

    def _populate_info_tab(self) -> None:
        a = self._account
        if a is None:
            return

        def _or_dash(val: str | None) -> str:
            return val or "—"

        parent_text = "—"
        if a.parent_account_code and a.parent_account_name:
            parent_text = f"{a.parent_account_code} — {a.parent_account_name}"

        self._info_code.setText(_or_dash(a.account_code))
        self._info_name.setText(_or_dash(a.account_name))
        self._info_class.setText(_or_dash(a.account_class_name))
        self._info_type.setText(_or_dash(a.account_type_name))
        self._info_normal_balance.setText(a.normal_balance.title() if a.normal_balance else "—")
        self._info_parent.setText(parent_text)
        self._info_manual_posting.setText("Yes" if a.allow_manual_posting else "No")
        self._info_control.setText("Yes" if a.is_control_account else "No")
        self._info_notes.setText(_or_dash(a.notes))
        self._info_created.setText(a.created_at.strftime("%d %b %Y %H:%M"))

    def _populate_ledger(self) -> None:
        ledger = self._ledger_data

        # Period label
        today = date.today()
        date_from = today - timedelta(days=_LEDGER_LOOKBACK_DAYS)
        self._ledger_period_label.setText(
            f"{date_from.strftime('%d %b %Y')}  –  {today.strftime('%d %b %Y')}"
        )

        self._ledger_model.removeRows(0, self._ledger_model.rowCount())

        if ledger is None or not ledger.lines:
            self._ledger_opening.setText("—")
            self._ledger_period_debit.setText("—")
            self._ledger_period_credit.setText("—")
            self._ledger_closing.setText("—")
            self._ledger_table.setVisible(False)
            self._ledger_empty.setVisible(True)
            return

        self._ledger_table.setVisible(True)
        self._ledger_empty.setVisible(False)

        self._ledger_opening.setText(f"{ledger.opening_balance:,.2f}")
        self._ledger_period_debit.setText(f"{ledger.period_debit:,.2f}")
        self._ledger_period_credit.setText(f"{ledger.period_credit:,.2f}")
        self._ledger_closing.setText(f"{ledger.closing_balance:,.2f}")

        for line in ledger.lines:
            date_item = self._make_item(line.entry_date.strftime("%d %b %Y"))
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

            entry_item = self._make_item(line.entry_number or "—", user_data=line.journal_entry_id)

            desc_parts = [p for p in (line.line_description, line.journal_description, line.reference_text) if p]
            desc = desc_parts[0] if desc_parts else "—"
            desc_item = self._make_item(desc)

            debit_text = f"{line.debit_amount:,.2f}" if line.debit_amount else "—"
            debit_item = self._make_item(debit_text)
            debit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            credit_text = f"{line.credit_amount:,.2f}" if line.credit_amount else "—"
            credit_item = self._make_item(credit_text)
            credit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            balance_item = self._make_item(f"{line.running_balance:,.2f}")
            balance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self._ledger_model.appendRow([date_item, entry_item, desc_item, debit_item, credit_item, balance_item])

    def _on_ledger_line_double_clicked(self, index) -> None:
        proxy = self._ledger_table.view().model()
        if proxy is None:
            return
        src = proxy.mapToSource(index)
        row = src.row()
        entry_item = self._ledger_model.item(row, 1)
        if entry_item is None:
            return
        journal_entry_id = entry_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(journal_entry_id, int):
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.JOURNALS, context={"journal_entry_id": journal_entry_id}
        )

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    # ── Actions ───────────────────────────────────────────────────────

    def _set_actions_enabled(self, enabled: bool) -> None:
        self._edit_button.setEnabled(enabled)

    def _open_edit_dialog(self) -> None:
        if self._account is None:
            return
        active_company = self._service_registry.company_context_service.get_active_company()
        if active_company is None:
            return

        from seeker_accounting.modules.accounting.chart_of_accounts.ui.account_form_dialog import AccountFormDialog
        updated = AccountFormDialog.edit_account(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            account_id=self._account.id,
            parent=self,
        )
        if updated is not None:
            self._load_data()
