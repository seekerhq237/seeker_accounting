"""Syntax-check all non-UI module files."""
from __future__ import annotations
import ast
import pathlib

root = pathlib.Path("src/seeker_accounting/modules")
errors = []
total = 0
for f in sorted(root.rglob("*.py")):
    if "ui" in f.parts or "__pycache__" in f.parts:
        continue
    total += 1
    try:
        ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
    except SyntaxError as e:
        errors.append(f"{f}: {e}")

if errors:
    print("SYNTAX ERRORS:")
    for e in errors:
        print(e)
else:
    print(f"All {total} service files parse cleanly.")
