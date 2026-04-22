from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QAbstractItemView, QLineEdit

from seeker_accounting.modules.inventory.ui.inventory_document_dialog import InventoryDocumentDialog
from seeker_accounting.modules.purchases.ui.purchase_bill_dialog import PurchaseBillDialog
from seeker_accounting.modules.purchases.ui.supplier_payment_dialog import SupplierPaymentDialog
from seeker_accounting.modules.sales.ui.customer_receipt_dialog import CustomerReceiptDialog


def _ns(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


class DocumentDialogUiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_purchase_bill_dialog_recalculates_line_and_header_totals(self) -> None:
        registry = _ns(
            supplier_service=_ns(
                list_suppliers=lambda company_id, active_only=True: [
                    _ns(id=1, supplier_code="SUP-001", display_name="Vendor One")
                ]
            ),
            contract_service=_ns(list_contracts=lambda company_id: []),
            project_service=_ns(list_projects=lambda company_id: []),
            reference_data_service=_ns(list_active_currencies=lambda: [_ns(code="XAF")]),
            active_company_context=_ns(base_currency_code="XAF"),
            chart_of_accounts_service=_ns(
                list_accounts=lambda company_id, active_only=True: [
                    _ns(
                        id=10,
                        account_code="6100",
                        account_name="Office Supplies",
                        allow_manual_posting=True,
                    )
                ]
            ),
            tax_setup_service=_ns(
                list_tax_codes=lambda company_id, active_only=True: [
                    _ns(id=5, code="VAT10", name="VAT 10%", rate_percent=Decimal("10.00"))
                ]
            ),
        )

        dialog = PurchaseBillDialog(registry, 1, "Test Company")
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._supplier_combo.count(), 2)

        dialog._lines_grid._add_empty_row()
        grid = dialog._lines_grid
        table = grid._table
        model = grid._model

        # Set description via the persistent QLineEdit editor
        desc_widget = table.indexWidget(model.index(0, 1))
        self.assertIsInstance(desc_widget, QLineEdit)
        desc_widget.setText("Paper")

        # Set qty via persistent editor
        qty_widget = table.indexWidget(model.index(0, 2))
        self.assertIsInstance(qty_widget, QLineEdit)
        qty_widget.setText("2")
        qty_widget.editingFinished.emit()

        # Set unit cost via persistent editor
        cost_widget = table.indexWidget(model.index(0, 3))
        self.assertIsInstance(cost_widget, QLineEdit)
        cost_widget.setText("100")
        cost_widget.editingFinished.emit()

        # Set tax code via persistent SearchableComboBox editor
        tax_widget = table.indexWidget(model.index(0, 4))
        self.assertIsNotNone(tax_widget)
        tax_widget.setCurrentIndex(1)

        # Set account via persistent SearchableComboBox editor
        acct_widget = table.indexWidget(model.index(0, 5))
        self.assertIsNotNone(acct_widget)
        acct_widget.setCurrentIndex(1)

        self.app.processEvents()

        # Check line total in model (col 6)
        line_total = model.data(model.index(0, 6), Qt.ItemDataRole.UserRole)
        self.assertEqual(line_total, Decimal("220.00"))

        # Check header totals
        self.assertEqual(dialog._subtotal_value.text(), "200.00")
        self.assertEqual(dialog._tax_value.text(), "20.00")
        self.assertEqual(dialog._total_value.text(), "220.00")

    def test_customer_receipt_dialog_updates_allocation_preview(self) -> None:
        registry = _ns(
            customer_service=_ns(
                list_customers=lambda company_id, active_only=True: [
                    _ns(id=1, customer_code="CUST-001", display_name="Retail Customer")
                ]
            ),
            financial_account_service=_ns(
                list_financial_accounts=lambda company_id, active_only=True: [
                    _ns(id=2, account_code="BANK-01", name="Main Bank")
                ]
            ),
            reference_data_service=_ns(list_active_currencies=lambda: [_ns(code="XAF")]),
            active_company_context=_ns(base_currency_code="XAF"),
            customer_receipt_service=_ns(
                list_allocatable_invoices=lambda company_id, customer_id: [
                    _ns(
                        id=11,
                        invoice_number="SI-0001",
                        invoice_date=date(2026, 3, 1),
                        due_date=date(2026, 3, 31),
                        currency_code="XAF",
                        total_amount=Decimal("120.00"),
                        open_balance_amount=Decimal("120.00"),
                        payment_status_code="unpaid",
                    ),
                    _ns(
                        id=12,
                        invoice_number="SI-0002",
                        invoice_date=date(2026, 3, 5),
                        due_date=date(2026, 4, 4),
                        currency_code="XAF",
                        total_amount=Decimal("80.00"),
                        open_balance_amount=Decimal("80.00"),
                        payment_status_code="unpaid",
                    ),
                ]
            ),
        )

        dialog = CustomerReceiptDialog(registry, 1, "Test Company")
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._customer_combo.count(), 2)

        dialog._customer_combo.setCurrentIndex(1)
        self.app.processEvents()
        self.assertEqual(dialog._allocations_panel._table.rowCount(), 2)

        dialog._amount_input.setText("100")
        dialog._allocations_panel._table.cellWidget(0, 6).setText("60")
        dialog._allocations_panel._table.cellWidget(1, 6).setText("30")
        self.app.processEvents()

        self.assertEqual(dialog._amount_received_label.text(), "Received: 100.00")
        self.assertEqual(dialog._total_allocated_label.text(), "Allocated: 90.00")
        self.assertEqual(dialog._remaining_label.text(), "Remaining: 10.00")

        dialog._allocations_panel._table.cellWidget(1, 6).setText("50")
        self.app.processEvents()
        self.assertEqual(dialog._remaining_label.text(), "Over allocated: 10.00")

    def test_supplier_payment_dialog_uses_supplier_display_name_and_updates_preview(self) -> None:
        registry = _ns(
            supplier_service=_ns(
                list_suppliers=lambda company_id, active_only=True: [
                    _ns(id=1, supplier_code="SUP-001", display_name="Packaging Partner")
                ]
            ),
            financial_account_service=_ns(
                list_financial_accounts=lambda company_id, active_only=True: [
                    _ns(id=2, account_code="BANK-01", name="Main Bank")
                ]
            ),
            reference_data_service=_ns(list_active_currencies=lambda: [_ns(code="XAF")]),
            active_company_context=_ns(base_currency_code="XAF"),
            supplier_payment_service=_ns(
                list_allocatable_bills=lambda company_id, supplier_id: [
                    _ns(
                        id=21,
                        bill_number="PB-0001",
                        bill_date=date(2026, 3, 2),
                        due_date=date(2026, 4, 1),
                        currency_code="XAF",
                        total_amount=Decimal("200.00"),
                        open_balance_amount=Decimal("200.00"),
                        payment_status_code="unpaid",
                    )
                ]
            ),
        )

        dialog = SupplierPaymentDialog(registry, 1, "Test Company")
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._supplier_combo.count(), 2)

        dialog._supplier_combo.setCurrentIndex(1)
        self.app.processEvents()
        dialog._amount_input.setText("150")
        dialog._allocations_panel._table.cellWidget(0, 6).setText("125")
        self.app.processEvents()

        self.assertEqual(dialog._amount_paid_label.text(), "Paid: 150.00")
        self.assertEqual(dialog._total_allocated_label.text(), "Allocated: 125.00")
        self.assertEqual(dialog._remaining_label.text(), "Remaining: 25.00")

    def test_inventory_document_dialog_is_editable_and_updates_line_amounts(self) -> None:
        registry = _ns(
            item_service=_ns(
                list_items=lambda company_id, active_only=True, item_type_code="stock": [
                    _ns(
                        id=31,
                        item_code="ITEM-001",
                        item_name="Steel Sheet",
                        unit_of_measure_id=7,
                    )
                ]
            ),
            unit_of_measure_service=_ns(
                list_units_of_measure=lambda company_id, active_only=True: [
                    _ns(id=7, code="PCS", name="Pieces")
                ]
            ),
            chart_of_accounts_service=_ns(
                list_accounts=lambda company_id, active_only=True: [
                    _ns(id=41, account_code="5100", account_name="COGS", allow_manual_posting=True)
                ]
            ),
            inventory_location_service=_ns(
                list_inventory_locations=lambda company_id, active_only=True: [
                    _ns(id=51, code="MAIN", name="Main Warehouse")
                ]
            ),
            contract_service=_ns(list_contracts=lambda company_id: []),
            project_service=_ns(list_projects=lambda company_id: []),
        )

        dialog = InventoryDocumentDialog(registry, 1, "Test Company")
        self.addCleanup(dialog.close)

        grid = dialog._lines_grid
        table = grid._table
        self.assertNotEqual(table.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)

        grid._add_empty_row()
        self.app.processEvents()

        # Select item in row 0 — should auto-set UoM
        model = grid._model
        from PySide6.QtCore import Qt as _Qt
        model.setData(model.index(0, 1), 31, _Qt.ItemDataRole.UserRole)
        model.setData(model.index(0, 1), "ITEM-001 - Steel Sheet", _Qt.ItemDataRole.DisplayRole)
        self.app.processEvents()

        uom_value = model.data(model.index(0, 2), _Qt.ItemDataRole.UserRole)
        self.assertEqual(uom_value, 7)

        # Set qty and unit cost
        model.setData(model.index(0, 3), Decimal("3"), _Qt.ItemDataRole.UserRole)
        model.setData(model.index(0, 3), "3", _Qt.ItemDataRole.DisplayRole)
        model.setData(model.index(0, 4), Decimal("12.50"), _Qt.ItemDataRole.UserRole)
        model.setData(model.index(0, 4), "12.50", _Qt.ItemDataRole.DisplayRole)
        self.app.processEvents()

        total, _, _, count = grid.calculate_totals()
        self.assertEqual(total, Decimal("37.50"))
        self.assertEqual(dialog._total_value.text(), "37.50")

        dialog._type_combo.set_current_value("issue")
        dialog._on_document_type_changed()
        self.app.processEvents()
        self.assertIn("draft value preview", dialog._document_hint_label.text().lower())


if __name__ == "__main__":
    unittest.main()
