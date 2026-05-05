"""Slice T43 tests — VAT period locks.

Validates:
* VatPeriodLock model can be instantiated and persisted.
* VatPeriodLockRepository: is_locked() correctly finds/misses based on date ranges.
* VatPeriodLockRepository: find_by_period() returns exact-match or None.
* VatPeriodLockRepository: list_by_company() filters by tax_type_code.
* VATPeriodLockService.lock_period() creates a lock and returns a DTO.
* VATPeriodLockService.lock_period() is idempotent (returns existing).
* VATPeriodLockService.unlock_period() removes the lock.
* VATPeriodLockService.unlock_period() raises NotFoundError if no lock.
* VATPeriodLockService.is_period_locked() delegates to the repo correctly.
* TaxReturnService.file_return() creates an auto-lock via the repo.
"""
from __future__ import annotations

import datetime
import unittest
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db import model_registry  # noqa: F401 — registers all tables
from seeker_accounting.db.base import Base
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.taxation.models.vat_period_lock import VatPeriodLock
from seeker_accounting.modules.taxation.repositories.vat_period_lock_repository import (
    VatPeriodLockRepository,
)
from seeker_accounting.modules.taxation.services.vat_period_lock_service import (
    VATPeriodLockService,
    VatPeriodLockDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError


# ─── In-memory DB helpers ──────────────────────────────────────────────────────


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    return SF()


def _seed_company(session: Session) -> int:
    company = Company(
        legal_name="Lock Test Co",
        display_name="LTC",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()
    return company.id


# ─── Model tests ──────────────────────────────────────────────────────────────


class VatPeriodLockModelTests(unittest.TestCase):
    def test_model_has_required_columns(self) -> None:
        lock = VatPeriodLock(
            company_id=1,
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 1, 31),
            tax_type_code="VAT",
            locked_at=datetime.datetime(2026, 2, 1, 10, 0, 0),
        )
        self.assertEqual(lock.company_id, 1)
        self.assertEqual(lock.tax_type_code, "VAT")
        self.assertIsNone(lock.return_id)
        self.assertIsNone(lock.notes)

    def test_model_table_name(self) -> None:
        self.assertEqual(VatPeriodLock.__tablename__, "vat_period_locks")


# ─── Repository tests ─────────────────────────────────────────────────────────


class VatPeriodLockRepositoryTests(unittest.TestCase):

    def setUp(self) -> None:
        self.session = _make_session()
        self.company_id = _seed_company(self.session)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def _add_lock(
        self,
        period_start: datetime.date,
        period_end: datetime.date,
        tax_type_code: str = "VAT",
    ) -> VatPeriodLock:
        lock = VatPeriodLock(
            company_id=self.company_id,
            period_start=period_start,
            period_end=period_end,
            tax_type_code=tax_type_code,
            locked_at=datetime.datetime.utcnow(),
        )
        self.session.add(lock)
        self.session.commit()
        return lock

    # is_locked

    def test_is_locked_returns_true_for_date_within_period(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        repo = VatPeriodLockRepository(self.session)
        self.assertTrue(repo.is_locked(self.company_id, datetime.date(2026, 1, 15)))

    def test_is_locked_returns_true_for_period_start_date(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        repo = VatPeriodLockRepository(self.session)
        self.assertTrue(repo.is_locked(self.company_id, datetime.date(2026, 1, 1)))

    def test_is_locked_returns_true_for_period_end_date(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        repo = VatPeriodLockRepository(self.session)
        self.assertTrue(repo.is_locked(self.company_id, datetime.date(2026, 1, 31)))

    def test_is_locked_returns_false_for_date_before_period(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        repo = VatPeriodLockRepository(self.session)
        self.assertFalse(repo.is_locked(self.company_id, datetime.date(2025, 12, 31)))

    def test_is_locked_returns_false_for_date_after_period(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        repo = VatPeriodLockRepository(self.session)
        self.assertFalse(repo.is_locked(self.company_id, datetime.date(2026, 2, 1)))

    def test_is_locked_ignores_different_company(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        repo = VatPeriodLockRepository(self.session)
        self.assertFalse(repo.is_locked(99999, datetime.date(2026, 1, 15)))

    def test_is_locked_filters_by_tax_type_code(self) -> None:
        self._add_lock(
            datetime.date(2026, 1, 1), datetime.date(2026, 1, 31), tax_type_code="WHT"
        )
        repo = VatPeriodLockRepository(self.session)
        # VAT lock does not exist — should return False
        self.assertFalse(repo.is_locked(self.company_id, datetime.date(2026, 1, 15), "VAT"))
        # WHT lock exists
        self.assertTrue(repo.is_locked(self.company_id, datetime.date(2026, 1, 15), "WHT"))

    # find_by_period

    def test_find_by_period_returns_lock_when_exists(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        repo = VatPeriodLockRepository(self.session)
        found = repo.find_by_period(
            self.company_id, datetime.date(2026, 1, 1), datetime.date(2026, 1, 31)
        )
        self.assertIsNotNone(found)
        self.assertEqual(found.period_start, datetime.date(2026, 1, 1))

    def test_find_by_period_returns_none_when_missing(self) -> None:
        repo = VatPeriodLockRepository(self.session)
        found = repo.find_by_period(
            self.company_id, datetime.date(2026, 1, 1), datetime.date(2026, 1, 31)
        )
        self.assertIsNone(found)

    # list_by_company

    def test_list_by_company_returns_all_locks(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        self._add_lock(datetime.date(2026, 2, 1), datetime.date(2026, 2, 28))
        repo = VatPeriodLockRepository(self.session)
        locks = repo.list_by_company(self.company_id)
        self.assertEqual(len(locks), 2)

    def test_list_by_company_filters_by_tax_type_code(self) -> None:
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31), "VAT")
        self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31), "WHT")
        repo = VatPeriodLockRepository(self.session)
        vat_locks = repo.list_by_company(self.company_id, tax_type_code="VAT")
        self.assertEqual(len(vat_locks), 1)
        self.assertEqual(vat_locks[0].tax_type_code, "VAT")

    # delete

    def test_delete_removes_lock(self) -> None:
        lock = self._add_lock(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        repo = VatPeriodLockRepository(self.session)
        repo.delete(lock)
        self.session.commit()
        remaining = repo.list_by_company(self.company_id)
        self.assertEqual(len(remaining), 0)


# ─── Service tests (unit — mock UoW) ──────────────────────────────────────────


@dataclass
class _StubAppContext:
    current_user_id: int = 99


class _AllGrantedPermService:
    def require_permission(self, code: str) -> None:
        pass

    def has_permission(self, code: str) -> bool:
        return True


class _DenyPermService:
    def require_permission(self, code: str) -> None:
        from seeker_accounting.platform.exceptions import PermissionDeniedError
        raise PermissionDeniedError(f"Denied: {code}")

    def has_permission(self, code: str) -> bool:
        return False


def _build_service_with_real_db(
    session: Session,
    perm_service=None,
) -> VATPeriodLockService:
    """Build a VATPeriodLockService backed by a real in-memory session."""
    from contextlib import contextmanager

    @contextmanager
    def _uow_factory():
        class _UoW:
            def __init__(self):
                self.session = session

            def commit(self):
                session.commit()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        yield _UoW()

    def _company_repo_factory(s: Session):
        from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
        return CompanyRepository(s)

    def _lock_repo_factory(s: Session):
        return VatPeriodLockRepository(s)

    return VATPeriodLockService(
        unit_of_work_factory=_uow_factory,
        app_context=_StubAppContext(),
        company_repository_factory=_company_repo_factory,
        vat_period_lock_repository_factory=_lock_repo_factory,
        permission_service=perm_service or _AllGrantedPermService(),
    )


class VATPeriodLockServiceTests(unittest.TestCase):

    def setUp(self) -> None:
        self.session = _make_session()
        self.company_id = _seed_company(self.session)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_lock_period_creates_lock_and_returns_dto(self) -> None:
        svc = _build_service_with_real_db(self.session)
        dto = svc.lock_period(
            self.company_id,
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        self.assertIsInstance(dto, VatPeriodLockDTO)
        self.assertEqual(dto.company_id, self.company_id)
        self.assertEqual(dto.period_start, datetime.date(2026, 1, 1))
        self.assertEqual(dto.period_end, datetime.date(2026, 1, 31))
        self.assertEqual(dto.tax_type_code, "VAT")

    def test_lock_period_is_idempotent(self) -> None:
        svc = _build_service_with_real_db(self.session)
        dto1 = svc.lock_period(
            self.company_id,
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        dto2 = svc.lock_period(
            self.company_id,
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        self.assertEqual(dto1.id, dto2.id)

    def test_unlock_period_removes_lock(self) -> None:
        svc = _build_service_with_real_db(self.session)
        svc.lock_period(
            self.company_id,
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        svc.unlock_period(
            self.company_id,
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        repo = VatPeriodLockRepository(self.session)
        found = repo.find_by_period(
            self.company_id, datetime.date(2026, 1, 1), datetime.date(2026, 1, 31)
        )
        self.assertIsNone(found)

    def test_unlock_period_raises_not_found_when_no_lock(self) -> None:
        svc = _build_service_with_real_db(self.session)
        with self.assertRaises(NotFoundError):
            svc.unlock_period(
                self.company_id,
                datetime.date(2026, 1, 1),
                datetime.date(2026, 1, 31),
            )

    def test_is_period_locked_returns_true_when_locked(self) -> None:
        svc = _build_service_with_real_db(self.session)
        svc.lock_period(
            self.company_id,
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        self.assertTrue(svc.is_period_locked(self.company_id, datetime.date(2026, 1, 15)))

    def test_is_period_locked_returns_false_when_not_locked(self) -> None:
        svc = _build_service_with_real_db(self.session)
        self.assertFalse(svc.is_period_locked(self.company_id, datetime.date(2026, 1, 15)))

    def test_list_locks_returns_dtos(self) -> None:
        svc = _build_service_with_real_db(self.session)
        svc.lock_period(
            self.company_id,
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        svc.lock_period(
            self.company_id,
            datetime.date(2026, 2, 1),
            datetime.date(2026, 2, 28),
        )
        locks = svc.list_locks(self.company_id)
        self.assertEqual(len(locks), 2)
        for lock in locks:
            self.assertIsInstance(lock, VatPeriodLockDTO)

    def test_lock_period_unknown_company_raises_not_found(self) -> None:
        svc = _build_service_with_real_db(self.session)
        with self.assertRaises(NotFoundError):
            svc.lock_period(
                99999,
                datetime.date(2026, 1, 1),
                datetime.date(2026, 1, 31),
            )

    def test_lock_period_requires_manage_permission(self) -> None:
        from seeker_accounting.platform.exceptions import PermissionDeniedError
        svc = _build_service_with_real_db(self.session, perm_service=_DenyPermService())
        with self.assertRaises(PermissionDeniedError):
            svc.lock_period(
                self.company_id,
                datetime.date(2026, 1, 1),
                datetime.date(2026, 1, 31),
            )

    def test_unlock_period_requires_unlock_permission(self) -> None:
        # First lock with a privileged service, then try to unlock with denied service.
        priv_svc = _build_service_with_real_db(self.session)
        priv_svc.lock_period(
            self.company_id,
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        from seeker_accounting.platform.exceptions import PermissionDeniedError
        deny_svc = _build_service_with_real_db(self.session, perm_service=_DenyPermService())
        with self.assertRaises(PermissionDeniedError):
            deny_svc.unlock_period(
                self.company_id,
                datetime.date(2026, 1, 1),
                datetime.date(2026, 1, 31),
            )


# ─── TaxReturnService auto-lock integration (unit — mock repo) ────────────────


class TaxReturnServiceAutoLockTests(unittest.TestCase):
    """Verify that file_return() creates an auto-lock via the lock repo."""

    def _build_mock_lock_repo(self):
        repo = MagicMock()
        repo.find_by_period.return_value = None  # no existing lock
        return repo

    def test_file_return_calls_add_on_lock_repo(self) -> None:
        """When vat_period_lock_repository_factory is wired, filing auto-locks."""
        from seeker_accounting.modules.taxation.services.tax_return_service import TaxReturnService
        from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
        from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
        from seeker_accounting.modules.taxation.constants import (
            RETURN_STATUS_DRAFT,
            RETURN_STATUS_FILED,
            TAX_TYPE_VAT,
        )

        # Build a stub return in DRAFT state
        stub_return = MagicMock(spec=TaxReturn)
        stub_return.id = 42
        stub_return.status_code = RETURN_STATUS_DRAFT
        stub_return.tax_type_code = TAX_TYPE_VAT
        stub_return.period_start = datetime.date(2026, 1, 1)
        stub_return.period_end = datetime.date(2026, 1, 31)
        stub_return.total_due_amount = Decimal("150000")

        stub_return_repo = MagicMock()
        stub_return_repo.get_by_id.return_value = stub_return

        lock_repo = self._build_mock_lock_repo()
        lock_repo_factory = MagicMock(return_value=lock_repo)

        uow = MagicMock()
        uow.session = MagicMock()
        uow.__enter__ = MagicMock(return_value=uow)
        uow.__exit__ = MagicMock(return_value=False)

        # Stub all repo factories
        svc = TaxReturnService(
            unit_of_work_factory=lambda: uow,
            app_context=_StubAppContext(),
            tax_return_repository_factory=lambda s: stub_return_repo,
            tax_obligation_repository_factory=lambda s: MagicMock(),
            posted_tax_line_repository_factory=lambda s: MagicMock(),
            fiscal_period_repository_factory=lambda s: MagicMock(),
            company_repository_factory=lambda s: MagicMock(
                **{"get_by_id.return_value": MagicMock()}
            ),
            permission_service=_AllGrantedPermService(),
            vat_period_lock_repository_factory=lock_repo_factory,
        )

        from seeker_accounting.modules.taxation.dto.tax_compliance_dto import FileTaxReturnCommand
        cmd = FileTaxReturnCommand(return_id=42)
        svc.file_return(self.company_id, cmd)
        lock_repo.add.assert_called_once()

    @property
    def company_id(self) -> int:
        return 1

    def test_file_return_no_lock_when_factory_not_provided(self) -> None:
        """Without the factory, filing does not attempt to create a lock."""
        from seeker_accounting.modules.taxation.services.tax_return_service import TaxReturnService
        from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
        from seeker_accounting.modules.taxation.constants import (
            RETURN_STATUS_DRAFT,
            TAX_TYPE_VAT,
        )

        stub_return = MagicMock(spec=TaxReturn)
        stub_return.id = 42
        stub_return.status_code = RETURN_STATUS_DRAFT
        stub_return.tax_type_code = TAX_TYPE_VAT
        stub_return.period_start = datetime.date(2026, 1, 1)
        stub_return.period_end = datetime.date(2026, 1, 31)
        stub_return.total_due_amount = Decimal("0")

        stub_return_repo = MagicMock()
        stub_return_repo.get_by_id.return_value = stub_return

        uow = MagicMock()
        uow.session = MagicMock()
        uow.__enter__ = MagicMock(return_value=uow)
        uow.__exit__ = MagicMock(return_value=False)

        svc = TaxReturnService(
            unit_of_work_factory=lambda: uow,
            app_context=_StubAppContext(),
            tax_return_repository_factory=lambda s: stub_return_repo,
            tax_obligation_repository_factory=lambda s: MagicMock(),
            posted_tax_line_repository_factory=lambda s: MagicMock(),
            fiscal_period_repository_factory=lambda s: MagicMock(),
            company_repository_factory=lambda s: MagicMock(
                **{"get_by_id.return_value": MagicMock()}
            ),
            permission_service=_AllGrantedPermService(),
            # vat_period_lock_repository_factory intentionally omitted
        )

        # Should not raise; auto-lock block is skipped
        from seeker_accounting.modules.taxation.dto.tax_compliance_dto import FileTaxReturnCommand
        svc.file_return(1, FileTaxReturnCommand(return_id=42))


if __name__ == "__main__":
    unittest.main()
