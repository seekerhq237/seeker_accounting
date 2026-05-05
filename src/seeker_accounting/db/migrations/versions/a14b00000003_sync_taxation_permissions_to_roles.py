"""Sync taxation permissions catalog into the database.

Revision ID: a14b00000003
Revises: a14b00000002
Create Date: 2026-04-29

The taxation permissions (``taxation.profile.*``, ``taxation.obligations.*``,
``taxation.returns.*``, ``taxation.payments.*``, ``taxation.dsf.export``,
``taxation.withholding.*``, ``taxation.dashboard.view``, ``taxation.audit.view``,
``taxation.returns.export_pdf``) were added to the Python catalog
(``rbac_catalog.TAXATION_PERMISSION_DEFINITIONS``) progressively across
slices T1, T4, T5, T8, T13, T15, T22-T24.  No migration ever inserted
those rows into existing databases, so freshly upgraded installs were
unable to grant them through Role Permissions administration.

This migration:

1. Inserts any missing taxation permission rows into ``permissions``.
2. Re-applies the baseline-role link sheet from the current Python
   catalog for every taxation permission, so ``company_admin``,
   ``finance_manager``, ``general_accountant`` and ``auditor_read_only``
   pick up the relevant grants without disturbing any custom links a
   user may have already made.

Idempotent: existing rows / links are preserved; only missing ones are
inserted.
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

from seeker_accounting.modules.administration.rbac_catalog import (
    BASELINE_SYSTEM_ROLES,
    TAXATION_PERMISSION_DEFINITIONS,
)


revision: str = "a14b00000003"
down_revision: Union[str, None] = "a14b00000002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


_TAXATION_PERMISSION_CODES: frozenset[str] = frozenset(
    permission.code for permission in TAXATION_PERMISSION_DEFINITIONS
)


def upgrade() -> None:
    bind = op.get_bind()

    permissions_table = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("module_code", sa.String),
        sa.column("description", sa.String),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
    )

    # ── 1. Insert missing taxation permission rows ──────────────────
    existing_permission_codes = set(
        bind.execute(sa.text("SELECT code FROM permissions")).scalars()
    )
    permission_rows_to_insert = [
        {
            "code": permission.code,
            "name": permission.name,
            "module_code": permission.module_code,
            "description": permission.description,
        }
        for permission in TAXATION_PERMISSION_DEFINITIONS
        if permission.code not in existing_permission_codes
    ]
    if permission_rows_to_insert:
        op.bulk_insert(permissions_table, permission_rows_to_insert)

    # ── 2. Re-apply baseline-role grants for taxation permissions ───
    role_id_by_code = {
        row.code: row.id
        for row in bind.execute(sa.text("SELECT id, code FROM roles")).mappings()
    }
    permission_id_by_code = {
        row.code: row.id
        for row in bind.execute(sa.text("SELECT id, code FROM permissions")).mappings()
    }
    existing_role_permissions = {
        (row.role_id, row.permission_id)
        for row in bind.execute(
            sa.text("SELECT role_id, permission_id FROM role_permissions")
        ).mappings()
    }

    role_permission_rows: list[dict[str, int]] = []
    for role in BASELINE_SYSTEM_ROLES:
        role_id = role_id_by_code.get(role.code)
        if role_id is None:
            # Role does not exist in this database; skip.  A user may
            # have removed it; do not recreate it here.
            continue
        for permission_code in role.permission_codes:
            if permission_code not in _TAXATION_PERMISSION_CODES:
                continue
            permission_id = permission_id_by_code.get(permission_code)
            if permission_id is None:
                continue
            key = (role_id, permission_id)
            if key in existing_role_permissions:
                continue
            existing_role_permissions.add(key)
            role_permission_rows.append(
                {"role_id": role_id, "permission_id": permission_id}
            )

    if role_permission_rows:
        op.bulk_insert(role_permissions_table, role_permission_rows)


def downgrade() -> None:
    """Remove the taxation permission rows and their role links.

    This is intentionally aggressive on the ``role_permissions`` side:
    every link involving a taxation permission is removed, including
    any custom links a user may have made.  This matches the policy
    of the original RBAC seed migration's downgrade.
    """
    bind = op.get_bind()

    if not _TAXATION_PERMISSION_CODES:
        return

    formatted_codes = ", ".join(f"'{code}'" for code in _TAXATION_PERMISSION_CODES)

    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            f"(SELECT id FROM permissions WHERE code IN ({formatted_codes}))"
        )
    )
    op.execute(
        sa.text(
            f"DELETE FROM permissions WHERE code IN ({formatted_codes})"
        )
    )
