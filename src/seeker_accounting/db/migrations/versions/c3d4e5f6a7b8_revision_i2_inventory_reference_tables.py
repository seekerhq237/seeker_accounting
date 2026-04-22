"""Revision I2: Inventory reference tables — units_of_measure, item_categories, inventory_locations.

Adds normalized reference tables for UoM, item categories, and inventory locations.
Adds unit_of_measure_id and item_category_id FKs to items.
Adds location_id FK to inventory_documents.
Backfills unit_of_measure_id from existing unit_of_measure_code values per company.
Backfills location_id with a per-company DEFAULT location for existing documents.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-25
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")

    # -- units_of_measure --
    op.create_table(
        "units_of_measure",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index("ix_units_of_measure_company_id", "units_of_measure", ["company_id"])

    # -- item_categories --
    op.create_table(
        "item_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index("ix_item_categories_company_id", "item_categories", ["company_id"])

    # -- inventory_locations --
    op.create_table(
        "inventory_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code"),
    )
    op.create_index("ix_inventory_locations_company_id", "inventory_locations", ["company_id"])

    # -- Backfill: seed units_of_measure from existing item.unit_of_measure_code per company --
    conn = op.get_bind()

    distinct_uoms = conn.execute(
        sa.text(
            "SELECT DISTINCT company_id, unit_of_measure_code FROM items "
            "WHERE unit_of_measure_code IS NOT NULL"
        )
    ).fetchall()

    # Track (company_id, code) -> inserted uom_id
    uom_id_map: dict[tuple[int, str], int] = {}
    for company_id, code in distinct_uoms:
        result = conn.execute(
            sa.text(
                "INSERT INTO units_of_measure "
                "(company_id, code, name, is_active, created_at, updated_at) "
                "VALUES (:cid, :code, :name, 1, :now, :now)"
            ),
            {"cid": company_id, "code": code, "name": code, "now": now},
        )
        uom_id_map[(company_id, code)] = result.lastrowid

    # -- Add FK columns to items via batch (SQLite-compatible) --
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("unit_of_measure_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("item_category_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_items_unit_of_measure_id",
            "units_of_measure",
            ["unit_of_measure_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_items_item_category_id",
            "item_categories",
            ["item_category_id"], ["id"],
            ondelete="RESTRICT",
        )

    # Update items.unit_of_measure_id from the backfilled records
    for (company_id, code), uom_id in uom_id_map.items():
        conn.execute(
            sa.text(
                "UPDATE items SET unit_of_measure_id = :uid "
                "WHERE company_id = :cid AND unit_of_measure_code = :code"
            ),
            {"uid": uom_id, "cid": company_id, "code": code},
        )

    # -- Backfill: create DEFAULT location per company that has inventory_documents --
    companies_with_docs = conn.execute(
        sa.text("SELECT DISTINCT company_id FROM inventory_documents")
    ).fetchall()

    loc_id_map: dict[int, int] = {}
    for (company_id,) in companies_with_docs:
        existing = conn.execute(
            sa.text(
                "SELECT id FROM inventory_locations "
                "WHERE company_id = :cid AND code = 'DEFAULT'"
            ),
            {"cid": company_id},
        ).fetchone()
        if existing:
            loc_id_map[company_id] = existing[0]
        else:
            result = conn.execute(
                sa.text(
                    "INSERT INTO inventory_locations "
                    "(company_id, code, name, is_active, created_at, updated_at) "
                    "VALUES (:cid, 'DEFAULT', 'Default Location', 1, :now, :now)"
                ),
                {"cid": company_id, "now": now},
            )
            loc_id_map[company_id] = result.lastrowid

    # -- Add location_id FK to inventory_documents via batch (SQLite-compatible) --
    with op.batch_alter_table("inventory_documents") as batch_op:
        batch_op.add_column(sa.Column("location_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_inventory_documents_location_id",
            "inventory_locations",
            ["location_id"], ["id"],
            ondelete="RESTRICT",
        )

    # Update inventory_documents.location_id from the backfilled locations
    for company_id, loc_id in loc_id_map.items():
        conn.execute(
            sa.text(
                "UPDATE inventory_documents SET location_id = :lid WHERE company_id = :cid"
            ),
            {"lid": loc_id, "cid": company_id},
        )


def downgrade() -> None:
    with op.batch_alter_table("inventory_documents") as batch_op:
        batch_op.drop_constraint("fk_inventory_documents_location_id", type_="foreignkey")
        batch_op.drop_column("location_id")

    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_constraint("fk_items_item_category_id", type_="foreignkey")
        batch_op.drop_constraint("fk_items_unit_of_measure_id", type_="foreignkey")
        batch_op.drop_column("item_category_id")
        batch_op.drop_column("unit_of_measure_id")

    op.drop_index("ix_inventory_locations_company_id", table_name="inventory_locations")
    op.drop_table("inventory_locations")
    op.drop_index("ix_item_categories_company_id", table_name="item_categories")
    op.drop_table("item_categories")
    op.drop_index("ix_units_of_measure_company_id", table_name="units_of_measure")
    op.drop_table("units_of_measure")
