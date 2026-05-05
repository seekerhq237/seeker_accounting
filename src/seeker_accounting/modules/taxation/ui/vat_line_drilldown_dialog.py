"""VAT line drill-down dialog (T40).

Opened from the tax return detail view when the user double-clicks a
VAT return line.  Shows the raw ``PostedTaxLine`` facts that aggregated
into the selected line (identified by its DGI return-box code, e.g.
"L20" for standard-rate output VAT).

The dialog calls the tax-return service via the service registry so
that no raw repositories are touched from the UI layer.
"""

from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.dialogs import BaseDialog


class VATLineDrillDownDialog(BaseDialog):
    """Display the source tax facts that contributed to one VAT return line."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        fiscal_period_ids: list[int],
        line_code: str,
        line_label: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._fiscal_period_ids = fiscal_period_ids
        self._line_code = line_code

        super().__init__(
            f"VAT Line Detail — {line_code}: {line_label}",
            parent,
            help_key="dialog.vat_line_drilldown",
        )
        self.setObjectName("VATLineDrillDownDialog")
        apply_window_size(self, "modules.taxation.ui.vat.line.drilldown.dialog.0")

        self.body_layout.addWidget(
            QLabel(
                f"Source transactions contributing to <b>{line_code}</b> ({line_label})",
                self,
            )
        )

        self._table = self._build_table()
        self.body_layout.addWidget(self._table)

        self._status_label = QLabel(self)
        self._status_label.setObjectName("DialogStatusLabel")
        self.body_layout.addWidget(self._status_label)

        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject)

        # T40: "Open Document" button — enabled when a row is selected.
        self._open_doc_btn = QPushButton("Open Document", self)
        self._open_doc_btn.setEnabled(False)
        self._open_doc_btn.setToolTip("Navigate to the source document for the selected fact")
        self.button_box.addButton(
            self._open_doc_btn, QDialogButtonBox.ButtonRole.ActionRole
        )
        self._open_doc_btn.clicked.connect(self._on_open_document)

        self._table.view().selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        self._load()

    # ── Table ─────────────────────────────────────────────────────────

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _build_table(self) -> DataTable:
        _headers = [
            "Tax point date",
            "Document type",
            "Document ID",
            "Direction",
            "Tax code",
            "Taxable base",
            "Tax amount",
            "Recoverable",
        ]
        _cols = tuple(
            DataTableColumn(key=f"col_{i}", title=h) for i, h in enumerate(_headers)
        )
        table = DataTable(
            columns=_cols,
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=self,
        )
        self._model = QStandardItemModel(0, len(_headers), self)
        self._model.setHorizontalHeaderLabels(_headers)
        table.set_model(self._model)
        hdr = table.view().horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        return table

    # ── Data loading ──────────────────────────────────────────────────

    def _load(self) -> None:
        svc = self._service_registry.tax_return_service
        try:
            facts = svc.list_facts_for_line(
                company_id=self._company_id,
                fiscal_period_ids=self._fiscal_period_ids,
                return_box_code=self._line_code,
            )
        except Exception as exc:  # pragma: no cover
            self._status_label.setText(f"Could not load detail: {exc}")
            return

        self._model.removeRows(0, self._model.rowCount())
        for fact in facts:
            taxable = self._make_item(f"{fact.get('taxable_base', Decimal('0')):,.2f}")
            taxable.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tax_amt = self._make_item(f"{fact.get('tax_amount', Decimal('0')):,.2f}")
            tax_amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._model.appendRow([
                self._make_item(str(fact.get("tax_point_date", ""))),
                self._make_item(fact.get("source_document_type", "")),
                self._make_item(str(fact.get("source_document_id", ""))),
                self._make_item(fact.get("direction", "")),
                self._make_item(fact.get("tax_code_code", "")),
                taxable,
                tax_amt,
                self._make_item("Yes" if fact.get("is_recoverable") else "No"),
            ])

        count = len(facts)
        self._status_label.setText(
            f"{count} source record{'s' if count != 1 else ''}"
            + (" (limited to 500)" if count == 500 else "")
        )

    # ── T40 interaction ────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        selection = self._table.view().selectionModel()
        self._open_doc_btn.setEnabled(bool(selection.hasSelection()))

    def _on_open_document(self) -> None:
        indexes = self._table.view().selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        doc_type = self._model.item(row, 1).text() if self._model.item(row, 1) else ""
        doc_id_text = self._model.item(row, 2).text() if self._model.item(row, 2) else ""
        try:
            doc_id = int(doc_id_text)
        except (ValueError, TypeError):
            doc_id = None
        if not doc_type or doc_id is None:
            QMessageBox.information(
                self, "Open Document", "No source document information available."
            )
            return
        # Format readable name for the document type.
        readable = doc_type.replace("_", " ").title()
        QMessageBox.information(
            self,
            "Open Document",
            f"Document: <b>{readable}</b><br>"
            f"ID: <b>{doc_id}</b><br><br>"
            "Use the relevant module to locate and open this document.",
        )
