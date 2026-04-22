"""Add backup/restore permissions and grant to company_admin.

Revision ID: r5s6t7u8v9w0
Revises: q3r4s5t6u7v8
Create Date: 2026-04-02 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r5s6t7u8v9w0"
down_revision: Union[str, None] = "q3r4s5t6u7v8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMISSIONS = (
    ("administration.backup.export", "Export System Backup", "administration",
     "Export an encrypted backup of the full application database and assets."),
    ("administration.backup.import", "Import System Backup", "administration",
     "Import an encrypted backup file and merge its data into this installation."),
)

_GRANT_TO_ROLES = ("company_admin",)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Insert permissions (idempotent) ───────────────────────────────────────
    existing_codes: set[str] = set(
        bind.execute(sa.text("SELECT code FROM permissions")).scalars()
    )
    permissions_table = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("module_code", sa.String),
        sa.column("description", sa.String),
    )
    rows_to_insert = [
        {"code": code, "name": name, "module_code": module, "description": desc}
        for code, name, module, desc in _NEW_PERMISSIONS
        if code not in existing_codes
    ]
    if rows_to_insert:
        op.bulk_insert(permissions_table, rows_to_insert)

    # ── Grant to target roles via role_permissions ────────────────────────────
    permission_id_by_code: dict[str, int] = {
        row.code: row.id
        for row in bind.execute(sa.text("SELECT id, code FROM permissions")).mappings()
    }
    role_id_by_code: dict[str, int] = {
        row.code: row.id
        for row in bind.execute(sa.text("SELECT id, code FROM roles")).mappings()
    }
    existing_rp: set[tuple[int, int]] = {
        (row.role_id, row.permission_id)
        for row in bind.execute(sa.text("SELECT role_id, permission_id FROM role_permissions")).mappings()
    }
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
    )
    rp_rows: list[dict[str, int]] = []
    for role_code in _GRANT_TO_ROLES:
        role_id = role_id_by_code.get(role_code)
        if role_id is None:
            continue
        for perm_code, _, _, _ in _NEW_PERMISSIONS:
            perm_id = permission_id_by_code.get(perm_code)
            if perm_id is None:
                continue
            if (role_id, perm_id) not in existing_rp:
                rp_rows.append({"role_id": role_id, "permission_id": perm_id})
    if rp_rows:
        op.bulk_insert(role_permissions_table, rp_rows)


def downgrade() -> None:
    bind = op.get_bind()
    for code, _, _, _ in _NEW_PERMISSIONS:
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id IN "
                    "(SELECT id FROM permissions WHERE code = :code)"),
            {"code": code},
        )
        bind.execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": code})
