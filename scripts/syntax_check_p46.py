import ast, sys, pathlib
files = [
    "src/seeker_accounting/modules/payroll/dto/employee_dto.py",
    "src/seeker_accounting/modules/payroll/services/employee_service.py",
    "src/seeker_accounting/modules/payroll/ui/bp/employee_termination_wizard.py",
    "src/seeker_accounting/modules/payroll/ui/bp/employee_rehire_wizard.py",
    "src/seeker_accounting/modules/payroll/ui/workbench/panes/people_pane.py",
]
ok = True
for f in files:
    try:
        ast.parse(pathlib.Path(f).read_text(encoding="utf-8"))
        print(f"OK  {f}")
    except SyntaxError as e:
        print(f"ERR {f}:{e.lineno}: {e.msg}")
        ok = False
sys.exit(0 if ok else 1)
