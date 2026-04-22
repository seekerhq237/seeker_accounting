from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.dto.company_dto import CompanyListItemDTO
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository

logger = logging.getLogger(__name__)

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]

_PURGE_WINDOW_DAYS = 30


class CompanyPurgeService:
    """Handles permanent purge of companies past their 30-day deletion window.

    The purge sequence runs at application startup. For each overdue company,
    the bootstrap layer shows a UI export prompt BEFORE calling permanently_purge_company().
    This service only provides the data query and the actual deletion — no UI concerns.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory

    def get_companies_due_for_purge(self) -> list[CompanyListItemDTO]:
        """Return all companies whose deletion window has expired (read-only)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=_PURGE_WINDOW_DAYS)
        with self._unit_of_work_factory() as uow:
            repo = self._company_repository_factory(uow.session)
            companies = repo.list_pending_deletion_before(cutoff)
            return [
                CompanyListItemDTO(
                    id=c.id,
                    legal_name=c.legal_name,
                    display_name=c.display_name,
                    country_code=c.country_code,
                    base_currency_code=c.base_currency_code,
                    logo_storage_path=c.logo_storage_path,
                    is_active=c.is_active,
                    updated_at=c.updated_at,
                    deleted_at=c.deleted_at,
                )
                for c in companies
            ]

    def permanently_purge_company(self, company_id: int) -> None:
        """Permanently delete all data for the given company_id across all tables.

        Executes DELETEs in dependency order (leaf → root) using raw SQL so that
        no ORM models need to be imported. Each table group is wrapped in a
        try/except to tolerate schema differences across migration states.
        """
        logger.warning("Permanently purging all data for company_id=%d", company_id)
        with self._unit_of_work_factory() as uow:
            session = uow.session
            cid = company_id

            # ── Payroll (deepest leaves first) ────────────────────────────────
            self._safe_delete(
                session,
                "DELETE FROM payroll_remittance_lines "
                "WHERE batch_id IN (SELECT id FROM payroll_remittance_batches WHERE company_id = :cid)",
                cid, "payroll_remittance_lines",
            )
            self._safe_delete_by_company(session, "payroll_remittance_batches", cid)
            self._safe_delete_by_company(session, "payroll_payment_records", cid)
            self._safe_delete(
                session,
                "DELETE FROM payroll_input_lines "
                "WHERE batch_id IN (SELECT id FROM payroll_input_batches WHERE company_id = :cid)",
                cid, "payroll_input_lines",
            )
            self._safe_delete_by_company(session, "payroll_input_batches", cid)
            self._safe_delete(
                session,
                "DELETE FROM payroll_run_lines "
                "WHERE run_id IN (SELECT id FROM payroll_runs WHERE company_id = :cid)",
                cid, "payroll_run_lines",
            )
            self._safe_delete_by_company(session, "payroll_run_employees", cid)
            self._safe_delete_by_company(session, "payroll_runs", cid)
            self._safe_delete_by_company(session, "employee_component_assignments", cid)
            self._safe_delete_by_company(session, "employee_compensation_profiles", cid)
            self._safe_delete_by_company(session, "employees", cid)
            self._safe_delete_by_company(session, "departments", cid)
            self._safe_delete_by_company(session, "positions", cid)
            self._safe_delete(
                session,
                "DELETE FROM payroll_rule_brackets "
                "WHERE rule_set_id IN (SELECT id FROM payroll_rule_sets WHERE company_id = :cid)",
                cid, "payroll_rule_brackets",
            )
            self._safe_delete_by_company(session, "payroll_rule_sets", cid)
            self._safe_delete_by_company(session, "payroll_components", cid)
            self._safe_delete_by_company(session, "company_payroll_settings", cid)

            # ── Inventory ─────────────────────────────────────────────────────
            self._safe_delete(
                session,
                "DELETE FROM inventory_document_lines "
                "WHERE document_id IN (SELECT id FROM inventory_documents WHERE company_id = :cid)",
                cid, "inventory_document_lines",
            )
            self._safe_delete_by_company(session, "inventory_cost_layers", cid)
            self._safe_delete_by_company(session, "inventory_documents", cid)
            self._safe_delete_by_company(session, "items", cid)
            self._safe_delete_by_company(session, "item_categories", cid)
            self._safe_delete_by_company(session, "inventory_locations", cid)
            self._safe_delete_by_company(session, "units_of_measure", cid)

            # ── Fixed assets ──────────────────────────────────────────────────
            self._safe_delete(
                session,
                "DELETE FROM asset_depreciation_pool_members "
                "WHERE pool_id IN (SELECT id FROM asset_depreciation_pools WHERE company_id = :cid)",
                cid, "asset_depreciation_pool_members",
            )
            self._safe_delete(
                session,
                "DELETE FROM asset_depreciation_run_lines "
                "WHERE run_id IN (SELECT id FROM asset_depreciation_runs WHERE company_id = :cid)",
                cid, "asset_depreciation_run_lines",
            )
            self._safe_delete_by_company(session, "asset_depreciation_runs", cid)
            self._safe_delete_by_company(session, "asset_usage_records", cid)
            self._safe_delete_by_company(session, "asset_depletion_profiles", cid)
            self._safe_delete_by_company(session, "asset_depreciation_settings", cid)
            self._safe_delete_by_company(session, "asset_components", cid)
            self._safe_delete_by_company(session, "asset_depreciation_pools", cid)
            self._safe_delete_by_company(session, "assets", cid)
            self._safe_delete_by_company(session, "asset_categories", cid)

            # ── Treasury / Banking ────────────────────────────────────────────
            self._safe_delete(
                session,
                "DELETE FROM bank_reconciliation_matches "
                "WHERE session_id IN (SELECT id FROM bank_reconciliation_sessions WHERE company_id = :cid)",
                cid, "bank_reconciliation_matches",
            )
            self._safe_delete_by_company(session, "bank_reconciliation_sessions", cid)
            self._safe_delete(
                session,
                "DELETE FROM bank_statement_lines "
                "WHERE batch_id IN (SELECT id FROM bank_statement_import_batches WHERE company_id = :cid)",
                cid, "bank_statement_lines",
            )
            self._safe_delete_by_company(session, "bank_statement_import_batches", cid)
            self._safe_delete(
                session,
                "DELETE FROM treasury_transaction_lines "
                "WHERE transaction_id IN (SELECT id FROM treasury_transactions WHERE company_id = :cid)",
                cid, "treasury_transaction_lines",
            )
            self._safe_delete_by_company(session, "treasury_transactions", cid)
            self._safe_delete_by_company(session, "treasury_transfers", cid)
            self._safe_delete_by_company(session, "financial_accounts", cid)

            # ── Sales / AR ────────────────────────────────────────────────────
            self._safe_delete_by_company(session, "customer_receipt_allocations", cid)
            self._safe_delete_by_company(session, "customer_receipts", cid)
            self._safe_delete(
                session,
                "DELETE FROM sales_invoice_lines "
                "WHERE invoice_id IN (SELECT id FROM sales_invoices WHERE company_id = :cid)",
                cid, "sales_invoice_lines",
            )
            self._safe_delete_by_company(session, "sales_invoices", cid)
            self._safe_delete_by_company(session, "customers", cid)
            self._safe_delete_by_company(session, "customer_groups", cid)

            # ── Purchases / AP ────────────────────────────────────────────────
            self._safe_delete_by_company(session, "supplier_payment_allocations", cid)
            self._safe_delete_by_company(session, "supplier_payments", cid)
            self._safe_delete(
                session,
                "DELETE FROM purchase_bill_lines "
                "WHERE bill_id IN (SELECT id FROM purchase_bills WHERE company_id = :cid)",
                cid, "purchase_bill_lines",
            )
            self._safe_delete_by_company(session, "purchase_bills", cid)
            self._safe_delete_by_company(session, "suppliers", cid)
            self._safe_delete_by_company(session, "supplier_groups", cid)

            # ── Journals ──────────────────────────────────────────────────────
            self._safe_delete(
                session,
                "DELETE FROM journal_entry_lines "
                "WHERE journal_entry_id IN (SELECT id FROM journal_entries WHERE company_id = :cid)",
                cid, "journal_entry_lines",
            )
            self._safe_delete_by_company(session, "journal_entries", cid)

            # ── Accounting reference (company-scoped) ─────────────────────────
            self._safe_delete_by_company(session, "tax_code_account_mappings", cid)
            self._safe_delete_by_company(session, "account_role_mappings", cid)
            self._safe_delete_by_company(session, "accounts", cid)
            self._safe_delete_by_company(session, "tax_codes", cid)
            self._safe_delete_by_company(session, "payment_terms", cid)
            self._safe_delete_by_company(session, "document_sequences", cid)
            self._safe_delete_by_company(session, "fiscal_periods", cid)
            self._safe_delete_by_company(session, "fiscal_years", cid)

            # ── Audit events ──────────────────────────────────────────────────
            self._safe_delete_by_company(session, "audit_events", cid)

            # ── Company relations and settings ────────────────────────────────
            self._safe_delete_by_company(session, "user_company_access", cid)
            self._safe_delete_by_company(session, "company_project_preferences", cid)
            self._safe_delete_by_company(session, "company_fiscal_defaults", cid)
            self._safe_delete_by_company(session, "company_preferences", cid)

            # ── Company row ───────────────────────────────────────────────────
            self._safe_delete(
                session,
                "DELETE FROM companies WHERE id = :cid",
                cid, "companies",
            )

            uow.commit()
            logger.info("Company id=%d permanently purged.", company_id)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _safe_delete_by_company(self, session: Session, table: str, company_id: int) -> None:
        self._safe_delete(
            session,
            f"DELETE FROM {table} WHERE company_id = :cid",
            company_id,
            table,
        )

    def _safe_delete(self, session: Session, sql: str, company_id: int, label: str) -> None:
        try:
            session.execute(text(sql), {"cid": company_id})
        except Exception:
            logger.warning("Purge skipped table/query '%s' (may not exist or column differs).", label)
