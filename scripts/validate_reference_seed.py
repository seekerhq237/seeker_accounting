"""Quick validation of global reference data seeding."""
from seeker_accounting.config.settings import load_settings
from seeker_accounting.app.dependency.factories import create_session_context
from seeker_accounting.modules.accounting.reference_data.services.reference_data_service import ReferenceDataService
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.accounting.reference_data.repositories.account_class_repository import AccountClassRepository
from seeker_accounting.modules.accounting.reference_data.repositories.account_type_repository import AccountTypeRepository
from seeker_accounting.modules.accounting.reference_data.repositories.payment_term_repository import PaymentTermRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.db.migrations.init import ensure_database_schema

settings = load_settings()
ensure_database_schema(settings.database_url)
session_context = create_session_context(settings)

svc = ReferenceDataService(
    unit_of_work_factory=session_context.unit_of_work_factory,
    country_repository_factory=CountryRepository,
    currency_repository_factory=CurrencyRepository,
    account_class_repository_factory=AccountClassRepository,
    account_type_repository_factory=AccountTypeRepository,
    payment_term_repository_factory=PaymentTermRepository,
    company_repository_factory=CompanyRepository,
)

# First run
r1 = svc.ensure_global_reference_data_seed()
print(f"Run 1: {r1.countries_inserted} countries, {r1.currencies_inserted} currencies inserted")

# Second run (idempotency check)
r2 = svc.ensure_global_reference_data_seed()
print(f"Run 2: {r2.countries_inserted} countries, {r2.currencies_inserted} currencies inserted")
assert r2.countries_inserted == 0, "Idempotency failed for countries"
assert r2.currencies_inserted == 0, "Idempotency failed for currencies"
print("Idempotency: PASS")

# Verify totals
countries = svc.list_active_countries()
currencies = svc.list_active_currencies()
print(f"Active countries: {len(countries)}")
print(f"Active currencies: {len(currencies)}")

# Verify XAF and XOF
currency_codes = {c.code for c in currencies}
assert "XAF" in currency_codes, "XAF not found!"
assert "XOF" in currency_codes, "XOF not found!"
print("XAF present: YES")
print("XOF present: YES")

# Spot checks
cm = [c for c in countries if c.code == "CM"]
print(f"Cameroon: {cm[0].name if cm else 'NOT FOUND'}")
us = [c for c in countries if c.code == "US"]
print(f"United States: {us[0].name if us else 'NOT FOUND'}")

xaf = [c for c in currencies if c.code == "XAF"]
print(f"XAF: {xaf[0].name} (symbol={xaf[0].code})")
xof = [c for c in currencies if c.code == "XOF"]
print(f"XOF: {xof[0].name} (symbol={xof[0].code})")

print("\nAll checks PASSED.")
