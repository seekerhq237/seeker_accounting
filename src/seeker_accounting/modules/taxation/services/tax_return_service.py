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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.purchase_bill_line import (
    PurchaseBillLine,
)
from seeker_accounting.modules.purchases.models.purchase_bill_line_tax import (
    PurchaseBillLineTax,
)
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
from seeker_accounting.modules.sales.models.sales_invoice_line_tax import (
    SalesInvoiceLineTax,
)
from seeker_accounting.modules.taxation.constants import (
    ALL_ASSESSED_RETURN_TAX_TYPES,
    OBLIGATION_STATUS_FILED,
    OBLIGATION_STATUS_OPEN,
    RETURN_STATUS_CANCELLED,
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_FILED,
    TAX_TYPE_VAT,
    VAT_BOX_INPUT_TAX_DEDUCTIBLE,
    VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE,
    VAT_BOX_NET_VAT_DUE,
    VAT_BOX_OUTPUT_TAX,
    VAT_BOX_TAXABLE_PURCHASES,
    VAT_BOX_TAXABLE_SALES,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    DraftVATReturnCommand,
    FileAssessedTaxReturnCommand,
    FileTaxReturnCommand,
    TaxReturnDTO,
    TaxReturnLineDTO,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
from seeker_accounting.modules.taxation.models.tax_return_line import TaxReturnLine
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


TaxReturnRepositoryFactory = Callable[[Session], TaxReturnRepository]
TaxObligationRepositoryFactory = Callable[[Session], TaxObligationRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


_ZERO = Decimal("0.00")


# Default VAT box ordering / labels (Phase 1 — Cameroon DGI form proxy).
_VAT_BOX_DEFINITIONS: tuple[tuple[str, str], ...] = (
    (VAT_BOX_TAXABLE_SALES, "Taxable sales (HT)"),
    (VAT_BOX_OUTPUT_TAX, "Output VAT (collected)"),
    (VAT_BOX_TAXABLE_PURCHASES, "Taxable purchases (HT)"),
    (VAT_BOX_INPUT_TAX_DEDUCTIBLE, "Input VAT (deductible)"),
    (VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE, "Input VAT (non-deductible)"),
    (VAT_BOX_NET_VAT_DUE, "Net VAT due"),
)


class TaxReturnService:
    PERMISSION_VIEW = "taxation.returns.view"
    PERMISSION_MANAGE = "taxation.returns.manage"
    PERMISSION_FILE = "taxation.returns.file"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        tax_return_repository_factory: TaxReturnRepositoryFactory,
        tax_obligation_repository_factory: TaxObligationRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_return_repository_factory = tax_return_repository_factory
        self._tax_obligation_repository_factory = tax_obligation_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

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

            box_totals = self._compute_vat_box_totals(
                uow.session,
                company_id,
                obligation.period_start,
                obligation.period_end,
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
                    notes=notes,
                    prepared_by_user_id=actor_id,
                )
                return_repo.add(tax_return)
                event_code = "TAX_RETURN_DRAFTED"
            else:
                tax_return = existing
                tax_return.notes = notes
                tax_return.prepared_by_user_id = actor_id
                # Wipe old lines; rebuild from posted facts.
                tax_return.lines.clear()
                event_code = "TAX_RETURN_UPDATED"

            for sort_order, (box_code, label) in enumerate(_VAT_BOX_DEFINITIONS):
                tax_return.lines.append(
                    TaxReturnLine(
                        box_code=box_code,
                        label=label,
                        amount=box_totals.get(box_code, _ZERO),
                        sort_order=sort_order,
                    )
                )

            tax_return.total_due_amount = box_totals.get(VAT_BOX_NET_VAT_DUE, _ZERO)

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

    def file_return(
        self,
        company_id: int,
        command: FileTaxReturnCommand,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        self._permission_service.require_permission(self.PERMISSION_FILE)
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

    def _compute_vat_box_totals(
        self,
        session: Session,
        company_id: int,
        period_start,
        period_end,
    ) -> dict[str, Decimal]:
        """Aggregate VAT facts from posted sales invoices and purchase bills."""
        totals: dict[str, Decimal] = {
            VAT_BOX_TAXABLE_SALES: _ZERO,
            VAT_BOX_OUTPUT_TAX: _ZERO,
            VAT_BOX_TAXABLE_PURCHASES: _ZERO,
            VAT_BOX_INPUT_TAX_DEDUCTIBLE: _ZERO,
            VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE: _ZERO,
            VAT_BOX_NET_VAT_DUE: _ZERO,
        }

        # ── Sales side ──
        sales_stmt = (
            select(
                SalesInvoiceLineTax.taxable_base,
                SalesInvoiceLineTax.tax_amount,
            )
            .join(
                SalesInvoiceLine,
                SalesInvoiceLine.id == SalesInvoiceLineTax.sales_invoice_line_id,
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .join(TaxCode, TaxCode.id == SalesInvoiceLineTax.tax_code_id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status_code == "posted",
                SalesInvoice.invoice_date >= period_start,
                SalesInvoice.invoice_date <= period_end,
                TaxCode.tax_type_code == TAX_TYPE_VAT,
            )
        )
        for taxable_base, tax_amount in session.execute(sales_stmt).all():
            totals[VAT_BOX_TAXABLE_SALES] += taxable_base or _ZERO
            totals[VAT_BOX_OUTPUT_TAX] += tax_amount or _ZERO

        # ── Purchases side ──
        purchases_stmt = (
            select(
                PurchaseBillLineTax.taxable_base,
                PurchaseBillLineTax.tax_amount,
                PurchaseBillLineTax.is_recoverable,
            )
            .join(
                PurchaseBillLine,
                PurchaseBillLine.id == PurchaseBillLineTax.purchase_bill_line_id,
            )
            .join(PurchaseBill, PurchaseBill.id == PurchaseBillLine.purchase_bill_id)
            .join(TaxCode, TaxCode.id == PurchaseBillLineTax.tax_code_id)
            .where(
                PurchaseBill.company_id == company_id,
                PurchaseBill.status_code == "posted",
                PurchaseBill.bill_date >= period_start,
                PurchaseBill.bill_date <= period_end,
                TaxCode.tax_type_code == TAX_TYPE_VAT,
            )
        )
        for taxable_base, tax_amount, is_recoverable in session.execute(
            purchases_stmt
        ).all():
            totals[VAT_BOX_TAXABLE_PURCHASES] += taxable_base or _ZERO
            if bool(is_recoverable):
                totals[VAT_BOX_INPUT_TAX_DEDUCTIBLE] += tax_amount or _ZERO
            else:
                totals[VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE] += tax_amount or _ZERO

        totals[VAT_BOX_NET_VAT_DUE] = (
            totals[VAT_BOX_OUTPUT_TAX] - totals[VAT_BOX_INPUT_TAX_DEDUCTIBLE]
        )

        # Quantize to 2 dp.
        return {k: v.quantize(Decimal("0.01")) for k, v in totals.items()}

    # ------------------------------ Helpers ------------------------------

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        company_repo = self._company_repository_factory(session)
        if company_repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    @staticmethod
    def _to_dto(tax_return: TaxReturn) -> TaxReturnDTO:
        lines = tuple(
            TaxReturnLineDTO(
                id=line.id,
                box_code=line.box_code,
                label=line.label,
                amount=line.amount,
                sort_order=line.sort_order,
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
