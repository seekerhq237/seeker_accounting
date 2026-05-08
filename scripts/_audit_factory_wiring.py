"""
Audit factories.py: for every create_* function that instantiates a class,
compare kwargs passed to the class __init__ signature.
Reports: missing required args, unexpected args.
"""
from __future__ import annotations
import ast
import importlib
import inspect
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

FACTORIES_PATH = pathlib.Path(__file__).parent.parent / "src" / "seeker_accounting" / "app" / "dependency" / "factories.py"

with open(FACTORIES_PATH, encoding="utf-8") as fh:
    source = fh.read()

tree = ast.parse(source)
lines = source.splitlines()

# ── collect all top-level create_* functions ──────────────────────────────
factory_nodes: dict[str, ast.FunctionDef] = {}
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name.startswith("create_"):
        factory_nodes[node.name] = node

# ── for each factory, find the first Return(Call(...)) and extract kwargs ─
def extract_call_kwargs(func_node: ast.FunctionDef):
    """Return (class_name, kwargs_set) for the first Return(Call) found."""
    for stmt in ast.walk(func_node):
        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            # class name
            if isinstance(call.func, ast.Name):
                cls_name = call.func.id
            elif isinstance(call.func, ast.Attribute):
                cls_name = call.func.attr
            else:
                return None, None
            kwargs = {kw.arg for kw in call.keywords if kw.arg is not None}
            return cls_name, kwargs
    return None, None

# ── build a map of class_name -> module path by scanning imports ──────────
# We import factories and inspect actual objects via the module's globals
import seeker_accounting.app.dependency.factories as fmod

factory_globals = vars(fmod)

errors: list[str] = []
warnings_list: list[str] = []
ok_count = 0

for fname, fnode in sorted(factory_nodes.items(), key=lambda x: x[1].lineno):
    cls_name, passed_kwargs = extract_call_kwargs(fnode)
    if cls_name is None:
        continue

    cls_obj = factory_globals.get(cls_name)
    if cls_obj is None or not inspect.isclass(cls_obj):
        warnings_list.append(f"  WARN  L{fnode.lineno:4d}  {fname}: class '{cls_name}' not found in factory globals, skipping")
        continue

    try:
        sig = inspect.signature(cls_obj.__init__)
    except (ValueError, TypeError):
        warnings_list.append(f"  WARN  L{fnode.lineno:4d}  {fname}: cannot inspect {cls_name}.__init__")
        continue

    init_params = sig.parameters
    required = {
        n for n, p in init_params.items()
        if n != "self"
        and p.default is inspect.Parameter.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    all_accepted = {
        n for n, p in init_params.items()
        if n != "self"
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in init_params.values()
    )

    missing = required - passed_kwargs
    unexpected = (passed_kwargs - all_accepted) if not has_var_keyword else set()

    if missing or unexpected:
        errors.append(
            f"  ERROR L{fnode.lineno:4d}  {fname} -> {cls_name}"
            + (f"\n           MISSING : {sorted(missing)}" if missing else "")
            + (f"\n           UNEXPECTED: {sorted(unexpected)}" if unexpected else "")
        )
    else:
        ok_count += 1

print(f"\n{'='*70}")
print(f"FACTORY WIRING AUDIT — {FACTORIES_PATH.name}")
print(f"{'='*70}")
print(f"  Checked: {ok_count + len(errors)} factories  |  OK: {ok_count}  |  Errors: {len(errors)}")
print()

if errors:
    print("ERRORS (will crash at runtime):")
    for e in errors:
        print(e)
    print()

if warnings_list:
    print("WARNINGS (could not verify):")
    for w in warnings_list:
        print(w)
    print()

if not errors:
    print("All factory wirings look correct.")

sys.exit(1 if errors else 0)
