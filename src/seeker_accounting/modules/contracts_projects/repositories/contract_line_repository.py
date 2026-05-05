from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.contracts_projects.models.contract_change_order import ContractChangeOrder
from seeker_accounting.modules.contracts_projects.models.contract_line import ContractLine


class ContractLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, line_id: int) -> ContractLine | None:
        return self._session.get(ContractLine, line_id)

    def list_by_contract(self, company_id: int, contract_id: int) -> list[ContractLine]:
        statement = (
            select(ContractLine)
            .where(
                ContractLine.company_id == company_id,
                ContractLine.contract_id == contract_id,
            )
            .options(selectinload(ContractLine.change_order))
            .order_by(ContractLine.line_number.asc(), ContractLine.id.asc())
        )
        return list(self._session.scalars(statement))

    def replace_base_lines(
        self,
        company_id: int,
        contract_id: int,
        lines: list[ContractLine],
    ) -> list[ContractLine]:
        existing_statement = select(ContractLine).where(
            ContractLine.company_id == company_id,
            ContractLine.contract_id == contract_id,
            ContractLine.change_order_id.is_(None),
        )
        for existing_line in self._session.scalars(existing_statement):
            self._session.delete(existing_line)
        self._session.flush()
        for line in lines:
            line.company_id = company_id
            line.contract_id = contract_id
            line.change_order_id = None
            self._session.add(line)
        return lines

    def sum_base_line_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractLine.line_amount), 0)).where(
            ContractLine.company_id == company_id,
            ContractLine.contract_id == contract_id,
            ContractLine.change_order_id.is_(None),
            ContractLine.status_code == "active",
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def sum_approved_change_order_line_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = (
            select(func.coalesce(func.sum(ContractLine.line_amount), 0))
            .join(ContractChangeOrder, ContractChangeOrder.id == ContractLine.change_order_id)
            .where(
                ContractLine.company_id == company_id,
                ContractLine.contract_id == contract_id,
                ContractLine.status_code == "active",
                ContractChangeOrder.status_code == "approved",
            )
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def count_approved_change_order_lines(self, company_id: int, contract_id: int) -> int:
        statement = (
            select(func.count(ContractLine.id))
            .join(ContractChangeOrder, ContractChangeOrder.id == ContractLine.change_order_id)
            .where(
                ContractLine.company_id == company_id,
                ContractLine.contract_id == contract_id,
                ContractLine.status_code == "active",
                ContractChangeOrder.status_code == "approved",
            )
        )
        return int(self._session.scalar(statement) or 0)

    def add(self, line: ContractLine) -> ContractLine:
        self._session.add(line)
        return line

    def save(self, line: ContractLine) -> ContractLine:
        self._session.add(line)
        return line
