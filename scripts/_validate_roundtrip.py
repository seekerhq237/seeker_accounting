"""Round-trip validation of export + merge service compatibility.

Phase 1: Export from live DB and verify the backup contains all tables
Phase 2: Decrypt and verify column parity with live DB
Phase 3: Try importing into a COPY of the live DB (merge into itself)
"""
import sqlite3, tempfile, os, sys, io, json, zipfile, shutil
from pathlib import Path

# ── Phase 0: Live DB stats ──────────────────────────────────────────────────
db_path = ".seeker_runtime/data/seeker_accounting.db"
db = sqlite3.connect(db_path)

all_tables = [r[0] for r in db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]
live_counts: dict[str, int] = {}
print("== Phase 0: Live DB table counts ==")
for t in all_tables:
    cnt = db.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    live_counts[t] = cnt
    if cnt > 0:
        print(f"  {t}: {cnt}")
db.close()

# ── Phase 1: Export ─────────────────────────────────────────────────────────
print("\n== Phase 1: Export ==")
from seeker_accounting.config.settings import load_settings
from seeker_accounting.db.engine import create_database_engine
from seeker_accounting.db.session import create_session_factory
from seeker_accounting.db.unit_of_work import SqlAlchemyUnitOfWork
from seeker_accounting.modules.administration.services.backup_export_service import (
    BackupExportService, _derive_key, _decrypt,
)
from seeker_accounting.modules.administration.services.backup_analysis_service import (
    BackupAnalysisService,
)

settings = load_settings()
engine = create_database_engine(settings)
sf = create_session_factory(engine)
uow_factory = lambda: SqlAlchemyUnitOfWork(session_factory=sf)

export_svc = BackupExportService(settings=settings)
test_path = Path(tempfile.gettempdir()) / "test_roundtrip.seekerbackup"
export_svc.export(password="testpassword123", output_path=test_path)
print(f"  Export OK: {test_path}  ({os.path.getsize(test_path)} bytes)")

# ── Phase 1b: Analysis service preview ──────────────────────────────────────
analysis_svc = BackupAnalysisService(unit_of_work_factory=uow_factory)
preview = analysis_svc.analyse(backup_path=test_path, password="testpassword123")
print(f"  Analysis OK: {len(preview.companies)} companies, {len(preview.users)} users")
print(f"  Record summary: {dict(preview.record_summary)}")

# ── Phase 2: Decrypt and verify columns ─────────────────────────────────────
print("\n== Phase 2: Decrypt and verify backup DB ==")
with zipfile.ZipFile(test_path, "r") as outer:
    manifest = json.loads(outer.read("manifest.json"))
    enc_data = outer.read("data.enc")

salt = bytes.fromhex(manifest["salt_hex"])
nonce = bytes.fromhex(manifest["nonce_hex"])
key = _derive_key("testpassword123", salt)
inner_bytes = _decrypt(key, nonce, enc_data)

tmp_exported = Path(tempfile.gettempdir()) / "test_exported.db"
with zipfile.ZipFile(io.BytesIO(inner_bytes), "r") as inner:
    tmp_exported.write_bytes(inner.read("database.db"))

exported_db = sqlite3.connect(str(tmp_exported))
exported_tables = {r[0] for r in exported_db.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}

# Tables the merge service processes (from the _run_merge method)
merge_tables = [
    "permissions", "roles", "role_permissions", "users", "companies",
    "company_preferences", "company_fiscal_defaults", "company_project_preferences",
    "user_company_access", "user_roles",
    "currencies", "countries", "account_classes", "account_types",
    "depreciation_methods", "macrs_profiles",
    "payment_terms", "tax_codes", "document_sequences",
    "accounts", "account_role_mappings", "tax_code_account_mappings",
    "ias_income_statement_templates", "ias_income_statement_sections",
    "ias_income_statement_mappings", "ias_income_statement_preferences",
    "fiscal_years", "fiscal_periods",
    "customer_groups", "customers", "supplier_groups", "suppliers",
    "financial_accounts",
    "contracts", "contract_change_orders",
    "projects", "project_jobs", "project_cost_codes",
    "journal_entries", "journal_entry_lines",
    "sales_invoices", "sales_invoice_lines",
    "customer_receipts", "customer_receipt_allocations",
    "purchase_bills", "purchase_bill_lines",
    "supplier_payments", "supplier_payment_allocations",
    "treasury_transactions", "treasury_transaction_lines", "treasury_transfers",
    "bank_statement_import_batches", "bank_statement_lines",
    "bank_reconciliation_sessions", "bank_reconciliation_matches",
    "uom_categories", "units_of_measure", "item_categories", "inventory_locations",
    "items", "inventory_documents", "inventory_document_lines", "inventory_cost_layers",
    "company_payroll_settings", "departments", "positions", "employees",
    "payroll_components", "payroll_rule_sets", "payroll_rule_brackets",
    "employee_compensation_profiles", "employee_component_assignments",
    "payroll_input_batches", "payroll_input_lines",
    "payroll_runs", "payroll_run_employees",
    "payroll_run_employee_project_allocations", "payroll_run_lines",
    "payroll_payment_records", "payroll_remittance_batches", "payroll_remittance_lines",
    "asset_categories", "assets", "asset_depletion_profiles",
    "asset_depreciation_runs", "asset_depreciation_run_lines",
    "asset_depreciation_settings", "asset_components", "asset_usage_records",
    "asset_depreciation_pools", "asset_depreciation_pool_members",
    "project_budget_versions", "project_budget_lines",
    "project_commitments", "project_commitment_lines",
    "audit_events",
]

missing = [t for t in merge_tables if t not in exported_tables]
if missing:
    print(f"  FAIL: Tables missing from export: {missing}")
else:
    print(f"  All {len(merge_tables)} merge tables present in export")

# Column parity check: backup DB cols vs live DB cols
live_db = sqlite3.connect(db_path)
col_errors = 0
for t in merge_tables:
    if t not in exported_tables:
        continue
    exp_cols = {r[1] for r in exported_db.execute(f"PRAGMA table_info([{t}])").fetchall()}
    live_cols = {r[1] for r in live_db.execute(f"PRAGMA table_info([{t}])").fetchall()}
    if exp_cols != live_cols:
        print(f"  MISMATCH {t}: export extra={exp_cols - live_cols}, missing={live_cols - exp_cols}")
        col_errors += 1
if col_errors == 0:
    print("  Column parity: ALL tables match perfectly")
exported_db.close()
live_db.close()

# ── Phase 3: Merge into a copy of the live DB ──────────────────────────────
print("\n== Phase 3: Merge into DB copy ==")
from seeker_accounting.modules.administration.services.backup_merge_service import (
    BackupMergeService,
)
from seeker_accounting.modules.administration.dto.backup_dto import (
    MergeDecisionDTO,
)

# Create a copy of the live DB to use as merge target
tmp_target = Path(tempfile.gettempdir()) / "test_merge_target.db"
shutil.copy2(db_path, str(tmp_target))

# Create engine/session/uow pointing at the copy
from sqlalchemy import create_engine as _create_engine
merge_engine = _create_engine(f"sqlite:///{tmp_target.as_posix()}", connect_args={"check_same_thread": False})
merge_sf = create_session_factory(merge_engine)
merge_uow = lambda: SqlAlchemyUnitOfWork(session_factory=merge_sf)

merge_svc = BackupMergeService(
    unit_of_work_factory=merge_uow,
    settings=settings,  # original settings (assets path is fine)
)

# Build decision: empty = use source names (merge will auto-suffix conflicts)
decision = MergeDecisionDTO()

try:
    result = merge_svc.apply_merge(
        backup_path=test_path,
        password="testpassword123",
        decision=decision,
    )
    print(f"  Merge result: {result}")
    print("  MERGE SUCCEEDED")
except Exception as exc:
    print(f"  MERGE FAILED: {type(exc).__name__}: {exc}")
    import traceback
    traceback.print_exc()

# Verify counts in merged DB
print("\n== Phase 3b: Post-merge counts ==")
merged_db = sqlite3.connect(str(tmp_target))
for t in sorted(merge_tables):
    try:
        new_cnt = merged_db.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        orig = live_counts.get(t, 0)
        if new_cnt != orig:
            print(f"  {t}: {orig} -> {new_cnt}  (delta +{new_cnt - orig})")
    except Exception as e:
        print(f"  {t}: ERROR {e}")
merged_db.close()

# Cleanup
merge_engine.dispose()
engine.dispose()
tmp_exported.unlink(missing_ok=True)
tmp_target.unlink(missing_ok=True)
test_path.unlink(missing_ok=True)

print("\n== Round-trip validation COMPLETE ==")
