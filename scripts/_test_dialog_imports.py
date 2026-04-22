"""Quick smoke test: import all 20 payroll dialog modules."""
import importlib
import sys

dialogs = [
    "employee_form_dialog",
    "department_dialog",
    "position_dialog",
    "compensation_profile_dialog",
    "component_assignment_dialog",
    "company_payroll_settings_dialog",
    "apply_statutory_pack_dialog",
    "payroll_run_dialog",
    "payroll_input_batch_dialog",
    "payroll_post_run_dialog",
    "payroll_payment_record_dialog",
    "payroll_run_employee_detail_dialog",
    "payroll_run_posting_detail_dialog",
    "payroll_summary_dialog",
    "payslip_preview_dialog",
    "payroll_remittance_batch_dialog",
    "payroll_remittance_line_dialog",
    "payroll_project_allocations_dialog",
    "payroll_export_dialog",
    "validation_check_detail_dialog",
]

ok = 0
fail = 0
for d in dialogs:
    mod = f"seeker_accounting.modules.payroll.ui.dialogs.{d}"
    try:
        importlib.import_module(mod)
        ok += 1
    except Exception as e:
        fail += 1
        print(f"FAIL {d}: {e}")

print(f"\nOK: {ok}, FAIL: {fail}")
sys.exit(1 if fail else 0)
