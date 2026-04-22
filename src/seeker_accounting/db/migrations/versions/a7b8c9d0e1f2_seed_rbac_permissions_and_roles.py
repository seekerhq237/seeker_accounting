"""Seed system permissions and baseline roles.

Revision ID: a7b8c9d0e1f2
Revises: f0a1b2c3d4e5
Create Date: 2026-03-28
"""

from __future__ import annotations

from datetime import datetime, UTC

import sqlalchemy as sa
from alembic import op

from seeker_accounting.modules.administration.rbac_catalog import (
    BASELINE_SYSTEM_ROLES,
    NON_PAYROLL_PERMISSION_DEFINITIONS,
)

revision = "a7b8c9d0e1f2"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    permissions_table = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("module_code", sa.String),
        sa.column("description", sa.String),
    )
    roles_table = sa.table(
        "roles",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
    )

    existing_permission_codes = set(bind.execute(sa.text("SELECT code FROM permissions")).scalars())
    permission_rows = [
        {
            "code": permission.code,
            "name": permission.name,
            "module_code": permission.module_code,
            "description": permission.description,
        }
        for permission in NON_PAYROLL_PERMISSION_DEFINITIONS
        if permission.code not in existing_permission_codes
    ]
    if permission_rows:
        op.bulk_insert(permissions_table, permission_rows)

    existing_role_codes = set(bind.execute(sa.text("SELECT code FROM roles")).scalars())
    now = datetime.now(UTC).replace(tzinfo=None)
    role_rows = [
        {
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_system": True,
            "created_at": now,
            "updated_at": now,
        }
        for role in BASELINE_SYSTEM_ROLES
        if role.code not in existing_role_codes
    ]
    if role_rows:
        op.bulk_insert(roles_table, role_rows)

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
        for row in bind.execute(sa.text("SELECT role_id, permission_id FROM role_permissions")).mappings()
    }

    role_permission_rows: list[dict[str, int]] = []
    for role in BASELINE_SYSTEM_ROLES:
        role_id = role_id_by_code.get(role.code)
        if role_id is None:
            continue
        for permission_code in role.permission_codes:
            permission_id = permission_id_by_code.get(permission_code)
            if permission_id is None:
                continue
            key = (role_id, permission_id)
            if key in existing_role_permissions:
                continue
            existing_role_permissions.add(key)
            role_permission_rows.append(
                {
                    "role_id": role_id,
                    "permission_id": permission_id,
                }
            )

    if role_permission_rows:
        op.bulk_insert(role_permissions_table, role_permission_rows)


def downgrade() -> None:
    role_codes = tuple(role.code for role in BASELINE_SYSTEM_ROLES)
    permission_codes = tuple(permission.code for permission in NON_PAYROLL_PERMISSION_DEFINITIONS)

    if role_codes:
        formatted_role_codes = ", ".join(f"'{code}'" for code in role_codes)
        op.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE role_id IN "
                f"(SELECT id FROM roles WHERE code IN ({formatted_role_codes}))"
            )
        )
        op.execute(sa.text(f"DELETE FROM roles WHERE code IN ({formatted_role_codes})"))

    if permission_codes:
        formatted_permission_codes = ", ".join(f"'{code}'" for code in permission_codes)
        op.execute(sa.text(f"DELETE FROM permissions WHERE code IN ({formatted_permission_codes})"))