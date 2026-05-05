"""Per-(item, location) GL account override.

Allows a single item to post to different inventory / COGS / expense / revenue
accounts depending on the warehouse the movement is for. Used by
:class:`~seeker_accounting.modules.inventory.services.item_account_resolver_service.ItemAccountResolverService`
which is the single source of truth for GL account selection on inventory,
sales-COGS, and purchase-receipt postings.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ItemAccountOverride(TimestampMixin, Base):
    """Per-(item, location) account override. ``location_id`` may be ``NULL`` for
    company-wide overrides that win over the item default but lose to a more
    specific per-location override."""

    __tablename__ = "item_account_overrides"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "item_id",
            "location_id",
            name="uq_item_account_overrides_company_item_location",
        ),
        Index(
            "ix_item_account_overrides_company_item",
            "company_id",
            "item_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True
    )
    inventory_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    cogs_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    expense_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    revenue_account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item", back_populates="account_overrides")
    location: Mapped["InventoryLocation | None"] = relationship("InventoryLocation")
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
