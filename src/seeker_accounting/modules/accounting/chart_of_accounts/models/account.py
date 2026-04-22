from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class Account(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "account_code"),
        Index("ix_accounts_company_id", "company_id"),
        Index("ix_accounts_parent_account_id", "parent_account_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_class_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("account_classes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("account_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    normal_balance: Mapped[str] = mapped_column(String(10), nullable=False)
    allow_manual_posting: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_control_account: Mapped[bool] = mapped_column(nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    account_class: Mapped["AccountClass"] = relationship("AccountClass")
    account_type: Mapped["AccountType"] = relationship("AccountType")
    parent_account: Mapped["Account | None"] = relationship(
        "Account",
        back_populates="child_accounts",
        remote_side="Account.id",
    )
    child_accounts: Mapped[list["Account"]] = relationship(
        "Account",
        back_populates="parent_account",
    )

