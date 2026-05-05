"""Patch script: add T47 permission constants and state machine methods to TaxReturnService."""
import sys

path = "src/seeker_accounting/modules/taxation/services/tax_return_service.py"
content = open(path, "rb").read()

# --- Patch 1: add T47 permission class attributes ---
old1 = b'    PERMISSION_FILE = "taxation.returns.file"\r\n'
new1 = (
    b'    PERMISSION_FILE = "taxation.returns.file"\r\n'
    b'    # T47: 4-eye workflow permissions\r\n'
    b'    PERMISSION_REVIEW = "taxation.returns.review"\r\n'
    b'    PERMISSION_APPROVE = "taxation.returns.approve"\r\n'
    b'    PERMISSION_CONFIRM = "taxation.returns.confirm"\r\n'
)
if old1 not in content:
    print("ERROR: Patch 1 pattern not found")
    sys.exit(1)
content = content.replace(old1, new1, 1)
print("Patch 1 applied: T47 permission constants")

# --- Patch 2: add T47 state machine methods before @staticmethod def _to_dto ---
anchor = b"    @staticmethod\r\n    def _to_dto(tax_return: TaxReturn) -> TaxReturnDTO:\r\n"
if anchor not in content:
    print("ERROR: Patch 2 anchor not found")
    sys.exit(1)

T47_METHODS = b'''
    # ----------------------------- T47: state machine --------------------

    def submit_for_review(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: DRAFT -> READY_FOR_REVIEW."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_DRAFT:
                raise ValidationError(
                    f"Only DRAFT returns can be submitted for review "
                    f"(current status: {tax_return.status_code})."
                )
            tax_return.status_code = RETURN_STATUS_READY_FOR_REVIEW
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_SUBMITTED_FOR_REVIEW", return_id,
                f"Return {return_id} submitted for review.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def revert_to_draft(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: READY_FOR_REVIEW -> DRAFT (re-draft; APPROVED cannot be reverted)."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_READY_FOR_REVIEW:
                raise ValidationError(
                    "Only READY_FOR_REVIEW returns can be reverted to DRAFT. "
                    f"Cannot revert from '{tax_return.status_code}'."
                )
            tax_return.status_code = RETURN_STATUS_DRAFT
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_REVERTED_TO_DRAFT", return_id,
                f"Return {return_id} reverted to DRAFT from READY_FOR_REVIEW.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def approve_return(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: READY_FOR_REVIEW -> APPROVED."""
        self._permission_service.require_permission(self.PERMISSION_APPROVE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_READY_FOR_REVIEW:
                raise ValidationError(
                    "Only READY_FOR_REVIEW returns can be approved "
                    f"(current status: {tax_return.status_code})."
                )
            tax_return.status_code = RETURN_STATUS_APPROVED
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_APPROVED", return_id,
                f"Return {return_id} approved.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def submit_return(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: FILED -> SUBMITTED_AWAITING_CONFIRMATION."""
        self._permission_service.require_permission(self.PERMISSION_FILE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_FILED:
                raise ValidationError(
                    "Only FILED returns can be submitted to the authority "
                    f"(current status: {tax_return.status_code})."
                )
            tax_return.status_code = RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_SUBMITTED", return_id,
                f"Return {return_id} submitted to DGI - awaiting confirmation.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

    def confirm_submission(
        self,
        company_id: int,
        return_id: int,
        actor_user_id: int | None = None,
    ) -> TaxReturnDTO:
        """T47: SUBMITTED_AWAITING_CONFIRMATION -> SUBMITTED_CONFIRMED."""
        self._permission_service.require_permission(self.PERMISSION_CONFIRM)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._tax_return_repository_factory(uow.session)
            tax_return = repo.get_by_id(company_id, return_id)
            if tax_return is None:
                raise NotFoundError(f"Tax return {return_id} not found.")
            if tax_return.status_code != RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION:
                raise ValidationError(
                    "Only SUBMITTED_AWAITING_CONFIRMATION returns can be confirmed "
                    f"(current status: {tax_return.status_code})."
                )
            tax_return.status_code = RETURN_STATUS_SUBMITTED_CONFIRMED
            uow.commit()
            self._record_audit(
                company_id, "TAX_RETURN_SUBMISSION_CONFIRMED", return_id,
                f"Return {return_id} submission confirmed.",
            )
            tax_return = repo.get_by_id(company_id, return_id)  # type: ignore[assignment]
            assert tax_return is not None
            return self._to_dto(tax_return)

'''

content = content.replace(anchor, T47_METHODS + anchor, 1)
print("Patch 2 applied: T47 state machine methods")

# --- Patch 3: add T47 constants import ---
old3 = b"    RETURN_STATUS_CANCELLED,\r\n    RETURN_STATUS_DRAFT,\r\n    RETURN_STATUS_FILED,\r\n"
new3 = (
    b"    RETURN_STATUS_APPROVED,\r\n"
    b"    RETURN_STATUS_CANCELLED,\r\n"
    b"    RETURN_STATUS_DRAFT,\r\n"
    b"    RETURN_STATUS_FILED,\r\n"
    b"    RETURN_STATUS_READY_FOR_REVIEW,\r\n"
    b"    RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION,\r\n"
    b"    RETURN_STATUS_SUBMITTED_CONFIRMED,\r\n"
)
if old3 in content:
    content = content.replace(old3, new3, 1)
    print("Patch 3 applied: T47 constants imported")
else:
    print("Patch 3 skipped: already applied or pattern changed")

open(path, "wb").write(content)
print("File written successfully")
