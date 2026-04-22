"""Revision I: Inventory-linked accounting tables.

Creates items, inventory_documents, inventory_document_lines, and inventory_cost_layers.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- items --
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_code", sa.String(40), nullable=False),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("item_type_code", sa.String(20), nullable=False),
        sa.Column("unit_of_measure_code", sa.String(20), nullable=False, server_default="UNIT"),
        sa.Column("inventory_cost_method_code", sa.String(30), nullable=True),
        sa.Column("inventory_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("cogs_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("expense_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("revenue_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("purchase_tax_code_id", sa.Integer(), sa.ForeignKey("tax_codes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sales_tax_code_id", sa.Integer(), sa.ForeignKey("tax_codes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("reorder_level_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "item_code"),
    )
    op.create_index("ix_items_company_id", "items", ["company_id"])
    op.create_index("ix_items_company_id_item_type_code", "items", ["company_id", "item_type_code"])
    op.create_index("ix_items_company_id_is_active", "items", ["company_id", "is_active"])

    # -- inventory_documents --
    op.create_table(
        "inventory_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_number", sa.String(40), nullable=False),
        sa.Column("document_type_code", sa.String(20), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("reference_number", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("total_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("posted_journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "document_number"),
    )
    op.create_index("ix_inventory_documents_company_id", "inventory_documents", ["company_id"])
    op.create_index("ix_inventory_documents_company_id_status_code", "inventory_documents", ["company_id", "status_code"])
    op.create_index("ix_inventory_documents_company_id_document_type_code", "inventory_documents", ["company_id", "document_type_code"])

    # -- inventory_document_lines --
    op.create_table(
        "inventory_document_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inventory_document_id", sa.Integer(), sa.ForeignKey("inventory_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("line_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("counterparty_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("line_description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("inventory_document_id", "line_number"),
    )
    op.create_index("ix_inventory_document_lines_document_id", "inventory_document_lines", ["inventory_document_id"])
    op.create_index("ix_inventory_document_lines_item_id", "inventory_document_lines", ["item_id"])

    # -- inventory_cost_layers --
    op.create_table(
        "inventory_cost_layers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_document_line_id", sa.Integer(), sa.ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("layer_date", sa.Date(), nullable=False),
        sa.Column("quantity_in", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_remaining", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_inventory_cost_layers_company_id_item_id", "inventory_cost_layers", ["company_id", "item_id"])
    op.create_index("ix_inventory_cost_layers_item_id", "inventory_cost_layers", ["item_id"])
    op.create_index("ix_inventory_cost_layers_document_line_id", "inventory_cost_layers", ["inventory_document_line_id"])


def downgrade() -> None:
    op.drop_table("inventory_cost_layers")
    op.drop_table("inventory_document_lines")
    op.drop_table("inventory_documents")
    op.drop_table("items")
