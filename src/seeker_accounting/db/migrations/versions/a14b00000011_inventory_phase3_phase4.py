"""Inventory upgrade plan — Phase 3 / Phase 4 operational and traceability schema.

Revision ID: a14b00000011
Revises: a14b00000010
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a14b00000011"
down_revision = "a14b00000010"
branch_labels = None
depends_on = None


def _ts_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


def upgrade() -> None:
    with op.batch_alter_table("company_preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "enforce_inventory_segregation_of_duties",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("parent_item_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("tracking_mode_code", sa.String(20), nullable=False, server_default="none"))
        batch_op.add_column(sa.Column("is_variant", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("attribute_values_json", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_items_parent_item_id_items", "items", ["parent_item_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_index("ix_items_parent_item_id", ["parent_item_id"])
        batch_op.create_index("ix_items_company_tracking_mode", ["company_id", "tracking_mode_code"])

    op.create_table(
        "item_batches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("batch_number", sa.String(80), nullable=False),
        sa.Column("manufactured_on", sa.Date(), nullable=True),
        sa.Column("expiry_on", sa.Date(), nullable=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "item_id", "batch_number", name="uq_item_batches_company_item_batch"),
    )
    op.create_index("ix_item_batches_company_item", "item_batches", ["company_id", "item_id"])
    op.create_index("ix_item_batches_expiry_on", "item_batches", ["expiry_on"])
    op.create_index("ix_item_batches_status_code", "item_batches", ["status_code"])

    op.create_table(
        "item_serials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("item_batches.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=False),
        sa.Column("status_code", sa.String(30), nullable=False, server_default="allocated"),
        sa.Column("current_location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("current_doc_line_id", sa.Integer(), sa.ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("warranty_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "item_id", "serial_number", name="uq_item_serials_company_item_serial"),
    )
    op.create_index("ix_item_serials_company_item", "item_serials", ["company_id", "item_id"])
    op.create_index("ix_item_serials_status_code", "item_serials", ["status_code"])
    op.create_index("ix_item_serials_current_location_id", "item_serials", ["current_location_id"])

    op.create_table(
        "item_attribute_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_category_id", sa.Integer(), sa.ForeignKey("item_categories.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("attribute_code", sa.String(40), nullable=False),
        sa.Column("attribute_name", sa.String(120), nullable=False),
        sa.Column("allowed_values_json", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "item_category_id", "attribute_code", name="uq_item_attr_defs_company_category_code"),
    )
    op.create_index("ix_item_attr_defs_company_category", "item_attribute_definitions", ["company_id", "item_category_id"])

    op.create_table(
        "item_variants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("parent_item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("child_item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attribute_value_combination_hash", sa.String(64), nullable=False),
        sa.Column("attribute_values_json", sa.Text(), nullable=False),
        sa.Column("variant_sku_suffix", sa.String(80), nullable=True),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="active"),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "parent_item_id", "attribute_value_combination_hash", name="uq_item_variants_company_parent_hash"),
        sa.UniqueConstraint("company_id", "child_item_id", name="uq_item_variants_company_child"),
    )
    op.create_index("ix_item_variants_parent_item_id", "item_variants", ["parent_item_id"])

    op.create_table(
        "bills_of_material",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("status_code", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("type_code", sa.String(20), nullable=False, server_default="assembly"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("overhead_per_unit", sa.Numeric(18, 4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        *_ts_columns(),
        sa.UniqueConstraint("company_id", "item_id", "version", name="uq_bom_company_item_version"),
    )
    op.create_index("ix_bom_company_item_status", "bills_of_material", ["company_id", "item_id", "status_code"])

    op.create_table(
        "bom_components",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bom_id", sa.Integer(), sa.ForeignKey("bills_of_material.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("component_item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity_per", sa.Numeric(18, 6), nullable=False),
        sa.Column("scrap_percent", sa.Numeric(9, 4), nullable=False, server_default="0"),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("bom_id", "sequence", name="uq_bom_components_bom_sequence"),
    )
    op.create_index("ix_bom_components_bom_id", "bom_components", ["bom_id"])
    op.create_index("ix_bom_components_component_item_id", "bom_components", ["component_item_id"])

    op.create_table(
        "stock_count_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plan_number", sa.String(40), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(30), nullable=False, server_default="planning"),
        sa.Column("cycle_class_code", sa.String(20), nullable=True),
        sa.Column("item_filter_json", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        *_ts_columns(),
    )
    op.create_index("ix_stock_count_plans_company_status", "stock_count_plans", ["company_id", "status_code"])
    op.create_index("ix_stock_count_plans_plan_date", "stock_count_plans", ["plan_date"])

    op.create_table(
        "stock_count_plan_locations",
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("stock_count_plans.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.create_index("ix_stock_count_plan_locations_location_id", "stock_count_plan_locations", ["location_id"])

    op.create_table(
        "stock_count_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("stock_count_plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("session_number", sa.String(40), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(30), nullable=False, server_default="planning"),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.Column("frozen_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("posted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_ts_columns(),
    )
    op.create_index("ix_stock_count_sessions_company_status", "stock_count_sessions", ["company_id", "status_code"])
    op.create_index("ix_stock_count_sessions_plan_id", "stock_count_sessions", ["plan_id"])

    op.create_table(
        "stock_count_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("stock_count_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("snapshot_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("snapshot_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("counted_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("variance_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("variance_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("variance_reason_code_id", sa.Integer(), sa.ForeignKey("inventory_reason_codes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("counted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("counted_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("session_id", "item_id", "location_id", name="uq_stock_count_lines_session_item_location"),
    )
    op.create_index("ix_stock_count_lines_session_id", "stock_count_lines", ["session_id"])
    op.create_index("ix_stock_count_lines_item_location", "stock_count_lines", ["item_id", "location_id"])

    op.create_table(
        "stock_count_recounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("stock_count_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recount_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("recounted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("recounted_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_stock_count_recounts_line_id", "stock_count_recounts", ["line_id"])

    op.create_table(
        "stock_count_variances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("stock_count_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("stock_count_lines.id", ondelete="CASCADE"), nullable=True),
        sa.Column("decision_code", sa.String(30), nullable=False),
        sa.Column("reason_code_id", sa.Integer(), sa.ForeignKey("inventory_reason_codes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_stock_count_variances_session_id", "stock_count_variances", ["session_id"])
    op.create_index("ix_stock_count_variances_line_id", "stock_count_variances", ["line_id"])

    op.create_table(
        "inventory_import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_code", sa.String(40), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("status_code", sa.String(30), nullable=False, server_default="previewed"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("applied_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("preview_json", sa.Text(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        *_ts_columns(),
    )
    op.create_index("ix_inventory_import_jobs_company_status", "inventory_import_jobs", ["company_id", "status_code"])
    op.create_index("ix_inventory_import_jobs_template_code", "inventory_import_jobs", ["template_code"])

    op.create_table(
        "inventory_import_job_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("inventory_import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.String(30), nullable=False),
        sa.Column("normalized_json", sa.Text(), nullable=True),
        sa.Column("error_messages_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_inventory_import_job_rows_job_id", "inventory_import_job_rows", ["job_id"])
    op.create_index("ix_inventory_import_job_rows_status_code", "inventory_import_job_rows", ["status_code"])

    op.create_table(
        "production_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("order_number", sa.String(40), nullable=False),
        sa.Column("bom_id", sa.Integer(), sa.ForeignKey("bills_of_material.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("finished_item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("quantity_to_produce", sa.Numeric(18, 4), nullable=False),
        sa.Column("status_code", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("component_issue_document_id", sa.Integer(), sa.ForeignKey("inventory_documents.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("finished_receipt_document_id", sa.Integer(), sa.ForeignKey("inventory_documents.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_ts_columns(),
    )
    op.create_index("ix_production_orders_company_status", "production_orders", ["company_id", "status_code"])
    op.create_index("ix_production_orders_bom_id", "production_orders", ["bom_id"])

    op.create_table(
        "inventory_document_line_serials",
        sa.Column("inventory_document_line_id", sa.Integer(), sa.ForeignKey("inventory_document_lines.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("serial_id", sa.Integer(), sa.ForeignKey("item_serials.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("role_code", sa.String(20), nullable=False, server_default="movement"),
        sa.Column("linked_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_inv_doc_line_serials_doc_line_id", "inventory_document_line_serials", ["inventory_document_line_id"])
    op.create_index("ix_inv_doc_line_serials_serial_id", "inventory_document_line_serials", ["serial_id"])

    with op.batch_alter_table("inventory_document_lines") as batch_op:
        batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_inventory_document_lines_batch_id", "item_batches", ["batch_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_index("ix_inventory_document_lines_batch_id", ["batch_id"])

    with op.batch_alter_table("stock_ledger_entries") as batch_op:
        batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_stock_ledger_entries_batch_id", "item_batches", ["batch_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_index("ix_stock_ledger_entries_batch_id", ["batch_id"])

    with op.batch_alter_table("inventory_cost_layers") as batch_op:
        batch_op.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_inventory_cost_layers_batch_id", "item_batches", ["batch_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_index("ix_inventory_cost_layers_batch_id", ["batch_id"])
        batch_op.create_index(
            "ix_inventory_cost_layers_company_item_location_batch",
            ["company_id", "item_id", "location_id", "batch_id"],
        )

    with op.batch_alter_table("inventory_documents") as batch_op:
        columns = (
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("submitted_by_user_id", sa.Integer(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(), nullable=True),
            sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
            sa.Column("cancellation_reason_code_id", sa.Integer(), nullable=True),
            sa.Column("reversal_of_document_id", sa.Integer(), nullable=True),
            sa.Column("reversal_document_id", sa.Integer(), nullable=True),
            sa.Column("reverse_reason_code_id", sa.Integer(), nullable=True),
            sa.Column("reversed_at", sa.DateTime(), nullable=True),
            sa.Column("reversed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("reversing_journal_entry_id", sa.Integer(), nullable=True),
            sa.Column("stock_count_session_id", sa.Integer(), nullable=True),
            sa.Column("bom_id", sa.Integer(), nullable=True),
            sa.Column("production_order_id", sa.Integer(), nullable=True),
        )
        for column in columns:
            batch_op.add_column(column)
        fks = (
            ("fk_inv_docs_submitted_by_user_id", "users", ["submitted_by_user_id"]),
            ("fk_inv_docs_approved_by_user_id", "users", ["approved_by_user_id"]),
            ("fk_inv_docs_cancelled_by_user_id", "users", ["cancelled_by_user_id"]),
            ("fk_inv_docs_cancellation_reason_code_id", "inventory_reason_codes", ["cancellation_reason_code_id"]),
            ("fk_inv_docs_reversal_of_document_id", "inventory_documents", ["reversal_of_document_id"]),
            ("fk_inv_docs_reversal_document_id", "inventory_documents", ["reversal_document_id"]),
            ("fk_inv_docs_reverse_reason_code_id", "inventory_reason_codes", ["reverse_reason_code_id"]),
            ("fk_inv_docs_reversed_by_user_id", "users", ["reversed_by_user_id"]),
            ("fk_inv_docs_reversing_journal_entry_id", "journal_entries", ["reversing_journal_entry_id"]),
            ("fk_inv_docs_stock_count_session_id", "stock_count_sessions", ["stock_count_session_id"]),
            ("fk_inv_docs_bom_id", "bills_of_material", ["bom_id"]),
            ("fk_inv_docs_production_order_id", "production_orders", ["production_order_id"]),
        )
        for name, table, local_cols in fks:
            batch_op.create_foreign_key(name, table, local_cols, ["id"], ondelete="RESTRICT")
        for name, columns in (
            ("ix_inv_docs_submitted_by_user_id", ["submitted_by_user_id"]),
            ("ix_inv_docs_reversal_of_document_id", ["reversal_of_document_id"]),
            ("ix_inv_docs_reversal_document_id", ["reversal_document_id"]),
            ("ix_inv_docs_stock_count_session_id", ["stock_count_session_id"]),
            ("ix_inv_docs_bom_id", ["bom_id"]),
            ("ix_inv_docs_production_order_id", ["production_order_id"]),
        ):
            batch_op.create_index(name, columns)


def downgrade() -> None:
    with op.batch_alter_table("inventory_documents") as batch_op:
        for index_name in (
            "ix_inv_docs_production_order_id",
            "ix_inv_docs_bom_id",
            "ix_inv_docs_stock_count_session_id",
            "ix_inv_docs_reversal_document_id",
            "ix_inv_docs_reversal_of_document_id",
            "ix_inv_docs_submitted_by_user_id",
        ):
            batch_op.drop_index(index_name)
        for fk_name in (
            "fk_inv_docs_production_order_id",
            "fk_inv_docs_bom_id",
            "fk_inv_docs_stock_count_session_id",
            "fk_inv_docs_reversing_journal_entry_id",
            "fk_inv_docs_reversed_by_user_id",
            "fk_inv_docs_reverse_reason_code_id",
            "fk_inv_docs_reversal_document_id",
            "fk_inv_docs_reversal_of_document_id",
            "fk_inv_docs_cancellation_reason_code_id",
            "fk_inv_docs_cancelled_by_user_id",
            "fk_inv_docs_approved_by_user_id",
            "fk_inv_docs_submitted_by_user_id",
        ):
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        for column_name in (
            "production_order_id",
            "bom_id",
            "stock_count_session_id",
            "reversing_journal_entry_id",
            "reversed_by_user_id",
            "reversed_at",
            "reverse_reason_code_id",
            "reversal_document_id",
            "reversal_of_document_id",
            "cancellation_reason_code_id",
            "cancelled_by_user_id",
            "cancelled_at",
            "approved_by_user_id",
            "approved_at",
            "submitted_by_user_id",
            "submitted_at",
        ):
            batch_op.drop_column(column_name)

    with op.batch_alter_table("inventory_cost_layers") as batch_op:
        batch_op.drop_index("ix_inventory_cost_layers_company_item_location_batch")
        batch_op.drop_index("ix_inventory_cost_layers_batch_id")
        batch_op.drop_constraint("fk_inventory_cost_layers_batch_id", type_="foreignkey")
        batch_op.drop_column("batch_id")

    with op.batch_alter_table("stock_ledger_entries") as batch_op:
        batch_op.drop_index("ix_stock_ledger_entries_batch_id")
        batch_op.drop_constraint("fk_stock_ledger_entries_batch_id", type_="foreignkey")
        batch_op.drop_column("batch_id")

    with op.batch_alter_table("inventory_document_lines") as batch_op:
        batch_op.drop_index("ix_inventory_document_lines_batch_id")
        batch_op.drop_constraint("fk_inventory_document_lines_batch_id", type_="foreignkey")
        batch_op.drop_column("batch_id")

    op.drop_index("ix_inv_doc_line_serials_serial_id", table_name="inventory_document_line_serials")
    op.drop_index("ix_inv_doc_line_serials_doc_line_id", table_name="inventory_document_line_serials")
    op.drop_table("inventory_document_line_serials")
    op.drop_index("ix_production_orders_bom_id", table_name="production_orders")
    op.drop_index("ix_production_orders_company_status", table_name="production_orders")
    op.drop_table("production_orders")
    op.drop_index("ix_inventory_import_job_rows_status_code", table_name="inventory_import_job_rows")
    op.drop_index("ix_inventory_import_job_rows_job_id", table_name="inventory_import_job_rows")
    op.drop_table("inventory_import_job_rows")
    op.drop_index("ix_inventory_import_jobs_template_code", table_name="inventory_import_jobs")
    op.drop_index("ix_inventory_import_jobs_company_status", table_name="inventory_import_jobs")
    op.drop_table("inventory_import_jobs")
    op.drop_index("ix_stock_count_variances_line_id", table_name="stock_count_variances")
    op.drop_index("ix_stock_count_variances_session_id", table_name="stock_count_variances")
    op.drop_table("stock_count_variances")
    op.drop_index("ix_stock_count_recounts_line_id", table_name="stock_count_recounts")
    op.drop_table("stock_count_recounts")
    op.drop_index("ix_stock_count_lines_item_location", table_name="stock_count_lines")
    op.drop_index("ix_stock_count_lines_session_id", table_name="stock_count_lines")
    op.drop_table("stock_count_lines")
    op.drop_index("ix_stock_count_sessions_plan_id", table_name="stock_count_sessions")
    op.drop_index("ix_stock_count_sessions_company_status", table_name="stock_count_sessions")
    op.drop_table("stock_count_sessions")
    op.drop_index("ix_stock_count_plan_locations_location_id", table_name="stock_count_plan_locations")
    op.drop_table("stock_count_plan_locations")
    op.drop_index("ix_stock_count_plans_plan_date", table_name="stock_count_plans")
    op.drop_index("ix_stock_count_plans_company_status", table_name="stock_count_plans")
    op.drop_table("stock_count_plans")
    op.drop_index("ix_bom_components_component_item_id", table_name="bom_components")
    op.drop_index("ix_bom_components_bom_id", table_name="bom_components")
    op.drop_table("bom_components")
    op.drop_index("ix_bom_company_item_status", table_name="bills_of_material")
    op.drop_table("bills_of_material")
    op.drop_index("ix_item_variants_parent_item_id", table_name="item_variants")
    op.drop_table("item_variants")
    op.drop_index("ix_item_attr_defs_company_category", table_name="item_attribute_definitions")
    op.drop_table("item_attribute_definitions")
    op.drop_index("ix_item_serials_current_location_id", table_name="item_serials")
    op.drop_index("ix_item_serials_status_code", table_name="item_serials")
    op.drop_index("ix_item_serials_company_item", table_name="item_serials")
    op.drop_table("item_serials")
    op.drop_index("ix_item_batches_status_code", table_name="item_batches")
    op.drop_index("ix_item_batches_expiry_on", table_name="item_batches")
    op.drop_index("ix_item_batches_company_item", table_name="item_batches")
    op.drop_table("item_batches")

    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_index("ix_items_company_tracking_mode")
        batch_op.drop_index("ix_items_parent_item_id")
        batch_op.drop_constraint("fk_items_parent_item_id_items", type_="foreignkey")
        batch_op.drop_column("attribute_values_json")
        batch_op.drop_column("is_variant")
        batch_op.drop_column("tracking_mode_code")
        batch_op.drop_column("parent_item_id")

    with op.batch_alter_table("company_preferences") as batch_op:
        batch_op.drop_column("enforce_inventory_segregation_of_duties")
