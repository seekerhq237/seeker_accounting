from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class InventoryImportJob(TimestampMixin, Base):
    """Two-phase import job for inventory onboarding templates."""

    __tablename__ = "inventory_import_jobs"
    __table_args__ = (
        Index("ix_inventory_import_jobs_company_status", "company_id", "status_code"),
        Index("ix_inventory_import_jobs_template_code", "template_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    template_code: Mapped[str] = mapped_column(String(40), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_code: Mapped[str] = mapped_column(
        String(30), nullable=False, default="previewed", server_default="previewed"
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    conflict_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    applied_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    preview_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    applied_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[applied_by_user_id])
    created_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    rows: Mapped[list["InventoryImportJobRow"]] = relationship(
        "InventoryImportJobRow", back_populates="job", cascade="all, delete-orphan"
    )


class InventoryImportJobRow(Base):
    """Validated raw import row with normalized payload and conflict details."""

    __tablename__ = "inventory_import_job_rows"
    __table_args__ = (
        Index("ix_inventory_import_job_rows_job_id", "job_id"),
        Index("ix_inventory_import_job_rows_status_code", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_import_jobs.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    normalized_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_messages_json: Mapped[str | None] = mapped_column(Text(), nullable=True)

    job: Mapped["InventoryImportJob"] = relationship("InventoryImportJob", back_populates="rows")
