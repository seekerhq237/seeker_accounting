from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.reporting.models.ias_income_statement_section import (
    IasIncomeStatementSection,
)
from seeker_accounting.modules.reporting.models.ias_income_statement_template import (
    IasIncomeStatementTemplate,
)


@dataclass(frozen=True, slots=True)
class IasTemplateRow:
    id: int
    statement_profile_code: str
    template_code: str
    template_title: str
    description: str
    standard_note: str
    display_order: int
    row_height: int
    section_background: str
    subtotal_background: str
    statement_background: str
    amount_font_size: int
    label_font_size: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class IasSectionRow:
    id: int
    statement_profile_code: str
    section_code: str
    section_label: str
    parent_section_code: str | None
    display_order: int
    row_kind_code: str
    is_mapping_target: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class IasCompanyAccountRow:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_class_name: str | None
    account_type_code: str | None
    account_type_name: str | None
    account_type_section_code: str | None
    account_type_normal_balance: str | None
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class IasAccountActivityRow:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_class_name: str | None
    account_type_code: str | None
    account_type_name: str | None
    account_type_section_code: str | None
    account_type_normal_balance: str | None
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    is_active: bool
    journal_line_count: int
    total_debit: Decimal
    total_credit: Decimal


class IasIncomeStatementRepository:
    """Report-shaped IAS/IFRS income statement queries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_templates(
        self,
        statement_profile_code: str,
        active_only: bool = True,
    ) -> list[IasTemplateRow]:
        statement = select(IasIncomeStatementTemplate).where(
            IasIncomeStatementTemplate.statement_profile_code == statement_profile_code,
        )
        if active_only:
            statement = statement.where(IasIncomeStatementTemplate.is_active.is_(True))
        statement = statement.order_by(
            IasIncomeStatementTemplate.display_order.asc(),
            IasIncomeStatementTemplate.template_code.asc(),
            IasIncomeStatementTemplate.id.asc(),
        )
        return [
            IasTemplateRow(
                id=row.id,
                statement_profile_code=row.statement_profile_code,
                template_code=row.template_code,
                template_title=row.template_title,
                description=row.description,
                standard_note=row.standard_note,
                display_order=row.display_order,
                row_height=row.row_height,
                section_background=row.section_background,
                subtotal_background=row.subtotal_background,
                statement_background=row.statement_background,
                amount_font_size=row.amount_font_size,
                label_font_size=row.label_font_size,
                is_active=row.is_active,
            )
            for row in self._session.scalars(statement)
        ]

    def get_template_by_code(
        self,
        statement_profile_code: str,
        template_code: str,
        active_only: bool = True,
    ) -> IasTemplateRow | None:
        statement = select(IasIncomeStatementTemplate).where(
            IasIncomeStatementTemplate.statement_profile_code == statement_profile_code,
            IasIncomeStatementTemplate.template_code == template_code,
        )
        if active_only:
            statement = statement.where(IasIncomeStatementTemplate.is_active.is_(True))
        row = self._session.scalar(statement)
        if row is None:
            return None
        return IasTemplateRow(
            id=row.id,
            statement_profile_code=row.statement_profile_code,
            template_code=row.template_code,
            template_title=row.template_title,
            description=row.description,
            standard_note=row.standard_note,
            display_order=row.display_order,
            row_height=row.row_height,
            section_background=row.section_background,
            subtotal_background=row.subtotal_background,
            statement_background=row.statement_background,
            amount_font_size=row.amount_font_size,
            label_font_size=row.label_font_size,
            is_active=row.is_active,
        )

    def list_sections(
        self,
        statement_profile_code: str,
        active_only: bool = True,
    ) -> list[IasSectionRow]:
        statement = select(IasIncomeStatementSection).where(
            IasIncomeStatementSection.statement_profile_code == statement_profile_code,
        )
        if active_only:
            statement = statement.where(IasIncomeStatementSection.is_active.is_(True))
        statement = statement.order_by(
            IasIncomeStatementSection.display_order.asc(),
            IasIncomeStatementSection.section_code.asc(),
            IasIncomeStatementSection.id.asc(),
        )
        return [
            IasSectionRow(
                id=row.id,
                statement_profile_code=row.statement_profile_code,
                section_code=row.section_code,
                section_label=row.section_label,
                parent_section_code=row.parent_section_code,
                display_order=row.display_order,
                row_kind_code=row.row_kind_code,
                is_mapping_target=row.is_mapping_target,
                is_active=row.is_active,
            )
            for row in self._session.scalars(statement)
        ]

    def get_section_by_code(
        self,
        statement_profile_code: str,
        section_code: str,
        active_only: bool = True,
    ) -> IasSectionRow | None:
        statement = select(IasIncomeStatementSection).where(
            IasIncomeStatementSection.statement_profile_code == statement_profile_code,
            IasIncomeStatementSection.section_code == section_code,
        )
        if active_only:
            statement = statement.where(IasIncomeStatementSection.is_active.is_(True))
        row = self._session.scalar(statement)
        if row is None:
            return None
        return IasSectionRow(
            id=row.id,
            statement_profile_code=row.statement_profile_code,
            section_code=row.section_code,
            section_label=row.section_label,
            parent_section_code=row.parent_section_code,
            display_order=row.display_order,
            row_kind_code=row.row_kind_code,
            is_mapping_target=row.is_mapping_target,
            is_active=row.is_active,
        )

    def list_company_accounts(self, company_id: int, active_only: bool = False) -> list[IasCompanyAccountRow]:
        statement = (
            select(
                Account.id.label("account_id"),
                Account.account_code,
                Account.account_name,
                AccountClass.code.label("account_class_code"),
                AccountClass.name.label("account_class_name"),
                AccountType.code.label("account_type_code"),
                AccountType.name.label("account_type_name"),
                AccountType.financial_statement_section_code.label("account_type_section_code"),
                AccountType.normal_balance.label("account_type_normal_balance"),
                Account.normal_balance,
                Account.allow_manual_posting,
                Account.is_control_account,
                Account.is_active,
            )
            .outerjoin(AccountClass, AccountClass.id == Account.account_class_id)
            .outerjoin(AccountType, AccountType.id == Account.account_type_id)
            .where(Account.company_id == company_id)
        )
        if active_only:
            statement = statement.where(Account.is_active.is_(True))
        statement = statement.order_by(Account.account_code.asc(), Account.id.asc())

        rows: list[IasCompanyAccountRow] = []
        for row in self._session.execute(statement):
            rows.append(
                IasCompanyAccountRow(
                    account_id=int(row.account_id),
                    account_code=str(row.account_code),
                    account_name=str(row.account_name),
                    account_class_code=row.account_class_code,
                    account_class_name=row.account_class_name,
                    account_type_code=row.account_type_code,
                    account_type_name=row.account_type_name,
                    account_type_section_code=row.account_type_section_code,
                    account_type_normal_balance=row.account_type_normal_balance,
                    normal_balance=str(row.normal_balance),
                    allow_manual_posting=bool(row.allow_manual_posting),
                    is_control_account=bool(row.is_control_account),
                    is_active=bool(row.is_active),
                )
            )
        return rows

    def list_period_activity(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[IasAccountActivityRow]:
        conditions = [
            JournalEntry.company_id == company_id,
            JournalEntry.status_code == "POSTED",
            JournalEntry.posted_at.is_not(None),
        ]
        if date_from is not None:
            conditions.append(JournalEntry.entry_date >= date_from)
        if date_to is not None:
            conditions.append(JournalEntry.entry_date <= date_to)

        statement = (
            select(
                Account.id.label("account_id"),
                Account.account_code,
                Account.account_name,
                AccountClass.code.label("account_class_code"),
                AccountClass.name.label("account_class_name"),
                AccountType.code.label("account_type_code"),
                AccountType.name.label("account_type_name"),
                AccountType.financial_statement_section_code.label("account_type_section_code"),
                AccountType.normal_balance.label("account_type_normal_balance"),
                Account.normal_balance,
                Account.allow_manual_posting,
                Account.is_control_account,
                Account.is_active,
                func.count(JournalEntryLine.id).label("journal_line_count"),
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("total_credit"),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .outerjoin(AccountClass, AccountClass.id == Account.account_class_id)
            .outerjoin(AccountType, AccountType.id == Account.account_type_id)
            .where(*conditions)
            .where(Account.company_id == company_id)
            .group_by(
                Account.id,
                Account.account_code,
                Account.account_name,
                AccountClass.code,
                AccountClass.name,
                AccountType.code,
                AccountType.name,
                AccountType.financial_statement_section_code,
                AccountType.normal_balance,
                Account.normal_balance,
                Account.allow_manual_posting,
                Account.is_control_account,
                Account.is_active,
            )
            .order_by(Account.account_code.asc(), Account.id.asc())
        )

        rows: list[IasAccountActivityRow] = []
        for row in self._session.execute(statement):
            rows.append(
                IasAccountActivityRow(
                    account_id=int(row.account_id),
                    account_code=str(row.account_code),
                    account_name=str(row.account_name),
                    account_class_code=row.account_class_code,
                    account_class_name=row.account_class_name,
                    account_type_code=row.account_type_code,
                    account_type_name=row.account_type_name,
                    account_type_section_code=row.account_type_section_code,
                    account_type_normal_balance=row.account_type_normal_balance,
                    normal_balance=str(row.normal_balance),
                    allow_manual_posting=bool(row.allow_manual_posting),
                    is_control_account=bool(row.is_control_account),
                    is_active=bool(row.is_active),
                    journal_line_count=int(row.journal_line_count or 0),
                    total_debit=self._to_decimal(row.total_debit),
                    total_credit=self._to_decimal(row.total_credit),
                )
            )
        return rows

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
