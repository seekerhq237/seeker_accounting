"""slice_13d_payroll_operations

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-03-27

Slice 13D — Payroll Operations:
  - Create audit_events table (shared audit foundation)
  - Seed payroll permission codes into permissions table
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None

# ── Payroll permission seeds ─────────────────────────────────────────────────
_PAYROLL_PERMISSIONS = [
    ("payroll.setup.manage", "Manage Payroll Setup", "payroll", "Manage company payroll settings, departments, and positions"),
    ("payroll.employee.manage", "Manage Employees", "payroll", "Create, edit, and deactivate employee records"),
    ("payroll.component.manage", "Manage Payroll Components", "payroll", "Create and edit payroll components"),
    ("payroll.rule.manage", "Manage Payroll Rules", "payroll", "Create and edit payroll rule sets and brackets"),
    ("payroll.pack.apply", "Apply Statutory Packs", "payroll", "Apply and rollover statutory payroll packs"),
    ("payroll.input.manage", "Manage Payroll Inputs", "payroll", "Create, submit, and approve payroll input batches"),
    ("payroll.run.create", "Create Payroll Runs", "payroll", "Create new payroll runs"),
    ("payroll.run.calculate", "Calculate Payroll", "payroll", "Trigger payroll calculation for a run"),
    ("payroll.run.approve", "Approve Payroll Runs", "payroll", "Approve calculated payroll runs"),
    ("payroll.run.post", "Post Payroll Runs", "payroll", "Post approved payroll runs to the general ledger"),
    ("payroll.payment.manage", "Manage Employee Payments", "payroll", "Record and manage employee payment records"),
    ("payroll.remittance.manage", "Manage Remittances", "payroll", "Create and manage statutory remittance batches"),
    ("payroll.import", "Import Payroll Data", "payroll", "Import employees, components, and other payroll data"),
    ("payroll.print", "Print Payslips & Reports", "payroll", "Print payslips and payroll summary reports"),
    ("payroll.audit.view", "View Payroll Audit Log", "payroll", "View the payroll audit event log"),
]


def upgrade() -> None:
    # ── audit_events ─────────────────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type_code", sa.String(60), nullable=False),
        sa.Column("module_code", sa.String(40), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("actor_display_name", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_audit_events_company", "audit_events", ["company_id"]
    )
    op.create_index(
        "ix_audit_events_type", "audit_events", ["event_type_code"]
    )
    op.create_index(
        "ix_audit_events_module", "audit_events", ["module_code"]
    )
    op.create_index(
        "ix_audit_events_company_created",
        "audit_events",
        ["company_id", "created_at"],
    )

    # ── Seed payroll permissions ─────────────────────────────────────────────
    permissions_table = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("module_code", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions_table,
        [
            {
                "code": code,
                "name": name,
                "module_code": module,
                "description": desc,
            }
            for code, name, module, desc in _PAYROLL_PERMISSIONS
        ],
    )


def downgrade() -> None:
    # Remove seeded permissions
    op.execute(
        "DELETE FROM permissions WHERE module_code = 'payroll'"
    )
    op.drop_table("audit_events")
