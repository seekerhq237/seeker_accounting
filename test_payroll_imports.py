#!/usr/bin/env python3
"""Quick test of payroll model imports."""

try:
    from seeker_accounting.modules.payroll.models.company_payroll_setting import CompanyPayrollSetting
    from seeker_accounting.modules.payroll.models.department import Department
    from seeker_accounting.modules.payroll.models.position import Position
    from seeker_accounting.modules.payroll.models.employee import Employee
    from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
    from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet
    from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
    print("All payroll models imported successfully")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()