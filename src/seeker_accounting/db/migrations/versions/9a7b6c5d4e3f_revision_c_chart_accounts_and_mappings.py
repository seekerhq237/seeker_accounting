"""revision_c_chart_accounts_and_mappings

Revision ID: 9a7b6c5d4e3f
Revises: 5c7c4f4a8d7e
Create Date: 2026-03-23 23:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9a7b6c5d4e3f"
down_revision = "5c7c4f4a8d7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(length=20), nullable=False),
        sa.Column("account_name", sa.String(length=255), nullable=False),
        sa.Column("account_class_id", sa.Integer(), nullable=False),
        sa.Column("account_type_id", sa.Integer(), nullable=False),
        sa.Column("parent_account_id", sa.Integer(), nullable=True),
        sa.Column("normal_balance", sa.String(length=10), nullable=False),
        sa.Column("allow_manual_posting", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_control_account", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_class_id"],
            ["account_classes.id"],
            name=op.f("fk_accounts_account_class_id_account_classes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_type_id"],
            ["account_types.id"],
            name=op.f("fk_accounts_account_type_id_account_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_accounts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_account_id"],
            ["accounts.id"],
            name=op.f("fk_accounts_parent_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("company_id", "account_code", name=op.f("uq_accounts_company_id_account_code")),
    )
    op.create_index(op.f("ix_accounts_company_id"), "accounts", ["company_id"], unique=False)
    op.create_index(op.f("ix_accounts_parent_account_id"), "accounts", ["parent_account_id"], unique=False)

    op.create_table(
        "account_role_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("role_code", sa.String(length=60), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_account_role_mappings_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_account_role_mappings_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_role_mappings")),
        sa.UniqueConstraint(
            "company_id",
            "role_code",
            name=op.f("uq_account_role_mappings_company_id_role_code"),
        ),
    )

    op.create_table(
        "tax_code_account_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("tax_code_id", sa.Integer(), nullable=False),
        sa.Column("sales_account_id", sa.Integer(), nullable=True),
        sa.Column("purchase_account_id", sa.Integer(), nullable=True),
        sa.Column("tax_liability_account_id", sa.Integer(), nullable=True),
        sa.Column("tax_asset_account_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_tax_code_account_mappings_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_account_id"],
            ["accounts.id"],
            name=op.f("fk_tax_code_account_mappings_purchase_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sales_account_id"],
            ["accounts.id"],
            name=op.f("fk_tax_code_account_mappings_sales_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tax_asset_account_id"],
            ["accounts.id"],
            name=op.f("fk_tax_code_account_mappings_tax_asset_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tax_code_id"],
            ["tax_codes.id"],
            name=op.f("fk_tax_code_account_mappings_tax_code_id_tax_codes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tax_liability_account_id"],
            ["accounts.id"],
            name=op.f("fk_tax_code_account_mappings_tax_liability_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_code_account_mappings")),
        sa.UniqueConstraint(
            "company_id",
            "tax_code_id",
            name=op.f("uq_tax_code_account_mappings_company_id_tax_code_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("tax_code_account_mappings")
    op.drop_table("account_role_mappings")
    op.drop_index(op.f("ix_accounts_parent_account_id"), table_name="accounts")
    op.drop_index(op.f("ix_accounts_company_id"), table_name="accounts")
    op.drop_table("accounts")
