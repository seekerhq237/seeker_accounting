from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry
    from seeker_accounting.platform.exceptions.error_resolution import ResumeTokenPayload

from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver
from seeker_accounting.shared.ui.guided_resolution_coordinator import GuidedResolutionCoordinator


def ensure_sequence_available(
    service_registry: ServiceRegistry,
    company_id: int,
    document_type_code: str,
) -> None:
    """Raise ``ValidationError(MISSING_DOCUMENT_SEQUENCE)`` if no active sequence is configured.

    Pure service-level check — no UI dependency.  Callers that need guided UI handling
    should either use :func:`run_document_sequence_preflight` (for preflight entry guards)
    or :func:`handle_document_sequence_error` (for post-handler exception routing).

    The document_type_code should be in lowercase (e.g. "sales_invoice").
    """
    service_registry.numbering_setup_service.check_sequence_available(
        company_id, document_type_code
    )


def consume_resume_payload_for_workflows(
    *,
    context: Mapping[str, object],
    service_registry: ServiceRegistry,
    allowed_workflow_keys: Iterable[str],
) -> ResumeTokenPayload | None:
    """Return a single-use resume payload when token/key validation succeeds.

    The token is only consumed after a successful workflow-key check to avoid
    dropping tokens meant for other workflows.
    """
    resume_token = context.get("resume_token")
    if not isinstance(resume_token, str) or not resume_token:
        return None

    workflow_keys = set(allowed_workflow_keys)
    token_payload = service_registry.workflow_resume_service.peek_token(resume_token)
    if token_payload is None or token_payload.workflow_key not in workflow_keys:
        return None

    return service_registry.workflow_resume_service.consume_token(resume_token)


def handle_document_sequence_error(
    page: QWidget,
    service_registry: ServiceRegistry,
    exc: ValidationError,
    workflow_key: str,
    workflow_snapshot,
    origin_nav_id: str,
    company_name: str,
) -> None:
    """Route a MISSING_DOCUMENT_SEQUENCE ValidationError through the guided coordinator.

    This is the single place where GuidedResolutionCoordinator is wired for document-sequence
    errors.  Post handlers should catch the exception, check the code, then delegate here.
    """
    coordinator = GuidedResolutionCoordinator(
        resolver=ErrorResolutionResolver(),
        workflow_resume_service=service_registry.workflow_resume_service,
        navigation_service=service_registry.navigation_service,
    )
    coordinator.handle_exception(
        parent=page,
        error=exc,
        workflow_key=workflow_key,
        workflow_snapshot=workflow_snapshot,
        origin_nav_id=origin_nav_id,
        resolution_context={"company_name": company_name},
    )


def run_document_sequence_preflight(
    page: QWidget,
    service_registry: ServiceRegistry,
    company_id: int,
    company_name: str,
    document_type_code: str,
    origin_nav_id: str,
    workflow_key: str | None = None,
) -> bool:
    """Check that an active document sequence exists before opening a create workflow.

    Returns True when the sequence is present and the caller should proceed.
    Returns False when a guided blocker was shown; the caller should abort.

    Delegates to :func:`ensure_sequence_available` for the service check and
    :func:`handle_document_sequence_error` for the guided UI response.

    The document_type_code should be in lowercase (e.g. "sales_invoice").
    """
    try:
        ensure_sequence_available(service_registry, company_id, document_type_code)
        return True
    except ValidationError as exc:
        if exc.app_error_code != AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
            raise
        effective_key = workflow_key or f"{document_type_code.lower()}.preflight"
        handle_document_sequence_error(
            page, service_registry, exc, effective_key, {}, origin_nav_id, company_name
        )
        return False
