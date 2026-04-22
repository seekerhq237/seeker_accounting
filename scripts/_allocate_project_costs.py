"""Allocate project/job/cost-code references to existing expense JE lines.

~70% of expense lines get allocated to give realistic job-cost data.
Overhead items (rent, utilities, insurance) stay unallocated or go to overhead.
Purchase-related and payroll expenses get allocated to active projects.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, text
import random

RNG = random.Random(42)

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")

with engine.begin() as conn:
    # Load projects
    projects = conn.execute(text(
        "SELECT id, project_code, status_code, contract_id FROM projects ORDER BY id"
    )).fetchall()
    active_projects = [p for p in projects if p.status_code == "active"]
    all_projects = list(projects)
    print(f"Projects: {len(all_projects)} total, {len(active_projects)} active")

    # Load jobs grouped by project
    jobs_by_project = {}
    all_jobs = conn.execute(text(
        "SELECT id, project_id, job_code FROM project_jobs ORDER BY id"
    )).fetchall()
    for j in all_jobs:
        jobs_by_project.setdefault(j.project_id, []).append(j)
    print(f"Jobs: {len(all_jobs)} total")

    # Load cost codes
    cost_codes = conn.execute(text(
        "SELECT id, code, name FROM project_cost_codes ORDER BY id"
    )).fetchall()
    cc_by_code = {c.code: c.id for c in cost_codes}
    print(f"Cost codes: {len(cost_codes)}")

    # Load expense JE lines (debit side on class 6)
    expense_lines = conn.execute(text("""
        SELECT jel.id, je.entry_date, je.description, a.account_code, jel.debit_amount
        FROM journal_entry_lines jel
        JOIN journal_entries je ON je.id = jel.journal_entry_id
        JOIN accounts a ON a.id = jel.account_id
        JOIN account_classes ac ON ac.id = a.account_class_id
        WHERE ac.code = '6' AND jel.debit_amount > 0 AND je.status_code = 'POSTED'
        ORDER BY je.entry_date
    """)).fetchall()
    print(f"Expense JE lines: {len(expense_lines)}")

    # Map account codes to likely cost code categories
    acct_to_cc = {
        "601": "MAT",   # Purchases → Materials
        "602": "SUB",   # External services → Subcontractor
        "628": "OVH",   # Telecom → Overhead
        "661": "LAB",   # Salaries → Labour
        "664": "LAB",   # Social charges → Labour
        "624": "EQP",   # Maintenance → Equipment
        "632": "SUB",   # Professional fees → Subcontractor
    }

    # Allocation rules:
    # - Rent (6222), Insurance (625) → NOT allocated (pure overhead)
    # - Purchases (601), External services (602) → allocated to project ~75%
    # - Salaries (661), Social charges (664) → allocated to project ~60%
    # - Maintenance (624) → allocated ~50%
    # - Telecom (628) → allocated ~30%
    allocatable_rates = {
        "601": 0.80,
        "602": 0.80,
        "628": 0.30,
        "661": 0.65,
        "664": 0.65,
        "624": 0.50,
        "632": 0.70,
    }

    updated = 0
    for line in expense_lines:
        line_id, entry_date, desc, acct_code, amount = line

        # Skip non-allocatable overhead
        rate = allocatable_rates.get(acct_code, 0)
        if rate == 0 or RNG.random() > rate:
            continue

        # Pick a project based on timeline
        # Use all projects for variety, weight towards active ones
        year = entry_date.year if isinstance(entry_date, str) is False else int(entry_date[:4])

        # Completed projects were active in 2024
        if year == 2024:
            eligible = all_projects
        else:
            eligible = active_projects if active_projects else all_projects

        proj = RNG.choice(eligible)
        proj_id = proj.id

        # Pick a job for this project
        proj_jobs = jobs_by_project.get(proj_id, [])
        job_id = RNG.choice(proj_jobs).id if proj_jobs else None

        # Pick cost code based on account
        cc_code = acct_to_cc.get(acct_code, "OVH")
        cc_id = cc_by_code.get(cc_code, cc_by_code.get("OVH"))

        conn.execute(text("""
            UPDATE journal_entry_lines
            SET project_id = :pid, project_job_id = :jid, project_cost_code_id = :ccid
            WHERE id = :lid
        """), {"pid": proj_id, "jid": job_id, "ccid": cc_id, "lid": line_id})
        updated += 1

    print(f"\nAllocated {updated} / {len(expense_lines)} expense lines to projects")

    # Verify
    counts = conn.execute(text("""
        SELECT COUNT(project_id), COUNT(DISTINCT project_id), COUNT(DISTINCT project_job_id), COUNT(DISTINCT project_cost_code_id)
        FROM journal_entry_lines
        WHERE project_id IS NOT NULL
    """)).one()
    print(f"Lines with project: {counts[0]}, distinct projects: {counts[1]}, distinct jobs: {counts[2]}, distinct cost codes: {counts[3]}")

    # Sample
    rows = conn.execute(text("""
        SELECT jel.id, p.project_code, pj.job_code, pcc.code as cc_code, jel.debit_amount
        FROM journal_entry_lines jel
        JOIN projects p ON p.id = jel.project_id
        LEFT JOIN project_jobs pj ON pj.id = jel.project_job_id
        LEFT JOIN project_cost_codes pcc ON pcc.id = jel.project_cost_code_id
        LIMIT 10
    """)).fetchall()
    print("\nSample allocations:")
    for r in rows:
        print(f"  Line {r[0]}: {r[1]} / {r[2]} / {r[3]}  amount={r[4]}")
