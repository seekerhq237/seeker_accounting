from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtGui import QImageReader
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.config.settings import AppSettings
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.companies.services.company_context_service import CompanyContextService
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


@dataclass(frozen=True, slots=True)
class _PreparedLogo:
    source_path: Path
    relative_path: str
    storage_path: Path
    original_filename: str
    content_type: str
    sha256: str


class CompanyLogoService:
    _ALLOWED_SUFFIX_TO_CONTENT_TYPE = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    _MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024

    def __init__(
        self,
        settings: AppSettings,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        company_context_service: CompanyContextService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._settings = settings
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._company_context_service = company_context_service
        self._audit_service = audit_service

    def validate_logo_file(self, source_file_path: str) -> None:
        self._validate_source_path(Path(source_file_path))

    def resolve_logo_path(self, relative_path: str | None) -> Path | None:
        if not relative_path:
            return None

        base_dir = self._logo_root.resolve()
        candidate = (self._settings.runtime_paths.data / relative_path).resolve()
        try:
            candidate.relative_to(base_dir)
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    def set_logo(self, company_id: int, source_file_path: str) -> None:
        with self._unit_of_work_factory() as uow:
            if uow.session is None:
                raise RuntimeError("Unit of work has no active session.")

            company_repository = self._company_repository_factory(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")

            prepared = self._prepare_logo(Path(source_file_path), company_id)
            old_relative_path = company.logo_storage_path
            self._ensure_logo_directory()
            copied_new_file = False

            try:
                if prepared.storage_path.resolve() != prepared.source_path.resolve():
                    if not prepared.storage_path.exists():
                        shutil.copyfile(prepared.source_path, prepared.storage_path)
                        copied_new_file = True

                company_repository.set_logo_metadata(
                    company,
                    storage_path=prepared.relative_path,
                    original_filename=prepared.original_filename,
                    content_type=prepared.content_type,
                    sha256=prepared.sha256,
                    updated_at=datetime.utcnow(),
                )
                uow.commit()
            except IntegrityError as exc:
                if copied_new_file and prepared.storage_path.exists():
                    prepared.storage_path.unlink(missing_ok=True)
                raise ValidationError("Company logo metadata could not be saved.") from exc
            except OSError as exc:
                if copied_new_file and prepared.storage_path.exists():
                    prepared.storage_path.unlink(missing_ok=True)
                raise ValidationError(f"Company logo could not be stored. {exc}") from exc

        if old_relative_path and old_relative_path != prepared.relative_path:
            self._delete_managed_logo_file(old_relative_path)

        from seeker_accounting.modules.audit.event_type_catalog import COMPANY_LOGO_SET
        self._record_audit(company_id, COMPANY_LOGO_SET, "Company", company_id, f"Set logo for company id={company_id}")

        active_company = self._company_context_service.get_active_company()
        if active_company is not None and active_company.company_id == company_id:
            self._company_context_service.set_active_company(company_id)

    def clear_logo(self, company_id: int) -> None:
        old_relative_path: str | None = None
        with self._unit_of_work_factory() as uow:
            if uow.session is None:
                raise RuntimeError("Unit of work has no active session.")

            company_repository = self._company_repository_factory(uow.session)
            company = company_repository.get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company with id {company_id} was not found.")

            old_relative_path = company.logo_storage_path
            company_repository.clear_logo_metadata(company)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Company logo could not be cleared.") from exc

        if old_relative_path:
            self._delete_managed_logo_file(old_relative_path)

        from seeker_accounting.modules.audit.event_type_catalog import COMPANY_LOGO_CLEARED
        self._record_audit(company_id, COMPANY_LOGO_CLEARED, "Company", company_id, f"Cleared logo for company id={company_id}")

        active_company = self._company_context_service.get_active_company()
        if active_company is not None and active_company.company_id == company_id:
            self._company_context_service.set_active_company(company_id)

    @property
    def _logo_root(self) -> Path:
        return self._settings.runtime_paths.data / "company_logos"

    def _ensure_logo_directory(self) -> None:
        self._logo_root.mkdir(parents=True, exist_ok=True)

    def _prepare_logo(self, source_path: Path, company_id: int) -> _PreparedLogo:
        validated_source = self._validate_source_path(source_path)
        sha256 = self._hash_file(validated_source)
        suffix = validated_source.suffix.lower()
        file_name = f"company_{company_id}_{sha256[:16]}{suffix}"
        relative_path = f"company_logos/{file_name}"
        storage_path = self._settings.runtime_paths.data / relative_path
        return _PreparedLogo(
            source_path=validated_source,
            relative_path=relative_path,
            storage_path=storage_path,
            original_filename=validated_source.name,
            content_type=self._ALLOWED_SUFFIX_TO_CONTENT_TYPE[suffix],
            sha256=sha256,
        )

    def _validate_source_path(self, source_path: Path) -> Path:
        candidate = source_path.expanduser().resolve()
        if not candidate.exists() or not candidate.is_file():
            raise ValidationError("Logo file must reference an existing file.")

        suffix = candidate.suffix.lower()
        if suffix not in self._ALLOWED_SUFFIX_TO_CONTENT_TYPE:
            raise ValidationError("Logo must be a PNG, JPG, JPEG, or WEBP image.")

        if candidate.stat().st_size > self._MAX_FILE_SIZE_BYTES:
            raise ValidationError("Logo file must not exceed 2 MB.")

        image_reader = QImageReader(str(candidate))
        if not image_reader.canRead():
            raise ValidationError("Logo file must be a readable image.")

        return candidate

    def _hash_file(self, source_path: Path) -> str:
        digest = hashlib.sha256()
        with source_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _delete_managed_logo_file(self, relative_path: str) -> None:
        resolved = self.resolve_logo_path(relative_path)
        if resolved is None:
            return
        resolved.unlink(missing_ok=True)

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
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_COMPANIES
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_COMPANIES,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
