"""Offscreen smoke for the unified budget editor, revision flow, and project workspace card swap.

Exercises:
- ``ProjectBudgetService.create_version_with_lines`` atomic path (draft + empty drafts + 3-line draft)
- submit gating (>= 1 line) + approve + supersede behavior
- ``BudgetApprovalService.prepare_revision_draft`` produces fresh line numbers with base_version_id
- ``ProjectBudgetService.replace_version_lines`` replaces + recomputes total
- ``ProjectWorkspaceWindow`` budget card shows approved version lines + correct subtitle,
  ``new_budget``/``revise_budget`` ribbon state follows approved-exists
"""

from __future__ import annotations

import os
import sys
import time
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime

from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.budgeting.dto.project_budget_commands import (
    ApproveProjectBudgetVersionCommand,
    BudgetLineDraftDTO,
    CreateProjectBudgetVersionWithLinesCommand,
    SubmitProjectBudgetVersionCommand,
)
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.contracts_projects.dto.contract_dto import CreateContractCommand
from seeker_accounting.modules.contracts_projects.dto.project_dto import CreateProjectCommand
from seeker_accounting.modules.contracts_projects.dto.project_cost_code_commands import (
    CreateProjectCostCodeCommand,
)
from seeker_accounting.modules.contracts_projects.dto.project_job_commands import (
    CreateProjectJobCommand,
)
from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerCommand,
    CreateCustomerGroupCommand,
)
from seeker_accounting.platform.exceptions import ValidationError


def _seed_reference_data(registry) -> None:
    with registry.session_context.unit_of_work_factory() as uow:
        session = uow.session
        if session.get(Country, "CM") is None:
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if session.get(Currency, "XAF") is None:
            session.add(
                Currency(
                    code="XAF",
                    name="CFA Franc BEAC",
                    symbol="FCFA",
                    decimal_places=0,
                    is_active=True,
                )
            )
        uow.commit()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    runtime = bootstrap_script_runtime(
        app,
        permission_snapshot=(
            "companies.create",
            "companies.view",
            "customers.groups.create",
            "customers.groups.view",
            "customers.create",
            "customers.view",
        ),
    )
    registry = runtime.service_registry
    _seed_reference_data(registry)

    unique = str(int(time.time() * 1000))
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Budget Smoke {unique}",
            display_name=f"Budget Smoke {unique}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    company_id = company.id
    registry.company_context_service.set_active_company(company_id)

    group = registry.customer_service.create_customer_group(
        company_id,
        CreateCustomerGroupCommand(code=f"BG{unique[-4:]}", name="Budget Smoke Customers"),
    )
    customer = registry.customer_service.create_customer(
        company_id,
        CreateCustomerCommand(
            customer_group_id=group.id,
            customer_code=f"CUST{unique[-6:]}",
            display_name="Budget Smoke Customer",
            country_code="CM",
        ),
    )
    contract = registry.contract_service.create_contract(
        CreateContractCommand(
            company_id=company_id,
            contract_number=f"CTR-{unique[-6:]}",
            contract_title="Budget Smoke Contract",
            customer_id=customer.id,
            contract_type_code="fixed_price",
            currency_code="XAF",
            base_contract_amount=Decimal("1000000.00"),
            start_date=date(2026, 1, 1),
            planned_end_date=date(2026, 12, 31),
            billing_basis_code="milestone",
        )
    )
    project = registry.project_service.create_project(
        CreateProjectCommand(
            company_id=company_id,
            project_code=f"PRJ-{unique[-6:]}",
            project_name="Budget Smoke Project",
            contract_id=contract.id,
            customer_id=customer.id,
            project_type_code="external",
            currency_code="XAF",
            start_date=date(2026, 1, 15),
            planned_end_date=date(2026, 11, 30),
            budget_control_mode_code="warn",
        )
    )
    project_id = project.id

    # Activate project so Record Cost gating is correct downstream
    registry.project_service.activate_project(project_id)

    # Seed two cost codes
    cc_labour = registry.project_cost_code_service.create_cost_code(
        CreateProjectCostCodeCommand(
            company_id=company_id,
            code="LAB",
            name="Labour",
            cost_code_type_code="labour",
        )
    )
    cc_materials = registry.project_cost_code_service.create_cost_code(
        CreateProjectCostCodeCommand(
            company_id=company_id,
            code="MAT",
            name="Materials",
            cost_code_type_code="materials",
        )
    )

    # Seed one job
    job = registry.project_structure_service.create_job(
        CreateProjectJobCommand(
            company_id=company_id,
            project_id=project_id,
            job_code="J001",
            job_name="Foundation",
        )
    )

    svc = registry.project_budget_service
    approval_svc = registry.budget_approval_service

    # ── Assertion 1: create_version_with_lines, 3-line draft ─────────
    lines = (
        BudgetLineDraftDTO(
            line_number=1,
            project_cost_code_id=cc_labour.id,
            line_amount=Decimal("500000.00"),
            project_job_id=job.id,
            description="Foundation labour",
            quantity=Decimal("100"),
            unit_rate=Decimal("5000"),
        ),
        BudgetLineDraftDTO(
            line_number=2,
            project_cost_code_id=cc_materials.id,
            line_amount=Decimal("300000.00"),
            project_job_id=job.id,
            description="Foundation materials",
        ),
        BudgetLineDraftDTO(
            line_number=3,
            project_cost_code_id=cc_labour.id,
            line_amount=Decimal("200000.00"),
            description="Supervision labour",
        ),
    )
    v1 = svc.create_version_with_lines(
        CreateProjectBudgetVersionWithLinesCommand(
            company_id=company_id,
            project_id=project_id,
            version_number=1,
            version_name="Original Budget",
            version_type_code="original",
            budget_date=date(2026, 2, 1),
            lines=lines,
        )
    )
    assert v1.status_code == "draft", f"expected draft, got {v1.status_code}"
    assert v1.total_budget_amount == Decimal("1000000.00"), (
        f"total should be 1,000,000 got {v1.total_budget_amount}"
    )
    v1_line_dtos = svc.list_lines(v1.id)
    assert len(v1_line_dtos) == 3, f"expected 3 lines, got {len(v1_line_dtos)}"
    print("OK  create_version_with_lines: 3 lines, total 1,000,000")

    # ── Assertion 2: zero-line draft allowed, submit rejected ────────
    v_empty = svc.create_version_with_lines(
        CreateProjectBudgetVersionWithLinesCommand(
            company_id=company_id,
            project_id=project_id,
            version_number=99,
            version_name="Empty Draft",
            version_type_code="working",
            budget_date=date(2026, 2, 1),
            lines=(),
        )
    )
    assert v_empty.status_code == "draft"
    assert v_empty.total_budget_amount == Decimal("0")
    try:
        approval_svc.submit_version(
            SubmitProjectBudgetVersionCommand(version_id=v_empty.id, company_id=company_id)
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("submit should have failed on zero-line draft")
    print("OK  zero-line draft allowed, submit blocked")

    # ── Assertion 3: submit + approve v1 ─────────────────────────────
    submitted = approval_svc.submit_version(
        SubmitProjectBudgetVersionCommand(version_id=v1.id, company_id=company_id)
    )
    assert submitted.status_code == "submitted"
    approved = approval_svc.approve_version(
        ApproveProjectBudgetVersionCommand(
            version_id=v1.id, company_id=company_id, approved_by_user_id=1
        )
    )
    assert approved.status_code == "approved"
    current = approval_svc.get_current_approved_budget(project_id)
    assert current is not None and current.version_id == v1.id
    print("OK  submit + approve + current_approved lookup")

    # ── Assertion 4: prepare_revision_draft produces lines w/ base ──
    seed = approval_svc.prepare_revision_draft(project_id)
    assert seed is not None, "prepare_revision_draft should return a seed"
    next_number, default_name, base_version_id, draft_lines = seed
    assert next_number > v1.version_number, (
        f"next version number should be greater than {v1.version_number}, got {next_number}"
    )
    assert base_version_id == v1.id, "base_version_id should reference the approved version"
    assert len(draft_lines) == 3, "revision should start with 3 cloned lines"
    # Line numbers should be sequential from 1
    assert tuple(d.line_number for d in draft_lines) == (1, 2, 3)
    # Amounts should match
    assert sum((d.line_amount for d in draft_lines), Decimal("0")) == Decimal("1000000.00")
    print("OK  prepare_revision_draft: clone w/ fresh line numbers + base_version_id")

    # ── Assertion 5: save the revision as a new version, then modify its lines ──
    v2 = svc.create_version_with_lines(
        CreateProjectBudgetVersionWithLinesCommand(
            company_id=company_id,
            project_id=project_id,
            version_number=next_number,
            version_name=default_name,
            version_type_code="revision",
            budget_date=date(2026, 3, 1),
            lines=draft_lines,
            base_version_id=base_version_id,
            revision_reason="Increase materials allowance",
        )
    )
    assert v2.status_code == "draft"
    assert v2.total_budget_amount == Decimal("1000000.00")

    # Replace lines: reduce to 2 lines totalling 750,000
    reshaped = (
        BudgetLineDraftDTO(
            line_number=1,
            project_cost_code_id=cc_labour.id,
            line_amount=Decimal("450000.00"),
            project_job_id=job.id,
            description="Foundation labour (revised)",
        ),
        BudgetLineDraftDTO(
            line_number=2,
            project_cost_code_id=cc_materials.id,
            line_amount=Decimal("300000.00"),
            description="Materials (revised)",
        ),
    )
    v2_updated = svc.replace_version_lines(v2.id, reshaped)
    assert v2_updated.total_budget_amount == Decimal("750000.00"), (
        f"after replace, total should be 750,000 got {v2_updated.total_budget_amount}"
    )
    assert len(svc.list_lines(v2.id)) == 2
    print("OK  replace_version_lines: 2-line reshape, total recomputed")

    # v1 remains approved; v2 is still a draft, so current approved must be v1
    still_current = approval_svc.get_current_approved_budget(project_id)
    assert still_current is not None and still_current.version_id == v1.id

    # ── Assertion 6: workspace window — card shows approved v1 lines ──
    from seeker_accounting.modules.contracts_projects.ui.project_workspace_window import (
        ProjectWorkspaceWindow,
    )

    window = ProjectWorkspaceWindow(
        registry,
        company_id=company_id,
        company_name=company.legal_name,
        project_id=project_id,
    )
    for _ in range(8):
        app.processEvents()

    # Subtitle should reference v1, approved, and total 1,000,000
    subtitle = window._budgets_subtitle.text()
    assert "v1" in subtitle, f"subtitle missing version marker: {subtitle!r}"
    assert "Approved" in subtitle or "approved" in subtitle.lower(), (
        f"subtitle missing approved marker: {subtitle!r}"
    )
    assert "1,000,000" in subtitle, f"subtitle missing total: {subtitle!r}"

    # Table should list v1's 3 lines
    assert window._budgets_table.rowCount() == 3, (
        f"expected 3 line rows, got {window._budgets_table.rowCount()}"
    )

    # Buttons: revise visible, new hidden (approved exists). We use isHidden() (explicit
    # state) rather than isVisible() because the window is not shown in offscreen mode.
    assert not window._revise_budget_btn.isHidden(), "Revise should be shown when approved exists"
    assert window._new_budget_btn.isHidden(), "New Budget should be hidden when approved exists"

    # Ribbon state follows approved-exists
    state = window.ribbon_state()
    assert state["project_workspace.revise_budget"] is True
    assert state["project_workspace.new_budget"] is False
    print("OK  workspace card: subtitle + 3 lines + buttons + ribbon state")

    window.close()
    print("PASS smoke_budgeting_unified_editor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
