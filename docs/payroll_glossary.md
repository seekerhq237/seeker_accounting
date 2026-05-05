# Payroll Glossary

Status: Phase 11 baseline.
Scope: payroll UI labels, user-facing messages, help text, and operator documentation.

This glossary is the canonical wording source for payroll surfaces. Persistence names, DTO fields, database columns, service methods, and audit event codes may keep schema-aligned names where changing them would create migration or compatibility risk. UI text must use the canonical terms below.

## Canonical Terms

| Concept | Canonical UI term | Rejected UI wording | Notes |
|---|---|---|---|
| Payroll cycle | Payroll run | Run, Payroll Run, Run Payroll | Use Payroll run as the noun. Use Calculate, Approve, Post, Reverse as verbs. |
| Payroll line definition | Payroll component | Component when shown alone | Component assignment is allowed when the linkage is the subject. |
| Employee compensation record | Compensation | Compensation profile, Profile | Database and service names may still contain profile. |
| Employee-to-component linkage | Component assignment | Component Assignment when title-cased | Use sentence case in labels and headings. |
| Period-specific payroll inputs | Variable input | Input batch, Variable Input Batch, Payroll Input Batch | Input batch remains a persistence concept only. |
| Statutory recipient | Statutory authority | Authority when shown alone | CNPS, DGI, FNE, and CFC are statutory authorities. |
| Statutory outbound payment/declaration | Remittance | Remit, Remittance Batch | Use remittance for the user-facing artifact. |
| Jurisdiction manifest | Statutory pack | Pack when shown alone | Pack is acceptable only when already qualified nearby. |

## Phrase Rules

- Prefer sentence case in payroll UI headings and dialog titles: Payroll run, Payroll component, Statutory authority.
- Do not show persistence containers such as input batch unless the user is in an administrator/debugging context.
- Use Compensation for the employee pay package. If extra clarity is needed, use compensation record, not profile.
- Use Payroll component for standalone columns, field labels, and dialogs. Use Component assignment only for the employee/component linkage.
- Use Statutory authority when the field or column is a recipient such as CNPS, DGI, FNE, or CFC.
- Use Remittance for the statutory payment/declaration artifact. Avoid batch unless discussing internal storage.

## Lint Contract

The repository hook in `scripts/check_payroll_terminology.py` scans payroll module string literals for rejected user-facing wording. It intentionally does not rename database models, DTOs, services, code identifiers, or audit codes.