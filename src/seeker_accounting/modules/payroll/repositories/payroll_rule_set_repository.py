from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet


class PayrollRuleSetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        active_only: bool = False,
        rule_type_code: str | None = None,
    ) -> list[PayrollRuleSet]:
        stmt = (
            select(PayrollRuleSet)
            .where(PayrollRuleSet.company_id == company_id)
            .options(selectinload(PayrollRuleSet.brackets))
            .order_by(PayrollRuleSet.rule_code, PayrollRuleSet.effective_from)
        )
        if active_only:
            stmt = stmt.where(PayrollRuleSet.is_active == True)  # noqa: E712
        if rule_type_code is not None:
            stmt = stmt.where(PayrollRuleSet.rule_type_code == rule_type_code)
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, rule_set_id: int) -> PayrollRuleSet | None:
        stmt = (
            select(PayrollRuleSet)
            .where(PayrollRuleSet.id == rule_set_id)
            .where(PayrollRuleSet.company_id == company_id)
            .options(selectinload(PayrollRuleSet.brackets))
        )
        return self._session.scalar(stmt)

    def get_by_code_and_date(
        self, company_id: int, rule_code: str, effective_from: date
    ) -> PayrollRuleSet | None:
        stmt = (
            select(PayrollRuleSet)
            .where(PayrollRuleSet.company_id == company_id)
            .where(PayrollRuleSet.rule_code == rule_code)
            .where(PayrollRuleSet.effective_from == effective_from)
        )
        return self._session.scalar(stmt)

    def save(self, rule_set: PayrollRuleSet) -> PayrollRuleSet:
        self._session.add(rule_set)
        return rule_set

    # -- Brackets ---------------------------------------------------------

    def get_bracket(self, rule_set_id: int, line_number: int) -> PayrollRuleBracket | None:
        stmt = (
            select(PayrollRuleBracket)
            .where(PayrollRuleBracket.payroll_rule_set_id == rule_set_id)
            .where(PayrollRuleBracket.line_number == line_number)
        )
        return self._session.scalar(stmt)

    def get_bracket_by_id(self, bracket_id: int) -> PayrollRuleBracket | None:
        return self._session.get(PayrollRuleBracket, bracket_id)

    def save_bracket(self, bracket: PayrollRuleBracket) -> PayrollRuleBracket:
        self._session.add(bracket)
        return bracket

    def delete_bracket(self, bracket: PayrollRuleBracket) -> None:
        self._session.delete(bracket)
