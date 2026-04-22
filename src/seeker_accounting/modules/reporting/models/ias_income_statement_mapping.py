from __future__ import annotations

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class IasIncomeStatementMapping(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "ias_income_statement_mappings"
    __table_args__ = (
        UniqueConstraint("company_id", "statement_profile_code", "account_id"),
        ForeignKeyConstraint(
            ["statement_profile_code", "section_code"],
            ["ias_income_statement_sections.statement_profile_code", "ias_income_statement_sections.section_code"],
            name="fk_ias_income_statement_mappings_section",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["statement_profile_code", "subsection_code"],
            ["ias_income_statement_sections.statement_profile_code", "ias_income_statement_sections.section_code"],
            name="fk_ias_income_statement_mappings_subsection",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    statement_profile_code: Mapped[str] = mapped_column(String(80), nullable=False)
    section_code: Mapped[str] = mapped_column(String(80), nullable=False)
    subsection_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sign_behavior_code: Mapped[str] = mapped_column(String(20), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    account: Mapped["Account"] = relationship("Account")
    created_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])
    # Section labels are resolved in the repository layer to keep this model lean.
