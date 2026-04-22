"""Payroll Output Warning Service — surfaces compliance/quality warnings for export contexts.

This service provides non-blocking, operator-facing warnings that should
appear in print/export previews and dialogs.  It reads from:
- statutory pack verification metadata (R2)
- company payroll settings
- pack registry

No new truth tables.  No blocking behavior — these are informational only.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.payroll.dto.payroll_export_dto import PayrollOutputWarningDTO
from seeker_accounting.modules.payroll.repositories.company_payroll_setting_repository import (
    CompanyPayrollSettingRepository,
)
from seeker_accounting.modules.payroll.statutory_packs import pack_registry

CompanyPayrollSettingRepositoryFactory = Callable[[Session], CompanyPayrollSettingRepository]


class PayrollOutputWarningService:
    """Gathers non-blocking warnings relevant to payroll export/print operations."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        settings_repo_factory: CompanyPayrollSettingRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._settings_repo_factory = settings_repo_factory

    def get_export_warnings(self, company_id: int) -> list[PayrollOutputWarningDTO]:
        """Return list of warnings relevant to payroll output for a company."""
        warnings: list[PayrollOutputWarningDTO] = []
        self._check_pack_verification(company_id, warnings)
        return warnings

    def _check_pack_verification(
        self,
        company_id: int,
        warnings: list[PayrollOutputWarningDTO],
    ) -> None:
        """Check if the active statutory pack has provisional or unverified items."""
        with self._uow_factory() as uow:
            settings_repo = self._settings_repo_factory(uow.session)
            settings = settings_repo.get_by_company(company_id)

        if settings is None or not settings.statutory_pack_version_code:
            warnings.append(PayrollOutputWarningDTO(
                code="NO_PACK_APPLIED",
                severity="warning",
                title="No Statutory Pack",
                message="No statutory pack has been applied. Outputs may use fallback rates.",
            ))
            return

        descriptor = pack_registry.get_pack_by_code(settings.statutory_pack_version_code)
        if descriptor is None:
            return

        pack_mod = descriptor.pack_module
        get_summary = getattr(pack_mod, "get_pack_verification_summary", None)
        if get_summary is None:
            return

        summary = get_summary()
        unverified = summary.get("unverified", 0)
        provisional = summary.get("provisional", 0)

        if unverified > 0:
            warnings.append(PayrollOutputWarningDTO(
                code="PACK_UNVERIFIED_ITEMS",
                severity="warning",
                title="Unverified Statutory Items",
                message=(
                    f"The active statutory pack ({descriptor.pack_code}) contains "
                    f"{unverified} unverified item(s). Confirm these against official "
                    "DGI/CNPS publications before relying on exported outputs."
                ),
            ))

        if provisional > 0:
            warnings.append(PayrollOutputWarningDTO(
                code="PACK_PROVISIONAL_ITEMS",
                severity="info",
                title="Provisional Statutory Items",
                message=(
                    f"The active pack has {provisional} provisional item(s) "
                    "(e.g. CRTV, TDL brackets). Values are consistent with known "
                    "regulations but should be confirmed against current Finance Law."
                ),
            ))
