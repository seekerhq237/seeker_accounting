"""payroll_lint_ast.py — AST-level lint guards for payroll UI (P1.S8).

Three rules enforced on every ``*.py`` file under
``src/seeker_accounting/modules/payroll/ui/``:

1. **PAYROLL_QLINEEDIT_NUMERIC** — ``QLineEdit`` assigned to a variable whose
   name matches common numeric-field patterns (amount, salary, rate, qty,
   quantity, net, gross, tax, cnps, pit, deduction, allowance).  These must
   use ``MoneyInput``, ``RateInput``, or ``QuantityInput`` instead.

2. **PAYROLL_RESIZE_LITERAL** — direct ``resize(`` calls on any widget.
   Dimensions must come from ``apply_window_size`` / ``WindowSizeToken``.

3. **PAYROLL_HEX_COLOR** — bare hex colour string literals
   (``"#RRGGBB"``, ``"#RGB"``, ``"#RRGGBBAA"``) in payroll UI code.
   Colours must be consumed from ``palette.py`` / ``tokens.py``.

Usage
-----
    python scripts/payroll_lint_ast.py [--fix-report] [path ...]

Exit code 0 = clean; 1 = violations found.

This script is also the entry-point for the ``payroll-ui-ast`` pre-commit hook.
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# ── configuration ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_ROOT = REPO_ROOT / "src" / "seeker_accounting" / "modules" / "payroll" / "ui"

# Regex for numeric-field name patterns (case-insensitive match on any part).
_NUMERIC_FIELD_RE = re.compile(
    r"\b(amount|salary|rate|qty|quantity|net|gross|tax|cnps|pit|deduction|allowance)\b",
    re.IGNORECASE,
)

# Regex for hex colour string literals: #RGB, #RRGGBB, #RRGGBBAA.
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?$")


# ── finding dataclass ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    col: int
    code: str
    message: str

    def format(self) -> str:
        rel = self.path.relative_to(REPO_ROOT) if self.path.is_relative_to(REPO_ROOT) else self.path
        return f"{rel}:{self.line}:{self.col}: {self.code}: {self.message}"


# ── AST visitor ───────────────────────────────────────────────────────────────


class _PayrollUIVisitor(ast.NodeVisitor):
    """Collects violations in one source file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[Violation] = []

    # ── Rule 1: QLineEdit for numeric variable names ──────────────────

    def visit_Assign(self, node: ast.Assign) -> None:
        """Detect: self._<numeric_name> = QLineEdit(...)."""
        self._check_qlineedit_assign(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Detect annotated assignment: self._amount: QLineEdit = QLineEdit(...)."""
        if (
            isinstance(node.value, ast.Call)
            and self._is_qlineedit_call(node.value)
            and isinstance(node.target, ast.Attribute)
            and _NUMERIC_FIELD_RE.search(node.target.attr)
        ):
            self._add(
                node,
                "PAYROLL_QLINEEDIT_NUMERIC",
                f"Use MoneyInput/RateInput/QuantityInput for '{node.target.attr}', not QLineEdit.",
            )
        self.generic_visit(node)

    def _check_qlineedit_assign(self, node: ast.Assign) -> None:
        if not (isinstance(node.value, ast.Call) and self._is_qlineedit_call(node.value)):
            return
        for target in node.targets:
            name = self._extract_name(target)
            if name and _NUMERIC_FIELD_RE.search(name):
                self._add(
                    node,
                    "PAYROLL_QLINEEDIT_NUMERIC",
                    f"Use MoneyInput/RateInput/QuantityInput for '{name}', not QLineEdit.",
                )

    @staticmethod
    def _is_qlineedit_call(call: ast.Call) -> bool:
        func = call.func
        if isinstance(func, ast.Name) and func.id == "QLineEdit":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "QLineEdit":
            return True
        return False

    @staticmethod
    def _extract_name(target: ast.expr) -> str | None:
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            return target.attr
        return None

    # ── Rule 2: resize( literal ──────────────────────────────────────

    def visit_Call(self, node: ast.Call) -> None:
        """Detect self.resize(...) / widget.resize(...)."""
        if isinstance(node.func, ast.Attribute) and node.func.attr == "resize":
            # Only flag if arguments are integer/float literals (not variable
            # references to token sizes).
            if node.args and any(isinstance(a, ast.Constant) and isinstance(a.value, (int, float)) for a in node.args):
                self._add(
                    node,
                    "PAYROLL_RESIZE_LITERAL",
                    "Replace resize() with apply_window_size() or WindowSizeToken constraints.",
                )
        self.generic_visit(node)

    # ── Rule 3: hex color string literal ─────────────────────────────

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _HEX_COLOR_RE.match(node.value):
            self._add(
                node,
                "PAYROLL_HEX_COLOR",
                f"Raw hex colour {node.value!r} must come from palette.py / tokens.py.",
            )
        self.generic_visit(node)

    # ── helpers ───────────────────────────────────────────────────────

    def _add(self, node: ast.AST, code: str, message: str) -> None:
        self.violations.append(
            Violation(
                path=self.path,
                line=getattr(node, "lineno", 0),
                col=getattr(node, "col_offset", 0),
                code=code,
                message=message,
            )
        )


# ── file scanning ─────────────────────────────────────────────────────────────


def check_file(path: Path) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [Violation(path=path, line=exc.lineno or 0, col=exc.offset or 0,
                          code="PAYROLL_SYNTAX", message=str(exc))]
    visitor = _PayrollUIVisitor(path)
    visitor.visit(tree)
    return visitor.violations


def collect_python_files(roots: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return files


# ── baseline ledger ───────────────────────────────────────────────────────────
# Pre-existing violations are recorded here so CI only fails on *new*
# regressions. When a violation is fixed, remove its entry from this set.

_KNOWN_VIOLATIONS: frozenset[str] = frozenset(
    # Format: "relative/path.py:LINE:COL:CODE"
    # Populated incrementally as existing violations are confirmed and accepted.
    # Leave empty until a full audit pass is done; new code must be clean.
)


def _violation_key(v: Violation) -> str:
    rel = v.path.relative_to(REPO_ROOT) if v.path.is_relative_to(REPO_ROOT) else v.path
    return f"{str(rel).replace(chr(92), '/')}:{v.line}:{v.col}:{v.code}"


# ── entry-point ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Payroll UI AST lint guards (P1.S8)")
    parser.add_argument("paths", nargs="*", type=Path,
                        help="Files or directories to scan (default: payroll/ui/)")
    parser.add_argument("--baseline", action="store_true",
                        help="Print violation keys suitable for adding to _KNOWN_VIOLATIONS")
    args = parser.parse_args(argv)

    roots = args.paths if args.paths else [DEFAULT_SCAN_ROOT]
    files = collect_python_files(roots)

    all_violations: list[Violation] = []
    for f in files:
        all_violations.extend(check_file(f))

    if args.baseline:
        for v in sorted(all_violations, key=_violation_key):
            print(f'    "{_violation_key(v)}",')
        return 0

    new_violations = [v for v in all_violations if _violation_key(v) not in _KNOWN_VIOLATIONS]

    for v in sorted(new_violations, key=lambda x: (x.path, x.line)):
        print(v.format())

    if new_violations:
        print(
            f"\n{len(new_violations)} payroll UI AST violation(s) found "
            f"({len(all_violations) - len(new_violations)} suppressed by baseline).",
            file=sys.stderr,
        )
        return 1

    if all_violations:
        print(
            f"payroll-ui-ast: {len(all_violations)} known violation(s) suppressed "
            f"(clean on new code).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
