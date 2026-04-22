from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class AssetCategory(TimestampMixin, Base):
    __tablename__ = "asset_categories"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_asset_categories_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Category-level account mapping
    asset_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    accumulated_depreciation_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    depreciation_expense_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Category-level depreciation defaults
    default_useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    default_depreciation_method_code: Mapped[str] = mapped_column(String(30), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    company: Mapped["Company"] = relationship("Company")
    asset_account: Mapped["Account"] = relationship("Account", foreign_keys=[asset_account_id])
    accumulated_depreciation_account: Mapped["Account"] = relationship(
        "Account", foreign_keys=[accumulated_depreciation_account_id]
    )
    depreciation_expense_account: Mapped["Account"] = relationship(
        "Account", foreign_keys=[depreciation_expense_account_id]
    )
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="category")
