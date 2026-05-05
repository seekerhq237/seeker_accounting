"""Inventory upgrade plan — P2 Sales/purchase integration & COGS,
P5 OHADA/Cameroon tax & customs, P6 Planning, reporting & dashboards.

Slices implemented:
  P2/3.1 – item_id + costing columns on all sales/purchase line tables
  P2/3.3 – purchase_order_line_receipt_links, purchase_bill_line_receipt_links
  P2/3.4 – item_suppliers catalog
  P5/6.1 – is_vat_exempt_sales / is_vat_exempt_purchases on items
  P5/6.2 – landed_cost_vouchers, landed_cost_voucher_receipts;
            customs/FX columns on inventory_documents
  P5/6.3 – stock_impairment_provisions
  P6/7.1 – price_lists, price_list_lines; price_list_id on customers/groups
  P6/7.2 – item_reorder_profiles
  P6/7.5 – barcode on items; item_barcodes table

Revision ID: a14b00000018
Revises: a14b00000017
Create Date: 2026-05-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000018"
down_revision = "a14b00000017"
branch_labels = None
depends_on = None


def _ts_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


# ---------------------------------------------------------------------------
# Helper – add nullable column only when it doesn't already exist
# ---------------------------------------------------------------------------


def _add_nullable(table: str, col: sa.Column) -> None:
    with op.batch_alter_table(table) as b:
        b.add_column(col)


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # P2 / Slice 3.1 – item linkage on sales/purchase line tables
    # -----------------------------------------------------------------------

    # Columns shared by all document-line tables that carry inventory impact.
    # All nullable to allow backward-compat with legacy free-text lines.
    _item_cols: list[sa.Column] = [
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("uom_ratio_snapshot", sa.Numeric(18, 6), nullable=True),
        sa.Column("base_quantity", sa.Numeric(18, 4), nullable=True),
    ]

    # Sales-side also captures COGS cost filled by the posting service.
    _cogs_cols: list[sa.Column] = [
        sa.Column("unit_cost_at_issue", sa.Numeric(18, 6), nullable=True),
        sa.Column("cogs_amount", sa.Numeric(18, 2), nullable=True),
    ]

    for tbl in (
        "sales_invoice_lines",
        "sales_credit_note_lines",
        "sales_order_lines",
        "customer_quote_lines",
    ):
        with op.batch_alter_table(tbl) as b:
            b.add_column(sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=True))
            b.add_column(sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True))
            b.add_column(sa.Column("uom_ratio_snapshot", sa.Numeric(18, 6), nullable=True))
            b.add_column(sa.Column("base_quantity", sa.Numeric(18, 4), nullable=True))
            b.add_column(sa.Column("unit_cost_at_issue", sa.Numeric(18, 6), nullable=True))
            b.add_column(sa.Column("cogs_amount", sa.Numeric(18, 2), nullable=True))
            b.create_index(f"ix_{tbl}_item_id", ["item_id"])

    for tbl in (
        "purchase_bill_lines",
        "purchase_order_lines",
        "purchase_credit_note_lines",
    ):
        with op.batch_alter_table(tbl) as b:
            b.add_column(sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=True))
            b.add_column(sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True))
            b.add_column(sa.Column("uom_ratio_snapshot", sa.Numeric(18, 6), nullable=True))
            b.add_column(sa.Column("base_quantity", sa.Numeric(18, 4), nullable=True))
            b.create_index(f"ix_{tbl}_item_id", ["item_id"])

    # Also add purchase_order_id to inventory_documents for GRN traceability.
    with op.batch_alter_table("inventory_documents") as b:
        b.add_column(sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=True))
        b.add_column(sa.Column("customs_declaration_number", sa.String(80), nullable=True))
        b.add_column(sa.Column("bill_of_lading_number", sa.String(80), nullable=True))
        b.add_column(sa.Column("port_entry_date", sa.Date(), nullable=True))
        b.add_column(sa.Column("foreign_currency_code", sa.String(10), nullable=True))
        b.add_column(sa.Column("foreign_unit_cost", sa.Numeric(18, 6), nullable=True))
        b.add_column(sa.Column("foreign_exchange_rate", sa.Numeric(18, 8), nullable=True))

    # -----------------------------------------------------------------------
    # P2 / Slice 3.3 – GRN three-way match link tables
    # -----------------------------------------------------------------------

    op.create_table(
        "purchase_order_line_receipt_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_order_line_id", sa.Integer(), sa.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_document_line_id", sa.Integer(), sa.ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("received_qty", sa.Numeric(18, 4), nullable=False),
        *_ts_columns(),
        sa.UniqueConstraint("purchase_order_line_id", "inventory_document_line_id", name="uq_po_receipt_link"),
    )
    op.create_index("ix_po_receipt_links_company_id", "purchase_order_line_receipt_links", ["company_id"])
    op.create_index("ix_po_receipt_links_po_line_id", "purchase_order_line_receipt_links", ["purchase_order_line_id"])

    op.create_table(
        "purchase_bill_line_receipt_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_bill_line_id", sa.Integer(), sa.ForeignKey("purchase_bill_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_document_line_id", sa.Integer(), sa.ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("matched_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("matched_amount", sa.Numeric(18, 2), nullable=False),
        *_ts_columns(),
        sa.UniqueConstraint("purchase_bill_line_id", "inventory_document_line_id", name="uq_bill_receipt_link"),
    )
    op.create_index("ix_bill_receipt_links_company_id", "purchase_bill_line_receipt_links", ["company_id"])
    op.create_index("ix_bill_receipt_links_bill_line_id", "purchase_bill_line_receipt_links", ["purchase_bill_line_id"])

    # -----------------------------------------------------------------------
    # P2 / Slice 3.4 – Item-supplier catalog
    # -----------------------------------------------------------------------

    op.create_table(
        "item_suppliers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_item_code", sa.String(80), nullable=True),
        sa.Column("supplier_uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("last_unit_cost", sa.Numeric(18, 6), nullable=True),
        sa.Column("last_currency_code", sa.String(10), nullable=True),
        sa.Column("last_purchase_date", sa.Date(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("is_preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("minimum_order_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "item_id", "supplier_id", name="uq_item_suppliers"),
    )
    op.create_index("ix_item_suppliers_company_item", "item_suppliers", ["company_id", "item_id"])
    op.create_index("ix_item_suppliers_company_supplier", "item_suppliers", ["company_id", "supplier_id"])

    # -----------------------------------------------------------------------
    # P5 / Slice 6.1 – VAT-exempt flags on items
    # -----------------------------------------------------------------------

    with op.batch_alter_table("items") as b:
        b.add_column(sa.Column("is_vat_exempt_sales", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("is_vat_exempt_purchases", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("barcode", sa.String(100), nullable=True))

    # -----------------------------------------------------------------------
    # P5 / Slice 6.2 – Landed cost vouchers
    # -----------------------------------------------------------------------

    op.create_table(
        "landed_cost_vouchers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("voucher_number", sa.String(40), nullable=False),
        sa.Column("voucher_date", sa.Date(), nullable=False),
        sa.Column("declaration_number", sa.String(80), nullable=True),
        sa.Column("total_freight", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_duty", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_insurance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_other", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("allocation_basis_code", sa.String(20), nullable=False, server_default="by_value"),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("posted_journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "voucher_number", name="uq_landed_cost_vouchers"),
    )
    op.create_index("ix_landed_cost_vouchers_company", "landed_cost_vouchers", ["company_id"])
    op.create_index("ix_landed_cost_vouchers_status", "landed_cost_vouchers", ["company_id", "status_code"])

    op.create_table(
        "landed_cost_voucher_receipts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("voucher_id", sa.Integer(), sa.ForeignKey("landed_cost_vouchers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_document_id", sa.Integer(), sa.ForeignKey("inventory_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("allocation_weight", sa.Numeric(18, 6), nullable=True),
        *_ts_columns(),
        sa.UniqueConstraint("voucher_id", "inventory_document_id", name="uq_lcv_receipts"),
    )
    op.create_index("ix_lcv_receipts_voucher_id", "landed_cost_voucher_receipts", ["voucher_id"])

    # -----------------------------------------------------------------------
    # P5 / Slice 6.3 – Stock impairment provisions
    # -----------------------------------------------------------------------

    op.create_table(
        "stock_impairment_provisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("fiscal_period_id", sa.Integer(), sa.ForeignKey("fiscal_periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provision_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("expense_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provision_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        *_ts_columns(),
    )
    op.create_index("ix_stock_impairment_company_item", "stock_impairment_provisions", ["company_id", "item_id"])
    op.create_index("ix_stock_impairment_period", "stock_impairment_provisions", ["company_id", "fiscal_period_id"])

    # -----------------------------------------------------------------------
    # P6 / Slice 7.1 – Price lists
    # -----------------------------------------------------------------------

    op.create_table(
        "price_lists",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("currency_code", sa.String(10), nullable=False, server_default="XAF"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "name", name="uq_price_lists_company_name"),
    )
    op.create_index("ix_price_lists_company", "price_lists", ["company_id"])
    op.create_index("ix_price_lists_company_active", "price_lists", ["company_id", "is_active"])

    op.create_table(
        "price_list_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("price_list_id", sa.Integer(), sa.ForeignKey("price_lists.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("min_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        *_ts_columns(),
    )
    op.create_index("ix_price_list_lines_list_id", "price_list_lines", ["price_list_id"])
    op.create_index("ix_price_list_lines_item_id", "price_list_lines", ["item_id"])

    # Add price_list_id to customers and customer_groups
    with op.batch_alter_table("customers") as b:
        b.add_column(sa.Column("price_list_id", sa.Integer(), sa.ForeignKey("price_lists.id", ondelete="RESTRICT"), nullable=True))

    with op.batch_alter_table("customer_groups") as b:
        b.add_column(sa.Column("price_list_id", sa.Integer(), sa.ForeignKey("price_lists.id", ondelete="RESTRICT"), nullable=True))

    # -----------------------------------------------------------------------
    # P6 / Slice 7.2 – Item reorder profiles
    # -----------------------------------------------------------------------

    op.create_table(
        "item_reorder_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("min_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("max_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("safety_stock_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("lead_time_override_days", sa.Integer(), nullable=True),
        sa.Column("preferred_supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "item_id", "location_id", name="uq_reorder_profiles_item_location"),
    )
    op.create_index("ix_reorder_profiles_company_item", "item_reorder_profiles", ["company_id", "item_id"])

    # -----------------------------------------------------------------------
    # P6 / Slice 7.5 – Item barcodes (multi-barcode table)
    # -----------------------------------------------------------------------

    op.create_table(
        "item_barcodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("barcode", sa.String(100), nullable=False),
        sa.Column("barcode_type_code", sa.String(20), nullable=False, server_default="EAN13"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "barcode", name="uq_item_barcodes_company_barcode"),
    )
    op.create_index("ix_item_barcodes_item_id", "item_barcodes", ["item_id"])
    op.create_index("ix_item_barcodes_barcode", "item_barcodes", ["company_id", "barcode"])


def downgrade() -> None:
    # Reverse in opposite order

    # P6
    op.drop_table("item_barcodes")
    op.drop_table("item_reorder_profiles")

    with op.batch_alter_table("customer_groups") as b:
        b.drop_column("price_list_id")
    with op.batch_alter_table("customers") as b:
        b.drop_column("price_list_id")

    op.drop_table("price_list_lines")
    op.drop_table("price_lists")

    # P5
    op.drop_table("stock_impairment_provisions")
    op.drop_table("landed_cost_voucher_receipts")
    op.drop_table("landed_cost_vouchers")

    with op.batch_alter_table("items") as b:
        b.drop_column("barcode")
        b.drop_column("is_vat_exempt_purchases")
        b.drop_column("is_vat_exempt_sales")

    with op.batch_alter_table("inventory_documents") as b:
        b.drop_column("foreign_exchange_rate")
        b.drop_column("foreign_unit_cost")
        b.drop_column("foreign_currency_code")
        b.drop_column("port_entry_date")
        b.drop_column("bill_of_lading_number")
        b.drop_column("customs_declaration_number")
        b.drop_column("purchase_order_id")

    # P2
    op.drop_table("item_suppliers")
    op.drop_table("purchase_bill_line_receipt_links")
    op.drop_table("purchase_order_line_receipt_links")

    for tbl in (
        "purchase_credit_note_lines",
        "purchase_order_lines",
        "purchase_bill_lines",
    ):
        with op.batch_alter_table(tbl) as b:
            b.drop_index(f"ix_{tbl}_item_id")
            b.drop_column("base_quantity")
            b.drop_column("uom_ratio_snapshot")
            b.drop_column("uom_id")
            b.drop_column("item_id")

    for tbl in (
        "customer_quote_lines",
        "sales_order_lines",
        "sales_credit_note_lines",
        "sales_invoice_lines",
    ):
        with op.batch_alter_table(tbl) as b:
            b.drop_index(f"ix_{tbl}_item_id")
            b.drop_column("cogs_amount")
            b.drop_column("unit_cost_at_issue")
            b.drop_column("base_quantity")
            b.drop_column("uom_ratio_snapshot")
            b.drop_column("uom_id")
            b.drop_column("item_id")
