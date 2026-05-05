"""Tax settlement service.

Slice T15. A *filed* VAT return only declares the obligation to the
state — the accounting facts (output VAT collected, input VAT
recovered) still sit in their original control accounts.  The
**settlement journal** transfers those facts into a single payable
balance (or a credit carry-forward).

This service owns:

* preview computation — given a filed return, project the journal
  lines without committing anything (used by the UI to show the user
  what they are about to post),
* the post operation itself — build, validate, and POST the
  settlement JE in one transaction, then stamp
  ``tax_returns.journal_entry_id`` and ``settled_at``.

Settlement is intentionally idempotent against double-posting: a
return that already carries a ``journal_entry_id`` is rejected.

The service does NOT change the return status — settlement is a
pure accounting fact, the return remains FILED.  Payments against
the resulting payable are still recorded through ``TaxPaymentService``
(which is its own slice; T16 will tighten the bank-side JE so that
payment posting and tax-payment recording cooperate).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import (
    JournalEntryLine,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_account_mapping_repository import (
    TaxCodeAccountMappingRepository,
)
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    RETURN_STATUS_FILED,
    SETTLEMENT_VAT_CREDIT_CARRYFORWARD_ACCOUNT_CODE,
    SETTLEMENT_VAT_PAYABLE_ACCOUNT_CODE,
    SETTLEMENT_WITHHOLDING_VAT_RECEIVABLE_ACCOUNT_CODE,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    SettleTaxReturnCommand,
    TaxSettlementLineDTO,
    TaxSettlementPreviewDTO,
    TaxSettlementResultDTO,
)
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    DIRECTION_SALES,
)
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineAggregate,
    PostedTaxLineRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService


_ZERO = Decimal("0.00")
_JOURNAL_DOC_TYPE = "JOURNAL_ENTRY"
_JOURNAL_TYPE_CODE_OD = "OD"  # Opérations Diverses — manual/general journal
_LINE_ROLE_OUTPUT = "OUTPUT_VAT"
_LINE_ROLE_INPUT = "INPUT_VAT"
_LINE_ROLE_PAYABLE = "VAT_PAYABLE"
_LINE_ROLE_CREDIT_CARRYFORWARD = "VAT_CREDIT_CARRYFORWARD"
_LINE_ROLE_WITHHOLDING_RECEIVABLE = "VAT_WITHHOLDING_RECEIVABLE"


TaxReturnRepositoryFactory = Callable[[Session], TaxReturnRepository]
PostedTaxLineRepositoryFactory = Callable[[Session], PostedTaxLineRepository]
TaxCodeAccountMappingRepositoryFactory = Callable[
    [Session], TaxCodeAccountMappingRepository
]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


@dataclass(frozen=True, slots=True)
class _AccountAggregate:
    """Internal: one account-keyed leg of the settlement plan."""

    account_id: int
    account_code: str
    account_name: str
    amount: Decimal


class TaxSettlementService:
    PERMISSION_SETTLE = "taxation.returns.settle"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        tax_return_repository_factory: TaxReturnRepositoryFactory,
        posted_tax_line_repository_factory: PostedTaxLineRepositoryFactory,
        tax_code_account_mapping_repository_factory: TaxCodeAccountMappingRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_return_repository_factory = tax_return_repository_factory
        self._posted_tax_line_repository_factory = posted_tax_line_repository_factory
        self._tax_code_account_mapping_repository_factory = (
            tax_code_account_mapping_repository_factory
        )
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._account_repository_factory = account_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ---------------------------------------------------------------- public

    def preview_settlement(
        self,
        company_id: int,
        return_id: int,
    ) -> TaxSettlementPreviewDTO:
        """Project the settlement JE without writing anything."""
        self._permission_service.require_permission(self.PERMISSION_SETTLE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            tax_return = self._load_filed_vat_return(uow.session, company_id, return_id)
            return self._build_preview(uow.session, company_id, tax_return)

    def settle_return(
        self,
        company_id: int,
        command: SettleTaxReturnCommand,
    ) -> TaxSettlementResultDTO:
        """Build, post, and link the settlement JE for a filed VAT return."""
        self._permission_service.require_permission(self.PERMISSION_SETTLE)
        with self._unit_of_work_factory() as uow:
            actor_id = (
                command.actor_user_id
                if command.actor_user_id is not None
                else self._app_context.current_user_id
            )
            self._require_company_exists(uow.session, company_id)
            tax_return = self._load_filed_vat_return(
                uow.session, company_id, command.return_id
            )
            preview = self._build_preview(
                uow.session,
                company_id,
                tax_return,
                requested_settlement_date=command.settlement_date,
            )
            if preview.blocking_issues:
                raise ValidationError(
                    "Settlement cannot be posted: " + "; ".join(preview.blocking_issues)
                )
            if not preview.journal_lines:
                raise ValidationError(
                    "Settlement journal would be empty for this return."
                )

            settlement_date = preview.settlement_date

            fiscal_period_repo = self._fiscal_period_repository_factory(uow.session)
            fiscal_period = fiscal_period_repo.get_covering_date(
                company_id, settlement_date
            )
            if fiscal_period is None:
                raise ValidationError(
                    "Settlement date must fall within an existing fiscal period."
                )
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError(
                    f"Settlement journal cannot be posted into locked fiscal period "
                    f"{fiscal_period.period_code}.",
                )
            if fiscal_period.status_code != "OPEN":
                raise ValidationError(
                    "Settlement journal can only be posted into an open fiscal period."
                )

            journal_repo = self._journal_entry_repository_factory(uow.session)
            description = (command.description or "").strip() or (
                f"VAT settlement {tax_return.period_start.isoformat()} – "
                f"{tax_return.period_end.isoformat()}"
            )
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=settlement_date,
                transaction_date=settlement_date,
                journal_type_code=_JOURNAL_TYPE_CODE_OD,
                reference_text=f"VAT-RET-{tax_return.id}",
                description=description,
                source_module_code="taxation",
                source_document_type="tax_return",
                source_document_id=tax_return.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_id,
                created_by_user_id=actor_id,
            )
            journal_repo.add(journal_entry)
            uow.session.flush()
            journal_entry.entry_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code=_JOURNAL_DOC_TYPE,
            )
            journal_repo.save(journal_entry)

            for line_number, line in enumerate(preview.journal_lines, start=1):
                uow.session.add(
                    JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        line_number=line_number,
                        account_id=line.account_id,
                        line_description=line.description,
                        debit_amount=line.debit_amount,
                        credit_amount=line.credit_amount,
                    )
                )

            tax_return.journal_entry_id = journal_entry.id
            tax_return.settled_at = datetime.utcnow()

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Tax settlement could not be saved due to a data conflict."
                ) from exc

            self._record_audit(
                company_id,
                tax_return.id,
                journal_entry.id,
                f"VAT settlement posted (entry={journal_entry.entry_number}, "
                f"period={tax_return.period_start.isoformat()}–"
                f"{tax_return.period_end.isoformat()}).",
            )

            return TaxSettlementResultDTO(
                return_id=tax_return.id,
                journal_entry_id=journal_entry.id,
                settlement_date=settlement_date,
                total_output_vat=preview.total_output_vat,
                total_input_vat_recoverable=preview.total_input_vat_recoverable,
                net_payable_amount=preview.net_payable_amount,
                net_credit_carryforward_amount=preview.net_credit_carryforward_amount,
            )

    # --------------------------------------------------------------- planning

    def _build_preview(
        self,
        session: Session,
        company_id: int,
        tax_return,
        *,
        requested_settlement_date: date | None = None,
    ) -> TaxSettlementPreviewDTO:
        settlement_date = requested_settlement_date or tax_return.period_end

        # Resolve the fiscal_period_ids whose coverage falls inside the
        # return window.  We sum posted_tax_lines through these periods
        # (typically a single monthly period; CIT or quarterly windows
        # may span multiple).
        fiscal_period_repo = self._fiscal_period_repository_factory(session)
        all_periods = fiscal_period_repo.list_by_company(company_id)
        period_ids = [
            p.id
            for p in all_periods
            if p.start_date >= tax_return.period_start
            and p.end_date <= tax_return.period_end
        ]

        ptl_repo = self._posted_tax_line_repository_factory(session)
        sales_aggs = (
            ptl_repo.aggregate_for_period(
                company_id, period_ids, direction=DIRECTION_SALES
            )
            if period_ids
            else []
        )
        purchase_aggs = (
            ptl_repo.aggregate_for_period(
                company_id, period_ids, direction=DIRECTION_PURCHASE
            )
            if period_ids
            else []
        )

        mapping_repo = self._tax_code_account_mapping_repository_factory(session)
        mappings_by_tax_code = {
            m.tax_code_id: m
            for m in mapping_repo.list_by_company(company_id)
        }
        account_repo = self._account_repository_factory(session)

        blocking: list[str] = []

        output_lines, output_total = self._aggregate_by_account(
            aggs=sales_aggs,
            mappings_by_tax_code=mappings_by_tax_code,
            account_resolver=lambda m: m.tax_liability_account_id,
            account_repo=account_repo,
            company_id=company_id,
            kind_label="output VAT",
            blocking=blocking,
            include_recoverable_filter=False,
        )
        input_lines, input_total = self._aggregate_by_account(
            aggs=purchase_aggs,
            mappings_by_tax_code=mappings_by_tax_code,
            account_resolver=lambda m: m.tax_asset_account_id,
            account_repo=account_repo,
            company_id=company_id,
            kind_label="input VAT",
            blocking=blocking,
            include_recoverable_filter=True,
        )

        net = output_total - input_total
        # T37: withholding VAT (précompte) reduces amount payable to DGI.
        withholding_vat = getattr(tax_return, "withholding_vat_amount", _ZERO) or _ZERO
        withholding_vat = Decimal(str(withholding_vat))
        net_payable = max(_ZERO, net - withholding_vat) if net > _ZERO else _ZERO
        net_credit = (-net) if net < _ZERO else _ZERO

        plan_lines: list[TaxSettlementLineDTO] = []
        # Dr each output VAT account (drains the credit balance).
        for agg in output_lines:
            plan_lines.append(
                TaxSettlementLineDTO(
                    account_id=agg.account_id,
                    account_code=agg.account_code,
                    account_name=agg.account_name,
                    debit_amount=agg.amount,
                    credit_amount=_ZERO,
                    description=f"Output VAT settlement ({agg.account_code})",
                    role=_LINE_ROLE_OUTPUT,
                )
            )
        # Cr each input VAT account (drains the debit balance).
        for agg in input_lines:
            plan_lines.append(
                TaxSettlementLineDTO(
                    account_id=agg.account_id,
                    account_code=agg.account_code,
                    account_name=agg.account_name,
                    debit_amount=_ZERO,
                    credit_amount=agg.amount,
                    description=f"Input VAT settlement ({agg.account_code})",
                    role=_LINE_ROLE_INPUT,
                )
            )

        # T37: withholding VAT receivable leg (Dr 4443 — funds withheld by customer).
        if withholding_vat > _ZERO:
            wht_account = self._resolve_settlement_account(
                account_repo,
                company_id,
                SETTLEMENT_WITHHOLDING_VAT_RECEIVABLE_ACCOUNT_CODE,
                "VAT withholding receivable",
                blocking,
            )
            if wht_account is not None:
                plan_lines.append(
                    TaxSettlementLineDTO(
                        account_id=wht_account.id,
                        account_code=wht_account.account_code,
                        account_name=wht_account.account_name,
                        debit_amount=withholding_vat,
                        credit_amount=_ZERO,
                        description="VAT withheld by customer (précompte)",
                        role=_LINE_ROLE_WITHHOLDING_RECEIVABLE,
                    )
                )

        # Plug — payable or credit-carry-forward.
        if net_payable > _ZERO:
            payable = self._resolve_settlement_account(
                account_repo,
                company_id,
                SETTLEMENT_VAT_PAYABLE_ACCOUNT_CODE,
                "VAT payable",
                blocking,
            )
            if payable is not None:
                plan_lines.append(
                    TaxSettlementLineDTO(
                        account_id=payable.id,
                        account_code=payable.account_code,
                        account_name=payable.account_name,
                        debit_amount=_ZERO,
                        credit_amount=net_payable,
                        description="Net VAT payable",
                        role=_LINE_ROLE_PAYABLE,
                    )
                )
        elif net_credit > _ZERO:
            credit_account = self._resolve_settlement_account(
                account_repo,
                company_id,
                SETTLEMENT_VAT_CREDIT_CARRYFORWARD_ACCOUNT_CODE,
                "VAT credit carry-forward",
                blocking,
            )
            if credit_account is not None:
                plan_lines.append(
                    TaxSettlementLineDTO(
                        account_id=credit_account.id,
                        account_code=credit_account.account_code,
                        account_name=credit_account.account_name,
                        debit_amount=net_credit,
                        credit_amount=_ZERO,
                        description="VAT credit carry-forward",
                        role=_LINE_ROLE_CREDIT_CARRYFORWARD,
                    )
                )

        return TaxSettlementPreviewDTO(
            return_id=tax_return.id,
            company_id=company_id,
            period_start=tax_return.period_start,
            period_end=tax_return.period_end,
            settlement_date=settlement_date,
            total_output_vat=output_total,
            total_input_vat_recoverable=input_total,
            net_payable_amount=net_payable,
            net_credit_carryforward_amount=net_credit,
            journal_lines=tuple(plan_lines),
            blocking_issues=tuple(blocking),
        )

    @staticmethod
    def _aggregate_by_account(
        *,
        aggs: list[PostedTaxLineAggregate],
        mappings_by_tax_code: dict[int, object],
        account_resolver: Callable[[object], int | None],
        account_repo: AccountRepository,
        company_id: int,
        kind_label: str,
        blocking: list[str],
        include_recoverable_filter: bool,
    ) -> tuple[list[_AccountAggregate], Decimal]:
        amounts_by_account: dict[int, Decimal] = {}
        total = _ZERO
        for agg in aggs:
            if agg.tax_code_id is None:
                continue
            if include_recoverable_filter and agg.is_recoverable is False:
                # Non-recoverable input VAT does not flow through the
                # settlement — it stays expensed against the original
                # purchase account.
                continue
            mapping = mappings_by_tax_code.get(agg.tax_code_id)
            if mapping is None:
                blocking.append(
                    f"No tax-code account mapping for {kind_label} on tax_code_id="
                    f"{agg.tax_code_id}."
                )
                continue
            account_id = account_resolver(mapping)
            if account_id is None:
                blocking.append(
                    f"Tax code {agg.tax_code_id} has no {kind_label} account configured."
                )
                continue
            amount = agg.tax_amount or _ZERO
            if amount == _ZERO:
                continue
            amounts_by_account[account_id] = (
                amounts_by_account.get(account_id, _ZERO) + amount
            )
            total += amount

        if total < _ZERO:
            # Net negative aggregate (heavy reversals via credit notes)
            # should not be settled blindly — it implies amended posts
            # that the operator should review.
            blocking.append(
                f"Aggregate {kind_label} for the period is negative; review credit-note posts."
            )
            return [], total

        results: list[_AccountAggregate] = []
        for account_id, amount in amounts_by_account.items():
            if amount == _ZERO:
                continue
            account = account_repo.get_by_id(company_id, account_id)
            if account is None:  # pragma: no cover - defensive
                blocking.append(
                    f"Configured {kind_label} account id={account_id} could not be loaded."
                )
                continue
            results.append(
                _AccountAggregate(
                    account_id=account.id,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    amount=amount,
                )
            )
        results.sort(key=lambda a: a.account_code)
        return results, total

    @staticmethod
    def _resolve_settlement_account(
        account_repo: AccountRepository,
        company_id: int,
        account_code: str,
        label: str,
        blocking: list[str],
    ) -> Account | None:
        account = account_repo.get_by_code(company_id, account_code)
        if account is None:
            blocking.append(
                f"{label} account ({account_code}) is missing from the chart of accounts."
            )
            return None
        if not account.is_active:
            blocking.append(
                f"{label} account ({account_code}) is inactive."
            )
            return None
        if not account.allow_manual_posting:
            blocking.append(
                f"{label} account ({account_code}) does not allow manual posting."
            )
            return None
        return account

    # ----------------------------------------------------------------- helpers

    def _load_filed_vat_return(
        self,
        session: Session,
        company_id: int,
        return_id: int,
    ):
        repo = self._tax_return_repository_factory(session)
        tax_return = repo.get_by_id(company_id, return_id)
        if tax_return is None:
            raise NotFoundError(f"Tax return {return_id} was not found for this company.")
        if tax_return.tax_type_code != TAX_TYPE_VAT:
            raise ValidationError(
                "Settlement is currently supported for VAT returns only."
            )
        if tax_return.status_code != RETURN_STATUS_FILED:
            raise ValidationError(
                "Only filed tax returns can be settled."
            )
        if tax_return.journal_entry_id is not None:
            raise ConflictError(
                "This tax return has already been settled — its settlement journal entry exists."
            )
        return tax_return

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _record_audit(
        self,
        company_id: int,
        return_id: int,
        journal_entry_id: int,
        message: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import (
            RecordAuditEventCommand,
        )
        from seeker_accounting.modules.audit.event_type_catalog import (
            MODULE_TAXATION,
            TAX_RETURN_SETTLED,
        )

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=TAX_RETURN_SETTLED,
                    module_code=MODULE_TAXATION,
                    entity_type="TaxReturn",
                    entity_id=return_id,
                    description=f"{message} [journal_entry_id={journal_entry_id}]",
                ),
            )
        except Exception:
            pass
