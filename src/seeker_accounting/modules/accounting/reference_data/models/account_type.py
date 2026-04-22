from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import ActiveFlagMixin, Base


class AccountType(ActiveFlagMixin, Base):
    __tablename__ = "account_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normal_balance: Mapped[str] = mapped_column(String(10), nullable=False)
    financial_statement_section_code: Mapped[str] = mapped_column(String(50), nullable=False)
