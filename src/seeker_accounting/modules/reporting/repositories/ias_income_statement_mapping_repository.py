from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.reporting.models.ias_income_statement_mapping import (
    IasIncomeStatementMapping,
)
from seeker_accounting.modules.reporting.models.ias_income_statement_section import (
    IasIncomeStatementSection,
)


@dataclass(frozen=True, slots=True)
class IasMappingRow:
    mapping_id: int
    company_id: int
    statement_profile_code: str
    section_code: str
    section_label: str | None
    section_row_kind_code: str | None
    subsection_code: str | None
    subsection_label: str | None
    account_id: int
    account_code: str | None
    account_name: str | None
    account_class_code: str | None
    account_type_code: str | None
    account_type_section_code: str | None
    normal_balance: str | None
    allow_manual_posting: bool | None
    is_control_account: bool | None
    account_is_active: bool | None
    sign_behavior_code: str
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None


class IasIncomeStatementMappingRepository:
    """Persistence and query helpers for IAS income statement mappings."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        statement_profile_code: str,
        active_only: bool = False,
    ) -> list[IasMappingRow]:
        section = aliased(IasIncomeStatementSection)
        subsection = aliased(IasIncomeStatementSection)

        statement = (
            select(
                IasIncomeStatementMapping.id.label("mapping_id"),
                IasIncomeStatementMapping.company_id,
                IasIncomeStatementMapping.statement_profile_code,
                IasIncomeStatementMapping.section_code,
                section.section_label.label("section_label"),
                section.row_kind_code.label("section_row_kind_code"),
                IasIncomeStatementMapping.subsection_code,
                subsection.section_label.label("subsection_label"),
                IasIncomeStatementMapping.account_id,
                Account.account_code,
                Account.account_name,
                AccountClass.code.label("account_class_code"),
                AccountType.code.label("account_type_code"),
                AccountType.financial_statement_section_code.label("account_type_section_code"),
                Account.normal_balance,
                Account.allow_manual_posting,
                Account.is_control_account,
                Account.is_active.label("account_is_active"),
                IasIncomeStatementMapping.sign_behavior_code,
                IasIncomeStatementMapping.display_order,
                IasIncomeStatementMapping.is_active,
                IasIncomeStatementMapping.created_at,
                IasIncomeStatementMapping.updated_at,
                IasIncomeStatementMapping.created_by_user_id,
                IasIncomeStatementMapping.updated_by_user_id,
            )
            .select_from(IasIncomeStatementMapping)
            .outerjoin(
                section,
                (section.statement_profile_code == IasIncomeStatementMapping.statement_profile_code)
                & (section.section_code == IasIncomeStatementMapping.section_code),
            )
            .outerjoin(
                subsection,
                (subsection.statement_profile_code == IasIncomeStatementMapping.statement_profile_code)
                & (subsection.section_code == IasIncomeStatementMapping.subsection_code),
            )
            .outerjoin(
                Account,
                (Account.id == IasIncomeStatementMapping.account_id)
                & (Account.company_id == IasIncomeStatementMapping.company_id),
            )
            .outerjoin(AccountClass, AccountClass.id == Account.account_class_id)
            .outerjoin(AccountType, AccountType.id == Account.account_type_id)
            .where(
                IasIncomeStatementMapping.company_id == company_id,
                IasIncomeStatementMapping.statement_profile_code == statement_profile_code,
            )
        )
        if active_only:
            statement = statement.where(IasIncomeStatementMapping.is_active.is_(True))
        statement = statement.order_by(
            IasIncomeStatementMapping.display_order.asc(),
            Account.account_code.asc().nullslast(),
            IasIncomeStatementMapping.id.asc(),
        )

        rows: list[IasMappingRow] = []
        for row in self._session.execute(statement):
            rows.append(
                IasMappingRow(
                    mapping_id=int(row.mapping_id),
                    company_id=int(row.company_id),
                    statement_profile_code=str(row.statement_profile_code),
                    section_code=str(row.section_code),
                    section_label=row.section_label,
                    section_row_kind_code=row.section_row_kind_code,
                    subsection_code=row.subsection_code,
                    subsection_label=row.subsection_label,
                    account_id=int(row.account_id),
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_class_code=row.account_class_code,
                    account_type_code=row.account_type_code,
                    account_type_section_code=row.account_type_section_code,
                    normal_balance=row.normal_balance,
                    allow_manual_posting=row.allow_manual_posting,
                    is_control_account=row.is_control_account,
                    account_is_active=row.account_is_active,
                    sign_behavior_code=str(row.sign_behavior_code),
                    display_order=int(row.display_order),
                    is_active=bool(row.is_active),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    created_by_user_id=row.created_by_user_id,
                    updated_by_user_id=row.updated_by_user_id,
                )
            )
        return rows

    def get_by_id(
        self,
        company_id: int,
        statement_profile_code: str,
        mapping_id: int,
    ) -> IasIncomeStatementMapping | None:
        statement = select(IasIncomeStatementMapping).where(
            IasIncomeStatementMapping.company_id == company_id,
            IasIncomeStatementMapping.statement_profile_code == statement_profile_code,
            IasIncomeStatementMapping.id == mapping_id,
        )
        return self._session.scalar(statement)

    def get_by_account(
        self,
        company_id: int,
        statement_profile_code: str,
        account_id: int,
    ) -> IasIncomeStatementMapping | None:
        statement = select(IasIncomeStatementMapping).where(
            IasIncomeStatementMapping.company_id == company_id,
            IasIncomeStatementMapping.statement_profile_code == statement_profile_code,
            IasIncomeStatementMapping.account_id == account_id,
        )
        return self._session.scalar(statement)

    def add(self, mapping: IasIncomeStatementMapping) -> IasIncomeStatementMapping:
        self._session.add(mapping)
        return mapping

    def save(self, mapping: IasIncomeStatementMapping) -> IasIncomeStatementMapping:
        self._session.add(mapping)
        return mapping
