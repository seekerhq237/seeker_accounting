from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from seeker_accounting.modules.payroll.engines.engine_types import (
    CalcStep,
    EmployeeCalculationResult,
    EngineLineResult,
)
from seeker_accounting.modules.payroll.dto.payroll_variance_dto import (
    PayrollVarianceAnalysisDTO,
    PayrollVarianceLineDTO,
)
from seeker_accounting.modules.payroll.services.payroll_dry_run_report_service import (
    PayrollDryRunReportService,
)
from seeker_accounting.modules.payroll.services.payroll_run_service import PayrollRunService
from seeker_accounting.modules.payroll.services.payroll_variance_analysis_service import (
    PayrollVarianceAnalysisService,
)


@dataclass
class _Component:
    id: int
    component_code: str
    component_name: str
    component_type_code: str


@dataclass
class _Correction:
    employee_id: int
    correction_amount: Decimal
    component: _Component
    status_code: str = "pending"
    applied_run_id: int | None = None
    applied_run_employee_id: int | None = None
    applied_at: object | None = None


@dataclass
class _Line:
    component_id: int
    component_amount: Decimal
    component: _Component


@dataclass
class _RunEmployee:
    status_code: str
    gross_earnings: Decimal
    net_payable: Decimal
    lines: list[_Line] = field(default_factory=list)


class _PermissionService:
    def __init__(self) -> None:
        self.required: list[str] = []

    def require_permission(self, code: str) -> None:
        self.required.append(code)


def test_employee_scope_for_regular_run_returns_none() -> None:
    run = type("Run", (), {"run_type_code": "regular", "off_cycle_employee_ids": None})()
    assert PayrollRunService._employee_scope_for_run(run) is None


def test_employee_scope_for_off_cycle_run_uses_serialized_ids() -> None:
    run = type(
        "Run",
        (),
        {"run_type_code": "off_cycle", "off_cycle_employee_ids": "[7, 9, 7]"},
    )()
    assert PayrollRunService._employee_scope_for_run(run) == {7, 9}


def test_pending_corrections_are_additive_forward_facts() -> None:
    earning = _Component(11, "ADJ", "Adjustment", "earning")
    deduction = _Component(12, "DED_ADJ", "Deduction adjustment", "deduction")
    result = EmployeeCalculationResult(
        employee_id=5,
        gross_earnings=Decimal("1000"),
        total_earnings=Decimal("1000"),
        total_employee_deductions=Decimal("100"),
        net_payable=Decimal("900"),
        employer_cost_base=Decimal("1000"),
    )

    PayrollRunService._apply_pending_corrections(
        result,
        [
            _Correction(5, Decimal("250"), earning),
            _Correction(5, Decimal("40"), deduction),
        ],
    )

    assert result.gross_earnings == Decimal("1250")
    assert result.total_earnings == Decimal("1250")
    assert result.total_employee_deductions == Decimal("140")
    assert result.net_payable == Decimal("1110")
    assert [line.component_id for line in result.lines] == [11, 12]


def test_mark_corrections_applied_records_application_links() -> None:
    correction = _Correction(
        5,
        Decimal("250"),
        _Component(11, "ADJ", "Adjustment", "earning"),
    )
    applied_at = object()
    PayrollRunService._mark_corrections_applied(
        [correction],
        run_id=44,
        run_employee_id=55,
        applied_at=applied_at,
    )

    assert correction.status_code == "applied"
    assert correction.applied_run_id == 44
    assert correction.applied_run_employee_id == 55
    assert correction.applied_at is applied_at


def test_persist_calc_steps_writes_trace_rows() -> None:
    from seeker_accounting.db.model_registry import load_model_registry

    load_model_registry()
    saved: list[object] = []

    class _TraceRepo:
        def __init__(self, session: object) -> None:
            self.session = session

        def save_many(self, traces: list[object]) -> None:
            saved.extend(traces)

    service = object.__new__(PayrollRunService)
    service._trace_repo_factory = _TraceRepo
    calc_result = EmployeeCalculationResult(
        employee_id=5,
        calc_steps=[
            CalcStep(
                sequence_number=1,
                stage_code="gross",
                component_id=11,
                component_code="BASE",
                formula_code="fixed_amount",
                input_json='{"base": 1000}',
                output_json='{"amount": 1000}',
                amount=Decimal("1000"),
            )
        ],
    )

    service._persist_calc_steps(
        object(),
        company_id=10,
        run_id=20,
        run_employee_id=30,
        employee_id=5,
        calc_result=calc_result,
    )

    assert len(saved) == 1
    assert saved[0].company_id == 10
    assert saved[0].run_id == 20
    assert saved[0].run_employee_id == 30
    assert saved[0].stage_code == "gross"
    assert saved[0].amount == Decimal("1000")


def test_variance_lines_warn_when_threshold_exceeded() -> None:
    base = _Component(1, "BASE", "Base Salary", "earning")
    prior_rows = [
        _RunEmployee(
            "included",
            gross_earnings=Decimal("1000"),
            net_payable=Decimal("800"),
            lines=[_Line(1, Decimal("1000"), base)],
        )
    ]
    current_rows = [
        _RunEmployee(
            "included",
            gross_earnings=Decimal("1250"),
            net_payable=Decimal("900"),
            lines=[_Line(1, Decimal("1250"), base)],
        )
    ]
    service = PayrollVarianceAnalysisService(
        lambda: None,
        lambda session: None,
        lambda session: None,
        lambda session: None,
        lambda session: None,
    )

    lines = service._build_variance_lines(
        current_rows, prior_rows, Decimal("10.00")
    )

    gross = next(line for line in lines if line.subject_code == "gross")
    component = next(line for line in lines if line.subject_code == "BASE")
    assert gross.delta_percent == Decimal("25.00")
    assert gross.severity_code == "warning"
    assert component.current_amount == Decimal("1250")
    assert component.severity_code == "warning"


def test_dry_run_report_exports_csv(tmp_path) -> None:
    line = PayrollVarianceLineDTO(
        category_code="summary",
        subject_code="net",
        subject_label="Net payable",
        prior_amount=Decimal("800"),
        current_amount=Decimal("900"),
        delta_amount=Decimal("100"),
        delta_percent=Decimal("12.5"),
        severity_code="warning",
        explanation="Change is 100.00 (12.50%).",
    )
    analysis = PayrollVarianceAnalysisDTO(
        run_id=99,
        run_reference="PAY-99",
        prior_run_id=98,
        prior_run_reference="PAY-98",
        threshold_percent=Decimal("10.00"),
        lines=(line,),
    )

    class _VarianceService:
        def analyze_run(self, company_id: int, run_id: int) -> PayrollVarianceAnalysisDTO:
            assert company_id == 10
            assert run_id == 99
            return analysis

    permission = _PermissionService()
    service = PayrollDryRunReportService(_VarianceService(), permission)
    output = tmp_path / "dry_run.csv"

    result = service.export_report(10, 99, str(output), fmt="csv")

    text = output.read_text(encoding="utf-8-sig")
    assert result.warning_count == 1
    assert result.file_path == str(output)
    assert "PAY-99" in text
    assert "Net payable" in text
    assert permission.required == ["payroll.print"]