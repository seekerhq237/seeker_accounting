from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - relationship type hints only
    from seeker_accounting.modules.inventory.models.item_account_override import ItemAccountOverride
    from seeker_accounting.modules.inventory.models.item_uom_conversion import ItemUomConversion


# ---------------------------------------------------------------------------
# Lifecycle, OHADA-class, and costing taxonomy enumerations
# ---------------------------------------------------------------------------

ITEM_LIFECYCLE_STATUSES: frozenset[str] = frozenset(
    {"draft", "active", "discontinued", "obsolete"}
)
"""Allowed values for :attr:`Item.lifecycle_status_code`."""

ITEM_COSTING_METHODS: frozenset[str] = frozenset(
    {"weighted_average", "fifo", "fefo", "standard_cost"}
)
"""Allowed values for :attr:`Item.inventory_cost_method_code` (Slice 1.1)."""

ITEM_TRACKING_MODES: frozenset[str] = frozenset({"none", "batch", "serial"})
"""Allowed values for :attr:`Item.tracking_mode_code` (Phase 4 traceability)."""

OHADA_STOCK_CLASS_CODES: frozenset[str] = frozenset(
    {
        "merchandise",          # 31x
        "raw_material",         # 32x
        "other_consumable",     # 33x
        "in_process",           # 34x
        "finished_goods",       # 35x
        "byproduct",            # 36x
        "packaging",            # 37x
        "in_transit",           # 38x
    }
)
"""Allowed values for :attr:`Item.ohada_stock_class_code`. The mapping from
class code to the SYSCOHADA class-3 sub-account is owned by
``ItemAccountResolverService`` and the chart-of-accounts seed."""


class Item(TimestampMixin, Base):
    """Item master for stock, non-stock, and service items.

    Phase 0 / Slice 1.1 of the inventory upgrade plan introduces:

    * ``lifecycle_status_code`` orthogonal to the legacy ``is_active`` flag.
    * ``is_sellable``, ``is_purchasable``, ``is_stockable`` flags.
    * ``ohada_stock_class_code`` driving default GL account selection.
    * ``standard_cost`` for items costed under the ``standard_cost`` method.
    * Mandatory ``unit_of_measure_id`` (the legacy denormalised
      ``unit_of_measure_code`` column has been dropped; the same name is now a
      Python ``@property`` derived from the relationship).
    """

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("company_id", "item_code"),
        Index("ix_items_company_id", "company_id"),
        Index("ix_items_company_id_item_type_code", "company_id", "item_type_code"),
        Index("ix_items_company_id_is_active", "company_id", "is_active"),
        Index(
            "ix_items_company_id_lifecycle_status_code",
            "company_id",
            "lifecycle_status_code",
        ),
        Index("ix_items_parent_item_id", "parent_item_id"),
        Index("ix_items_company_tracking_mode", "company_id", "tracking_mode_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_code: Mapped[str] = mapped_column(String(40), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_type_code: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_of_measure_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("item_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    parent_item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    inventory_cost_method_code: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    standard_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    """Required when ``inventory_cost_method_code = 'standard_cost'``. Held to
    6 decimals so that small variances are visible in standard-vs-actual
    variance reports without rounding noise."""
    lifecycle_status_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    tracking_mode_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="none",
        server_default="none",
    )
    is_variant: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    attribute_values_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_sellable: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default=expression.true(),
    )
    is_purchasable: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default=expression.true(),
    )
    is_stockable: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default=expression.true(),
    )
    ohada_stock_class_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    inventory_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cogs_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    expense_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    revenue_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    purchase_tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sales_tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reorder_level_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # P5 / Slice 6.1 – per-item VAT-exempt overrides
    is_vat_exempt_sales: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    is_vat_exempt_purchases: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    # P6 / Slice 7.5 – primary barcode
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default=expression.true(),
    )

    company: Mapped["Company"] = relationship("Company")
    unit_of_measure: Mapped["UnitOfMeasure"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_of_measure_id]
    )
    item_category: Mapped["ItemCategory | None"] = relationship(
        "ItemCategory", foreign_keys=[item_category_id]
    )
    parent_item: Mapped["Item | None"] = relationship(
        "Item",
        remote_side=[id],
        foreign_keys=[parent_item_id],
        back_populates="variant_children",
    )
    variant_children: Mapped[list["Item"]] = relationship(
        "Item",
        foreign_keys="Item.parent_item_id",
        back_populates="parent_item",
    )
    inventory_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[inventory_account_id]
    )
    cogs_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[cogs_account_id]
    )
    expense_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[expense_account_id]
    )
    revenue_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[revenue_account_id]
    )
    uom_conversions: Mapped[list["ItemUomConversion"]] = relationship(
        "ItemUomConversion",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    account_overrides: Mapped[list["ItemAccountOverride"]] = relationship(
        "ItemAccountOverride",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    batches: Mapped[list["ItemBatch"]] = relationship("ItemBatch", back_populates="item")
    serials: Mapped[list["ItemSerial"]] = relationship("ItemSerial", back_populates="item")

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def unit_of_measure_code(self) -> str:
        """Display alias for the related UoM's code.

        Returned as a Python property so existing read paths and DTOs that
        reference ``item.unit_of_measure_code`` continue to work after the
        denormalised column was dropped in Phase 0 / Slice 1.1.
        """

        if self.unit_of_measure is not None:
            return self.unit_of_measure.code
        return ""
