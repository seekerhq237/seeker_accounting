"""Inventory upgrade plan — Phase 1 / Slice 2.1: immutable stock ledger.

Revision ID: a14b00000009
Revises: a14b00000007, a14b00000008
Create Date: 2026-05-05

Implements Slice 2.1 of ``docs/inventory_upgrade_plan.md``:

* Creates ``stock_ledger_entries`` (append-only fact table) and
  ``stock_ledger_balances`` (materialized current position cache).
* Backfills both tables from already-posted ``inventory_documents`` by
  replaying every document line in chronological order, computing per
  ``(company_id, item_id, location_id)`` running quantity, value, and
  weighted-average cost.

Direction sign is derived from the document type via the same
``_DOC_TYPE_ACTION`` mapping used by ``InventoryPostingService`` (legacy
short codes ``receipt`` / ``issue`` / ``adjustment`` are also honoured for
historical rows). For ``adjustment`` types we use the sign of the line
quantity to choose direction.

The new ``stock_ledger_balances`` table uses the sentinel ``location_id =
0`` for legacy rows whose ``inventory_documents.location_id`` was NULL
(SQLite/Firebird/PostgreSQL all treat composite-PK NULLs differently; we
sidestep that with a fixed sentinel).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op


# Alembic identifiers
revision = "a14b00000009"
down_revision = ("a14b00000007", "a14b00000008")
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Direction map — keep aligned with
# ``modules/inventory/services/inventory_document_service._DOC_TYPE_ACTION``.
# ---------------------------------------------------------------------------
_DOC_TYPE_DIRECTION: dict[str, int] = {
    # receipts (+1)
    "goods_receipt_purchase": 1,
    "goods_receipt_other": 1,
    "transfer_in": 1,
    "customer_return": 1,
    "production_receipt": 1,
    "opening_balance": 1,
    "consignment_in": 1,
    "adjustment_increase": 1,
    "count_gain": 1,
    "receipt": 1,  # legacy
    # issues (-1)
    "goods_issue_sale": -1,
    "goods_issue_consumption": -1,
    "transfer_out": -1,
    "supplier_return": -1,
    "production_issue": -1,
    "consignment_out": -1,
    "adjustment_decrease": -1,
    "scrap": -1,
    "wastage": -1,
    "count_loss": -1,
    "issue": -1,  # legacy
    # ambiguous: derive from line quantity sign
    "adjustment": 0,  # legacy
    "transfer_in_transit": 0,
    "revaluation": 0,
}


_NO_LOCATION = 0  # sentinel for stock_ledger_balances rows with NULL location


def upgrade() -> None:
    op.create_table(
        "stock_ledger_entries",
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
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "location_id",
            sa.Integer(),
            sa.ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("document_type_code", sa.String(40), nullable=False),
        sa.Column(
            "inventory_document_line_id",
            sa.Integer(),
            sa.ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("direction", sa.Integer(), nullable=False),
        sa.Column("quantity_base", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("value", sa.Numeric(18, 2), nullable=False),
        sa.Column("running_quantity_after", sa.Numeric(18, 4), nullable=False),
        sa.Column("running_value_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("running_avg_cost_after", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_stock_ledger_entries_company_item_location_date_id",
        "stock_ledger_entries",
        ["company_id", "item_id", "location_id", "posting_date", "id"],
    )
    op.create_index(
        "ix_stock_ledger_entries_doc_line_id",
        "stock_ledger_entries",
        ["inventory_document_line_id"],
    )

    op.create_table(
        "stock_ledger_balances",
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("avg_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column(
            "last_movement_id",
            sa.Integer(),
            sa.ForeignKey("stock_ledger_entries.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint(
            "company_id", "item_id", "location_id", name="pk_stock_ledger_balances"
        ),
    )
    op.create_index("ix_stock_ledger_balances_company_id", "stock_ledger_balances", ["company_id"])
    op.create_index("ix_stock_ledger_balances_item_id", "stock_ledger_balances", ["item_id"])

    _backfill_stock_ledger()


def _backfill_stock_ledger() -> None:
    """Replay every posted inventory document line into the stock ledger."""

    conn = op.get_bind()
    now = datetime.utcnow()

    rows = conn.execute(
        sa.text(
            """
            SELECT
                d.id            AS document_id,
                d.company_id    AS company_id,
                d.document_date AS document_date,
                d.document_type_code AS doc_type,
                d.location_id   AS location_id,
                l.id            AS line_id,
                l.line_number   AS line_number,
                l.item_id       AS item_id,
                l.quantity      AS quantity,
                l.base_quantity AS base_quantity,
                l.unit_cost     AS unit_cost,
                l.line_amount   AS line_amount
            FROM inventory_documents d
            JOIN inventory_document_lines l
              ON l.inventory_document_id = d.id
            WHERE d.status_code = 'posted'
            ORDER BY d.document_date, d.id, l.line_number, l.id
            """
        )
    ).mappings().all()

    # Per-(company, item, location) running totals.
    running: dict[tuple[int, int, int], dict[str, Decimal | int | None]] = {}
    next_entry_id = 1

    insert_entry = sa.text(
        """
        INSERT INTO stock_ledger_entries (
            id, company_id, item_id, location_id, posting_date,
            document_type_code, inventory_document_line_id, direction,
            quantity_base, unit_cost, value,
            running_quantity_after, running_value_after, running_avg_cost_after,
            created_at
        ) VALUES (
            :id, :company_id, :item_id, :location_id, :posting_date,
            :document_type_code, :inventory_document_line_id, :direction,
            :quantity_base, :unit_cost, :value,
            :running_quantity_after, :running_value_after, :running_avg_cost_after,
            :created_at
        )
        """
    )

    for row in rows:
        company_id = int(row["company_id"])
        item_id = int(row["item_id"])
        location_id = row["location_id"]
        location_key = _NO_LOCATION if location_id is None else int(location_id)
        doc_type = (row["doc_type"] or "").strip()

        line_qty_signed = Decimal(str(row["quantity"] or 0))
        base_qty_signed = (
            Decimal(str(row["base_quantity"]))
            if row["base_quantity"] is not None
            else line_qty_signed
        )
        unit_cost_in = (
            Decimal(str(row["unit_cost"])) if row["unit_cost"] is not None else Decimal("0")
        )
        line_amount = (
            Decimal(str(row["line_amount"])) if row["line_amount"] is not None else Decimal("0")
        )

        # Resolve direction.
        direction = _DOC_TYPE_DIRECTION.get(doc_type, 0)
        if direction == 0:
            direction = 1 if base_qty_signed >= 0 else -1
        if direction not in (1, -1):
            continue  # skip unhandled / informational rows

        qty_delta = abs(base_qty_signed)
        if qty_delta <= 0:
            continue

        key = (company_id, item_id, location_key)
        state = running.get(key)
        if state is None:
            old_qty = Decimal("0")
            old_value = Decimal("0.00")
            old_avg = Decimal("0.000000")
        else:
            old_qty = state["quantity"]  # type: ignore[assignment]
            old_value = state["value"]  # type: ignore[assignment]
            old_avg = state["avg_cost"]  # type: ignore[assignment]

        if direction == 1:
            # Receipts: prefer the line_amount as the value delta because the
            # already-posted journal used it (preserves cost-layer parity).
            if line_amount > 0:
                value_delta = line_amount.quantize(Decimal("0.01"))
                effective_unit_cost = (
                    (value_delta / qty_delta).quantize(Decimal("0.000001"))
                    if qty_delta > 0
                    else unit_cost_in.quantize(Decimal("0.000001"))
                )
            else:
                effective_unit_cost = unit_cost_in.quantize(Decimal("0.000001"))
                value_delta = (qty_delta * effective_unit_cost).quantize(Decimal("0.01"))
            new_qty = (old_qty + qty_delta).quantize(Decimal("0.0001"))
            new_value = (old_value + value_delta).quantize(Decimal("0.01"))
            new_avg = (
                (new_value / new_qty).quantize(Decimal("0.000001"))
                if new_qty > 0
                else Decimal("0.000000")
            )
        else:
            # Issues consume at running avg cost.
            if qty_delta > old_qty:
                # Inconsistency in historical data — clamp to drain the
                # position rather than fail the migration.
                qty_delta = old_qty
                if qty_delta <= 0:
                    continue
            effective_unit_cost = old_avg
            value_delta = (qty_delta * effective_unit_cost).quantize(Decimal("0.01"))
            new_qty = (old_qty - qty_delta).quantize(Decimal("0.0001"))
            new_value = (old_value - value_delta).quantize(Decimal("0.01"))
            new_avg = old_avg if new_qty > 0 else Decimal("0.000000")

        conn.execute(
            insert_entry,
            {
                "id": next_entry_id,
                "company_id": company_id,
                "item_id": item_id,
                "location_id": location_id,
                "posting_date": row["document_date"],
                "document_type_code": doc_type,
                "inventory_document_line_id": int(row["line_id"]),
                "direction": direction,
                "quantity_base": str(qty_delta),
                "unit_cost": str(effective_unit_cost),
                "value": str(value_delta),
                "running_quantity_after": str(new_qty),
                "running_value_after": str(new_value),
                "running_avg_cost_after": str(new_avg),
                "created_at": now,
            },
        )

        running[key] = {
            "quantity": new_qty,
            "value": new_value,
            "avg_cost": new_avg,
            "last_id": next_entry_id,
        }
        next_entry_id += 1

    # Insert final balance rows.
    insert_balance = sa.text(
        """
        INSERT INTO stock_ledger_balances (
            company_id, item_id, location_id,
            quantity, value, avg_cost, last_movement_id, version,
            created_at, updated_at
        ) VALUES (
            :company_id, :item_id, :location_id,
            :quantity, :value, :avg_cost, :last_movement_id, :version,
            :created_at, :updated_at
        )
        """
    )
    for (company_id, item_id, location_key), state in running.items():
        conn.execute(
            insert_balance,
            {
                "company_id": company_id,
                "item_id": item_id,
                "location_id": location_key,
                "quantity": str(state["quantity"]),
                "value": str(state["value"]),
                "avg_cost": str(state["avg_cost"]),
                "last_movement_id": state["last_id"],
                "version": 1,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_stock_ledger_balances_item_id", table_name="stock_ledger_balances")
    op.drop_index("ix_stock_ledger_balances_company_id", table_name="stock_ledger_balances")
    op.drop_table("stock_ledger_balances")
    op.drop_index("ix_stock_ledger_entries_doc_line_id", table_name="stock_ledger_entries")
    op.drop_index(
        "ix_stock_ledger_entries_company_item_location_date_id",
        table_name="stock_ledger_entries",
    )
    op.drop_table("stock_ledger_entries")
