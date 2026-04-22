"""revision_b_reference_foundation_base

Revision ID: 5c7c4f4a8d7e
Revises: 83a0b6b04650
Create Date: 2026-03-23 22:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5c7c4f4a8d7e"
down_revision = "83a0b6b04650"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_classes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_classes")),
        sa.UniqueConstraint("code", name=op.f("uq_account_classes_code")),
    )
    op.create_table(
        "account_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normal_balance", sa.String(length=10), nullable=False),
        sa.Column("financial_statement_section_code", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_types")),
        sa.UniqueConstraint("code", name=op.f("uq_account_types_code")),
    )
    op.create_table(
        "document_sequences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("document_type_code", sa.String(length=50), nullable=False),
        sa.Column("prefix", sa.String(length=20), nullable=True),
        sa.Column("suffix", sa.String(length=20), nullable=True),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.Column("padding_width", sa.Integer(), nullable=False),
        sa.Column("reset_frequency_code", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("next_number >= 1", name=op.f("ck_document_sequences_next_number_positive")),
        sa.CheckConstraint(
            "padding_width >= 0",
            name=op.f("ck_document_sequences_padding_width_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_document_sequences_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_sequences")),
        sa.UniqueConstraint(
            "company_id",
            "document_type_code",
            name=op.f("uq_document_sequences_company_id_document_type_code"),
        ),
    )
    op.create_table(
        "payment_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("days_due", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("days_due >= 0", name=op.f("ck_payment_terms_days_due_non_negative")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_payment_terms_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_terms")),
        sa.UniqueConstraint("company_id", "code", name=op.f("uq_payment_terms_company_id_code")),
        sa.UniqueConstraint("company_id", "name", name=op.f("uq_payment_terms_company_id_name")),
    )
    op.create_table(
        "tax_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("tax_type_code", sa.String(length=50), nullable=False),
        sa.Column("calculation_method_code", sa.String(length=50), nullable=False),
        sa.Column("rate_percent", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("is_recoverable", sa.Boolean(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_tax_codes_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_codes")),
        sa.UniqueConstraint(
            "company_id",
            "code",
            "effective_from",
            name=op.f("uq_tax_codes_company_id_code_effective_from"),
        ),
    )


def downgrade() -> None:
    op.drop_table("tax_codes")
    op.drop_table("payment_terms")
    op.drop_table("document_sequences")
    op.drop_table("account_types")
    op.drop_table("account_classes")
