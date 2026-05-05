"""Inventory upgrade plan — Phase 0 (Slices 1.1–1.4) foundations.

Revision ID: a14b00000007
Revises: a14b00000006
Create Date: 2026-04-30

Implements Phase 0 of ``docs/inventory_upgrade_plan.md``:

* **Slice 1.1** — Item lifecycle / classifier columns
  (``standard_cost``, ``lifecycle_status_code``, ``is_sellable``,
  ``is_purchasable``, ``is_stockable``, ``ohada_stock_class_code``).
* **Slice 1.2** — Drop denormalised stored totals
  (``inventory_documents.total_value``) and the redundant
  ``items.unit_of_measure_code`` column. ``items.unit_of_measure_id`` is
  enforced ``NOT NULL`` (post-backfill).
* **Slice 1.3** — Item UoM matrix (``item_uom_conversions``) and per-item
  GL account overrides (``item_account_overrides``).
* **Slice 1.4** — Document-type taxonomy (``inventory_document_types``)
  and reason codes (``inventory_reason_codes``); new header fields
  ``reason_code_id`` / ``source_module_code`` / ``source_document_type``
  / ``source_document_id`` on ``inventory_documents``; widen
  ``document_type_code`` to 40 chars and back-fill legacy
  ``receipt`` / ``issue`` / ``adjustment`` codes onto the new catalog.

Standard catalog seed data is inserted for each existing company so that
freshly-upgraded databases are usable without a follow-up seed step.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "a14b00000007"
down_revision = "a14b00000006"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Catalog data (must mirror
# ``inventory_reference_data_service.STANDARD_DOCUMENT_TYPES`` and
# ``STANDARD_REASON_CODES``).
# ---------------------------------------------------------------------------

# (code, name, direction_sign, is_transfer, is_reversal,
#  requires_unit_cost_on_line, requires_reason_code, posts_to_inventory_account)
STANDARD_DOCUMENT_TYPES: tuple[tuple[str, str, int, bool, bool, bool, bool, bool], ...] = (
    ("goods_receipt_purchase", "Goods Receipt (Purchase)", 1, False, False, True, False, True),
    ("goods_receipt_other", "Goods Receipt (Other)", 1, False, False, True, False, True),
    ("goods_issue_sale", "Goods Issue (Sale)", -1, False, False, False, False, True),
    ("goods_issue_consumption", "Goods Issue (Consumption)", -1, False, False, False, False, True),
    ("transfer_out", "Transfer Out", -1, True, False, False, False, True),
    ("transfer_in", "Transfer In", 1, True, False, False, False, True),
    ("transfer_in_transit", "Transfer In Transit", 0, True, False, False, False, True),
    ("adjustment_increase", "Adjustment (Increase)", 1, False, False, True, True, True),
    ("adjustment_decrease", "Adjustment (Decrease)", -1, False, False, False, True, True),
    ("scrap", "Scrap", -1, False, False, False, True, True),
    ("wastage", "Wastage", -1, False, False, False, True, True),
    ("count_gain", "Count Gain", 1, False, False, True, True, True),
    ("count_loss", "Count Loss", -1, False, False, False, True, True),
    ("opening_balance", "Opening Balance", 1, False, False, True, False, True),
    ("production_receipt", "Production Receipt", 1, False, False, True, False, True),
    ("production_issue", "Production Issue", -1, False, False, False, False, True),
    ("customer_return", "Customer Return", 1, False, True, False, False, True),
    ("supplier_return", "Supplier Return", -1, False, True, False, False, True),
    ("revaluation", "Revaluation", 0, False, False, True, True, True),
    ("consignment_in", "Consignment In", 1, False, False, True, False, True),
    ("consignment_out", "Consignment Out", -1, False, False, False, False, True),
)


STANDARD_REASON_CODES: tuple[tuple[str, str], ...] = (
    ("damaged_goods", "Damaged Goods"),
    ("expiry", "Expiry"),
    ("count_variance", "Physical Count Variance"),
    ("breakage", "Breakage"),
    ("theft_loss", "Theft / Loss"),
    ("supplier_quality", "Supplier Quality Issue"),
    ("opening_balance", "Opening Balance"),
    ("scrap_disposal", "Scrap Disposal"),
    ("internal_use", "Internal Use"),
    ("revaluation", "Inventory Revaluation"),
    ("other", "Other"),
)


# Map legacy ``inventory_documents.document_type_code`` values to the new
# catalog codes. The choice is conservative: legacy ``receipt`` rows are
# treated as "other" goods receipts (purchases would have been linked via the
# AP module which already has its own posting); legacy ``issue`` rows become
# consumption issues; legacy ``adjustment`` rows become positive adjustments.
# Operators can re-classify historical rows after upgrade.
LEGACY_DOC_TYPE_MAP: dict[str, str] = {
    "receipt": "goods_receipt_other",
    "issue": "goods_issue_consumption",
    "adjustment": "adjustment_increase",
}


def upgrade() -> None:  # noqa: C901 — single linear migration script
    conn = op.get_bind()
    now = datetime.utcnow()

    # -----------------------------------------------------------------
    # 1. New reference tables
    # -----------------------------------------------------------------
    op.create_table(
        "inventory_document_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("direction_sign", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_transfer", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_reversal", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "requires_unit_cost_on_line",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "requires_reason_code",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "posts_to_inventory_account",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "company_id", "code", name="uq_inventory_document_types_company_id_code"
        ),
    )
    op.create_index(
        "ix_inventory_document_types_company_id",
        "inventory_document_types",
        ["company_id"],
    )

    op.create_table(
        "inventory_reason_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "company_id", "code", name="uq_inventory_reason_codes_company_id_code"
        ),
    )
    op.create_index(
        "ix_inventory_reason_codes_company_id",
        "inventory_reason_codes",
        ["company_id"],
    )

    op.create_table(
        "item_uom_conversions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "unit_of_measure_id",
            sa.Integer(),
            sa.ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ratio_to_base", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "rounding_rule_code", sa.String(20), nullable=False, server_default="none"
        ),
        sa.Column("min_increment", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "is_purchase_default", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_sales_default", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("is_stocking", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "item_id",
            "unit_of_measure_id",
            name="uq_item_uom_conversions_item_id_unit_of_measure_id",
        ),
    )
    op.create_index(
        "ix_item_uom_conversions_item_id", "item_uom_conversions", ["item_id"]
    )
    op.create_index(
        "ix_item_uom_conversions_unit_of_measure_id",
        "item_uom_conversions",
        ["unit_of_measure_id"],
    )

    op.create_table(
        "item_account_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "location_id",
            sa.Integer(),
            sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "inventory_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "cogs_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "expense_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "revenue_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "item_id",
            "location_id",
            name="uq_item_account_overrides_company_item_location",
        ),
    )
    op.create_index(
        "ix_item_account_overrides_company_item",
        "item_account_overrides",
        ["company_id", "item_id"],
    )

    # -----------------------------------------------------------------
    # 2. items: add Slice 1.1 lifecycle/classifier columns and ensure
    #    unit_of_measure_id is populated and NOT NULL.
    # -----------------------------------------------------------------
    with op.batch_alter_table("items") as batch:
        batch.add_column(sa.Column("standard_cost", sa.Numeric(18, 6), nullable=True))
        batch.add_column(
            sa.Column(
                "lifecycle_status_code",
                sa.String(20),
                nullable=False,
                server_default="active",
            )
        )
        batch.add_column(
            sa.Column(
                "is_sellable", sa.Boolean(), nullable=False, server_default=sa.text("1")
            )
        )
        batch.add_column(
            sa.Column(
                "is_purchasable", sa.Boolean(), nullable=False, server_default=sa.text("1")
            )
        )
        batch.add_column(
            sa.Column(
                "is_stockable", sa.Boolean(), nullable=False, server_default=sa.text("1")
            )
        )
        batch.add_column(
            sa.Column("ohada_stock_class_code", sa.String(30), nullable=True)
        )

    op.create_index(
        "ix_items_company_id_lifecycle_status_code",
        "items",
        ["company_id", "lifecycle_status_code"],
    )

    # Backfill any items whose unit_of_measure_id is still NULL from the
    # legacy ``unit_of_measure_code`` value, then enforce NOT NULL.
    null_uom_rows = conn.execute(
        sa.text(
            "SELECT id, company_id, unit_of_measure_code FROM items "
            "WHERE unit_of_measure_id IS NULL"
        )
    ).fetchall()
    for item_id, company_id, code in null_uom_rows:
        if not code:
            code = "UNIT"
        existing = conn.execute(
            sa.text(
                "SELECT id FROM units_of_measure WHERE company_id = :cid AND code = :code"
            ),
            {"cid": company_id, "code": code},
        ).fetchone()
        if existing is None:
            res = conn.execute(
                sa.text(
                    "INSERT INTO units_of_measure "
                    "(company_id, code, name, is_active, created_at, updated_at) "
                    "VALUES (:cid, :code, :code, 1, :now, :now)"
                ),
                {"cid": company_id, "code": code, "now": now},
            )
            uom_id = res.lastrowid
        else:
            uom_id = existing[0]
        conn.execute(
            sa.text("UPDATE items SET unit_of_measure_id = :uid WHERE id = :iid"),
            {"uid": uom_id, "iid": item_id},
        )

    with op.batch_alter_table("items") as batch:
        batch.alter_column("unit_of_measure_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("unit_of_measure_code")

    # -----------------------------------------------------------------
    # 3. inventory_documents: widen document_type_code, add new header
    #    fields, drop denormalised total_value, back-fill legacy codes.
    # -----------------------------------------------------------------
    with op.batch_alter_table("inventory_documents") as batch:
        batch.alter_column(
            "document_type_code",
            existing_type=sa.String(20),
            type_=sa.String(40),
            existing_nullable=False,
        )
        batch.add_column(
            sa.Column(
                "reason_code_id",
                sa.Integer(),
                sa.ForeignKey("inventory_reason_codes.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("source_module_code", sa.String(40), nullable=True))
        batch.add_column(sa.Column("source_document_type", sa.String(40), nullable=True))
        batch.add_column(sa.Column("source_document_id", sa.Integer(), nullable=True))

    op.create_index(
        "ix_inventory_documents_company_id_source",
        "inventory_documents",
        [
            "company_id",
            "source_module_code",
            "source_document_type",
            "source_document_id",
        ],
    )

    # Back-fill legacy short codes onto the new catalog before any
    # service-level validation can run.
    for legacy_code, new_code in LEGACY_DOC_TYPE_MAP.items():
        conn.execute(
            sa.text(
                "UPDATE inventory_documents SET document_type_code = :new "
                "WHERE document_type_code = :legacy"
            ),
            {"new": new_code, "legacy": legacy_code},
        )

    with op.batch_alter_table("inventory_documents") as batch:
        batch.drop_column("total_value")

    # -----------------------------------------------------------------
    # 4. Per-company seed of the standard document type and reason code
    #    catalogs.
    # -----------------------------------------------------------------
    company_rows = conn.execute(sa.text("SELECT id FROM companies")).fetchall()
    for (company_id,) in company_rows:
        for (
            code,
            name,
            direction_sign,
            is_transfer,
            is_reversal,
            requires_unit_cost,
            requires_reason,
            posts_to_inventory,
        ) in STANDARD_DOCUMENT_TYPES:
            existing = conn.execute(
                sa.text(
                    "SELECT id FROM inventory_document_types "
                    "WHERE company_id = :cid AND code = :code"
                ),
                {"cid": company_id, "code": code},
            ).fetchone()
            if existing is not None:
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO inventory_document_types ("
                    "company_id, code, name, direction_sign, is_transfer, "
                    "is_reversal, requires_unit_cost_on_line, requires_reason_code, "
                    "posts_to_inventory_account, is_active, created_at, updated_at"
                    ") VALUES ("
                    ":cid, :code, :name, :ds, :it, :ir, :ruc, :rrc, :pia, 1, :now, :now"
                    ")"
                ),
                {
                    "cid": company_id,
                    "code": code,
                    "name": name,
                    "ds": direction_sign,
                    "it": 1 if is_transfer else 0,
                    "ir": 1 if is_reversal else 0,
                    "ruc": 1 if requires_unit_cost else 0,
                    "rrc": 1 if requires_reason else 0,
                    "pia": 1 if posts_to_inventory else 0,
                    "now": now,
                },
            )

        for code, name in STANDARD_REASON_CODES:
            existing = conn.execute(
                sa.text(
                    "SELECT id FROM inventory_reason_codes "
                    "WHERE company_id = :cid AND code = :code"
                ),
                {"cid": company_id, "code": code},
            ).fetchone()
            if existing is not None:
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO inventory_reason_codes ("
                    "company_id, code, name, is_active, created_at, updated_at"
                    ") VALUES (:cid, :code, :name, 1, :now, :now)"
                ),
                {
                    "cid": company_id,
                    "code": code,
                    "name": name,
                    "now": now,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()

    # Reverse legacy code mapping for any rows we touched.
    for legacy_code, new_code in {v: k for k, v in LEGACY_DOC_TYPE_MAP.items()}.items():
        conn.execute(
            sa.text(
                "UPDATE inventory_documents SET document_type_code = :legacy "
                "WHERE document_type_code = :new"
            ),
            {"legacy": new_code, "new": legacy_code},
        )

    op.drop_index(
        "ix_inventory_documents_company_id_source", table_name="inventory_documents"
    )
    with op.batch_alter_table("inventory_documents") as batch:
        batch.add_column(
            sa.Column(
                "total_value",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0",
            )
        )
        batch.drop_column("source_document_id")
        batch.drop_column("source_document_type")
        batch.drop_column("source_module_code")
        batch.drop_column("reason_code_id")
        batch.alter_column(
            "document_type_code",
            existing_type=sa.String(40),
            type_=sa.String(20),
            existing_nullable=False,
        )

    op.drop_index("ix_items_company_id_lifecycle_status_code", table_name="items")
    with op.batch_alter_table("items") as batch:
        batch.add_column(
            sa.Column(
                "unit_of_measure_code",
                sa.String(20),
                nullable=False,
                server_default="UNIT",
            )
        )
        batch.alter_column("unit_of_measure_id", existing_type=sa.Integer(), nullable=True)
        batch.drop_column("ohada_stock_class_code")
        batch.drop_column("is_stockable")
        batch.drop_column("is_purchasable")
        batch.drop_column("is_sellable")
        batch.drop_column("lifecycle_status_code")
        batch.drop_column("standard_cost")

    op.drop_index(
        "ix_item_account_overrides_company_item", table_name="item_account_overrides"
    )
    op.drop_table("item_account_overrides")

    op.drop_index(
        "ix_item_uom_conversions_unit_of_measure_id", table_name="item_uom_conversions"
    )
    op.drop_index("ix_item_uom_conversions_item_id", table_name="item_uom_conversions")
    op.drop_table("item_uom_conversions")

    op.drop_index(
        "ix_inventory_reason_codes_company_id", table_name="inventory_reason_codes"
    )
    op.drop_table("inventory_reason_codes")

    op.drop_index(
        "ix_inventory_document_types_company_id", table_name="inventory_document_types"
    )
    op.drop_table("inventory_document_types")
