"""Payroll permission code constants.

These codes must match the permission rows seeded in the migration.
Services call permission_service.require_permission(CODE) before
performing sensitive operations.
"""
from __future__ import annotations

PAYROLL_SETUP_MANAGE = "payroll.setup.manage"
PAYROLL_EMPLOYEE_MANAGE = "payroll.employee.manage"
PAYROLL_COMPONENT_MANAGE = "payroll.component.manage"
PAYROLL_RULE_MANAGE = "payroll.rule.manage"
PAYROLL_PACK_APPLY = "payroll.pack.apply"
PAYROLL_INPUT_MANAGE = "payroll.input.manage"
PAYROLL_RUN_CREATE = "payroll.run.create"
PAYROLL_RUN_CALCULATE = "payroll.run.calculate"
PAYROLL_RUN_APPROVE = "payroll.run.approve"
PAYROLL_RUN_POST = "payroll.run.post"
PAYROLL_PAYMENT_MANAGE = "payroll.payment.manage"
PAYROLL_REMITTANCE_MANAGE = "payroll.remittance.manage"
PAYROLL_IMPORT = "payroll.import"
PAYROLL_PRINT = "payroll.print"
PAYROLL_AUDIT_VIEW = "payroll.audit.view"

ALL_PAYROLL_PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    (PAYROLL_SETUP_MANAGE, "Manage Payroll Setup", "Manage company payroll settings, departments, and positions"),
    (PAYROLL_EMPLOYEE_MANAGE, "Manage Employees", "Create, edit, and deactivate employee records"),
    (PAYROLL_COMPONENT_MANAGE, "Manage Payroll Components", "Create and edit payroll components"),
    (PAYROLL_RULE_MANAGE, "Manage Payroll Rules", "Create and edit payroll rule sets and brackets"),
    (PAYROLL_PACK_APPLY, "Apply Statutory Packs", "Apply and rollover statutory payroll packs"),
    (PAYROLL_INPUT_MANAGE, "Manage Payroll Inputs", "Create, submit, and approve payroll input batches"),
    (PAYROLL_RUN_CREATE, "Create Payroll Runs", "Create new payroll runs"),
    (PAYROLL_RUN_CALCULATE, "Calculate Payroll", "Trigger payroll calculation for a run"),
    (PAYROLL_RUN_APPROVE, "Approve Payroll Runs", "Approve calculated payroll runs"),
    (PAYROLL_RUN_POST, "Post Payroll Runs", "Post approved payroll runs to the general ledger"),
    (PAYROLL_PAYMENT_MANAGE, "Manage Employee Payments", "Record and manage employee payment records"),
    (PAYROLL_REMITTANCE_MANAGE, "Manage Remittances", "Create and manage statutory remittance batches"),
    (PAYROLL_IMPORT, "Import Payroll Data", "Import employees, components, and other payroll data"),
    (PAYROLL_PRINT, "Print Payslips & Reports", "Print payslips and payroll summary reports"),
    (PAYROLL_AUDIT_VIEW, "View Payroll Audit Log", "View the payroll audit event log"),
)
