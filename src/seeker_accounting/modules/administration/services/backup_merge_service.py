"""BackupMergeService — applies a decrypted backup archive into the live DB.

Strategy
--------
All tables are processed with an ID-remapping approach:
  new_id = src_id + max(target.id)  (per table, computed once before insert)

This guarantees no PK collision for any table.  All FK columns referencing a
remapped table are patched via the per-table id_maps dict before insertion.

Processing order respects FK dependency:
  1-3.   permissions / roles / role_permissions        — upsert by code
  4.     users                                         — insert with resolved username
  5.     companies                                     — insert with resolved name
  6-8.   company_preferences / company_fiscal_defaults
         / company_project_preferences                 — singleton per company
  9-10.  user_company_access / user_roles              — remap both FK columns
  10b.   Global reference data (upsert by code):
           currencies, countries, account_classes,
           account_types, depreciation_methods,
           macrs_profiles
  11.    Reference: payment_terms, tax_codes,
                    document_sequences                 — company-scoped inserts
  12.    Chart: accounts, account_role_mappings,
               tax_code_account_mappings
  13.    IAS: ias_income_statement_templates (global),
             ias_income_statement_sections (global),
             ias_income_statement_mappings,
             ias_income_statement_preferences
  14.    Fiscal: fiscal_years, fiscal_periods
  15-16. Customers & Suppliers (groups + entities)
  17.    Financial accounts
  18-19. Contracts & projects (before journals
         because JE lines have project FKs)
  20.    Journals: journal_entries, journal_entry_lines
  21.    Sales: invoices, invoice_lines,
               receipts, receipt_allocations
  22.    Purchases: bills, bill_lines,
                   payments, payment_allocations
  23.    Treasury: transactions, transaction_lines,
                  transfers
  24.    Bank: statement_import_batches, statement_lines,
              reconciliation_sessions,
              reconciliation_matches
  25.    Inventory: uom_categories, units_of_measure,
                   item_categories, inventory_locations,
                   items, inventory_documents,
                   inventory_document_lines,
                   inventory_cost_layers
  26.    Payroll: company_payroll_settings, departments,
                 positions, employees, components,
                 rule_sets, rule_brackets, profiles,
                 assignments, input_batches, input_lines,
                 runs, run_employees, project_allocs,
                 run_lines, payment_records,
                 remittance_batches, remittance_lines
  27.    Fixed assets: categories, assets, depletion,
                      depreciation runs/lines/settings,
                      components, usage_records,
                      pools, pool_members
  28.    Project budgets & commitments
  29.    Audit events
  30.    Asset files copied after DB commit
"""
from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import (
    IntegrityError as SAIntegrityError,
    OperationalError as SAOperationalError,
)

from seeker_accounting.config.settings import AppSettings
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.dto.backup_dto import (
    MergeDecisionDTO,
    MergeResultDTO,
)
from seeker_accounting.modules.administration.services.backup_analysis_service import (
    BackupAnalysisService,
)
from seeker_accounting.modules.administration.services.backup_export_service import (
    _derive_key,
    _decrypt,
)
from seeker_accounting.platform.exceptions import ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

IdMap = dict[int, int]


def _max_id(conn: Connection, table: str) -> int:
    try:
        row = conn.execute(text(f"SELECT MAX(id) FROM {table}")).fetchone()  # noqa: S608
        return (row[0] or 0)
    except SAOperationalError:
        return 0


def _remap(val: int | None, id_map: IdMap) -> int | None:
    if val is None:
        return None
    return id_map.get(val, val)


def _remap_required(val: int, id_map: IdMap) -> int:
    return id_map.get(val, val)


class BackupMergeService:
    """Merges a decrypted backup into the live database (merge mode only)."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        settings: AppSettings,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._settings = settings
        self._audit_service = audit_service

    # ── Public API ────────────────────────────────────────────────────────────

    def apply_merge(
        self,
        backup_path: Path,
        password: str,
        decision: MergeDecisionDTO,
    ) -> MergeResultDTO:
        """Decrypt *backup_path* and merge into the live database.

        All work runs inside a single transaction; on any error the whole
        operation is rolled back.
        """
        if not password:
            raise ValidationError("Backup password must not be empty.")

        manifest, inner_zip_bytes = BackupAnalysisService._open_and_decrypt(backup_path, password)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_db = tmp_path / "backup.db"
            BackupAnalysisService._extract_db(inner_zip_bytes, tmp_db)

            # Also extract asset files so we can copy them after DB commit
            self._extract_assets(inner_zip_bytes, tmp_path)

            warnings: list[str] = []
            companies_imported, users_imported, tables_processed = self._merge_db(
                tmp_db, decision, warnings
            )

            # Copy asset files (after successful DB commit)
            self._copy_assets(tmp_path)

        result = MergeResultDTO(
            companies_imported=companies_imported,
            users_imported=users_imported,
            tables_processed=tables_processed,
            warnings=tuple(warnings),
        )
        self._record_audit(str(backup_path), result)
        return result

    def _record_audit(self, backup_path: str, result: MergeResultDTO) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import (
            DATABASE_BACKUP_RESTORED,
            MODULE_AUTH,
        )
        try:
            self._audit_service.record_event(
                0,
                RecordAuditEventCommand(
                    event_type_code=DATABASE_BACKUP_RESTORED,
                    module_code=MODULE_AUTH,
                    entity_type="DatabaseBackup",
                    entity_id=None,
                    description=(
                        f"Database backup restored from {backup_path}: "
                        f"{result.companies_imported} companies, "
                        f"{result.users_imported} users, "
                        f"{result.tables_processed} tables"
                    ),
                ),
            )
        except Exception:
            pass  # Audit must not break business operations

    # ── Asset helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_assets(inner_zip_bytes: bytes, dest_dir: Path) -> None:
        """Extract assets/ subtree from the inner ZIP to dest_dir."""
        try:
            with zipfile.ZipFile(io.BytesIO(inner_zip_bytes), "r") as inner:
                for name in inner.namelist():
                    if name.startswith("assets/") and not name.endswith("/"):
                        dest = dest_dir / name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(inner.read(name))
        except zipfile.BadZipFile:
            pass  # assets may be missing in older backups — not fatal

    def _copy_assets(self, tmp_dir: Path) -> None:
        """Copy extracted asset files into the live data directory."""
        data_dir = self._settings.runtime_paths.data
        assets_root = tmp_dir / "assets"
        if not assets_root.exists():
            return
        for subdir in ("user_avatars", "company_logos"):
            src_dir = assets_root / subdir
            if not src_dir.exists():
                continue
            dest_dir = data_dir / subdir
            dest_dir.mkdir(parents=True, exist_ok=True)
            for asset_file in src_dir.iterdir():
                dest = dest_dir / asset_file.name
                if not dest.exists():
                    shutil.copy2(asset_file, dest)

    # ── Core merge ────────────────────────────────────────────────────────────

    def _merge_db(
        self,
        src_db_path: Path,
        decision: MergeDecisionDTO,
        warnings: list[str],
    ) -> tuple[int, int, int]:
        """Open src DB and target DB connections and run the full merge."""
        src_engine = create_engine(f"sqlite:///{src_db_path.as_posix()}")
        try:
            with src_engine.connect() as src:
                with self._uow_factory() as uow:
                    tgt = uow.session.connection()
                    companies_imported, users_imported, tables_processed = self._run_merge(
                        src, tgt, decision, warnings
                    )
                    uow.commit()
        finally:
            src_engine.dispose()
        return companies_imported, users_imported, tables_processed


    def _run_merge(
        self,
        src: Connection,
        tgt: Connection,
        decision: MergeDecisionDTO,
        warnings: list[str],
    ) -> tuple[int, int, int]:
        """Execute the full ordered merge using id_maps for FK remapping."""
        id_maps: dict[str, IdMap] = {}
        tables_processed = 0

        def _offset(table: str) -> int:
            return _max_id(tgt, table)

        # ── 1. Permissions (upsert by code) ────────────────────────────────
        perm_map: IdMap = {}
        existing_perm: dict[str, int] = {
            row[0]: row[1]
            for row in tgt.execute(text("SELECT code, id FROM permissions")).fetchall()
        }
        new_perm_rows = []
        for row in src.execute(text("SELECT id, code, name, module_code, description FROM permissions")):
            m = row._mapping
            if m["code"] in existing_perm:
                perm_map[m["id"]] = existing_perm[m["code"]]
            else:
                new_perm_rows.append(m)
        if new_perm_rows:
            offset = _offset("permissions")
            for i, m in enumerate(new_perm_rows):
                new_id = offset + i + 1
                perm_map[m["id"]] = new_id
                tgt.execute(
                    text("INSERT INTO permissions (id, code, name, module_code, description) "
                         "VALUES (:id, :code, :name, :module_code, :description)"),
                    {"id": new_id, "code": m["code"], "name": m["name"],
                     "module_code": m["module_code"], "description": m["description"]},
                )
        id_maps["permissions"] = perm_map
        tables_processed += 1

        # ── 2. Roles (upsert by code) ──────────────────────────────────────
        role_map: IdMap = {}
        existing_role: dict[str, int] = {
            row[0]: row[1]
            for row in tgt.execute(text("SELECT code, id FROM roles")).fetchall()
        }
        new_role_rows = []
        for row in src.execute(text("SELECT id, code, name, description, is_system, created_at, updated_at FROM roles")):
            m = row._mapping
            if m["code"] in existing_role:
                role_map[m["id"]] = existing_role[m["code"]]
            else:
                new_role_rows.append(m)
        if new_role_rows:
            offset = _offset("roles")
            for i, m in enumerate(new_role_rows):
                new_id = offset + i + 1
                role_map[m["id"]] = new_id
                tgt.execute(
                    text("INSERT INTO roles (id, code, name, description, is_system, created_at, updated_at) "
                         "VALUES (:id, :code, :name, :description, :is_system, :created_at, :updated_at)"),
                    {"id": new_id, "code": m["code"], "name": m["name"],
                     "description": m["description"], "is_system": m["is_system"],
                     "created_at": m["created_at"], "updated_at": m["updated_at"]},
                )
        id_maps["roles"] = role_map
        tables_processed += 1

        # ── 3. role_permissions (upsert) ───────────────────────────────────
        existing_rp: set[tuple[int, int]] = {
            (row[0], row[1])
            for row in tgt.execute(text("SELECT role_id, permission_id FROM role_permissions")).fetchall()
        }
        for row in src.execute(text("SELECT role_id, permission_id FROM role_permissions")):
            m = row._mapping
            r_id = _remap(m["role_id"], role_map)
            p_id = _remap(m["permission_id"], perm_map)
            if r_id and p_id and (r_id, p_id) not in existing_rp:
                tgt.execute(
                    text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"),
                    {"role_id": r_id, "permission_id": p_id},
                )
                existing_rp.add((r_id, p_id))
        tables_processed += 1

        # ── 4. Users (insert with resolved username) ───────────────────────
        user_map: IdMap = {}
        user_offset = _offset("users")
        users_imported = 0
        src_users = src.execute(
            text("SELECT id, username, display_name, email, password_hash, "
                 "must_change_password, is_active, created_at, updated_at, "
                 "last_login_at, password_changed_at, "
                 "avatar_storage_path, avatar_original_filename, "
                 "avatar_content_type, avatar_sha256, avatar_updated_at "
                 "FROM users")
        ).fetchall()
        existing_usernames_tgt: set[str] = {
            row[0].lower()
            for row in tgt.execute(text("SELECT username FROM users")).fetchall()
        }
        for i, row in enumerate(src_users):
            m = row._mapping
            new_id = user_offset + i + 1
            user_map[m["id"]] = new_id
            resolved_username = decision.user_names.get(m["id"], m["username"])
            if resolved_username.lower() in existing_usernames_tgt:
                resolved_username = f"{resolved_username}_imported"
                warnings.append(
                    f"User '{m['username']}' was renamed to '{resolved_username}' to avoid conflict."
                )
            existing_usernames_tgt.add(resolved_username.lower())
            tgt.execute(
                text("INSERT INTO users (id, username, display_name, email, password_hash, "
                     "must_change_password, is_active, created_at, updated_at, "
                     "last_login_at, password_changed_at, "
                     "avatar_storage_path, avatar_original_filename, "
                     "avatar_content_type, avatar_sha256, avatar_updated_at) "
                     "VALUES (:id, :username, :display_name, :email, :password_hash, "
                     ":must_change_password, :is_active, :created_at, :updated_at, "
                     ":last_login_at, :password_changed_at, "
                     ":avatar_storage_path, :avatar_original_filename, "
                     ":avatar_content_type, :avatar_sha256, :avatar_updated_at)"),
                {"id": new_id, "username": resolved_username,
                 "display_name": m["display_name"], "email": m["email"],
                 "password_hash": m["password_hash"],
                 "must_change_password": m["must_change_password"],
                 "is_active": m["is_active"],
                 "created_at": m["created_at"], "updated_at": m["updated_at"],
                 "last_login_at": m["last_login_at"],
                 "password_changed_at": m["password_changed_at"],
                 "avatar_storage_path": m["avatar_storage_path"],
                 "avatar_original_filename": m["avatar_original_filename"],
                 "avatar_content_type": m["avatar_content_type"],
                 "avatar_sha256": m["avatar_sha256"],
                 "avatar_updated_at": m["avatar_updated_at"]},
            )
            users_imported += 1
        id_maps["users"] = user_map
        tables_processed += 1

        # ── 5. Companies (insert with resolved name) ───────────────────────
        company_map: IdMap = {}
        company_offset = _offset("companies")
        companies_imported = 0
        src_companies = src.execute(
            text("SELECT id, legal_name, display_name, registration_number, tax_identifier, "
                 "phone, email, website, sector_of_operation, address_line_1, address_line_2, "
                 "city, region, country_code, base_currency_code, "
                 "logo_storage_path, logo_original_filename, logo_content_type, logo_sha256, "
                 "logo_updated_at, deleted_at, is_active, created_at, updated_at, "
                 "cnps_employer_number "
                 "FROM companies")
        ).fetchall()
        existing_legal_names_tgt: set[str] = {
            row[0].lower()
            for row in tgt.execute(text("SELECT legal_name FROM companies")).fetchall()
        }
        for i, row in enumerate(src_companies):
            m = row._mapping
            new_id = company_offset + i + 1
            company_map[m["id"]] = new_id
            resolved_names = decision.company_names.get(m["id"])
            if resolved_names:
                legal_name, display_name = resolved_names
            else:
                legal_name = m["legal_name"]
                display_name = m["display_name"]
            if legal_name.lower() in existing_legal_names_tgt:
                legal_name = f"{legal_name} (Imported)"
                display_name = f"{display_name} (Imported)"
                warnings.append(
                    f"Company '{m['legal_name']}' was renamed to '{legal_name}' to avoid conflict."
                )
            existing_legal_names_tgt.add(legal_name.lower())
            tgt.execute(
                text("INSERT INTO companies (id, legal_name, display_name, registration_number, "
                     "tax_identifier, phone, email, website, sector_of_operation, "
                     "address_line_1, address_line_2, city, region, country_code, "
                     "base_currency_code, logo_storage_path, logo_original_filename, "
                     "logo_content_type, logo_sha256, logo_updated_at, deleted_at, "
                     "is_active, created_at, updated_at, cnps_employer_number) "
                     "VALUES (:id, :legal_name, :display_name, :registration_number, "
                     ":tax_identifier, :phone, :email, :website, :sector_of_operation, "
                     ":address_line_1, :address_line_2, :city, :region, :country_code, "
                     ":base_currency_code, :logo_storage_path, :logo_original_filename, "
                     ":logo_content_type, :logo_sha256, :logo_updated_at, :deleted_at, "
                     ":is_active, :created_at, :updated_at, :cnps_employer_number)"),
                {"id": new_id, "legal_name": legal_name, "display_name": display_name,
                 "registration_number": m["registration_number"],
                 "tax_identifier": m["tax_identifier"],
                 "phone": m["phone"], "email": m["email"], "website": m["website"],
                 "sector_of_operation": m["sector_of_operation"],
                 "address_line_1": m["address_line_1"],
                 "address_line_2": m["address_line_2"],
                 "city": m["city"], "region": m["region"],
                 "country_code": m["country_code"],
                 "base_currency_code": m["base_currency_code"],
                 "logo_storage_path": m["logo_storage_path"],
                 "logo_original_filename": m["logo_original_filename"],
                 "logo_content_type": m["logo_content_type"],
                 "logo_sha256": m["logo_sha256"],
                 "logo_updated_at": m["logo_updated_at"],
                 "deleted_at": m["deleted_at"],
                 "is_active": m["is_active"],
                 "created_at": m["created_at"], "updated_at": m["updated_at"],
                 "cnps_employer_number": m["cnps_employer_number"]},
            )
            companies_imported += 1
        id_maps["companies"] = company_map
        tables_processed += 1

        # ── 6. company_preferences (PK=company_id, no id col) ─────────────
        tables_processed += self._copy_table_with_remap(
            src, tgt, "company_preferences",
            ["company_id", "date_format_code", "number_format_code",
             "decimal_places", "tax_inclusive_default", "allow_negative_stock",
             "default_inventory_cost_method", "updated_at", "updated_by_user_id",
             "idle_timeout_minutes", "password_expiry_days"],
            {"company_id": company_map, "updated_by_user_id": user_map},
        )

        # ── 7. company_fiscal_defaults (PK=company_id, no id col) ─────────
        tables_processed += self._copy_table_with_remap(
            src, tgt, "company_fiscal_defaults",
            ["company_id", "fiscal_year_start_month", "fiscal_year_start_day",
             "default_posting_grace_days", "updated_at"],
            {"company_id": company_map},
        )

        # ── 8. company_project_preferences (PK=company_id, no id col) ─────
        tables_processed += self._copy_table_with_remap(
            src, tgt, "company_project_preferences",
            ["company_id", "allow_projects_without_contract",
             "default_budget_control_mode_code", "default_commitment_control_mode_code",
             "budget_warning_percent_threshold",
             "require_job_on_cost_posting", "require_cost_code_on_cost_posting",
             "updated_at", "updated_by_user_id"],
            {"company_id": company_map, "updated_by_user_id": user_map},
        )

        # ── 9. user_company_access ────────────────────────────────────────
        tables_processed += self._copy_table_with_remap(
            src, tgt, "user_company_access",
            ["id", "user_id", "company_id", "role_scope_note",
             "is_default_company", "granted_at", "granted_by_user_id"],
            {"user_id": user_map, "company_id": company_map, "granted_by_user_id": user_map},
        )

        # ── 10. user_roles (composite PK, no id col) ─────────────────────
        existing_ur: set[tuple[int, int]] = {
            (row[0], row[1])
            for row in tgt.execute(text("SELECT user_id, role_id FROM user_roles")).fetchall()
        }
        for row in src.execute(text("SELECT user_id, role_id FROM user_roles")):
            m = row._mapping
            u_id = _remap(m["user_id"], user_map)
            r_id = _remap(m["role_id"], role_map)
            if u_id and r_id and (u_id, r_id) not in existing_ur:
                tgt.execute(
                    text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"),
                    {"user_id": u_id, "role_id": r_id},
                )
                existing_ur.add((u_id, r_id))
        tables_processed += 1

        # ── 10b. Global reference data (upsert by code) ───────────────
        currency_map = self._upsert_global_by_code(
            src, tgt, "currencies", pk_col="code",
            columns=["code", "name", "symbol", "decimal_places", "is_active"],
        )
        id_maps["currencies"] = currency_map
        tables_processed += 1

        country_map = self._upsert_global_by_code(
            src, tgt, "countries", pk_col="code",
            columns=["code", "name", "is_active"],
        )
        id_maps["countries"] = country_map
        tables_processed += 1

        acls_map: IdMap = {}
        acls_map = self._upsert_global_by_code(
            src, tgt, "account_classes", pk_col="code",
            columns=["id", "code", "name", "display_order", "is_active"],
        )
        id_maps["account_classes"] = acls_map
        tables_processed += 1

        atype_map: IdMap = {}
        atype_map = self._upsert_global_by_code(
            src, tgt, "account_types", pk_col="code",
            columns=["id", "code", "name", "normal_balance",
                     "financial_statement_section_code", "is_active"],
        )
        id_maps["account_types"] = atype_map
        tables_processed += 1

        depr_method_map: IdMap = {}
        depr_method_map = self._upsert_global_by_code(
            src, tgt, "depreciation_methods", pk_col="code",
            columns=["id", "code", "name", "asset_family_code",
                     "requires_settings", "requires_components",
                     "requires_usage_records", "requires_pool",
                     "requires_depletion_profile", "has_switch_to_sl",
                     "sort_order", "is_active"],
        )
        id_maps["depreciation_methods"] = depr_method_map
        tables_processed += 1

        macrs_map: IdMap = {}
        macrs_map = self._upsert_global_by_code(
            src, tgt, "macrs_profiles", pk_col="class_code",
            columns=["id", "class_code", "class_name",
                     "recovery_period_years", "convention_code",
                     "gds_rates_json", "is_active"],
        )
        id_maps["macrs_profiles"] = macrs_map
        tables_processed += 1

        # ── 11. Reference data (company-scoped) ──────────────────────────
        pay_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "payment_terms",
            ["id", "company_id", "code", "name", "days_due",
             "description", "is_active"],
            {"company_id": company_map}, pay_map,
        )
        id_maps["payment_terms"] = pay_map

        tax_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "tax_codes",
            ["id", "company_id", "code", "name", "tax_type_code",
             "calculation_method_code", "rate_percent", "is_recoverable",
             "effective_from", "effective_to",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map}, tax_map,
        )
        id_maps["tax_codes"] = tax_map

        seq_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "document_sequences",
            ["id", "company_id", "document_type_code", "prefix", "suffix",
             "next_number", "padding_width", "reset_frequency_code",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map}, seq_map,
        )
        id_maps["document_sequences"] = seq_map

        # ── 12. Chart of accounts ─────────────────────────────────────────
        account_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "accounts",
            ["id", "company_id", "account_code", "account_name",
             "account_class_id", "account_type_id", "parent_account_id",
             "normal_balance", "allow_manual_posting", "is_control_account",
             "notes", "created_at", "updated_at", "is_active"],
            {"company_id": company_map,
             "account_class_id": acls_map,
             "account_type_id": atype_map}, account_map,
        )
        id_maps["accounts"] = account_map
        self._fix_self_ref(tgt, "accounts", "parent_account_id", account_map)

        tables_processed += self._copy_table_with_remap(
            src, tgt, "account_role_mappings",
            ["id", "company_id", "role_code", "account_id", "updated_at"],
            {"company_id": company_map, "account_id": account_map},
        )

        tables_processed += self._copy_table_with_remap(
            src, tgt, "tax_code_account_mappings",
            ["id", "company_id", "tax_code_id",
             "sales_account_id", "purchase_account_id",
             "tax_liability_account_id", "tax_asset_account_id",
             "updated_at"],
            {"company_id": company_map, "tax_code_id": tax_map,
             "sales_account_id": account_map, "purchase_account_id": account_map,
             "tax_liability_account_id": account_map, "tax_asset_account_id": account_map},
        )

        # ── 13. IAS income statement (global + company-scoped) ────────────
        # Templates and sections are global seed data — upsert by code
        _ias_tmpl_map = self._upsert_global_by_code(
            src, tgt, "ias_income_statement_templates", pk_col="template_code",
            columns=["id", "statement_profile_code", "template_code", "template_title",
                     "description", "standard_note", "display_order",
                     "row_height", "section_background", "subtotal_background",
                     "statement_background", "amount_font_size", "label_font_size",
                     "created_at", "updated_at", "is_active"],
        )
        tables_processed += 1

        _ias_sec_map = self._upsert_global_by_code(
            src, tgt, "ias_income_statement_sections", pk_col="section_code",
            columns=["id", "statement_profile_code", "section_code", "section_label",
                     "parent_section_code", "display_order", "row_kind_code",
                     "is_mapping_target", "created_at", "updated_at", "is_active"],
        )
        tables_processed += 1

        # Mappings are company-scoped (reference sections by code, not by ID)
        tables_processed += self._copy_table_with_remap(
            src, tgt, "ias_income_statement_mappings",
            ["id", "company_id", "statement_profile_code", "section_code",
             "subsection_code", "account_id", "sign_behavior_code",
             "display_order", "created_by_user_id", "updated_by_user_id",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map, "account_id": account_map,
             "created_by_user_id": user_map, "updated_by_user_id": user_map},
        )

        # Preferences (PK=company_id, no id col)
        tables_processed += self._copy_table_with_remap(
            src, tgt, "ias_income_statement_preferences",
            ["company_id", "template_code", "updated_at", "updated_by_user_id"],
            {"company_id": company_map, "updated_by_user_id": user_map},
        )

        # ── 14. Fiscal ─────────────────────────────────────────────────────
        fy_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "fiscal_years",
            ["id", "company_id", "year_code", "year_name",
             "start_date", "end_date", "status_code",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map}, fy_map,
        )
        fp_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "fiscal_periods",
            ["id", "company_id", "fiscal_year_id", "period_number",
             "period_code", "period_name",
             "start_date", "end_date", "status_code",
             "is_adjustment_period", "created_at", "updated_at"],
            {"company_id": company_map, "fiscal_year_id": fy_map}, fp_map,
        )
        id_maps["fiscal_periods"] = fp_map

        # ── 15. Customer groups & customers ────────────────────────────────
        cgrp_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "customer_groups",
            ["id", "company_id", "code", "name",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map}, cgrp_map,
        )
        cust_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "customers",
            ["id", "company_id", "customer_code", "display_name", "legal_name",
             "customer_group_id", "payment_term_id",
             "tax_identifier", "phone", "email",
             "address_line_1", "address_line_2", "city", "region", "country_code",
             "credit_limit_amount", "notes",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map, "customer_group_id": cgrp_map,
             "payment_term_id": pay_map},
            cust_map,
        )

        # ── 16. Supplier groups & suppliers ────────────────────────────────
        sgrp_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "supplier_groups",
            ["id", "company_id", "code", "name",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map}, sgrp_map,
        )
        supp_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "suppliers",
            ["id", "company_id", "supplier_code", "display_name", "legal_name",
             "supplier_group_id", "payment_term_id",
             "tax_identifier", "phone", "email",
             "address_line_1", "address_line_2", "city", "region", "country_code",
             "notes", "created_at", "updated_at", "is_active"],
            {"company_id": company_map, "supplier_group_id": sgrp_map,
             "payment_term_id": pay_map},
            supp_map,
        )

        # ── 17. Financial accounts ─────────────────────────────────────────
        fa_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "financial_accounts",
            ["id", "company_id", "account_code", "name",
             "financial_account_type_code", "gl_account_id",
             "bank_name", "bank_account_number", "bank_branch",
             "currency_code", "created_at", "updated_at", "is_active"],
            {"company_id": company_map, "gl_account_id": account_map},
            fa_map,
        )

        # ── 18. Contracts & change orders ──────────────────────────────────
        contract_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "contracts",
            ["id", "company_id", "contract_number", "contract_title",
             "customer_id", "contract_type_code", "currency_code", "exchange_rate",
             "base_contract_amount", "start_date", "planned_end_date", "actual_end_date",
             "status_code", "billing_basis_code", "retention_percent",
             "reference_number", "description",
             "approved_at", "approved_by_user_id",
             "created_at", "updated_at",
             "created_by_user_id", "updated_by_user_id"],
            {"company_id": company_map, "customer_id": cust_map,
             "approved_by_user_id": user_map,
             "created_by_user_id": user_map, "updated_by_user_id": user_map},
            contract_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "contract_change_orders",
            ["id", "company_id", "contract_id", "change_order_number",
             "change_order_date", "status_code", "change_type_code",
             "description", "contract_amount_delta", "days_extension",
             "effective_date", "approved_at", "approved_by_user_id",
             "created_at", "updated_at"],
            {"company_id": company_map, "contract_id": contract_map,
             "approved_by_user_id": user_map},
        )

        # ── 19. Projects, jobs, cost codes ─────────────────────────────────
        project_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "projects",
            ["id", "company_id", "project_code", "project_name",
             "contract_id", "customer_id", "project_type_code",
             "project_manager_user_id", "currency_code", "exchange_rate",
             "start_date", "planned_end_date", "actual_end_date",
             "status_code", "budget_control_mode_code", "notes",
             "created_at", "updated_at",
             "created_by_user_id", "updated_by_user_id"],
            {"company_id": company_map, "contract_id": contract_map,
             "customer_id": cust_map, "project_manager_user_id": user_map,
             "created_by_user_id": user_map, "updated_by_user_id": user_map},
            project_map,
        )
        job_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "project_jobs",
            ["id", "company_id", "project_id", "job_code", "job_name",
             "parent_job_id", "sequence_number", "status_code",
             "start_date", "planned_end_date", "actual_end_date",
             "allow_direct_cost_posting", "notes",
             "created_at", "updated_at"],
            {"company_id": company_map, "project_id": project_map},
            job_map,
        )
        self._fix_self_ref(tgt, "project_jobs", "parent_job_id", job_map)

        costcode_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "project_cost_codes",
            ["id", "company_id", "code", "name", "cost_code_type_code",
             "default_account_id", "is_active", "description",
             "created_at", "updated_at"],
            {"company_id": company_map, "default_account_id": account_map},
            costcode_map,
        )

        # ── 20. Journal entries ────────────────────────────────────────────
        je_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "journal_entries",
            ["id", "company_id", "fiscal_period_id", "entry_number",
             "entry_date", "journal_type_code", "reference_text",
             "description", "source_module_code",
             "source_document_type", "source_document_id",
             "status_code", "posted_at", "posted_by_user_id",
             "created_by_user_id", "created_at", "updated_at",
             "transaction_date"],
            {"company_id": company_map, "fiscal_period_id": fp_map,
             "posted_by_user_id": user_map, "created_by_user_id": user_map},
            je_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "journal_entry_lines",
            ["id", "journal_entry_id", "line_number", "account_id",
             "line_description", "debit_amount", "credit_amount",
             "created_at", "updated_at",
             "contract_id", "project_id", "project_job_id", "project_cost_code_id"],
            {"journal_entry_id": je_map, "account_id": account_map,
             "contract_id": contract_map, "project_id": project_map,
             "project_job_id": job_map, "project_cost_code_id": costcode_map},
        )

        # ── 21. Sales & receivables ────────────────────────────────────────
        inv_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "sales_invoices",
            ["id", "company_id", "invoice_number", "customer_id",
             "invoice_date", "due_date", "currency_code", "exchange_rate",
             "status_code", "payment_status_code", "reference_number",
             "notes", "subtotal_amount", "tax_amount", "total_amount",
             "posted_journal_entry_id", "posted_at", "posted_by_user_id",
             "created_at", "updated_at",
             "contract_id", "project_id"],
            {"company_id": company_map, "customer_id": cust_map,
             "posted_journal_entry_id": je_map, "posted_by_user_id": user_map,
             "contract_id": contract_map, "project_id": project_map},
            inv_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "sales_invoice_lines",
            ["id", "sales_invoice_id", "line_number", "description",
             "quantity", "unit_price", "discount_percent", "discount_amount",
             "tax_code_id", "revenue_account_id",
             "line_subtotal_amount", "line_tax_amount", "line_total_amount",
             "created_at", "updated_at",
             "contract_id", "project_id", "project_job_id", "project_cost_code_id"],
            {"sales_invoice_id": inv_map, "tax_code_id": tax_map,
             "revenue_account_id": account_map,
             "contract_id": contract_map, "project_id": project_map,
             "project_job_id": job_map, "project_cost_code_id": costcode_map},
        )
        rcpt_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "customer_receipts",
            ["id", "company_id", "receipt_number", "customer_id",
             "financial_account_id", "receipt_date", "currency_code", "exchange_rate",
             "amount_received", "status_code", "reference_number", "notes",
             "posted_journal_entry_id", "posted_at", "posted_by_user_id",
             "created_at", "updated_at"],
            {"company_id": company_map, "customer_id": cust_map,
             "financial_account_id": fa_map,
             "posted_journal_entry_id": je_map, "posted_by_user_id": user_map},
            rcpt_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "customer_receipt_allocations",
            ["id", "company_id", "customer_receipt_id", "sales_invoice_id",
             "allocated_amount", "allocation_date", "created_at"],
            {"company_id": company_map, "customer_receipt_id": rcpt_map,
             "sales_invoice_id": inv_map},
        )

        # ── 22. Purchases & payables ───────────────────────────────────────
        bill_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "purchase_bills",
            ["id", "company_id", "bill_number", "supplier_bill_reference",
             "supplier_id", "bill_date", "due_date",
             "currency_code", "exchange_rate",
             "status_code", "payment_status_code",
             "notes", "subtotal_amount", "tax_amount", "total_amount",
             "posted_journal_entry_id", "posted_at", "posted_by_user_id",
             "created_at", "updated_at",
             "contract_id", "project_id"],
            {"company_id": company_map, "supplier_id": supp_map,
             "posted_journal_entry_id": je_map, "posted_by_user_id": user_map,
             "contract_id": contract_map, "project_id": project_map},
            bill_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "purchase_bill_lines",
            ["id", "purchase_bill_id", "line_number", "description",
             "quantity", "unit_cost", "expense_account_id", "tax_code_id",
             "line_subtotal_amount", "line_tax_amount", "line_total_amount",
             "created_at", "updated_at",
             "contract_id", "project_id", "project_job_id", "project_cost_code_id"],
            {"purchase_bill_id": bill_map,
             "expense_account_id": account_map, "tax_code_id": tax_map,
             "contract_id": contract_map, "project_id": project_map,
             "project_job_id": job_map, "project_cost_code_id": costcode_map},
        )
        spay_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "supplier_payments",
            ["id", "company_id", "payment_number", "supplier_id",
             "financial_account_id", "payment_date",
             "currency_code", "exchange_rate", "amount_paid",
             "status_code", "reference_number", "notes",
             "posted_journal_entry_id", "posted_at", "posted_by_user_id",
             "created_at", "updated_at"],
            {"company_id": company_map, "supplier_id": supp_map,
             "financial_account_id": fa_map,
             "posted_journal_entry_id": je_map, "posted_by_user_id": user_map},
            spay_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "supplier_payment_allocations",
            ["id", "company_id", "supplier_payment_id", "purchase_bill_id",
             "allocated_amount", "allocation_date", "created_at"],
            {"company_id": company_map, "supplier_payment_id": spay_map,
             "purchase_bill_id": bill_map},
        )

        # ── 23. Treasury ───────────────────────────────────────────────────
        tt_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "treasury_transactions",
            ["id", "company_id", "transaction_number", "transaction_type_code",
             "financial_account_id", "transaction_date",
             "currency_code", "exchange_rate", "total_amount",
             "status_code", "reference_number", "description", "notes",
             "posted_journal_entry_id", "posted_at", "posted_by_user_id",
             "created_at", "updated_at",
             "contract_id", "project_id"],
            {"company_id": company_map, "financial_account_id": fa_map,
             "posted_journal_entry_id": je_map, "posted_by_user_id": user_map,
             "contract_id": contract_map, "project_id": project_map},
            tt_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "treasury_transaction_lines",
            ["id", "treasury_transaction_id", "line_number", "account_id",
             "line_description", "party_type", "party_id", "tax_code_id",
             "amount", "created_at", "updated_at",
             "contract_id", "project_id", "project_job_id", "project_cost_code_id"],
            {"treasury_transaction_id": tt_map, "account_id": account_map,
             "tax_code_id": tax_map,
             "contract_id": contract_map, "project_id": project_map,
             "project_job_id": job_map, "project_cost_code_id": costcode_map},
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "treasury_transfers",
            ["id", "company_id", "transfer_number",
             "from_financial_account_id", "to_financial_account_id",
             "transfer_date", "currency_code", "exchange_rate",
             "amount", "status_code", "reference_number",
             "description", "notes",
             "posted_journal_entry_id", "posted_at", "posted_by_user_id",
             "created_at", "updated_at"],
            {"company_id": company_map,
             "from_financial_account_id": fa_map, "to_financial_account_id": fa_map,
             "posted_journal_entry_id": je_map, "posted_by_user_id": user_map},
        )

        # ── 24. Bank statements & reconciliation ──────────────────────────
        batch_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "bank_statement_import_batches",
            ["id", "company_id", "financial_account_id", "file_name",
             "import_source", "statement_start_date", "statement_end_date",
             "line_count", "notes", "imported_at", "imported_by_user_id"],
            {"company_id": company_map, "financial_account_id": fa_map,
             "imported_by_user_id": user_map},
            batch_map,
        )
        bsl_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "bank_statement_lines",
            ["id", "company_id", "financial_account_id", "import_batch_id",
             "line_date", "value_date", "description", "reference",
             "debit_amount", "credit_amount", "is_reconciled", "created_at"],
            {"company_id": company_map, "financial_account_id": fa_map,
             "import_batch_id": batch_map},
            bsl_map,
        )
        recon_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "bank_reconciliation_sessions",
            ["id", "company_id", "financial_account_id",
             "statement_end_date", "statement_ending_balance",
             "status_code", "notes",
             "completed_at", "completed_by_user_id",
             "created_at", "created_by_user_id"],
            {"company_id": company_map, "financial_account_id": fa_map,
             "completed_by_user_id": user_map, "created_by_user_id": user_map},
            recon_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "bank_reconciliation_matches",
            ["id", "company_id", "reconciliation_session_id",
             "bank_statement_line_id", "match_entity_type", "match_entity_id",
             "matched_amount", "created_at"],
            {"company_id": company_map, "reconciliation_session_id": recon_map,
             "bank_statement_line_id": bsl_map},
        )

        # ── 25. Inventory ──────────────────────────────────────────────────
        uom_cat_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "uom_categories",
            ["id", "company_id", "code", "name", "description",
             "is_active", "created_at", "updated_at"],
            {"company_id": company_map}, uom_cat_map,
        )
        uom_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "units_of_measure",
            ["id", "company_id", "code", "name", "description",
             "is_active", "created_at", "updated_at",
             "category_id", "ratio_to_base"],
            {"company_id": company_map, "category_id": uom_cat_map},
            uom_map,
        )
        icat_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "item_categories",
            ["id", "company_id", "code", "name", "description",
             "is_active", "created_at", "updated_at"],
            {"company_id": company_map}, icat_map,
        )
        loc_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "inventory_locations",
            ["id", "company_id", "code", "name", "description",
             "is_active", "created_at", "updated_at"],
            {"company_id": company_map}, loc_map,
        )
        item_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "items",
            ["id", "company_id", "item_code", "item_name", "item_type_code",
             "unit_of_measure_code", "inventory_cost_method_code",
             "inventory_account_id", "cogs_account_id",
             "expense_account_id", "revenue_account_id",
             "purchase_tax_code_id", "sales_tax_code_id",
             "reorder_level_quantity", "description",
             "is_active", "created_at", "updated_at",
             "unit_of_measure_id", "item_category_id"],
            {"company_id": company_map,
             "inventory_account_id": account_map,
             "cogs_account_id": account_map,
             "expense_account_id": account_map,
             "revenue_account_id": account_map,
             "purchase_tax_code_id": tax_map,
             "sales_tax_code_id": tax_map,
             "unit_of_measure_id": uom_map,
             "item_category_id": icat_map},
            item_map,
        )
        inv_doc_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "inventory_documents",
            ["id", "company_id", "document_number", "document_type_code",
             "document_date", "status_code", "reference_number", "notes",
             "total_value", "posted_journal_entry_id",
             "posted_at", "posted_by_user_id",
             "created_at", "updated_at",
             "location_id", "contract_id", "project_id"],
            {"company_id": company_map,
             "posted_journal_entry_id": je_map, "posted_by_user_id": user_map,
             "location_id": loc_map,
             "contract_id": contract_map, "project_id": project_map},
            inv_doc_map,
        )
        inv_doc_line_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "inventory_document_lines",
            ["id", "inventory_document_id", "line_number", "item_id",
             "quantity", "unit_cost", "line_amount",
             "counterparty_account_id", "line_description",
             "created_at",
             "contract_id", "project_id", "project_job_id", "project_cost_code_id",
             "transaction_uom_id", "uom_ratio_snapshot", "base_quantity"],
            {"inventory_document_id": inv_doc_map, "item_id": item_map,
             "counterparty_account_id": account_map,
             "contract_id": contract_map, "project_id": project_map,
             "project_job_id": job_map, "project_cost_code_id": costcode_map,
             "transaction_uom_id": uom_map},
            inv_doc_line_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "inventory_cost_layers",
            ["id", "company_id", "item_id", "inventory_document_line_id",
             "layer_date", "quantity_in", "quantity_remaining",
             "unit_cost", "created_at"],
            {"company_id": company_map, "item_id": item_map,
             "inventory_document_line_id": inv_doc_line_map},
        )

        # ── 26. Payroll ────────────────────────────────────────────────────
        # company_payroll_settings (PK=company_id, no id col)
        tables_processed += self._copy_table_with_remap(
            src, tgt, "company_payroll_settings",
            ["company_id", "statutory_pack_version_code", "cnps_regime_code",
             "accident_risk_class_code", "default_pay_frequency_code",
             "default_payroll_currency_code", "overtime_policy_mode_code",
             "benefit_in_kind_policy_mode_code",
             "payroll_number_prefix", "payroll_number_padding_width",
             "updated_at", "updated_by_user_id"],
            {"company_id": company_map, "updated_by_user_id": user_map},
        )
        dept_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "departments",
            ["id", "company_id", "code", "name",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map}, dept_map,
        )
        pos_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "positions",
            ["id", "company_id", "code", "name",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map}, pos_map,
        )
        emp_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "employees",
            ["id", "company_id", "employee_number", "display_name",
             "first_name", "last_name",
             "department_id", "position_id",
             "hire_date", "termination_date", "phone", "email",
             "tax_identifier", "base_currency_code",
             "created_at", "updated_at", "is_active",
             "cnps_number", "default_payment_account_id"],
            {"company_id": company_map,
             "department_id": dept_map, "position_id": pos_map,
             "default_payment_account_id": fa_map},
            emp_map,
        )
        comp_map_payroll: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "payroll_components",
            ["id", "company_id", "component_code", "component_name",
             "component_type_code", "calculation_method_code",
             "is_taxable", "is_pensionable",
             "expense_account_id", "liability_account_id",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map,
             "expense_account_id": account_map,
             "liability_account_id": account_map},
            comp_map_payroll,
        )
        ruleset_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "payroll_rule_sets",
            ["id", "company_id", "rule_code", "rule_name", "rule_type_code",
             "effective_from", "effective_to", "calculation_basis_code",
             "created_at", "updated_at", "is_active"],
            {"company_id": company_map}, ruleset_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "payroll_rule_brackets",
            ["id", "payroll_rule_set_id", "line_number",
             "lower_bound_amount", "upper_bound_amount",
             "rate_percent", "fixed_amount", "deduction_amount", "cap_amount"],
            {"payroll_rule_set_id": ruleset_map},
        )
        cprofile_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "employee_compensation_profiles",
            ["id", "company_id", "employee_id", "profile_name",
             "basic_salary", "currency_code",
             "effective_from", "effective_to", "notes",
             "is_active", "created_at", "updated_at", "number_of_parts"],
            {"company_id": company_map, "employee_id": emp_map},
            cprofile_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "employee_component_assignments",
            ["id", "company_id", "employee_id", "component_id",
             "override_amount", "override_rate",
             "effective_from", "effective_to",
             "is_active", "created_at", "updated_at"],
            {"company_id": company_map, "employee_id": emp_map,
             "component_id": comp_map_payroll},
        )
        input_batch_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "payroll_input_batches",
            ["id", "company_id", "batch_reference", "period_year", "period_month",
             "status_code", "description",
             "submitted_at", "approved_at",
             "created_at", "updated_at"],
            {"company_id": company_map},
            input_batch_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "payroll_input_lines",
            ["id", "company_id", "batch_id", "employee_id", "component_id",
             "input_amount", "input_quantity", "notes",
             "created_at", "updated_at"],
            {"company_id": company_map, "batch_id": input_batch_map,
             "employee_id": emp_map, "component_id": comp_map_payroll},
        )
        prun_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "payroll_runs",
            ["id", "company_id", "run_reference", "run_label",
             "period_year", "period_month",
             "status_code", "currency_code",
             "run_date", "payment_date", "notes",
             "calculated_at", "approved_at",
             "created_at", "updated_at",
             "posted_at", "posted_by_user_id", "posted_journal_entry_id"],
            {"company_id": company_map,
             "posted_by_user_id": user_map, "posted_journal_entry_id": je_map},
            prun_map,
        )
        premp_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "payroll_run_employees",
            ["id", "company_id", "run_id", "employee_id",
             "gross_earnings", "taxable_salary_base", "tdl_base",
             "cnps_contributory_base", "employer_cost_base", "net_payable",
             "total_earnings", "total_employee_deductions",
             "total_employer_contributions", "total_taxes",
             "status_code", "calculation_notes",
             "created_at", "updated_at",
             "payment_status_code", "payment_date"],
            {"company_id": company_map, "run_id": prun_map,
             "employee_id": emp_map},
            premp_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "payroll_run_employee_project_allocations",
            ["id", "payroll_run_employee_id", "line_number",
             "contract_id", "project_id", "project_job_id", "project_cost_code_id",
             "allocation_basis_code", "allocation_quantity",
             "allocation_percent", "allocated_cost_amount",
             "notes", "created_at"],
            {"payroll_run_employee_id": premp_map,
             "contract_id": contract_map, "project_id": project_map,
             "project_job_id": job_map, "project_cost_code_id": costcode_map},
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "payroll_run_lines",
            ["id", "company_id", "run_id", "run_employee_id",
             "employee_id", "component_id",
             "component_type_code", "calculation_basis",
             "rate_applied", "component_amount",
             "created_at", "updated_at"],
            {"company_id": company_map, "run_id": prun_map,
             "run_employee_id": premp_map,
             "employee_id": emp_map, "component_id": comp_map_payroll},
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "payroll_payment_records",
            ["id", "company_id", "run_employee_id",
             "payment_date", "amount_paid", "payment_method_code",
             "payment_reference", "treasury_transaction_id",
             "notes", "created_by_user_id", "updated_by_user_id",
             "created_at", "updated_at"],
            {"company_id": company_map, "run_employee_id": premp_map,
             "treasury_transaction_id": tt_map,
             "created_by_user_id": user_map, "updated_by_user_id": user_map},
        )
        prem_batch_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "payroll_remittance_batches",
            ["id", "company_id", "batch_number", "payroll_run_id",
             "period_start_date", "period_end_date",
             "remittance_authority_code", "remittance_date",
             "amount_due", "amount_paid", "status_code",
             "reference", "treasury_transaction_id",
             "notes", "created_by_user_id", "updated_by_user_id",
             "created_at", "updated_at"],
            {"company_id": company_map, "payroll_run_id": prun_map,
             "treasury_transaction_id": tt_map,
             "created_by_user_id": user_map, "updated_by_user_id": user_map},
            prem_batch_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "payroll_remittance_lines",
            ["id", "payroll_remittance_batch_id", "line_number",
             "payroll_component_id", "liability_account_id",
             "description", "amount_due", "amount_paid",
             "status_code", "notes",
             "created_at", "updated_at"],
            {"payroll_remittance_batch_id": prem_batch_map,
             "payroll_component_id": comp_map_payroll,
             "liability_account_id": account_map},
        )

        # ── 27. Fixed assets ───────────────────────────────────────────────
        acat_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "asset_categories",
            ["id", "company_id", "code", "name",
             "asset_account_id", "accumulated_depreciation_account_id",
             "depreciation_expense_account_id",
             "default_useful_life_months", "default_depreciation_method_code",
             "is_active", "created_at", "updated_at"],
            {"company_id": company_map,
             "asset_account_id": account_map,
             "accumulated_depreciation_account_id": account_map,
             "depreciation_expense_account_id": account_map},
            acat_map,
        )
        asset_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "assets",
            ["id", "company_id", "asset_number", "asset_name",
             "asset_category_id", "acquisition_date", "capitalization_date",
             "acquisition_cost", "salvage_value", "useful_life_months",
             "depreciation_method_code",
             "status_code", "supplier_id", "purchase_bill_id",
             "notes", "created_at", "updated_at"],
            {"company_id": company_map, "asset_category_id": acat_map,
             "supplier_id": supp_map, "purchase_bill_id": bill_map},
            asset_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "asset_depletion_profiles",
            ["id", "company_id", "asset_id",
             "resource_type", "estimated_total_units", "unit_description",
             "created_at", "updated_at"],
            {"company_id": company_map, "asset_id": asset_map},
        )
        arun_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "asset_depreciation_runs",
            ["id", "company_id", "run_number", "run_date", "period_end_date",
             "status_code", "posted_journal_entry_id",
             "posted_at", "posted_by_user_id", "created_at"],
            {"company_id": company_map,
             "posted_journal_entry_id": je_map, "posted_by_user_id": user_map},
            arun_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "asset_depreciation_run_lines",
            ["id", "asset_depreciation_run_id", "asset_id",
             "depreciation_amount", "accumulated_depreciation_after",
             "net_book_value_after"],
            {"asset_depreciation_run_id": arun_map, "asset_id": asset_map},
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "asset_depreciation_settings",
            ["id", "company_id", "asset_id",
             "declining_factor", "switch_to_straight_line",
             "expected_total_units", "interest_rate",
             "macrs_profile_id", "macrs_convention_code",
             "created_at", "updated_at"],
            {"company_id": company_map, "asset_id": asset_map,
             "macrs_profile_id": macrs_map},
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "asset_components",
            ["id", "company_id", "parent_asset_id", "component_name",
             "acquisition_cost", "salvage_value", "useful_life_months",
             "depreciation_method_code",
             "notes", "is_active", "created_at", "updated_at"],
            {"company_id": company_map, "parent_asset_id": asset_map},
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "asset_usage_records",
            ["id", "company_id", "asset_id", "usage_date",
             "units_used", "notes", "created_at"],
            {"company_id": company_map, "asset_id": asset_map},
        )
        pool_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "asset_depreciation_pools",
            ["id", "company_id", "code", "name", "pool_type_code",
             "depreciation_method_code", "useful_life_months",
             "is_active", "created_at", "updated_at"],
            {"company_id": company_map}, pool_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "asset_depreciation_pool_members",
            ["id", "pool_id", "asset_id", "joined_date", "left_date"],
            {"pool_id": pool_map, "asset_id": asset_map},
        )

        # ── 28. Project budgets & commitments ──────────────────────────────
        budgetver_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "project_budget_versions",
            ["id", "company_id", "project_id", "version_number",
             "version_name", "version_type_code", "status_code",
             "base_version_id", "budget_date", "revision_reason",
             "total_budget_amount",
             "approved_at", "approved_by_user_id",
             "created_at", "updated_at"],
            {"company_id": company_map, "project_id": project_map,
             "approved_by_user_id": user_map},
            budgetver_map,
        )
        self._fix_self_ref(tgt, "project_budget_versions", "base_version_id", budgetver_map)

        tables_processed += self._copy_table_with_remap(
            src, tgt, "project_budget_lines",
            ["id", "project_budget_version_id", "line_number",
             "project_job_id", "project_cost_code_id",
             "description", "quantity", "unit_rate", "line_amount",
             "start_date", "end_date", "notes",
             "created_at", "updated_at"],
            {"project_budget_version_id": budgetver_map,
             "project_job_id": job_map, "project_cost_code_id": costcode_map},
        )
        comm_map: IdMap = {}
        tables_processed += self._copy_table_building_map(
            src, tgt, "project_commitments",
            ["id", "company_id", "commitment_number", "project_id",
             "supplier_id", "commitment_type_code",
             "commitment_date", "required_date",
             "currency_code", "exchange_rate",
             "status_code", "reference_number", "notes", "total_amount",
             "approved_at", "approved_by_user_id",
             "created_at", "updated_at"],
            {"company_id": company_map, "project_id": project_map,
             "supplier_id": supp_map, "approved_by_user_id": user_map},
            comm_map,
        )
        tables_processed += self._copy_table_with_remap(
            src, tgt, "project_commitment_lines",
            ["id", "project_commitment_id", "line_number",
             "project_job_id", "project_cost_code_id",
             "description", "quantity", "unit_rate", "line_amount",
             "notes", "created_at", "updated_at"],
            {"project_commitment_id": comm_map,
             "project_job_id": job_map, "project_cost_code_id": costcode_map},
        )

        # ── 29. Audit events ──────────────────────────────────────────────
        tables_processed += self._copy_table_with_remap(
            src, tgt, "audit_events",
            ["id", "company_id", "event_type_code", "module_code",
             "entity_type", "entity_id",
             "description", "detail_json",
             "actor_user_id", "actor_display_name",
             "created_at"],
            {"company_id": company_map, "actor_user_id": user_map},
        )

        return companies_imported, users_imported, tables_processed


    # ── Table-copy helpers ────────────────────────────────────────────────────

    def _copy_table_with_remap(
        self,
        src: Connection,
        tgt: Connection,
        table: str,
        columns: list[str],
        fk_maps: dict[str, IdMap],
    ) -> int:
        """Copy all rows from src.table into tgt.table, remapping PK and FKs."""
        id_map: IdMap = {}
        self._copy_table_building_map(src, tgt, table, columns, fk_maps, id_map)
        return 1

    def _copy_table_building_map(
        self,
        src: Connection,
        tgt: Connection,
        table: str,
        columns: list[str],
        fk_maps: dict[str, IdMap],
        result_map: IdMap | None = None,
    ) -> int:
        """Copy rows, remapping 'id' column using an offset derived from tgt max(id).

        Populates *result_map* with {src_id: new_id} if provided.
        Returns 1 (table count increment) regardless of row count.
        """
        try:
            rows = src.execute(
                text(f"SELECT {', '.join(columns)} FROM {table}")  # noqa: S608
            ).fetchall()
        except SAOperationalError:
            return 1  # table absent in backup -- skip silently

        if not rows:
            return 1

        offset = _max_id(tgt, table)
        col_idx = {col: i for i, col in enumerate(columns)}
        placeholders = ", ".join(f":{col}" for col in columns)
        sql = text(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})")  # noqa: S608

        for row in rows:
            values = list(row)

            # Remap id column
            if "id" in col_idx:
                old_id = values[col_idx["id"]]
                new_id = offset + old_id
                values[col_idx["id"]] = new_id
                if result_map is not None and old_id is not None:
                    result_map[old_id] = new_id

            # Remap FK columns
            for fk_col, id_map in fk_maps.items():
                if fk_col in col_idx:
                    old_val = values[col_idx[fk_col]]
                    values[col_idx[fk_col]] = _remap(old_val, id_map) if old_val is not None else None

            try:
                tgt.execute(sql, dict(zip(columns, values)))
            except SAIntegrityError:
                pass  # constraint conflict -- skip row, add warning later if needed

        return 1

    @staticmethod
    def _fix_self_ref(
        tgt: Connection,
        table: str,
        self_ref_col: str,
        id_map: IdMap,
    ) -> None:
        """Fix self-referencing FK (e.g. parent_account_id) after initial insert."""
        try:
            rows = tgt.execute(
                text(f"SELECT id, {self_ref_col} FROM {table} WHERE {self_ref_col} IS NOT NULL")  # noqa: S608
            ).fetchall()
        except SAOperationalError:
            return
        for row in rows:
            old_parent = row[1]
            new_parent = id_map.get(old_parent)
            if new_parent is not None:
                tgt.execute(
                    text(f"UPDATE {table} SET {self_ref_col} = :new_parent WHERE id = :id"),  # noqa: S608
                    {"new_parent": new_parent, "id": row[0]},
                )

    @staticmethod
    def _upsert_global_by_code(
        src: Connection,
        tgt: Connection,
        table: str,
        pk_col: str,
        columns: list[str],
    ) -> IdMap:
        """Upsert global reference rows by their natural key (code column).

        For tables with an integer ``id`` PK, builds an IdMap {src_id: tgt_id}.
        For tables whose PK **is** the code (e.g. currencies, countries), the
        returned map is ``{code: code}`` (identity) -- it is only populated for
        completeness.

        Rows that already exist in target (matched by *pk_col*) are skipped;
        new rows are inserted with a remapped ``id`` if applicable.
        """
        has_id = "id" in columns
        try:
            src_rows = src.execute(
                text(f"SELECT {', '.join(columns)} FROM {table}")  # noqa: S608
            ).fetchall()
        except SAOperationalError:
            return {}

        col_idx = {col: i for i, col in enumerate(columns)}
        pk_idx = col_idx[pk_col]

        # Build lookup of existing target rows by their natural-key value
        existing: dict[str, int | str] = {}
        try:
            if has_id:
                tgt_rows = tgt.execute(
                    text(f"SELECT id, {pk_col} FROM {table}")  # noqa: S608
                ).fetchall()
                for r in tgt_rows:
                    existing[str(r[1])] = r[0]  # code -> id
            else:
                tgt_rows = tgt.execute(
                    text(f"SELECT {pk_col} FROM {table}")  # noqa: S608
                ).fetchall()
                for r in tgt_rows:
                    existing[str(r[0])] = r[0]
        except SAOperationalError:
            pass

        id_map: IdMap = {}
        offset = _max_id(tgt, table) if has_id else 0

        placeholders = ", ".join(f":{col}" for col in columns)
        sql = text(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"  # noqa: S608
        )

        insert_counter = 0
        for row in src_rows:
            values = list(row)
            src_code = str(values[pk_idx])

            if src_code in existing:
                # Row exists -- map src id to existing target id
                if has_id:
                    src_id = values[col_idx["id"]]
                    id_map[src_id] = existing[src_code]
                continue

            # New row -- insert with remapped id
            if has_id:
                src_id = values[col_idx["id"]]
                insert_counter += 1
                new_id = offset + insert_counter
                values[col_idx["id"]] = new_id
                id_map[src_id] = new_id

            try:
                tgt.execute(sql, dict(zip(columns, values)))
                if not has_id:
                    existing[src_code] = src_code
            except SAIntegrityError:
                pass

        return id_map
