from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class TaxCodeAccountMapping(Base):
    __tablename__ = "tax_code_account_mappings"
    __table_args__ = (
        UniqueConstraint("company_id", "tax_code_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tax_code_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sales_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    purchase_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tax_liability_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tax_asset_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    company: Mapped["Company"] = relationship("Company")
    tax_code: Mapped["TaxCode"] = relationship("TaxCode")
    sales_account: Mapped["Account | None"] = relationship("Account", foreign_keys=[sales_account_id])
    purchase_account: Mapped["Account | None"] = relationship("Account", foreign_keys=[purchase_account_id])
    tax_liability_account: Mapped["Account | None"] = relationship("Account", foreign_keys=[tax_liability_account_id])
    tax_asset_account: Mapped["Account | None"] = relationship("Account", foreign_keys=[tax_asset_account_id])
