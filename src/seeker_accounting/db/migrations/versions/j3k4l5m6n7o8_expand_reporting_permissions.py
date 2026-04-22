"""Expand reporting permissions — split balance_sheet, add operational tiles and analytics.

Revision ID: j3k4l5m6n7o8
Revises: i2j3k4l5m6n7
Create Date: 2026-03-29

Changes:
- Retire the unified reports.balance_sheet.{view,export,print} codes (3 removed).
- Add per-framework balance sheet codes:
    reports.ohada_balance_sheet.{view,export,print}
    reports.ias_balance_sheet.{view,export,print}
- Add per-tile operational report codes:
    reports.ar_aging.{view,export,print}
    reports.ap_aging.{view,export,print}
    reports.customer_statements.{view,export,print}
    reports.supplier_statements.{view,export,print}
    reports.payroll_summary.{view,export,print}
    reports.treasury_reports.{view,export,print}
- Add analytics workspace codes:
    reports.financial_analysis.{view,export,print}
Total new codes: 27. Net change: +24.

Role assignments use the catalog definitions so roles using
_permission_codes_with_prefix("reports.") pick up new codes automatically.
Roles with explicit code lists (ar_officer, ap_officer, treasury_officer) are
updated by this migration to add the relevant new tile codes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from seeker_accounting.modules.administration.rbac_catalog import (
    REPORTING_PERMISSION_DEFINITIONS,
    BASELINE_SYSTEM_ROLES,
)

revision = "j3k4l5m6n7o8"
down_revision = "i2j3k4l5m6n7"
branch_labels = None
depends_on = None

# The three codes being retired
_RETIRED_CODES = frozenset({
    "reports.balance_sheet.view",
    "reports.balance_sheet.export",
    "reports.balance_sheet.print",
})

# New permission codes being added (all codes currently in the catalog
# minus the 16 that already existed before this migration)
_EXISTING_CODES_BEFORE_MIGRATION = frozenset({
    "reports.trial_balance.view",
    "reports.trial_balance.export",
    "reports.trial_balance.print",
    "reports.general_ledger.view",
    "reports.general_ledger.export",
    "reports.general_ledger.print",
    "reports.ohada_income_statement.view",
    "reports.ohada_income_statement.export",
    "reports.ohada_income_statement.print",
    "reports.ias_income_statement.view",
    "reports.ias_income_statement.export",
    "reports.ias_income_statement.print",
    "reports.ias_templates.view",
    "reports.ias_templates.manage",
    "reports.ias_mappings.view",
    "reports.ias_mappings.manage",
})

_permissions_table = sa.table(
    "permissions",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("module_code", sa.String),
    sa.column("description", sa.String),
)

_role_permissions_table = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("permission_id", sa.Integer),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Remove retired codes (cascade-delete role_permissions first)
    # ------------------------------------------------------------------
    retired_rows = bind.execute(
        sa.text(
            "SELECT id FROM permissions WHERE code IN :codes"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(_RETIRED_CODES)},
    ).mappings().all()

    retired_ids = [row["id"] for row in retired_rows]

    if retired_ids:
        bind.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE permission_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": retired_ids},
        )
        bind.execute(
            sa.text(
                "DELETE FROM permissions WHERE id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": retired_ids},
        )

    # ------------------------------------------------------------------
    # 2. Insert new permission codes
    # ------------------------------------------------------------------
    existing_codes = set(
        bind.execute(sa.text("SELECT code FROM permissions")).scalars()
    )

    new_permission_rows = [
        {
            "code": p.code,
            "name": p.name,
            "module_code": p.module_code,
            "description": p.description,
        }
        for p in REPORTING_PERMISSION_DEFINITIONS
        if p.code not in existing_codes
        and p.code not in _EXISTING_CODES_BEFORE_MIGRATION
    ]

    if new_permission_rows:
        op.bulk_insert(_permissions_table, new_permission_rows)

    # ------------------------------------------------------------------
    # 3. Re-link role_permissions for all baseline roles
    # ------------------------------------------------------------------
    # Reload permission id map after insertions
    permission_id_by_code: dict[str, int] = {
        row["code"]: row["id"]
        for row in bind.execute(sa.text("SELECT id, code FROM permissions")).mappings().all()
    }

    role_id_by_code: dict[str, int] = {
        row["code"]: row["id"]
        for row in bind.execute(sa.text("SELECT id, code FROM roles")).mappings().all()
    }

    # Build the full set of role→permission links that *should* exist after migration
    desired_links: set[tuple[int, int]] = set()
    for role in BASELINE_SYSTEM_ROLES:
        role_id = role_id_by_code.get(role.code)
        if role_id is None:
            continue
        for perm_code in role.permission_codes:
            perm_id = permission_id_by_code.get(perm_code)
            if perm_id is not None:
                desired_links.add((role_id, perm_id))

    # Fetch what already exists
    existing_links: set[tuple[int, int]] = set(
        map(
            tuple,
            bind.execute(sa.text("SELECT role_id, permission_id FROM role_permissions")).all(),
        )
    )

    missing_links = desired_links - existing_links
    if missing_links:
        op.bulk_insert(
            _role_permissions_table,
            [{"role_id": rid, "permission_id": pid} for rid, pid in missing_links],
        )


def downgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Remove all new codes and their role_permissions links
    # ------------------------------------------------------------------
    new_codes = [
        p.code
        for p in REPORTING_PERMISSION_DEFINITIONS
        if p.code not in _EXISTING_CODES_BEFORE_MIGRATION
    ]

    if new_codes:
        new_rows = bind.execute(
            sa.text(
                "SELECT id FROM permissions WHERE code IN :codes"
            ).bindparams(sa.bindparam("codes", expanding=True)),
            {"codes": new_codes},
        ).mappings().all()
        new_ids = [row["id"] for row in new_rows]

        if new_ids:
            bind.execute(
                sa.text(
                    "DELETE FROM role_permissions WHERE permission_id IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": new_ids},
            )
            bind.execute(
                sa.text(
                    "DELETE FROM permissions WHERE id IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": new_ids},
            )

    # ------------------------------------------------------------------
    # 2. Re-insert the retired codes (best-effort restore)
    # ------------------------------------------------------------------
    existing_codes = set(
        bind.execute(sa.text("SELECT code FROM permissions")).scalars()
    )

    retired_rows = [
        {"code": c, "name": c.replace(".", " ").title(), "module_code": "reports", "description": ""}
        for c in _RETIRED_CODES
        if c not in existing_codes
    ]
    if retired_rows:
        op.bulk_insert(_permissions_table, retired_rows)
