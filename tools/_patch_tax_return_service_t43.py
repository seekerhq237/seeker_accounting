with open('src/seeker_accounting/modules/taxation/services/tax_return_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add VatPeriodLockRepository to TYPE_CHECKING block
old1 = (
    '    from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (\n'
    '        CompanyTaxProfileRepository,\n'
    '    )\n'
    '\n'
    '\n'
    'TaxReturnRepositoryFactory'
)
new1 = (
    '    from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (\n'
    '        CompanyTaxProfileRepository,\n'
    '    )\n'
    '    from seeker_accounting.modules.taxation.repositories.vat_period_lock_repository import (\n'
    '        VatPeriodLockRepository,\n'
    '    )\n'
    '\n'
    '\n'
    'TaxReturnRepositoryFactory'
)
content = content.replace(old1, new1, 1)

# 2. Add VatPeriodLockRepositoryFactory type alias
old2 = (
    'CompanyTaxProfileRepositoryFactory = Callable[\n'
    '    [Session], "CompanyTaxProfileRepository"\n'
    ']\n'
    '\n'
    '\n'
    '_ZERO'
)
new2 = (
    'CompanyTaxProfileRepositoryFactory = Callable[\n'
    '    [Session], "CompanyTaxProfileRepository"\n'
    ']\n'
    'VatPeriodLockRepositoryFactory = Callable[[Session], "VatPeriodLockRepository"]\n'
    '\n'
    '\n'
    '_ZERO'
)
content = content.replace(old2, new2, 1)

# 3. Add vat_period_lock_repository_factory param to __init__
old3 = (
    '        audit_service: "AuditService | None" = None,\n'
    '        company_tax_profile_repository_factory: CompanyTaxProfileRepositoryFactory | None = None,\n'
    '    ) -> None:\n'
    '        self._unit_of_work_factory = unit_of_work_factory\n'
    '        self._app_context = app_context\n'
    '        self._tax_return_repository_factory = tax_return_repository_factory\n'
    '        self._tax_obligation_repository_factory = tax_obligation_repository_factory\n'
    '        self._company_repository_factory = company_repository_factory\n'
    '        self._posted_tax_line_repository_factory = posted_tax_line_repository_factory\n'
    '        self._fiscal_period_repository_factory = fiscal_period_repository_factory\n'
    '        self._permission_service = permission_service\n'
    '        self._audit_service = audit_service\n'
    '        self._company_tax_profile_repository_factory = company_tax_profile_repository_factory'
)
new3 = (
    '        audit_service: "AuditService | None" = None,\n'
    '        company_tax_profile_repository_factory: CompanyTaxProfileRepositoryFactory | None = None,\n'
    '        vat_period_lock_repository_factory: "VatPeriodLockRepositoryFactory | None" = None,\n'
    '    ) -> None:\n'
    '        self._unit_of_work_factory = unit_of_work_factory\n'
    '        self._app_context = app_context\n'
    '        self._tax_return_repository_factory = tax_return_repository_factory\n'
    '        self._tax_obligation_repository_factory = tax_obligation_repository_factory\n'
    '        self._company_repository_factory = company_repository_factory\n'
    '        self._posted_tax_line_repository_factory = posted_tax_line_repository_factory\n'
    '        self._fiscal_period_repository_factory = fiscal_period_repository_factory\n'
    '        self._permission_service = permission_service\n'
    '        self._audit_service = audit_service\n'
    '        self._company_tax_profile_repository_factory = company_tax_profile_repository_factory\n'
    '        self._vat_period_lock_repository_factory = vat_period_lock_repository_factory'
)
content = content.replace(old3, new3, 1)

# 4. Add auto-lock in file_return after commit
old4 = (
    '            tax_return.status_code = RETURN_STATUS_FILED\n'
    '            tax_return.filed_at = datetime.utcnow()\n'
    '            tax_return.otp_reference = otp\n'
    '            tax_return.external_reference = ext\n'
    '            uow.commit()\n'
    '\n'
    '            self._record_audit(\n'
    '                company_id,\n'
    '                "TAX_RETURN_FILED",'
)
new4 = (
    '            tax_return.status_code = RETURN_STATUS_FILED\n'
    '            tax_return.filed_at = datetime.utcnow()\n'
    '            tax_return.otp_reference = otp\n'
    '            tax_return.external_reference = ext\n'
    '            uow.commit()\n'
    '\n'
    '            # T43: auto-lock the period so backdating is blocked.\n'
    '            if self._vat_period_lock_repository_factory is not None:\n'
    '                from seeker_accounting.modules.taxation.models.vat_period_lock import VatPeriodLock as _VPL\n'
    '                import datetime as _dt\n'
    '                lock_repo = self._vat_period_lock_repository_factory(uow.session)\n'
    '                existing_lock = lock_repo.find_by_period(\n'
    '                    company_id,\n'
    '                    tax_return.period_start,\n'
    '                    tax_return.period_end,\n'
    '                    tax_return.tax_type_code,\n'
    '                )\n'
    '                if existing_lock is None:\n'
    '                    period_lock = _VPL(\n'
    '                        company_id=company_id,\n'
    '                        period_start=tax_return.period_start,\n'
    '                        period_end=tax_return.period_end,\n'
    '                        tax_type_code=tax_return.tax_type_code,\n'
    '                        locked_at=_dt.datetime.utcnow(),\n'
    '                        locked_by_user_id=actor_id,\n'
    '                        return_id=tax_return.id,\n'
    '                    )\n'
    '                    lock_repo.add(period_lock)\n'
    '                    uow.commit()\n'
    '\n'
    '            self._record_audit(\n'
    '                company_id,\n'
    '                "TAX_RETURN_FILED",'
)
content = content.replace(old4, new4, 1)

with open('src/seeker_accounting/modules/taxation/services/tax_return_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('VatPeriodLockRepository count:', content.count('VatPeriodLockRepository'))
print('VatPeriodLock count:', content.count('VatPeriodLock'))
print('vat_period_lock_repository_factory count:', content.count('vat_period_lock_repository_factory'))
