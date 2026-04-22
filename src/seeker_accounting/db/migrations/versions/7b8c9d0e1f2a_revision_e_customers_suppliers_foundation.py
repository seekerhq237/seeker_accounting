"""revision_e_customers_suppliers_foundation

Revision ID: 7b8c9d0e1f2a
Revises: 6f1a2b3c4d5e
Create Date: 2026-03-24 05:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7b8c9d0e1f2a"
down_revision = "6f1a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_customer_groups_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_groups")),
        sa.UniqueConstraint("company_id", "code", name=op.f("uq_customer_groups_company_id_code")),
    )
    op.create_index("ix_customer_groups_company_id", "customer_groups", ["company_id"], unique=False)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("customer_code", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("customer_group_id", sa.Integer(), nullable=True),
        sa.Column("payment_term_id", sa.Integer(), nullable=True),
        sa.Column("tax_identifier", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address_line_1", sa.String(length=255), nullable=True),
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("credit_limit_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_customers_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["country_code"],
            ["countries.code"],
            name=op.f("fk_customers_country_code_countries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_group_id"],
            ["customer_groups.id"],
            name=op.f("fk_customers_customer_group_id_customer_groups"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payment_term_id"],
            ["payment_terms.id"],
            name=op.f("fk_customers_payment_term_id_payment_terms"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("company_id", "customer_code", name=op.f("uq_customers_company_id_customer_code")),
    )
    op.create_index("ix_customers_company_id", "customers", ["company_id"], unique=False)

    op.create_table(
        "supplier_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_supplier_groups_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supplier_groups")),
        sa.UniqueConstraint("company_id", "code", name=op.f("uq_supplier_groups_company_id_code")),
    )
    op.create_index("ix_supplier_groups_company_id", "supplier_groups", ["company_id"], unique=False)

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("supplier_code", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("supplier_group_id", sa.Integer(), nullable=True),
        sa.Column("payment_term_id", sa.Integer(), nullable=True),
        sa.Column("tax_identifier", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address_line_1", sa.String(length=255), nullable=True),
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_suppliers_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["country_code"],
            ["countries.code"],
            name=op.f("fk_suppliers_country_code_countries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payment_term_id"],
            ["payment_terms.id"],
            name=op.f("fk_suppliers_payment_term_id_payment_terms"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_group_id"],
            ["supplier_groups.id"],
            name=op.f("fk_suppliers_supplier_group_id_supplier_groups"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint("company_id", "supplier_code", name=op.f("uq_suppliers_company_id_supplier_code")),
    )
    op.create_index("ix_suppliers_company_id", "suppliers", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_suppliers_company_id", table_name="suppliers")
    op.drop_table("suppliers")
    op.drop_index("ix_supplier_groups_company_id", table_name="supplier_groups")
    op.drop_table("supplier_groups")
    op.drop_index("ix_customers_company_id", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_customer_groups_company_id", table_name="customer_groups")
    op.drop_table("customer_groups")
