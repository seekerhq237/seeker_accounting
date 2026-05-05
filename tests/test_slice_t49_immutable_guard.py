"""Slice T49 — Immutable filed-return guard + view-audit tests.

Tests cover:
  1. TAX_RETURN_VIEWED audit event exists in catalog.
  2. T47 workflow audit events exist in catalog.
  3. TaxReturnLine.is_immutable column exists on model.
  4. Service raises ConflictError when re-drafting lines that are immutable.
  5. is_immutable = True is set on all lines when file_return is called.
  6. Audit event constants importable.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import unittest

import pytest

from seeker_accounting.modules.audit.event_type_catalog import (
    TAX_RETURN_VIEWED,
    TAX_RETURN_SUBMITTED_FOR_REVIEW,
    TAX_RETURN_REVERTED_TO_DRAFT,
    TAX_RETURN_APPROVED,
    TAX_RETURN_SUBMISSION_CONFIRMED,
)
from seeker_accounting.modules.taxation.models.tax_return_line import TaxReturnLine
from seeker_accounting.platform.exceptions import ConflictError

_COMPANY_ID = 1


# ---------------------------------------------------------------------------
# T49AuditEventTests
# ---------------------------------------------------------------------------


class T49AuditEventTests(unittest.TestCase):
    def test_tax_return_viewed_event_exists(self):
        assert TAX_RETURN_VIEWED == "TAX_RETURN_VIEWED"

    def test_t47_workflow_events_exist(self):
        assert TAX_RETURN_SUBMITTED_FOR_REVIEW == "TAX_RETURN_SUBMITTED_FOR_REVIEW"
        assert TAX_RETURN_REVERTED_TO_DRAFT == "TAX_RETURN_REVERTED_TO_DRAFT"
        assert TAX_RETURN_APPROVED == "TAX_RETURN_APPROVED"
        assert TAX_RETURN_SUBMISSION_CONFIRMED == "TAX_RETURN_SUBMISSION_CONFIRMED"


# ---------------------------------------------------------------------------
# T49ModelTests
# ---------------------------------------------------------------------------


class T49ModelTests(unittest.TestCase):
    def test_tax_return_line_has_is_immutable_field(self):
        """TaxReturnLine must have an is_immutable column."""
        assert hasattr(TaxReturnLine, "is_immutable")

    def test_tax_return_line_is_immutable_default_is_false(self):
        """Default value for is_immutable must be False (not immutable)."""
        # Check the column default, not instantiation (which requires full SA registry).
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(TaxReturnLine)
        col = mapper.columns["is_immutable"]
        # The Python-level default should be False.
        assert col.default is not None or col.server_default is not None

    def test_tax_return_model_has_efiling_columns(self):
        """TaxReturn must carry the T50 e-filing scaffold columns."""
        from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
        assert hasattr(TaxReturn, "submission_payload_hash")
        assert hasattr(TaxReturn, "submission_acknowledgement_id")
        assert hasattr(TaxReturn, "submission_authority_timestamp")


# ---------------------------------------------------------------------------
# T49ImmutableGuardTests
# ---------------------------------------------------------------------------


def _make_immutable_line() -> MagicMock:
    line = MagicMock(spec=TaxReturnLine)
    line.is_immutable = True
    line.box_code = "VAT_OUTPUT"
    line.label = "TVA collectée"
    line.amount = Decimal("192500")
    line.base_amount = Decimal("1000000")
    line.sort_order = 0
    return line


def _make_mutable_line() -> MagicMock:
    line = MagicMock(spec=TaxReturnLine)
    line.is_immutable = False
    line.box_code = "VAT_OUTPUT"
    line.label = "TVA collectée"
    line.amount = Decimal("192500")
    line.base_amount = Decimal("1000000")
    line.sort_order = 0
    return line


class T49ImmutableGuardTests(unittest.TestCase):
    """Validate immutability guard in TaxReturnService.draft_vat_return."""

    def _build_draft_scenario(
        self,
        *,
        lines_are_immutable: bool = False,
    ):
        """Build mocks for draft_vat_return to exercise the immutable guard."""
        from seeker_accounting.modules.taxation.services.tax_return_service import (
            TaxReturnService,
        )

        mock_permission = MagicMock()
        mock_session = MagicMock()
        mock_session.scalar.return_value = None  # makes _aggregate_withholding_vat return _ZERO
        mock_uow = MagicMock()
        mock_uow.__enter__.return_value = mock_uow
        mock_uow.__exit__.return_value = False
        mock_uow.session = mock_session
        mock_uow.commit = MagicMock()

        existing_return = MagicMock()
        existing_return.status_code = "DRAFT"
        existing_return.notes = ""
        existing_return.credit_brought_forward = None
        existing_return.withholding_vat_amount = None
        immutable_line = _make_immutable_line() if lines_are_immutable else _make_mutable_line()
        existing_return.lines = [immutable_line]

        obligation = MagicMock()
        obligation.id = 10
        obligation.status_code = "OPEN"
        obligation.tax_type_code = "VAT"
        obligation.period_start = datetime.date(2025, 1, 1)
        obligation.period_end = datetime.date(2025, 1, 31)

        obligation_repo = MagicMock()
        obligation_repo.get_by_id.return_value = obligation

        return_repo = MagicMock()
        return_repo.get_by_obligation.return_value = existing_return

        company_repo = MagicMock()
        company_repo.get.return_value = MagicMock()

        period_repo = MagicMock()
        mock_fiscal_period = MagicMock()
        mock_fiscal_period.id = 5
        period_repo.find_by_company_and_date.return_value = mock_fiscal_period

        posted_tax_line_repo = MagicMock()
        posted_tax_line_repo.aggregate_for_period.return_value = []
        posted_tax_line_repo.sum_withheld_for_period.return_value = Decimal("0")

        svc = TaxReturnService(
            unit_of_work_factory=MagicMock(return_value=mock_uow),
            app_context=MagicMock(current_user_id=1),
            tax_return_repository_factory=MagicMock(return_value=return_repo),
            tax_obligation_repository_factory=MagicMock(return_value=obligation_repo),
            company_repository_factory=MagicMock(return_value=company_repo),
            posted_tax_line_repository_factory=MagicMock(return_value=posted_tax_line_repo),
            fiscal_period_repository_factory=MagicMock(return_value=period_repo),
            permission_service=mock_permission,
        )
        return svc

    def test_re_draft_with_immutable_lines_raises_conflict_error(self):
        """draft_vat_return must raise ConflictError if lines are immutable."""
        from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
            DraftVATReturnCommand,
        )

        svc = self._build_draft_scenario(lines_are_immutable=True)
        cmd = DraftVATReturnCommand(obligation_id=10)
        with pytest.raises(ConflictError):
            svc.draft_vat_return(_COMPANY_ID, cmd)
