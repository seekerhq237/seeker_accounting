"""Sync company_admin role to have all permissions.

Revision ID: i2j3k4l5m6n7
Revises: h1i2j3k4l5m6
Create Date: 2026-03-29

The RBAC seed migration only inserted non-payroll permissions, so
company_admin was silently missing payroll permission links.  This
migration fills any gaps: every permission row in the database that
is not yet linked to company_admin gets linked.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i2j3k4l5m6n7"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None

_ADMIN_ROLE_CODE = "company_admin"


def upgrade() -> None:
    bind = op.get_bind()

    role_row = bind.execute(
        sa.text("SELECT id FROM roles WHERE code = :code"),
        {"code": _ADMIN_ROLE_CODE},
    ).mappings().first()
    if role_row is None:
        return
    admin_role_id = role_row["id"]

    already_linked = set(
        bind.execute(
            sa.text(
                "SELECT permission_id FROM role_permissions WHERE role_id = :rid"
            ),
            {"rid": admin_role_id},
        ).scalars()
    )

    all_permissions = list(
        bind.execute(sa.text("SELECT id FROM permissions")).scalars()
    )

    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
    )

    missing = [
        {"role_id": admin_role_id, "permission_id": pid}
        for pid in all_permissions
        if pid not in already_linked
    ]
    if missing:
        op.bulk_insert(role_permissions_table, missing)


def downgrade() -> None:
    # Downgrade removes only the payroll permission links that this
    # migration would have added.  Non-payroll links already existed.
    bind = op.get_bind()

    role_row = bind.execute(
        sa.text("SELECT id FROM roles WHERE code = :code"),
        {"code": _ADMIN_ROLE_CODE},
    ).mappings().first()
    if role_row is None:
        return
    admin_role_id = role_row["id"]

    payroll_ids = list(
        bind.execute(
            sa.text(
                "SELECT id FROM permissions WHERE module_code = 'payroll'"
            )
        ).scalars()
    )
    if payroll_ids:
        placeholders = ", ".join(str(pid) for pid in payroll_ids)
        bind.execute(
            sa.text(
                f"DELETE FROM role_permissions "
                f"WHERE role_id = :rid AND permission_id IN ({placeholders})"
            ),
            {"rid": admin_role_id},
        )
