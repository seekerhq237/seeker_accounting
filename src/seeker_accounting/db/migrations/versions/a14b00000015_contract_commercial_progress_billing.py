"""contract commercial structure and progress billing

Revision ID: a14b00000015
Revises: a14b00000014
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a14b00000015"
down_revision = "a14b00000014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_rate", sa.Numeric(18, 2), nullable=False),
        sa.Column("line_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_code_id", sa.Integer(), sa.ForeignKey("tax_codes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("tax_treatment_code", sa.String(length=30), nullable=True),
        sa.Column("billing_basis_code", sa.String(length=30), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("project_job_id", sa.Integer(), sa.ForeignKey("project_jobs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("change_order_id", sa.Integer(), sa.ForeignKey("contract_change_orders.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("contract_id", "line_number"),
    )
    op.create_index("ix_contract_lines_company_id", "contract_lines", ["company_id"])
    op.create_index("ix_contract_lines_contract_id", "contract_lines", ["contract_id"])
    op.create_index("ix_contract_lines_change_order_id", "contract_lines", ["change_order_id"])
    op.create_index("ix_contract_lines_project_id", "contract_lines", ["project_id"])
    op.create_index("ix_contract_lines_project_job_id", "contract_lines", ["project_job_id"])

    op.create_table(
        "contract_billing_schedule_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("schedule_type_code", sa.String(length=30), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("milestone_code", sa.String(length=40), nullable=True),
        sa.Column("billing_percent", sa.Numeric(9, 4), nullable=True),
        sa.Column("scheduled_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("retention_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("advance_recovery_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("time_material_reference", sa.String(length=120), nullable=True),
        sa.Column("contract_line_id", sa.Integer(), sa.ForeignKey("contract_lines.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("project_job_id", sa.Integer(), sa.ForeignKey("project_jobs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("contract_id", "line_number"),
    )
    op.create_index("ix_contract_billing_schedule_company_id", "contract_billing_schedule_items", ["company_id"])
    op.create_index("ix_contract_billing_schedule_contract_id", "contract_billing_schedule_items", ["contract_id"])
    op.create_index("ix_contract_billing_schedule_contract_line_id", "contract_billing_schedule_items", ["contract_line_id"])
    op.create_index("ix_contract_billing_schedule_project_id", "contract_billing_schedule_items", ["project_id"])
    op.create_index("ix_contract_billing_schedule_project_job_id", "contract_billing_schedule_items", ["project_job_id"])

    op.create_table(
        "contract_progress_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("claim_number", sa.String(length=40), nullable=False),
        sa.Column("claim_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("billing_schedule_item_id", sa.Integer(), sa.ForeignKey("contract_billing_schedule_items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sales_invoice_id", sa.Integer(), sa.ForeignKey("sales_invoices.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("taxable_base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("previous_certified_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("current_claim_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("certified_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("earned_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("retention_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("retention_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("advance_recovery_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("withheld_vat_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("withholding_tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("net_receivable_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("source_reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("certified_at", sa.DateTime(), nullable=True),
        sa.Column("certified_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "claim_number"),
    )
    op.create_index("ix_contract_progress_claims_company_id", "contract_progress_claims", ["company_id"])
    op.create_index("ix_contract_progress_claims_contract_id", "contract_progress_claims", ["contract_id"])
    op.create_index("ix_contract_progress_claims_sales_invoice_id", "contract_progress_claims", ["sales_invoice_id"])

    op.create_table(
        "contract_progress_claim_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("progress_claim_id", sa.Integer(), sa.ForeignKey("contract_progress_claims.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("contract_line_id", sa.Integer(), sa.ForeignKey("contract_lines.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("billing_schedule_item_id", sa.Integer(), sa.ForeignKey("contract_billing_schedule_items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_rate", sa.Numeric(18, 2), nullable=False),
        sa.Column("claimed_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("certified_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("project_job_id", sa.Integer(), sa.ForeignKey("project_jobs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("project_cost_code_id", sa.Integer(), sa.ForeignKey("project_cost_codes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("progress_claim_id", "line_number"),
    )
    op.create_index("ix_contract_progress_claim_lines_company_id", "contract_progress_claim_lines", ["company_id"])
    op.create_index("ix_contract_progress_claim_lines_claim_id", "contract_progress_claim_lines", ["progress_claim_id"])
    op.create_index("ix_contract_progress_claim_lines_contract_line_id", "contract_progress_claim_lines", ["contract_line_id"])

    op.create_table(
        "contract_customer_advances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("advance_number", sa.String(length=40), nullable=False),
        sa.Column("advance_date", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("source_invoice_id", sa.Integer(), sa.ForeignKey("sales_invoices.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("customer_receipt_id", sa.Integer(), sa.ForeignKey("customer_receipts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("advance_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("received_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("recovery_basis_code", sa.String(length=30), nullable=True),
        sa.Column("recovery_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "advance_number"),
    )
    op.create_index("ix_contract_customer_advances_company_id", "contract_customer_advances", ["company_id"])
    op.create_index("ix_contract_customer_advances_contract_id", "contract_customer_advances", ["contract_id"])
    op.create_index("ix_contract_customer_advances_receipt_id", "contract_customer_advances", ["customer_receipt_id"])

    op.create_table(
        "contract_retention_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("progress_claim_id", sa.Integer(), sa.ForeignKey("contract_progress_claims.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sales_invoice_id", sa.Integer(), sa.ForeignKey("sales_invoices.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("customer_receipt_id", sa.Integer(), sa.ForeignKey("customer_receipts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("movement_type_code", sa.String(length=30), nullable=False),
        sa.Column("status_code", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_contract_retention_movements_company_id", "contract_retention_movements", ["company_id"])
    op.create_index("ix_contract_retention_movements_contract_id", "contract_retention_movements", ["contract_id"])
    op.create_index("ix_contract_retention_movements_claim_id", "contract_retention_movements", ["progress_claim_id"])
    op.create_index("ix_contract_retention_movements_invoice_id", "contract_retention_movements", ["sales_invoice_id"])

    op.create_table(
        "contract_receipt_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_receipt_id", sa.Integer(), sa.ForeignKey("customer_receipts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sales_invoice_id", sa.Integer(), sa.ForeignKey("sales_invoices.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("progress_claim_id", sa.Integer(), sa.ForeignKey("contract_progress_claims.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("allocation_date", sa.Date(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("net_receivable_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("withholding_vat_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("withholding_tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("retention_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("advance_recovery_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_allocated_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_contract_receipt_allocations_company_id", "contract_receipt_allocations", ["company_id"])
    op.create_index("ix_contract_receipt_allocations_contract_id", "contract_receipt_allocations", ["contract_id"])
    op.create_index("ix_contract_receipt_allocations_receipt_id", "contract_receipt_allocations", ["customer_receipt_id"])
    op.create_index("ix_contract_receipt_allocations_invoice_id", "contract_receipt_allocations", ["sales_invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_contract_receipt_allocations_invoice_id", table_name="contract_receipt_allocations")
    op.drop_index("ix_contract_receipt_allocations_receipt_id", table_name="contract_receipt_allocations")
    op.drop_index("ix_contract_receipt_allocations_contract_id", table_name="contract_receipt_allocations")
    op.drop_index("ix_contract_receipt_allocations_company_id", table_name="contract_receipt_allocations")
    op.drop_table("contract_receipt_allocations")
    op.drop_index("ix_contract_retention_movements_invoice_id", table_name="contract_retention_movements")
    op.drop_index("ix_contract_retention_movements_claim_id", table_name="contract_retention_movements")
    op.drop_index("ix_contract_retention_movements_contract_id", table_name="contract_retention_movements")
    op.drop_index("ix_contract_retention_movements_company_id", table_name="contract_retention_movements")
    op.drop_table("contract_retention_movements")
    op.drop_index("ix_contract_customer_advances_receipt_id", table_name="contract_customer_advances")
    op.drop_index("ix_contract_customer_advances_contract_id", table_name="contract_customer_advances")
    op.drop_index("ix_contract_customer_advances_company_id", table_name="contract_customer_advances")
    op.drop_table("contract_customer_advances")
    op.drop_index("ix_contract_progress_claim_lines_contract_line_id", table_name="contract_progress_claim_lines")
    op.drop_index("ix_contract_progress_claim_lines_claim_id", table_name="contract_progress_claim_lines")
    op.drop_index("ix_contract_progress_claim_lines_company_id", table_name="contract_progress_claim_lines")
    op.drop_table("contract_progress_claim_lines")
    op.drop_index("ix_contract_progress_claims_sales_invoice_id", table_name="contract_progress_claims")
    op.drop_index("ix_contract_progress_claims_contract_id", table_name="contract_progress_claims")
    op.drop_index("ix_contract_progress_claims_company_id", table_name="contract_progress_claims")
    op.drop_table("contract_progress_claims")
    op.drop_index("ix_contract_billing_schedule_project_job_id", table_name="contract_billing_schedule_items")
    op.drop_index("ix_contract_billing_schedule_project_id", table_name="contract_billing_schedule_items")
    op.drop_index("ix_contract_billing_schedule_contract_line_id", table_name="contract_billing_schedule_items")
    op.drop_index("ix_contract_billing_schedule_contract_id", table_name="contract_billing_schedule_items")
    op.drop_index("ix_contract_billing_schedule_company_id", table_name="contract_billing_schedule_items")
    op.drop_table("contract_billing_schedule_items")
    op.drop_index("ix_contract_lines_project_job_id", table_name="contract_lines")
    op.drop_index("ix_contract_lines_project_id", table_name="contract_lines")
    op.drop_index("ix_contract_lines_change_order_id", table_name="contract_lines")
    op.drop_index("ix_contract_lines_contract_id", table_name="contract_lines")
    op.drop_index("ix_contract_lines_company_id", table_name="contract_lines")
    op.drop_table("contract_lines")