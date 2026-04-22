"""UserAvatarService — stores and retrieves user profile picture files.

Mirrors CompanyLogoService exactly, adapted for the users table.
Files are stored in: <data_root>/user_avatars/user_{user_id}_{sha256_prefix}{suffix}
"""
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
from seeker_accounting.modules.administration.repositories.user_repository import UserRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

UserRepositoryFactory = Callable[[Session], UserRepository]


@dataclass(frozen=True, slots=True)
class _PreparedAvatar:
    source_path: Path
    relative_path: str
    storage_path: Path
    original_filename: str
    content_type: str
    sha256: str


class UserAvatarService:
    _ALLOWED_SUFFIX_TO_CONTENT_TYPE = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    _MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

    def __init__(
        self,
        settings: AppSettings,
        unit_of_work_factory: UnitOfWorkFactory,
        user_repository_factory: UserRepositoryFactory,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._settings = settings
        self._unit_of_work_factory = unit_of_work_factory
        self._user_repository_factory = user_repository_factory
        self._audit_service = audit_service

    # ── Public API ──────────────────────────────────────────────────────────

    def validate_avatar_file(self, source_file_path: str) -> None:
        """Validate that the file is an acceptable avatar image. Raises ValidationError if not."""
        self._validate_source_path(Path(source_file_path))

    def resolve_avatar_path(self, relative_path: str | None) -> Path | None:
        """Return the absolute Path for a stored avatar, or None if missing/invalid."""
        if not relative_path:
            return None

        base_dir = self._avatar_root.resolve()
        candidate = (self._settings.runtime_paths.data / relative_path).resolve()
        try:
            candidate.relative_to(base_dir)
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    def set_avatar(self, user_id: int, source_file_path: str) -> None:
        """Copy source_file_path into managed storage and update user avatar metadata."""
        with self._unit_of_work_factory() as uow:
            if uow.session is None:
                raise RuntimeError("Unit of work has no active session.")

            user_repo = self._user_repository_factory(uow.session)
            user = user_repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User with id {user_id} was not found.")

            prepared = self._prepare_avatar(Path(source_file_path), user_id)
            old_relative_path = user.avatar_storage_path
            self._ensure_avatar_directory()
            copied_new_file = False

            try:
                if prepared.storage_path.resolve() != prepared.source_path.resolve():
                    if not prepared.storage_path.exists():
                        shutil.copyfile(prepared.source_path, prepared.storage_path)
                        copied_new_file = True

                user.avatar_storage_path = prepared.relative_path
                user.avatar_original_filename = prepared.original_filename
                user.avatar_content_type = prepared.content_type
                user.avatar_sha256 = prepared.sha256
                user.avatar_updated_at = datetime.utcnow()
                user_repo.save(user)
                uow.commit()
            except IntegrityError as exc:
                if copied_new_file and prepared.storage_path.exists():
                    prepared.storage_path.unlink(missing_ok=True)
                raise ValidationError("User avatar metadata could not be saved.") from exc
            except OSError as exc:
                if copied_new_file and prepared.storage_path.exists():
                    prepared.storage_path.unlink(missing_ok=True)
                raise ValidationError(f"User avatar could not be stored. {exc}") from exc

        if old_relative_path and old_relative_path != prepared.relative_path:
            self._delete_managed_avatar_file(old_relative_path)
        from seeker_accounting.modules.audit.event_type_catalog import USER_AVATAR_SET
        self._record_audit(0, USER_AVATAR_SET, "User", user_id, f"Set avatar for user id={user_id}")

    def clear_avatar(self, user_id: int) -> None:
        """Remove the user's avatar from storage and clear the metadata fields."""
        old_relative_path: str | None = None
        with self._unit_of_work_factory() as uow:
            if uow.session is None:
                raise RuntimeError("Unit of work has no active session.")

            user_repo = self._user_repository_factory(uow.session)
            user = user_repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User with id {user_id} was not found.")

            old_relative_path = user.avatar_storage_path
            user.avatar_storage_path = None
            user.avatar_original_filename = None
            user.avatar_content_type = None
            user.avatar_sha256 = None
            user.avatar_updated_at = None
            user_repo.save(user)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("User avatar could not be cleared.") from exc

        if old_relative_path:
            self._delete_managed_avatar_file(old_relative_path)
        from seeker_accounting.modules.audit.event_type_catalog import USER_AVATAR_CLEARED
        self._record_audit(0, USER_AVATAR_CLEARED, "User", user_id, f"Cleared avatar for user id={user_id}")

    # ── Internal helpers ────────────────────────────────────────────────────

    @property
    def _avatar_root(self) -> Path:
        return self._settings.runtime_paths.data / "user_avatars"

    def _ensure_avatar_directory(self) -> None:
        self._avatar_root.mkdir(parents=True, exist_ok=True)

    def _prepare_avatar(self, source_path: Path, user_id: int) -> _PreparedAvatar:
        validated_source = self._validate_source_path(source_path)
        sha256 = self._hash_file(validated_source)
        suffix = validated_source.suffix.lower()
        file_name = f"user_{user_id}_{sha256[:16]}{suffix}"
        relative_path = f"user_avatars/{file_name}"
        storage_path = self._settings.runtime_paths.data / relative_path
        return _PreparedAvatar(
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
            raise ValidationError("Avatar file must reference an existing file.")

        suffix = candidate.suffix.lower()
        if suffix not in self._ALLOWED_SUFFIX_TO_CONTENT_TYPE:
            raise ValidationError("Avatar must be a PNG, JPG, JPEG, or WEBP image.")

        if candidate.stat().st_size > self._MAX_FILE_SIZE_BYTES:
            raise ValidationError("Avatar file must not exceed 2 MB.")

        image_reader = QImageReader(str(candidate))
        if not image_reader.canRead():
            raise ValidationError("Avatar file must be a readable image.")

        return candidate

    def _hash_file(self, source_path: Path) -> str:
        digest = hashlib.sha256()
        with source_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _delete_managed_avatar_file(self, relative_path: str) -> None:
        resolved = self.resolve_avatar_path(relative_path)
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_AUTH
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_AUTH,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
