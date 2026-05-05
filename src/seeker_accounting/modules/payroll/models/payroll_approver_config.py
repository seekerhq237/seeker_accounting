"""PayrollApproverConfig — P7 approval-routing model.

Stores per-company approval routing rules.  Each active record names an
approver user and an optional minimum-run-amount threshold.  The routing
service selects the first active record whose threshold is met (or has
no threshold) to determine the required approver for a given run.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base


class PayrollApproverConfig(Base):
    """Per-company approval-routing rule.

    Fields
    ------
    approver_user_id
        The user who is designated as approver when the routing rule fires.
    min_run_amount
        Optional.  When set, this rule only applies when the run's total
        net payable is ≥ this amount.  Use ``None`` to apply unconditionally.
    is_active
        Soft-disable without deleting historical routing data.
    """

    __tablename__ = "payroll_approver_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approver_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    min_run_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────

    company: Mapped["Company"] = relationship(  # noqa: F821
        "Company",
        foreign_keys=[company_id],
        lazy="selectin",
    )
    approver_user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        foreign_keys=[approver_user_id],
        lazy="selectin",
    )
