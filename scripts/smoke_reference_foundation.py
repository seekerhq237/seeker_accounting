from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
    UpdateDocumentSequenceCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import (
    CreatePaymentTermCommand,
    UpdatePaymentTermCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import (
    CreateTaxCodeCommand,
    UpdateTaxCodeCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand


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
                    name="CFA Franc BEAC",
                    symbol="FCFA",
                    decimal_places=0,
                    is_active=True,
                )
            )
        uow.commit()

    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Reference Foundation Smoke Company",
            display_name="Reference Foundation Smoke Company",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    company_id = company.id
    print("company_created", company_id)

    account_classes = registry.reference_data_service.list_account_classes()
    account_types = registry.reference_data_service.list_account_types()
    print("account_classes", len(account_classes))
    print("account_types", len(account_types))

    payment_term = registry.reference_data_service.create_payment_term(
        company_id,
        CreatePaymentTermCommand(
            code="NET30",
            name="Net 30",
            days_due=30,
            description="Due within thirty days",
        ),
    )
    print("payment_term_created", payment_term.id, payment_term.code, payment_term.days_due)
    print("payment_term_list", len(registry.reference_data_service.list_payment_terms(company_id)))

    payment_term = registry.reference_data_service.update_payment_term(
        company_id,
        payment_term.id,
        UpdatePaymentTermCommand(
            code="NET45",
            name="Net 45",
            days_due=45,
            description="Updated due window",
        ),
    )
    print("payment_term_updated", payment_term.id, payment_term.code, payment_term.days_due)
    registry.reference_data_service.deactivate_payment_term(company_id, payment_term.id)
    print("payment_term_active_only", len(registry.reference_data_service.list_payment_terms(company_id, active_only=True)))

    tax_code = registry.tax_setup_service.create_tax_code(
        company_id,
        CreateTaxCodeCommand(
            code="VAT_STD",
            name="Standard VAT",
            tax_type_code="VAT",
            calculation_method_code="PERCENTAGE",
            rate_percent=Decimal("19.2500"),
            is_recoverable=True,
            effective_from=date(2026, 1, 1),
        ),
    )
    print("tax_code_created", tax_code.id, tax_code.code, tax_code.rate_percent)
    print("tax_code_list", len(registry.tax_setup_service.list_tax_codes(company_id)))

    tax_code = registry.tax_setup_service.update_tax_code(
        company_id,
        tax_code.id,
        UpdateTaxCodeCommand(
            code="VAT_STD",
            name="Standard VAT Updated",
            tax_type_code="VAT",
            calculation_method_code="PERCENTAGE",
            rate_percent=Decimal("20.0000"),
            is_recoverable=True,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31),
        ),
    )
    print("tax_code_updated", tax_code.id, tax_code.name, tax_code.rate_percent, tax_code.effective_to)
    registry.tax_setup_service.deactivate_tax_code(company_id, tax_code.id)
    print("tax_code_active_only", len(registry.tax_setup_service.list_tax_codes(company_id, active_only=True)))

    sequence = registry.numbering_setup_service.create_document_sequence(
        company_id,
        CreateDocumentSequenceCommand(
            document_type_code="SALES_INVOICE",
            prefix="INV-",
            next_number=42,
            padding_width=5,
            reset_frequency_code="YEARLY",
        ),
    )
    print("sequence_created", sequence.id, sequence.document_type_code, sequence.next_number)
    print("sequence_list", len(registry.numbering_setup_service.list_document_sequences(company_id)))
    preview = registry.numbering_setup_service.preview_document_number(company_id, sequence.id)
    print("sequence_preview", preview.sequence_id, preview.preview_number)

    sequence = registry.numbering_setup_service.update_document_sequence(
        company_id,
        sequence.id,
        UpdateDocumentSequenceCommand(
            document_type_code="SALES_INVOICE",
            prefix="INV-",
            suffix="-A",
            next_number=7,
            padding_width=4,
            reset_frequency_code="MONTHLY",
        ),
    )
    print("sequence_updated", sequence.id, sequence.next_number, sequence.suffix)
    preview = registry.numbering_setup_service.preview_document_number(company_id, sequence.id)
    print("sequence_preview_updated", preview.sequence_id, preview.preview_number)
    registry.numbering_setup_service.deactivate_document_sequence(company_id, sequence.id)
    print(
        "sequence_active_only",
        len(registry.numbering_setup_service.list_document_sequences(company_id, active_only=True)),
    )

    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
