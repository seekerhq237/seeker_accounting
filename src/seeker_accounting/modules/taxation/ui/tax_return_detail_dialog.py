"""Tax return detail viewer dialog (Slice T28).

Opens a single tax return — DRAFT or FILED — and displays it laid out
as the official DGI Cameroon VAT-return form (Sections 4 → 8 with
statutory line codes L17-L47).

Read-only for now: the user can inspect every box, see what aggregated
into each line, and verify the breakdown before filing. Editing of
manual fields (pro-rata, adjustments, reimbursement requested) is
intentionally deferred to a follow-up slice — this dialog is the
foundation that future "edit draft" buttons will grow on top of.

Architecture: the dialog never reaches into repositories or the DB.
It receives a fully-loaded ``TaxReturnDTO``, projects it through the
``vat_return_form_layout`` read-model, and renders the resulting
sections into stacked Qt tables.
"""

from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.taxation.constants import (
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_FILED,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    DraftVATReturnCommand,
    TaxReturnDTO,
)
from seeker_accounting.modules.taxation.services.vat_return_form_layout import (
    VATFormLayout,
    VATFormRow,
    VATFormSection,
    build_vat_form_layout,
)
from seeker_accounting.platform.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.modules.taxation.ui.vat_line_drilldown_dialog import (
    VATLineDrillDownDialog,
)


_DASH = "—"


def _money(value: Decimal | None) -> str:
    if value is None:
        return _DASH
    return f"{Decimal(value):,.2f}"


def _status_palette(status_code: str) -> tuple[str, str]:
    """Return (background, text) colours for a status pill."""
    if status_code == RETURN_STATUS_DRAFT:
        return ("#FEF3C7", "#92400E")  # amber-100 / amber-800
    if status_code == RETURN_STATUS_FILED:
        return ("#DCFCE7", "#166534")  # green-100 / green-800
    return ("#E5E7EB", "#374151")      # gray-200 / gray-700


class TaxReturnDetailDialog(BaseDialog):
    """Read-only DGI-form viewer for a single VAT tax return."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        tax_return: TaxReturnDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title=f"Tax Return #{tax_return.id} — {tax_return.tax_type_code}",
            parent=parent,
            help_key="taxation.return_detail",
        )
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._tax_return = tax_return
        self._redrafted = False

        self.setMinimumSize(880, 720)
        apply_window_size(self, "modules.taxation.ui.tax.return.detail.dialog.0")

        self._build_body()
        self._configure_buttons()

    # ── Public API ────────────────────────────────────────────────────

    def was_redrafted(self) -> bool:
        """True when the user clicked ``Recompute from posted documents``
        and the service successfully regenerated the draft.
        """
        return self._redrafted

    def current_return(self) -> TaxReturnDTO:
        return self._tax_return

    # ── Body ──────────────────────────────────────────────────────────

    def _build_body(self) -> None:
        # Replace BaseDialog's body_layout with a scrollable area.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        container = QWidget(scroll)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(16)

        v.addWidget(self._build_header_card(container))
        v.addWidget(self._build_meta_card(container))

        if self._tax_return.tax_type_code != TAX_TYPE_VAT:
            v.addWidget(self._build_non_vat_breakdown(container))
        else:
            layout = build_vat_form_layout(self._tax_return)
            if layout.has_unmapped_data:
                v.addWidget(self._build_unmapped_warning(container))
            for section in layout.sections:
                v.addWidget(self._build_section_card(container, section))
            v.addWidget(self._build_totals_card(container, layout))

        if self._tax_return.notes:
            v.addWidget(self._build_notes_card(container))

        v.addStretch(1)

        scroll.setWidget(container)
        self.body_layout.addWidget(scroll)

    # ── Header card (company + status pill) ───────────────────────────

    def _build_header_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("DialogSection")
        card.setProperty("card", True)

        h = QHBoxLayout(card)
        h.setContentsMargins(16, 14, 16, 14)
        h.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(2)

        company = QLabel(self._company_name or "—", card)
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        company.setFont(f)
        company.setStyleSheet("color: #111827;")
        left.addWidget(company)

        title = QLabel(
            f"Tax Return — {self._tax_return.tax_type_code}", card
        )
        title.setStyleSheet("color: #6B7280; font-size: 11pt;")
        left.addWidget(title)

        h.addLayout(left, 1)

        status_pill = QLabel(self._tax_return.status_code, card)
        bg, fg = _status_palette(self._tax_return.status_code)
        status_pill.setStyleSheet(
            f"background-color: {bg}; color: {fg}; "
            "padding: 4px 12px; border-radius: 10px; "
            "font-weight: 600; font-size: 10pt;"
        )
        status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(status_pill, 0, Qt.AlignmentFlag.AlignTop)

        return card

    # ── Meta card (period, refs, …) ───────────────────────────────────

    def _build_meta_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("DialogSection")
        card.setProperty("card", True)

        grid = QGridLayout(card)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        rows = [
            ("Return ID", f"#{self._tax_return.id}"),
            ("Obligation ID", f"#{self._tax_return.obligation_id}"),
            (
                "Period",
                f"{self._tax_return.period_start.isoformat()} — "
                f"{self._tax_return.period_end.isoformat()}",
            ),
            (
                "Filed at",
                (
                    self._tax_return.filed_at.strftime("%Y-%m-%d %H:%M")
                    if self._tax_return.filed_at
                    else _DASH
                ),
            ),
            ("OTP reference", self._tax_return.otp_reference or _DASH),
            (
                "External reference",
                self._tax_return.external_reference or _DASH,
            ),
        ]

        for i, (k, v) in enumerate(rows):
            row, col = divmod(i, 2)
            label = QLabel(k, card)
            label.setStyleSheet("color: #6B7280; font-size: 10pt;")
            value = QLabel(v, card)
            value.setStyleSheet("color: #111827; font-size: 11pt;")
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            grid.addWidget(label, row, col * 2)
            grid.addWidget(value, row, col * 2 + 1)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        return card

    # ── Unmapped warning ─────────────────────────────────────────────

    def _build_unmapped_warning(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setStyleSheet(
            "background-color: #FEF3C7; border-left: 3px solid #F59E0B;"
        )
        h = QHBoxLayout(card)
        h.setContentsMargins(12, 8, 12, 8)
        msg = QLabel(
            "This return contains line codes outside the standard "
            "DGI VAT-form layout. Those entries are preserved on disk "
            "but are not shown below.",
            card,
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #92400E; font-size: 10pt;")
        h.addWidget(msg)
        return card

    # ── Section card (one per DGI form section) ──────────────────────

    def _build_section_card(
        self, parent: QWidget, section: VATFormSection
    ) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("DialogSection")
        card.setProperty("card", True)

        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        heading = QLabel(
            f"Section {section.number} — {section.title}", card
        )
        heading.setStyleSheet(
            "font-weight: 600; color: #111827; font-size: 12pt;"
        )
        v.addWidget(heading)

        # Column headers: Code | Description | …value columns
        all_columns = ("Code", "Description") + tuple(section.columns)

        model = QStandardItemModel(len(section.rows), len(all_columns), card)
        model.setHorizontalHeaderLabels(list(all_columns))
        dt_columns = tuple(DataTableColumn(key=str(i), title=col) for i, col in enumerate(all_columns))
        table = DataTable(columns=dt_columns, show_search=False, parent=card)
        table.set_model(model)

        for ri, row in enumerate(section.rows):
            self._fill_form_row(model, ri, row, section)

        # T40: double-click opens the VAT line drill-down dialog (VAT returns only)
        if self._tax_return.tax_type_code == TAX_TYPE_VAT:
            def _make_handler(_section=section, _model=model):
                def _on_dbl(index):
                    proxy = table.view().model()
                    src = proxy.mapToSource(index) if proxy else index
                    row_idx = src.row()
                    self._handle_drilldown(_section, _model, row_idx)
                return _on_dbl
            table.view().doubleClicked.connect(_make_handler())

        # Compute compact height: header + rows + a small margin.
        row_h = 24
        total_h = 30 + row_h * len(section.rows) + 6
        table.setFixedHeight(total_h)

        v.addWidget(table)
        return card

    def _fill_form_row(
        self,
        model: QStandardItemModel,
        ri: int,
        row: VATFormRow,
        section: VATFormSection,
    ) -> None:
        # Code
        code_item = QStandardItem(row.code)
        code_item.setEditable(False)
        code_item.setFont(self._mono_font())
        if row.emphasis:
            self._bold(code_item)
        model.setItem(ri, 0, code_item)

        # Description
        desc_item = QStandardItem(row.label)
        desc_item.setEditable(False)
        if row.note:
            desc_item.setToolTip(row.note)
        if row.emphasis:
            self._bold(desc_item)
        model.setItem(ri, 1, desc_item)

        # Value columns are dispatched by section semantics.
        if section.number == "4":
            # Base / Rate / Tax
            self._set_amount_cell(model, ri, 2, row.base, emphasis=row.emphasis)
            self._set_text_cell(model, ri, 3, row.rate or _DASH)
            self._set_amount_cell(model, ri, 4, row.amount, emphasis=row.emphasis)
        elif section.number == "8":
            # Principal / CAC / Fines / Total
            principal = row.amount
            self._set_amount_cell(
                model, ri, 2, principal, emphasis=row.emphasis
            )
            self._set_amount_cell(model, ri, 3, None)
            self._set_amount_cell(model, ri, 4, None)
            self._set_amount_cell(
                model, ri, 5, principal, emphasis=row.emphasis
            )
        else:
            # Sections 5, 6, 7 — Detail / blank / Amount
            self._set_text_cell(model, ri, 2, "")
            self._set_text_cell(model, ri, 3, "")
            self._set_amount_cell(
                model, ri, 4, row.amount, emphasis=row.emphasis
            )

    # ── T40: VAT line drill-down ──────────────────────────────────────

    def _handle_drilldown(
        self,
        section: VATFormSection,
        model: QStandardItemModel,
        row_idx: int,
    ) -> None:
        """Open VATLineDrillDownDialog for the double-clicked VAT form row."""
        code_item = model.item(row_idx, 0)
        if code_item is None:
            return
        row_code = code_item.text().strip()
        if not row_code or row_code == _DASH:
            return
        desc_item = model.item(row_idx, 1)
        row_label = desc_item.text() if desc_item else ""

        try:
            fiscal_period_ids = (
                self._service_registry.tax_return_service.resolve_fiscal_period_ids(
                    self._company_id,
                    self._tax_return.period_start,
                    self._tax_return.period_end,
                )
            )
        except Exception:
            fiscal_period_ids = []

        dlg = VATLineDrillDownDialog(
            self._service_registry,
            self._company_id,
            fiscal_period_ids,
            row_code,
            row_label,
            self,
        )
        dlg.exec()

    # ── Totals card ───────────────────────────────────────────────────

    def _build_totals_card(
        self, parent: QWidget, layout: VATFormLayout
    ) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("DialogSection")
        card.setProperty("card", True)
        card.setStyleSheet("background-color: #F9FAFB;")

        h = QHBoxLayout(card)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(32)

        for label_text, amount_text, accent in (
            ("Total due", _money(layout.total_due), "#111827"),
            ("Total paid", _money(layout.total_paid), "#111827"),
            (
                "Outstanding",
                _money(layout.outstanding),
                "#B91C1C" if layout.outstanding > 0 else "#166534",
            ),
        ):
            block = QVBoxLayout()
            block.setSpacing(2)
            lab = QLabel(label_text, card)
            lab.setStyleSheet("color: #6B7280; font-size: 10pt;")
            val = QLabel(amount_text, card)
            f = QFont()
            f.setBold(True)
            f.setPointSize(13)
            val.setFont(f)
            val.setStyleSheet(f"color: {accent};")
            block.addWidget(lab)
            block.addWidget(val)
            h.addLayout(block)

        h.addStretch(1)

        return card

    # ── Non-VAT breakdown (Patente / TSR / Customs / CIT) ────────────

    def _build_non_vat_breakdown(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("DialogSection")
        card.setProperty("card", True)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        heading = QLabel("Assessed Amount", card)
        heading.setStyleSheet(
            "font-weight: 600; color: #111827; font-size: 12pt;"
        )
        v.addWidget(heading)

        info = QLabel(
            f"This is a {self._tax_return.tax_type_code} return. "
            "The amount was entered directly as an assessed liability "
            "rather than aggregated from posted accounting data.",
            card,
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #6B7280; font-size: 10pt;")
        v.addWidget(info)

        amount = QLabel(_money(self._tax_return.total_due_amount), card)
        f = QFont()
        f.setPointSize(20)
        f.setBold(True)
        amount.setFont(f)
        amount.setStyleSheet("color: #111827; margin-top: 8px;")
        v.addWidget(amount)
        return card

    # ── Notes card ───────────────────────────────────────────────────

    def _build_notes_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setStyleSheet(
            "background-color: #F9FAFB; border-left: 3px solid #D1D5DB;"
        )
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 8, 12, 8)

        heading = QLabel("Notes", card)
        heading.setStyleSheet("font-weight: 600; color: #374151;")
        v.addWidget(heading)

        body = QLabel(self._tax_return.notes or "", card)
        body.setWordWrap(True)
        body.setStyleSheet("color: #4B5563; font-size: 10pt;")
        v.addWidget(body)
        return card

    # ── Buttons ──────────────────────────────────────────────────────

    def _configure_buttons(self) -> None:
        self.button_box.clear()
        close_btn = self.button_box.addButton(
            QDialogButtonBox.StandardButton.Close
        )
        close_btn.setDefault(True)

        # Recompute is only meaningful on a DRAFT VAT return.
        is_draft_vat = (
            self._tax_return.status_code == RETURN_STATUS_DRAFT
            and self._tax_return.tax_type_code == TAX_TYPE_VAT
        )
        if is_draft_vat:
            try:
                can_manage = self._service_registry.permission_service.has_permission(
                    "taxation.returns.manage"
                )
            except Exception:
                can_manage = False
            if can_manage:
                redraft = QPushButton("Recompute from posted documents", self)
                redraft.clicked.connect(self._handle_redraft)
                self.button_box.addButton(
                    redraft, QDialogButtonBox.ButtonRole.ActionRole
                )

    def _handle_redraft(self) -> None:
        try:
            updated = self._service_registry.tax_return_service.draft_vat_return(
                self._company_id,
                DraftVATReturnCommand(
                    obligation_id=self._tax_return.obligation_id,
                    notes=self._tax_return.notes,
                ),
            )
        except (
            ValidationError,
            NotFoundError,
            ConflictError,
            PermissionDeniedError,
        ) as exc:
            show_error(self, "Recompute Draft", str(exc))
            return
        except AppError as exc:
            show_error(self, "Recompute Draft", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Recompute Draft",
                f"An unexpected error occurred.\n\n{exc}",
            )
            return

        self._tax_return = updated
        self._redrafted = True
        show_info(
            self,
            "Recompute Draft",
            "Draft return regenerated from posted invoices and bills. "
            "Close and reopen this dialog to see the refreshed breakdown.",
        )

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _mono_font() -> QFont:
        f = QFont("Consolas")
        f.setStyleHint(QFont.StyleHint.Monospace)
        return f

    @staticmethod
    def _bold(item: QStandardItem) -> None:
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    def _set_amount_cell(
        self,
        model: QStandardItemModel,
        ri: int,
        ci: int,
        value: Decimal | None,
        *,
        emphasis: bool = False,
    ) -> None:
        item = QStandardItem(_money(value))
        item.setEditable(False)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        if value is None:
            item.setForeground(QBrush(QColor("gray")))
        if emphasis:
            self._bold(item)
        model.setItem(ri, ci, item)

    def _set_text_cell(
        self, model: QStandardItemModel, ri: int, ci: int, text: str
    ) -> None:
        item = QStandardItem(text)
        item.setEditable(False)
        if text == _DASH:
            item.setForeground(QBrush(QColor("gray")))
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        model.setItem(ri, ci, item)
