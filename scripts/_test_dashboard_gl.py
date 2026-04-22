"""Quick smoke test for dashboard GL balance queries."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine, func, and_, select
from sqlalchemy.orm import Session
# Load all models so relationships resolve
from seeker_accounting.db.model_registry import load_model_registry
load_model_registry()
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")

def gl_balance(session, company_id, class_code, date_from=None, date_to=None):
    conditions = [
        JournalEntry.company_id == company_id,
        JournalEntry.status_code == "POSTED",
        AccountClass.code == class_code,
    ]
    if date_from:
        conditions.append(JournalEntry.entry_date >= date_from)
    if date_to:
        conditions.append(JournalEntry.entry_date <= date_to)
    stmt = (
        select(
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("debit"),
            func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("credit"),
        )
        .select_from(JournalEntryLine)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .join(AccountClass, AccountClass.id == Account.account_class_id)
        .where(and_(*conditions))
    )
    row = session.execute(stmt).one()
    d = Decimal(str(row.debit)) if row.debit else Decimal(0)
    c = Decimal(str(row.credit)) if row.credit else Decimal(0)
    return d, c

with Session(engine) as s:
    for cls, name in [("5", "Treasury"), ("6", "Expenses"), ("7", "Revenue")]:
        d, c = gl_balance(s, 1, cls)
        print(f"Class {cls} ({name}) ALL TIME:  debit={d:>15,}  credit={c:>15,}  net(D-C)={d-c:>15,}")
    
    print()
    # Current period (March 2026)
    for cls, name in [("6", "Expenses"), ("7", "Revenue")]:
        d, c = gl_balance(s, 1, cls, date(2026, 3, 1), date(2026, 3, 31))
        print(f"Class {cls} ({name}) Mar 2026:  debit={d:>15,}  credit={c:>15,}  net(D-C)={d-c:>15,}")
    
    # April 2026 (current month - should be empty since seed only goes to Mar)
    for cls, name in [("6", "Expenses"), ("7", "Revenue")]:
        d, c = gl_balance(s, 1, cls, date(2026, 4, 1), date(2026, 4, 30))
        print(f"Class {cls} ({name}) Apr 2026:  debit={d:>15,}  credit={c:>15,}  net(D-C)={d-c:>15,}")
