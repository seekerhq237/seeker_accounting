from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.contract import Contract


class ContractRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, contract_id: int) -> Contract | None:
        return self._session.get(Contract, contract_id)

    def get_by_company_and_id(self, company_id: int, contract_id: int) -> Contract | None:
        return self._session.scalar(
            select(Contract).where(
                Contract.company_id == company_id,
                Contract.id == contract_id,
            )
        )

    def get_by_company_and_contract_number(self, company_id: int, contract_number: str) -> Contract | None:
        return self._session.scalar(
            select(Contract).where(
                Contract.company_id == company_id,
                Contract.contract_number == contract_number,
            )
        )

    def list_by_company(self, company_id: int) -> list[Contract]:
        return list(
            self._session.scalars(
                select(Contract).where(Contract.company_id == company_id).order_by(
                    Contract.contract_number.asc()
                )
            )
        )

    def add(self, contract: Contract) -> Contract:
        self._session.add(contract)
        return contract

    def save(self, contract: Contract) -> Contract:
        self._session.add(contract)
        return contract