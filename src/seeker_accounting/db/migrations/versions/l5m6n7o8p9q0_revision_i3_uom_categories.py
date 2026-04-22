"""Revision I3: UoM categories, conversion factors, and document line conversion fields.

Revision ID: l5m6n7o8p9q0
Revises: k4l5m6n7o8p9
Create Date: 2026-03-30

Changes:
- Create ``uom_categories`` table for grouping convertible units.
- Add ``category_id`` (FK) and ``ratio_to_base`` (Numeric) to ``units_of_measure``.
- Add ``transaction_uom_id``, ``uom_ratio_snapshot``, and ``base_quantity``
  to ``inventory_document_lines`` for transaction-level UoM conversion.
- Backfill existing inventory document lines: ``base_quantity = quantity``.
"""

from alembic import op
import sqlalchemy as sa

revision = "l5m6n7o8p9q0"
down_revision = "k4l5m6n7o8p9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- uom_categories --
    op.create_table(
        "uom_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index(
        "ix_uom_categories_company_id", "uom_categories", ["company_id"]
    )

    # -- Extend units_of_measure --
    with op.batch_alter_table("units_of_measure") as batch_op:
        batch_op.add_column(
            sa.Column(
                "category_id",
                sa.Integer(),
                sa.ForeignKey("uom_categories.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "ratio_to_base",
                sa.Numeric(18, 6),
                nullable=False,
                server_default=sa.text("1"),
            )
        )

    # -- Extend inventory_document_lines --
    with op.batch_alter_table("inventory_document_lines") as batch_op:
        batch_op.add_column(
            sa.Column(
                "transaction_uom_id",
                sa.Integer(),
                sa.ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "uom_ratio_snapshot",
                sa.Numeric(18, 6),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "base_quantity",
                sa.Numeric(18, 4),
                nullable=True,
            )
        )

    # Backfill: existing lines get base_quantity = quantity (ratio 1:1)
    op.execute(
        "UPDATE inventory_document_lines SET base_quantity = quantity WHERE base_quantity IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("inventory_document_lines") as batch_op:
        batch_op.drop_column("base_quantity")
        batch_op.drop_column("uom_ratio_snapshot")
        batch_op.drop_column("transaction_uom_id")

    with op.batch_alter_table("units_of_measure") as batch_op:
        batch_op.drop_column("ratio_to_base")
        batch_op.drop_column("category_id")

    op.drop_index("ix_uom_categories_company_id", table_name="uom_categories")
    op.drop_table("uom_categories")
