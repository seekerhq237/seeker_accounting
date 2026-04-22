from __future__ import annotations

from contextlib import contextmanager
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
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import (
    CreateAccountCommand,
)
from seeker_accounting.modules.accounting.reference_data.constants.account_role_codes import (
    ACCOUNT_ROLE_DEFINITION_BY_CODE,
)
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import (
    CreatePaymentTermCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerCommand,
    CreateCustomerGroupCommand,
)
from seeker_accounting.modules.customers.ui.customer_dialog import CustomerDialog
from seeker_accounting.modules.customers.ui.customers_page import CustomersPage
from seeker_accounting.modules.suppliers.dto.supplier_commands import (
    CreateSupplierCommand,
    CreateSupplierGroupCommand,
)
from seeker_accounting.modules.suppliers.ui.supplier_dialog import SupplierDialog
from seeker_accounting.modules.suppliers.ui.suppliers_page import SuppliersPage
from seeker_accounting.platform.exceptions import ConflictError, ValidationError


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

    _ensure_country_and_currency(registry)

    primary_company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Slice Seven Smoke Company SARL",
            display_name="Slice Seven Smoke Company",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    secondary_company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Slice Seven Smoke Company Two SARL",
            display_name="Slice Seven Smoke Company Two",
            country_code="SN",
            base_currency_code="XAF",
        )
    )
    print("companies_created", primary_company.id, secondary_company.id)

    primary_term = registry.reference_data_service.create_payment_term(
        primary_company.id,
        CreatePaymentTermCommand(code="NET30", name="Net 30", days_due=30),
    )
    secondary_term = registry.reference_data_service.create_payment_term(
        secondary_company.id,
        CreatePaymentTermCommand(code="NET15", name="Net 15", days_due=15),
    )
    print("payment_terms_created", primary_term.id, secondary_term.id)

    customer_group = registry.customer_service.create_customer_group(
        primary_company.id,
        CreateCustomerGroupCommand(code="RETAIL", name="Retail Customers"),
    )
    print("customer_group_created", customer_group.id, customer_group.code)

    try:
        registry.customer_service.create_customer_group(
            primary_company.id,
            CreateCustomerGroupCommand(code="RETAIL", name="Retail Customers Duplicate"),
        )
    except ConflictError as exc:
        print("duplicate_customer_group_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Duplicate customer group code was not blocked.")

    secondary_customer_group = registry.customer_service.create_customer_group(
        secondary_company.id,
        CreateCustomerGroupCommand(code="WHOLESALE", name="Wholesale Customers"),
    )

    customer = registry.customer_service.create_customer(
        primary_company.id,
        CreateCustomerCommand(
            customer_code="CUST-001",
            display_name="Douala Retail",
            customer_group_id=customer_group.id,
            payment_term_id=primary_term.id,
            country_code="CM",
            credit_limit_amount=Decimal("1500000.00"),
        ),
    )
    print("customer_created", customer.id, customer.customer_code)

    try:
        registry.customer_service.create_customer(
            primary_company.id,
            CreateCustomerCommand(customer_code="CUST-001", display_name="Duplicate"),
        )
    except ConflictError as exc:
        print("duplicate_customer_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Duplicate customer code was not blocked.")

    try:
        registry.customer_service.create_customer(
            primary_company.id,
            CreateCustomerCommand(
                customer_code="CUST-002",
                display_name="Wrong Payment Term",
                payment_term_id=secondary_term.id,
            ),
        )
    except ValidationError as exc:
        print("customer_payment_term_validation", type(exc).__name__)
    else:
        raise RuntimeError("Cross-company customer payment term was not blocked.")

    try:
        registry.customer_service.create_customer(
            primary_company.id,
            CreateCustomerCommand(
                customer_code="CUST-003",
                display_name="Wrong Group",
                customer_group_id=secondary_customer_group.id,
            ),
        )
    except ValidationError as exc:
        print("customer_group_validation", type(exc).__name__)
    else:
        raise RuntimeError("Cross-company customer group was not blocked.")

    try:
        registry.customer_service.create_customer(
            primary_company.id,
            CreateCustomerCommand(
                customer_code="CUST-004",
                display_name="Wrong Country",
                country_code="ZZ",
            ),
        )
    except ValidationError as exc:
        print("customer_country_validation", type(exc).__name__)
    else:
        raise RuntimeError("Invalid customer country code was not blocked.")

    registry.customer_service.deactivate_customer(primary_company.id, customer.id)
    print("customer_deactivated", not registry.customer_service.get_customer(primary_company.id, customer.id).is_active)

    supplier_group = registry.supplier_service.create_supplier_group(
        primary_company.id,
        CreateSupplierGroupCommand(code="LOCAL", name="Local Suppliers"),
    )
    print("supplier_group_created", supplier_group.id, supplier_group.code)

    try:
        registry.supplier_service.create_supplier_group(
            primary_company.id,
            CreateSupplierGroupCommand(code="LOCAL", name="Duplicate Group"),
        )
    except ConflictError as exc:
        print("duplicate_supplier_group_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Duplicate supplier group code was not blocked.")

    secondary_supplier_group = registry.supplier_service.create_supplier_group(
        secondary_company.id,
        CreateSupplierGroupCommand(code="FOREIGN", name="Foreign Suppliers"),
    )

    supplier = registry.supplier_service.create_supplier(
        primary_company.id,
        CreateSupplierCommand(
            supplier_code="SUP-001",
            display_name="Cameroon Packaging",
            supplier_group_id=supplier_group.id,
            payment_term_id=primary_term.id,
            country_code="CM",
        ),
    )
    print("supplier_created", supplier.id, supplier.supplier_code)

    try:
        registry.supplier_service.create_supplier(
            primary_company.id,
            CreateSupplierCommand(supplier_code="SUP-001", display_name="Duplicate"),
        )
    except ConflictError as exc:
        print("duplicate_supplier_blocked", type(exc).__name__)
    else:
        raise RuntimeError("Duplicate supplier code was not blocked.")

    try:
        registry.supplier_service.create_supplier(
            primary_company.id,
            CreateSupplierCommand(
                supplier_code="SUP-002",
                display_name="Wrong Payment Term",
                payment_term_id=secondary_term.id,
            ),
        )
    except ValidationError as exc:
        print("supplier_payment_term_validation", type(exc).__name__)
    else:
        raise RuntimeError("Cross-company supplier payment term was not blocked.")

    try:
        registry.supplier_service.create_supplier(
            primary_company.id,
            CreateSupplierCommand(
                supplier_code="SUP-003",
                display_name="Wrong Group",
                supplier_group_id=secondary_supplier_group.id,
            ),
        )
    except ValidationError as exc:
        print("supplier_group_validation", type(exc).__name__)
    else:
        raise RuntimeError("Cross-company supplier group was not blocked.")

    try:
        registry.supplier_service.create_supplier(
            primary_company.id,
            CreateSupplierCommand(
                supplier_code="SUP-004",
                display_name="Wrong Country",
                country_code="ZZ",
            ),
        )
    except ValidationError as exc:
        print("supplier_country_validation", type(exc).__name__)
    else:
        raise RuntimeError("Invalid supplier country code was not blocked.")

    registry.supplier_service.deactivate_supplier(primary_company.id, supplier.id)
    print("supplier_deactivated", not registry.supplier_service.get_supplier(primary_company.id, supplier.id).is_active)

    registry.chart_seed_service.ensure_global_chart_reference_seed()
    classes = registry.reference_data_service.list_account_classes()
    types = registry.reference_data_service.list_account_types()
    if not classes or not types:
        raise RuntimeError("Account classes or account types are not available.")
    debit_type = next((row for row in types if row.normal_balance == "DEBIT"), types[0])
    credit_type = next((row for row in types if row.normal_balance == "CREDIT"), types[0])

    ar_inactive = registry.chart_of_accounts_service.create_account(
        primary_company.id,
        CreateAccountCommand(
            account_code="ARCTL-1",
            account_name="AR Control Inactive",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=True,
        ),
    )
    ar_active = registry.chart_of_accounts_service.create_account(
        primary_company.id,
        CreateAccountCommand(
            account_code="ARCTL-2",
            account_name="AR Control Active",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=True,
        ),
    )
    ap_active = registry.chart_of_accounts_service.create_account(
        primary_company.id,
        CreateAccountCommand(
            account_code="APCTL-1",
            account_name="AP Control Active",
            account_class_id=classes[0].id,
            account_type_id=credit_type.id,
            normal_balance=credit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=True,
        ),
    )
    print("control_accounts_created", ar_inactive.id, ar_active.id, ap_active.id)

    missing_ar = registry.control_account_foundation_service.get_customer_ar_foundation_status(primary_company.id)
    missing_ap = registry.control_account_foundation_service.get_supplier_ap_foundation_status(primary_company.id)
    print("ar_missing", not missing_ar.is_ready, "missing" in " ".join(missing_ar.issues).lower())
    print("ap_missing", not missing_ap.is_ready, "missing" in " ".join(missing_ap.issues).lower())

    registry.account_role_mapping_service.set_role_mapping(
        primary_company.id,
        SetAccountRoleMappingCommand(role_code="ar_control", account_id=ar_inactive.id),
    )
    registry.chart_of_accounts_service.deactivate_account(primary_company.id, ar_inactive.id)
    inactive_ar = registry.control_account_foundation_service.get_customer_ar_foundation_status(primary_company.id)
    print("ar_inactive", not inactive_ar.is_ready, "inactive" in " ".join(inactive_ar.issues).lower())

    registry.account_role_mapping_service.set_role_mapping(
        primary_company.id,
        SetAccountRoleMappingCommand(role_code="ar_control", account_id=ar_active.id),
    )
    ready_ar = registry.control_account_foundation_service.get_customer_ar_foundation_status(primary_company.id)
    print("ar_ready", ready_ar.is_ready, ready_ar.mapped_account_code)

    registry.account_role_mapping_service.set_role_mapping(
        primary_company.id,
        SetAccountRoleMappingCommand(role_code="ap_control", account_id=ap_active.id),
    )
    ready_ap = registry.control_account_foundation_service.get_supplier_ap_foundation_status(primary_company.id)
    print("ap_ready", ready_ap.is_ready, ready_ap.mapped_account_code)

    registry.company_context_service.clear_active_company()
    main_window = MainWindow(registry)
    main_window.show()
    app.processEvents()

    customers_page = _get_page(main_window, nav_ids.CUSTOMERS, CustomersPage, app)
    suppliers_page = _get_page(main_window, nav_ids.SUPPLIERS, SuppliersPage, app)
    print("customers_page_no_active", customers_page._stack.currentWidget() is customers_page._no_active_company_state)
    print("suppliers_page_no_active", suppliers_page._stack.currentWidget() is suppliers_page._no_active_company_state)

    active_company = registry.company_context_service.set_active_company(primary_company.id)
    app.processEvents()
    print("active_company_set", active_company.company_id, active_company.company_name)
    print("customers_page_ready", customers_page._stack.currentWidget() is customers_page._table_surface)
    print("suppliers_page_ready", suppliers_page._stack.currentWidget() is suppliers_page._table_surface)

    customer_dialog = CustomerDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.company_name if hasattr(primary_company, "company_name") else primary_company.display_name,
        parent=customers_page,
    )
    customer_dialog._customer_code_edit.setText("CUST-100")
    customer_dialog._display_name_edit.setText("Dialog Customer")
    customer_dialog._select_combo_data(customer_dialog._group_combo, customer_group.id)
    customer_dialog._select_combo_data(customer_dialog._payment_term_combo, primary_term.id)
    customer_dialog._select_combo_data(customer_dialog._country_combo, "CM")
    customer_dialog._credit_limit_edit.setText("250000.00")
    customer_dialog._handle_submit()
    if customer_dialog.saved_customer is None:
        raise RuntimeError("Customer dialog did not save a customer.")
    print("customer_dialog_saved", customer_dialog.saved_customer.id)

    edit_customer_dialog = CustomerDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.company_name if hasattr(primary_company, "company_name") else primary_company.display_name,
        customer_id=customer_dialog.saved_customer.id,
        parent=customers_page,
    )
    edit_customer_dialog._display_name_edit.setText("Dialog Customer Updated")
    edit_customer_dialog._handle_submit()
    if edit_customer_dialog.saved_customer is None:
        raise RuntimeError("Customer edit dialog did not save changes.")
    print("customer_dialog_updated", edit_customer_dialog.saved_customer.display_name)

    supplier_dialog = SupplierDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.company_name if hasattr(primary_company, "company_name") else primary_company.display_name,
        parent=suppliers_page,
    )
    supplier_dialog._supplier_code_edit.setText("SUP-100")
    supplier_dialog._display_name_edit.setText("Dialog Supplier")
    supplier_dialog._select_combo_data(supplier_dialog._group_combo, supplier_group.id)
    supplier_dialog._select_combo_data(supplier_dialog._payment_term_combo, primary_term.id)
    supplier_dialog._select_combo_data(supplier_dialog._country_combo, "CM")
    supplier_dialog._handle_submit()
    if supplier_dialog.saved_supplier is None:
        raise RuntimeError("Supplier dialog did not save a supplier.")
    print("supplier_dialog_saved", supplier_dialog.saved_supplier.id)

    edit_supplier_dialog = SupplierDialog(
        registry,
        company_id=primary_company.id,
        company_name=primary_company.company_name if hasattr(primary_company, "company_name") else primary_company.display_name,
        supplier_id=supplier_dialog.saved_supplier.id,
        parent=suppliers_page,
    )
    edit_supplier_dialog._display_name_edit.setText("Dialog Supplier Updated")
    edit_supplier_dialog._handle_submit()
    if edit_supplier_dialog.saved_supplier is None:
        raise RuntimeError("Supplier edit dialog did not save changes.")
    print("supplier_dialog_updated", edit_supplier_dialog.saved_supplier.display_name)

    customers_page.reload_customers(selected_customer_id=edit_customer_dialog.saved_customer.id)
    suppliers_page.reload_suppliers(selected_supplier_id=edit_supplier_dialog.saved_supplier.id)
    app.processEvents()

    with auto_confirm_message_boxes():
        customers_page._deactivate_selected_customer()
        suppliers_page._deactivate_selected_supplier()
    app.processEvents()
    print(
        "page_customer_deactivate",
        not registry.customer_service.get_customer(primary_company.id, edit_customer_dialog.saved_customer.id).is_active,
    )
    print(
        "page_supplier_deactivate",
        not registry.supplier_service.get_supplier(primary_company.id, edit_supplier_dialog.saved_supplier.id).is_active,
    )

    customers_page._search_edit.setText("Dialog Customer")
    suppliers_page._search_edit.setText("Dialog Supplier")
    app.processEvents()
    print("customers_search_applied", "shown of" in customers_page._record_count_label.text())
    print("suppliers_search_applied", "shown of" in suppliers_page._record_count_label.text())
    print("role_codes_present", "ar_control" in ACCOUNT_ROLE_DEFINITION_BY_CODE and "ap_control" in ACCOUNT_ROLE_DEFINITION_BY_CODE)

    main_window.close()
    app.quit()
    return 0


def _ensure_country_and_currency(registry: object) -> None:
    with registry.session_context.unit_of_work_factory() as uow:  # type: ignore[attr-defined]
        session = uow.session
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        if session.get(Country, "CM") is None:
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if session.get(Country, "SN") is None:
            session.add(Country(code="SN", name="Senegal", is_active=True))
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


def _get_page(main_window: MainWindow, nav_id: str, page_type: type, app: QApplication) -> object:
    main_window._service_registry.navigation_service.navigate(nav_id)  # type: ignore[attr-defined]
    app.processEvents()
    page = main_window.findChild(page_type)
    if page is None:
        raise RuntimeError(f"Page {page_type.__name__} could not be located.")
    return page


if __name__ == "__main__":
    raise SystemExit(main())
