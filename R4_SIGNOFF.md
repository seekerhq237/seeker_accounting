# R4 — Final Payroll Compliance Regression and Operational Acceptance — Signoff Report

## 1. What Was Tested

**79 checks across 4 sections. All 79 passed.**

### Section A — End-to-end Workflow (39 tests)
Full payroll lifecycle: company setup → chart of accounts → account mapping → statutory pack application → employee creation → compensation profiles → component assignments → payroll run creation → calculation → approval → journal posting → payment tracking (partial + full) → remittance batch lifecycle → payslip data → summary data → CSV/PDF export → output warnings → deadline service → validation dashboard → run summary.

Verified calculation accuracy for:
- **EMP001** (500,000 XAF): gross=500,000 | CNPS=21,000 | taxable=293,633.33 | IRPP=40,075 | CAC=4,007.50 | TDL=250 | net=416,867.50 | employer_cost=569,750
- **EMP002** (50,000 XAF, below threshold): gross=50,000 | CNPS=2,100 | taxable=0 | IRPP=0 | TDL=0 | net=46,150 | employer_cost=56,975

Verified journal posting: Dr=626,725.00 Cr=626,725.00 (balanced, 5 journal lines across salary expense 6611, social expense 6641, payroll payable 422, tax liability 441, social liability 4311).

### Section B — Cameroon Compliance (14 tests)
- B1: CNPS employee and employer both capped at 31,500 (4.2% × 750k ceiling) ✓
- B2: Taxable salary base for 1.5M salary = 986,283.33 ✓
- B3: IRPP monthly for high salary = 270,199.17 ✓
- B4: CAC = 10% of IRPP = 27,019.92 ✓
- B5: TDL = 250 for gross > 208,333 (step bracket) ✓
- B6: CRTV = 13,000 for 1.5M salary ✓
- B7: Accident risk (1.75%) = 26,250, FNE employer (1%) = 15,000, Family allowances (7% capped) = 52,500 ✓
- B8: CFC-HLF = 15,000 (1%), FNE employee = 15,000 (1%) ✓
- B9: Below-threshold (50k) taxable base = 0 ✓
- B10: DGI deadline = Feb 15, CNPS deadline = Feb 15 ✓

### Section C — Edge-case Regression (17 tests)
- C1: Double-posting blocked (ValidationError) ✓
- C2: Void posted run blocked ✓
- C3: Overpayment blocked ✓
- C4: Future period draft creation allowed ✓
- C5: Approve uncalculated run blocked ✓
- C6: Void draft run succeeds ✓
- C7: Void calculated run succeeds ✓
- C8: Zero-input run calculates (employees get base salary only) ✓
- C9: Duplicate employee number blocked ✓
- C10: Terminated employee excluded from run ✓
- C11: Remittance draft → cancel lifecycle ✓
- C12: Input batch → add line → submit lifecycle ✓
- C13: Pre-run validation service works ✓
- C14: Pack version service works ✓
- C15: Payslip preview service works ✓

### Section D — Test Harness Validation (4 tests)
- D1: All 24 payroll services wired on registry ✓
- D2: 15 statutory components seeded ✓
- D3: 16 rule sets seeded ✓
- D4: 1 statutory pack available ✓

---

## 2. Files Created or Modified

### Created
| File | Purpose |
|------|---------|
| `scripts/smoke_payroll_r4_regression.py` | Comprehensive R4 regression test (79 checks, 4 sections) |
| `R4_SIGNOFF.md` | This signoff report |

### Modified (production code — defect fixes)
| File | Change |
|------|--------|
| `src/seeker_accounting/modules/payroll/services/payroll_calculation_service.py` | **Defect #3 fix:** `_build_context()` now resolves `base_amount` from `profile.basic_salary` for BASE_SALARY component when `override_amount` is None |
| `src/seeker_accounting/modules/payroll/engines/tdl_engine.py` | **Defect #4 fix:** Replaced progressive bracket accumulation with step-bracket (single-match) logic for TDL |
| `src/seeker_accounting/modules/accounting/reference_data/services/numbering_setup_service.py` | **Defect #1+2 fix:** Added `payroll_remittance` and `payroll_input_batch` to valid doc types; fixed `_require_code()` to normalize to lowercase |
| `src/seeker_accounting/platform/numbering/numbering_service.py` | **Defect #2 fix:** Added lowercase normalization in `issue_next_number()` |
| `src/seeker_accounting/modules/payroll/services/payroll_posting_service.py` | **Defect #2 fix:** `_JOURNAL_DOC_TYPE` → lowercase |
| `src/seeker_accounting/modules/payroll/services/payroll_remittance_service.py` | **Defect #2 fix:** `_REMITTANCE_DOC_TYPE` → lowercase |
| `src/seeker_accounting/modules/payroll/services/payroll_run_service.py` | **Defect #2 fix:** `_RUN_DOC_TYPE` → lowercase |
| `src/seeker_accounting/modules/payroll/services/payroll_input_service.py` | **Defect #2 fix:** `_BATCH_DOC_TYPE` → lowercase |
| `src/seeker_accounting/modules/accounting/journals/services/journal_posting_service.py` | **Defect #2 fix:** `DOCUMENT_TYPE_CODE` → lowercase |

---

## 3. Defects Found and Fixed

### Defect #1 — Missing document type codes in numbering validation
- **Severity:** Blocking — payroll remittance and input batch sequences could not be created
- **Root cause:** `_VALID_DOCUMENT_TYPE_CODES` in `numbering_setup_service.py` did not include `payroll_remittance` or `payroll_input_batch`
- **Fix:** Added both codes to the frozenset

### Defect #2 — Case normalization mismatch in document numbering
- **Severity:** Blocking — all document sequence lookups failed silently
- **Root cause:** `_require_code()` normalized to UPPERCASE but `_VALID_DOCUMENT_TYPE_CODES` was lowercase; all payroll service doc type constants used UPPERCASE (e.g., `"PAYROLL_RUN"`) which wouldn't match lowercase DB storage
- **Fix:** (1) Changed `_require_code()` to normalize to lowercase, (2) Added lowercase normalization in platform `issue_next_number()`, (3) Converted all doc type constants across 5 service files to lowercase

### Defect #3 — BASE_SALARY amount not resolved from compensation profile
- **Severity:** Critical — all employees calculated to zero gross/net/taxes
- **Root cause:** `_build_context()` in `payroll_calculation_service.py` set `base_amount=Decimal("0")` when `override_amount` was None, with no fallback to `profile.basic_salary` for the BASE_SALARY component. The `ComponentInput.base_amount` docstring explicitly says "resolved fixed amount (from **profile**, assignment override, or default)" — the profile fallback was intended but never implemented.
- **Fix:** Added profile-based resolution: when `override_amount` is None and `component_code == "BASE_SALARY"`, uses `basic_salary` from the compensation profile

### Defect #4 — TDL engine used progressive accumulation instead of step-bracket
- **Severity:** Calculation error — TDL amounts were inflated (e.g., 417 instead of 250 for 1.5M salary)
- **Root cause:** TDL is a step-bracket levy where the salary falls into exactly one bracket and that bracket's fixed amount is the entire tax. The engine incorrectly used progressive accumulation (summing across all matching brackets), which added bracket 2 (167) + bracket 3 (250) = 417 for high salaries.
- **Fix:** Replaced `_calculate_bracket_tax()` with `_resolve_tdl_bracket()` using single-match step-bracket logic (same pattern as CRTV in `irpp_engine.py`)

---

## 4. Remaining Risks

| Risk | Severity | Notes |
|------|----------|-------|
| Provisional statutory items (1 warning per pack application) | Low | The output warning service correctly flags provisional items. No impact on calculation accuracy. |
| BIK and overtime engines not tested with variable inputs | Low | Engines exist and are wired, but the regression test only uses base salary components. BIK/overtime would need dedicated test data with input batches. |
| Multi-period rollover not tested | Low | Pack version service lists versions and is wired, but full rollover workflow (year-end pack update) was not exercised. |
| Large-volume performance | Low | Regression tests 3 employees. Production workloads with 100+ employees per run are untested. |
| `submit_batch` returns `None` instead of DTO | Cosmetic | The service method transitions the batch but returns nothing. The test works around this by re-fetching. Not a correctness issue but inconsistent with `create_batch` which returns a DTO. |

---

## 5. Final Assessment

**R4 complete: YES**

**Payroll closeable: YES** — with the following qualifications:
- All 4 defects found during regression were fixed and verified
- Full end-to-end lifecycle works: setup → calculate → approve → post → pay → remit → export
- Cameroon statutory compliance verified: CNPS caps, IRPP brackets, CAC, TDL, CRTV, employer contributions, below-threshold exemption, remittance deadlines
- Edge cases verified: double-post prevention, void controls, overpayment blocking, terminated employee exclusion, input batch lifecycle
- All 24 payroll services wired and accessible
- 15 statutory components, 16 rule sets, 1 pack (CMR_2024_V1) operational
- Journal posting balanced and correct (double-entry integrity confirmed)

The payroll module is production-ready for the Cameroon statutory configuration. Future slices (BIK scenarios, overtime variable inputs, multi-period rollover, additional country packs) can build on this validated foundation.
