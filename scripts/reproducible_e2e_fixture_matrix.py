"""Reproducible end-to-end fixture matrix for payroll/year-end hardening.

The script emits a deterministic matrix that service-level fixture builders can
consume. It intentionally contains no UI automation and no hidden database
writes; execution belongs to dedicated smoke tests or setup scripts.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class FixtureStep:
    sequence: int
    code: str
    description: str
    expected_result: str


@dataclass(frozen=True, slots=True)
class FixtureStepResult:
    sequence: int
    code: str
    executed: bool
    message: str


FixtureStepHandler = Callable[[FixtureStep], str | None]
DatabaseFixtureStepHandler = Callable[[FixtureStep, Any], str | None]


class UnitOfWork(Protocol):
    session: Any

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> object: ...

    def commit(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]


def build_fixture_matrix() -> tuple[FixtureStep, ...]:
    return (
        FixtureStep(1, "setup_company", "Create one company with fiscal calendar, OHADA chart, document sequences, and payroll settings.", "Company foundation is ready."),
        FixtureStep(2, "seed_employees", "Create five active employees with pay components, tax identifiers, CNPS numbers, and payment accounts.", "Five payroll-ready employees exist."),
        FixtureStep(3, "monthly_run_2026_01", "Calculate, approve, and post the January regular payroll run.", "January payroll is posted and balanced."),
        FixtureStep(4, "monthly_run_2026_02", "Calculate, approve, and post the February regular payroll run.", "February payroll is posted and balanced."),
        FixtureStep(5, "monthly_run_2026_03", "Calculate, approve, and post the March regular payroll run.", "March payroll is posted and balanced."),
        FixtureStep(6, "off_cycle_adjustment", "Create one off-cycle run for a scoped employee correction.", "Correction is applied only to the selected employee."),
        FixtureStep(7, "reverse_off_cycle", "Reverse the off-cycle posting through the payroll reversal service.", "Reversal journal balances and run state is updated."),
        FixtureStep(8, "year_end_dsf", "Run year-end DSF fixture checks against posted payroll and tax facts.", "Year-end DSF totals reconcile to posted source data."),
    )


def write_fixture_matrix(path: Path) -> None:
    payload = [asdict(step) for step in build_fixture_matrix()]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_fixture_results(path: Path, results: tuple[FixtureStepResult, ...]) -> None:
    payload = [asdict(result) for result in results]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_fixture_matrix(
    handlers: Mapping[str, FixtureStepHandler],
    *,
    dry_run: bool = False,
) -> tuple[FixtureStepResult, ...]:
    results: list[FixtureStepResult] = []
    for step in build_fixture_matrix():
        handler = handlers.get(step.code)
        if handler is None:
            if not dry_run:
                raise KeyError(f"No fixture handler registered for step {step.code}.")
            results.append(FixtureStepResult(step.sequence, step.code, False, "No handler registered."))
            continue
        message = handler(step) or step.expected_result
        results.append(FixtureStepResult(step.sequence, step.code, True, message))
    return tuple(results)


def run_database_fixture_matrix(
    handlers: Mapping[str, DatabaseFixtureStepHandler],
    unit_of_work_factory: UnitOfWorkFactory,
    *,
    dry_run: bool = False,
) -> tuple[FixtureStepResult, ...]:
    """Execute the fixture matrix with one database unit of work per step.

    Handlers receive the current ``FixtureStep`` plus the active session from
    the unit of work. A successful handler is committed before the next step
    starts, which keeps scenario setup deterministic and resumable.
    """
    results: list[FixtureStepResult] = []
    for step in build_fixture_matrix():
        handler = handlers.get(step.code)
        if handler is None:
            if not dry_run:
                raise KeyError(f"No database fixture handler registered for step {step.code}.")
            results.append(FixtureStepResult(step.sequence, step.code, False, "No handler registered."))
            continue

        with unit_of_work_factory() as uow:
            message = handler(step, uow.session) or step.expected_result
            uow.commit()
        results.append(FixtureStepResult(step.sequence, step.code, True, message))
    return tuple(results)


def build_dry_run_handlers() -> dict[str, FixtureStepHandler]:
    return {step.code: (lambda fixture_step: fixture_step.expected_result) for step in build_fixture_matrix()}


def main() -> None:
    default_path = Path("artifacts") / "p14_e2e_fixture_matrix.json"
    default_path.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_matrix(default_path)
    run_fixture_matrix(build_dry_run_handlers(), dry_run=True)
    print(default_path.as_posix())


if __name__ == "__main__":
    main()