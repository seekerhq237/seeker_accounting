"""Inventory upgrade plan — Phase 1 / Slices 2.2–2.4.

Revision ID: a14b00000010
Revises: a14b00000009
Create Date: 2026-05-05

Implements Slices 2.2, 2.3, and 2.4 of ``docs/inventory_upgrade_plan.md``:

Slice 2.2 — Multi-method costing:
* Adds ``location_id`` to ``inventory_cost_layers``.

Slice 2.3 — Stock transfers:
* Adds ``from_location_id``, ``to_location_id``, and
  ``transfer_status_code`` to ``inventory_documents``.
* Creates the ``cost_layer_consumptions`` append-only audit table.

Slice 2.4 — ATP / stock reservations:
* Creates the ``stock_reservations`` table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000010"
down_revision = "a14b00000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Slice 2.2 — location_id on cost layers
    # ------------------------------------------------------------------
    with op.batch_alter_table("inventory_cost_layers") as batch_op:
        batch_op.add_column(
            sa.Column(
                "location_id",
                sa.Integer(),
                sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_inv_cost_layers_location_id", ["location_id"])

    # ------------------------------------------------------------------
    # Slice 2.3 — transfer metadata on inventory_documents
    # ------------------------------------------------------------------
    with op.batch_alter_table("inventory_documents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "from_location_id",
                sa.Integer(),
                sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "to_location_id",
                sa.Integer(),
                sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("transfer_status_code", sa.String(20), nullable=True)
        )
        batch_op.create_index("ix_inv_docs_from_location_id", ["from_location_id"])
        batch_op.create_index("ix_inv_docs_to_location_id", ["to_location_id"])

    # ------------------------------------------------------------------
    # Slice 2.3 — cost_layer_consumptions (append-only audit trail)
    # ------------------------------------------------------------------
    op.create_table(
        "cost_layer_consumptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_layer_id",
            sa.Integer(),
            sa.ForeignKey("inventory_cost_layers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "consuming_doc_line_id",
            sa.Integer(),
            sa.ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("consumed_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("consumed_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_clc_source_layer_id",
        "cost_layer_consumptions",
        ["source_layer_id"],
    )
    op.create_index(
        "ix_clc_consuming_doc_line_id",
        "cost_layer_consumptions",
        ["consuming_doc_line_id"],
    )
    op.create_index(
        "ix_clc_posting_date",
        "cost_layer_consumptions",
        ["posting_date"],
    )

    # ------------------------------------------------------------------
    # Slice 2.4 — stock_reservations
    # ------------------------------------------------------------------
    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "location_id",
            sa.Integer(),
            sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("source_module", sa.String(40), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("source_document_line_id", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_stock_res_company_item_location",
        "stock_reservations",
        ["company_id", "item_id", "location_id"],
    )
    op.create_index(
        "ix_stock_res_source",
        "stock_reservations",
        ["source_module", "source_document_id"],
    )
    op.create_index(
        "ix_stock_res_status_code",
        "stock_reservations",
        ["status_code"],
    )


def downgrade() -> None:
    # Reservations
    op.drop_index("ix_stock_res_status_code", table_name="stock_reservations")
    op.drop_index("ix_stock_res_source", table_name="stock_reservations")
    op.drop_index("ix_stock_res_company_item_location", table_name="stock_reservations")
    op.drop_table("stock_reservations")

    # Cost layer consumptions
    op.drop_index("ix_clc_posting_date", table_name="cost_layer_consumptions")
    op.drop_index("ix_clc_consuming_doc_line_id", table_name="cost_layer_consumptions")
    op.drop_index("ix_clc_source_layer_id", table_name="cost_layer_consumptions")
    op.drop_table("cost_layer_consumptions")

    # Transfer metadata from inventory_documents
    with op.batch_alter_table("inventory_documents") as batch_op:
        batch_op.drop_index("ix_inv_docs_to_location_id")
        batch_op.drop_index("ix_inv_docs_from_location_id")
        batch_op.drop_column("transfer_status_code")
        batch_op.drop_column("to_location_id")
        batch_op.drop_column("from_location_id")

    # location_id from cost layers
    with op.batch_alter_table("inventory_cost_layers") as batch_op:
        batch_op.drop_index("ix_inv_cost_layers_location_id")
        batch_op.drop_column("location_id")
