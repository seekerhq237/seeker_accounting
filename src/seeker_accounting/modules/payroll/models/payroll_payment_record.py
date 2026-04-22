from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollPaymentRecord(TimestampMixin, Base):
    """Internal settlement-fact record for employee net-pay disbursement.

    Multiple records per payroll_run_employee are allowed to support partial
    and instalment payments.  This table does NOT execute payment — it records
    internal tracking facts only.

    payment_method_code allowed values (service-enforced):
        manual_bank, cash, cheque, transfer_note, other

    The optional treasury_transaction_id links to an existing treasury
    transaction when the payment is also recorded in the treasury module.
    """

    __tablename__ = "payroll_payment_records"
    __table_args__ = (
        Index("ix_payroll_payment_records_run_employee_id", "run_employee_id"),
        Index("ix_payroll_payment_records_company_id_date", "company_id", "payment_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_employee_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_run_employees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payment_date: Mapped[date] = mapped_column(Date(), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    payment_method_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    treasury_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("treasury_transactions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    run_employee: Mapped["PayrollRunEmployee"] = relationship("PayrollRunEmployee")
    created_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_user_id]
    )
    updated_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[updated_by_user_id]
    )
