"""VAT e-filing payload service (Slice T50).

Generates a structured XML payload ready for upload to the DGI
Cameroon e-filing portal (MECEF integration deferred — Seeker controls
the schema here, named "Seeker DGI v1").

The payload captures:

* Company identity (NIU, legal name, tax centre, regime)
* Return header (period, filing date, otp reference if any)
* Statutory box breakdown from ``TaxReturnLine`` rows

After payload generation, the SHA-256 digest of the XML is stored on
the ``tax_return`` record (``submission_payload_hash``) for
non-repudiation.  API submission is explicitly out of scope (CLAUDE.md
§2 — no fragile fintech integrations); the caller saves the bytes to
disk or presents a save dialog.

To record an authority acknowledgement after the operator manually
uploads the file to the DGI portal, call
``record_submission_acknowledgement()``.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable

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
    RETURN_STATUS_FILED,
    RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION,
    RETURN_STATUS_SUBMITTED_CONFIRMED,
)
from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (
    CompanyTaxProfileRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    pass


PERMISSION_GENERATE_EFILING: str = "taxation.returns.file"
PERMISSION_RECORD_ACK: str = "taxation.returns.confirm"

_SCHEMA_VERSION: str = "SeekerDGI_v1"
_XML_ENCODING: str = "UTF-8"


# ── DTOs ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EFilingPayloadDTO:
    """Result of a payload generation call."""

    return_id: int
    payload_xml: str
    payload_hash: str  # SHA-256 hex digest


@dataclass(frozen=True)
class RecordAcknowledgementCommand:
    """Data needed to record a portal acknowledgement."""

    return_id: int
    acknowledgement_id: str
    authority_timestamp: datetime | None = None


# ── XML builder ───────────────────────────────────────────────────────────────


def _build_xml(
    company_name: str,
    niu: str | None,
    tax_centre: str | None,
    tax_regime: str | None,
    period_start: str,
    period_end: str,
    filed_at: str,
    otp_reference: str | None,
    lines: list[dict],
) -> str:
    root = ET.Element(
        "VATReturn",
        attrib={
            "xmlns": f"urn:seeker-accounting:{_SCHEMA_VERSION}",
            "schemaVersion": _SCHEMA_VERSION,
        },
    )
    header = ET.SubElement(root, "Header")
    ET.SubElement(header, "CompanyName").text = company_name
    ET.SubElement(header, "NIU").text = niu or ""
    ET.SubElement(header, "TaxCentre").text = tax_centre or ""
    ET.SubElement(header, "TaxRegime").text = tax_regime or ""
    ET.SubElement(header, "PeriodStart").text = period_start
    ET.SubElement(header, "PeriodEnd").text = period_end
    ET.SubElement(header, "FiledAt").text = filed_at
    if otp_reference:
        ET.SubElement(header, "OTPReference").text = otp_reference

    breakdown = ET.SubElement(root, "Breakdown")
    for line in lines:
        el = ET.SubElement(breakdown, "Line")
        el.set("code", line["box_code"])
        el.set("label", line["label"])
        el.set("amount", str(line["amount"]))
        if line.get("base_amount") is not None:
            el.set("baseAmount", str(line["base_amount"]))

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


# ── Service ───────────────────────────────────────────────────────────────────


class VATEFilingPayloadService:
    """Generates e-filing XML payloads and records acknowledgements.

    The service is intentionally agnostic about where the payload ends
    up — the caller receives bytes and can write a file, open a save
    dialog, or attach it to a UI message.
    """

    PERMISSION_GENERATE_EFILING: str = PERMISSION_GENERATE_EFILING
    PERMISSION_RECORD_ACK: str = PERMISSION_RECORD_ACK

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: Callable[[Session], CompanyRepository],
        tax_return_repository_factory: Callable[[Session], TaxReturnRepository],
        permission_service: PermissionService,
        company_tax_profile_repository_factory: Callable[
            [Session], CompanyTaxProfileRepository
        ]
        | None = None,
        app_context: AppContext | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._company_repo_factory = company_repository_factory
        self._tax_return_repo_factory = tax_return_repository_factory
        self._permission_service = permission_service
        self._tax_profile_repo_factory = company_tax_profile_repository_factory
        self._app_context = app_context

    # ── Public methods ────────────────────────────────────────────────────────

    def generate_payload(
        self,
        company_id: int,
        return_id: int,
    ) -> EFilingPayloadDTO:
        """Build a Seeker DGI v1 XML payload for a filed return.

        Only filed returns (``FILED`` status) can generate a payload.
        On success, the payload hash is persisted on the return record
        and the return is transitioned to
        ``SUBMITTED_AWAITING_CONFIRMATION``.
        """
        self._permission_service.require_permission(self.PERMISSION_GENERATE_EFILING)
        with self._uow_factory() as session:
            company = self._company_repo_factory(session).get(company_id)
            if company is None:
                raise NotFoundError(f"Company {company_id} not found.")

            repo = self._tax_return_repo_factory(session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_FILED:
                raise ValidationError(
                    "Only filed returns can generate an e-filing payload. "
                    f"Current status: {tax_return.status_code}."
                )

            # Optional tax profile for NIU / tax centre.
            niu: str | None = None
            tax_centre: str | None = None
            tax_regime: str | None = None
            if self._tax_profile_repo_factory is not None:
                profile = self._tax_profile_repo_factory(session).get_by_company(
                    company_id
                )
                if profile is not None:
                    niu = getattr(profile, "niu", None) or getattr(
                        profile, "tax_identifier", None
                    )
                    tax_centre = getattr(profile, "tax_center_code", None)
                    tax_regime = getattr(profile, "tax_regime_code", None)

            lines = [
                {
                    "box_code": line.box_code,
                    "label": line.label,
                    "amount": str(line.amount),
                    "base_amount": str(line.base_amount)
                    if line.base_amount is not None
                    else None,
                }
                for line in sorted(tax_return.lines, key=lambda l: l.sort_order)
            ]

            xml_str = _build_xml(
                company_name=company.display_name,
                niu=niu,
                tax_centre=tax_centre,
                tax_regime=tax_regime,
                period_start=tax_return.period_start.isoformat(),
                period_end=tax_return.period_end.isoformat(),
                filed_at=tax_return.filed_at.isoformat()
                if tax_return.filed_at
                else "",
                otp_reference=tax_return.otp_reference,
                lines=lines,
            )

            payload_hash = hashlib.sha256(xml_str.encode(_XML_ENCODING)).hexdigest()

            # Persist hash and advance state.
            tax_return.submission_payload_hash = payload_hash
            tax_return.status_code = RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION

            session.commit()

        return EFilingPayloadDTO(
            return_id=return_id,
            payload_xml=xml_str,
            payload_hash=payload_hash,
        )

    def record_submission_acknowledgement(
        self,
        company_id: int,
        command: RecordAcknowledgementCommand,
        actor_user_id: int | None = None,
    ) -> None:
        """Record a DGI portal acknowledgement for a submitted return.

        Transitions the return from ``SUBMITTED_AWAITING_CONFIRMATION``
        to ``SUBMITTED_CONFIRMED`` and stores the acknowledgement ID
        and authority timestamp.
        """
        self._permission_service.require_permission(self.PERMISSION_RECORD_ACK)

        ack_id = (command.acknowledgement_id or "").strip()
        if not ack_id:
            raise ValidationError("Acknowledgement ID is required.")

        with self._uow_factory() as session:
            repo = self._tax_return_repo_factory(session)
            tax_return = repo.get_by_id(company_id, command.return_id)
            if tax_return is None:
                raise NotFoundError(
                    f"Tax return {command.return_id} not found."
                )
            if tax_return.status_code != RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION:
                raise ConflictError(
                    "Return is not in SUBMITTED_AWAITING_CONFIRMATION state. "
                    f"Current status: {tax_return.status_code}."
                )

            tax_return.submission_acknowledgement_id = ack_id
            tax_return.submission_authority_timestamp = (
                command.authority_timestamp or datetime.utcnow()
            )
            tax_return.status_code = RETURN_STATUS_SUBMITTED_CONFIRMED

            session.commit()
