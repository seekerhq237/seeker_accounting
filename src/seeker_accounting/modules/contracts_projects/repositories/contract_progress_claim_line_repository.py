from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.contract_progress_claim_line import (
    ContractProgressClaimLine,
)


class ContractProgressClaimLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_claim(self, company_id: int, progress_claim_id: int) -> list[ContractProgressClaimLine]:
        statement = (
            select(ContractProgressClaimLine)
            .where(
                ContractProgressClaimLine.company_id == company_id,
                ContractProgressClaimLine.progress_claim_id == progress_claim_id,
            )
            .order_by(ContractProgressClaimLine.line_number.asc(), ContractProgressClaimLine.id.asc())
        )
        return list(self._session.scalars(statement))

    def replace_lines(
        self,
        company_id: int,
        progress_claim_id: int,
        lines: list[ContractProgressClaimLine],
    ) -> list[ContractProgressClaimLine]:
        for existing_line in self.list_by_claim(company_id, progress_claim_id):
            self._session.delete(existing_line)
        self._session.flush()
        for line in lines:
            line.company_id = company_id
            line.progress_claim_id = progress_claim_id
            self._session.add(line)
        return lines

    def add(self, line: ContractProgressClaimLine) -> ContractProgressClaimLine:
        self._session.add(line)
        return line

    def save(self, line: ContractProgressClaimLine) -> ContractProgressClaimLine:
        self._session.add(line)
        return line
