"""Service for tax returns (filings).

Returns are generated from POSTED source documents only. Sales
invoices and purchase bills with ``status_code = "posted"`` are read,
their line tax-detail rows aggregated by VAT box, and the resulting
breakdown stored as immutable ``TaxReturnLine`` rows.

Re-drafting a return wipes the existing lines and recomputes from
posted facts. Filing locks the return.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    ALL_ASSESSED_RETURN_TAX_TYPES,
    OBLIGATION_STATUS_FILED,
    OBLIGATION_STATUS_OPEN,
    RETURN_STATUS_APPROVED,
    RETURN_STATUS_CANCELLED,
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_FILED,
    RETURN_STATUS_READY_FOR_REVIEW,
    RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION,
    RETURN_STATUS_SUBMITTED_CONFIRMED,
    TAX_TYPE_VAT,
    VAT_BASIS_CASH,
    VAT_BOX_INPUT_TAX_DEDUCTIBLE,
    VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE,
    VAT_BOX_NET_VAT_DUE,
    VAT_BOX_OUTPUT_TAX,
    VAT_BOX_TAXABLE_PURCHASES,
    VAT_BOX_TAXABLE_SALES,
    VAT_EXEMPTION_KIND_EXEMPT,
    VAT_EXEMPTION_KIND_EXPORT,
    VAT_EXEMPTION_KIND_OUT_OF_SCOPE,
    VAT_EXEMPTION_KIND_STATE_BORNE,
    VAT_RETURN_LINE_L17,
    VAT_RETURN_LINE_L18,
    VAT_RETURN_LINE_L19,
    VAT_RETURN_LINE_L20,
    VAT_RETURN_LINE_L21,
    VAT_RETURN_LINE_L22,
    VAT_RETURN_LINE_L23,
    VAT_RETURN_LINE_L24,
    VAT_RETURN_LINE_L25,
    VAT_RETURN_LINE_L26,
    VAT_RETURN_LINE_L27,
    VAT_RETURN_LINE_L28,
    VAT_RETURN_LINE_L29,
    VAT_RETURN_LINE_L30,
    VAT_RETURN_LINE_L31,
    VAT_RETURN_LINE_L36,
    VAT_RETURN_LINE_L37,
    VAT_RETURN_LINE_L40,
    VAT_RETURN_LINE_L43,
    VAT_RETURN_LINE_L44,
    VAT_RETURN_LINE_L45,
    VAT_RETURN_LINE_L47,
    VAT_RETURN_LINE_NON_DEDUCTIBLE,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    AmendVATReturnCommand,
    DraftVATReturnCommand,
    FileAssessedTaxReturnCommand,
    FileTaxReturnCommand,
    TaxReturnDTO,
    TaxReturnLineDTO,
)
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    DIRECTION_SALES,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
from seeker_accounting.modules.taxation.models.tax_return_line import TaxReturnLine
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_obligation_repository import (
    TaxObligationRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (
        CompanyTaxProfileRepository,
    )
    from seeker_accounting.modules.taxation.repositories.vat_period_lock_repository import (
        VatPeriodLockRepository,
    )


TaxReturnRepositoryFactory = Callable[[Session], TaxReturnRepository]
TaxObligationRepositoryFactory = Callable[[Session], TaxObligationRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
PostedTaxLineRepositoryFactory = Callable[[Session], PostedTaxLineRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
CompanyTaxProfileRepositoryFactory = Callable[
    [Session], "CompanyTaxProfileRepository"
]
VatPeriodLockRepositoryFactory = Callable[[Session], "VatPeriodLockRepository"]


_ZERO = Decimal("0.00")


# Slice T30: persistence keyed on the DGI statutory line codes
# (L17 … L47).  Order here is the canonical render order.
# T32-T37 extend with L24 (pro-rata %, T34), L25 (credit b/f, T36),
# L31 (deductible after pro-rata, T34), L44 (payable principal),
# L45 (précompte/withholding, T37).
_VAT_FORM_LINE_DEFINITIONS: tuple[tuple[str, str], ...] = (
    (VAT_RETURN_LINE_L17, "Transactions taxable at standard rate"),
    (VAT_RETURN_LINE_L18, "Excise-duty bearing transactions"),
    (VAT_RETURN_LINE_L19, "Lodging-tax transactions"),
    (VAT_RETURN_LINE_L20, "Other taxable transactions"),
    (VAT_RETURN_LINE_L21, "Exports (zero-rated)"),
    (VAT_RETURN_LINE_L22, "Exempt turnover"),
    (VAT_RETURN_LINE_L23, "Total turnover excl. taxes"),
    (VAT_RETURN_LINE_L24, "Pro-rata percentage"),
    (VAT_RETURN_LINE_L25, "Credit brought forward from prior period"),
    (VAT_RETURN_LINE_L26, "VAT recoverable on local goods"),
    (VAT_RETURN_LINE_L27, "VAT recoverable on local services"),
    (VAT_RETURN_LINE_L28, "VAT recoverable on imported goods"),
    (VAT_RETURN_LINE_L29, "VAT recoverable on imported services"),
    (VAT_RETURN_LINE_L30, "Total VAT recoverable before pro-rata"),
    (VAT_RETURN_LINE_L31, "VAT deductible after pro-rata"),
    (VAT_RETURN_LINE_L36, "VAT collected (output)"),
    (VAT_RETURN_LINE_L37, "VAT recoverable (input)"),
    (VAT_RETURN_LINE_L40, "VAT payable"),
    (VAT_RETURN_LINE_L43, "Credit to be carried forward"),
    (VAT_RETURN_LINE_L44, "VAT payable (principal)"),
    (VAT_RETURN_LINE_L45, "VAT retained at source (précompte)"),
    (VAT_RETURN_LINE_L47, "Total amount payable"),
    (VAT_RETURN_LINE_NON_DEDUCTIBLE, "Non-deductible input VAT (informational)"),
)


# Lines whose ``base_amount`` carries the HT base value while ``amount``
# carries the VAT figure.  Any L-code outside this set is a sum / total
# row and stores ``base_amount = NULL``.
_LINES_WITH_BASE: frozenset[str] = frozenset(
    {
        VAT_RETURN_LINE_L17, VAT_RETURN_LINE_L18, VAT_RETURN_LINE_L19,
        VAT_RETURN_LINE_L20, VAT_RETURN_LINE_L21, VAT_RETURN_LINE_L22,
        VAT_RETURN_LINE_L26, VAT_RETURN_LINE_L27, VAT_RETURN_LINE_L28,
        VAT_RETURN_LINE_L29,
    }
)

# L24 stores the pro-rata percentage as a plain decimal in the ``tax``
# slot (0.00–100.00); its base slot is NULL like other total rows.
# L25 stores the credit-carried-forward amount in the ``tax`` slot.
# L45 stores the précompte (withholding) amount in the ``tax`` slot.


# Sales-side L-codes that contribute to L36 (VAT collected total).
_OUTPUT_VAT_LINES: tuple[str, ...] = (
    VAT_RETURN_LINE_L17, VAT_RETURN_LINE_L18,
    VAT_RETURN_LINE_L19, VAT_RETURN_LINE_L20,
)
# Sales-side L-codes that contribute to L23 (total turnover HT).
_TURNOVER_LINES: tuple[str, ...] = (
    VAT_RETURN_LINE_L17, VAT_RETURN_LINE_L18, VAT_RETURN_LINE_L19,
    VAT_RETURN_LINE_L20, VAT_RETURN_LINE_L21,
)
# Purchase-side L-codes that contribute to L30 (VAT recoverable total).
_INPUT_VAT_LINES: tuple[str, ...] = (
    VAT_RETURN_LINE_L26, VAT_RETURN_LINE_L27,
    VAT_RETURN_LINE_L28, VAT_RETURN_LINE_L29,
)


class TaxReturnService:
    PERMISSION_VIEW = "taxation.returns.view"
    PERMISSION_MANAGE = "taxation.returns.manage"
    PERMISSION_FILE = "taxation.returns.file"
    # T47: 4-eye workflow permissions
    PERMISSION_REVIEW = "taxation.returns.review"
    PERMISSION_APPROVE = "taxation.returns.approve"
    PERMISSION_CONFIRM = "taxation.returns.confirm"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        tax_return_repository_factory: TaxReturnRepositoryFactory,
        tax_obligation_repository_factory: TaxObligationRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        posted_tax_line_repository_factory: PostedTaxLineRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
        company_tax_profile_repository_factory: CompanyTaxProfileRepositoryFactory | None = None,
        vat_period_lock_repository_factory: VatPeriodLockRepositoryFactory | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_return_repository_factory = tax_return_repository_factory
        self._tax_obligation_repository_factory = tax_obligation_repository_factory
        self._company_repository_factory = company_repository_factory
        self._posted_tax_line_repository_factory = posted_tax_line_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service
        self._company_tax_profile_repository_factory = company_tax_profile_repository_factory
        self._vat_period_lock_repository_factory = vat_period_lock_repository_factory

    # ------------------------------ Read ------------------------------

    def list_returns(
        self,
        company_id: int,
        *,
        status_code: str | None = None,
    ) -> list[TaxReturnDTO]:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            returns = repo.list_by_company(company_id, status_code=status_code)
            return [self._to_dto(r) for r in returns]

    def get_return(self, company_id: int, return_id: int) -> TaxReturnDTO:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(
                    f"Tax return {return_id} was not found for this company.",
                )
            return self._to_dto(tax_return)

    # ------------------------------ Write ------------------------------

    def draft_vat_return(
        self,
        company_id: int,
        command: DraftVATReturnCommand,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """Generate or regenerate a draft VAT return for the obligation."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        actor_id = (
            actor_user_id
            if actor_user_id is not None
            else self._app_context.current_user_id
        )

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)

            obligation_repo = self._tax_obligation_repository_factory(uow.session)
            obligation = obligation_repo.get_by_id(company_id, command.obligation_id)
            if obligation is None:
                raise NotFoundError(
                    f"Tax obligation {command.obligation_id} was not found.",
                )
            if obligation.tax_type_code != TAX_TYPE_VAT:
                raise ValidationError(
                    "Drafting a VAT return requires a VAT-type obligation.",
                )

            return_repo = self._tax_return_repository_factory(uow.session)
            existing = return_repo.get_by_obligation(company_id, obligation.id)
            if existing is not None and existing.status_code == RETURN_STATUS_FILED:
                raise ConflictError(
                    "This obligation already has a filed return. Amend it instead.",
                )

            # T36: credit brought forward — read the L43 value from the most
            # recent FILED return for this obligation's tax type.
            credit_bf = self._resolve_credit_brought_forward(
                uow.session, company_id, TAX_TYPE_VAT,
                exclude_return_id=existing.id if existing else None,
            )

            # T37: withholding VAT — aggregate withheld amounts from posted
            # sales invoices in this return period.
            withholding_vat = self._aggregate_withholding_vat(
                uow.session, company_id,
                obligation.period_start, obligation.period_end,
            )

            form_lines = self._compute_vat_form_lines(
                uow.session,
                company_id,
                obligation.period_start,
                obligation.period_end,
                credit_brought_forward=credit_bf,
                withholding_vat_amount=withholding_vat,
            )

            notes = (command.notes or "").strip() or None

            if existing is None:
                tax_return = TaxReturn(
                    company_id=company_id,
                    obligation_id=obligation.id,
                    tax_type_code=TAX_TYPE_VAT,
                    period_start=obligation.period_start,
                    period_end=obligation.period_end,
                    status_code=RETURN_STATUS_DRAFT,
                    total_due_amount=_ZERO,
                    total_paid_amount=_ZERO,
                    credit_brought_forward=credit_bf,
                    withholding_vat_amount=withholding_vat,
                    notes=notes,
                    prepared_by_user_id=actor_id,
                )
                return_repo.add(tax_return)
                event_code = "TAX_RETURN_DRAFTED"
            else:
                tax_return = existing
                tax_return.notes = notes
                tax_return.prepared_by_user_id = actor_id
                tax_return.credit_brought_forward = credit_bf
                tax_return.withholding_vat_amount = withholding_vat
                # T49: block re-drafting of a filed (immutable) return.
                if any(getattr(line, "is_immutable", False) for line in tax_return.lines):
                    raise ConflictError(
                        "Cannot re-draft a filed return whose lines are immutable."
                    )
                # Wipe old lines; rebuild from posted facts.
                tax_return.lines.clear()
                event_code = "TAX_RETURN_UPDATED"

            for sort_order, (line_code, label) in enumerate(_VAT_FORM_LINE_DEFINITIONS):
                bucket = form_lines.get(line_code, {"base": _ZERO, "tax": _ZERO})
                base_value = bucket.get("base", _ZERO)
                tax_value = bucket.get("tax", _ZERO)
                # Persist ``base_amount`` only for line codes that
                # carry an HT base.  Sum / total rows leave it NULL.
                base_amount: Decimal | None = (
                    base_value if line_code in _LINES_WITH_BASE else None
                )
                tax_return.lines.append(
                    TaxReturnLine(
                        box_code=line_code,
                        label=label,
                        amount=tax_value,
                        base_amount=base_amount,
                        sort_order=sort_order,
                    )
                )

            tax_return.total_due_amount = form_lines.get(
                VAT_RETURN_LINE_L40, {"tax": _ZERO}
            ).get("tax", _ZERO)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Tax return could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                event_code,
                tax_return.id,
                f"Drafted VAT return for "
                f"{obligation.period_start.isoformat()} – {obligation.period_end.isoformat()}.",
            )

            # Reload with lines/payments for DTO.
            tax_return = return_repo.get_by_id(company_id, tax_return.id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    # T35: amendment --------------------------------------------------

    def amend_vat_return(
        self,
        company_id: int,
        command: AmendVATReturnCommand,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """Create an amended (corrective) VAT return for a FILED return.

        The original return is NOT cancelled — both coexist.  The new
        return is created as DRAFT, flagged ``is_amended=True`` and
        linked to the original via ``amends_return_id``.  The caller
        files the new return separately via ``file_return``.
        """
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        actor_id = (
            actor_user_id
            if actor_user_id is not None
            else self._app_context.current_user_id
        )

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)

            obligation_repo = self._tax_obligation_repository_factory(uow.session)
            obligation = obligation_repo.get_by_id(
                company_id, command.obligation_id
            )
            if obligation is None:
                raise NotFoundError(
                    f"Tax obligation {command.obligation_id} was not found.",
                )
            if obligation.tax_type_code != TAX_TYPE_VAT:
                raise ValidationError(
                    "Amendments are only supported for VAT-type obligations.",
                )

            return_repo = self._tax_return_repository_factory(uow.session)
            original = return_repo.get_by_id(company_id, command.original_return_id)
            if original is None:
                raise NotFoundError(
                    f"Original return {command.original_return_id} was not found.",
                )
            if original.status_code != RETURN_STATUS_FILED:
                raise ValidationError(
                    "Only a FILED return can be amended.  The original return is "
                    f"currently '{original.status_code}'.",
                )

            # Block if a DRAFT amendment already exists for this obligation.
            existing_draft = return_repo.get_by_obligation(
                company_id, obligation.id, status_code=RETURN_STATUS_DRAFT
            )
            if existing_draft is not None:
                raise ConflictError(
                    "An unresolved DRAFT return already exists for this obligation. "
                    "File or cancel it before creating a new amendment.",
                )

            credit_bf = self._resolve_credit_brought_forward(
                uow.session, company_id, TAX_TYPE_VAT,
                exclude_return_id=None,
            )
            withholding_vat = self._aggregate_withholding_vat(
                uow.session, company_id,
                obligation.period_start, obligation.period_end,
            )

            form_lines = self._compute_vat_form_lines(
                uow.session,
                company_id,
                obligation.period_start,
                obligation.period_end,
                credit_brought_forward=credit_bf,
                withholding_vat_amount=withholding_vat,
            )

            notes = (command.notes or "").strip() or None

            amended_return = TaxReturn(
                company_id=company_id,
                obligation_id=obligation.id,
                tax_type_code=TAX_TYPE_VAT,
                period_start=obligation.period_start,
                period_end=obligation.period_end,
                status_code=RETURN_STATUS_DRAFT,
                total_due_amount=_ZERO,
                total_paid_amount=_ZERO,
                is_amended=True,
                amends_return_id=command.original_return_id,
                credit_brought_forward=credit_bf,
                withholding_vat_amount=withholding_vat,
                notes=notes,
                prepared_by_user_id=actor_id,
            )
            return_repo.add(amended_return)

            for sort_order, (line_code, label) in enumerate(_VAT_FORM_LINE_DEFINITIONS):
                bucket = form_lines.get(line_code, {"base": _ZERO, "tax": _ZERO})
                base_value = bucket.get("base", _ZERO)
                tax_value = bucket.get("tax", _ZERO)
                base_amount: Decimal | None = (
                    base_value if line_code in _LINES_WITH_BASE else None
                )
                amended_return.lines.append(
                    TaxReturnLine(
                        box_code=line_code,
                        label=label,
                        amount=tax_value,
                        base_amount=base_amount,
                        sort_order=sort_order,
                    )
                )

            amended_return.total_due_amount = form_lines.get(
                VAT_RETURN_LINE_L40, {"tax": _ZERO}
            ).get("tax", _ZERO)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError(
                    "Amendment could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "TAX_RETURN_AMENDED",
                amended_return.id,
                f"Created amended return for obligation {obligation.id} "
                f"(amends return {command.original_return_id}).",
            )

            amended_return = return_repo.get_by_id(company_id, amended_return.id)  # type: ignore[assignment]
            assert amended_return is not None
            return self._to_dto(amended_return)

    def file_return(
        self,
        company_id: int,
        command: FileTaxReturnCommand,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        self._permission_service.require_permission(self.PERMISSION_FILE)
        actor_id = (
            actor_user_id
            if actor_user_id is not None
            else self._app_context.current_user_id
        )
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, command.return_id)
            if tax_return is None:
                raise NotFoundError(
                    f"Tax return {command.return_id} was not found.",
                )
            if tax_return.status_code == RETURN_STATUS_FILED:
                raise ConflictError("This return has already been filed.")
            if tax_return.status_code == RETURN_STATUS_CANCELLED:
                raise ValidationError("Cancelled returns cannot be filed.")

            otp = (command.otp_reference or "").strip() or None
            ext = (command.external_reference or "").strip() or None

            tax_return.status_code = RETURN_STATUS_FILED
            tax_return.filed_at = datetime.utcnow()
            tax_return.otp_reference = otp
            tax_return.external_reference = ext

            # T49: mark all lines immutable when the return is filed.
            for line in tax_return.lines:
                line.is_immutable = True

            # T43: auto-lock the VAT period when a VAT return is filed.
            if (
                tax_return.tax_type_code == TAX_TYPE_VAT
                and self._vat_period_lock_repository_factory is not None
            ):
                from seeker_accounting.modules.taxation.models.vat_period_lock import VatPeriodLock
                lock_repo = self._vat_period_lock_repository_factory(uow.session)
                lock = VatPeriodLock(
                    company_id=company_id,
                    period_start=tax_return.period_start,
                    period_end=tax_return.period_end,
                    tax_type_code=TAX_TYPE_VAT,
                    locked_by_user_id=actor_id if actor_id else None,
                    locked_at=datetime.utcnow(),
                )
                lock_repo.add(lock)

            uow.commit()

            self._record_audit(
                company_id,
                "TAX_RETURN_FILED",
                tax_return.id,
                f"Filed VAT return for "
                f"{tax_return.period_start.isoformat()} – {tax_return.period_end.isoformat()}.",
            )

            tax_return = repo.get_by_id(company_id, tax_return.id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def file_assessed_return(
        self,
        company_id: int,
        command: FileAssessedTaxReturnCommand,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """File a minimal return for a fixed-amount obligation (T27).

        Patente / TSR / Customs obligations do not aggregate posted
        accounting facts — the assessed amount is entered directly
        and the return is created already in the FILED state.  This
        avoids a redundant DRAFT step for assessment-driven taxes.
        """
        self._permission_service.require_permission(self.PERMISSION_FILE)

        if command.total_due_amount is None:
            raise ValidationError("Assessed amount is required.")
        amount = Decimal(command.total_due_amount).quantize(Decimal("0.01"))
        if amount <= _ZERO:
            raise ValidationError("Assessed amount must be greater than zero.")

        otp = (command.otp_reference or "").strip() or None
        ext = (command.external_reference or "").strip() or None
        notes = (command.notes or "").strip() or None
        if otp is not None and len(otp) > 120:
            raise ValidationError("OTP reference is too long (max 120 characters).")
        if ext is not None and len(ext) > 120:
            raise ValidationError("External reference is too long (max 120 characters).")
        if notes is not None and len(notes) > 500:
            raise ValidationError("Notes are too long (max 500 characters).")

        actor_id = (
            actor_user_id
            if actor_user_id is not None
            else self._app_context.current_user_id
        )

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)

            obligation_repo = self._tax_obligation_repository_factory(uow.session)
            obligation = obligation_repo.get_by_id(company_id, command.obligation_id)
            if obligation is None:
                raise NotFoundError(
                    f"Tax obligation {command.obligation_id} was not found.",
                )
            if obligation.tax_type_code not in ALL_ASSESSED_RETURN_TAX_TYPES:
                raise ValidationError(
                    "Assessed-amount filing is only available for "
                    "Patente, TSR, and Customs obligations.  Use the "
                    "draft-return workflow for VAT.",
                )
            if obligation.status_code != OBLIGATION_STATUS_OPEN:
                raise ValidationError(
                    f"Obligation status is {obligation.status_code}; "
                    "only OPEN obligations can be filed.",
                )

            return_repo = self._tax_return_repository_factory(uow.session)
            existing = return_repo.get_by_obligation(company_id, obligation.id)
            if existing is not None and existing.status_code != RETURN_STATUS_CANCELLED:
                raise ConflictError(
                    "This obligation already has a return.  Cancel it "
                    "before filing a new assessed return.",
                )

            filing_date = command.filing_date  # used only for audit trail today
            tax_return = TaxReturn(
                company_id=company_id,
                obligation_id=obligation.id,
                tax_type_code=obligation.tax_type_code,
                period_start=obligation.period_start,
                period_end=obligation.period_end,
                status_code=RETURN_STATUS_FILED,
                total_due_amount=amount,
                total_paid_amount=_ZERO,
                otp_reference=otp,
                external_reference=ext,
                notes=notes,
                prepared_by_user_id=actor_id,
                filed_at=datetime.utcnow(),
            )
            return_repo.add(tax_return)

            # Move the obligation forward so it shows as filed in the
            # workspace; payment recording will move it to PAID once
            # the amount is fully settled.
            obligation.status_code = OBLIGATION_STATUS_FILED

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Tax return could not be saved due to a data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "TAX_RETURN_ASSESSED_AND_FILED",
                tax_return.id,
                f"Filed assessed {obligation.tax_type_code} return for "
                f"{obligation.period_start.isoformat()} – "
                f"{obligation.period_end.isoformat()} "
                f"(amount {amount}"
                + (f", filing_date {filing_date.isoformat()}" if filing_date else "")
                + ").",
            )

            tax_return = return_repo.get_by_id(company_id, tax_return.id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    # ------------------------------ Aggregation ------------------------------

    def _compute_vat_form_lines(
        self,
        session: Session,
        company_id: int,
        period_start,
        period_end,
        *,
        credit_brought_forward: Decimal = _ZERO,
        withholding_vat_amount: Decimal = _ZERO,
    ) -> dict[str, dict[str, Decimal]]:
        """Aggregate VAT facts into DGI statutory line codes.

        Returns ``{line_code: {"base": Decimal, "tax": Decimal}}`` for
        every L-code populated this period, plus computed totals.

        T32: cash-basis — when company profile uses CASH basis, filter
        by ``payment_date`` (not tax_point_date).

        T33: reverse-charge — purchase facts with ``is_reverse_charge``
        also have a paired SALES fact written by TaxFactService.
        Those pair as L29 (input) and populate L36 as output, so the
        formula self-balances.

        T34: pro-rata — when ``vat_pro_rata_percent`` is set on the
        company tax profile, L30 = gross input total, L31 = L30 ×
        (pro_rata/100), L37 = L31.  L24 stores the percentage.

        T36: credit b/f — passed in by ``draft_vat_return`` from the
        prior period's L43.  Stored in L25; L30 includes L25.

        T37: withholding VAT — passed in by ``draft_vat_return`` from
        aggregated sales invoice withheld amounts.  Stored in L45;
        reduces L47: ``L47 = L40 - L45``.
        """
        out: dict[str, dict[str, Decimal]] = {
            line_code: {"base": _ZERO, "tax": _ZERO}
            for line_code, _ in _VAT_FORM_LINE_DEFINITIONS
        }

        # Resolve fiscal-period ids covering the return window.
        fiscal_period_repo = self._fiscal_period_repository_factory(session)
        all_periods = fiscal_period_repo.list_by_company(company_id)
        period_ids = [
            p.id
            for p in all_periods
            if p.start_date >= period_start and p.end_date <= period_end
        ]
        if not period_ids:
            return {
                k: {kk: vv.quantize(Decimal("0.01")) for kk, vv in v.items()}
                for k, v in out.items()
            }

        # T32: determine VAT accounting basis and payment-date kwargs.
        vat_basis_cash = False
        payment_date_kwargs: dict = {}
        pro_rata_pct: Decimal | None = None
        if self._company_tax_profile_repository_factory is not None:
            ctp_repo = self._company_tax_profile_repository_factory(session)
            profile = ctp_repo.get_by_company(company_id)
            if profile is not None:
                vat_basis_cash = (
                    getattr(profile, "vat_accounting_basis", None) == VAT_BASIS_CASH
                )
                if vat_basis_cash:
                    payment_date_kwargs = {
                        "payment_date_start": period_start,
                        "payment_date_end": period_end,
                    }
                # T34: pro-rata
                pro_rata = getattr(profile, "vat_pro_rata_percent", None)
                if pro_rata is not None:
                    pro_rata_pct = Decimal(str(pro_rata))

        ptl_repo = self._posted_tax_line_repository_factory(session)

        base_kwargs = dict(
            tax_type_code=TAX_TYPE_VAT,
            tax_point_start=None if vat_basis_cash else period_start,
            tax_point_end=None if vat_basis_cash else period_end,
            **payment_date_kwargs,
        )
        period_ids_arg = period_ids if not vat_basis_cash else []

        sales_aggs = ptl_repo.aggregate_for_period(
            company_id,
            period_ids_arg,
            direction=DIRECTION_SALES,
            **base_kwargs,
        )
        purchase_aggs = ptl_repo.aggregate_for_period(
            company_id,
            period_ids_arg,
            direction=DIRECTION_PURCHASE,
            **base_kwargs,
        )

        # T42: merge late claims (ACCRUAL basis only — facts with tax_point_date
        # before the current period that have not yet been included in a return).
        if not vat_basis_cash and hasattr(ptl_repo, "aggregate_late_claims"):
            late_sales = ptl_repo.aggregate_late_claims(
                company_id,
                before_date=period_start,
                direction=DIRECTION_SALES,
                tax_type_code=TAX_TYPE_VAT,
            )
            late_purchases = ptl_repo.aggregate_late_claims(
                company_id,
                before_date=period_start,
                direction=DIRECTION_PURCHASE,
                tax_type_code=TAX_TYPE_VAT,
            )
            sales_aggs = list(sales_aggs) + list(late_sales)
            purchase_aggs = list(purchase_aggs) + list(late_purchases)

        tax_code_ids = {
            agg.tax_code_id
            for agg in (*sales_aggs, *purchase_aggs)
            if agg.tax_code_id is not None
        }
        tax_codes_by_id: dict[int, TaxCode] = {}
        if tax_code_ids:
            from sqlalchemy import select as _select

            stmt = _select(TaxCode).where(TaxCode.id.in_(tax_code_ids))
            for tc in session.scalars(stmt):
                tax_codes_by_id[tc.id] = tc

        # ── Sales side ──
        for agg in sales_aggs:
            tc = tax_codes_by_id.get(agg.tax_code_id) if agg.tax_code_id else None
            line_code = self._sales_line_for(tc)
            out[line_code]["base"] += agg.taxable_base
            if line_code not in (VAT_RETURN_LINE_L21, VAT_RETURN_LINE_L22):
                out[line_code]["tax"] += agg.tax_amount

        # ── Purchases side ──
        for agg in purchase_aggs:
            if not bool(agg.is_recoverable):
                out[VAT_RETURN_LINE_NON_DEDUCTIBLE]["tax"] += agg.tax_amount
                continue
            tc = tax_codes_by_id.get(agg.tax_code_id) if agg.tax_code_id else None
            line_code = self._purchase_line_for(tc)
            out[line_code]["base"] += agg.taxable_base
            out[line_code]["tax"] += agg.tax_amount

        # ── Computed totals ──
        out[VAT_RETURN_LINE_L23]["tax"] = sum(
            (out[c]["base"] for c in _TURNOVER_LINES), _ZERO
        )
        out[VAT_RETURN_LINE_L36]["tax"] = sum(
            (out[c]["tax"] for c in _OUTPUT_VAT_LINES), _ZERO
        )

        # T36: credit brought forward (L25) → included in gross input (L30).
        out[VAT_RETURN_LINE_L25]["tax"] = credit_brought_forward

        # L30 = L25 + L26 + L27 + L28 + L29
        gross_input = sum(
            (out[c]["tax"] for c in _INPUT_VAT_LINES), _ZERO
        ) + credit_brought_forward
        out[VAT_RETURN_LINE_L30]["tax"] = gross_input

        # T34: pro-rata reduces effective deductible (L31 / L37).
        if pro_rata_pct is not None:
            out[VAT_RETURN_LINE_L24]["tax"] = pro_rata_pct
            deductible = (gross_input * pro_rata_pct / Decimal("100")).quantize(
                Decimal("0.01")
            )
            out[VAT_RETURN_LINE_L31]["tax"] = deductible
            out[VAT_RETURN_LINE_L37]["tax"] = deductible
        else:
            out[VAT_RETURN_LINE_L37]["tax"] = gross_input

        net = out[VAT_RETURN_LINE_L36]["tax"] - out[VAT_RETURN_LINE_L37]["tax"]
        if net >= _ZERO:
            out[VAT_RETURN_LINE_L40]["tax"] = net
            out[VAT_RETURN_LINE_L43]["tax"] = _ZERO
        else:
            out[VAT_RETURN_LINE_L40]["tax"] = _ZERO
            out[VAT_RETURN_LINE_L43]["tax"] = -net

        # T37: withholding (précompte) VAT reduces amount actually payable.
        out[VAT_RETURN_LINE_L45]["tax"] = withholding_vat_amount
        # L44 = L40 (principal before précompte adjustment).
        out[VAT_RETURN_LINE_L44]["tax"] = out[VAT_RETURN_LINE_L40]["tax"]
        # L47 = L40 - L45  (précompte already collected).
        payable = out[VAT_RETURN_LINE_L40]["tax"] - withholding_vat_amount
        out[VAT_RETURN_LINE_L47]["tax"] = max(_ZERO, payable)

        return {
            k: {kk: vv.quantize(Decimal("0.01")) for kk, vv in v.items()}
            for k, v in out.items()
        }

    @staticmethod
    def _sales_line_for(tax_code: TaxCode | None) -> str:
        """Bucket a sales fact into its DGI turnover line."""
        if tax_code is None:
            return VAT_RETURN_LINE_L17
        ek = tax_code.exemption_kind
        if ek == VAT_EXEMPTION_KIND_EXEMPT or ek == VAT_EXEMPTION_KIND_OUT_OF_SCOPE:
            return VAT_RETURN_LINE_L22
        if bool(getattr(tax_code, "is_export", False)) or ek == VAT_EXEMPTION_KIND_EXPORT:
            return VAT_RETURN_LINE_L21
        if ek == VAT_EXEMPTION_KIND_STATE_BORNE:
            return VAT_RETURN_LINE_L20
        rb = tax_code.return_box_code
        if rb in (
            VAT_RETURN_LINE_L17, VAT_RETURN_LINE_L18,
            VAT_RETURN_LINE_L19, VAT_RETURN_LINE_L20,
            VAT_RETURN_LINE_L21, VAT_RETURN_LINE_L22,
        ):
            return rb
        return VAT_RETURN_LINE_L17

    @staticmethod
    def _purchase_line_for(tax_code: TaxCode | None) -> str:
        """Bucket a recoverable-purchase fact into its DGI input line."""
        if tax_code is None:
            return VAT_RETURN_LINE_L26
        if bool(getattr(tax_code, "is_imported_service", False)):
            return VAT_RETURN_LINE_L29
        rb = tax_code.return_box_code
        if rb in (
            VAT_RETURN_LINE_L26, VAT_RETURN_LINE_L27,
            VAT_RETURN_LINE_L28, VAT_RETURN_LINE_L29,
        ):
            return rb
        return VAT_RETURN_LINE_L26

    # ------------------------------ Helpers ------------------------------

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        company_repo = self._company_repository_factory(session)
        if company_repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _resolve_credit_brought_forward(
        self,
        session: Session,
        company_id: int,
        tax_type_code: str,
        *,
        exclude_return_id: int | None,
    ) -> Decimal:
        """T36: return the L43 (credit c/f) from the most recently FILED return.

        Returns ``Decimal("0.00")`` if no prior filed return exists.
        """
        repo = self._tax_return_repository_factory(session)
        filed_returns = repo.list_by_company(
            company_id,
            status_code=RETURN_STATUS_FILED,
            tax_type_code=tax_type_code,
        )
        candidates = [
            r for r in filed_returns
            if exclude_return_id is None or r.id != exclude_return_id
        ]
        if not candidates:
            return _ZERO
        # Most recently ended period first.
        latest = max(candidates, key=lambda r: r.period_end)
        # Read L43 from the stored lines.
        for line in latest.lines:
            if line.box_code == VAT_RETURN_LINE_L43:
                return line.amount or _ZERO
        return _ZERO

    def _aggregate_withholding_vat(
        self,
        session: Session,
        company_id: int,
        period_start,
        period_end,
    ) -> Decimal:
        """T37: sum ``withheld_vat_amount`` from POSTED sales invoices in period."""
        from sqlalchemy import select as _select, func as _func

        try:
            from seeker_accounting.modules.sales.models.sales_invoice import (
                SalesInvoice,
            )
        except ImportError:
            return _ZERO

        # Status code constant for posted invoices.
        try:
            from seeker_accounting.modules.sales.constants import (
                INVOICE_STATUS_POSTED,
            )
        except ImportError:
            INVOICE_STATUS_POSTED = "POSTED"  # type: ignore[assignment]

        stmt = (
            _select(_func.coalesce(_func.sum(SalesInvoice.withheld_vat_amount), _ZERO))
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status_code == INVOICE_STATUS_POSTED,
                SalesInvoice.invoice_date >= period_start,
                SalesInvoice.invoice_date <= period_end,
            )
        )
        result = session.scalar(stmt)
        return Decimal(str(result)) if result else _ZERO

    # ----------------------------- T40: drill-down ----------------------

    def list_facts_for_line(
        self,
        company_id: int,
        fiscal_period_ids: list[int],
        return_box_code: str,
        *,
        direction: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """T40: return raw tax facts contributing to a given DGI return-box line.

        Called by ``VATLineDrillDownDialog`` to populate the detail grid.
        Returns a list of dicts with keys:
            ``tax_point_date``, ``source_document_type``, ``source_document_id``,
            ``direction``, ``tax_code_code``, ``taxable_base``, ``tax_amount``,
            ``is_recoverable``, ``is_reverse_charge``.
        """
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            repo = self._posted_tax_line_repository_factory(uow.session)
            facts = repo.list_facts_for_line(
                company_id,
                fiscal_period_ids,
                return_box_code,
                direction=direction,
                limit=limit,
            )
            result = []
            for fact in facts:
                # Resolve tax code display code via joined attribute or lazy load.
                tc_code = ""
                if fact.tax_code_id is not None:
                    from sqlalchemy import select as _select
                    from seeker_accounting.modules.accounting.reference_data.models.tax_code import (
                        TaxCode as _TC,
                    )
                    tc = uow.session.get(_TC, fact.tax_code_id)
                    tc_code = tc.code if tc else str(fact.tax_code_id)
                result.append(
                    {
                        "tax_point_date": fact.tax_point_date,
                        "source_document_type": fact.source_document_type,
                        "source_document_id": fact.source_document_id,
                        "direction": fact.direction,
                        "tax_code_code": tc_code,
                        "taxable_base": fact.taxable_base or _ZERO,
                        "tax_amount": fact.tax_amount or _ZERO,
                        "is_recoverable": fact.is_recoverable,
                        "is_reverse_charge": getattr(fact, "is_reverse_charge", False),
                    }
                )
            return result

    # ----------------------------- T47: state machine --------------------

    def submit_for_review(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: DRAFT → READY_FOR_REVIEW."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_DRAFT:
                raise ValidationError(
                    f"Only DRAFT returns can be submitted for review "
                    f"(current status: {tax_return.status_code})."
                )
            tax_return.status_code = RETURN_STATUS_READY_FOR_REVIEW
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_SUBMITTED_FOR_REVIEW", return_id,
                f"Return {return_id} submitted for review.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def revert_to_draft(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: READY_FOR_REVIEW → DRAFT (re-draft allowed; APPROVED is not)."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_READY_FOR_REVIEW:
                raise ValidationError(
                    "Only READY_FOR_REVIEW returns can be reverted to DRAFT. "
                    f"Cannot revert from '{tax_return.status_code}'."
                )
            tax_return.status_code = RETURN_STATUS_DRAFT
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_REVERTED_TO_DRAFT", return_id,
                f"Return {return_id} reverted to DRAFT from READY_FOR_REVIEW.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def approve_return(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: READY_FOR_REVIEW → APPROVED."""
        self._permission_service.require_permission(self.PERMISSION_APPROVE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_READY_FOR_REVIEW:
                raise ValidationError(
                    "Only READY_FOR_REVIEW returns can be approved "
                    f"(current status: {tax_return.status_code})."
                )
            tax_return.status_code = RETURN_STATUS_APPROVED
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_APPROVED", return_id,
                f"Return {return_id} approved.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def submit_return(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: FILED → SUBMITTED_AWAITING_CONFIRMATION."""
        self._permission_service.require_permission(self.PERMISSION_FILE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_FILED:
                raise ValidationError(
                    "Only FILED returns can be submitted to the authority "
                    f"(current status: {tax_return.status_code})."
                )
            tax_return.status_code = RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_SUBMITTED", return_id,
                f"Return {return_id} submitted to DGI — awaiting confirmation.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def confirm_submission(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: SUBMITTED_AWAITING_CONFIRMATION → SUBMITTED_CONFIRMED."""
        self._permission_service.require_permission(self.PERMISSION_CONFIRM)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION:
                raise ValidationError(
                    "Only SUBMITTED_AWAITING_CONFIRMATION returns can be confirmed "
                    f"(current status: {tax_return.status_code})."
                )
            tax_return.status_code = RETURN_STATUS_SUBMITTED_CONFIRMED
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_SUBMISSION_CONFIRMED", return_id,
                f"Return {return_id} submission confirmed.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    @staticmethod
    def _to_dto(tax_return: TaxReturn) -> TaxReturnDTO:
        lines = tuple(
            TaxReturnLineDTO(
                id=line.id,
                box_code=line.box_code,
                label=line.label,
                amount=line.amount,
                sort_order=line.sort_order,
                base_amount=line.base_amount,
            )
            for line in sorted(tax_return.lines, key=lambda x: x.sort_order)
        )
        return TaxReturnDTO(
            id=tax_return.id,
            company_id=tax_return.company_id,
            obligation_id=tax_return.obligation_id,
            tax_type_code=tax_return.tax_type_code,
            period_start=tax_return.period_start,
            period_end=tax_return.period_end,
            status_code=tax_return.status_code,
            total_due_amount=tax_return.total_due_amount,
            total_paid_amount=tax_return.total_paid_amount,
            filed_at=tax_return.filed_at,
            otp_reference=tax_return.otp_reference,
            external_reference=tax_return.external_reference,
            notes=tax_return.notes,
            prepared_by_user_id=tax_return.prepared_by_user_id,
            lines=lines,
            created_at=tax_return.created_at,
            updated_at=tax_return.updated_at,
            is_amended=getattr(tax_return, "is_amended", False),
            amends_return_id=getattr(tax_return, "amends_return_id", None),
            credit_brought_forward=getattr(
                tax_return, "credit_brought_forward", _ZERO
            ) or _ZERO,
            withholding_vat_amount=getattr(
                tax_return, "withholding_vat_amount", _ZERO
            ) or _ZERO,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import (
            RecordAuditEventCommand,
        )
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_TAXATION

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_TAXATION,
                    entity_type="TaxReturn",
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass
