"""Tax audit trail service (T23).

Thin facade over :class:`AuditService` that scopes events to the
taxation module and gates with a dedicated taxation-audit
permission. Keeps UI surfaces from reaching directly into the audit
module's permission catalog.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.audit.dto.audit_event_dto import AuditEventDTO
from seeker_accounting.modules.audit.event_type_catalog import MODULE_TAXATION
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    TaxAuditFilterDTO,
)
from seeker_accounting.platform.exceptions import ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService


class TaxAuditTrailService:
    PERMISSION_VIEW = "taxation.audit.view"

    MAX_LIMIT = 1000

    def __init__(
        self,
        audit_service: "AuditService",
        permission_service: PermissionService,
    ) -> None:
        self._audit_service = audit_service
        self._permission_service = permission_service

    def list_events(self, filter_dto: TaxAuditFilterDTO) -> list[AuditEventDTO]:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        if filter_dto.limit <= 0 or filter_dto.limit > self.MAX_LIMIT:
            raise ValidationError(
                f"Limit must be between 1 and {self.MAX_LIMIT}."
            )
        if filter_dto.offset < 0:
            raise ValidationError("Offset must be non-negative.")
        if (
            filter_dto.from_date is not None
            and filter_dto.to_date is not None
            and filter_dto.from_date > filter_dto.to_date
        ):
            raise ValidationError("from_date must be on or before to_date.")

        return self._audit_service.list_events(
            filter_dto.company_id,
            module_code=MODULE_TAXATION,
            event_type_code=filter_dto.event_type_code,
            entity_type=filter_dto.entity_type,
            entity_id=filter_dto.entity_id,
            actor_user_id=filter_dto.actor_user_id,
            from_date=filter_dto.from_date,
            to_date=filter_dto.to_date,
            limit=filter_dto.limit,
            offset=filter_dto.offset,
        )


# Re-export for ergonomics
__all__ = ["TaxAuditTrailService"]
