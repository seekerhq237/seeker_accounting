"""Repository for ``WithholdingTaxCertificate``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.withholding_tax_certificate import (
    WithholdingTaxCertificate,
)


class WithholdingTaxCertificateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(
        self, company_id: int, certificate_id: int
    ) -> WithholdingTaxCertificate | None:
        stmt = select(WithholdingTaxCertificate).where(
            WithholdingTaxCertificate.id == certificate_id,
            WithholdingTaxCertificate.company_id == company_id,
        )
        return self._session.scalar(stmt)

    def list_by_company(
        self,
        company_id: int,
        *,
        direction: str | None = None,
        status_code: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[WithholdingTaxCertificate]:
        stmt = select(WithholdingTaxCertificate).where(
            WithholdingTaxCertificate.company_id == company_id,
        )
        if direction is not None:
            stmt = stmt.where(WithholdingTaxCertificate.direction == direction)
        if status_code is not None:
            stmt = stmt.where(WithholdingTaxCertificate.status_code == status_code)
        if date_from is not None:
            stmt = stmt.where(WithholdingTaxCertificate.certificate_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WithholdingTaxCertificate.certificate_date <= date_to)
        stmt = stmt.order_by(
            WithholdingTaxCertificate.certificate_date.desc(),
            WithholdingTaxCertificate.id.desc(),
        )
        return list(self._session.scalars(stmt))

    def find_existing_certificate_number(
        self,
        company_id: int,
        direction: str,
        certificate_number: str,
        *,
        exclude_id: int | None = None,
    ) -> WithholdingTaxCertificate | None:
        """Lookup used by the service to enforce uniqueness of
        ``certificate_number`` per company + direction (a typical
        compliance requirement so the same physical certificate is
        not registered twice).
        """
        stmt = select(WithholdingTaxCertificate).where(
            WithholdingTaxCertificate.company_id == company_id,
            WithholdingTaxCertificate.direction == direction,
            WithholdingTaxCertificate.certificate_number == certificate_number,
        )
        if exclude_id is not None:
            stmt = stmt.where(WithholdingTaxCertificate.id != exclude_id)
        return self._session.scalar(stmt)

    def add(
        self, certificate: WithholdingTaxCertificate
    ) -> WithholdingTaxCertificate:
        self._session.add(certificate)
        return certificate

    def save(
        self, certificate: WithholdingTaxCertificate
    ) -> WithholdingTaxCertificate:
        self._session.add(certificate)
        return certificate

    def aggregate_totals(
        self,
        company_id: int,
        *,
        direction: str,
        date_from: date,
        date_to: date,
        include_voided: bool = False,
    ) -> tuple[int, Decimal, Decimal]:
        """Return ``(certificate_count, total_taxable_base, total_tax_amount)``
        for the given direction and date range.

        Voided certificates are excluded by default — they are kept in
        the register for audit traceability but should not contribute to
        receivable/payable balances.
        """
        from seeker_accounting.modules.taxation.constants import WHT_STATUS_VOIDED

        stmt = select(
            func.count(WithholdingTaxCertificate.id),
            func.coalesce(func.sum(WithholdingTaxCertificate.taxable_base), 0),
            func.coalesce(func.sum(WithholdingTaxCertificate.tax_amount), 0),
        ).where(
            WithholdingTaxCertificate.company_id == company_id,
            WithholdingTaxCertificate.direction == direction,
            WithholdingTaxCertificate.certificate_date >= date_from,
            WithholdingTaxCertificate.certificate_date <= date_to,
        )
        if not include_voided:
            stmt = stmt.where(
                WithholdingTaxCertificate.status_code != WHT_STATUS_VOIDED
            )
        row = self._session.execute(stmt).one()
        count = int(row[0] or 0)
        base = Decimal(row[1] or 0)
        amount = Decimal(row[2] or 0)
        return count, base, amount
