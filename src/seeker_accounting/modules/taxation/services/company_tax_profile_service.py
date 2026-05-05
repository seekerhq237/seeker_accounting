"""Service for managing the company tax profile.

One profile per company. The service exposes a single ``get_or_default``
read entry point (which always returns a renderable DTO, even before
the row is created) and a single ``upsert`` write entry point — there
is no separate create/update because ``company_id`` is the natural key.

The profile is intentionally permission-gated: the data here drives
return generation, regime classification, and DSF filing, so casual
edits must be guarded.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    ALL_CIT_RATE_PROFILE_CODES,
    ALL_DSF_FORM_CODES,
    ALL_DSF_SUBMISSION_MODES,
    ALL_TAX_REGIME_CODES,
    ALL_TAXPAYER_SEGMENT_CODES,
    ALL_VAT_ACCOUNTING_BASIS_CODES,
    VAT_BASIS_ACCRUAL,
)
from seeker_accounting.modules.taxation.dto.company_tax_profile_dto import (
    CompanyTaxProfileDTO,
    UpsertCompanyTaxProfileCommand,
)
from seeker_accounting.modules.taxation.models.company_tax_profile import (
    CompanyTaxProfile,
)
from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (
    CompanyTaxProfileRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService


CompanyTaxProfileRepositoryFactory = Callable[[Session], CompanyTaxProfileRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


_NIU_MAX_LEN = 50
_CODE_MAX_LEN = 50


class CompanyTaxProfileService:
    PERMISSION_VIEW = "taxation.profile.view"
    PERMISSION_MANAGE = "taxation.profile.manage"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        company_tax_profile_repository_factory: CompanyTaxProfileRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._company_tax_profile_repository_factory = company_tax_profile_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_or_default(self, company_id: int) -> CompanyTaxProfileDTO:
        """Return the company's tax profile, or a default DTO if absent.

        The DTO carries an ``exists`` flag so the UI can distinguish
        "first-time setup" from "edit existing" without a separate API.
        """
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._company_tax_profile_repository_factory(uow.session)
            profile = repo.get_by_company(company_id)
            if profile is None:
                return self._default_dto(company_id)
            return self._to_dto(profile)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(
        self,
        company_id: int,
        command: UpsertCompanyTaxProfileCommand,
        actor_user_id: int | None = None,
    ) -> CompanyTaxProfileDTO:
        """Create or update the single profile row for ``company_id``."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        normalized = self._normalize_command(command)

        actor_id = (
            actor_user_id
            if actor_user_id is not None
            else self._app_context.current_user_id
        )

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._company_tax_profile_repository_factory(uow.session)

            profile = repo.get_by_company(company_id)
            is_new = profile is None
            if profile is None:
                profile = CompanyTaxProfile(company_id=company_id)
                repo.add(profile)

            self._apply_command(profile, normalized)
            profile.updated_by_user_id = actor_id

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Company tax profile could not be saved due to a data conflict.",
                ) from exc

            from seeker_accounting.modules.audit.event_type_catalog import (
                COMPANY_TAX_PROFILE_CREATED,
                COMPANY_TAX_PROFILE_UPDATED,
            )
            event_code = (
                COMPANY_TAX_PROFILE_CREATED if is_new else COMPANY_TAX_PROFILE_UPDATED
            )
            self._record_audit(
                company_id,
                event_code,
                "CompanyTaxProfile",
                company_id,
                "Created company tax profile" if is_new else "Updated company tax profile",
            )

            return self._to_dto(profile)

    # ------------------------------------------------------------------
    # Validation / normalization
    # ------------------------------------------------------------------

    def _normalize_command(
        self, command: UpsertCompanyTaxProfileCommand
    ) -> UpsertCompanyTaxProfileCommand:
        niu = self._normalize_text(command.niu, "NIU", _NIU_MAX_LEN)
        tax_center_code = self._normalize_code(
            command.tax_center_code, "Tax center code"
        )
        taxpayer_segment_code = self._normalize_enum(
            command.taxpayer_segment_code,
            "Taxpayer segment",
            ALL_TAXPAYER_SEGMENT_CODES,
        )
        tax_regime_code = self._normalize_enum(
            command.tax_regime_code, "Tax regime", ALL_TAX_REGIME_CODES
        )

        is_vat_liable = bool(command.is_vat_liable)
        vat_effective_from = command.vat_effective_from
        if is_vat_liable and vat_effective_from is None:
            raise ValidationError(
                "VAT effective-from date is required when the company is VAT liable.",
            )
        if not is_vat_liable and vat_effective_from is not None:
            # Keep the date for historical record; do not error. This
            # matches the reality of a company de-registering from VAT
            # while still wanting to preserve when liability started.
            pass

        cit_rate_profile_code = self._normalize_enum(
            command.cit_rate_profile_code,
            "CIT rate profile",
            ALL_CIT_RATE_PROFILE_CODES,
        )
        cit_installment_profile_code = self._normalize_code(
            command.cit_installment_profile_code, "CIT installment profile"
        )

        dsf_form_code = self._normalize_enum(
            command.dsf_form_code, "DSF form", ALL_DSF_FORM_CODES
        )
        dsf_submission_mode_code = self._normalize_enum(
            command.dsf_submission_mode_code,
            "DSF submission mode",
            ALL_DSF_SUBMISSION_MODES,
        )

        return UpsertCompanyTaxProfileCommand(
            niu=niu,
            tax_center_code=tax_center_code,
            taxpayer_segment_code=taxpayer_segment_code,
            tax_regime_code=tax_regime_code,
            is_vat_liable=is_vat_liable,
            vat_effective_from=vat_effective_from,
            vat_uses_tax_point=bool(command.vat_uses_tax_point),
            vat_accounting_basis=self._normalize_enum(
                getattr(command, "vat_accounting_basis", None) or VAT_BASIS_ACCRUAL,
                "VAT accounting basis",
                ALL_VAT_ACCOUNTING_BASIS_CODES,
            ) or VAT_BASIS_ACCRUAL,
            vat_pro_rata_percent=self._validate_pro_rata(
                getattr(command, "vat_pro_rata_percent", None)
            ),
            cit_rate_profile_code=cit_rate_profile_code,
            cit_installment_profile_code=cit_installment_profile_code,
            sme_qualified_flag=bool(command.sme_qualified_flag),
            dsf_form_code=dsf_form_code,
            dsf_submission_mode_code=dsf_submission_mode_code,
            otp_enabled_flag=bool(command.otp_enabled_flag),
            default_withholding_applicable_flag=bool(
                command.default_withholding_applicable_flag
            ),
        )

    @staticmethod
    def _normalize_text(value: str | None, label: str, max_len: int) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > max_len:
            raise ValidationError(f"{label} is too long (max {max_len} characters).")
        return normalized

    @staticmethod
    def _normalize_code(value: str | None, label: str) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            return None
        if len(normalized) > _CODE_MAX_LEN:
            raise ValidationError(
                f"{label} is too long (max {_CODE_MAX_LEN} characters)."
            )
        return normalized

    @classmethod
    def _normalize_enum(
        cls,
        value: str | None,
        label: str,
        allowed: frozenset[str],
    ) -> str | None:
        normalized = cls._normalize_code(value, label)
        if normalized is None:
            return None
        if normalized not in allowed:
            raise ValidationError(f"{label} is not a recognized value.")
        return normalized

    @staticmethod
    def _validate_pro_rata(value: float | None) -> float | None:
        """Validate pro-rata percent is in [0, 100] or None (= 100%)."""
        if value is None:
            return None
        pct = float(value)
        if pct < 0 or pct > 100:
            raise ValidationError(
                "VAT pro-rata percentage must be between 0 and 100."
            )
        return pct

    @staticmethod
    def _apply_command(
        profile: CompanyTaxProfile, command: UpsertCompanyTaxProfileCommand
    ) -> None:
        profile.niu = command.niu
        profile.tax_center_code = command.tax_center_code
        profile.taxpayer_segment_code = command.taxpayer_segment_code
        profile.tax_regime_code = command.tax_regime_code
        profile.is_vat_liable = command.is_vat_liable
        profile.vat_effective_from = command.vat_effective_from
        profile.vat_uses_tax_point = bool(command.vat_uses_tax_point)
        profile.cit_rate_profile_code = command.cit_rate_profile_code
        profile.cit_installment_profile_code = command.cit_installment_profile_code
        profile.sme_qualified_flag = command.sme_qualified_flag
        profile.dsf_form_code = command.dsf_form_code
        profile.dsf_submission_mode_code = command.dsf_submission_mode_code
        profile.otp_enabled_flag = command.otp_enabled_flag
        profile.default_withholding_applicable_flag = (
            command.default_withholding_applicable_flag
        )
        profile.vat_accounting_basis = getattr(
            command, "vat_accounting_basis", VAT_BASIS_ACCRUAL
        ) or VAT_BASIS_ACCRUAL
        profile.vat_pro_rata_percent = getattr(command, "vat_pro_rata_percent", None)

    # ------------------------------------------------------------------
    # DTO mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dto(profile: CompanyTaxProfile) -> CompanyTaxProfileDTO:
        return CompanyTaxProfileDTO(
            company_id=profile.company_id,
            exists=True,
            niu=profile.niu,
            tax_center_code=profile.tax_center_code,
            taxpayer_segment_code=profile.taxpayer_segment_code,
            tax_regime_code=profile.tax_regime_code,
            is_vat_liable=profile.is_vat_liable,
            vat_effective_from=profile.vat_effective_from,
            vat_uses_tax_point=profile.vat_uses_tax_point,
            vat_accounting_basis=getattr(profile, "vat_accounting_basis", VAT_BASIS_ACCRUAL) or VAT_BASIS_ACCRUAL,
            vat_pro_rata_percent=(
                float(profile.vat_pro_rata_percent)
                if profile.vat_pro_rata_percent is not None
                else None
            ),
            cit_rate_profile_code=profile.cit_rate_profile_code,
            cit_installment_profile_code=profile.cit_installment_profile_code,
            sme_qualified_flag=profile.sme_qualified_flag,
            dsf_form_code=profile.dsf_form_code,
            dsf_submission_mode_code=profile.dsf_submission_mode_code,
            otp_enabled_flag=profile.otp_enabled_flag,
            default_withholding_applicable_flag=profile.default_withholding_applicable_flag,
            updated_by_user_id=profile.updated_by_user_id,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    @staticmethod
    def _default_dto(company_id: int) -> CompanyTaxProfileDTO:
        return CompanyTaxProfileDTO(
            company_id=company_id,
            exists=False,
            niu=None,
            tax_center_code=None,
            taxpayer_segment_code=None,
            tax_regime_code=None,
            is_vat_liable=False,
            vat_effective_from=None,
            vat_uses_tax_point=False,
            vat_accounting_basis=VAT_BASIS_ACCRUAL,
            vat_pro_rata_percent=None,
            cit_rate_profile_code=None,
            cit_installment_profile_code=None,
            sme_qualified_flag=False,
            dsf_form_code=None,
            dsf_submission_mode_code=None,
            otp_enabled_flag=False,
            default_withholding_applicable_flag=False,
            updated_by_user_id=None,
            created_at=None,
            updated_at=None,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        company_repo = self._company_repository_factory(session)
        company = company_repo.get_by_id(company_id)
        if company is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
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
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            # Audit must not break business operations.
            pass
