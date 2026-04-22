"""Slice 14D: IAS/IFRS income statement builder

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a
Create Date: 2026-03-28 12:00:00.000000
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b1c2d3e4f5a"
branch_labels = None
depends_on = None


PROFILE_CODE = "ias_ifrs_income_statement_v1"


def upgrade() -> None:
    op.create_table(
        "ias_income_statement_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("statement_profile_code", sa.String(length=80), nullable=False),
        sa.Column("template_code", sa.String(length=80), nullable=False),
        sa.Column("template_title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("standard_note", sa.String(length=120), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("row_height", sa.Integer(), nullable=False, server_default="28"),
        sa.Column("section_background", sa.String(length=20), nullable=False),
        sa.Column("subtotal_background", sa.String(length=20), nullable=False),
        sa.Column("statement_background", sa.String(length=20), nullable=False),
        sa.Column("amount_font_size", sa.Integer(), nullable=False, server_default="11"),
        sa.Column("label_font_size", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ias_income_statement_templates")),
        sa.UniqueConstraint(
            "statement_profile_code",
            "template_code",
            name=op.f("uq_ias_income_statement_templates_statement_profile_code_template_code"),
        ),
    )

    op.create_table(
        "ias_income_statement_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("statement_profile_code", sa.String(length=80), nullable=False),
        sa.Column("section_code", sa.String(length=80), nullable=False),
        sa.Column("section_label", sa.String(length=160), nullable=False),
        sa.Column("parent_section_code", sa.String(length=80), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("row_kind_code", sa.String(length=20), nullable=False),
        sa.Column("is_mapping_target", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["statement_profile_code", "parent_section_code"],
            ["ias_income_statement_sections.statement_profile_code", "ias_income_statement_sections.section_code"],
            name=op.f("fk_ias_income_statement_sections_parent_section_code_ias_income_statement_sections"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ias_income_statement_sections")),
        sa.UniqueConstraint(
            "statement_profile_code",
            "section_code",
            name=op.f("uq_ias_income_statement_sections_statement_profile_code_section_code"),
        ),
    )

    op.create_table(
        "ias_income_statement_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("statement_profile_code", sa.String(length=80), nullable=False),
        sa.Column("section_code", sa.String(length=80), nullable=False),
        sa.Column("subsection_code", sa.String(length=80), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("sign_behavior_code", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_ias_income_statement_mappings_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["statement_profile_code", "section_code"],
            ["ias_income_statement_sections.statement_profile_code", "ias_income_statement_sections.section_code"],
            name=op.f("fk_ias_income_statement_mappings_section_code_ias_income_statement_sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["statement_profile_code", "subsection_code"],
            ["ias_income_statement_sections.statement_profile_code", "ias_income_statement_sections.section_code"],
            name=op.f("fk_ias_income_statement_mappings_subsection_code_ias_income_statement_sections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_ias_income_statement_mappings_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_ias_income_statement_mappings_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_ias_income_statement_mappings_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ias_income_statement_mappings")),
        sa.UniqueConstraint(
            "company_id",
            "statement_profile_code",
            "account_id",
            name=op.f("uq_ias_income_statement_mappings_company_id_statement_profile_code_account_id"),
        ),
    )

    now = datetime.utcnow()

    op.bulk_insert(
        sa.table(
            "ias_income_statement_templates",
            sa.column("id", sa.Integer()),
            sa.column("statement_profile_code", sa.String()),
            sa.column("template_code", sa.String()),
            sa.column("template_title", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("standard_note", sa.String()),
            sa.column("display_order", sa.Integer()),
            sa.column("row_height", sa.Integer()),
            sa.column("section_background", sa.String()),
            sa.column("subtotal_background", sa.String()),
            sa.column("statement_background", sa.String()),
            sa.column("amount_font_size", sa.Integer()),
            sa.column("label_font_size", sa.Integer()),
            sa.column("created_at", sa.DateTime()),
            sa.column("updated_at", sa.DateTime()),
            sa.column("is_active", sa.Boolean()),
        ),
        [
            {
                "id": 1,
                "statement_profile_code": PROFILE_CODE,
                "template_code": "corporate_classic",
                "template_title": "Corporate Classic",
                "description": "Formal statutory presentation with restrained spacing and a conservative hierarchy suited to board packs and official review.",
                "standard_note": "IAS / IFRS",
                "display_order": 10,
                "row_height": 28,
                "section_background": "#F3F4F6",
                "subtotal_background": "#E5E7EB",
                "statement_background": "#FFFFFF",
                "amount_font_size": 11,
                "label_font_size": 10,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
            },
            {
                "id": 2,
                "statement_profile_code": PROFILE_CODE,
                "template_code": "board_presentation",
                "template_title": "Board Presentation",
                "description": "Clearer spacing and stronger subtotal emphasis for board and management review of profitability levels.",
                "standard_note": "IAS / IFRS",
                "display_order": 20,
                "row_height": 26,
                "section_background": "#EEF2F7",
                "subtotal_background": "#DDE5EF",
                "statement_background": "#FFFFFF",
                "amount_font_size": 11,
                "label_font_size": 10,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
            },
            {
                "id": 3,
                "statement_profile_code": PROFILE_CODE,
                "template_code": "executive_presentation",
                "template_title": "Executive Presentation",
                "description": "Premium hierarchy with refined spacing and cleaner grouping while remaining serious accounting software, not decorative BI.",
                "standard_note": "IAS / IFRS",
                "display_order": 30,
                "row_height": 32,
                "section_background": "#EAF0FF",
                "subtotal_background": "#DCE7F7",
                "statement_background": "#FCFCFD",
                "amount_font_size": 12,
                "label_font_size": 11,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
            },
        ],
    )

    op.bulk_insert(
        sa.table(
            "ias_income_statement_sections",
            sa.column("id", sa.Integer()),
            sa.column("statement_profile_code", sa.String()),
            sa.column("section_code", sa.String()),
            sa.column("section_label", sa.String()),
            sa.column("parent_section_code", sa.String()),
            sa.column("display_order", sa.Integer()),
            sa.column("row_kind_code", sa.String()),
            sa.column("is_mapping_target", sa.Boolean()),
            sa.column("created_at", sa.DateTime()),
            sa.column("updated_at", sa.DateTime()),
            sa.column("is_active", sa.Boolean()),
        ),
        [
            {"id": 1, "statement_profile_code": PROFILE_CODE, "section_code": "REV", "section_label": "Revenue", "parent_section_code": None, "display_order": 10, "row_kind_code": "section", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 2, "statement_profile_code": PROFILE_CODE, "section_code": "COS", "section_label": "Cost of Sales", "parent_section_code": None, "display_order": 20, "row_kind_code": "section", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 3, "statement_profile_code": PROFILE_CODE, "section_code": "GROSS_PROFIT", "section_label": "Gross Profit", "parent_section_code": None, "display_order": 30, "row_kind_code": "formula", "is_mapping_target": False, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 4, "statement_profile_code": PROFILE_CODE, "section_code": "OPERATING_EXPENSES", "section_label": "Operating Expenses", "parent_section_code": None, "display_order": 40, "row_kind_code": "group", "is_mapping_target": False, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 5, "statement_profile_code": PROFILE_CODE, "section_code": "OPEX_SELLING", "section_label": "Selling and Distribution Expenses", "parent_section_code": "OPERATING_EXPENSES", "display_order": 50, "row_kind_code": "subsection", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 6, "statement_profile_code": PROFILE_CODE, "section_code": "OPEX_ADMIN", "section_label": "Administrative Expenses", "parent_section_code": "OPERATING_EXPENSES", "display_order": 60, "row_kind_code": "subsection", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 7, "statement_profile_code": PROFILE_CODE, "section_code": "OPEX_OTHER", "section_label": "Other Operating Expenses", "parent_section_code": "OPERATING_EXPENSES", "display_order": 70, "row_kind_code": "subsection", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 8, "statement_profile_code": PROFILE_CODE, "section_code": "OINC_OTHER", "section_label": "Other Operating Income", "parent_section_code": "OPERATING_EXPENSES", "display_order": 80, "row_kind_code": "subsection", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 9, "statement_profile_code": PROFILE_CODE, "section_code": "OPERATING_PROFIT", "section_label": "Operating Profit", "parent_section_code": None, "display_order": 90, "row_kind_code": "formula", "is_mapping_target": False, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 10, "statement_profile_code": PROFILE_CODE, "section_code": "FIN_INCOME", "section_label": "Finance Income", "parent_section_code": None, "display_order": 100, "row_kind_code": "section", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 11, "statement_profile_code": PROFILE_CODE, "section_code": "FIN_COSTS", "section_label": "Finance Costs", "parent_section_code": None, "display_order": 110, "row_kind_code": "section", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 12, "statement_profile_code": PROFILE_CODE, "section_code": "PROFIT_BEFORE_TAX", "section_label": "Profit Before Tax", "parent_section_code": None, "display_order": 120, "row_kind_code": "formula", "is_mapping_target": False, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 13, "statement_profile_code": PROFILE_CODE, "section_code": "INCOME_TAX", "section_label": "Income Tax Expense", "parent_section_code": None, "display_order": 130, "row_kind_code": "section", "is_mapping_target": True, "created_at": now, "updated_at": now, "is_active": True},
            {"id": 14, "statement_profile_code": PROFILE_CODE, "section_code": "PROFIT_FOR_PERIOD", "section_label": "Profit for the Period", "parent_section_code": None, "display_order": 140, "row_kind_code": "formula", "is_mapping_target": False, "created_at": now, "updated_at": now, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("ias_income_statement_mappings")
    op.drop_table("ias_income_statement_sections")
    op.drop_table("ias_income_statement_templates")

