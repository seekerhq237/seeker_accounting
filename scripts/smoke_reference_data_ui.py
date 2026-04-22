from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication, QMessageBox

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.app.dependency.factories import (
    create_active_company_context,
    create_app_context,
    create_navigation_service,
    create_service_registry,
    create_session_context,
    create_theme_manager,
)
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.main_window import MainWindow
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.ui.document_sequence_dialog import (
    DocumentSequenceDialog,
)
from seeker_accounting.modules.accounting.reference_data.ui.document_sequences_page import (
    DocumentSequencesPage,
)
from seeker_accounting.modules.accounting.reference_data.ui.payment_term_dialog import PaymentTermDialog
from seeker_accounting.modules.accounting.reference_data.ui.payment_terms_page import PaymentTermsPage
from seeker_accounting.modules.accounting.reference_data.ui.tax_code_dialog import TaxCodeDialog
from seeker_accounting.modules.accounting.reference_data.ui.tax_codes_page import TaxCodesPage
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand


@contextmanager
def auto_confirm_message_boxes() -> None:
    original_question = QMessageBox.question

    def _always_yes(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return QMessageBox.StandardButton.Yes

    QMessageBox.question = _always_yes  # type: ignore[assignment]
    try:
        yield
    finally:
        QMessageBox.question = original_question  # type: ignore[assignment]


@contextmanager
def capture_information_messages(messages: list[str]) -> None:
    original_information = QMessageBox.information

    def _capture(parent, title, text, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = parent, title, args, kwargs
        messages.append(text)
        return QMessageBox.StandardButton.Ok

    QMessageBox.information = _capture  # type: ignore[assignment]
    try:
        yield
    finally:
        QMessageBox.information = original_information  # type: ignore[assignment]


def main() -> int:
    app = QApplication([])
    bootstrap = bootstrap_script_runtime(app)
    settings = bootstrap.settings
    app_context = bootstrap.app_context
    session_context = bootstrap.session_context
    active_company_context = bootstrap.active_company_context
    navigation_service = bootstrap.navigation_service
    theme_manager = bootstrap.theme_manager
    registry = bootstrap.service_registry

    with registry.session_context.unit_of_work_factory() as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        if session.get(Country, "CM") is None:
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if session.get(Currency, "XAF") is None:
            session.add(
                Currency(
                    code="XAF",
                    name="Central African CFA franc",
                    symbol="FCFA",
                    decimal_places=0,
                    is_active=True,
                )
            )
        uow.commit()

    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Reference UI Smoke Company",
            display_name="Reference UI Smoke Company",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    registry.company_context_service.set_active_company(company.id)

    main_window = MainWindow(registry)
    main_window.show()
    app.processEvents()

    payment_terms_page = _get_page(main_window, nav_ids.PAYMENT_TERMS, PaymentTermsPage, app)
    tax_codes_page = _get_page(main_window, nav_ids.TAX_CODES, TaxCodesPage, app)
    document_sequences_page = _get_page(main_window, nav_ids.DOCUMENT_SEQUENCES, DocumentSequencesPage, app)

    registry.company_context_service.clear_active_company()
    app.processEvents()
    registry.navigation_service.navigate(nav_ids.PAYMENT_TERMS)
    app.processEvents()
    print("payment_terms_no_active", payment_terms_page._stack.currentWidget() is payment_terms_page._no_active_company_state)
    registry.navigation_service.navigate(nav_ids.TAX_CODES)
    app.processEvents()
    print("tax_codes_no_active", tax_codes_page._stack.currentWidget() is tax_codes_page._no_active_company_state)
    registry.navigation_service.navigate(nav_ids.DOCUMENT_SEQUENCES)
    app.processEvents()
    print(
        "document_sequences_no_active",
        document_sequences_page._stack.currentWidget() is document_sequences_page._no_active_company_state,
    )

    active_company = registry.company_context_service.set_active_company(company.id)
    app.processEvents()
    print("active_company_set", active_company.company_id, active_company.company_name)

    registry.navigation_service.navigate(nav_ids.PAYMENT_TERMS)
    app.processEvents()
    print("payment_terms_empty_after_set", payment_terms_page._stack.currentWidget() is payment_terms_page._empty_state)

    payment_term_dialog = PaymentTermDialog(
        registry,
        company_id=company.id,
        company_name=company.display_name,
        parent=payment_terms_page,
    )
    payment_term_dialog._code_edit.setText("NET30")
    payment_term_dialog._name_edit.setText("Net 30")
    payment_term_dialog._days_due_spin.setValue(30)
    payment_term_dialog._description_edit.setPlainText("Due within thirty days")
    payment_term_dialog._handle_submit()
    created_payment_term = payment_term_dialog.saved_payment_term
    if created_payment_term is None:
        raise RuntimeError("Payment term create dialog did not save.")

    payment_terms_page.reload_payment_terms(selected_payment_term_id=created_payment_term.id)
    app.processEvents()
    print("payment_term_created", created_payment_term.id, created_payment_term.code)
    print("payment_terms_rows_after_create", payment_terms_page._table.rowCount())

    payment_term_edit_dialog = PaymentTermDialog(
        registry,
        company_id=company.id,
        company_name=company.display_name,
        payment_term_id=created_payment_term.id,
        parent=payment_terms_page,
    )
    payment_term_edit_dialog._name_edit.setText("Net 45")
    payment_term_edit_dialog._days_due_spin.setValue(45)
    payment_term_edit_dialog._handle_submit()
    updated_payment_term = payment_term_edit_dialog.saved_payment_term
    if updated_payment_term is None:
        raise RuntimeError("Payment term edit dialog did not save.")

    payment_terms_page.reload_payment_terms(selected_payment_term_id=updated_payment_term.id)
    app.processEvents()
    print("payment_term_updated", updated_payment_term.id, updated_payment_term.name, updated_payment_term.days_due)

    with auto_confirm_message_boxes():
        payment_terms_page._deactivate_selected_payment_term()
    app.processEvents()
    print(
        "payment_term_active_only",
        len(registry.reference_data_service.list_payment_terms(company.id, active_only=True)),
    )

    registry.navigation_service.navigate(nav_ids.TAX_CODES)
    app.processEvents()
    print("tax_codes_empty_after_set", tax_codes_page._stack.currentWidget() is tax_codes_page._empty_state)

    tax_code_dialog = TaxCodeDialog(
        registry,
        company_id=company.id,
        company_name=company.display_name,
        parent=tax_codes_page,
    )
    tax_code_dialog._code_edit.setText("VAT_STD")
    tax_code_dialog._name_edit.setText("Standard VAT")
    tax_code_dialog._tax_type_combo.setEditText("VAT")
    tax_code_dialog._calculation_method_combo.setEditText("PERCENTAGE")
    tax_code_dialog._rate_percent_edit.setText("19.25")
    tax_code_dialog._recoverable_combo.setCurrentIndex(tax_code_dialog._recoverable_combo.findData(True))
    tax_code_dialog._effective_from_edit.setDate(tax_code_dialog._to_qdate(date(2026, 1, 1)))
    tax_code_dialog._handle_submit()
    created_tax_code = tax_code_dialog.saved_tax_code
    if created_tax_code is None:
        raise RuntimeError("Tax code create dialog did not save.")

    tax_codes_page.reload_tax_codes(selected_tax_code_id=created_tax_code.id)
    app.processEvents()
    print("tax_code_created", created_tax_code.id, created_tax_code.code, created_tax_code.rate_percent)

    tax_code_edit_dialog = TaxCodeDialog(
        registry,
        company_id=company.id,
        company_name=company.display_name,
        tax_code_id=created_tax_code.id,
        parent=tax_codes_page,
    )
    tax_code_edit_dialog._name_edit.setText("Standard VAT Updated")
    tax_code_edit_dialog._rate_percent_edit.setText("20.00")
    tax_code_edit_dialog._has_effective_to_checkbox.setChecked(True)
    tax_code_edit_dialog._effective_to_edit.setDate(tax_code_edit_dialog._to_qdate(date(2026, 12, 31)))
    tax_code_edit_dialog._handle_submit()
    updated_tax_code = tax_code_edit_dialog.saved_tax_code
    if updated_tax_code is None:
        raise RuntimeError("Tax code edit dialog did not save.")

    tax_codes_page.reload_tax_codes(selected_tax_code_id=updated_tax_code.id)
    app.processEvents()
    print("tax_code_updated", updated_tax_code.id, updated_tax_code.name, updated_tax_code.rate_percent)

    with auto_confirm_message_boxes():
        tax_codes_page._deactivate_selected_tax_code()
    app.processEvents()
    print("tax_code_active_only", len(registry.tax_setup_service.list_tax_codes(company.id, active_only=True)))

    registry.navigation_service.navigate(nav_ids.DOCUMENT_SEQUENCES)
    app.processEvents()
    print(
        "document_sequences_empty_after_set",
        document_sequences_page._stack.currentWidget() is document_sequences_page._empty_state,
    )

    document_sequence_dialog = DocumentSequenceDialog(
        registry,
        company_id=company.id,
        company_name=company.display_name,
        parent=document_sequences_page,
    )
    document_sequence_dialog._document_type_combo.setEditText("SALES_INVOICE")
    document_sequence_dialog._prefix_edit.setText("INV-")
    document_sequence_dialog._next_number_spin.setValue(42)
    document_sequence_dialog._padding_width_spin.setValue(5)
    document_sequence_dialog._reset_frequency_combo.setEditText("YEARLY")
    document_sequence_dialog._handle_submit()
    created_sequence = document_sequence_dialog.saved_sequence
    if created_sequence is None:
        raise RuntimeError("Document sequence create dialog did not save.")

    document_sequences_page.reload_document_sequences(selected_sequence_id=created_sequence.id)
    app.processEvents()
    print("document_sequence_created", created_sequence.id, created_sequence.document_type_code)

    preview_messages: list[str] = []
    with capture_information_messages(preview_messages):
        document_sequences_page._preview_selected_sequence()
    app.processEvents()
    print("document_sequence_preview", bool(preview_messages), preview_messages[-1] if preview_messages else "")

    document_sequence_edit_dialog = DocumentSequenceDialog(
        registry,
        company_id=company.id,
        company_name=company.display_name,
        sequence_id=created_sequence.id,
        parent=document_sequences_page,
    )
    document_sequence_edit_dialog._suffix_edit.setText("-A")
    document_sequence_edit_dialog._next_number_spin.setValue(7)
    document_sequence_edit_dialog._padding_width_spin.setValue(4)
    document_sequence_edit_dialog._reset_frequency_combo.setEditText("MONTHLY")
    document_sequence_edit_dialog._handle_submit()
    updated_sequence = document_sequence_edit_dialog.saved_sequence
    if updated_sequence is None:
        raise RuntimeError("Document sequence edit dialog did not save.")

    document_sequences_page.reload_document_sequences(selected_sequence_id=updated_sequence.id)
    app.processEvents()
    print("document_sequence_updated", updated_sequence.id, updated_sequence.next_number, updated_sequence.suffix)

    preview = registry.numbering_setup_service.preview_document_number(company.id, updated_sequence.id)
    print("document_sequence_preview_service", preview.preview_number)

    with auto_confirm_message_boxes():
        document_sequences_page._deactivate_selected_sequence()
    app.processEvents()
    print(
        "document_sequence_active_only",
        len(registry.numbering_setup_service.list_document_sequences(company.id, active_only=True)),
    )

    main_window.close()
    app.quit()
    return 0


def _get_page(main_window: MainWindow, nav_id: str, page_type: type, app: QApplication) -> object:
    main_window._service_registry.navigation_service.navigate(nav_id)  # type: ignore[attr-defined]
    app.processEvents()
    page = main_window.findChild(page_type)
    if page is None:
        raise RuntimeError(f"Page {page_type.__name__} could not be located.")
    return page


if __name__ == "__main__":
    raise SystemExit(main())

