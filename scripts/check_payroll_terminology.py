from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_ROOT = REPO_ROOT / "src" / "seeker_accounting" / "modules" / "payroll"


@dataclass(frozen=True, slots=True)
class TerminologyRule:
    code: str
    pattern: re.Pattern[str]
    suggestion: str


@dataclass(frozen=True, slots=True)
class TerminologyFinding:
    path: Path
    line: int
    code: str
    text: str
    suggestion: str

    def format(self) -> str:
        rel = self.path.relative_to(REPO_ROOT) if self.path.is_relative_to(REPO_ROOT) else self.path
        return f"{rel}:{self.line}: {self.code}: {self.suggestion} (found {self.text!r})"


RULES: tuple[TerminologyRule, ...] = (
    TerminologyRule("PAYROLL_RUN_CASE", re.compile(r"\bPayroll Run\b"), "Use 'Payroll run'."),
    TerminologyRule("PAYROLL_RUNS_CASE", re.compile(r"\bPayroll Runs\b"), "Use 'Payroll runs'."),
    TerminologyRule("RUN_PAYROLL_NOUN", re.compile(r"\bRun Payroll\b"), "Use 'Payroll runs' for navigation/headings."),
    TerminologyRule("INPUT_BATCH_UI", re.compile(r"\b(?:Variable Input Batch|Payroll Input Batch|Input Batch|input batch(?:es|\(es\))?)\b"), "Use 'Variable input' or 'Variable inputs'."),
    TerminologyRule("COMPENSATION_PROFILE_UI", re.compile(r"\b[Cc]ompensation [Pp]rofiles?\b|\bProfile Name\b|\bProfile name\b|\bProfile:|\b[Pp]rofile created\b|\bNew profile:\b"), "Use 'Compensation' or 'Compensation name'."),
    TerminologyRule("PAYROLL_COMPONENTS_CASE", re.compile(r"\bPayroll Components\b"), "Use 'Payroll components'."),
    TerminologyRule("COMPONENT_DEFINITION_UI", re.compile(r"\bComponent Definition\b"), "Use 'Payroll component definition'."),
    TerminologyRule("ASSIGN_COMPONENT_UI", re.compile(r"\bAssign Component\b"), "Use 'Assign payroll component'."),
    TerminologyRule("COMPONENT_TITLE_CASE", re.compile(r"\bComponent Assignments?\b"), "Use sentence case: 'Component assignment(s)'."),
    TerminologyRule("STANDALONE_COMPONENT", re.compile(r"^Component:?$"), "Use 'Payroll component'."),
    TerminologyRule("AUTHORITY_UI", re.compile(r"^Authority:?$"), "Use 'Statutory authority'."),
    TerminologyRule("STATUTORY_PACK_CASE", re.compile(r"\bStatutory Packs?\b"), "Use sentence case: 'Statutory pack(s)'."),
    TerminologyRule("REMIT_UI", re.compile(r"^Remit$"), "Use 'Remittances'."),
    TerminologyRule("REMITTANCE_BATCH_UI", re.compile(r"\bRemittance Batch\b"), "Use 'Remittance'."),
)


_IGNORED_CALL_NAMES = {
    "debug",
    "info",
    "warning",
    "error",
    "exception",
    "critical",
    "getLogger",
}


def _python_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.py"))
        elif path.suffix == ".py":
            yield path


class _StringVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[TerminologyFinding] = []
        self._ignored_depth = 0

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if _is_ignored_call(node):
            self._ignored_depth += 1
            self.generic_visit(node)
            self._ignored_depth -= 1
            return
        self.generic_visit(node)

    def visit_Module(self, node: ast.Module) -> None:  # noqa: N802
        self._visit_body_without_docstring(node.body)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._visit_body_without_docstring(node.body)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_body_without_docstring(node.body)
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if self._ignored_depth or not isinstance(node.value, str):
            return
        text = node.value
        for rule in RULES:
            if rule.pattern.search(text):
                self.findings.append(
                    TerminologyFinding(
                        path=self.path,
                        line=node.lineno,
                        code=rule.code,
                        text=_compact(text),
                        suggestion=rule.suggestion,
                    )
                )

    def _visit_body_without_docstring(self, body: list[ast.stmt]) -> None:
        start = 1 if body and _is_docstring_expr(body[0]) else 0
        for stmt in body[start:]:
            self.visit(stmt)


def _is_docstring_expr(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _is_ignored_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _IGNORED_CALL_NAMES:
        return True
    if isinstance(func, ast.Name) and func.id in _IGNORED_CALL_NAMES:
        return True
    return False


def _compact(text: str) -> str:
    return " ".join(text.split())[:160]


def check_paths(paths: Iterable[Path]) -> list[TerminologyFinding]:
    findings: list[TerminologyFinding] = []
    for path in _python_files(paths):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            findings.append(
                TerminologyFinding(
                    path=path,
                    line=exc.lineno or 1,
                    code="PYTHON_SYNTAX",
                    text=exc.msg,
                    suggestion="Fix syntax before terminology scan can run.",
                )
            )
            continue
        visitor = _StringVisitor(path)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    paths = [Path(arg) for arg in args] if args else [DEFAULT_SCAN_ROOT]
    resolved = [path if path.is_absolute() else REPO_ROOT / path for path in paths]
    findings = check_paths(resolved)
    if findings:
        print("Payroll terminology check failed:")
        for finding in findings:
            print(f"  {finding.format()}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())