"""Centralized contextual help content for every page and dialog in Seeker Accounting.

Each entry is a ``HelpArticle`` keyed by a help-key string.
Convention:
  - Pages use the ``nav_id`` directly (e.g. ``"customers"``).
  - Dialogs use ``"dialog.<descriptive_name>"`` (e.g. ``"dialog.customer"``).

The ``body_html`` field supports simple HTML (bold, lists, paragraphs).  Keep
content practical, concise, and helpful for a business user — not a developer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HelpArticle:
    key: str
    title: str
    summary: str
    body_html: str


# ---------------------------------------------------------------------------
# Content registry
# ---------------------------------------------------------------------------

HELP_CONTENT: dict[str, HelpArticle] = {}


def _register(key: str, title: str, summary: str, body_html: str) -> None:
    HELP_CONTENT[key] = HelpArticle(key=key, title=title, summary=summary, body_html=body_html)


# ═══════════════════════════════════════════════════════════════════════════
#  PAGES
# ═══════════════════════════════════════════════════════════════════════════

# ── Dashboard ─────────────────────────────────────────────────────────────

_register(
    "dashboard",
    "Home",
    "Your at-a-glance overview of cash position, receivables, payables, activity, and items needing attention.",
    """
    <p>The <b>Home</b> page is your daily starting point. It aggregates the
    most important financial signals for the active company into a single,
    calm overview.</p>

    <h3>KPI Strip</h3>
    <p>Six key figures appear at the top of the page:</p>
    <ul>
      <li><b>Cash Position</b> — current total across cash and bank accounts.</li>
      <li><b>Receivables Due</b> — outstanding customer invoices.</li>
      <li><b>Payables Due</b> — outstanding supplier bills.</li>
      <li><b>Month Revenue</b> — revenue recognised in the current fiscal month.</li>
      <li><b>Month Expenses</b> — expenses recorded in the current fiscal month.</li>
      <li><b>Pending Postings</b> — number of draft documents awaiting posting.</li>
    </ul>

    <h3>Recent Activity</h3>
    <p>A chronological table of the latest journals, invoices, and bills
    across the company. Each row shows the document type, reference number,
    counterparty, amount, and current status.</p>

    <h3>Tasks Requiring Attention</h3>
    <p>A prioritised list of items that may need action, such as:</p>
    <ul>
      <li>Overdue customer invoices</li>
      <li>Overdue supplier bills</li>
      <li>Draft documents waiting to be posted</li>
      <li>Fiscal period close reminders</li>
    </ul>

    <h3>Aging Snapshots</h3>
    <p>Visual summaries of accounts receivable and accounts payable aging
    broken down into standard buckets (Current, 1–30, 31–60, 61–90, 90+).
    The segmented bar provides a quick sense of concentration.</p>

    <h3>Quick Actions</h3>
    <p>Shortcut buttons for the most common workflows: creating a new
    journal entry, invoice, receipt, bill, supplier payment, or inventory
    item. Each button navigates directly to the relevant creation form.</p>

    <p><b>Tip:</b> The page refreshes automatically when you switch companies.
    Select a company from the sidebar or top bar to see its data.</p>
    """,
)

# ── Customers ─────────────────────────────────────────────────────────────

_register(
    "customers",
    "Customers",
    "Manage your company's customer master data.",
    """
    <p>The <b>Customers</b> page shows all customers for the active company.
    Each customer record holds identity, contact, and payment term information
    used across sales invoices and receipts.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create a customer</b> — click <em>New Customer</em> to open the
          creation dialog.</li>
      <li><b>Edit a customer</b> — double-click a row or select it and click
          <em>Edit</em>.</li>
      <li><b>Search</b> — type in the search bar to filter by name, code, or
          contact information.</li>
    </ul>

    <p><b>Readiness signal:</b> The page shows whether the Accounts Receivable
    control account mapping is configured. This mapping is required before
    sales invoices can be posted.</p>

    <p><b>Tip:</b> Customer codes should be unique within a company. Use a
    clear, consistent naming convention (e.g. CUST-001).</p>

    <p><b>Example:</b> A typical customer list might include:
    <br/>↕ CUST-001 | Brasseries du Cameroun | Net 30 | 5,000,000 limit
    <br/>↕ CUST-002 | SABC Douala | Net 15 | 2,000,000 limit
    <br/>↕ CUST-003 | Ets Nkamga | COD | No limit
    <br/>Start by creating your most active customers, then add others
    as invoices arise.</p>
    """,
)

# ── Suppliers ─────────────────────────────────────────────────────────────

_register(
    "suppliers",
    "Suppliers",
    "Manage your company's supplier master data.",
    """
    <p>The <b>Suppliers</b> page shows all suppliers for the active company.
    Supplier records hold identity, contact, and payment term information
    used across purchase bills and payments.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create a supplier</b> — click <em>New Supplier</em>.</li>
      <li><b>Edit a supplier</b> — double-click a row or select and click
          <em>Edit</em>.</li>
      <li><b>Search</b> — type in the search bar to filter by name, code, or
          contact.</li>
    </ul>

    <p><b>Readiness signal:</b> The page shows whether the Accounts Payable
    control account mapping is configured. This is required before purchase
    bills can be posted.</p>

    <p><b>Example:</b> A typical supplier list:
    <br/>↕ SUPP-001 | Cimencam | Net 30 | Cement &amp; building materials
    <br/>↕ SUPP-002 | CAMTEL | Net 15 | Telecom services
    <br/>↕ SUPP-003 | Total Cameroun | COD | Fuel
    <br/>Create key suppliers first, setting their default payment terms
    and tax codes to speed up bill entry later.</p>
    """,
)

# ── Payment Terms ─────────────────────────────────────────────────────────

_register(
    "payment_terms",
    "Payment Terms",
    "Define standard payment due-date terms for customers and suppliers.",
    """
    <p><b>Payment Terms</b> define how and when invoices are due. Each term
    has a code, a name, and a number of days until the due date.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Payment Term</em> to create a term (e.g. "Net 30").</li>
      <li>Assign terms to customers or suppliers in their master records.</li>
      <li>When creating a sales invoice or purchase bill, the due date is
          calculated automatically from the assigned payment term.</li>
    </ul>

    <p><b>Tip:</b> Common payment terms include Net 30, Net 60, and
    Immediate. You can create custom terms to match your business agreements.</p>
    """,
)

# ── Tax Codes ─────────────────────────────────────────────────────────────

_register(
    "tax_codes",
    "Tax Codes",
    "Define and manage company tax rates and account mappings.",
    """
    <p><b>Tax Codes</b> represent the different tax rates your company applies
    to sales and purchases (e.g. VAT 19.25%, VAT Exempt).</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Tax Code</em> to define a tax rate.</li>
      <li>Each tax code has a code, name, rate percentage, and linked
          GL accounts for tax collected and tax paid.</li>
      <li>Tax codes are assigned on invoice and bill line items to
          calculate tax amounts automatically.</li>
    </ul>

    <p><b>Account mapping:</b> Each tax code must be mapped to appropriate
    GL accounts so that tax amounts post correctly to the general ledger.</p>

    <p><b>Tip:</b> Set up all required tax codes before creating sales
    invoices or purchase bills.</p>
    """,
)

# ── Document Sequences ────────────────────────────────────────────────────

_register(
    "document_sequences",
    "Document Sequences",
    "Configure automatic document numbering for invoices, bills, and other documents.",
    """
    <p><b>Document Sequences</b> control how the system assigns reference
    numbers to invoices, receipts, bills, payments, and journal entries.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Sequence</em> to define a numbering pattern.</li>
      <li>Each sequence has a prefix, a starting number, and a step.</li>
      <li>Sequences are linked to specific document types and operate
          per company.</li>
    </ul>

    <p><b>Example:</b> A sales invoice sequence with prefix "INV-" and
    start 1000 will produce INV-1000, INV-1001, INV-1002, etc.</p>

    <p><b>Tip:</b> Set up sequences before creating any business documents.
    Once documents have been issued, avoid changing the sequence prefix.</p>
    """,
)

# ── Account Role Mappings ─────────────────────────────────────────────────

_register(
    "account_role_mappings",
    "Account Role Mappings",
    "Assign control account roles to specific GL accounts.",
    """
    <p><b>Account Role Mappings</b> connect system-defined roles (like
    Accounts Receivable, Accounts Payable, Sales Revenue, etc.) to the
    specific GL accounts in your chart of accounts.</p>

    <p><b>Why this matters:</b></p>
    <ul>
      <li>When a sales invoice is posted, the system needs to know which
          account is the AR control account.</li>
      <li>When a purchase bill is posted, it needs the AP control account.</li>
      <li>Revenue, COGS, bank, and other roles must also be mapped.</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>For each role listed, select the appropriate GL account from
          your chart of accounts.</li>
      <li>The system will prevent posting if required role mappings are
          missing.</li>
    </ul>

    <p><b>Tip:</b> Complete all required role mappings after setting up your
    chart of accounts and before processing any transactions.</p>
    """,
)

# ── Chart of Accounts ─────────────────────────────────────────────────────

_register(
    "chart_of_accounts",
    "Chart of Accounts",
    "View and manage the company's hierarchical account structure.",
    """
    <p>The <b>Chart of Accounts</b> is the foundational structure of your
    accounting system. It organises all GL accounts into a tree hierarchy
    grouped by class: Assets, Liabilities, Equity, Revenue, and Expenses.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create an account</b> — click <em>New Account</em>.</li>
      <li><b>Edit an account</b> — double-click a row.</li>
      <li><b>Search</b> — filter by account code or name.</li>
      <li><b>Seed OHADA chart</b> — use the <em>Seed</em> button to
          populate the standard OHADA chart of accounts.</li>
      <li><b>Import</b> — use the <em>Import</em> button to load accounts
          from a spreadsheet file.</li>
    </ul>

    <p><b>Key concepts:</b></p>
    <ul>
      <li><b>Account code</b> — a unique numeric code (e.g. 401, 601).</li>
      <li><b>Parent account</b> — allows nesting for hierarchical
          reporting.</li>
      <li><b>Control account</b> — accounts linked to subledgers (AR, AP)
          that must reconcile to their source documents.</li>
      <li><b>Allow manual posting</b> — only accounts with this flag can
          receive direct journal entries.</li>
    </ul>

    <p><b>Tip:</b> Follow the OHADA numbering convention if your business
    operates in the OHADA zone. Use parent accounts for grouping — only
    leaf accounts should receive postings.</p>
    """,
)

# ── Fiscal Periods ────────────────────────────────────────────────────────

_register(
    "fiscal_periods",
    "Fiscal Periods",
    "Manage fiscal years and their monthly accounting periods.",
    """
    <p><b>Fiscal Periods</b> divide your accounting year into monthly
    periods. Each period can be opened, closed, or locked to control
    when transactions can be posted.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create a fiscal year</b> — click <em>New Fiscal Year</em>
          and specify start/end dates.</li>
      <li><b>Generate periods</b> — the system can automatically generate
          12 monthly periods for a fiscal year.</li>
      <li><b>Close a period</b> — once all entries are finalised, close
          the period to prevent further posting.</li>
      <li><b>Lock a period</b> — lock for permanent immutability after
          audit or regulatory sign-off.</li>
    </ul>

    <p><b>Important:</b></p>
    <ul>
      <li>Transactions can only be posted to <em>open</em> periods.</li>
      <li>Closing a period is reversible; locking is not.</li>
      <li>Year-end close creates the necessary closing entries.</li>
    </ul>

    <p><b>Tip:</b> Close periods promptly after month-end to maintain
    accounting discipline and prevent backdated entries.</p>
    """,
)

# ── Journals ──────────────────────────────────────────────────────────────

_register(
    "journals",
    "Journal",
    "View, create, and manage journal entries — the core of double-entry accounting.",
    """
    <p><b>Journal</b> is where accounting truth lives. Every financial
    transaction ultimately becomes a journal entry with balanced debit
    and credit lines.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create an entry</b> — click <em>New Entry</em>.</li>
      <li><b>View entries</b> — browse existing entries filtered by
          period, status, or search text.</li>
      <li><b>Post an entry</b> — draft entries must be explicitly posted
          to become part of the accounting record.</li>
    </ul>

    <p><b>Key rules:</b></p>
    <ul>
      <li>Every entry must balance — total debits must equal total credits.</li>
      <li>Posted entries are immutable. To correct them, create a
          reversing entry.</li>
      <li>Entries can only be posted to open fiscal periods.</li>
      <li>System-generated entries (from invoices, bills, etc.) are
          marked with their source document.</li>
    </ul>

    <p><b>Tip:</b> Use meaningful descriptions on entries and lines.
    This makes audit trails and reporting much clearer.</p>
    """,
)

# ── Sales Invoices ────────────────────────────────────────────────────────

_register(
    "sales_invoices",
    "Sales Invoices",
    "Create, manage, and post sales invoices to record revenue.",
    """
    <p><b>Sales Invoices</b> are source documents that record amounts owed
    by your customers. When posted, they create journal entries that debit
    Accounts Receivable and credit Revenue accounts.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create a sales invoice</b> — click <em>New Invoice</em>,
          select a customer, add line items with quantities and prices.</li>
      <li><b>Tax</b> — assign tax codes to line items for automatic
          tax calculation.</li>
      <li><b>Post</b> — posting creates the GL journal entry. Draft
          invoices have no accounting impact.</li>
      <li><b>Void</b> — posted invoices can be voided, which creates
          a reversing journal entry.</li>
    </ul>

    <p><b>Prerequisites:</b></p>
    <ul>
      <li>At least one customer must exist.</li>
      <li>AR control account role mapping must be configured.</li>
      <li>Revenue account role mapping must be configured.</li>
      <li>A document sequence for sales invoices must be set up.</li>
    </ul>

    <p><b>Tip:</b> Always review line totals and tax amounts before posting.
    Posted invoices cannot be edited — they can only be voided.</p>
    """,
)

# ── Customer Receipts ─────────────────────────────────────────────────────

_register(
    "customer_receipts",
    "Customer Receipts",
    "Record payments received from customers against outstanding invoices.",
    """
    <p><b>Customer Receipts</b> record incoming payments from customers.
    When posted, they debit the Bank/Cash account and credit the
    Accounts Receivable control account.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create a receipt</b> — click <em>New Receipt</em>, select
          the customer and the financial account receiving the payment.</li>
      <li><b>Allocate</b> — link the receipt to one or more outstanding
          invoices to clear the receivable balance.</li>
      <li><b>Post</b> — posting creates the GL journal entry.</li>
    </ul>

    <p><b>Tip:</b> Allocate receipts to invoices promptly to keep the
    AR aging report accurate and customer balances up to date.</p>

    <p><b>Example:</b> Receiving 2,000,000 XAF from Brasseries du Cameroun:
    <br/>↕ 1. Create receipt: Customer = Brasseries, Amount = 2,000,000
    <br/>↕ 2. Financial account = Afriland First Bank
    <br/>↕ 3. Allocate: INV-2026-042 (566,438 fully) + INV-2026-055
    (1,433,562 partial)
    <br/>↕ 4. Post: Debit 521100 Bank 2,000,000 | Credit 411000 AR
    2,000,000
    <br/>INV-2026-042 is now fully paid; INV-2026-055 has a remaining
    balance.</p>
    """,
)

# ── Purchase Bills ────────────────────────────────────────────────────────

_register(
    "purchase_bills",
    "Purchase Bills",
    "Record purchase bills from suppliers to track payables and expenses.",
    """
    <p><b>Purchase Bills</b> are source documents that record amounts you
    owe to suppliers. When posted, they create journal entries that debit
    Expense/Asset accounts and credit Accounts Payable.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create a bill</b> — click <em>New Bill</em>, select a
          supplier, add line items with amounts and expense accounts.</li>
      <li><b>Tax</b> — assign tax codes for input tax calculation.</li>
      <li><b>Post</b> — posting creates the GL journal entry.</li>
    </ul>

    <p><b>Prerequisites:</b></p>
    <ul>
      <li>At least one supplier must exist.</li>
      <li>AP control account role mapping must be configured.</li>
    </ul>

    <p><b>Tip:</b> Enter the supplier's invoice reference number in the
    external reference field for easy reconciliation.</p>
    """,
)

# ── Supplier Payments ─────────────────────────────────────────────────────

_register(
    "supplier_payments",
    "Supplier Payments",
    "Record payments made to suppliers against outstanding bills.",
    """
    <p><b>Supplier Payments</b> record outgoing payments to suppliers.
    When posted, they debit Accounts Payable and credit the Bank/Cash
    account.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create a payment</b> — click <em>New Payment</em>, select
          the supplier and the financial account paying from.</li>
      <li><b>Allocate</b> — link the payment to outstanding bills.</li>
      <li><b>Post</b> — posting creates the GL journal entry.</li>
    </ul>

    <p><b>Tip:</b> Allocate payments to bills promptly to keep the
    AP aging report accurate.</p>

    <p><b>Example:</b> Paying 1,508,513 XAF to Cimencam:
    <br/>↕ 1. Create payment: Supplier = Cimencam, Amount = 1,508,513
    <br/>↕ 2. Financial account = Afriland First Bank
    <br/>↕ 3. Allocate fully to BILL-2026-031
    <br/>↕ 4. Post: Debit 401000 AP 1,508,513 | Credit 521100 Bank
    1,508,513
    <br/>BILL-2026-031 is now fully paid and will no longer appear
    in the AP aging report.</p>
    """,
)

# ── Financial Accounts ────────────────────────────────────────────────────

_register(
    "financial_accounts",
    "Financial Accounts",
    "Manage bank accounts, cash accounts, and other financial holding accounts.",
    """
    <p><b>Financial Accounts</b> represent your real-world bank accounts,
    petty cash funds, and other financial holding accounts.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create an account</b> — click <em>New Account</em> and
          specify the bank name, account number, currency, and linked
          GL account.</li>
      <li><b>Edit</b> — update details like bank name or opening balance.</li>
    </ul>

    <p><b>Key concepts:</b></p>
    <ul>
      <li>Each financial account is linked to a GL account in the
          chart of accounts.</li>
      <li>Receipts and payments reference a financial account to
          determine which bank/cash account is affected.</li>
      <li>Bank reconciliation operates on financial accounts.</li>
    </ul>

    <p><b>Tip:</b> Set up a financial account for every real bank account
    and petty cash fund your company uses.</p>
    """,
)

# ── Treasury Transactions ─────────────────────────────────────────────────

_register(
    "treasury_transactions",
    "Treasury Transactions",
    "View and manage cash and bank transactions across financial accounts.",
    """
    <p><b>Treasury Transactions</b> shows all cash and bank transactions
    recorded against your financial accounts — including receipts,
    payments, transfers, and manual adjustments.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Filter by financial account, date range, or status.</li>
      <li>Create manual transactions for items not originating from
          invoices or bills (e.g. bank charges, interest).</li>
      <li>View the running balance for each financial account.</li>
    </ul>

    <p><b>Tip:</b> Regularly review treasury transactions to ensure
    all bank activity is captured before reconciliation.</p>

    <p><b>Example:</b> Recording a bank charge manually:
    <br/>↕ 1. Click <em>New Transaction</em>
    <br/>↕ 2. Account: Afriland First Bank
    <br/>↕ 3. Type: Disbursement | Amount: 15,000 XAF
    <br/>↕ 4. Counterpart: 631000 — Bank Charges
    <br/>↕ 5. Reference: March bank fee
    <br/>↕ 6. Post: Debit 631000 Bank Charges 15,000 | Credit 521100
    Bank 15,000.</p>
    """,
)

# ── Treasury Transfers ────────────────────────────────────────────────────

_register(
    "treasury_transfers",
    "Treasury Transfers",
    "Record transfers between your company's financial accounts.",
    """
    <p><b>Treasury Transfers</b> move money between your own financial
    accounts — for example, transferring funds from a bank account to
    a petty cash fund, or between two bank accounts.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Transfer</em>, select the source and destination
          financial accounts, and enter the amount.</li>
      <li>Posting creates balanced journal entries: debit destination
          account, credit source account.</li>
    </ul>

    <p><b>Tip:</b> Transfers between your own accounts should always
    balance. The system ensures both sides are recorded together.</p>
    """,
)

# ── Statement Lines ───────────────────────────────────────────────────────

_register(
    "statement_lines",
    "Bank Statements",
    "Import and review bank statement lines for reconciliation.",
    """
    <p><b>Bank Statements</b> lets you import statement data from your
    bank and review individual statement lines before reconciliation.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Import</b> — click <em>Import Statement</em> to load a
          bank statement file (CSV or supported format).</li>
      <li><b>Review</b> — inspect each line for accuracy.</li>
      <li><b>Manual entry</b> — add statement lines manually if needed.</li>
      <li>Statement lines are matched to treasury transactions during
          bank reconciliation.</li>
    </ul>

    <p><b>Tip:</b> Import statements regularly to keep bank reconciliation
    up to date.</p>

    <p><b>Example workflow:</b>
    <br/>↕ 1. Download the CSV statement from your bank portal.
    <br/>↕ 2. Click <em>Import Statement</em> and select the file.
    <br/>↕ 3. Map CSV columns (date, description, debit, credit, balance).
    <br/>↕ 4. Preview the imported lines and confirm.
    <br/>↕ 5. Imported lines appear in the list, ready for matching during
    bank reconciliation.
    <br/>Each line shows the bank's transaction date, description,
    and amount. Unmatched lines need corresponding treasury
    transactions created or matched.</p>
    """,
)

# ── Bank Reconciliation ──────────────────────────────────────────────────

_register(
    "bank_reconciliation",
    "Bank Reconciliation",
    "Match bank statement lines with system transactions to reconcile balances.",
    """
    <p><b>Bank Reconciliation</b> is the process of matching your internal
    treasury transactions against imported bank statement lines to ensure
    your books agree with the bank.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Select</b> a financial account and reconciliation period.</li>
      <li><b>Match</b> — pair statement lines with system transactions.</li>
      <li><b>Auto-match</b> — the system can suggest matches based on
          amount and date.</li>
      <li><b>Complete</b> — once all lines are matched, mark the
          reconciliation as complete.</li>
    </ul>

    <p><b>Key concepts:</b></p>
    <ul>
      <li>Unmatched items indicate missing entries or timing differences.</li>
      <li>The reconciliation difference must be zero to complete.</li>
    </ul>

    <p><b>Tip:</b> Reconcile monthly, promptly after receiving your bank
    statement. Investigate and resolve all unmatched items.</p>
    """,
)

# ── Units of Measure ──────────────────────────────────────────────────────


# ── Units of Measure (UoM) ──────────────────────────────────────────────
_register(
        "units_of_measure",
        "Units of Measure (UoM)",
        "Define and control how items are measured, counted, and converted.",
        """
        <p><b>Units of Measure (UoM)</b> define how your inventory and operational items are counted, tracked, and converted. Examples include: pieces, cartons, pallets, kilograms, liters, drums, etc.</p>

        <p><b>Why use structured UoMs?</b></p>
        <ul>
            <li>Ensures consistency: prevents confusion between similar units (e.g. 'box' vs 'carton').</li>
            <li>Enables automatic conversion: e.g. sales in cartons, stock in pieces, purchases in pallets.</li>
            <li>Supports accurate reporting and costing across all documents.</li>
            <li>Prevents errors from free-text or ad hoc units.</li>
        </ul>

        <p><b>How to use:</b></p>
        <ul>
            <li>Click <em>New Unit</em> to define a UoM. Each unit has a code (e.g. "PCS"), a name, an optional description, and (optionally) a category and conversion ratio.</li>
            <li>Assign the correct UoM to each inventory item. Use categories for related units (see below).</li>
            <li>Set up all commonly used units before creating inventory items.</li>
        </ul>

        <p><b>Example 1: Packaging (Pieces, Cartons, Pallets)</b></p>
        <ul>
            <li><b>Category:</b> Packaging</li>
            <li><b>PCS</b> (Piece) — base unit, ratio 1</li>
            <li><b>CTN</b> (Carton) — ratio 12 (1 carton = 12 pieces)</li>
            <li><b>PLT</b> (Pallet) — ratio 480 (1 pallet = 40 cartons = 480 pieces)</li>
        </ul>
        <p>System can convert between these automatically for receipts, sales, and stock counts.</p>

        <p><b>Example 2: Liquids (Milliliters, Liters, Drums)</b></p>
        <ul>
            <li><b>Category:</b> Volume</li>
            <li><b>ML</b> (Milliliter) — base unit, ratio 1</li>
            <li><b>L</b> (Liter) — ratio 1000 (1 liter = 1000 ml)</li>
            <li><b>DRM</b> (Drum) — ratio 200000 (1 drum = 200 liters = 200,000 ml)</li>
        </ul>
        <p>Allows you to purchase in drums, stock in liters, and sell in milliliters with full traceability.</p>

        <p><b>Best Practice:</b> Use clear codes and group related units in categories. Avoid free-text units to ensure data integrity and reporting accuracy.</p>
        """,
)

# ── UoM Categories ──────────────────────────────────────────────────────
_register(
        "uom_categories",
        "UoM Categories",
        "Group related units for conversion and control.",
        """
        <p><b>UoM Categories</b> let you group related units of measure for automatic conversion and validation. Each category defines a logical group (e.g. Packaging, Volume, Weight) where units can be converted using defined ratios.</p>

        <p><b>Why use categories?</b></p>
        <ul>
            <li>Prevents mixing incompatible units (e.g. you cannot convert 'Carton' to 'Liter').</li>
            <li>Enables the system to convert between units within the same category (e.g. PCS, CTN, PLT in Packaging).</li>
            <li>Improves reporting and operational control.</li>
        </ul>

        <p><b>How to use:</b></p>
        <ul>
            <li>Click <em>New Category</em> to define a group (e.g. Packaging, Volume, Weight).</li>
            <li>Assign each UoM to the correct category. Only units in the same category can be converted.</li>
            <li>Assign categories to items for correct stock and transaction handling.</li>
        </ul>

        <p><b>Examples:</b></p>
        <ul>
            <li><b>Packaging:</b> PCS, CTN, PLT</li>
            <li><b>Volume:</b> ML, L, DRM</li>
        </ul>

        <p><b>Tip:</b> Always use categories for any units that need conversion or grouping. This ensures the system can handle all operational and reporting needs correctly.</p>
        """,
)

# ── Item Categories ───────────────────────────────────────────────────────

_register(
    "item_categories",
    "Item Categories",
    "Organise inventory items into categories for reporting and management.",
    """
    <p><b>Item Categories</b> let you group inventory items for easier
    management, reporting, and — critically — automatic GL account
    assignment. When you assign an item to a category, the category's
    default accounts are used for posting inventory receipts, COGS,
    and revenue.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Category</em> to create a category.</li>
      <li>Set the default GL accounts for each category.</li>
      <li>Assign a category to each item in the item master.</li>
    </ul>

    <p><b>GL account mappings per category:</b></p>
    <ul>
      <li><b>Inventory account</b> — balance sheet account for stock
          on hand (e.g. 31 — Merchandise Inventory).</li>
      <li><b>COGS account</b> — expense account for cost of goods
          sold (e.g. 601 — Purchases of Goods).</li>
      <li><b>Revenue account</b> — income account for sales
          (e.g. 701 — Sales of Goods).</li>
      <li><b>Stock adjustment account</b> — used for inventory
          adjustments and write-offs.</li>
    </ul>

    <p><b>Example category structure:</b></p>
    <ul>
      <li><em>RAW</em> — Raw Materials (class 32 inventory, class 602
          COGS)</li>
      <li><em>FIN</em> — Finished Goods (class 35 inventory, class 601
          COGS, class 701 revenue)</li>
      <li><em>SPARE</em> — Spare Parts (class 36 inventory)</li>
      <li><em>OFFICE</em> — Office Supplies (class 60 expense, no
          inventory tracking)</li>
    </ul>

    <p><b>Costing methods:</b> Each category can use a different costing
    method (Weighted Average, FIFO, or Standard Cost). All items within
    a category share the same method. Choose carefully — changing later
    requires recalculation of all stock values.</p>

    <p><b>Tip:</b> Well-structured categories with correct GL mappings
    ensure that inventory transactions automatically post to the right
    accounts. Incorrect mappings lead to misstated financial statements.</p>
    """,
)

# ── Inventory Locations ──────────────────────────────────────────────────

_register(
    "inventory_locations",
    "Inventory Locations",
    "Define warehouse and storage locations where inventory is held.",
    """
    <p><b>Inventory Locations</b> represent physical places where your
    company stores goods — warehouses, storage rooms, depot sites, or
    designated bin areas within a larger facility.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Location</em> to add a storage location.</li>
      <li>Locations are referenced when creating inventory documents
          (receipts, issues, transfers).</li>
      <li>Stock queries and reports can be filtered or grouped by
          location.</li>
    </ul>

    <p><b>Example location structure:</b></p>
    <ul>
      <li><em>MAIN-WH</em> — Main Warehouse (Douala)</li>
      <li><em>SITE-A</em> — Construction Site A (Yaoundé)</li>
      <li><em>SHOP</em> — Retail Showroom</li>
      <li><em>TRANSIT</em> — Goods in Transit (for items between
          locations)</li>
    </ul>

    <p><b>Multi-warehouse management:</b> If your company operates
    from multiple sites, create a location for each. When goods move
    between sites, use <em>Transfer</em> inventory documents to record
    the movement. This keeps location-level stock quantities accurate
    and lets you run stock valuation reports per location.</p>

    <p><b>Tip:</b> Create a location for each distinct place where
    someone might go to find physical goods. Avoid creating locations
    that are too granular (e.g. individual shelves) unless you genuinely
    need that level of tracking — it adds tagging overhead to every
    inventory movement.</p>
    """,
)

# ── Items ─────────────────────────────────────────────────────────────────

_register(
    "items",
    "Items",
    "Manage your company's inventory item master data.",
    """
    <p>The <b>Items</b> page is where you define and manage all inventory
    items — products, materials, and other goods your company buys, sells,
    or holds in stock.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create an item</b> — click <em>New Item</em> and fill in
          the code, name, category, unit of measure, and pricing.</li>
      <li><b>Edit</b> — double-click an item to modify its details.</li>
      <li><b>Search</b> — filter by code, name, or category.</li>
    </ul>

    <p><b>Key fields:</b></p>
    <ul>
      <li><b>Item code</b> — unique identifier within the company.</li>
      <li><b>Category</b> — determines default GL accounts.</li>
      <li><b>Unit of measure</b> — how the item is counted.</li>
      <li><b>Cost price / Selling price</b> — default prices for
          purchase and sales documents.</li>
    </ul>

    <p><b>Tip:</b> Keep item codes consistent and descriptive. Use
    categories to set sensible GL account defaults.</p>

    <p><b>Example item record:</b>
    <br/>↕ Code: CEM-50KG
    <br/>↕ Name: Cement CEM II 42.5 — 50kg bag
    <br/>↕ Category: Building Materials
    <br/>↕ UoM: Bag
    <br/>↕ Cost price: 4,200 XAF
    <br/>↕ Selling price: 4,800 XAF
    <br/>The category determines the inventory GL account (e.g. 311000)
    and cost of sales account (e.g. 601000) used when inventory
    documents are posted.</p>
    """,
)

# ── Inventory Documents ───────────────────────────────────────────────────

_register(
    "inventory_documents",
    "Inventory Documents",
    "Record goods receipts, issues, adjustments, and internal transfers.",
    """
    <p><b>Inventory Documents</b> record the physical movement of goods
    in and out of your inventory locations.</p>

    <p><b>Document types:</b></p>
    <ul>
      <li><b>Goods Receipt</b> — items received into a location.</li>
      <li><b>Goods Issue</b> — items issued out of a location.</li>
      <li><b>Adjustment</b> — correct stock quantities (increase or
          decrease) after physical counts.</li>
      <li><b>Transfer</b> — move items between locations.</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Document</em> to create an inventory document.</li>
      <li>Select the document type, location, and add item lines.</li>
      <li>Post the document to update stock quantities and create
          the related accounting entries.</li>
    </ul>

    <p><b>Tip:</b> Post inventory documents promptly to keep stock
    positions accurate and in sync with the GL.</p>

    <p><b>Example per document type:</b></p>
    <ul>
      <li><b>Goods Receipt:</b> Received 200 bags of Cement CEM II
          at Main Warehouse. On posting: stock increases by 200,
          GL debits 311000 Inventory, credits 601000 Purchases
          (or GR/IR account).</li>
      <li><b>Goods Issue:</b> Issued 50 bags for Project Alpha.
          Stock decreases by 50, GL debits 601000 Cost of Sales,
          credits 311000 Inventory.</li>
      <li><b>Adjustment:</b> Physical count found 195 bags vs
          system 200. Adjustment of −5 posts to an adjustment
          expense account.</li>
      <li><b>Transfer:</b> Moved 30 bags from Main Warehouse to
          Site B. No GL impact (same inventory account), only
          location quantities change.</li>
    </ul>
    """,
)

# ── Stock Position ────────────────────────────────────────────────────────

_register(
    "stock_position",
    "Stock Position",
    "View current stock on hand and valuation across items and locations.",
    """
    <p>The <b>Stock Position</b> page provides a real-time view of
    inventory quantities and valuations across all items and locations.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li>Current quantity on hand per item and location.</li>
      <li>Stock valuation based on the costing method.</li>
      <li>Items at zero or negative stock levels.</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>Filter by location, category, or item code.</li>
      <li>Review discrepancies between physical counts and system
          quantities.</li>
    </ul>

    <p><b>Tip:</b> The stock position reflects only <em>posted</em>
    inventory documents. Draft documents do not affect quantities.</p>
    """,
)

# ── Asset Categories ──────────────────────────────────────────────────────

_register(
    "asset_categories",
    "Asset Categories",
    "Define fixed asset categories with depreciation defaults and GL account mappings.",
    """
    <p><b>Asset Categories</b> group fixed assets by type (e.g. Buildings,
    Vehicles, Office Equipment) and define default depreciation methods,
    useful life, and GL account mappings.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Category</em> to create a category.</li>
      <li>Set the default depreciation method (straight-line, declining
          balance, etc.) and useful life in months.</li>
      <li>Map the asset, depreciation, and expense GL accounts.</li>
    </ul>

    <p><b>Tip:</b> Proper category setup ensures consistent depreciation
    treatment and correct GL posting for all assets in the category.</p>
    """,
)

# ── Assets ────────────────────────────────────────────────────────────────

_register(
    "assets",
    "Asset Register",
    "View and manage the company's fixed asset records.",
    """
    <p>The <b>Asset Register</b> lists all fixed assets owned by the
    company, with details on acquisition, depreciation status, and
    net book value.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Add an asset</b> — click <em>New Asset</em>.</li>
      <li>Fill in the asset code, name, category, acquisition date,
          and cost.</li>
      <li>Depreciation parameters are defaulted from the category but
          can be overridden per asset.</li>
      <li>Assets progress through states: Draft → Active → Fully
          Depreciated → Disposed.</li>
    </ul>

    <p><b>Key concepts:</b></p>
    <ul>
      <li><b>Acquisition cost</b> — the original cost of the asset.</li>
      <li><b>Accumulated depreciation</b> — total depreciation charged.</li>
      <li><b>Net book value</b> — acquisition cost minus accumulated
          depreciation.</li>
    </ul>

    <p><b>Tip:</b> Register assets promptly when acquired. Set the
    correct start date to ensure depreciation begins in the right period.</p>
    """,
)

# ── Depreciation Runs ─────────────────────────────────────────────────────

_register(
    "depreciation_runs",
    "Depreciation Runs",
    "Execute monthly depreciation calculations and post to the general ledger.",
    """
    <p><b>Depreciation Runs</b> are the monthly process that converts fixed
    asset wear-and-tear into accounting entries. A run calculates period
    depreciation for all <b>Active</b> assets, then posts a balanced journal
    entry to the general ledger.</p>

    <hr/>
    <p><b>What this page shows</b></p>
    <ul>
      <li><b>Run Number</b> - the document sequence reference
          (for example: <em>DEP-2025-0003</em>).</li>
      <li><b>Run Date</b> - when the run was executed.</li>
      <li><b>Period End</b> - the month-end date this run covers
          (for example: 31-Mar-2025).</li>
      <li><b>Status</b> - <em>Draft</em>, <em>Posted</em>, or
          <em>Cancelled</em>.</li>
      <li><b>Assets</b> - number of assets included in the run.</li>
      <li><b>Total Depreciation</b> - sum of all depreciation charges
          in the run.</li>
      <li><b>Posted At</b> - posting date (blank until posted).</li>
    </ul>

    <hr/>
    <p><b>End-of-month workflow</b></p>
    <ol>
      <li>Click <b>New Run</b>.</li>
      <li>Enter <b>Run Date</b> and <b>Period End Date</b>.
          Period End should normally be the last day of the month.</li>
      <li>Click <b>Generate Draft</b> in the dialog.
          The system computes depreciation line-by-line for each active asset.</li>
      <li>Open the draft and review the <b>Asset Lines</b>:
          depreciation amount, accumulated depreciation after, and
          net book value after.</li>
      <li>If values are correct, click <b>Post Run</b>.</li>
    </ol>

    <hr/>
    <p><b>What posting creates</b></p>
    <p>Posting creates GL entries for each asset category mapping:</p>
    <ul>
      <li><b>Debit:</b> Depreciation Expense account</li>
      <li><b>Credit:</b> Accumulated Depreciation account</li>
    </ul>
    <p>Total debits and credits match the run's <b>Total Depreciation</b>.</p>

    <hr/>
    <p><b>Important rules</b></p>
    <ul>
      <li>One accounting period should have exactly one posted run.
          Running multiple posted runs for the same period can overstate
          depreciation expense.</li>
      <li>Only <b>Active</b> assets are included.
          Draft, Disposed, and Fully Depreciated assets are excluded.</li>
      <li>The period must be open. Locked or closed fiscal periods block
          posting.</li>
      <li>All required category GL mappings must exist.
          Missing mappings block posting.</li>
    </ul>

    <hr/>
    <p><b>Worked example</b></p>
    <p>March 2025 run includes 12 assets with total monthly depreciation of
    985,000 XAF. After review, posting creates one balanced journal entry:
    Debit Depreciation Expense 985,000 XAF and Credit Accumulated
    Depreciation 985,000 XAF.</p>

    <p><b>Tip:</b> Make this page part of your close checklist:
    Assets updated -> Draft run generated -> Lines reviewed -> Run posted.</p>
    """,
)

# ── Contracts ─────────────────────────────────────────────────────────────

_register(
    "contracts",
    "Contracts",
    "Manage client contracts — the commercial agreements that projects are executed under.",
    """
    <p>A <b>Contract</b> is the formal commercial agreement with a client that
    authorises project work to begin. It defines what you are delivering, for
    how much, under what billing terms, and by when.</p>

    <p><b>How contracts, projects, and jobs relate:</b></p>
    <ul>
      <li>A <b>Contract</b> is the client agreement — the commercial wrapper
          (value, billing basis, retention, dates).</li>
      <li>A <b>Project</b> is linked to a contract and is where the actual
          work is tracked — costs, budgets, and commitments all sit on
          the project.</li>
      <li><b>Jobs</b> (inside the project) break the work into phases or
          work packages — e.g. Design, Procurement, Installation, Testing.</li>
    </ul>
    <p>So the full structure is: <em>Contract &rarr; Project &rarr; Jobs &rarr;
    Cost codes.</em> One contract can cover multiple projects if the scope
    is large enough.</p>

    <p><b>Example:</b> A contractor wins a road rehabilitation contract
    (CTR-2026-001, fixed price XAF 85 000 000). They create one project
    (PROJ-RD1) linked to that contract, then break the project into jobs:
    Site Clearing, Earthworks, Paving, Drainage. Every supplier bill and
    expense is tagged to a job and a cost code. The contract summary report
    shows total costs vs. contract value and the remaining margin.</p>

    <p><b>Change orders</b> are used when the client approves additional
    scope or adjusts the contract value. Each approved change order
    updates the contract's total value automatically.</p>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>New Contract</b> — create a contract record.</li>
      <li><b>Edit Contract</b> — update terms, dates, or details.</li>
      <li><b>Activate / Cancel</b> — move the contract through its lifecycle.</li>
      <li><b>Change Orders</b> — record approved scope or value adjustments.</li>
    </ul>

    <p><b>Tip:</b> Not every project needs a contract. Internal projects,
    capital expenditure projects, and administrative projects may not have
    a client contract. In those cases, create the project directly without
    linking a contract.</p>
    """,
)

# ── Projects ──────────────────────────────────────────────────────────────

_register(
    "projects",
    "Projects",
    "Define and manage projects — the unit of work for cost tracking, budgeting, and job costing.",
    """
    <p>A <b>Project</b> is the central unit of work in job costing. Everything
    else — jobs, budgets, commitments, cost codes — hangs off a project. When
    you tag a transaction with a project, the system knows where that cost or
    revenue belongs.</p>

    <p><b>Example:</b> A consulting firm has three active engagements —
    <em>PROJ-001</em> (ERP Implementation for Acme), <em>PROJ-002</em>
    (Audit Support for Beta Co.), and <em>PROJ-003</em> (Internal IT Upgrade).
    Staff timesheets, supplier bills, and invoices are all tagged to a project
    so management can see the profitability of each engagement separately.
    At month-end, the project variance report shows budget vs. actual by
    cost code for each project.</p>

    <p><b>What a project contains:</b></p>
    <ul>
      <li><b>Jobs</b> — phases or work packages within the project
          (e.g. Design, Build, Test, Go-Live).</li>
      <li><b>Budget</b> — planned costs by job and cost code, in one or
          more named versions (Original, Revised, Forecast).</li>
      <li><b>Commitments</b> — purchase reservations (POs, subcontracts)
          that represent future costs not yet invoiced.</li>
      <li><b>Contract link</b> — optionally linked to a formal client
          contract with value and billing terms.</li>
    </ul>

    <p><b>Budget control mode</b> determines what happens when actual costs
    exceed budget: <em>Hard Stop</em> blocks the transaction, <em>Warn</em>
    flags it but allows it, <em>None</em> allows without restriction.</p>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>New Project</b> — create a project record.</li>
      <li><b>Edit Project</b> — update details, status, or dates.</li>
      <li><b>Activate / Cancel</b> — move the project through its lifecycle.</li>
      <li><b>Jobs</b> — manage the work packages within this project.</li>
      <li><b>Budgets</b> — define or revise budget versions.</li>
      <li><b>Commitments</b> — record purchase reservations against the project.</li>
    </ul>

    <p><b>Tip:</b> Tag transactions with a project code consistently — every
    supplier bill, journal line, and invoice related to an engagement should
    carry the project code. Missing tags create blind spots in your cost
    reports.</p>
    """,
)

# ── Payroll Setup ─────────────────────────────────────────────────────────

_register(
    "payroll_setup",
    "Payroll Setup",
    "Everything you need to configure before you can calculate or pay your employees.",
    """
    <p>Before you can run payroll, the system needs to know how your
    company pays people. <b>Payroll Setup</b> is where you provide
    that information — who works for you, what they earn, what gets
    deducted, and how those amounts are calculated.</p>

    <p>Think of it as answering five questions in order:</p>

    <p><b>1. How is your company organised?</b></p>
    <ul>
      <li><b>Departments</b> — the teams or units in your business
          (e.g. Administration, Operations, Sales, Finance). These group
          employees for reporting and cost allocation.</li>
      <li><b>Positions</b> — the job titles that exist in your company
          (e.g. Driver, Accountant, Site Supervisor). Positions can carry
          a pay grade that pre-fills salary defaults when you hire.</li>
    </ul>

    <p><b>2. What makes up an employee’s pay packet?</b></p>
    <ul>
      <li><b>Payroll Components</b> are the individual line items that
          appear on every payslip. They come in two kinds:
          <em>Earnings</em> (things that add to pay) and
          <em>Deductions</em> (things that reduce take-home).
          <br/>Examples of earnings: Base Salary, Housing Allowance,
          Transport Allowance, Overtime, Performance Bonus.
          <br/>Examples of deductions: CNPS employee share, Withholding Tax
          (IRPP), Health insurance premium, Salary advance recovery.
          <br/>You define each component once here, then assign
          the relevant ones to each employee.</li>
    </ul>

    <p><b>3. How are the amounts actually calculated?</b></p>
    <ul>
      <li><b>Rule Sets</b> hold the calculation logic behind components
          that are not simple flat amounts. For example, income tax in
          Cameroon uses a bracket table — a different rate applies to
          each income band. A rule set encodes those brackets so the
          system can compute the exact tax automatically. Similarly,
          CNPS contributions have a rate and a ceiling defined in a rule.
          If a statutory rate changes, you update the rule here and
          every employee benefits from the correction on the next run.</li>
    </ul>

    <p><b>4. Who are your employees?</b></p>
    <ul>
      <li><b>Employees</b> — register each person with their full name,
          employee ID, position, department, contract type (permanent,
          fixed-term, casual), and bank account for payment. Each
          employee then gets a compensation profile listing which
          components apply to them and at what amounts.</li>
    </ul>

    <p><b>5. What are the company-wide defaults?</b></p>
    <ul>
      <li><b>Company Payroll Settings</b> — set the pay frequency
          (monthly, bi-weekly), the default currency, statutory
          registration numbers (CNPS employer number, tax ID), and
          the GL accounts payroll expenses should post to.</li>
    </ul>

    <p><b>Recommended setup order:</b> Departments &rarr; Positions &rarr;
    Components &rarr; Rule Sets &rarr; Company Settings &rarr; Employees.
    Once all five are complete, you can create your first payroll run.</p>
    """,
)

# ── Payroll Runs ──────────────────────────────────────────────────────────

_register(
    "payroll_calculation",
    "Payroll Runs",
    "Set up employee pay, enter variable inputs, calculate, review, and approve — all from one workspace with four tabs.",
    """
    <p>This workspace is where payroll comes together.  It has
    <b>four tabs</b>, each handling a different stage of the payroll
    cycle.  Work through them roughly left-to-right each pay
    period.</p>

    <hr/>

    <p><b>Tab 1 — Compensation Profiles</b></p>
    <p>A compensation profile is an employee’s "pay recipe" — it says
    what their base salary is, what currency they are paid in, and
    when the profile is effective.  Every employee needs at least one
    active profile before they can be included in a payroll run.</p>
    <ul>
      <li><b>New Profile</b> — select an employee from the filter
          dropdown first, then click <em>New Profile</em>.  Enter the
          basic salary, currency, and effective dates.</li>
      <li><b>Edit</b> — double-click a row (or select + Edit) to
          adjust salary or dates.</li>
      <li><b>Toggle Active</b> — deactivate a profile without
          deleting it (e.g.&nbsp;when an employee goes on unpaid
          leave).</li>
    </ul>
    <p><em>Example:</em> Marie Dupont is hired in January at
    350&thinsp;000&nbsp;FCFA/month.  You create a profile with
    Basic&nbsp;Salary&nbsp;=&nbsp;350&thinsp;000,
    From&nbsp;=&nbsp;01/01/2026.  In July she gets a raise to
    400&thinsp;000 — create a new profile effective 01/07/2026
    and deactivate the old one.</p>

    <hr/>

    <p><b>Tab 2 — Recurring Components</b></p>
    <p>Once an employee has a compensation profile, you assign the
    payroll components that apply to them every pay period — things
    like Housing Allowance, Transport Allowance, CNPS Employee Share,
    or Income Tax.  These are "recurring" because the system pulls
    them in automatically on every run; you do not re-enter them each
    month.</p>
    <ul>
      <li><b>Assign Component</b> — pick an employee, then click
          <em>Assign Component</em>.  Choose the component, set an
          override amount or rate if needed, and set an effective
          start date.</li>
      <li><b>Edit</b> — change the amount, rate, or dates.</li>
      <li><b>Toggle Active</b> — suspend a component (e.g.&nbsp;stop
          a transport allowance during a period of remote work).</li>
    </ul>
    <p><em>Columns explained:</em></p>
    <ul>
      <li><b>Component</b> — the code and name of the payroll
          component.</li>
      <li><b>Type</b> — Earning, Deduction, Tax, or Employer
          Contribution.</li>
      <li><b>Method</b> — how the amount is determined (Fixed,
          Percentage, Rule&nbsp;Based, Manual&nbsp;Input,
          Hourly).</li>
      <li><b>Override Amt / Rate</b> — an employee-specific amount
          or rate that overrides the component’s default.  Blank
          means the component default applies.</li>
    </ul>
    <p><em>Example:</em> You assign “Housing Allowance” to Marie with
    Override&nbsp;Amt&nbsp;=&nbsp;50&thinsp;000.  Every month the system
    automatically adds 50&thinsp;000 to her gross pay without anyone
    typing it in again.</p>

    <hr/>

    <p><b>Tab 3 — Variable Inputs</b></p>
    <p>Not everything is fixed.  Overtime hours, one-off bonuses,
    salary advances, sick-day deductions — these change every month.
    Variable inputs let you enter those period-specific values in
    batches before calculating payroll.</p>
    <ul>
      <li><b>New Batch</b> — creates a batch for a specific pay
          period.  A batch is like a container for all the variable
          entries for that month.</li>
      <li><b>Open / Manage</b> — select a batch and add, edit, or
          remove individual input lines (one line per employee per
          component).</li>
    </ul>
    <p><em>Columns explained:</em></p>
    <ul>
      <li><b>Reference</b> — the batch identifier.</li>
      <li><b>Period</b> — which pay period the batch belongs to.</li>
      <li><b>Status</b> — Draft (being edited), Submitted (ready for
          calculation), or Void.</li>
      <li><b>Lines</b> — how many individual input entries the batch
          contains.</li>
    </ul>
    <p><em>Example:</em> In March, three employees worked overtime.
    Create a batch for March, add three lines — one per employee —
    specifying the “Overtime” component and the hours or amount for
    each.  Submit the batch so the payroll run picks it up.</p>

    <hr/>

    <p><b>Tab 4 — Payroll Runs</b></p>
    <p>This is where everything comes together.  A <b>payroll run</b>
    is one complete cycle of calculating and approving employee pay
    for a specific pay period.</p>

    <p><b>Workflow — step by step:</b></p>
    <ol>
      <li><b>Create a run</b> — click <em>New Run</em>, choose the
          pay period (e.g.&nbsp;March&nbsp;2026) and which employees
          to include (typically all active employees).</li>
      <li><b>Calculate</b> — select the run and click
          <em>Calculate</em>.  The system processes every component
          and rule for every employee: gross pay, all deductions
          (tax, CNPS, insurance, advances), employer contributions,
          and net pay (what hits the bank account).</li>
      <li><b>Review</b> — the <em>Employee Results</em> sub-table
          shows each employee’s Gross, Deductions, Taxes, Net
          Payable, and Employer&nbsp;Cost.  Double-click an employee
          to see the full payslip breakdown.  If something is wrong,
          fix the variable inputs and recalculate.</li>
      <li><b>Approve</b> — once you are satisfied, click
          <em>Approve</em>.  This locks the payslips and marks the
          run as ready for posting to accounting.</li>
      <li><b>Void</b> — if the run is wrong beyond repair, void it
          and start fresh.</li>
    </ol>

    <p><em>Runs table columns:</em></p>
    <ul>
      <li><b>Reference</b> — the run identifier.</li>
      <li><b>Period</b> — the pay period.</li>
      <li><b>Status</b> — Draft &rarr; Calculated &rarr; Approved (or
          Voided).</li>
      <li><b>Employees</b> — number of employees in the run.</li>
      <li><b>Net Payable</b> — the total amount to be paid to all
          employees.</li>
    </ul>

    <p><b>Additional actions:</b></p>
    <ul>
      <li><b>Employee Detail</b> — opens a detailed payslip view
          for a selected employee within the run.</li>
      <li><b>Project Allocations</b> — if the company allocates
          payroll costs across projects or cost centres, view or
          manage those splits here.</li>
    </ul>

    <p><em>Example — full monthly cycle:</em></p>
    <ol>
      <li>Tab 1: Verify all employees have active compensation
          profiles.</li>
      <li>Tab 2: Confirm recurring components are up to date
          (any new hires assigned their allowances?).</li>
      <li>Tab 3: Enter this month’s variable inputs (overtime,
          bonuses, deductions).</li>
      <li>Tab 4: Create the March run &rarr; Calculate &rarr; Review
          employee-by-employee &rarr; Approve.</li>
      <li>Move to <em>Payroll Accounting</em> to post the approved
          run and record payments.</li>
    </ol>

    <p><b>Important:</b> Approving a run does <em>not</em>
    automatically pay anyone — it marks the calculations as correct
    and final.  Actual payment and GL posting happen in the Payroll
    Accounting section.  Always check the run summary before
    approving; corrections after approval require voiding the
    run.</p>
    """,
)

# ── Payroll Accounting ────────────────────────────────────────────────────

_register(
    "payroll_accounting",
    "Payroll Accounting",
    "Turn approved payroll into accounting entries, record salary payments, and track statutory remittances.",
    """
    <p>After a payroll run is approved, the numbers need to flow into
    your company’s financial records. <b>Payroll Accounting</b> handles
    that bridge between payroll and the general ledger.</p>

    <p><b>What happens here, in plain terms:</b></p>

    <p><b>1. Post to the General Ledger</b></p>
    <p>Posting converts an approved payroll run into accounting journal
    entries. The system records:
    the salary expense (what the company owes its employees),
    the deduction liabilities (tax withheld that must be paid to the
    government, CNPS contributions that must be remitted, etc.), and
    the net payable to employees (what will be transferred to bank
    accounts). Until you post, payroll figures exist only in the
    payroll module — they do not appear in your balance sheet or
    income statement.</p>

    <p><b>2. Record employee salary payments</b></p>
    <p>Posting creates a liability (the company owes employees their
    net pay). When you actually transfer money to employee bank
    accounts, you record that payment here — which clears the
    liability and reduces the bank balance. This keeps your cash
    position accurate.</p>

    <p><b>3. Record statutory remittances</b></p>
    <p>Payroll deductions like income tax and CNPS contributions are
    not the company’s money — they are held temporarily as liabilities
    and must be forwarded to the relevant authority (tax office, CNPS).
    When you make those government payments, record them here to clear
    the liability and prove compliance.</p>

    <p><b>Tip:</b> Post payroll to the GL as soon as it is approved.
    Keep employee payments and statutory remittances as separate
    transactions so your audit trail shows exactly what was
    paid to whom and when.</p>
    """,
)

# ── Payroll Operations ────────────────────────────────────────────────────

_register(
    "payroll_operations",
    "Payroll Operations",
    "Housekeeping tools: validate your data, apply statutory updates, send payslips, import and export.",
    """
    <p><b>Payroll Operations</b> contains the tools that keep your
    payroll clean, compliant, and communicated — things you use
    regularly but that are not part of running a payroll itself.</p>

    <p><b>Validation dashboard</b></p>
    <p>Runs a set of checks on your payroll data and flags problems
    before they cause errors in a payroll run. For example: employees
    with missing tax IDs, components with no rule assigned, employees
    with no bank details, or pay amounts that look unusually high or
    low. Run this before each payroll cycle.</p>

    <p><b>Statutory packs</b></p>
    <p>Governments periodically update tax tables, CNPS rates, and
    other statutory rates. A statutory pack is a pre-built bundle of
    updated rules you can apply in one step rather than editing each
    rule manually. When the Cameroon Finance Law changes the IRPP
    brackets, for example, you apply the new pack and the updated
    rates take effect for the next payroll run.</p>

    <p><b>Import and export</b></p>
    <p>If you have many employees, you can bulk-import staff records
    from a spreadsheet rather than entering each one by hand.
    Export generates structured files for banks (e.g. bulk payment
    instructions) or authorities (e.g. CNPS declarations).</p>

    <p><b>Payslips</b></p>
    <p>Preview and print payslips for any approved or posted payroll
    run. Each payslip shows the employee’s earnings, deductions,
    and net pay for the period — the document you hand to your
    employee as proof of what was calculated.</p>

    <p><b>Audit log</b></p>
    <p>A record of every significant action taken in payroll: who
    created or modified a run, who approved it, who posted it, and
    when. Useful for internal review and for answering questions
    from auditors or labour inspectors.</p>
    """,
)

# ── Reports ───────────────────────────────────────────────────────────────

_register(
    "reports",
    "Reports",
    "Access the full suite of financial and operational reports.",
    """
    <p>The <b>Reports</b> workspace gives you access to all standard
    financial and operational reports.</p>

    <p><b>Available report categories:</b></p>
    <ul>
      <li><b>Financial statements</b> — Balance Sheet, Income Statement
          (OHADA and IAS formats)</li>
      <li><b>General Ledger</b> — Trial Balance, Account Ledger</li>
      <li><b>Receivables</b> — AR Aging, Customer Statements</li>
      <li><b>Payables</b> — AP Aging, Supplier Statements</li>
      <li><b>Treasury</b> — Bank reconciliation report, Cash flow</li>
      <li><b>Inventory</b> — Stock valuation, Stock movements</li>
      <li><b>Fixed Assets</b> — Asset register, Depreciation schedule</li>
      <li><b>Payroll</b> — Payroll summary, Statutory reports</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>Select a report from the tile grid.</li>
      <li>Set filters (date range, account, etc.) and generate.</li>
      <li>Drill down into line items for detail.</li>
      <li>Print or export reports as needed.</li>
    </ul>

    <p><b>Tip:</b> All reports read from posted accounting data only.
    Draft transactions are not included.</p>

    <p><b>Example — generating a month-end report set:</b>
    <br/>↕ 1. Ensure all March entries are posted and the period is ready.
    <br/>↕ 2. Generate the <em>Trial Balance</em> for March — verify
    debits = credits.
    <br/>↕ 3. Generate the <em>OHADA Income Statement</em> for March —
    review revenue and expenses.
    <br/>↕ 4. Generate the <em>OHADA Balance Sheet</em> as at 31 March —
    verify assets = liabilities + equity.
    <br/>↕ 5. Print or export each report for management review.</p>
    """,
)

# ── Project Variance Analysis ─────────────────────────────────────────────

_register(
    "project_variance_analysis",
    "Project Variance Analysis",
    "Analyse budget versus actual costs by project.",
    """
    <p><b>Project Variance Analysis</b> compares budgeted costs to actual
    costs for each project, job, and cost code — showing where spending
    is above or below plan.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Select a <b>project</b> or <b>contract</b> to analyse.</li>
      <li>Choose the <b>budget version</b> to compare against (usually
          the Active version).</li>
      <li>Review the variance table: Budget vs. Actual vs. Committed.</li>
      <li>Drill down into specific cost codes or jobs for detail.</li>
    </ul>

    <p><b>Reading the variance table:</b></p>
    <ul>
      <li><b>Budget</b> — the approved budget amount for this cost
          code or job.</li>
      <li><b>Actual</b> — costs already posted to the ledger.</li>
      <li><b>Committed</b> — open commitments not yet invoiced.</li>
      <li><b>Forecast</b> — Actual + Committed = projected total
          cost.</li>
      <li><b>Variance</b> — Budget − Forecast. Positive = under
          budget (favourable). Negative = over budget (unfavourable).</li>
      <li><b>Variance %</b> — the variance as a percentage of budget.</li>
    </ul>

    <p><b>Example:</b> Cost code <em>MAT (Materials)</em> on project
    PROJ-001:
    <br/>↕ Budget: 12,000,000 XAF
    <br/>↕ Actual: 8,500,000 XAF
    <br/>↕ Committed: 2,800,000 XAF
    <br/>↕ Forecast: 11,300,000 XAF
    <br/>↕ Variance: +700,000 XAF (5.8% under budget) —
    <em>favourable</em></p>

    <p><b>Colour coding:</b> Favourable variances typically appear in
    green, unfavourable in red, and near-budget in neutral. Use the
    colours as a quick scan tool to identify problem areas.</p>

    <p><b>Tip:</b> Run variance analysis at least monthly. Early
    identification of unfavourable variances gives you time to adjust
    — whether by controlling spend, requesting change orders, or
    revising the budget.</p>
    """,
)

# ── Contract Summary ──────────────────────────────────────────────────────

_register(
    "contract_summary",
    "Contract Summary",
    "Financial summary and project rollup by contract.",
    """
    <p><b>Contract Summary</b> provides a consolidated financial view
    of each contract, rolling up costs, revenue, and profitability
    across all linked projects.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Contract value</b> — original value + approved change
          orders = revised contract value.</li>
      <li><b>Revenue recognised</b> — total invoiced / recognised
          revenue to date.</li>
      <li><b>Costs incurred</b> — total actual costs posted across
          all linked projects.</li>
      <li><b>Committed costs</b> — open commitments not yet invoiced.</li>
      <li><b>Margin</b> — Revenue − Costs = current margin.
          Shown as both amount and percentage.</li>
      <li><b>Completion %</b> — progress indicator based on cost
          completion (Actual Costs ÷ Forecast Total Costs).</li>
    </ul>

    <p><b>Example:</b> Contract CTR-2026-001 (<em>Office Building
    Phase 2</em>):
    <br/>↕ Contract value: 85,000,000 XAF (original 80M + CO 5M)
    <br/>↕ Revenue: 52,000,000 XAF (milestone billing)
    <br/>↕ Costs: 38,500,000 XAF actual + 6,200,000 committed
    <br/>↕ Forecast total cost: 44,700,000 XAF
    <br/>↕ Margin: 13,500,000 XAF (25.9%)
    <br/>↕ Completion: 86%</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Review the summary monthly to monitor contract health.</li>
      <li>Click on a contract to see its project breakdown.</li>
      <li>Flag contracts with declining margins for management
          attention.</li>
    </ul>

    <p><b>Tip:</b> Use this report for monthly management meetings
    and client progress reviews. It gives a full picture of where
    each contract stands without needing to drill into individual
    project details.</p>
    """,
)

# ── Organisation Settings ─────────────────────────────────────────────────

_register(
    "organisation_settings",
    "Organisation Settings",
    "Manage company master data, profiles, and operating context.",
    """
    <p><b>Organisation Settings</b> is the administration hub for managing
    your company records.</p>

    <p><b>What you can do:</b></p>
    <ul>
      <li>View and edit company profiles (name, address, tax ID, etc.).</li>
      <li>Create new companies for multi-company operation.</li>
      <li>Switch the active company context.</li>
      <li>Configure company-level preferences.</li>
    </ul>

    <p><b>Tip:</b> Keep company master data accurate — it appears on
    printed documents and reports.</p>

    <p><b>Example — multi-company setup:</b>
    <br/>↕ Company 1: Ets Mbarga Construction SARL (main entity)
    <br/>↕ Company 2: Mbarga Transport (logistics subsidiary)
    <br/>Each company has its own chart of accounts, fiscal periods,
    customers, suppliers, and transactions. Use the company selector
    in the sidebar to switch between them. Reports always show data
    for the currently active company.</p>
    """,
)

# ── Administration / Users ────────────────────────────────────────────────

_register(
    "administration",
    "Users",
    "Manage user accounts, access permissions, and security.",
    """
    <p>The <b>Users</b> page lets administrators manage who can access
    the system and what they can do.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li><b>Create a user</b> — click <em>New User</em> and fill in
          credentials and profile details.</li>
      <li><b>Assign roles</b> — grant roles that determine what modules
          and actions the user can access.</li>
      <li><b>Deactivate</b> — disable user accounts without deleting them.</li>
    </ul>

    <p><b>Tip:</b> Follow the principle of least privilege — grant only
    the permissions each user needs for their job function.</p>

    <p><b>Example — setting up a new bookkeeper:</b>
    <br/>↕ 1. Click <em>New User</em>
    <br/>↕ 2. Username: m.ndjock | Full name: Marie Ndjock
    <br/>↕ 3. Set a strong temporary password
    <br/>↕ 4. Assign the <em>Bookkeeper</em> role (journal entries,
    invoices, bills, receipts, payments)
    <br/>↕ 5. The user can now log in and work within their permitted
    modules. They cannot access payroll, period locking, or user
    administration.</p>
    """,
)

# ── Roles ─────────────────────────────────────────────────────────────────

_register(
    "roles",
    "Roles",
    "Define roles and their associated permissions.",
    """
    <p><b>Roles</b> define sets of permissions that can be assigned to
    users. Each role grants access to specific modules and actions.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click <em>New Role</em> to create a role (e.g. Accountant,
          Payroll Officer, Manager).</li>
      <li>Assign permissions to the role — module access, read/write,
          and special actions like posting or locking periods.</li>
      <li>Assign the role to one or more users.</li>
    </ul>

    <p><b>Tip:</b> Create a small number of well-defined roles rather
    than many highly specific ones. This simplifies administration.</p>

    <p><b>Example roles:</b></p>
    <ul>
      <li><b>Bookkeeper</b> — journal entries, invoices, bills,
          receipts, payments. No period close or user admin.</li>
      <li><b>Accountant</b> — everything the Bookkeeper can do,
          plus financial reports, period close, and reconciliation.</li>
      <li><b>Payroll Officer</b> — employee master data, payroll
          runs, payslips. No access to AP/AR or journal entries.</li>
      <li><b>Manager</b> — read-only access to all reports and
          dashboards. No posting or editing.</li>
      <li><b>Administrator</b> — full access including user
          management, roles, and system settings.</li>
    </ul>
    """,
)

# ── Audit Log ─────────────────────────────────────────────────────────────

_register(
    "audit_log",
    "Audit Log",
    "Review a chronological record of all significant system actions.",
    """
    <p>The <b>Audit Log</b> provides a chronological, tamper-evident
    record of important actions performed in the system.</p>

    <p><b>What is logged:</b></p>
    <ul>
      <li>User logins and logouts</li>
      <li>Create, edit, and delete operations on master data</li>
      <li>Document posting and voiding</li>
      <li>Period close and lock operations</li>
      <li>Role and permission changes</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>Filter by date, user, action type, or module.</li>
      <li>Review entries for compliance or troubleshooting.</li>
    </ul>

    <p><b>Tip:</b> The audit log is read-only and cannot be modified.
    It provides evidence for internal and external audit reviews.</p>

    <p><b>Example — investigating a voided invoice:</b>
    <br/>↕ 1. Filter: Action = "Void", Module = "Sales"
    <br/>↕ 2. Find entry: "INV-2026-042 voided by j.kamga at
    15:23 on 18 Mar 2026"
    <br/>↕ 3. Review the previous entry to see who posted the
    original invoice and when.
    <br/>This trail lets you verify that the void was authorised and
    the replacement invoice was issued correctly.</p>
    """,
)


# ═══════════════════════════════════════════════════════════════════════════
#  DIALOGS
# ═══════════════════════════════════════════════════════════════════════════

# ── Accounting: Chart of Accounts ─────────────────────────────────────────

_register(
    "dialog.account_form",
    "GL Account",
    "Create or edit a general ledger account in your chart of accounts.",
    """
    <p>A <b>GL account</b> is one node in your chart of accounts — the place
    where a specific type of financial value is recorded. Every debit and
    credit in the system ultimately lands on a GL account. Getting these
    right at setup prevents messy corrections later.</p>

    <p><b>Example:</b> A trading company might have account <em>401 —
    Suppliers</em> (a liability — what they owe to suppliers), account
    <em>411 — Customers</em> (an asset — what customers owe them), and
    account <em>601100 — Raw Materials Purchases</em> (an expense). Each
    is a separate account so that financial statements can report them
    individually and management can see exactly where money flows.</p>

    <p><b>Account Code</b> — the unique numeric identifier for this account
    (e.g. <em>401</em>, <em>601100</em>). Under OHADA, codes follow a
    prescribed numbering plan: class 1 for equity/long-term liabilities,
    class 2 for fixed assets, class 3 for stock, class 4 for third-party
    accounts, class 5 for cash and bank, class 6 for expenses, class 7
    for revenue. Your code must be unique within the company. Once the
    account receives posted entries, the code should not change.</p>

    <p><b>Account Name</b> — the plain-language label shown in journals,
    reports, and selection lists. Be descriptive
    (e.g. <em>Suppliers — Trade Payables</em> rather than just
    <em>Payables</em>). Staff select from this name on every transaction.</p>

    <p><b>Parent Account</b> — optional. Setting a parent places this
    account inside a hierarchy group. Grouping accounts under parents allows
    the balance sheet and income statement to show subtotals by group.
    Example: <em>601100 Raw Materials</em> and <em>601200 Packaging</em>
    both have parent <em>601 — Purchases of Goods</em>, so the report shows
    a subtotal for all purchases. Leave blank for top-level class accounts.</p>

    <p><b>Account Class</b> — the broadest financial category: Asset,
    Liability, Equity, Revenue, or Expense. This drives which financial
    statement section the account appears in and is usually determined by
    the account code range.</p>

    <p><b>Account Type</b> — a more specific classification within the class
    (e.g. Current Asset, Fixed Asset, Trade Payable, Operating Revenue).
    Account types control where lines appear on the OHADA balance sheet and
    income statement in the correct statutory order.</p>

    <p><b>Normal Balance</b> — the side of the ledger this account normally
    increases on. Asset and expense accounts are normally <em>Debit</em>.
    Liability, equity, and revenue accounts are normally <em>Credit</em>.
    This is set automatically based on the account type — only override
    it if you have a specific reason.</p>

    <p><b>Allow Manual Posting</b> — controls whether journal entries can
    post directly to this account. Enable this for leaf accounts where
    actual transactions land (e.g. a specific bank account, a specific
    expense line). Disable it for summary/group accounts that should only
    accumulate balances from their children and never receive direct
    postings. Posting to a group account is an accounting error — this
    flag prevents it.</p>

    <p><b>Control Account</b> — enable for accounts driven by a subledger.
    The Accounts Receivable control account (411) always equals the sum of
    all customer balances. The Accounts Payable control account (401) always
    equals the sum of all supplier balances. Control accounts must never be
    posted to manually — they are maintained exclusively through sales
    invoices, purchase bills, and payments. This flag prevents accidental
    manual journal postings to the account and ensures subledger
    reconciliation remains clean.</p>

    <p><b>Active</b> — only active accounts appear in transaction selection
    lists. Deactivate accounts that are no longer in use to keep lists
    clean without losing historical data.</p>

    <p><b>Notes</b> — optional internal guidance about this account's
    purpose or usage rules. Useful for training new staff or documenting
    unusual accounts.</p>
    """,
)

_register(
    "dialog.chart_import",
    "Chart of Accounts Import",
    "Import accounts from a spreadsheet file \u2014 CSV or Excel with a specific column layout.",
    """
    <p>Use this dialog to bulk-import GL accounts from a CSV or Excel file
    into your chart of accounts. The file must follow the exact column
    structure described below.</p>

    <p><b>How to use:</b></p>
    <ol>
      <li>Prepare your file with the required columns (see below).</li>
      <li>Select the file using the file picker.</li>
      <li>Click <em>Preview</em> to see what will be created, skipped,
          or flagged as invalid before anything is written.</li>
      <li>Confirm the import to create the accounts.</li>
    </ol>

    <p><b>Required column headers</b> \u2014 first row of the file, exact spelling
    (lowercase, underscores):</p>
    <ul>
      <li><b>template_code</b> \u2014 a short identifier for this import batch
          (e.g. <em>MY_COA_2026</em>). All rows in one file typically share
          the same value. Used for tracking and logging.</li>
      <li><b>account_code</b> \u2014 the GL account number
          (e.g. <em>401</em>, <em>601100</em>). Must be unique within
          the company. This is the primary key the import uses to detect
          existing accounts.</li>
      <li><b>account_name</b> \u2014 the account\u2019s display name shown in lists,
          journals, and reports (e.g. <em>Suppliers</em>,
          <em>Raw Materials Purchases</em>).</li>
      <li><b>parent_account_code</b> \u2014 the <em>account_code</em> of the
          parent account in the hierarchy. Leave blank if this account sits
          at the top level. The parent must exist either in the file or
          already in the chart.</li>
      <li><b>level_no</b> \u2014 integer depth in the chart hierarchy.
          Typically <em>1</em> for classes, <em>2</em> for groups,
          <em>3</em> or deeper for individual posting accounts.</li>
      <li><b>class_code</b> \u2014 the account class code this account belongs
          to (e.g. <em>1</em>, <em>2</em>, <em>4</em>, <em>6</em> under
          OHADA). Every account must be assigned to a class.</li>
      <li><b>class_name</b> \u2014 the account class display name
          (e.g. <em>Equity and Liabilities</em>,
          <em>Charges by Nature</em>).</li>
      <li><b>source_subaccount_code</b> \u2014 optional reference code from
          the source chart standard (e.g. the OHADA plan sub-account
          reference). Leave blank if not applicable.</li>
      <li><b>source_subaccount_name</b> \u2014 optional name for the source
          sub-account reference. Leave blank if not applicable.</li>
      <li><b>normal_balance</b> \u2014 the side this account normally increases
          on. Must be exactly <em>DEBIT</em> or <em>CREDIT</em>
          (uppercase). Asset and expense accounts are typically DEBIT;
          liability, equity, and revenue accounts are typically CREDIT.</li>
      <li><b>allow_manual_posting</b> \u2014 whether journal entries may post
          directly to this account. Use <em>True</em> or <em>False</em>.
          Set to <em>False</em> for summary/header accounts that should
          not receive direct postings.</li>
      <li><b>is_control_account_default</b> \u2014 whether this is a subledger
          control account (e.g. the Accounts Receivable or Accounts
          Payable control account). Use <em>True</em> or <em>False</em>.
          Control accounts are reconciled against subledger totals and
          should not be posted to manually.</li>
      <li><b>account_type_code</b> \u2014 classifies the account for financial
          statement reporting. Must match a valid account type code in
          the system (e.g. <em>ASSET</em>, <em>LIABILITY</em>,
          <em>EQUITY</em>, <em>REVENUE</em>, <em>EXPENSE</em>).</li>
      <li><b>notes</b> \u2014 optional free-text notes about the account.
          Leave blank if not needed.</li>
      <li><b>is_active_default</b> \u2014 whether the account should be active
          immediately after import. Use <em>True</em> or <em>False</em>.
          Almost always <em>True</em>; set to <em>False</em> to import
          accounts in an inactive/dormant state.</li>
    </ul>

    <p><b>Important:</b></p>
    <ul>
      <li>Existing accounts with matching codes will not be overwritten
          \u2014 the import is strictly additive.</li>
      <li>Column headers must match exactly: lowercase, underscores,
          no extra spaces.</li>
      <li>Always run Preview before confirming \u2014 it shows exactly how
          many accounts will be created, skipped, or rejected.</li>
    </ul>
    """,
)

# ── Accounting: Fiscal Periods ────────────────────────────────────────────

_register(
    "dialog.fiscal_year",
    "Fiscal Year",
        "Define the start and end dates of an accounting year for this company.",
    """
        <p>A <b>fiscal year</b> is the 12-month accounting cycle the company
        reports against. All transactions, financial statements, and period-end
        procedures are anchored to a fiscal year. You must have at least one
        fiscal year — and its monthly periods — before you can post any
        transactions.</p>

        <p><b>Example:</b> A Cameroonian company following the standard calendar
        year creates fiscal year <em>FY2026</em> running from 1 January 2026
        to 31 December 2026. After saving it, they generate 12 monthly periods
        (January through December). A transaction dated 15 March 2026 will post
        to the March 2026 period of FY2026 and appear on the March balance sheet
        and income statement.</p>

        <p><b>Year Label</b> — the display name shown in period selectors,
        reports, and year-end workflows (e.g. <em>FY2026</em>,
        <em>2025–2026</em>). Choose a label that makes the year immediately
        recognisable to staff. It does not affect any calculations — only
        the start and end dates matter for date-range logic.</p>

        <p><b>Start Date</b> — the first day of the fiscal year. For a calendar
        year this is 1 January. For a non-calendar fiscal year (e.g. April to
        March) this is the first day of the year. All transaction dates from
        this date onward belong to this fiscal year until the end date.</p>

        <p><b>End Date</b> — the last day of the fiscal year. Typically the
        start date plus 12 months minus 1 day. Fiscal years must not overlap
        — the system will reject dates that conflict with an existing year for
        this company.</p>

        <p><b>Next step:</b> After saving the fiscal year, go to
        <em>Generate Periods</em> to create the 12 monthly periods
        automatically. A fiscal year with no periods will block all posting
        — the periods are what the system checks against each transaction date.</p>
    """,
)

_register(
    "dialog.generate_periods",
    "Generate Periods",
    "Create the 12 monthly accounting periods for a fiscal year in one step.",
    """
    <p>An accounting <b>period</b> is a single month within a fiscal year.
    Periods are the gatekeepers for posting: a transaction can only be
    saved to a period that is <em>Open</em>. Closing a period locks it
    against further changes for that month. This is how accounting
    discipline works — once March is closed, nobody can slip a late
    expense into March without an explicit reopen decision.</p>

    <p>This dialog generates all 12 periods for the selected fiscal year
    at once, so you don't have to create January, February … December
    one by one.</p>

    <p><b>Example:</b> Fiscal year FY2026 runs 1 Jan – 31 Dec 2026. After
    clicking Generate, the system creates: P01 (1–31 Jan), P02 (1–28 Feb),
    P03 (1–31 Mar) … P12 (1–31 Dec 2026). A purchase bill dated 22 March
    2026 will post to period P03. A bill with yesterday's date entered after
    P03 has been closed will be rejected — you must either reopen March or
    post it to the next open period.</p>

    <p><b>Period states and what they mean:</b></p>
    <ul>
      <li><b>Open</b> — transactions can be posted freely. This is the
          normal working state for the current month.</li>
      <li><b>Closed</b> — no new transactions allowed. Used after
          month-end reconciliation is complete and management has
          signed off the month. Closing is reversible if you need to
          make a late correction.</li>
      <li><b>Locked</b> — permanently sealed after audit or statutory
          filing. Locked periods cannot be reopened under any
          circumstances — any correction must be made in a later
          open period.</li>
    </ul>

    <p><b>Note:</b> You can only generate periods once per fiscal year.
    If periods were already created (manually or by a previous generation
    run), this option will be unavailable for that year.</p>
    """,
)

# ── Accounting: Journals ──────────────────────────────────────────────────

_register(
    "dialog.journal_entry",
    "Journal Entry",
    "Record a double-entry accounting transaction with balanced debit and credit lines.",
    """
    <p>A <b>journal entry</b> is the fundamental unit of accounting. Every
    financial event — a salary payment, a bank charge, a prepayment, a
    correction — is recorded as a journal entry with at least two lines:
    one or more debits and one or more credits, always totalling the same
    amount. This is the double-entry principle: every debit has a matching
    credit somewhere.</p>

    <p><b>Example:</b> The company pays office rent of 150 000 XAF in cash.
    The journal entry has two lines:
    <br/>&#8195;Debit — <em>612 — Rent Expense</em> — 150 000 XAF
    <br/>&#8195;Credit — <em>521 — Bank Account</em> — 150 000 XAF
    <br/>The rent expense increases (debit) and the bank balance decreases
    (credit). Total debits = total credits = 150 000 XAF. The entry balances.</p>

    <p><b>Entry Type</b> — classifies what kind of transaction this is:</p>
    <ul>
      <li><b>General</b> — the default for most manual adjustments, accruals,
          corrections, and recharges not covered by a specific module
          (invoices, payments, payroll).</li>
      <li><b>Adjustment</b> — period-end adjustments such as depreciation
          charges, prepayment amortisation, or provision entries.</li>
      <li><b>Opening</b> — used to record opening balances when setting up
          the system for the first time or starting a new fiscal year.</li>
      <li><b>Closing</b> — year-end entries that transfer net profit or loss
          to retained earnings and reset revenue and expense accounts.</li>
    </ul>

    <p><b>Reference</b> — a short identifier for this entry
    (e.g. <em>JE-2026-0047</em>). Auto-generated from the document sequence
    or entered manually. Once posted, the reference is the permanent audit
    trail key — it appears on account ledger reports and audit printouts.</p>

    <p><b>Description</b> — explain what this entry records and why. A
    description like <em>March 2026 office rent — payment ref CHQ-0192</em>
    is far more useful than <em>Rent</em> when reviewing entries six months
    later or answering an auditor's question.</p>

    <p><b>Transaction Date</b> — the date the economic event occurred. This
    determines which fiscal period the entry posts to. Defaults to today
    but can be any date within an open period. You cannot post to a closed
    or locked period.</p>

    <p><b>Entry lines:</b> each line has an account, a debit or credit
    amount, and an optional per-line description.</p>
    <ul>
      <li><b>Account</b> — only accounts with <em>Allow Manual Posting</em>
          enabled are available. Control accounts (AR, AP) are excluded
          — those are driven by invoices and payments, not manual entries.</li>
      <li><b>Debit / Credit</b> — enter the amount on the correct side.
          Debits increase asset and expense accounts; credits increase
          liability, equity, and revenue accounts.</li>
      <li><b>Line description</b> — optional per-line note providing
          additional detail in the account ledger report.</li>
    </ul>

    <p><b>Balancing rule</b> — the entry cannot be posted unless total
    debits exactly equal total credits. The running difference is shown
    at the bottom of the lines — it must reach zero before posting.</p>

    <p><b>Draft vs Posted:</b> Save as draft while building the entry.
    Drafts are visible in the journal list but have no effect on account
    balances or financial statements. Once you are satisfied, post the
    entry — it then becomes immutable accounting truth. To correct a
    posted entry, create a reversing entry (same lines, opposite sides)
    and then post a corrected version.</p>
    """,
)

# ── Accounting: Reference Data ────────────────────────────────────────────

_register(
    "dialog.account_role_mapping",
    "Account Role Mapping",
    "Tell the system which GL account to use for each automatic posting role.",
    """
    <p>When the system posts a sales invoice, it needs to know which GL
    account represents Accounts Receivable. When it posts a supplier bill,
    it needs the Accounts Payable account. When it posts revenue, it needs
    the revenue account. <b>Account Role Mappings</b> are where you provide
    those answers — once, for all future transactions.</p>

    <p><b>Why this matters:</b> Without a correct mapping, posting will be
    blocked or will land in the wrong account. An invoice posted to the
    wrong AR account makes your receivables balance wrong and breaks
    reconciliation. Correct mappings are a prerequisite to processing
    any transactions.</p>

    <p><b>Example:</b> Role <em>Accounts Receivable Control</em> is mapped
    to GL account <em>411 — Customers</em>. Every sales invoice posted
    automatically debits account 411 without you specifying it on each
    invoice. If you later restructure and the AR account changes to
    <em>4111 — Local Customers</em>, you update the mapping here and all
    future postings use the new account automatically.</p>

    <p><b>Account Role</b> — a system-defined label describing the purpose
    of the account in automated postings. Common roles include: Accounts
    Receivable Control, Accounts Payable Control, Sales Revenue,
    Cost of Goods Sold, VAT Collected, VAT Recoverable, Bank Default,
    Retained Earnings, and others. Each role has exactly one mapping per
    company at a time.</p>

    <p><b>Account</b> — the GL account in your chart that should receive
    postings for this role. It must exist and be active. Choose an account
    that matches the economic nature of the role: AR roles need a
    receivables asset account, AP roles need a payables liability account,
    revenue roles need a revenue account, and so on.</p>

    <p><b>Tip:</b> Set up all required role mappings before processing any
    invoices, bills, or payments. The system will tell you exactly which
    mappings are missing if you try to post without them.</p>
    """,
)

_register(
    "dialog.document_sequence",
    "Document Sequence",
        "Configure automatic numbering for invoices, bills, payments, and other documents.",
    """
        <p>A <b>document sequence</b> is the rule that generates reference
        numbers for business documents automatically. Every sales invoice,
        purchase bill, receipt, payment, and journal entry gets a unique
        reference from its sequence. These numbers are the primary identifiers
        in audit trails, customer communications, and tax filings — they must
        be sequential, gapless, and consistent.</p>

        <p><b>Example:</b> A company creates a sequence for sales invoices:
        code <em>INV_2026</em>, document type <em>Sales Invoice</em>, prefix
        <em>INV-2026-</em>, starting number <em>1001</em>, step <em>1</em>.
        The first invoice gets reference <em>INV-2026-1001</em>, the second
        <em>INV-2026-1002</em>, and so on. At year-end they create a new
        sequence <em>INV_2027</em> with prefix <em>INV-2027-</em> starting
        at 1001 for the new year, leaving the old sequence intact.</p>

        <p><b>Sequence Code</b> — a short internal identifier for this sequence
        (e.g. <em>INV_2026</em>, <em>BILL_2026</em>, <em>JNL_2026</em>).
        Must be unique within the company. Used to link the sequence to
        a document type in system configuration.</p>

        <p><b>Document Type</b> — which type of document this sequence numbers:
        Sales Invoice, Purchase Bill, Customer Receipt, Supplier Payment,
        Journal Entry, etc. Each document type can have one active sequence
        at a time. When a new document of that type is created, it draws
        the next number from its assigned sequence automatically.</p>

        <p><b>Prefix</b> — text prepended to every number this sequence produces
        (e.g. <em>INV-2026-</em>, <em>BL-</em>, <em>REC-</em>). The prefix
        appears on every document, customer statement, and report. Once you
        have issued documents with a prefix, do not change it — customers
        and auditors will be confused by a sudden change in reference format,
        and it may violate chronological numbering requirements in your
        jurisdiction. Plan your prefix structure carefully at setup.</p>

        <p><b>Next Number</b> — the integer assigned to the very next document
        created. After each document is issued, this advances by the step
        value automatically. If migrating from another system and continuing
        an existing series, set this to your next unused number so there
        are no gaps or duplicates.</p>

        <p><b>Step</b> — how much the number increases with each document.
        Almost always <em>1</em>: starting at 1001 with step 1 produces
        1001, 1002, 1003…</p>

        <p><b>Important:</b> Once a sequence has been used on a posted
        document, do not change its prefix or reset the next number. Doing
        so creates duplicate or inconsistent references, which is an audit
        and compliance problem. For a new year, create a new sequence and
        leave the old one in place.</p>
    """,
)

_register(
    "dialog.payment_term",
    "Payment Term",
        "Define how long a customer or supplier has to pay an invoice or bill.",
    """
        <p>A <b>payment term</b> is the agreed rule for when an invoice or bill
        becomes due. It is assigned once to each customer or supplier record
        and applied automatically every time a new invoice or bill is created
        for that party. The system calculates the due date by adding the term's
        number of days to the invoice date.</p>

        <p><b>Example:</b> Customer <em>Ngum Trading</em> is set to payment
        term <em>Net 30</em>. A sales invoice is issued on 5 March 2026. The
        system automatically sets the due date to 4 April 2026. The AR aging
        report uses this due date to classify the balance as current, 1–30 days
        overdue, 31–60 days overdue, and so on. A customer on term
        <em>Immediate</em> (0 days) gets a due date equal to the invoice date
        — the balance is overdue from day one if not settled.</p>

        <p><b>Code</b> — a short internal identifier (e.g. <em>NET30</em>,
        <em>NET60</em>, <em>IMM</em>, <em>NET15</em>). Must be unique.
        Keep it concise and self-explanatory.</p>

        <p><b>Name</b> — the full display name shown in selection lists
        (e.g. <em>Net 30 Days</em>, <em>Due on Receipt</em>,
        <em>60 Days End of Month</em>).</p>

        <p><b>Days</b> — calendar days from invoice date until payment due:</p>
        <ul>
            <li><b>0</b> — immediate / due on receipt</li>
            <li><b>15</b> — net 15 days</li>
            <li><b>30</b> — net 30 days (most common standard term)</li>
            <li><b>60</b> — net 60 days</li>
            <li><b>90</b> — net 90 days (extended, usually negotiated)</li>
        </ul>

        <p><b>Where terms flow:</b> Terms assigned on customer/supplier records
        flow onto every invoice or bill for that party. The resulting due dates
        drive the AR and AP aging reports. Accurate terms are essential for
        effective collections follow-up and cash flow forecasting.</p>

        <p><b>Tip:</b> Create all terms before entering customers and suppliers.
        A party with no term will have no due date on their invoices, making
        aging reports unreliable.</p>
    """,
)

_register(
    "dialog.tax_code",
    "Tax Code",
    "Define a company tax code — rate, type, calculation method, and effective dates.",
    """
    <p>A <b>tax code</b> is the named, versioned definition of a tax rate the system
    uses when calculating tax on invoice and bill lines. Every tax line on a document
    must reference a tax code. Configure these before issuing invoices or recording
    supplier bills — a missing mapping will block posting.</p>

    <p><b>Code</b><br/>
    A short machine-readable identifier: upper-case, no spaces, 6–12 characters.
    Examples: <i>VAT_STD</i>, <i>VAT19</i>, <i>WHT15</i>, <i>EXEMPT</i>.
    Must be unique within the company. Once a code appears on a posted document
    do not rename it — end-date the old one and create a new code for any
    rate change.</p>

    <p><b>Name</b><br/>
    Human-readable label shown in line-item dropdowns and on reports.
    Be precise: <i>VAT 19.25% Standard</i> is far more useful than <i>VAT</i>.
    Staff pick from this name on every invoice line, so clarity reduces errors.</p>

    <p><b>Tax Type</b><br/>
    Classifies the nature of the tax:</p>
    <ul>
      <li><b>VAT</b> — Value Added Tax. Applies on both sales (output VAT) and
          purchases (input VAT). Standard Cameroon rate: 19.25%.</li>
      <li><b>WITHHOLDING</b> — Tax withheld at source on payments to suppliers.
          Common for services, rent, professional fees. Typical Cameroon rate:
          15.4% on most services. The withholding is remitted to DGI
          by the paying company, not the supplier.</li>
      <li><b>SALES_TAX</b> — Single-stage tax collected only on the final sale.
          Used in jurisdictions without a full VAT framework.</li>
      <li><b>SERVICE_TAX</b> — A levy specific to services rather than goods.
          Used where a separate services charge applies.</li>
    </ul>
    <p>You can also type any custom type code not listed above.</p>

    <p><b>Calculation Method</b><br/>
    Controls how the tax amount is derived:</p>
    <ul>
      <li><b>PERCENTAGE</b> — Tax = line amount × rate %. The standard method
          for VAT and withholding. Enter the rate in <i>Rate Percent</i>.</li>
      <li><b>FIXED_AMOUNT</b> — A flat amount per line regardless of value.
          Enter the flat amount in <i>Rate Percent</i>. Used for stamp duties
          or fixed levies (e.g. a 1,000 XAF flat fee).</li>
      <li><b>EXEMPT</b> — No tax is calculated. Use this for zero-rated or
          exempt lines where the line still needs a tax code for VAT schedule
          reporting. Set rate to 0.</li>
    </ul>

    <p><b>Rate Percent</b><br/>
    Enter the rate as a plain number: <i>19.25</i> means 19.25%, not 0.1925.
    For EXEMPT codes enter 0. For FIXED_AMOUNT codes enter the flat currency
    amount here. Leave blank only if the code is genuinely rate-free.</p>

    <p><b>Recoverable</b><br/>
    Whether tax paid on purchases can be reclaimed from the tax authority:</p>
    <ul>
      <li><b>Yes</b> — Input tax is deductible. VAT-registered companies reclaim
          input VAT against output VAT. The system posts to the input tax
          recoverable account.</li>
      <li><b>No</b> — Tax is a cost and is expensed directly. Applies to
          withholding tax and irrecoverable import duties.</li>
      <li><b>Not specified</b> — Use only if recoverability varies per transaction
          and is decided at posting time. Avoid this for standard codes.</li>
    </ul>

    <p><b>Effective From / Effective To</b><br/>
    Tax rates change. Use these dates to version your codes over time:</p>
    <ul>
      <li>Set <b>Effective From</b> to the date the rate first applies.
          Transactions before this date will not match this code.</li>
      <li>Leave <b>Effective To</b> blank for codes that are currently active
          with no planned end. Tick <i>Set an end date</i> only when retiring
          a rate: end-date the old code the day before the change, and create
          a fresh code starting the next day with the new rate.</li>
    </ul>

    <p><b>After saving</b><br/>
    Use the <b>Account Mappings</b> button on the Tax Codes list to link this
    code to GL accounts. This step is required before the code can be used on
    posted documents:</p>
    <ul>
      <li><b>Tax Collected account</b> — output/sales tax held as a liability
          until remitted to the authority
          (e.g. 4431 — TVA collectée).</li>
      <li><b>Tax Paid account</b> — input/purchase tax, either posted as a
          recoverable asset (e.g. 4452 — TVA déductible) or expensed directly
          if non-recoverable.</li>
    </ul>

    <p><b>Standard codes to create for Cameroon:</b></p>
    <ul>
      <li><i>VAT_STD</i> — VAT · 19.25% · PERCENTAGE · Recoverable: Yes</li>
      <li><i>VAT_EXEMPT</i> — VAT · 0% · EXEMPT · Recoverable: No</li>
      <li><i>WHT_SVC</i> — Withholding · 15.4% · PERCENTAGE · Recoverable: No</li>
      <li><i>WHT_RENT</i> — Withholding · 15.4% · PERCENTAGE · Recoverable: No</li>
    </ul>
    """,
)

_register(
    "dialog.tax_code_account_mapping",
    "Tax Code Account Mapping",
    "Map a tax code to specific GL accounts for posting.",
    """
    <p>Use this dialog to link a tax code to the GL accounts where tax
    amounts should be posted when invoices and bills are recorded.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Tax Collected Account</b> — the liability account where
          output (sales) tax is posted. When you issue a sales invoice
          with this tax code, the calculated tax amount is credited
          to this account.
          <br/><em>Example:</em> 4431 — TVA Collected (for Cameroon
          19.25% VAT).</li>
      <li><b>Tax Paid Account</b> — the asset account where input
          (purchase) tax is posted. When you enter a purchase bill
          with this tax code, the tax amount is debited to this
          account.
          <br/><em>Example:</em> 4451 — TVA Deductible on Purchases.</li>
    </ul>

    <p><b>How it works in practice:</b></p>
    <ul>
      <li>When a <b>sales invoice</b> with TVA 19.25% is posted:
          Debit AR, Credit Revenue, Credit 4431 TVA Collected.</li>
      <li>When a <b>purchase bill</b> with TVA 19.25% is posted:
          Debit Expense, Debit 4451 TVA Deductible, Credit AP.</li>
      <li>At tax filing time, the net tax liability is:
          TVA Collected (4431) minus TVA Deductible (4451).</li>
    </ul>

    <p><b>Common Cameroon tax accounts:</b></p>
    <ul>
      <li>4431 — TVA Collected (output)</li>
      <li>4451 — TVA Deductible on Purchases (input)</li>
      <li>4432 — TVA Collected on Services</li>
      <li>4441 — Withholding Tax Due</li>
    </ul>

    <p><b>Important:</b> Both accounts must exist in the chart of
    accounts and be active. Incorrect mappings will cause tax amounts
    to post to the wrong accounts, leading to misstated tax returns.</p>
    """,
)

# ── Administration ────────────────────────────────────────────────────────

_register(
    "dialog.login",
    "Login",
    "Sign in to your Seeker Accounting account.",
    """
    <p>Enter your credentials to access the system. Your username and
    password were set by a system administrator when your account was
    created.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Username</b> — your assigned username (case-sensitive).</li>
      <li><b>Password</b> — your login password.</li>
    </ul>

    <p><b>First login:</b> If this is your first time logging in, use
    the credentials provided by your administrator. You will be able to
    change your password afterwards from your profile.</p>

    <p><b>Forgot password:</b> There is no self-service password reset.
    Contact your system administrator to have your password reset.</p>

    <p><b>Security tips:</b></p>
    <ul>
      <li>Do not share your login credentials with others.</li>
      <li>Log out at the end of each session, especially on shared
          workstations.</li>
      <li>If you suspect unauthorised access, change your password
          immediately and notify your administrator.</li>
    </ul>
    """,
)

_register(
    "dialog.onboarding",
    "Onboarding",
    "Initial setup wizard for new Seeker Accounting installations.",
    """
    <p>The <b>Onboarding</b> wizard guides you through the essential
    first-time setup for Seeker Accounting. It runs automatically when
    no companies or users exist in the database.</p>

    <p><b>Step 1 — Administrator Account:</b> Create the first user
    account. This account receives full system administrator privileges.
    Choose a strong password — this is the master admin for the entire
    installation.</p>

    <p><b>Step 2 — First Company:</b> Enter the company name, tax ID,
    address, and base currency (e.g. XAF for Cameroon). This creates the
    company record and seeds the OHADA chart of accounts, default tax
    codes, payment terms, and journal types.</p>

    <p><b>Step 3 — Preferences:</b> Configure basic operating preferences
    such as default payment terms, fiscal year start month, and document
    numbering format.</p>

    <p><b>What happens after onboarding:</b></p>
    <ul>
      <li>The chart of accounts is seeded with SYSCOHADA defaults.</li>
      <li>Standard journals (General, Sales, Purchases, Cash, Bank) are
          created.</li>
      <li>You are logged in as the administrator and can begin setting
          up fiscal periods, additional users, and business data.</li>
    </ul>

    <p><b>Recommended first actions after onboarding:</b></p>
    <ol>
      <li>Create the first fiscal year and its periods.</li>
      <li>Review and customise the chart of accounts.</li>
      <li>Set up financial accounts (bank and cash).</li>
      <li>Create additional user accounts and assign roles.</li>
    </ol>

    <p><b>Tip:</b> All settings configured during onboarding can be
    changed later in Organisation Settings and Administration.</p>
    """,
)

_register(
    "dialog.password_change",
    "Change Password",
    "Change your account password.",
    """
    <p>Use this dialog to update your login password. You must know your
    current password to set a new one.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Current password</b> — enter your existing password to
          verify your identity.</li>
      <li><b>New password</b> — your new password.</li>
      <li><b>Confirm new password</b> — re-enter the new password
          exactly to prevent typos.</li>
    </ul>

    <p><b>Password strength guidelines:</b></p>
    <ul>
      <li>Use at least 8 characters.</li>
      <li>Mix uppercase and lowercase letters, numbers, and special
          characters.</li>
      <li>Avoid easily guessable passwords (e.g. company name,
          <em>password123</em>, sequential numbers).</li>
      <li>Do not reuse passwords from other systems.</li>
    </ul>

    <p><b>Tip:</b> Change your password regularly, especially if you
    suspect it may have been compromised. After changing, you will
    remain logged in — the new password takes effect on your next
    login.</p>
    """,
)

_register(
    "dialog.permission_assignment",
    "Permission Assignment",
    "Assign or modify permissions for a role.",
    """
    <p>Use this dialog to grant or revoke specific permissions within a
    role. Permissions are grouped by module and determine what actions
    users with this role can perform.</p>

    <p><b>Permission groups include:</b></p>
    <ul>
      <li><b>Accounting</b> — chart of accounts, journal entries,
          fiscal periods, posting, period locking.</li>
      <li><b>Sales &amp; Receivables</b> — customers, invoices,
          receipts, credit notes.</li>
      <li><b>Purchases &amp; Payables</b> — suppliers, bills,
          payments, debit notes.</li>
      <li><b>Treasury</b> — financial accounts, transactions,
          bank reconciliation.</li>
      <li><b>Inventory</b> — items, categories, stock movements.</li>
      <li><b>Fixed Assets</b> — assets, depreciation runs.</li>
      <li><b>Payroll</b> — employees, payroll runs, components.</li>
      <li><b>Reports</b> — financial statements, operational reports,
          analysis.</li>
      <li><b>Administration</b> — users, roles, company settings,
          audit log.</li>
    </ul>

    <p><b>Permission levels per module:</b></p>
    <ul>
      <li><b>View</b> — read-only access to lists and records.</li>
      <li><b>Create / Edit</b> — create new records and modify
          drafts.</li>
      <li><b>Post</b> — post documents to the general ledger
          (accounting-sensitive).</li>
      <li><b>Delete</b> — remove draft records.</li>
      <li><b>Admin</b> — module-level administration (e.g. lock
          periods, manage sequences).</li>
    </ul>

    <p><b>Example role configurations:</b></p>
    <ul>
      <li><em>Accountant</em> — full access to Accounting, Reports;
          view-only on Sales, Purchases, Treasury.</li>
      <li><em>Sales Officer</em> — full access to Sales &amp;
          Receivables; view-only on Reports.</li>
      <li><em>Payroll Officer</em> — full access to Payroll;
          view-only on Accounting, Reports.</li>
    </ul>

    <p><b>Important:</b> Changes take effect immediately for all users
    assigned to this role. Review carefully before saving — granting
    Post or Admin permissions gives significant control over financial
    data.</p>
    """,
)

_register(
    "dialog.profile_edit",
    "Edit Profile",
    "Update your user profile information.",
    """
    <p>Use this dialog to update your personal profile details. Changes
    apply immediately and affect how your name appears across the
    application — in the sidebar, on documents you create, and in
    the audit log.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Display name</b> — how your name appears in the system.
          Use your real name as it should appear on reports and audit
          trails (e.g. <em>Marie Ndongo</em>).</li>
      <li><b>Email</b> — your email address. Used for notifications
          and password recovery if configured.</li>
      <li><b>Password</b> — change your login password. You must enter
          your current password first for security.</li>
    </ul>

    <p><b>Important:</b> Your username cannot be changed from this
    dialog — only an administrator can modify usernames. If you need
    a username change, contact your system administrator.</p>

    <p><b>Tip:</b> Use a consistent display name across the organisation
    so that audit trails and document ownership are easy to follow.</p>
    """,
)

_register(
    "dialog.role_assignment",
    "Role Assignment",
    "Assign roles to a user.",
    """
    <p>Use this dialog to assign one or more roles to a user account.
    A user's effective permissions are the <em>union</em> of all their
    assigned roles — if any role grants a permission, the user has it.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Select roles from the available list by checking the box
          next to each role name.</li>
      <li>Uncheck roles to remove them from the user.</li>
      <li>Save to apply the changes.</li>
    </ul>

    <p><b>Common role combinations:</b></p>
    <ul>
      <li><em>Chief Accountant</em> — assign <em>Accountant</em> +
          <em>Report Viewer</em> + <em>Period Manager</em>.</li>
      <li><em>Accounts Clerk</em> — assign <em>Accounts Payable</em> +
          <em>Accounts Receivable</em> (no posting rights).</li>
      <li><em>Managing Director</em> — assign <em>Report Viewer</em>
          only (read-only access to financial overview).</li>
      <li><em>System Admin</em> — assign <em>Administrator</em>
          (full system access).</li>
    </ul>

    <p><b>Tip:</b> Follow the principle of least privilege — assign
    only the roles each user needs for their daily work. Avoid giving
    everyone the Administrator role, even in small companies.</p>
    """,
)

_register(
    "dialog.role_edit",
    "Role",
    "Create or edit a security role.",
    """
    <p>Use this dialog to create a new role or edit an existing one.
    Roles are the building blocks of access control — each role
    represents a job function and carries a set of permissions.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Role name</b> — a clear, descriptive name for the role.
          Use names that reflect job functions rather than individual
          people.</li>
      <li><b>Description</b> — explain what this role is intended for
          and which users should be assigned to it.</li>
    </ul>

    <p><b>Recommended role naming:</b></p>
    <ul>
      <li><em>Accountant</em> — manages chart of accounts, journal
          entries, and period operations.</li>
      <li><em>Accounts Payable Clerk</em> — enters purchase bills and
          supplier payments.</li>
      <li><em>Accounts Receivable Clerk</em> — enters sales invoices
          and customer receipts.</li>
      <li><em>Payroll Officer</em> — manages employees and payroll
          runs.</li>
      <li><em>Report Viewer</em> — read-only access to financial
          reports.</li>
      <li><em>Administrator</em> — full system access including user
          management and configuration.</li>
    </ul>

    <p><b>Workflow:</b> After creating the role, go to
    <em>Permission Assignment</em> to configure exactly which modules
    and actions this role can access. Then assign the role to users
    via <em>Role Assignment</em>.</p>
    """,
)

_register(
    "dialog.user_edit",
    "User",
    "Create or edit a user account.",
    """
    <p>Use this dialog to create a new user or edit an existing user's
    profile and access settings.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Username</b> — unique login identifier. Cannot be changed
          after creation. Choose a consistent convention (e.g.
          <em>mndongo</em>, <em>jean.paul</em>, or <em>EMP042</em>).</li>
      <li><b>Display name</b> — the user's full name as shown in the
          interface and on audit trails (e.g. <em>Marie Ndongo</em>).</li>
      <li><b>Email</b> — email address for notifications and
          identification.</li>
      <li><b>Password</b> — set an initial password when creating a new
          user. For existing users, use the <em>Reset Password</em>
          action if they need a new one.</li>
      <li><b>Active</b> — toggle whether the user can log in. Deactivate
          rather than delete when an employee leaves — this preserves
          audit trail references to their past actions.</li>
    </ul>

    <p><b>Setting up a new user (step by step):</b></p>
    <ol>
      <li>Fill in username, display name, email, and initial password.</li>
      <li>Save the user record.</li>
      <li>Open <em>Role Assignment</em> to grant appropriate roles.</li>
      <li>Communicate the username and initial password to the user
          securely — ask them to change the password on first login.</li>
    </ol>

    <p><b>Tip:</b> Avoid creating shared user accounts (e.g. “Admin”
    used by multiple people). Each person should have their own account
    so that the audit log accurately records who performed each
    action.</p>
    """,
)

# ── Companies ─────────────────────────────────────────────────────────────

_register(
    "dialog.company_form",
    "Company",
    "Create or edit a company record.",
    """
    <p>Use this dialog to create a new company or edit an existing company's
    master data. Each company in Seeker Accounting is a fully independent
    entity with its own chart of accounts, fiscal periods, journals, and
    transactional data.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Company name</b> — the full legal name as registered
          (e.g. <em>Ngum Trading SARL</em>).</li>
      <li><b>Short name</b> — abbreviated display name used in the
          sidebar and company selector (e.g. <em>Ngum Trading</em>).</li>
      <li><b>Tax ID</b> — the company's tax identification number
          (NIU in Cameroon). Appears on printed invoices and
          statutory documents.</li>
      <li><b>Address</b> — registered business address.</li>
      <li><b>Phone / Email</b> — company contact details.</li>
      <li><b>Currency</b> — the company's base operating currency
          (e.g. XAF). All accounting transactions are recorded in
          this currency. This <b>cannot be changed</b> after the
          company has transactions.</li>
    </ul>

    <p><b>Multi-company guidance:</b> Each company you create gets its
    own complete accounting setup. Use separate companies for legally
    distinct entities (e.g. a parent company and its subsidiaries, or
    different business lines with separate legal identities). Do not
    create separate companies for departments or branches of the same
    legal entity — use projects or cost centres instead.</p>

    <p><b>Example:</b> Setting up <em>Ngum Trading SARL</em>:
    <br/>↕ Company name: Ngum Trading SARL
    <br/>↕ Short name: Ngum Trading
    <br/>↕ Tax ID: M012345678901A
    <br/>↕ Address: 123 Rue de la Joie, Douala
    <br/>↕ Currency: XAF</p>

    <p><b>Tip:</b> Company master data appears on printed invoices,
    purchase orders, and reports. Keep it accurate, complete, and
    up to date.</p>
    """,
)

_register(
    "dialog.company_preferences",
    "Company Preferences",
    "Configure company-level operating preferences.",
    """
    <p>Use this dialog to set company-specific preferences that affect
    how the system behaves for this company. These preferences apply to
    all users working within this company context.</p>

    <p><b>Available preferences:</b></p>
    <ul>
      <li><b>Default payment terms</b> — the payment terms
          automatically applied to new sales invoices and purchase bills
          (e.g. Net 30, Net 60). Can be overridden per customer or
          supplier.</li>
      <li><b>Default sales tax code</b> — the tax code pre-selected
          on new invoice lines (e.g. TVA 19.25% for Cameroon standard
          VAT).</li>
      <li><b>Default purchase tax code</b> — the tax code pre-selected
          on new bill lines.</li>
      <li><b>Fiscal year start</b> — the month your fiscal year begins
          (typically January for Cameroon companies following the
          calendar year).</li>
      <li><b>Document formatting</b> — number format, date display
          preferences, and document sequence prefixes.</li>
    </ul>

    <p><b>Example for a Cameroon-based company:</b>
    <br/>↕ Default payment terms: Net 30
    <br/>↕ Default sales tax: TVA 19.25%
    <br/>↕ Default purchase tax: TVA 19.25%
    <br/>↕ Fiscal year start: January</p>

    <p><b>Tip:</b> Setting accurate defaults here saves time during
    daily data entry. Users can always override the defaults on
    individual transactions when needed.</p>
    """,
)

_register(
    "dialog.company_selector",
    "Company Selector",
    "Switch the active company context.",
    """
    <p>Use this dialog to select which company you want to work with.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Browse or search the list of available companies.</li>
      <li>Click a company to make it the active context.</li>
    </ul>

    <p><b>Note:</b> Switching companies changes all data views to reflect
    the selected company's records.</p>
    """,
)

# ── Customers ─────────────────────────────────────────────────────────────

_register(
    "dialog.customer",
    "Customer",
    "Create or edit a customer record.",
    """
    <p>Use this dialog to create a new customer or edit an existing one.</p>

    <p><b>Key sections:</b></p>
    <ul>
      <li><b>Identity</b> — customer code, display name, legal name.</li>
      <li><b>Terms &amp; Contact</b> — payment terms, credit limit,
          phone, email.</li>
      <li><b>Address &amp; Notes</b> — physical address and free-text
          notes.</li>
    </ul>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Customer Code</b> — unique identifier (e.g. CUST-001).</li>
      <li><b>Display Name</b> — the name used in lists and documents.</li>
      <li><b>Payment Term</b> — default terms for this customer's invoices.</li>
      <li><b>Tax Code</b> — default tax code for invoice lines.</li>
      <li><b>Credit Limit</b> — optional maximum outstanding balance.</li>
      <li><b>Customer Group</b> — optional grouping category.</li>
    </ul>

    <p><b>Tip:</b> Set default payment terms and tax codes to speed up
    invoice creation. The system will pre-fill these values.</p>

    <p><b>Example:</b> Setting up a new customer:
    <br/>↕ Code: CUST-004
    <br/>↕ Display Name: Société Mbarga &amp; Fils
    <br/>↕ Payment Term: Net 30
    <br/>↕ Tax Code: TVA 19.25%
    <br/>↕ Credit Limit: 3,000,000 XAF
    <br/>↕ Group: Construction
    <br/>↕ Phone: +237 6xx xxx xxx
    <br/>Now every invoice for this customer will default to Net 30
    terms and TVA 19.25% on line items.</p>
    """,
)

_register(
    "dialog.customer_group",
    "Customer Group",
    "Create or edit a customer group for categorisation.",
    """
    <p>Use this dialog to define a customer group — a way to categorise
    customers for reporting, filtering, and analysis.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Group code</b> — short identifier (e.g. <em>RET</em>,
          <em>WHO</em>, <em>GOV</em>).</li>
      <li><b>Group name</b> — descriptive name (e.g. <em>Retail
          Customers</em>, <em>Wholesale</em>,
          <em>Government &amp; Public Sector</em>).</li>
    </ul>

    <p><b>Common group structures:</b></p>
    <ul>
      <li><b>By channel:</b> Retail, Wholesale, Online, Export.</li>
      <li><b>By sector:</b> Government, Construction, Manufacturing,
          Services, Agriculture.</li>
      <li><b>By region:</b> Douala, Yaoundé, North, South-West,
          Littoral, International.</li>
      <li><b>By relationship:</b> Key Accounts, Regular,
          One-time/Occasional.</li>
    </ul>

    <p><b>Why use groups?</b> Groups let you filter customer lists,
    generate aging reports by segment, and analyse revenue by customer
    type. They are especially useful when you have many customers and
    need to review receivables or sales performance by category.</p>

    <p><b>Tip:</b> Choose one consistent grouping dimension (e.g. by
    channel or by sector) and apply it across all customers. Avoid
    creating too many groups — groups are more useful when each has
    several customers rather than one group per customer.</p>
    """,
)

# ── Suppliers ─────────────────────────────────────────────────────────────

_register(
    "dialog.supplier",
    "Supplier",
    "Create or edit a supplier record.",
    """
    <p>Use this dialog to create a new supplier or edit an existing one.</p>

    <p><b>Key sections:</b></p>
    <ul>
      <li><b>Identity</b> — supplier code, display name, legal name.</li>
      <li><b>Terms &amp; Contact</b> — payment terms, phone, email.</li>
      <li><b>Address &amp; Notes</b> — physical address and notes.</li>
    </ul>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Supplier Code</b> — unique identifier.</li>
      <li><b>Display Name</b> — name in lists and documents.</li>
      <li><b>Payment Term</b> — default terms for this supplier's bills.</li>
      <li><b>Tax Code</b> — default tax code for bill lines.</li>
      <li><b>Supplier Group</b> — optional grouping category.</li>
    </ul>

    <p><b>Tip:</b> Set default payment terms and tax codes per supplier to
    speed up purchase bill entry.</p>

    <p><b>Example:</b> Setting up a new supplier:
    <br/>↕ Code: SUPP-004
    <br/>↕ Display Name: Quincaillerie Ndongo
    <br/>↕ Payment Term: Net 45
    <br/>↕ Tax Code: TVA 19.25%
    <br/>↕ Group: Hardware
    <br/>Future bills from this supplier will default to Net 45 terms.</p>
    """,
)

_register(
    "dialog.supplier_group",
    "Supplier Group",
    "Create or edit a supplier group for categorisation.",
    """
    <p>Use this dialog to define a supplier group for categorisation and
    reporting.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Group code</b> — short identifier (e.g. <em>LOC</em>,
          <em>IMP</em>, <em>SVC</em>).</li>
      <li><b>Group name</b> — descriptive name (e.g. <em>Local
          Suppliers</em>, <em>Importers</em>, <em>Service
          Providers</em>).</li>
    </ul>

    <p><b>Common group structures:</b></p>
    <ul>
      <li><b>By type:</b> Raw Materials, Finished Goods, Services,
          Equipment, Utilities.</li>
      <li><b>By geography:</b> Local, Regional, International,
          CEMAC Zone.</li>
      <li><b>By criticality:</b> Strategic Partners, Regular Suppliers,
          Occasional.</li>
    </ul>

    <p><b>Why use groups?</b> Groups let you filter supplier lists,
    generate AP aging by category, and analyse spending patterns by
    supplier type. Useful for procurement reviews and payment
    prioritisation.</p>

    <p><b>Tip:</b> Keep groups broad and meaningful. A good test: each
    group should have at least 3–5 suppliers. If most groups have only
    one supplier, your categories are too granular.</p>
    """,
)

# ── Sales ─────────────────────────────────────────────────────────────────

_register(
    "dialog.sales_invoice",
    "Sales Invoice",
    "Create or edit a sales invoice.",
    """
    <p>Use this dialog to create a new sales invoice or edit a draft.</p>

    <p><b>Header fields:</b></p>
    <ul>
      <li><b>Customer</b> — select the customer being invoiced.</li>
      <li><b>Invoice date</b> — the date of the invoice.</li>
      <li><b>Due date</b> — auto-calculated from payment terms.</li>
      <li><b>Reference</b> — auto-generated from the document sequence.</li>
    </ul>

    <p><b>Line items:</b></p>
    <ul>
      <li>Each line has a description, quantity, unit price, tax code, and
          revenue account.</li>
      <li>Line totals and tax are calculated automatically.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>Save Draft</b> — save without posting (no GL impact).</li>
      <li><b>Post</b> — create the GL journal entry (AR debit, Revenue
          and Tax credits).</li>
    </ul>

    <p><b>Tip:</b> Review all line items, taxes, and totals before posting.
    Posted invoices cannot be edited — only voided.</p>

    <p><b>Example:</b> Invoice to Brasseries du Cameroun:
    <br/>↕ Line 1: Cement 50kg × 100 bags @ 4,500 = 450,000 XAF
    <br/>↕ Line 2: Delivery fee = 25,000 XAF
    <br/>↕ Subtotal: 475,000 XAF
    <br/>↕ TVA 19.25%: 91,438 XAF
    <br/>↕ Total: 566,438 XAF
    <br/>On posting: Debit 411000 AR 566,438 | Credit 701000
    Revenue 475,000 | Credit 4431 TVA 91,438.</p>
    """,
)

_register(
    "dialog.customer_receipt",
    "Customer Receipt",
    "Record a payment received from a customer.",
    """
    <p>Use this dialog to record a customer payment and allocate it
    against outstanding invoices.</p>

    <p><b>Header fields:</b></p>
    <ul>
      <li><b>Customer</b> — the paying customer.</li>
      <li><b>Financial account</b> — the bank or cash account receiving
          the payment.</li>
      <li><b>Amount</b> — the total payment amount received.</li>
      <li><b>Date</b> — the date the payment was received.</li>
      <li><b>Reference</b> — payment reference, cheque number, or
          bank transfer reference.</li>
    </ul>

    <p><b>Allocation section:</b></p>
    <p>The system shows all outstanding invoices for the selected
    customer. Tick the invoices being paid and enter the amount
    allocated to each. The total of allocations must not exceed the
    receipt amount.</p>

    <p><b>Example:</b> Customer <em>Mbeki Corp</em> sends a bank
    transfer for 1,500,000 XAF:
    <br/>↕ Receipt amount: 1,500,000 XAF
    <br/>↕ Allocate to INV-2026-0031 (200,000 XAF) — full
    <br/>↕ Allocate to INV-2026-0038 (800,000 XAF) — full
    <br/>↕ Allocate to INV-2026-0042 (500,000 of 750,000 XAF) —
    partial
    <br/>Total allocated: 1,500,000 XAF. INV-0042 still has 250,000
    outstanding.</p>

    <p><b>Under-allocation:</b> If the receipt amount exceeds the
    allocated total, the difference remains as an unallocated credit
    on the customer's account. You can allocate it later when new
    invoices are raised.</p>

    <p><b>Over-payment:</b> If a customer pays more than is owed,
    record the full amount received. The excess becomes an unallocated
    credit that will offset against future invoices.</p>

    <p><b>Posting:</b> When posted, the system creates a journal entry:
    Debit Bank/Cash, Credit Accounts Receivable (customer control
    account).</p>

    <p><b>Tip:</b> Always allocate receipts to specific invoices to
    maintain accurate customer balances and aging reports. Unallocated
    receipts make it difficult to determine which invoices are truly
    outstanding.</p>
    """,
)

# ── Purchases ─────────────────────────────────────────────────────────────

_register(
    "dialog.purchase_bill",
    "Purchase Bill",
    "Create or edit a purchase bill from a supplier.",
    """
    <p>Use this dialog to record a purchase bill (supplier invoice).</p>

    <p><b>Header fields:</b></p>
    <ul>
      <li><b>Supplier</b> — the supplier issuing the bill.</li>
      <li><b>Bill date</b> — the date on the supplier's invoice.</li>
      <li><b>Due date</b> — auto-calculated from payment terms.</li>
      <li><b>External reference</b> — the supplier's invoice number.</li>
    </ul>

    <p><b>Line items:</b></p>
    <ul>
      <li>Each line has a description, amount, tax code, and expense
          or asset account.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>Save Draft</b> — save without posting.</li>
      <li><b>Post</b> — create the GL journal entry (Expense/Asset debit,
          AP and Tax credits).</li>
    </ul>

    <p><b>Tip:</b> Always enter the supplier's invoice number in the
    external reference field for easy cross-referencing.</p>

    <p><b>Example:</b> Bill from Cimencam (their invoice #FAC-2026-118):
    <br/>↕ Line 1: Cement CEM II 50kg × 200 bags @ 4,200 = 840,000 XAF
    <br/>↕ Line 2: Iron rods 12mm × 50 @ 8,500 = 425,000 XAF
    <br/>↕ Subtotal: 1,265,000 XAF
    <br/>↕ TVA 19.25%: 243,513 XAF
    <br/>↕ Total: 1,508,513 XAF
    <br/>On posting: Debit 601000 Purchases 1,265,000 | Debit 4451
    TVA Deductible 243,513 | Credit 401000 AP 1,508,513.</p>
    """,
)

_register(
    "dialog.supplier_payment",
    "Supplier Payment",
    "Record a payment made to a supplier.",
    """
    <p>Use this dialog to record a payment to a supplier and allocate it
    against outstanding bills.</p>

    <p><b>Header fields:</b></p>
    <ul>
      <li><b>Supplier</b> — the supplier being paid.</li>
      <li><b>Financial account</b> — the bank or cash account the
          payment is made from.</li>
      <li><b>Amount</b> — the total payment amount.</li>
      <li><b>Date</b> — the payment date.</li>
      <li><b>Reference</b> — payment reference, cheque number, or
          transfer reference.</li>
    </ul>

    <p><b>Allocation section:</b></p>
    <p>The system shows all outstanding bills for the selected supplier.
    Tick the bills being paid and enter the allocated amount for each.
    The total allocations must not exceed the payment amount.</p>

    <p><b>Example:</b> Paying supplier <em>Cameroun Fournitures</em>
    by cheque for 2,000,000 XAF:
    <br/>↕ Payment amount: 2,000,000 XAF
    <br/>↕ Allocate to BILL-2026-0018 (1,200,000 XAF) — full
    <br/>↕ Allocate to BILL-2026-0023 (800,000 XAF) — full
    <br/>Total allocated: 2,000,000 XAF. Both bills are now fully
    paid.</p>

    <p><b>Partial payments:</b> You can pay part of a bill. The
    remaining balance stays outstanding and appears in the AP aging
    report.</p>

    <p><b>Posting:</b> When posted, the system creates a journal entry:
    Debit Accounts Payable (supplier control account), Credit
    Bank/Cash.</p>

    <p><b>Tip:</b> Always allocate payments to specific bills to maintain
    accurate supplier balances and aging. Check supplier statements
    against your records to ensure nothing is missed.</p>
    """,
)

# ── Treasury ──────────────────────────────────────────────────────────────

_register(
    "dialog.financial_account",
    "Financial Account",
    "Create or edit a bank or cash account.",
    """
    <p>Use this dialog to set up a financial account representing a real-world
    bank account or cash fund.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Account name</b> — descriptive name (e.g. "Main Bank - XAF").</li>
      <li><b>Bank name</b> — name of the banking institution.</li>
      <li><b>Account number</b> — the bank account number.</li>
      <li><b>Account type</b> — Bank, Cash, or other.</li>
      <li><b>Currency</b> — the account's currency.</li>
      <li><b>GL account</b> — the linked general ledger account.</li>
      <li><b>Opening balance</b> — the starting balance.</li>
    </ul>

    <p><b>Tip:</b> Ensure the GL account link is correct — all transactions
    against this financial account will post to the linked GL account.</p>

    <p><b>Example:</b> Setting up your primary bank account:
    <br/>↕ Account name: Afriland First Bank — XAF
    <br/>↕ Bank name: Afriland First Bank
    <br/>↕ Account number: 10234-56789-01
    <br/>↕ Account type: Bank
    <br/>↕ Currency: XAF
    <br/>↕ GL account: 521100 — Bank Afriland
    <br/>↕ Opening balance: 8,500,000 XAF
    <br/>All receipts and payments through this account will post to
    GL 521100.</p>
    """,
)

_register(
    "dialog.manual_statement_line",
    "Manual Statement Line",
    "Add a bank statement line manually.",
    """
    <p>Use this dialog to manually enter a bank statement line when you
    don't have a file to import — for example, when entering statement
    lines from a paper bank statement or correcting gaps in imported
    data.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Date</b> — the transaction date as it appears on the bank
          statement.</li>
      <li><b>Description</b> — the bank's description of the
          transaction (e.g. <em>Transfer from Ngum Trading</em>,
          <em>MTN Mobile Money CR</em>).</li>
      <li><b>Amount</b> — the transaction amount. Use a <b>positive
          value</b> for money coming in (credits / deposits) and a
          <b>negative value</b> for money going out (debits /
          withdrawals).</li>
    </ul>

    <p><b>Example:</b> Entering a bank charge:
    <br/>↕ Date: 31 March 2026
    <br/>↕ Description: Bank charges March 2026
    <br/>↕ Amount: -15,000 (negative because it reduces the
    balance)</p>

    <p><b>When to use:</b> Manual entry is useful for:
    <br/>↕ • Banks that don't provide electronic statement exports
    <br/>↕ • Adding individual missing transactions to an imported
    statement
    <br/>↕ • Entering mobile money statement lines</p>

    <p><b>Tip:</b> After adding statement lines, proceed to the bank
    reconciliation workflow to match them against your posted
    transactions.</p>
    """,
)

_register(
    "dialog.statement_import",
    "Statement Import",
    "Import bank statement data from a file.",
    """
    <p>Use this dialog to import bank statement lines from a file,
    saving time compared to manual entry.</p>

    <p><b>Steps:</b></p>
    <ol>
      <li><b>Select financial account</b> — choose the bank or cash
          account these statement lines belong to.</li>
      <li><b>Choose file format</b> — select CSV or a supported bank
          format.</li>
      <li><b>Select file</b> — browse and pick the statement file from
          your computer.</li>
      <li><b>Map columns</b> — if the format isn't auto-detected,
          specify which columns contain the date, description, and
          amount.</li>
      <li><b>Review preview</b> — check the parsed lines before
          importing to catch format issues.</li>
      <li><b>Confirm import</b> — commit the lines into the system.</li>
    </ol>

    <p><b>CSV format requirements:</b></p>
    <ul>
      <li>The file must contain at minimum: <b>date</b>,
          <b>description</b>, and <b>amount</b> columns.</li>
      <li>Dates should be in a consistent format (e.g. DD/MM/YYYY or
          YYYY-MM-DD).</li>
      <li>Amounts can be in a single column (positive for credits,
          negative for debits) or in separate Debit/Credit columns.</li>
      <li>The first row should contain column headers.</li>
    </ul>

    <p><b>Example CSV layout:</b></p>
    <p><code>Date,Description,Amount</code>
    <br/><code>01/03/2026,Transfer from Ngum Trading,1500000</code>
    <br/><code>05/03/2026,Rent payment,-800000</code>
    <br/><code>10/03/2026,Bank charges,-15000</code></p>

    <p><b>Tip:</b> If your import preview shows garbled data, check
    the column mapping and date format settings. Most Cameroon banks
    export statements in DD/MM/YYYY format.</p>
    """,
)

_register(
    "dialog.treasury_transaction",
    "Treasury Transaction",
    "Create or edit a manual treasury transaction.",
    """
    <p>Use this dialog to record a manual cash or bank transaction that
    doesn't originate from an invoice, bill, or standard receipt/payment.
    These are typically bank charges, interest, government levies, or
    other direct bank movements.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Financial account</b> — the bank or cash account affected.</li>
      <li><b>Date</b> — the transaction date.</li>
      <li><b>Amount</b> — the transaction amount (positive for money in,
          negative for money out).</li>
      <li><b>Counterpart account</b> — the GL account for the other side
          of the double entry.</li>
      <li><b>Description</b> — what this transaction records.</li>
    </ul>

    <p><b>Common counterpart accounts:</b></p>
    <ul>
      <li><b>Bank charges</b> — use the bank charges expense account
          (e.g. 631 — Banking Fees).</li>
      <li><b>Interest income</b> — use the interest income account
          (e.g. 771 — Interest Revenue).</li>
      <li><b>Government levies</b> — use the relevant tax or duty
          account.</li>
      <li><b>Foreign exchange gain/loss</b> — use the FX gain/loss
          account (e.g. 666 — Exchange Losses, 766 — Exchange Gains).</li>
    </ul>

    <p><b>Example:</b> Recording monthly bank charges:
    <br/>↕ Financial account: Main Bank — XAF
    <br/>↕ Date: 31 March 2026
    <br/>↕ Amount: -15,000
    <br/>↕ Counterpart: 631 — Banking Fees
    <br/>↕ Description: Bank charges March 2026
    <br/>Result: Debit 631 Banking Fees 15,000 / Credit 521 Bank 15,000</p>

    <p><b>Posting:</b> When posted, this creates a balanced journal
    entry: one side hits the financial account's linked GL account, the
    other side hits the counterpart account you specify.</p>

    <p><b>Tip:</b> Do not use treasury transactions for customer
    receipts or supplier payments — use the dedicated Receipt and
    Payment dialogs so that allocations and subledger balances are
    maintained correctly.</p>
    """,
)

_register(
    "dialog.treasury_transfer",
    "Treasury Transfer",
    "Create a fund transfer between financial accounts.",
    """
    <p>Use this dialog to transfer funds between your company's financial
    accounts — for example, moving cash from a bank account to the petty
    cash fund, or transferring between two bank accounts.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>From account</b> — the source financial account (money
          leaves here).</li>
      <li><b>To account</b> — the destination financial account (money
          arrives here).</li>
      <li><b>Amount</b> — the transfer amount.</li>
      <li><b>Date</b> — the date of the transfer.</li>
      <li><b>Description</b> — reason for the transfer (e.g.
          <em>Replenish petty cash</em>, <em>Move funds to savings
          account</em>).</li>
    </ul>

    <p><b>Example:</b> Replenishing petty cash from the main bank:
    <br/>↕ From: Main Bank — XAF
    <br/>↕ To: Petty Cash
    <br/>↕ Amount: 200,000 XAF
    <br/>↕ Description: Petty cash replenishment April 2026
    <br/>Result: Debit Petty Cash GL / Credit Main Bank GL for
    200,000 XAF.</p>

    <p><b>How it works:</b> The system creates a balanced journal entry
    that debits the destination account's linked GL account and credits
    the source account's linked GL account. Both financial account
    balances update accordingly.</p>

    <p><b>Tip:</b> Transfers are internal movements and do not involve
    customers or suppliers. If you need to record a payment to a
    supplier, use the Supplier Payment dialog instead.</p>
    """,
)

# ── Inventory ─────────────────────────────────────────────────────────────

_register(
    "dialog.inventory_document",
    "Inventory Document",
    "Create an inventory receipt, issue, adjustment, or transfer.",
    """
    <p>Use this dialog to record inventory movements. The document type
    determines how stock quantities and accounting entries are affected.</p>

    <p><b>Header fields:</b></p>
    <ul>
      <li><b>Document type</b> — determines the nature of the movement:
        <ul>
          <li><em>Receipt</em> — goods coming in (purchase delivery,
              production output).</li>
          <li><em>Issue</em> — goods going out (consumption, write-off,
              sample delivery).</li>
          <li><em>Adjustment</em> — correct stock quantities after a
              physical count (can increase or decrease).</li>
          <li><em>Transfer</em> — move stock between locations.</li>
        </ul>
      </li>
      <li><b>Location</b> — the inventory location affected (for
          transfers, this is the source location).</li>
      <li><b>Date</b> — the document date.</li>
      <li><b>Reference</b> — optional external reference (delivery note
          number, count sheet reference, etc.).</li>
    </ul>

    <p><b>Line items:</b></p>
    <ul>
      <li>Each line specifies an <b>item</b>, <b>quantity</b>, and
          optionally a <b>unit cost</b>.</li>
      <li>For <em>Receipts</em>, cost determines the inventory
          valuation entry.</li>
      <li>For <em>Transfers</em>, specify the <b>destination location</b>
          on each line.</li>
    </ul>

    <p><b>Example — Stock adjustment after physical count:</b>
    <br/>↕ Type: Adjustment | Location: Main Warehouse
    <br/>↕ Line 1: Item <em>Cement 50kg</em>, Book qty: 120, Counted:
    115, Adjustment: -5
    <br/>↕ Line 2: Item <em>Steel Bar 12mm</em>, Book qty: 85, Counted:
    88, Adjustment: +3</p>

    <p><b>Accounting impact:</b> When posted, receipts and issues
    create journal entries (Debit/Credit Inventory accounts vs.
    COGS, adjustment, or receiving accounts). Transfers between
    locations of the same company have no P&amp;L impact.</p>

    <p><b>Tip:</b> Save as Draft first to verify quantities and costs.
    Once posted, inventory documents cannot be edited — only reversed
    with a correcting document.</p>
    """,
)

_register(
    "dialog.item",
    "Item",
    "Create or edit an inventory item.",
    """
    <p>Use this dialog to define a new inventory item or edit an existing
    one. Items represent the goods your company buys, sells, and
    tracks in stock.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Item code</b> — unique identifier within the company
          (e.g. <em>CEM-50KG</em>, <em>STL-12MM</em>). Choose a
          consistent naming convention.</li>
      <li><b>Item name</b> — descriptive name (e.g. <em>Cement 50kg
          Bag</em>, <em>Steel Bar 12mm</em>).</li>
      <li><b>Category</b> — item category. This determines the default
          GL accounts used for inventory valuation, COGS, and revenue
          when the item is posted.</li>
      <li><b>Unit of measure</b> — how the item is counted
          (e.g. <em>Bag</em>, <em>Piece</em>, <em>Metre</em>,
          <em>Kg</em>).</li>
      <li><b>Cost price</b> — standard purchase cost per unit. Used
          as the default when entering purchase bills.</li>
      <li><b>Selling price</b> — standard selling price per unit.
          Used as the default when creating sales invoices.</li>
      <li><b>Description</b> — detailed description or notes.</li>
      <li><b>Active</b> — whether the item can be used in new
          transactions. Set to inactive for discontinued items
          (existing transactions are preserved).</li>
    </ul>

    <p><b>Example — setting up a new item:</b>
    <br/>↕ Code: CEM-50KG
    <br/>↕ Name: Cement 50kg Bag
    <br/>↕ Category: Building Materials
    <br/>↕ UoM: Bag
    <br/>↕ Cost price: 4,500 XAF
    <br/>↕ Selling price: 5,200 XAF</p>

    <p><b>Costing method:</b> The costing method (Weighted Average,
    FIFO, or Standard Cost) is set at the category level, not per item.
    All items in a category share the same costing method. Choose the
    category carefully — it determines how inventory value and cost of
    goods sold are calculated.</p>

    <p><b>Tip:</b> Setting default prices speeds up document creation.
    Prices can always be overridden on individual invoices, bills, and
    inventory documents.</p>
    """,
)

# ── Fixed Assets ──────────────────────────────────────────────────────────

_register(
    "dialog.asset",
    "Asset",
    "Create or edit a fixed asset record.",
    """
    <p>Use this dialog to register a new fixed asset or edit an existing one.
    Selecting a category pre-fills default depreciation parameters and GL
    accounts, but every field can be overridden per asset.</p>

    <hr/>
    <p><b>Fields</b></p>
    <ul>
      <li><b>Asset number</b> — unique identifier for the asset.</li>
      <li><b>Asset name</b> — descriptive name.</li>
      <li><b>Category</b> — asset category (sets default depreciation
          parameters and GL accounts).</li>
      <li><b>Acquisition date</b> — when the asset was acquired. This is the
          date used to begin depreciation calculations.</li>
      <li><b>Capitalization date</b> — when the asset was placed in service.
          Often the same as acquisition date; can differ for assets under
          construction or transit.</li>
      <li><b>Acquisition cost</b> — total cost of the asset, including
          purchase price, delivery, installation, and any costs to bring it
          to working condition.</li>
      <li><b>Salvage (residual) value</b> — estimated value at the end of
          useful life. The depreciable amount = cost &minus; salvage value.</li>
      <li><b>Useful life</b> — expected useful life in years and months.</li>
      <li><b>Method</b> — depreciation method (see below).</li>
    </ul>

    <hr/>
    <p><b>Depreciation Methods Explained</b></p>

    <p><b>Straight-Line</b> — the simplest and most common method.
    Spreads the depreciable amount evenly over the useful life.</p>
    <ul>
      <li><i>Formula:</i>&ensp;Monthly depreciation =
        (Cost &minus; Salvage) &divide; Useful life in months</li>
      <li><i>Best for:</i>&ensp;Assets that lose value at a steady rate —
        buildings, furniture, fixtures, leasehold improvements.</li>
      <li><i>Example:</i>&ensp;A desk costing 600,000, salvage 60,000,
        useful life 5 years (60 months). Monthly depreciation =
        (600,000 &minus; 60,000) &divide; 60 = <b>9,000 / month</b>.</li>
    </ul>

    <p><b>Reducing Balance (Declining Balance)</b> — applies a fixed
    percentage to the <i>remaining</i> book value each period, producing
    higher charges early and lower charges later.</p>
    <ul>
      <li><i>Formula:</i>&ensp;Period depreciation =
        Book value at start of period &times; Declining factor &divide;
        Useful life in years. (A declining factor of 2.0 gives Double
        Declining Balance; 1.5 gives 150% DB.)</li>
      <li><i>Best for:</i>&ensp;Assets that lose value quickly at first —
        vehicles, computers, electronics, machinery.</li>
      <li><i>Switch to straight-line:</i>&ensp;Many businesses switch to
        straight-line partway through when the straight-line charge exceeds
        the declining-balance charge. Enable this in Method Settings.</li>
      <li><i>Example:</i>&ensp;A vehicle costing 10,000,000, salvage 1,000,000,
        useful life 5 years, declining factor 2.0 (double).
        Year 1: 10,000,000 &times; (2 &divide; 5) = <b>4,000,000</b>.
        Year 2: 6,000,000 &times; 0.4 = <b>2,400,000</b>.
        Year 3: 3,600,000 &times; 0.4 = <b>1,440,000</b>, and so on —
        never below salvage value.</li>
    </ul>

    <p><b>Sum-of-Years-Digits (SYD)</b> — an accelerated method that
    front-loads depreciation using a fraction based on the remaining life.</p>
    <ul>
      <li><i>Formula:</i>&ensp;Year N depreciation =
        (Remaining years &divide; Sum of year digits) &times;
        (Cost &minus; Salvage).
        For a 5-year life, the sum = 5+4+3+2+1 = 15.</li>
      <li><i>Best for:</i>&ensp;Assets that are most productive early —
        technology equipment, specialised tooling.</li>
      <li><i>Example:</i>&ensp;Equipment costing 1,500,000, salvage 0,
        useful life 5 years (sum = 15).
        Year 1: 5/15 &times; 1,500,000 = <b>500,000</b>.
        Year 2: 4/15 &times; 1,500,000 = <b>400,000</b>.
        Year 3: 3/15 &times; 1,500,000 = <b>300,000</b>.</li>
    </ul>

    <p><b>Units of Production</b> — depreciation is based on actual usage
    rather than time, so charges vary each period.</p>
    <ul>
      <li><i>Formula:</i>&ensp;Period depreciation =
        (Cost &minus; Salvage) &divide; Total expected units &times;
        Units produced this period.</li>
      <li><i>Best for:</i>&ensp;Assets whose wear depends on use —
        factory machines, printing presses, delivery trucks (by km).</li>
      <li><i>Requires:</i>&ensp;You must record usage each period in the
        Method Settings section (expected total units) and log actual usage
        before each depreciation run.</li>
      <li><i>Example:</i>&ensp;A machine costing 5,000,000, salvage 500,000,
        expected output 100,000 units. Per-unit rate =
        (5,000,000 &minus; 500,000) &divide; 100,000 = 45.
        A month producing 2,000 units: <b>90,000</b> depreciation.</li>
    </ul>

    <p><b>Component Depreciation</b> — the asset is broken into major
    components (e.g. engine, body, avionics), each depreciated separately
    with its own method and life.</p>
    <ul>
      <li><i>Best for:</i>&ensp;Complex assets with parts that wear at
        different rates — aircraft, ships, large plant equipment.</li>
      <li><i>Requires:</i>&ensp;Define child components after saving the
        parent asset.</li>
    </ul>

    <p><b>Amortization (Straight-Line for Intangibles)</b> — identical
    calculation to straight-line, used for intangible assets such as patents,
    trademarks, and software licenses where "amortization" is the correct
    accounting term.</p>

    <hr/>
    <p><b>Which method should I choose?</b></p>
    <table cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
      <tr style="background:#f0f0f0;"><td><b>Situation</b></td><td><b>Recommended method</b></td></tr>
      <tr><td>Steady, predictable usage</td><td>Straight-Line</td></tr>
      <tr><td>Loses value fastest when new</td><td>Reducing Balance or SYD</td></tr>
      <tr><td>Value depends on how much it's used</td><td>Units of Production</td></tr>
      <tr><td>Complex asset with replaceable parts</td><td>Component</td></tr>
      <tr><td>Intangible asset (patent, licence)</td><td>Amortization</td></tr>
      <tr><td>Regulatory / tax compliance (US MACRS)</td><td>MACRS</td></tr>
    </table>

    <hr/>
    <p><b>Tips</b></p>
    <ul>
      <li>Ensure the <b>acquisition date</b> is correct — it determines when
        depreciation starts.</li>
      <li>Use <b>Depreciation Schedule Preview</b> (from the asset list) to
        verify the projected schedule before running depreciation.</li>
      <li>Category defaults apply when creating a new asset; changing the
        category after creation does not retroactively adjust posted
        depreciation.</li>
      <li>For reducing-balance methods, check <b>Method Settings</b> to set
        the declining factor and whether to switch to straight-line
        automatically.</li>
    </ul>
    """,
)

_register(
    "dialog.asset_category",
    "Asset Category",
    "Create or edit a fixed asset category.",
    """
    <p>Use this dialog to define a fixed asset category.  Categories set the
    default depreciation method, useful life, and GL account mappings for
    every asset assigned to them.  Individual assets can override these
    defaults.</p>

    <p><b>Fields</b></p>
    <ul>
      <li><b>Category code</b> — short identifier (e.g. <i>OFFEQ</i>).</li>
      <li><b>Category name</b> — descriptive name (e.g. "Office Equipment").</li>
      <li><b>Depreciation method</b> — default method for new assets in this
          category.  See the Asset help for a detailed guide to each
          method.</li>
      <li><b>Useful life</b> — default useful life in months.</li>
      <li><b>Asset account</b> — GL account that records the asset cost
          (debit on acquisition).</li>
      <li><b>Depreciation account</b> — contra-asset GL account for
          accumulated depreciation (credit each period).</li>
      <li><b>Expense account</b> — income-statement GL account for the
          depreciation expense charge (debit each period).</li>
    </ul>

    <p><b>Tips</b></p>
    <ul>
      <li>Proper GL mappings ensure depreciation posts to the correct
        accounts automatically when you run depreciation.</li>
      <li>Common categories: <i>Buildings</i>, <i>Vehicles</i>,
        <i>Office Equipment</i>, <i>IT Equipment</i>,
        <i>Furniture &amp; Fixtures</i>, <i>Machinery</i>,
        <i>Intangible Assets</i>.</li>
      <li>Changing category defaults only affects assets created afterward;
        existing assets keep their current settings.</li>
    </ul>
    """,
)

_register(
    "dialog.depreciation_run",
    "Depreciation Run",
    "Create and execute a monthly depreciation calculation.",
    """
    <p>Use this dialog to create a depreciation run for a specific fiscal
    period.  A single run calculates depreciation for <b>every eligible
    asset</b> in the active company.</p>

    <p><b>Fields</b></p>
    <ul>
      <li><b>Period</b> — the fiscal period to depreciate. Only open
        (unlocked) periods are available.</li>
      <li><b>Description</b> — optional note for audit purposes.</li>
    </ul>

    <p><b>Workflow</b></p>
    <ol>
      <li><b>Create</b> the run for the target period.</li>
      <li>The system calculates each asset's depreciation amount based on
        its method, useful life, cost, salvage value, and any usage records
        (for units-of-production assets).</li>
      <li><b>Review</b> the calculated line items.  You can inspect
        individual assets to verify amounts before committing.</li>
      <li><b>Post</b> to generate journal entries that debit each asset's
        depreciation expense account and credit the accumulated depreciation
        account.</li>
    </ol>

    <p><b>Important notes</b></p>
    <ul>
      <li>A period can only have one depreciation run.  Re-running requires
        reversing the previous run first.</li>
      <li>Assets with a status of <i>Disposed</i> or <i>Fully Depreciated</i>
        are automatically excluded.</li>
      <li>For <b>units-of-production</b> assets, make sure usage records are
        entered for the period before creating the run — otherwise those
        assets will show zero depreciation.</li>
      <li>Posting is irreversible in normal flows; use the schedule preview
        to double-check before posting.</li>
    </ul>
    """,
)

_register(
    "dialog.depreciation_schedule_preview",
    "Depreciation Schedule Preview",
    "Preview the full depreciation schedule for an asset.",
    """
    <p>This dialog projects the complete depreciation schedule for a
    selected asset — from acquisition through full depreciation or the end
    of its useful life.</p>

    <p><b>What you'll see</b></p>
    <ul>
      <li><b>Period</b> — each month or year in the schedule.</li>
      <li><b>Depreciation amount</b> — the charge for that period.</li>
      <li><b>Cumulative depreciation</b> — total depreciation to date.</li>
      <li><b>Net book value</b> — remaining carrying value
        (Cost &minus; Cumulative depreciation).</li>
    </ul>

    <p><b>How to use it</b></p>
    <ul>
      <li>Open the preview <i>before</i> your first depreciation run to
        confirm the method, useful life, and salvage value produce the
        expected schedule.</li>
      <li>For <b>reducing-balance</b> methods, the preview shows exactly
        when the system will switch to straight-line (if enabled) and
        the effect on later periods.</li>
      <li>For <b>units-of-production</b> assets, the preview uses the
        expected total units to project a hypothetical even-usage schedule.
        Actual results will differ based on real usage records.</li>
    </ul>

    <p><b>Tip:</b> If the schedule doesn't look right, close the preview,
    edit the asset's depreciation parameters, and preview again. No
    depreciation is recorded until you create and post a depreciation
    run.</p>
    """,
)

# ── Budgeting ─────────────────────────────────────────────────────────────

_register(
    "dialog.budget_version",
    "Budget Version",
    "Create or edit a budget version.",
    """
    <p>Use this dialog to define a budget version — a named set of
    budget figures for a fiscal year. Budget versions let you maintain
    multiple budgets (original, revised, best case, worst case) and
    compare them against actual results.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Version name</b> — a descriptive name that identifies
          this budget (e.g. <em>Original Budget 2026</em>,
          <em>Revised Q2 2026</em>, <em>Board-Approved Budget</em>).</li>
      <li><b>Fiscal year</b> — the fiscal year this budget covers.
          Budget lines will follow the periods defined in this fiscal
          year.</li>
      <li><b>Status</b> — controls the version's lifecycle:
        <ul>
          <li><em>Draft</em> — being prepared. Budget lines can be
              freely edited.</li>
          <li><em>Active</em> — the approved budget used for
              variance reporting. Only one version should be Active
              per project at a time.</li>
          <li><em>Archived</em> — retained for historical reference
              but not used in active reporting.</li>
        </ul>
      </li>
    </ul>

    <p><b>Typical workflow:</b></p>
    <ol>
      <li>Create a Draft version and enter budget lines.</li>
      <li>Review and adjust until approved by management.</li>
      <li>Set status to Active for variance reporting.</li>
      <li>If conditions change mid-year, create a new Revised version
          and make it Active. Archive the previous version.</li>
    </ol>

    <p><b>Tip:</b> Keep the Active version aligned with management's
    approved targets. Create separate versions for what-if scenarios
    rather than editing the Active version directly.</p>
    """,
)

_register(
    "dialog.budget_lines",
    "Budget Lines",
    "Define budget amounts by account and period.",
    """
    <p>Use this dialog to enter budget amounts for a specific budget
    version. Each line represents a budgeted amount for one GL account
    in one fiscal period.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Select a <b>GL account</b> from the chart of accounts.</li>
      <li>Enter the <b>budgeted amount</b> for each fiscal period
          (typically monthly).</li>
      <li>Repeat for all accounts that need budget figures.</li>
    </ul>

    <p><b>Example — budgeting a revenue account:</b>
    <br/>↕ Account: 701 — Sales of Finished Goods
    <br/>↕ January: 8,000,000 XAF
    <br/>↕ February: 8,500,000 XAF
    <br/>↕ March: 9,000,000 XAF
    <br/>↕ … (continue for each period in the fiscal year)</p>

    <p><b>Revenue vs. expense budgets:</b></p>
    <ul>
      <li><b>Revenue accounts</b> (class 7) — enter expected income
          amounts as positive numbers.</li>
      <li><b>Expense accounts</b> (class 6) — enter expected spending
          amounts as positive numbers.</li>
      <li><b>Balance sheet accounts</b> — typically don't need budget
          lines, unless you're tracking capital expenditure budgets
          (e.g. fixed asset purchases in class 2).</li>
    </ul>

    <p><b>Variance reporting:</b> Once budget lines are saved and the
    version is Active, variance reports will compare these budgeted
    amounts against actual posted balances for the same accounts and
    periods.</p>

    <p><b>Tip:</b> Start with the most significant accounts (top
    revenue lines, major expense categories) and add detail gradually.
    A budget covering 15–20 key accounts is more useful than a
    budget with every account at zero.</p>
    """,
)

_register(
    "dialog.budget_version_list",
    "Budget Versions",
    "View and manage budget versions for a project.",
    """
    <p>This list shows all budget versions attached to the selected
    project, with their status and fiscal year.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Version name</b> — the budget version identifier.</li>
      <li><b>Fiscal year</b> — the period covered.</li>
      <li><b>Status</b> — Draft (in preparation), Active (approved for
          reporting), or Archived (historical).</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>New</b> — create a new budget version (Original, Revised,
          etc.).</li>
      <li><b>Edit</b> — modify version details or change status.</li>
      <li><b>Budget Lines</b> — open the line-item editor to enter
          or adjust amounts.</li>
    </ul>

    <p><b>Tip:</b> Only one version should be Active at a time for
    each project. When you activate a new version (e.g. a mid-year
    revision), the previous Active version should be Archived to
    keep reporting consistent.</p>
    """,
)

_register(
    "dialog.budget_lines_list",
    "Budget Lines List",
    "View and manage budget line items for a version.",
    """
    <p>This list shows all budget lines defined for the selected budget
    version — one row per GL account per period.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Account</b> — the GL account being budgeted.</li>
      <li><b>Period</b> — the fiscal period (e.g. January 2026).</li>
      <li><b>Budgeted amount</b> — the target amount for this
          account in this period.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>New</b> — add a budget line for an account and period.</li>
      <li><b>Edit</b> — adjust budgeted amounts.</li>
      <li><b>Delete</b> — remove a budget line (only for Draft
          versions).</li>
    </ul>

    <p><b>Tip:</b> Use the filter or sort options to group lines by
    account or period for easier review. For a quick fill, enter annual
    amounts and distribute them evenly across periods.</p>
    """,
)

# ── Contracts &amp; Projects Dialogs ─────────────────────────────────────────

_register(
    "dialog.project_form",
    "Project",
    "Create or edit a project record — the container for jobs, budgets, and commitments.",
    """
    <p>A <b>Project</b> is the main container for a piece of work. Once created,
    you attach jobs (phases), budget versions, and commitments to it. Every cost
    transaction tagged with this project's code will flow into its cost reports.</p>

    <p><b>Identity</b></p>
    <ul>
      <li><b>Project code</b> — short unique identifier used when tagging
          transactions (e.g. PROJ-001, ERP-2026). Read-only after creation.</li>
      <li><b>Project name</b> — descriptive name shown in lists and reports.</li>
      <li><b>Project type</b> — External (client-facing), Internal, Capital,
          Administrative, or Other. Used for filtering and reporting.</li>
      <li><b>Status</b> — Active, On Hold, Completed, or Cancelled. Only
          Active projects accept new cost transactions.</li>
    </ul>

    <p><b>Linkage</b></p>
    <ul>
      <li><b>Contract</b> — optional link to a client contract. Links the
          project to billing terms and contract value.</li>
      <li><b>Customer</b> — the client commissioning this project. Can be
          set directly if there is no formal contract.</li>
      <li><b>Project manager</b> — the internal user responsible.</li>
    </ul>

    <p><b>Budget control</b></p>
    <ul>
      <li><b>Budget control mode</b> — what happens when actual costs exceed
          budget: <em>Hard Stop</em> blocks the transaction,
          <em>Warn</em> flags it but allows posting,
          <em>None</em> allows without any check.</li>
    </ul>

    <p><b>Dates &amp; currency</b></p>
    <ul>
      <li><b>Start / Planned end date</b> — planned timeline for the project.</li>
      <li><b>Currency</b> — the currency in which project costs are tracked.
          Defaults to the company base currency.</li>
    </ul>

    <p><b>Notes</b> — free-text field for internal context, scope summary,
    or any other relevant information about the project.</p>

    <p><b>Tip:</b> Set the budget control mode before attaching a budget
    version. Hard Stop is the safest default for client projects where
    cost overruns have direct commercial consequences.</p>
    """,
)

_register(
    "dialog.project_job",
    "Project Job",
    "Create or edit a job within a project.",
    """
    <p>A <b>Job</b> breaks a project into trackable work units or phases.
    Each job can carry its own budget lines and commitments, and every
    cost transaction tagged with a job appears separately in variance
    analysis — so you can see exactly which phase is on budget and
    which is not.</p>

    <p><b>Identity</b></p>
    <ul>
      <li><b>Job code</b> — unique identifier within the project
          (e.g. <em>PHASE-1</em>, <em>FOUNDATION</em>,
          <em>FITOUT</em>). Read-only after creation.</li>
      <li><b>Job name</b> — descriptive label shown in lists and
          reports (e.g. <em>Site preparation and foundation work</em>).</li>
    </ul>

    <p><b>Hierarchy &amp; ordering</b></p>
    <ul>
      <li><b>Parent job</b> — optional. Nest jobs under a parent to
          create a work-breakdown tree. A parent must belong to the
          same project, and circular references are prevented
          automatically.</li>
      <li><b>Sequence</b> — controls the display order within the
          job list. Lower numbers appear first.</li>
    </ul>

    <p><b>Dates</b></p>
    <ul>
      <li><b>Start date</b> — when work on this job is planned or
          actually began.</li>
      <li><b>Planned end date</b> — target completion date. Must be
          on or after the start date.</li>
    </ul>

    <p><b>Options</b></p>
    <ul>
      <li><b>Allow direct cost posting</b> — when checked (the
          default), cost transactions can be tagged directly to
          this job. Uncheck if this job is only a grouping parent
          and costs should be posted to its children instead.</li>
      <li><b>Notes</b> — free-text field for scope details, special
          instructions, or internal context.</li>
    </ul>

    <p><b>Status workflow</b></p>
    <ul>
      <li><b>Active</b> — the default for new jobs. Active jobs
          accept new cost allocations and can be edited freely.</li>
      <li><b>Inactive</b> — temporarily paused. No new costs are
          accepted. Can be reactivated at any time.</li>
      <li><b>Closed</b> — permanently archived. Closing is
          irreversible: the actual end date is stamped automatically
          and no further cost allocations are allowed. Historical
          data remains in reports.</li>
    </ul>

    <p><b>How costs flow to a job</b></p>
    <p>Budget lines and commitment lines can be attached at the
    job level (job × cost-code). Actual costs arrive from five
    sources — purchase bills, treasury payments, inventory issues,
    payroll allocations, and manual journals — each tagged with a
    job code. Variance reports then compare approved budget against
    actual spend per job.</p>

    <p><b>Example — construction project jobs:</b></p>
    <ul>
      <li><em>SITE-PREP</em> — Site Preparation (clearing, surveying)</li>
      <li><em>FOUNDATION</em> — Foundation Work</li>
      <li><em>STRUCTURE</em> — Structural Building</li>
      <li><em>FITOUT</em> — Interior Fit-out</li>
      <li><em>HANDOVER</em> — Commissioning &amp; Handover</li>
    </ul>

    <p><b>Tip:</b> Use parent jobs for broad phases and child jobs
    for specific deliverables. This lets variance reports drill from
    a single project total down to the exact work package that is
    over budget.</p>
    """,
)

_register(
    "dialog.project_job_list",
    "Project Jobs",
    "View and manage jobs for a project.",
    """
    <p>This list shows every job defined for the selected project.
    Jobs represent work phases or deliverable groups that let you
    track costs at a more granular level than the whole project.</p>

    <p><b>Columns</b></p>
    <ul>
      <li><b>Code</b> — the job identifier used when tagging costs.</li>
      <li><b>Name</b> — descriptive label for the job.</li>
      <li><b>Parent</b> — the parent job code, if nested in a
          hierarchy.</li>
      <li><b>Seq</b> — sequence number controlling display order.</li>
      <li><b>Status</b> — Active, Inactive, or Closed.</li>
      <li><b>Start</b> — planned or actual start date.</li>
      <li><b>Planned End</b> — target completion date.</li>
    </ul>

    <p><b>Actions</b></p>
    <ul>
      <li><b>New Job</b> — create a new job for this project.</li>
      <li><b>Edit</b> — modify job details. Available only while
          the job is Active.</li>
      <li><b>Deactivate</b> — pause an Active job so it stops
          accepting new costs. The job can be reactivated later.</li>
      <li><b>Reactivate</b> — resume an Inactive job back to
          Active status.</li>
      <li><b>Close Job</b> — permanently archive an Active or
          Inactive job. This is irreversible: the actual end date
          is stamped and no further costs can be posted. A
          confirmation prompt is shown before closing.</li>
    </ul>

    <p><b>Tip:</b> Use <em>Deactivate</em> when a phase is paused
    but may resume — it can be reactivated freely. Use
    <em>Close Job</em> only when the phase is genuinely finished,
    since closing cannot be undone. Closed jobs still appear in
    reports with their full historical costs.</p>
    """,
)

_register(
    "dialog.project_cost_code",
    "Cost Code",
    "Classify project expenditures into a named cost category for tracking and reporting.",
    """
    <p>A <b>Cost Code</b> is a named category used to classify project spending.
    Every cost recorded against a project — labour hours, materials purchased,
    subcontractor invoices, equipment hire — gets tagged with a cost code so
    you can see exactly where the money went, not just a single project total.</p>

    <p><b>Example:</b> A construction project might use codes like
    <em>LAB</em> (Labour), <em>MAT</em> (Materials), <em>SUB</em> (Subcontract),
    <em>EQP</em> (Equipment), and <em>OVH</em> (Overhead). Each supplier bill
    or journal line is tagged with one of these — so your cost report shows
    how much went on labour vs. materials vs. subcontractors, and compares
    each against its budget line.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Code</b> — short unique identifier used when tagging transactions
          (e.g. LAB, MAT, SUB). Read-only after creation.</li>
      <li><b>Name</b> — descriptive label shown in reports and dropdowns.</li>
      <li><b>Type</b> — broad category: Labour, Materials, Equipment,
          Subcontract, Overhead, or Other. Used for high-level grouping
          in reports.</li>
      <li><b>Default GL Account</b> — optional. When set, transactions tagged
          with this cost code will default to that general ledger account.</li>
      <li><b>Description</b> — optional notes on what belongs in this code.</li>
    </ul>

    <p><b>Tip:</b> Cost codes are company-wide — define them once and reuse
    across all projects. Keep the list concise; too many codes makes tagging
    inconsistent across the team.</p>
    """,
)

_register(
    "dialog.project_cost_code_list",
    "Cost Codes",
    "Classify project expenditures into named categories for tracking, budgeting, and variance analysis.",
    """
    <p><b>Cost codes</b> are the categories you use to classify every cost
    on a project. When a supplier bill, journal entry, or commitment is
    recorded against a project, it gets tagged with a cost code — so your
    reports can break spending down by type rather than showing just a
    single project total.</p>

    <p><b>Example — a building contractor:</b></p>
    <ul>
      <li><b>LAB</b> — Labour (site workers, foremen)</li>
      <li><b>MAT</b> — Materials (concrete, steel, timber)</li>
      <li><b>SUB</b> — Subcontract (plumbing, electrical)</li>
      <li><b>EQP</b> — Equipment hire</li>
      <li><b>OVH</b> — Overhead (site office, insurance)</li>
    </ul>
    <p>Every cost on every project flows into one of these codes. At month-end
    you can see: 40% on labour, 35% on materials, 15% on subcontractors — and
    compare each against its budget line to spot where the project is over
    or under.</p>

    <p><b>Cost codes are company-wide.</b> You define them once here and
    reuse them across all projects. Budget lines and commitment lines both
    use cost codes as their main classification dimension.</p>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>New</b> — define a new cost code.</li>
      <li><b>Edit</b> — update the name, type, or default GL account.</li>
    </ul>

    <p><b>Tip:</b> Aim for 5–10 codes that reflect how your business
    naturally thinks about project costs. More than 15 tends to be hard
    to apply consistently across the whole team.</p>
    """,
)

_register(
    "dialog.contract_form",
    "Contract",
    "Create or edit a client contract — the commercial agreement under which project work is authorised.",
    """
    <p>A <b>Contract</b> is the commercial agreement with your client. It records
    what you are delivering, for how much, and under what billing terms. Projects
    are linked to a contract to inherit its commercial context — so that cost
    reports can show how much of the contract value has been consumed and what
    margin remains.</p>

    <p><b>The structure:</b> Contract &rarr; Project &rarr; Jobs &rarr; Cost codes.
    The contract holds the commercial terms; the project holds the cost data;
    the jobs break the work into phases; the cost codes classify each expense.</p>

    <p><b>Identity</b></p>
    <ul>
      <li><b>Contract number</b> — unique reference for this contract
          (e.g. CTR-2026-001). Read-only after creation.</li>
      <li><b>Contract title</b> — descriptive name shown in lists and reports.</li>
      <li><b>Customer</b> — the client who commissioned the work.</li>
      <li><b>Contract type</b> — the commercial structure:
          <em>Fixed Price</em> (agreed lump sum regardless of cost),
          <em>Time &amp; Material</em> (billed by hours and materials used),
          <em>Cost Plus</em> (actual costs plus an agreed fee or margin),
          <em>Framework</em> (umbrella agreement with call-off orders),
          or <em>Other</em>.</li>
    </ul>

    <p><b>Commercial terms</b></p>
    <ul>
      <li><b>Base contract amount</b> — the original agreed contract value,
          before any change orders.</li>
      <li><b>Currency</b> — the currency the contract is denominated in.</li>
      <li><b>Billing basis</b> — how progress will be invoiced:
          <em>Milestone</em>, <em>Progress</em>, <em>Time &amp; Material</em>,
          <em>Fixed Schedule</em>, <em>Manual</em>, or none.</li>
      <li><b>Retention %</b> — percentage held back by the client until
          completion or defects liability period ends.</li>
      <li><b>Reference number</b> — client's own purchase order or
          reference number, if any.</li>
    </ul>

    <p><b>Dates</b></p>
    <ul>
      <li><b>Start date</b> — when work under the contract starts.</li>
      <li><b>Planned end date</b> — contracted completion date.</li>
    </ul>

    <p><b>Description</b> — free-text field for scope summary, special
    conditions, or any other relevant context.</p>

    <p><b>Tip:</b> Once a contract is Active, use <em>Change Orders</em> to
    record any client-approved adjustments to scope or value. Do not edit
    the base amount directly — change orders preserve the audit trail of
    how the contract value evolved.</p>
    """,
)

_register(
    "dialog.contract_change_order",
    "Change Order",
    "Create or edit a contract change order.",
    """
    <p>Change orders formally record modifications to a contract's scope
    or value after the original agreement. They preserve an audit trail
    of how the contract evolved over time.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Change order number</b> — auto-assigned sequential number
          within the contract (e.g. CO-001, CO-002).</li>
      <li><b>Description</b> — what changed and why
          (e.g. <em>Additional floor requested by client — extra
          structural and finishing work</em>).</li>
      <li><b>Amount</b> — the value adjustment. Use a positive amount
          for scope additions and a negative amount for scope
          reductions.</li>
      <li><b>Status</b> — the approval state:
        <ul>
          <li><em>Pending</em> — proposed but not yet approved.</li>
          <li><em>Approved</em> — accepted by the client. Updates
              the contract's total value.</li>
          <li><em>Rejected</em> — declined. No effect on contract
              value.</li>
        </ul>
      </li>
    </ul>

    <p><b>Example:</b> Client requests an extra office floor on a
    building project:
    <br/>↕ CO-003: Additional 4th floor — Amount: +18,500,000 XAF
    <br/>↕ Status: Approved
    <br/>The contract's total value increases by 18,500,000.</p>

    <p><b>Tip:</b> Always use change orders to adjust contract values
    rather than editing the original contract amount. This preserves
    the history and lets you report on: original value + approved
    changes = revised contract value.</p>
    """,
)

_register(
    "dialog.contract_change_order_list",
    "Change Orders",
    "View and manage change orders for a contract.",
    """
    <p>This list shows all change orders attached to the selected contract,
    with their amounts and approval status.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>CO number</b> — sequential change order reference.</li>
      <li><b>Description</b> — summary of the change.</li>
      <li><b>Amount</b> — value impact (positive or negative).</li>
      <li><b>Status</b> — Pending, Approved, or Rejected.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>New</b> — create a new change order.</li>
      <li><b>Edit</b> — modify a pending change order.</li>
      <li><b>Approve / Reject</b> — finalise a change order.</li>
    </ul>

    <p><b>Summary:</b> The list footer shows the total of approved
    change orders, giving you the net contract adjustment at a
    glance: Original Value + Approved Changes = Revised Contract
    Value.</p>

    <p><b>Tip:</b> Review pending change orders regularly. Large
    pending amounts represent potential scope and budget risk that
    should be resolved promptly.</p>
    """,
)

# ── Job Costing Dialogs ──────────────────────────────────────────────────

_register(
    "dialog.project_commitment",
    "Commitment",
    "Create or edit a project commitment.",
    """
    <p>Commitments represent planned expenditures — purchase orders,
    subcontractor agreements, or approved procurement requests —
    before actual costs are incurred. They let you track future
    obligations so your cost forecast includes both actual spend
    and committed but not-yet-invoiced amounts.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Commitment number</b> — unique reference (auto-generated
          or manual).</li>
      <li><b>Project / Job</b> — where the cost will be allocated.</li>
      <li><b>Supplier</b> — the vendor or subcontractor.</li>
      <li><b>Amount</b> — total committed value.</li>
      <li><b>Status</b> — lifecycle state:
        <ul>
          <li><em>Draft</em> — being prepared, not yet binding.</li>
          <li><em>Open</em> — active commitment. Included in
              project cost forecasts.</li>
          <li><em>Closed</em> — fully invoiced or completed.</li>
          <li><em>Cancelled</em> — voided, no longer applicable.</li>
        </ul>
      </li>
    </ul>

    <p><b>Example:</b> A subcontractor agreement for electrical work:
    <br/>↕ Project: PROJ-001 / Job: FITOUT
    <br/>↕ Supplier: Douala Electrical Services
    <br/>↕ Amount: 5,400,000 XAF
    <br/>↕ Status: Open
    <br/>This commitment appears in the project cost forecast as
    5,400,000 of committed but not-yet-actual cost.</p>

    <p><b>Cost forecast formula:</b>
    <br/>Total Forecast = Actual Costs + Open Commitments
    <br/>This gives you a more realistic view of where the project
    will land compared to looking at actuals alone.</p>

    <p><b>Tip:</b> Close commitments once all associated invoices
    have been received and posted. Open commitments with no recent
    activity may indicate stale procurement that should be reviewed
    or cancelled.</p>
    """,
)

_register(
    "dialog.project_commitment_list",
    "Commitments",
    "View and manage commitments for a project.",
    """
    <p>This list shows all commitments attached to the selected project,
    providing a view of planned but not-yet-actual expenditures.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Commitment number</b> — the reference identifier.</li>
      <li><b>Supplier</b> — who the commitment is with.</li>
      <li><b>Amount</b> — total committed value.</li>
      <li><b>Status</b> — Draft, Open, Closed, or Cancelled.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>New</b> — create a new commitment.</li>
      <li><b>Edit</b> — modify a draft or open commitment.</li>
      <li><b>Lines</b> — manage line items (material, labour,
          subcontract details) for a commitment.</li>
    </ul>

    <p><b>Summary:</b> The list footer shows the total of open
    commitments, which represents the project's outstanding future
    obligations.</p>

    <p><b>Tip:</b> Review open commitments monthly alongside actual
    costs. Large open commitments that haven't progressed may need
    supplier follow-up or cancellation.</p>
    """,
)

_register(
    "dialog.project_commitment_line",
    "Commitment Line",
    "Create or edit a commitment line item.",
    """
    <p>Commitment lines break a commitment into individual cost items,
    each classified by cost code. This lets you budget and track
    committed costs at a detailed level.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Cost code</b> — expense classification (e.g. <em>MAT</em>
          for Materials, <em>SUB</em> for Subcontract).</li>
      <li><b>Description</b> — line item detail (e.g. <em>Electrical
          wiring and fittings</em>, <em>Concrete supply 50m³</em>).</li>
      <li><b>Quantity</b> — the number of units.</li>
      <li><b>Unit price</b> — cost per unit.</li>
      <li><b>Amount</b> — total for this line (Quantity × Unit
          Price, or entered directly).</li>
    </ul>

    <p><b>Example:</b> A commitment to a concrete supplier:
    <br/>↕ Cost code: MAT (Materials)
    <br/>↕ Description: Ready-mix concrete Grade C30
    <br/>↕ Quantity: 50 m³ | Unit price: 85,000 XAF
    <br/>↕ Amount: 4,250,000 XAF</p>

    <p><b>Tip:</b> Break commitments into lines by cost code so that
    variance analysis can compare committed amounts against budget
    at the cost-code level — not just the whole commitment.</p>
    """,
)

_register(
    "dialog.project_commitment_lines_list",
    "Commitment Lines",
    "View and manage line items for a commitment.",
    """
    <p>This list shows all lines within the selected commitment,
    broken down by cost code and description.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Cost code</b> — the expense classification.</li>
      <li><b>Description</b> — line item detail.</li>
      <li><b>Quantity</b> — number of units.</li>
      <li><b>Unit price</b> — cost per unit.</li>
      <li><b>Amount</b> — line total.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>New</b> — add a line item to the commitment.</li>
      <li><b>Edit</b> — modify an existing line.</li>
      <li><b>Delete</b> — remove a line (only for Draft
          commitments).</li>
    </ul>

    <p><b>Summary:</b> The list footer shows the commitment total
    (sum of all line amounts). This should match the commitment
    header amount.</p>

    <p><b>Tip:</b> Keep line descriptions specific enough that
    someone reviewing the commitment months later can understand
    what was ordered without needing to check external documents.</p>
    """,
)

# ── Payroll Dialogs ───────────────────────────────────────────────────────

_register(
    "dialog.employee_form",
    "Employee",
    "Create or edit an employee record — identity, employment details, and statutory identifiers.",
    """
    <p>This dialog registers a new employee in the payroll system or updates
    an existing record. The form is organised into three cards.</p>

    <p><b>Card 1 — Employee Identity</b></p>
    <ul>
      <li><b>Employee Number</b> — a unique code you assign to each employee
          (e.g. <em>EMP001</em>, <em>SA-0042</em>). It appears on payslips,
          reports, and exports. Choose a consistent scheme and do not reuse
          numbers after an employee leaves.</li>
      <li><b>Display Name</b> — the name shown in lists and dropdowns
          (e.g. <em>Jean-Paul Mbeki</em>). This is the quick-reference
          name the system uses everywhere.</li>
      <li><b>First Name / Last Name</b> — the employee’s legal names.
          These appear on payslips and statutory declarations (CNPS
          forms, DGI filings). Make sure they match official ID
          documents exactly.</li>
    </ul>

    <p><b>Card 2 — Employment Details</b></p>
    <ul>
      <li><b>Hire Date</b> — the employee’s official start date. This
          determines the first pay period they can be included in.
          For a new hire starting 15 March, the March payroll run will
          prorate their salary from the 15th.</li>
      <li><b>Termination Date</b> — tick the checkbox and set a date if
          the employee has left. Terminated employees can still be
          included in final pay runs up to this date but are excluded
          from subsequent periods.</li>
      <li><b>Department</b> — the organisational unit (e.g. <em>Finance</em>,
          <em>Operations</em>). Departments are managed in
          Payroll Setup → Departments.</li>
      <li><b>Position</b> — the job title or role (e.g. <em>Accountant</em>,
          <em>Project Manager</em>). Positions are managed in
          Payroll Setup → Positions.</li>
      <li><b>Base Currency</b> — the currency for this employee’s salary
          calculations. Normally <b>XAF</b> for Cameroon-based staff.
          Only active currencies from Reference Data appear.</li>
      <li><b>Active</b> (edit mode only) — uncheck to exclude the
          employee from future payroll runs without deleting their record.</li>
    </ul>

    <p><b>Card 3 — Contact &amp; Tax</b></p>
    <ul>
      <li><b>Phone</b> — optional contact number.</li>
      <li><b>Email</b> — optional email address for payslip delivery.</li>
      <li><b>Tax Identifier</b> — the employee’s NIU (Numéro
          d’Identifiant Unique) or NIF, used on DGI statutory
          declarations. Fill this in to ensure correct income tax
          reporting.</li>
    </ul>

    <p><b>Example:</b> To register a new accountant named Marie Ngo Bassa,
    enter Employee Number <em>EMP012</em>, Display Name <em>Marie Ngo Bassa</em>,
    Hire Date <em>2025-01-15</em>, Department <em>Finance</em>,
    Position <em>Accountant</em>, Currency <em>XAF</em>. After saving,
    go to the employee’s Compensation Profiles tab to set up their
    salary.</p>

    <p><b>Tip:</b> Always complete the tax identifier — it is
    required for IRPP statutory filings to DGI.</p>
    """,
)

_register(
    "dialog.department",
    "Department",
    "Manage company departments — organisational units for grouping employees.",
    """
    <p>This management dialog lets you create, edit, and deactivate
    departments. Departments are used to group employees for payroll
    reporting and cost allocation.</p>

    <p><b>Fields (when creating or editing):</b></p>
    <ul>
      <li><b>Code</b> — a short unique identifier (e.g. <em>HR</em>,
          <em>FIN</em>, <em>OPS</em>). Maximum 20 characters. Codes
          appear in report filters and exports.</li>
      <li><b>Name</b> — the full department name (e.g. <em>Human
          Resources</em>, <em>Finance</em>). Maximum 100 characters.</li>
      <li><b>Active</b> (edit mode) — uncheck to retire a department.
          Inactive departments no longer appear in the employee form
          dropdown but historical records are preserved.</li>
    </ul>

    <p><b>Toolbar actions:</b></p>
    <ul>
      <li><em>New Department</em> — opens the form for a new record.</li>
      <li><em>Edit</em> — modify the selected department (or double-click).</li>
      <li><em>Toggle Active</em> — activate or deactivate the selected department.</li>
      <li><em>Show inactive</em> checkbox — includes inactive departments in the list.</li>
    </ul>

    <p><b>Tip:</b> Department codes are used in payroll cost allocation
    reports. Keep them short, consistent, and meaningful.</p>
    """,
)

_register(
    "dialog.position",
    "Position",
    "Manage job positions — roles and titles assigned to employees.",
    """
    <p>This management dialog lets you create, edit, and deactivate job
    positions. Positions describe <em>what role</em> an employee fills
    (e.g. Accountant, Project Manager, Driver).</p>

    <p><b>Fields (when creating or editing):</b></p>
    <ul>
      <li><b>Code</b> — a short unique identifier (e.g. <em>MGR</em>,
          <em>ACCT</em>, <em>DRV</em>). Maximum 20 characters.</li>
      <li><b>Name</b> — the full position title (e.g. <em>Senior
          Accountant</em>, <em>Operations Manager</em>). Maximum
          100 characters.</li>
      <li><b>Active</b> (edit mode) — uncheck to retire a position.
          Inactive positions no longer appear in employee dropdowns.</li>
    </ul>

    <p><b>Toolbar actions:</b></p>
    <ul>
      <li><em>New Position</em> — opens the form for a new record.</li>
      <li><em>Edit</em> — modify the selected position (or double-click).</li>
      <li><em>Toggle Active</em> — activate or deactivate the selection.</li>
      <li><em>Show inactive</em> checkbox — includes inactive positions in the list.</li>
    </ul>

    <p><b>Tip:</b> Positions are referenced on employee records and appear
    on payslips. Choose clear, professional titles.</p>
    """,
)

_register(
    "dialog.payroll_component_form",
    "Payroll Component",
    "Define one item that appears on every payslip \u2014 an earning, a deduction, a tax, or an employer contribution.",
    """
    <p>A <b>payroll component</b> is a single line item that contributes to
    an employee\u2019s pay calculation. Every figure on a payslip \u2014 base
    salary, housing allowance, income tax, CNPS deduction \u2014 comes from a
    component. You define each component once here, then assign the relevant
    ones to each employee\u2019s compensation profile.</p>

    <p><b>Component Definition</b></p>

    <p><b>Code</b> \u2014 a short, unique machine identifier for this component
    (e.g. <em>BASE_SALARY</em>, <em>TRANSPORT_ALLOW</em>, <em>CNPS_EMP</em>,
    <em>IRPP</em>). The code is used internally and in imports/exports.
    Choose something clear and consistent \u2014 it cannot be changed after
    the component is used in a payroll run.</p>

    <p><b>Name</b> \u2014 the human-readable label that appears on payslips and
    reports (e.g. <em>Base Salary</em>, <em>Transport Allowance</em>,
    <em>CNPS Employee Share</em>).</p>

    <p><b>Component Type</b> \u2014 what role this component plays in the
    pay calculation:</p>
    <ul>
      <li><b>Earning</b> \u2014 adds to the employee\u2019s gross pay. Examples:
          Base Salary, Housing Allowance, Transport Allowance, Overtime Pay,
          Performance Bonus. All earnings build up the gross pay total.</li>
      <li><b>Deduction</b> \u2014 reduces the employee\u2019s take-home (net) pay.
          This covers voluntary deductions the employee agrees to, such as
          a union fee, a salary advance recovery, or a personal loan
          repayment. The amount is withheld before the bank transfer.</li>
      <li><b>Tax</b> \u2014 a statutory deduction mandated by law and remitted
          to the government. Use this type for income tax (IRPP in
          Cameroon). Separating tax from generic deductions matters for
          statutory reporting.</li>
      <li><b>Employer Contribution</b> \u2014 a cost the company pays on top
          of the employee\u2019s gross, not deducted from the employee. Example:
          the employer\u2019s share of CNPS contributions. This increases the
          company\u2019s salary cost but does not reduce the employee\u2019s net pay.</li>
      <li><b>Informational</b> \u2014 a figure that appears on the payslip for
          reference only and does not affect any pay calculation. Example:
          showing the employee their taxable income base or a year-to-date
          figure without double-counting it in the totals.</li>
    </ul>

    <p><b>Calculation Method</b> \u2014 how the component\u2019s amount is
    determined each pay period:</p>
    <ul>
      <li><b>Fixed Amount</b> \u2014 the same flat value every period. Used for
          base salary, fixed allowances, and flat-rate deductions. The
          amount is set on the employee\u2019s compensation profile
          (e.g. Housing Allowance = 40 000 FCFA/month).</li>
      <li><b>Percentage</b> \u2014 calculated as a percentage of another
          component or total. Example: a bonus set at 10% of Base Salary,
          or a transport allowance at a fixed % of gross. You specify what
          the percentage is applied to on the rule or employee profile.</li>
      <li><b>Rule Based</b> \u2014 the amount is determined by a Rule Set \u2014
          a bracket table or formula you define separately under Rule Sets.
          Use this for income tax (IRPP), which uses progressive brackets,
          or CNPS contributions, which have a rate and a salary ceiling.
          When a statutory rate changes, you update the Rule Set and all
          employees benefit automatically on the next run.</li>
      <li><b>Manual Input</b> \u2014 the amount is entered manually each payroll
          run. Use this for variable items that are different every period:
          overtime hours paid, a one-off bonus, or a deduction that varies
          month to month.</li>
      <li><b>Hourly</b> \u2014 calculated as hours worked \u00d7 an hourly rate.
          Used for casual workers or part-time staff paid by the hour.
          Hours are entered as a variable input each payroll run.</li>
    </ul>

    <p><b>Taxable</b> \u2014 tick this if the component\u2019s amount should be
    included in the income tax calculation base (taxable gross). For example,
    Base Salary is taxable; a reimbursement of actual expenses is typically
    not. Getting this right matters: ticking taxable on an allowance that
    should be exempt will over-tax the employee; leaving it unticked on a
    taxable component will under-tax them.</p>

    <p><b>Pensionable</b> \u2014 tick this if the component should be included
    in the base used to calculate CNPS contributions (pensionable gross).
    Base Salary is usually pensionable; certain allowances may or may not
    be depending on the applicable rules. CNPS also applies a salary ceiling
    \u2014 the Rule Set handles that cap automatically.</p>

    <p><b>Account Mapping (optional)</b></p>
    <p>These fields link the component to your General Ledger so that payroll
    posting creates the right accounting entries automatically.</p>
    <ul>
      <li><b>Expense Account</b> \u2014 the P&amp;L account that records the cost
          of this component for the company (e.g. <em>6611 \u2014 Basic Salaries</em>,
          <em>6414 \u2014 Transport Allowances</em>). Set this on earnings and
          employer contributions.</li>
      <li><b>Liability Account</b> \u2014 the balance sheet account that holds
          the obligation until it is paid out or remitted (e.g.
          <em>4221 \u2014 Salaries Payable</em>, <em>4331 \u2014 CNPS Payable</em>,
          <em>4441 \u2014 Tax Withheld \u2014 IRPP</em>). Set this on deductions and
          taxes \u2014 the withheld amount is a liability until you remit it.</li>
    </ul>
    <p>Account mapping is optional at the component level \u2014 you can also
    configure GL mapping centrally in Company Payroll Settings. However,
    setting it per component gives the most precise posting detail in your
    accounts.</p>
    """,
)

_register(
    "dialog.payroll_rule_set_form",
    "Payroll Rule Set",
    "Create or edit the header of a payroll calculation rule — the engine behind statutory deductions, contributions, and other computed amounts.",
    """
    <p><b>What is a Rule Set?</b></p>
    <p>Some payroll amounts are not simple fixed numbers. Income tax is
    worked out from a bracket table. CNPS pension has a rate and a salary
    ceiling. A <b>Rule Set</b> captures that calculation logic so the
    system can compute the correct amount automatically every pay run, for
    every employee, without anyone doing the maths by hand.</p>

    <p>When a statutory rate changes (e.g.&nbsp;government updates the
    income-tax brackets), you update the Rule Set once and every employee
    benefits on the next payroll run.</p>

    <p><b>Fields on this form:</b></p>
    <ul>
      <li><b>Rule Code</b> — a short, unique machine-friendly identifier.
          Convention: <code>DGI_WITHHOLDING_BAREME</code>,
          <code>CNPS_PENSION_EE</code>, etc.  Keep it uppercase and
          descriptive; it appears in reports and exports.</li>
      <li><b>Rule Name</b> — a descriptive label shown in dropdowns
          and payslip breakdowns (e.g.&nbsp;“IRPP Withholding —
          Progressive Brackets”).</li>
      <li><b>Rule Type</b> — tells the system <em>what kind</em> of
          deduction or contribution this is:
        <ul>
          <li><b>PIT (IRPP&nbsp;Withholding)</b> — personal income tax
              withheld from the employee’s pay.</li>
          <li><b>Pension — Employee</b> — the employee’s share of
              pension contributions (e.g.&nbsp;CNPS 4.2%).</li>
          <li><b>Pension — Employer</b> — the employer’s share
              (e.g.&nbsp;CNPS 4.2% employer).</li>
          <li><b>Accident Risk (CNPS)</b> — the employer-only work-injury
              levy calculated on the salary total.</li>
          <li><b>Overtime</b> — calculated overtime premiums.</li>
          <li><b>Levy</b> — other statutory taxes such as TDL.</li>
          <li><b>Other</b> — any custom calculation that doesn’t fit
              the above categories.</li>
        </ul>
      </li>
      <li><b>Calculation Basis</b> — the salary figure the rule
          operates against:
        <ul>
          <li><b>Gross Salary</b> — total earnings before deductions.</li>
          <li><b>Basic Salary</b> — the employee’s base pay only.</li>
          <li><b>Taxable Gross</b> — gross minus any exempt allowances
              (used for income-tax rules).</li>
          <li><b>Pensionable Gross</b> — the salary portion subject to
              pension ceilings.</li>
          <li><b>Fixed Amount</b> — the rule produces a flat amount
              regardless of salary.</li>
          <li><b>Other</b> — a custom base defined elsewhere.</li>
        </ul>
      </li>
      <li><b>Effective From</b> — the date this version of the rule
          starts applying. If statutory rates change in January, set
          this to 01/01 of the relevant year.</li>
      <li><b>Set expiry date / Effective To</b> — tick the checkbox
          to define an end date. Leave unticked if the rule is
          open-ended (most statutory rules are).</li>
      <li><b>Active</b> (edit mode only) — uncheck to retire a rule
          set without deleting it. Inactive rules are skipped during
          payroll calculation.</li>
    </ul>

    <p><b>After saving:</b> go to the Payroll Rules table and click
    <em>Edit Brackets</em> to define the actual bracket rows (rate
    bands) that power the calculation.</p>

    <p><b>Tip:</b> Keep one rule set per statutory deduction. If a rate
    changes mid-year, create a new version with the new effective date
    and expire the old one. This preserves historical accuracy for
    earlier pay periods.</p>
    """,
)

_register(
    "dialog.payroll_rule_brackets",
    "Payroll Rule Brackets",
    "Define the rate bands (tiers) that drive progressive or tiered payroll calculations — income tax, pension ceilings, and more.",
    """
    <p><b>What are brackets?</b></p>
    <p>Many payroll deductions do not use a single flat rate.
    Income tax is <em>progressive</em> — the first portion of income
    is taxed at a low rate, the next portion at a higher rate, and so on.
    Pension contributions may apply a rate but cap the salary at a ceiling.
    <b>Brackets</b> encode these tiers so the system calculates the
    correct amount automatically.</p>

    <p><b>How to read the table:</b></p>
    <p>Each row is one tier of the calculation, processed in order of
    Line #.  The system walks through the employee’s salary from the
    bottom bracket upward, applying each tier’s logic to the portion of
    salary that falls within that band.</p>

    <p><b>Column reference:</b></p>
    <ul>
      <li><b>Line #</b> — the order in which the bracket is evaluated.
          Start at 1. Lower line numbers are processed first.</li>
      <li><b>Lower Bound</b> — the salary amount where this band begins
          (inclusive). Leave blank or 0 for the first bracket.</li>
      <li><b>Upper Bound</b> — the salary amount where this band ends.
          Leave blank for the highest (uncapped) bracket.</li>
      <li><b>Rate %</b> — the percentage applied to the portion of
          salary within this band. For example, 10 means 10%.</li>
      <li><b>Fixed Amount</b> — if set, adds a flat amount instead of
          (or in addition to) the rate for this tier. Useful for brackets
          that define a lump sum per band rather than a percentage.</li>
      <li><b>Deduction Amount</b> — an amount subtracted from the
          calculated result for this tier. Some tax schedules publish
          a “deduction” per bracket to simplify the progressive
          calculation into a single-rate-plus-deduction formula.</li>
      <li><b>Cap Amount</b> — an upper limit on the result for this
          bracket. If the calculated contribution exceeds the cap, the
          cap is used instead. Common for pension ceilings.</li>
    </ul>

    <p><b>Example — Cameroon IRPP (income tax):</b></p>
    <table>
      <tr><th>Line</th><th>Lower</th><th>Upper</th><th>Rate</th></tr>
      <tr><td>1</td><td>0</td><td>2 000 000</td><td>10%</td></tr>
      <tr><td>2</td><td>2 000 000</td><td>3 000 000</td><td>15%</td></tr>
      <tr><td>3</td><td>3 000 000</td><td>5 000 000</td><td>25%</td></tr>
      <tr><td>4</td><td>5 000 000</td><td></td><td>35%</td></tr>
    </table>
    <p>For a taxable income of 3 500 000 FCFA the system would
    calculate: (2M × 10%) + (1M × 15%) + (500K × 25%) =
    200K + 150K + 125K = <b>475 000 FCFA</b> tax.</p>

    <p><b>Example — CNPS pension (employee share):</b></p>
    <table>
      <tr><th>Line</th><th>Lower</th><th>Upper</th><th>Rate</th><th>Cap</th></tr>
      <tr><td>1</td><td>0</td><td></td><td>4.2%</td><td>29 484</td></tr>
    </table>
    <p>Only one bracket: apply 4.2% of the pensionable gross, but
    never exceed the monthly ceiling of 29 484 FCFA (based on the
    CNPS salary cap of 750 000).</p>

    <p><b>Adding / editing brackets:</b></p>
    <ul>
      <li>Click <em>Add Bracket</em> to create a new tier. The line
          number is auto-suggested.</li>
      <li>Double-click a row (or select it and click <em>Edit</em>) to
          modify an existing tier.</li>
      <li><em>Delete</em> removes the selected tier permanently.</li>
    </ul>

    <p><b>Tips:</b></p>
    <ul>
      <li>Make sure brackets do not overlap — the Upper Bound of one
          tier should equal the Lower Bound of the next.</li>
      <li>The last bracket usually has no upper bound (meaning
          “everything above”).</li>
      <li>If you only need a simple flat rate with a ceiling, one
          bracket row with a Rate and a Cap is enough.</li>
      <li>When statutory rates change, edit the brackets here. The new
          values apply from the next payroll run onward.</li>
    </ul>
    """,
)

_register(
    "dialog.compensation_profile",
    "Compensation Profile",
    "Define an employee’s basic salary and its effective period — the foundation of every pay calculation.",
    """
    <p>A <b>compensation profile</b> captures the employee’s agreed basic
    salary for a specific period. It is the starting point of every payroll
    calculation — the system reads the active profile to determine the
    base salary, then applies all assigned components (allowances,
    deductions, taxes) on top.</p>

    <p>An employee can have multiple profiles over time (e.g. a new profile
    each year when salary changes), but only <b>one profile may be active
    for any given pay period</b>. If profiles overlap, the validation
    dashboard will flag it.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Profile Name</b> — a descriptive label for this salary
          arrangement (e.g. <em>Standard 2025</em>, <em>Probation Rate</em>,
          <em>Post-Promotion Jul 2025</em>). It appears in the profile
          list so you can tell profiles apart at a glance.</li>
      <li><b>Basic Salary</b> — the gross base pay per period in whole
          numbers or decimals (e.g. <em>450000</em> for 450 000 XAF/month).
          This is the amount before any allowance, deduction, or tax.</li>
      <li><b>Currency</b> — 3-letter currency code, normally <b>XAF</b>.
          Must match the company’s payroll currency.</li>
      <li><b>Effective From</b> — the date this profile starts applying.
          The profile covers every pay period on or after this date.
          For a salary increase effective 1 July, set this to
          <em>2025-07-01</em>.</li>
      <li><b>Effective To</b> — the date this profile stops applying.
          Leave at the minimum (earliest possible date) to mean
          <b>open-ended</b> — the profile applies indefinitely until
          a newer one takes over. Set an explicit end date only when
          you know the arrangement expires (e.g. a fixed-term contract
          that ends on a specific date).</li>
      <li><b>Notes</b> — optional free-text (e.g. <em>Per contract
          amendment signed 15 Jun 2025</em>).</li>
      <li><b>Active</b> (edit mode only) — uncheck to retire a profile
          without deleting it.</li>
    </ul>

    <p><b>Example:</b> Jean-Paul Mbeki is hired at 350 000 XAF/month
    starting 1 January 2025. Create a profile named <em>Initial 2025</em>,
    Basic Salary <em>350000</em>, Currency <em>XAF</em>, Effective From
    <em>2025-01-01</em>, leave Effective To open-ended. If he gets a raise
    to 400 000 starting July, set the first profile’s Effective To to
    <em>2025-06-30</em> and create a new profile <em>Post-Raise Jul 2025</em>
    with Effective From <em>2025-07-01</em>.</p>

    <p><b>Tip:</b> After saving the profile, go to the employee’s
    <em>Component Assignments</em> tab to assign the payroll components
    (allowances, deductions, taxes) that apply to this employee.</p>
    """,
)

_register(
    "dialog.component_assignment",
    "Component Assignment",
    "Assign a payroll component to an employee and optionally override its default amount or rate.",
    """
    <p>This dialog links a payroll component (e.g. Transport Allowance,
    CNPS Employee, IRPP) to a specific employee. Once assigned, the
    component appears on every payslip calculated for this employee
    during the effective period.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Component</b> — select from the list of active payroll
          components (shown as <em>CODE — Name</em>). Only components
          defined in Payroll Setup → Components appear here.</li>
      <li><b>Override Amount</b> — if set, replaces the component’s
          default fixed amount for <em>this employee only</em>. Leave
          blank to use the component’s own default.
          <br/>Example: the TRANSPORT_ALLOW component has a default of
          30 000 XAF, but this employee receives 40 000 — enter
          <em>40000</em> here.</li>
      <li><b>Override Rate</b> — if set, replaces the component’s
          default rate for <em>this employee only</em>. Enter as a
          decimal (e.g. <em>0.042</em> for 4.2%). Leave blank to use
          the component’s standard rate.
          <br/>Example: a senior employee negotiated a personal pension
          contribution of 5% instead of the standard 4.2% — enter
          <em>0.05</em>.</li>
      <li><b>Effective From</b> — the date this assignment starts.
          The assignment applies to every pay period on or after this
          date.</li>
      <li><b>Effective To</b> — leave at the minimum date for
          <b>open-ended</b> (applies indefinitely). Set a specific end
          date for temporary assignments (e.g. a project bonus that runs
          only from January to March).</li>
      <li><b>Active</b> (edit mode only) — uncheck to stop this
          assignment without deleting the record.</li>
    </ul>

    <p><b>When to use overrides vs. not:</b></p>
    <ul>
      <li>For components where every employee gets the same amount or
          rate (e.g. CNPS at 4.2%), leave both override fields blank —
          the component’s default applies.</li>
      <li>For components where amounts vary per employee (e.g. housing
          allowance differs by grade), set the Override Amount on each
          employee’s assignment.</li>
    </ul>

    <p><b>Tip:</b> Assign at minimum the statutory components
    (BASE_SALARY, CNPS employee/employer, IRPP) to every employee.
    The validation dashboard will warn you if mandatory assignments
    are missing.</p>
    """,
)

_register(
    "dialog.company_payroll_settings",
    "Company Payroll Settings",
    "Configure company-wide payroll defaults and Cameroon statutory parameters.",
    """
    <p>This dialog sets company-level payroll configuration. These settings
    are the foundation for every payroll run: they determine how employees
    are paid, which statutory rules apply, and how payroll documents are
    numbered. Get them right before running payroll for the first time.</p>

    <p><b>Core Settings</b></p>

    <p><b>Default Pay Frequency</b><br/>
    Controls how often employees are paid. This becomes the default for
    new employees; individual employee contracts can override it.</p>
    <ul>
      <li><b>Monthly</b> — one pay run per calendar month. Most common
          for salaried staff in Cameroon.</li>
      <li><b>Bi-Monthly</b> — twice per calendar month (e.g. 15th and
          last day). Common for mid-month advances.</li>
      <li><b>Bi-Weekly</b> — every two weeks (26 runs/year). Common for
          certain hourly or project-based workforces.</li>
      <li><b>Weekly</b> — every week (52 runs/year). Typically for daily
          wage workers.</li>
      <li><b>Daily</b> — used for casual or piece-rate workers paid
          per working day.</li>
    </ul>

    <p><b>Default Payroll Currency</b><br/>
    The currency used for all payroll calculations, payslips, and GL
    postings. In Cameroon this is normally <b>XAF (CFA Franc)</b>.
    Only currencies marked <i>Active</i> in Reference Data appear here.
    If the expected currency is missing, activate it under
    Reference Data &rarr; Currencies first.</p>

    <hr/>
    <p><b>Cameroon Statutory Settings</b></p>

    <p>These fields control how Cameroon-specific statutory deductions and
    contributions are calculated for every employee in this company.</p>

    <p><b>Statutory Pack Version</b><br/>
    An optional free-text identifier that records which version of the
    government statutory tables is active (e.g. <i>CMR_2024_V1</i>).
    This is informational only — it does not change calculations, but it
    helps you document when tables were last updated and compare against
    official DGI/CNPS publications. Update it whenever you apply a new
    statutory pack.</p>

    <p><b>CNPS Regime</b><br/>
    Determines which CNPS (Caisse Nationale de Prévoyance Sociale)
    contribution schedule applies to this company’s employees.</p>
    <ul>
      <li><b>General Regime</b> — applies to the vast majority of
          private-sector employers. Employee contribution: 2.8% of gross
          salary (capped). Employer contribution: 7.7% of gross salary
          (capped) plus the accident risk class rate.</li>
      <li><b>Agricultural Regime</b> — applies to agro-pastoral and
          agricultural employers. The contribution ceiling and some rates
          differ from the general regime. Select only if your CNPS
          registration certificate specifies this regime.</li>
    </ul>
    <p>If unsure, check your CNPS employer registration certificate.
    Using the wrong regime leads to incorrect statutory declarations.</p>

    <p><b>Accident Risk Class</b><br/>
    The industrial accident and occupational disease contribution rate
    assigned to your company by CNPS based on the nature of your
    business activity. This is an <i>employer-only</i> contribution
    added on top of the standard CNPS employer share.</p>
    <ul>
      <li><b>Class 1 — 1.75%</b>: Administrative, commercial, financial
          services. Low physical risk.</li>
      <li><b>Class 2 — 2.50%</b>: Light industry, logistics, transport
          offices. Moderate risk.</li>
      <li><b>Class 3 — 5.00%</b>: Construction, manufacturing, mining
          support. High physical risk.</li>
      <li><b>Class 4 — 7.00%</b>: Heavy industry, quarrying, hazardous
          materials. Highest risk.</li>
    </ul>
    <p>Your class appears on your CNPS registration or annual assessment
    letter. If CNPS reassigns your class, update this immediately—every
    payroll run uses this rate for the employer CNPS line.</p>

    <p><b>Overtime Policy Mode</b><br/>
    Controls how overtime pay rates are determined when payroll components
    include overtime lines.</p>
    <ul>
      <li><b>CNPS Barème</b> — uses the official CNPS overtime rate
          scale, which specifies multipliers by hours worked beyond normal
          thresholds (e.g. first 8 extra hours at 120%, next 8 at 150%,
          Sundays and holidays at 200%). This is the default required by
          the Cameroon Labour Code.</li>
      <li><b>Company Policy</b> — uses rates defined directly in your
          payroll component rules. Choose this only if you have a
          negotiated collective agreement or internal policy that differs
          from the CNPS official scale, and ensure it is at least as
          favourable as the Labour Code minimum.</li>
    </ul>

    <p><b>Benefits in Kind Mode</b><br/>
    Determines how non-cash benefits provided to employees (company
    housing, vehicle, meals, fuel, etc.) are valued for income tax (IR)
    and CNPS contribution purposes.</p>
    <ul>
      <li><b>DGI Table</b> — uses the official Direction Générale des
          Impôts valuation table, which assigns fixed monthly XAF values
          or percentage-of-salary values to each benefit category.
          Required by default unless DGI has granted a specific exemption
          or your company has an approved alternative.</li>
      <li><b>Company Policy</b> — uses amounts or rates you define in
          your payroll component rules. Use this only when you have DGI
          approval for a different valuation method, or for benefits not
          covered by the standard DGI table.</li>
    </ul>

    <hr/>
    <p><b>Payroll Number Format</b></p>

    <p><b>Prefix</b><br/>
    A short text code prepended to every payroll run number.
    Examples: <i>PAY</i> produces <i>PAY-00001</i>, <i>SAL</i> produces
    <i>SAL-00001</i>. Leave blank for purely numeric run numbers.
    Maximum 20 characters. Choose a prefix that distinguishes payroll
    documents from other document sequences (invoices, journal entries)
    in your filing system.</p>

    <p><b>Number Padding Width</b><br/>
    The minimum number of digits in the numeric part of the run number.
    A width of 5 means run 1 appears as <i>00001</i>, run 42 as
    <i>00042</i>. This ensures payroll run numbers sort correctly
    alphabetically in reports and filing systems. The value applies
    after the prefix. Default of 5 is sufficient for up to 99,999 runs.</p>

    <hr/>
    <p><b>Important notes</b></p>
    <ul>
      <li>These settings apply to all future payroll runs. Posted runs
          already closed are not retroactively affected.</li>
      <li>Before your first payroll run, verify CNPS regime and accident
          risk class against your official CNPS registration documents.</li>
      <li>Update statutory settings at the start of each fiscal year if
          DGI or CNPS tables change. Keep a record of when you made each
          change and which pack version was applied.</li>
      <li>Changes to pay frequency or currency do not automatically
          update existing employee contracts — review employee records
          after making significant changes here.</li>
    </ul>
    """,
)

_register(
    "dialog.apply_statutory_pack",
    "Apply Statutory Pack",
    "Apply a pre-built statutory rule pack to seed payroll components and rules in one step.",
    """
    <p>A <b>statutory pack</b> is a ready-made bundle of payroll components
    and rule sets for a specific jurisdiction and fiscal year. Instead of
    manually creating each CNPS contribution, IRPP tax bracket, and TDL
    levy rule one by one, you apply the pack and the system creates
    everything in a single operation.</p>

    <p><b>What’s in the pack</b></p>
    <p>The Cameroon Standard pack typically includes:</p>
    <ul>
      <li>Statutory payroll components — CNPS Employee, CNPS Employer,
          IRPP, TDL, CRTV, CFC, and other mandatory deductions.</li>
      <li>Rule sets with bracket tables — IRPP progressive tax brackets,
          CNPS contribution rates and ceilings, TDL rates.</li>
    </ul>

    <p><b>How to use:</b></p>
    <ol>
      <li>Select a pack from the <b>Pack to apply</b> dropdown
          (e.g. <em>Cameroon Standard (CMR_2024_V1)</em>).</li>
      <li>Read the description in the <b>About This Pack</b> card
          to confirm it matches your fiscal year.</li>
      <li>Click <b>Apply Pack</b>.</li>
      <li>Review the result summary — it shows how many components
          and rules were created.</li>
    </ol>

    <p><b>Safe to re-apply:</b> The pack is <em>idempotent</em> — it
    only creates records that do not already exist. If you already have
    a CNPS_EMPLOYEE component, the pack skips it. You will never lose
    or overwrite data you have already customised. This means you can
    safely re-apply after a pack update to pick up any newly added
    components or rules.</p>

    <p><b>Currently applied:</b> If a pack version has been applied
    before, the dialog shows which version is recorded in your
    Company Payroll Settings.</p>

    <p><b>Tip:</b> Apply the statutory pack as the first step when
    setting up a new company’s payroll. Then review the seeded
    components and rule brackets to confirm they match the latest
    DGI/CNPS publications for your fiscal year.</p>
    """,
)

_register(
    "dialog.payroll_run",
    "Payroll Run",
    "Create a new payroll run for a pay period — the starting point for every payroll cycle.",
    """
    <p>A <b>payroll run</b> represents one pay cycle for a specific month.
    Creating a run reserves the period and prepares the system to calculate
    salaries for all active employees.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Period Year / Period Month</b> — the calendar month this
          payroll covers (e.g. March 2025). Each month can have only one
          active payroll run.</li>
      <li><b>Run Label</b> — an optional descriptive name
          (e.g. <em>March 2025 Regular</em>). Leave blank and the system
          generates one automatically from the period.</li>
      <li><b>Currency</b> — 3-letter code, normally <b>XAF</b>. Must
          match the company’s default payroll currency.</li>
      <li><b>Run Date</b> — the date the calculation is considered to
          apply (usually the last working day of the month). This date
          determines which compensation profiles and component
          assignments are active.</li>
      <li><b>Payment Date</b> — the target date for salary transfers
          to employee bank accounts. Leave as <em>Not set</em> if you
          don’t know it yet — you can record actual payment dates later
          in Payroll Accounting.</li>
      <li><b>Notes</b> — optional free-text for internal reference.</li>
    </ul>

    <p><b>What happens after creation:</b></p>
    <ol>
      <li>The run appears in the Payroll Runs table with status <b>Draft</b>.</li>
      <li>Enter any <b>variable inputs</b> (overtime, bonuses, deductions)
          via the Variable Input Batch dialog.</li>
      <li>Click <b>Calculate</b> to process all active employees.</li>
      <li>Review individual payslips and the period summary.</li>
      <li><b>Approve</b> the run when satisfied.</li>
      <li><b>Post to GL</b> via Payroll Accounting to create journal entries.</li>
    </ol>

    <p><b>Tip:</b> If you see a “document sequence” error, it means no
    payroll document sequence has been configured yet. Go to
    Accounting Setup → Document Sequences and create one for payroll.</p>
    """,
)

_register(
    "dialog.payroll_input_batch",
    "Variable Input Batch",
    "Enter variable payroll data that changes each period — overtime hours, bonuses, ad-hoc deductions.",
    """
    <p>Most payroll components are fixed (base salary, standard allowances)
    or rule-based (IRPP, CNPS). But some amounts change every month:
    overtime hours, a one-off performance bonus, a salary advance
    recovery, or extra shift pay. These are <b>variable inputs</b>.</p>

    <p><b>Creating a batch:</b></p>
    <p>The first dialog asks for:</p>
    <ul>
      <li><b>Period Year / Period Month</b> — the month these inputs
          apply to. Must match an existing payroll run period.</li>
      <li><b>Description</b> — optional label (e.g. <em>March overtime</em>,
          <em>Q1 bonus batch</em>).</li>
    </ul>
    <p>After creating, the system opens the <b>batch management dialog</b>
    where you add individual lines.</p>

    <p><b>Managing batch lines:</b></p>
    <p>Each line represents one variable amount for one employee:</p>
    <ul>
      <li><b>Employee</b> — the employee this input is for.</li>
      <li><b>Component</b> — the payroll component (must be a
          Manual Input type component).</li>
      <li><b>Type</b> — earning, deduction, etc.</li>
      <li><b>Amount</b> — the value for this period.</li>
      <li><b>Qty</b> — quantity (e.g. overtime hours).</li>
      <li><b>Notes</b> — optional justification.</li>
    </ul>

    <p><b>Batch lifecycle:</b></p>
    <ul>
      <li><b>Draft</b> — lines can be added, edited, or deleted.</li>
      <li><b>Approved</b> — the batch is locked and its values will be
          included in the next payroll calculation. Click
          <em>Approve Batch</em> when all inputs are entered.</li>
      <li><b>Voided</b> — the batch is cancelled and its values are
          excluded from calculation. Use this if the batch was created
          in error.</li>
    </ul>

    <p><b>Example:</b> Three employees worked overtime in March.
    Create a batch for March 2025, then add three lines — one per
    employee — selecting the OVERTIME component and entering the hours
    in the Qty field. Approve the batch, then run the payroll
    calculation to include these overtime amounts.</p>

    <p><b>Tip:</b> Approve all variable input batches <em>before</em>
    running the payroll calculation. Unapproved batches are ignored.</p>
    """,
)

_register(
    "dialog.payroll_summary",
    "Payroll Period Summary",
    "Review aggregated totals, payment status, and statutory exposure for a payroll period.",
    """
    <p>This dialog gives you a consolidated view of a payroll period —
    everything from gross earnings to outstanding statutory obligations.
    Use it as your final check before approving or as a period-end
    reconciliation tool.</p>

    <p><b>Period selector:</b> Choose the year and month at the top,
    then click <em>Load</em> to refresh the summary.</p>

    <p><b>Run Summary</b> (shown if a payroll run exists for the period):</p>
    <ul>
      <li><b>Run Reference / Label / Status</b> — identifies the run
          and its current workflow state (Draft, Calculated, Approved,
          Posted, Voided).</li>
      <li><b>Gross Earnings</b> — total of all earning components across
          all included employees.</li>
      <li><b>Total Net Payable</b> — gross minus all deductions and
          taxes. This is what employees will actually receive.</li>
      <li><b>Total Taxes</b> — sum of IRPP and other tax components
          withheld from employees.</li>
      <li><b>Employer Cost</b> — total cost to the company: gross
          earnings plus employer-only contributions (CNPS employer,
          accident risk).</li>
      <li><b>Included / Error</b> — how many employees were successfully
          calculated vs. how many had errors. Investigate errors before
          approving.</li>
      <li><b>Journal Entry</b> (posted only) — the GL journal entry ID
          created when this run was posted.</li>
    </ul>

    <p><b>Employee Net Pay Exposure:</b></p>
    <ul>
      <li><b>Total Paid / Outstanding</b> — how much salary has been
          disbursed so far vs. how much is still owed.</li>
      <li><b>Paid / Partial / Unpaid</b> — count of employees in each
          payment status.</li>
    </ul>

    <p><b>Statutory Remittance Exposure:</b></p>
    <p>For each authority (DGI, CNPS), shows the total due, total
    remitted, and outstanding balance. A non-zero outstanding balance
    means you still owe money to that authority for this period.</p>

    <p><b>Tip:</b> Review this summary after posting and before making
    salary transfers. Compare with the previous month’s figures to
    spot anomalies (large swings in gross, unexpected employee errors,
    or missing remittances).</p>
    """,
)

_register(
    "dialog.payslip_preview",
    "Payslip Preview",
    "View the detailed payslip for a single employee in a payroll run.",
    """
    <p>The payslip preview shows the full breakdown of one employee’s
    pay for a given period, exactly as it would appear on their
    printed or exported payslip.</p>

    <p><b>Header:</b> Employee name, employee number, payroll period,
    and the run reference.</p>

    <p><b>Sections on the payslip:</b></p>
    <ul>
      <li><b>Earnings</b> — every component classified as an earning:
          base salary, housing allowance, transport allowance, overtime,
          bonuses. Each line shows the component name, basis, rate,
          and calculated amount.</li>
      <li><b>Deductions</b> — employee-side deductions: CNPS employee
          contribution, salary advance recovery, loan repayments, etc.</li>
      <li><b>Taxes</b> — tax components: IRPP, TDL (Taxe de
          Développement Local), CRTV, CFC (Crédit Foncier du Cameroun).</li>
      <li><b>Net Payable</b> — the total the employee will receive
          after all deductions and taxes.</li>
    </ul>

    <p><b>Information line:</b> Below the summary, key calculation
    bases are displayed for reference:</p>
    <ul>
      <li><b>Employer Cost</b> — what the company actually spends
          including employer-only contributions.</li>
      <li><b>CNPS Base</b> — the earnings base subject to social
          insurance contributions (capped at the ceiling).</li>
      <li><b>Taxable Base</b> — the amount subject to income tax
          after abatements.</li>
      <li><b>TDL Base</b> — the base for the local development tax.</li>
    </ul>

    <p><b>Employer Contributions:</b> A separate section shows
    contributions paid by the employer on the employee’s behalf
    (e.g. CNPS Employer share, Accident Risk).</p>

    <p><b>Example:</b> Marie Ngo Bassa — March 2025. Earnings:
    Base Salary 350,000 XAF + Transport 25,000 = Gross 375,000.
    Deductions: CNPS Employee 9,712 (2.8% of capped base).
    Taxes: IRPP 18,200, TDL 2,730. Net Payable: 344,358 XAF.
    Employer Cost includes CNPS Employer share of 29,135.</p>

    <p><b>Tip:</b> Use the payslip preview to verify individual
    calculations before approving the run. Compare the Net Payable
    against expected amounts. If something looks wrong, check the
    employee’s compensation profile and component assignments.</p>

    <p><b>Exporting the payslip:</b> Click the <b>Export…</b> button
    at the bottom of this dialog to save the payslip to a file.
    A format picker will appear with three options:</p>
    <ul>
      <li><b>PDF</b> — a ready-to-send document, A4 portrait.
          Use this when you need to e-mail the payslip or archive
          it alongside other company documents.</li>
      <li><b>Word (.docx)</b> — an editable document that mirrors
          the payslip layout. Useful when you need to adjust
          branding or add a cover note before sending.</li>
      <li><b>Excel (.xlsx)</b> — a structured spreadsheet version
          of the payslip. Useful for importing figures into other
          tools or for lightweight auditing.</li>
    </ul>
    <p>After selecting a format, choose where to save the file.
    When the export succeeds you will be offered the option to
    open the file immediately.</p>

    <p><b>Batch export:</b> To export payslips for all employees
    in a run at once, go to the <b>Print</b> tab in the Payroll
    Operations workspace, select the run, then click
    <b>Export Payslips…</b>. For PDF and Word the output is one
    file per employee in a folder you choose. For Excel all
    employees are written as separate sheets in a single workbook.</p>
    """,
)

_register(
    "dialog.payroll_run_employee_detail",
    "Employee Run Detail",
    "View the full calculation breakdown for one employee in a payroll run.",
    """
    <p>This dialog shows how every figure was computed for a single
    employee in the selected payroll run. It is the most detailed
    view available for troubleshooting calculations.</p>

    <p><b>Header:</b> Employee name, run reference, and the
    calculation status (Calculated, Error, Excluded).</p>

    <p><b>Six base figures:</b></p>
    <ul>
      <li><b>Gross Earnings</b> — total of all earning-type components.</li>
      <li><b>CNPS Base</b> — the portion of earnings subject to CNPS
          contributions. Subject to a monthly ceiling (e.g. 750,000 XAF
          for the general regime).</li>
      <li><b>TDL Base</b> — the base for Taxe de Développement Local
          (normally tied to IRPP calculation).</li>
      <li><b>Taxable Base</b> — gross minus statutory abatements,
          used as the input to the IRPP tax brackets.</li>
      <li><b>Employer Cost</b> — total cost to the company: gross
          earnings plus employer-only contributions.</li>
      <li><b>Net Payable</b> — what the employee actually receives.</li>
    </ul>

    <p><b>Lines table:</b> Every payroll component that contributed to
    this employee’s calculation, showing:</p>
    <ul>
      <li><b>Component</b> — e.g. BASE_SALARY, CNPS_EMPLOYEE, IRPP.</li>
      <li><b>Type</b> — Earning, Deduction, Tax, or Employer Contribution.</li>
      <li><b>Basis</b> — the base amount the calculation used.</li>
      <li><b>Rate</b> — the rate or percentage applied.</li>
      <li><b>Amount</b> — the final calculated amount for this component.</li>
    </ul>

    <p><b>Using this to troubleshoot:</b></p>
    <p>If an employee’s net pay looks wrong, open this detail view and
    trace the calculation:</p>
    <ol>
      <li>Check <b>Gross Earnings</b> — is the base salary correct?
          Are all expected allowances present?</li>
      <li>Check <b>Taxable Base</b> — are abatements (30% +
          500,000 charge forfaitaire) applied correctly?</li>
      <li>Check each <b>IRPP</b> and <b>CNPS</b> line — do
          rates and brackets match the current rule sets?</li>
    </ol>

    <p><b>Payslip Preview button:</b> Click it to see the formatted
    payslip version of these same figures.</p>
    """,
)

_register(
    "dialog.payroll_run_posting_detail",
    "Posting Detail",
    "View the GL posting status and journal entry reference for a payroll run.",
    """
    <p>This dialog shows the details of a payroll run’s posting to the
    General Ledger. Once a payroll run is posted, this is where you
    confirm what was created.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Run Reference / Label</b> — identifies the payroll run.</li>
      <li><b>Status</b> — colour-coded badge (e.g. <em>Posted</em> in
          green, <em>Voided</em> in red).</li>
      <li><b>Period</b> — the pay period (month and year).</li>
      <li><b>Posted Date</b> — the date the journal entry was created.</li>
      <li><b>Journal Entry</b> — the reference of the GL journal entry.
          Navigate to <b>Journals &amp; Posting</b> in the Accounting
          module to view the full double-entry detail.</li>
    </ul>

    <p><b>What the posting creates:</b></p>
    <p>A payroll GL posting generates a journal entry with debit and
    credit lines for:</p>
    <ul>
      <li><b>Salary Expense</b> accounts (debited for gross earnings
          and employer contributions).</li>
      <li><b>CNPS Payable</b> (credited for employee + employer
          CNPS due).</li>
      <li><b>IRPP Payable / Tax Payable</b> (credited for tax
          withheld).</li>
      <li><b>Net Salary Payable</b> (credited for the net amount
          owed to employees).</li>
    </ul>
    <p>The exact accounts used depend on the <b>Account Role Mappings</b>
    configured in Payroll Setup. If any mapping is missing, the posting
    will not proceed — this is by design to prevent incomplete
    accounting entries.</p>

    <p><b>Tip:</b> After posting, reconcile the journal entry totals
    against the Payroll Summary. Debits must equal credits.
    If they don’t, check for missing account role mappings.</p>
    """,
)

_register(
    "dialog.payroll_post_run",
    "Post Payroll Run to GL",
    "Validate and post a payroll run to the General Ledger — this creates the official journal entry.",
    """
    <p>Posting converts a calculated and approved payroll run into a
    proper double-entry journal entry in the General Ledger. This is
    the step that makes the payroll <b>official accounting truth</b>.
    Once posted, the run cannot be recalculated.</p>

    <p><b>Two-step process:</b></p>
    <ol>
      <li><b>Validation</b> — the system automatically runs validation
          checks when the dialog opens. Each check is listed with a
          pass/fail status. Common checks include:
          <ul>
            <li>All required <b>Account Role Mappings</b> are configured
                (salary expense, CNPS payable, IRPP payable, net salary
                payable, etc.).</li>
            <li>A valid <b>fiscal period</b> exists and is open for
                the run’s date.</li>
            <li>All payroll components have the required GL account
                mappings.</li>
            <li>No employees with error status in the run.</li>
          </ul></li>
      <li><b>Post to GL</b> — once all blocking errors are resolved,
          click the <em>Post to GL</em> button to create the journal
          entry.</li>
    </ol>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Posting Date</b> — defaults to the run date. This becomes
          the journal entry date.</li>
      <li><b>Narration</b> — the journal entry description. An
          auto-generated narration is used if left blank
          (e.g. <em>Payroll for March 2025 — PR-2025-0003</em>).</li>
    </ul>

    <p><b>Quick-fix buttons:</b> If validation finds issues, context-
    sensitive buttons appear to take you directly to:</p>
    <ul>
      <li><b>Open Account Role Mappings</b> — if GL account mappings
          are missing.</li>
      <li><b>Open Payroll Components</b> — if component configurations
          are incomplete.</li>
      <li><b>Open Fiscal Periods</b> — if no open period covers the
          posting date.</li>
    </ul>

    <p><b>Tip:</b> If you see blocking validation errors, fix the
    underlying configuration first, then click <em>Run Validation</em>
    to re-check. The <em>Post to GL</em> button only becomes active
    when there are no blocking errors.</p>
    """,
)

_register(
    "dialog.payroll_payment_record",
    "Record Salary Payment",
    "Record the actual salary disbursement to an employee after a payroll run is posted.",
    """
    <p>After a payroll run is posted, each employee is owed their
    <b>Net Payable</b> amount. This dialog records the actual payment —
    the bank transfer, cheque, or cash handover that settles the
    obligation.</p>

    <p><b>Header:</b> The employee’s <b>Net Payable</b> amount is shown
    at the top as a read-only reference so you know exactly how much
    is owed.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Payment Date</b> — when the payment was made or will be
          made (e.g. the bank transfer value date).</li>
      <li><b>Amount Paid</b> — pre-filled with the full Net Payable.
          Adjust downward for partial payments if needed (the system
          tracks the outstanding balance).</li>
      <li><b>Payment Method</b> — choose from:
          <em>Manual Bank Transfer</em>, <em>Cash</em>, <em>Cheque</em>,
          <em>Transfer Note</em>, or <em>Other</em>.</li>
      <li><b>Reference</b> — the bank transfer reference, cheque
          number, or other identifier. Important for reconciliation.</li>
      <li><b>Notes</b> — optional free-text (e.g. <em>Paid via
          BICEC bulk transfer batch #4521</em>).</li>
    </ul>

    <p><b>Example:</b> Marie Ngo Bassa — Net Payable 344,358 XAF.
    Payment Date: 28-Mar-2025, Amount Paid: 344,358, Method: Manual
    Bank Transfer, Reference: BICEC-TRF-20250328-042.</p>

    <p><b>Partial payments:</b> If you cannot pay the full amount at
    once, enter a smaller Amount Paid. The employee’s status will show
    as <em>Partial</em> in the Payroll Summary until the balance is
    cleared by a subsequent payment record.</p>

    <p><b>Tip:</b> Record payments promptly after bank transfers clear.
    This keeps the <em>Employee Net Pay Exposure</em> section of the
    Period Summary accurate and up to date.</p>
    """,
)

_register(
    "dialog.payroll_remittance_batch",
    "Statutory Remittance Batch",
    "Record a payment batch to a statutory authority (DGI, CNPS) for a payroll period.",
    """
    <p>Statutory remittances are the payments your company makes to
    government authorities for taxes and social insurance withheld
    from employees. This dialog creates a remittance batch — a
    record of one payment to one authority covering a date range.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Period Start / Period End</b> — the date range this
          remittance covers. The end date auto-adjusts to a month
          boundary. Typically one calendar month
          (e.g. 01-Mar-2025 to 31-Mar-2025).</li>
      <li><b>Authority</b> — select the statutory body:
          <ul>
            <li><b>DGI — Tax Authority</b> (for IRPP, TDL, CRTV,
                CFC remittances).</li>
            <li><b>CNPS — Social Insurance</b> (for CNPS employee
                and employer contributions).</li>
            <li><b>Other</b> (for any other statutory body).</li>
          </ul></li>
      <li><b>Amount Due</b> — the total amount being remitted to
          this authority.</li>
      <li><b>Notes</b> — optional reference (e.g. <em>DGI payment
          for March 2025 — receipt #78432</em>).</li>
    </ul>

    <p><b>Example:</b> CNPS remittance for March 2025. Period:
    01/03/2025 – 31/03/2025. Authority: CNPS — Social Insurance.
    Amount Due: 387,420 XAF (sum of all CNPS employee + employer
    contributions for the month).</p>

    <p><b>Adding detail lines:</b> After creating the batch, you can
    add individual <b>remittance lines</b> to break down the total
    by component or description (e.g. separate lines for CNPS
    Employee and CNPS Employer).</p>

    <p><b>Tip:</b> Cross-reference the Amount Due with the
    <em>Statutory Remittance Exposure</em> section of the Period
    Summary to ensure you are remitting the correct total.</p>
    """,
)

_register(
    "dialog.payroll_remittance_line",
    "Remittance Line",
    "Add or edit a detail line within a statutory remittance batch.",
    """
    <p>Each remittance line breaks down part of a remittance batch into
    a described amount. Use lines to itemise what the batch payment
    covers.</p>

    <p><b>Fields:</b></p>
    <ul>
      <li><b>Description</b> — what this line represents
          (e.g. <em>IRPP for January 2025</em>,
          <em>CNPS Employer contribution March</em>).</li>
      <li><b>Amount Due</b> — the monetary amount for this line.
          All line amounts should add up to the batch total.</li>
      <li><b>Notes</b> — optional reference or detail.</li>
    </ul>

    <p><b>Example:</b> A DGI remittance batch of 245,600 XAF might
    have three lines:</p>
    <ul>
      <li>IRPP withholding — 198,000 XAF</li>
      <li>TDL — 29,700 XAF</li>
      <li>CRTV + CFC — 17,900 XAF</li>
    </ul>

    <p><b>Tip:</b> Breaking a batch into lines makes it easier to
    reconcile with the payroll summary and with the authority’s
    receipt or declaration form.</p>
    """,
)

_register(
    "dialog.payroll_project_allocations",
    "Project Cost Allocations",
    "Distribute an employee’s payroll cost across projects and cost codes.",
    """
    <p>When your company runs project-based accounting, you may need to
    split an employee’s salary cost across multiple projects. This dialog
    lets you define the allocation percentages.</p>

    <p><b>Summary section:</b> Shows the employee, payroll period, and
    total cost being allocated.</p>

    <p><b>Allocation lines table:</b></p>
    <ul>
      <li><b>Project</b> — the project the cost is charged to.</li>
      <li><b>Contract</b> — optional contract within the project.</li>
      <li><b>Cost Code</b> — the specific cost category
          (e.g. <em>LABOUR</em>, <em>OVERHEAD</em>).</li>
      <li><b>Allocation %</b> — the percentage of the total payroll
          cost assigned to this line.</li>
    </ul>

    <p><b>Rule:</b> All allocation percentages <b>must total exactly
    100%</b>. The dialog validates this before saving. You cannot
    save an allocation that is under or over 100%.</p>

    <p><b>Example:</b> An engineer earns 500,000 XAF/month and works
    on two projects: Project Alpha (60%) and Project Beta (40%).
    Create two lines: Alpha/LABOUR/60% and Beta/LABOUR/40%.
    The system will charge 300,000 to Alpha and 200,000 to Beta in
    project cost reports.</p>

    <p><b>Tip:</b> If an employee works on only one project, you still
    need a single line at 100%. Employees without allocations use the
    company’s default cost centre.</p>
    """,
)

_register(
    "dialog.payroll_export",
    "Export Payroll Data",
    "Export payslips, batch payslip PDFs, or a payroll summary report from a run.",
    """
    <p>This dialog lets you generate files from a payroll run for
    distribution, archiving, or further processing.</p>

    <p><b>Three export modes:</b></p>
    <ul>
      <li><b>Single Payslip</b> — exports one employee’s payslip as
          a PDF file. Use this when an employee requests their pay
          stub.</li>
      <li><b>Batch Payslips</b> — generates a PDF payslip for every
          employee in the run. Useful for printing or emailing the
          full month’s payslips at once.</li>
      <li><b>Summary Report</b> — a consolidated payroll summary.
          Choose between:
          <ul>
            <li><b>CSV</b> — spreadsheet-compatible file for further
                analysis in Excel or LibreOffice Calc.</li>
            <li><b>PDF</b> — formatted report suitable for management
                review or archiving.</li>
          </ul></li>
    </ul>

    <p><b>Context info:</b> The dialog shows the run reference and
    period to confirm you are exporting the correct data.</p>

    <p><b>Warning banner:</b> If the system detects a potential issue
    (e.g. the run has not been approved yet, or output directories
    are not configured), a warning appears at the top of the dialog.
    Exports still proceed, but review the warning.</p>

    <p><b>Example workflow:</b></p>
    <ol>
      <li>Post the March 2025 payroll run.</li>
      <li>Open Export → select <em>Batch Payslips</em> → click
          <em>Export</em>. A PDF per employee is saved to the
          chosen folder.</li>
      <li>Open Export again → select <em>Summary Report</em> →
          choose <em>CSV</em> → click <em>Export</em>. Send the
          CSV to the CFO for review.</li>
    </ol>

    <p><b>Tip:</b> Always export from an <em>approved</em> or
    <em>posted</em> run to ensure the figures are final.</p>
    """,
)

_register(
    "dialog.validation_check_detail",
    "Validation Check Detail",
    "Understand a specific validation check result and how to fix it.",
    """
    <p>When you validate a payroll run for posting, each check produces
    a result. This dialog explains <b>one specific check</b> in full
    detail — what failed, why it matters, and exactly how to fix it.</p>

    <p><b>Parts of the dialog:</b></p>
    <ul>
      <li><b>Severity badge</b> — colour-coded indicator:
          <ul>
            <li><b>Error</b> (red) — blocks posting. Must be fixed.</li>
            <li><b>Warning</b> (amber) — does not block posting but
                should be reviewed.</li>
            <li><b>Info</b> (blue) — informational only.</li>
          </ul></li>
      <li><b>Title</b> — short description of the check
          (e.g. <em>Missing Account Role Mapping</em>).</li>
      <li><b>Meta card</b> — shows the <b>Category</b> (e.g.
          <em>Account Mappings</em>, <em>Fiscal Period</em>),
          <b>Entity</b> (the specific component or employee involved),
          and <b>Check Code</b> (internal identifier like
          <em>MISSING_ACCOUNT_MAPPING</em>).</li>
      <li><b>Full message</b> — detailed explanation of the issue.</li>
      <li><b>Remediation steps</b> — a numbered list of actions to
          resolve the problem. The system has built-in remediation
          guidance for over 20 common check codes.</li>
    </ul>

    <p><b>Common check codes and their fixes:</b></p>
    <ul>
      <li><b>MISSING_SALARY_EXPENSE_MAPPING</b> — Go to Payroll Setup →
          Account Role Mappings and assign a GL account to the
          Salary Expense role.</li>
      <li><b>MISSING_NET_SALARY_PAYABLE</b> — Assign a liability account
          to the Net Salary Payable role in Account Role Mappings.</li>
      <li><b>MISSING_COMPONENT_ACCOUNT</b> — The payroll component
          needs a credit or debit GL account. Open the component in
          Payroll Setup → Components and set its account.</li>
      <li><b>NO_OPEN_FISCAL_PERIOD</b> — The posting date falls outside
          any open fiscal period. Go to Accounting Setup → Fiscal
          Periods and ensure the period is open.</li>
      <li><b>EMPLOYEE_CALC_ERROR</b> — One or more employees had
          calculation errors. Open the Employee Detail view to see
          what went wrong.</li>
      <li><b>RUN_NOT_APPROVED</b> — The payroll run must be approved
          before posting. Go back and approve it first.</li>
    </ul>

    <p><b>Tip:</b> Click on any failed check in the Post Run dialog
    to open this detail view. Fix the issue, then click
    <em>Run Validation</em> to re-check.</p>
    """,
)

# ── Reporting Dialogs ─────────────────────────────────────────────────────

_register(
    "dialog.trial_balance",
    "Trial Balance Report",
    "View the trial balance for a fiscal period.",
    """
    <p>The <b>Trial Balance</b> lists all GL accounts with their debit and
    credit balances for a selected period or date range. It is the primary
    tool for verifying that the ledger is in balance before preparing
    financial statements.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Account code</b> — the OHADA account number.</li>
      <li><b>Account name</b> — description of the account.</li>
      <li><b>Opening balance</b> — balance at the start of the period
          (debit or credit).</li>
      <li><b>Period debits</b> — total debits posted during the period.</li>
      <li><b>Period credits</b> — total credits posted during the period.</li>
      <li><b>Closing balance</b> — balance at the end of the period.</li>
    </ul>

    <p><b>How to read it:</b></p>
    <ul>
      <li>The <b>total debits must equal total credits</b>. An imbalance
          indicates a posting error.</li>
      <li>Asset accounts (class 2–5) normally have debit balances.</li>
      <li>Liability and equity accounts (class 1) normally have credit
          balances.</li>
      <li>Revenue accounts (class 7) have credit balances; expense
          accounts (class 6) have debit balances.</li>
    </ul>

    <p><b>Example excerpt:</b></p>
    <table>
      <tr><td>521000</td><td>Bank - Afriland</td>
          <td>5,200,000 Dr</td><td>3,100,000</td>
          <td>2,800,000</td><td>5,500,000 Dr</td></tr>
      <tr><td>411000</td><td>Accounts Receivable</td>
          <td>8,000,000 Dr</td><td>4,500,000</td>
          <td>3,200,000</td><td>9,300,000 Dr</td></tr>
      <tr><td>701000</td><td>Sales Revenue</td>
          <td>0</td><td>0</td>
          <td>4,500,000</td><td>4,500,000 Cr</td></tr>
    </table>

    <p><b>Tip:</b> Run the trial balance at the end of each month before
    closing the period. Investigate any unusual balances — for example,
    a revenue account with a debit balance or an asset account showing
    credit — as these usually indicate mis-postings.</p>
    """,
)

_register(
    "dialog.general_ledger",
    "General Ledger Report",
    "View detailed transaction history for GL accounts.",
    """
    <p>The <b>General Ledger</b> report shows all posted transactions for
    selected accounts over a date range. It provides the complete
    transaction-level detail behind each account balance.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Date</b> — posting date of the transaction.</li>
      <li><b>Journal</b> — the journal where the entry was recorded
          (Sales, Purchases, Bank, General, etc.).</li>
      <li><b>Reference</b> — document or entry number.</li>
      <li><b>Description</b> — narration or memo.</li>
      <li><b>Debit / Credit</b> — the amounts posted.</li>
      <li><b>Running balance</b> — cumulative balance after each
          transaction.</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>Select one or more accounts and a date range.</li>
      <li>Review each posting to verify it is correct.</li>
      <li>Click a transaction to drill down to the source journal
          entry.</li>
    </ul>

    <p><b>Example:</b> Viewing account 411000 (Accounts Receivable)
    for March 2026:
    <br/>↕ 01 Mar — Opening balance: 8,000,000 XAF
    <br/>↕ 05 Mar — INV-2026-042 Sales to Brasseries: +2,500,000 Dr
    <br/>↕ 12 Mar — RCT-2026-018 Payment from SABC: −1,200,000 Cr
    <br/>↕  Balance: 9,300,000 XAF</p>

    <p><b>Tip:</b> The general ledger is essential for audit trails.
    If a trial balance figure looks unexpected, drill into the
    general ledger for that account to find the specific transactions
    causing the discrepancy.</p>
    """,
)

_register(
    "dialog.ohada_balance_sheet",
    "OHADA Balance Sheet",
    "View the balance sheet in OHADA format.",
    """
    <p>The <b>OHADA Balance Sheet</b> presents the company's financial
    position following the OHADA (SYSCOHADA) presentation standard,
    which is the mandatory format for Cameroon statutory reporting.</p>

    <p><b>Asset side:</b></p>
    <ul>
      <li><b>Fixed assets (Immobilisations)</b> — intangible assets,
          tangible assets (land, buildings, equipment, vehicles),
          and financial assets. Shown at cost less accumulated
          depreciation.</li>
      <li><b>Current assets (Actif circulant)</b> — inventory, trade
          receivables, other receivables, prepayments.</li>
      <li><b>Cash and bank (Trésorerie-Actif)</b> — bank balances
          and cash in hand.</li>
    </ul>

    <p><b>Liability side:</b></p>
    <ul>
      <li><b>Equity (Capitaux propres)</b> — share capital, reserves,
          retained earnings, and current year result.</li>
      <li><b>Long-term liabilities (Dettes financières)</b> — bank
          loans, long-term borrowings.</li>
      <li><b>Current liabilities (Passif circulant)</b> — trade
          payables, tax liabilities, social liabilities, other
          payables.</li>
      <li><b>Bank overdrafts (Trésorerie-Passif)</b> — short-term
          bank credit facilities.</li>
    </ul>

    <p><b>Key check:</b> Total Assets must equal Total Liabilities +
    Equity. If they do not balance, there are unposted or misclassified
    entries.</p>

    <p><b>Tip:</b> Ensure all period-end entries (depreciation,
    accruals, provisions) are posted before generating the balance
    sheet. This report is used for DGI annual tax filings and must
    match the <em>Bilan</em> section of the DSF.</p>
    """,
)

_register(
    "dialog.ias_balance_sheet",
    "IAS Balance Sheet",
    "View the balance sheet in IAS/IFRS format.",
    """
    <p>The <b>IAS Balance Sheet</b> (Statement of Financial Position)
    presents the company's financial position following International
    Accounting Standards (IAS/IFRS) classification.</p>

    <p><b>Assets:</b></p>
    <ul>
      <li><b>Non-current assets</b> — property, plant and equipment;
          intangible assets; financial assets; deferred tax assets.
          These are long-term resources with useful lives exceeding
          one year.</li>
      <li><b>Current assets</b> — inventories, trade receivables,
          other receivables, prepayments, cash and cash equivalents.
          Expected to be realised within 12 months.</li>
    </ul>

    <p><b>Equity and Liabilities:</b></p>
    <ul>
      <li><b>Equity</b> — share capital, retained earnings, other
          reserves, current year profit/loss.</li>
      <li><b>Non-current liabilities</b> — long-term borrowings,
          deferred tax liabilities, provisions.</li>
      <li><b>Current liabilities</b> — trade payables, tax
          liabilities, short-term borrowings, accrued expenses.
          Due within 12 months.</li>
    </ul>

    <p><b>Key check:</b> Total Assets = Total Equity + Total
    Liabilities. An imbalance signals missing or misclassified
    entries.</p>

    <p><b>Tip:</b> The IAS format is useful for international
    reporting, investor presentations, and group consolidation.
    For Cameroon statutory filings, use the OHADA Balance Sheet
    instead.</p>
    """,
)

_register(
    "dialog.ohada_income_statement",
    "OHADA Income Statement",
    "View the income statement in OHADA format.",
    """
    <p>The <b>OHADA Income Statement</b> (Compte de Résultat) shows
    revenue, expenses, and profit/loss following the SYSCOHADA
    presentation standard — the mandatory format for Cameroon
    statutory reporting.</p>

    <p><b>Sections:</b></p>
    <ul>
      <li><b>Operating revenue (Produits d’exploitation)</b> — sales
          of goods, services, and other operating income
          (accounts 70x–75x).</li>
      <li><b>Operating expenses (Charges d’exploitation)</b> —
          purchases, external charges, personnel costs,
          depreciation, and other operating charges
          (accounts 60x–68x).</li>
      <li><b>Operating result (Résultat d’exploitation)</b> —
          operating revenue minus operating expenses.</li>
      <li><b>Financial revenue/expenses</b> — interest income,
          interest expense, exchange gains/losses
          (accounts 77x, 67x).</li>
      <li><b>Financial result (Résultat financier)</b></li>
      <li><b>Extraordinary items (HAO)</b> — gains/losses outside
          normal activity (accounts 82x–87x).</li>
      <li><b>Income tax (Impôt sur le résultat)</b> — corporate
          income tax (account 89x).</li>
      <li><b>Net result (Résultat net)</b> — final profit or loss.</li>
    </ul>

    <p><b>Example reading:</b>
    <br/>↕ Operating revenue: 45,000,000 XAF
    <br/>↕ Operating expenses: 38,000,000 XAF
    <br/>↕ Operating result: 7,000,000 XAF
    <br/>↕ Financial result: −500,000 XAF
    <br/>↕ Net result before tax: 6,500,000 XAF
    <br/>↕ Tax: 2,145,000 XAF (33%)
    <br/>↕ Net result: 4,355,000 XAF</p>

    <p><b>Tip:</b> This report feeds directly into the DGI DSF annual
    filing. Verify that the net result here agrees with the balance
    sheet equity movement before submission.</p>
    """,
)

_register(
    "dialog.ias_income_statement",
    "IAS Income Statement",
    "View the income statement in IAS/IFRS format.",
    """
    <p>The <b>IAS Income Statement</b> (Statement of Profit or Loss)
    shows revenue, expenses, and profit/loss following IAS/IFRS
    classification. This format is used for international reporting
    and investor presentations.</p>

    <p><b>Sections:</b></p>
    <ul>
      <li><b>Revenue</b> — total sales of goods and services.</li>
      <li><b>Cost of sales</b> — direct costs of goods sold
          (materials, direct labour, production overheads).</li>
      <li><b>Gross profit</b> — Revenue minus Cost of Sales.
          A key indicator of product profitability.</li>
      <li><b>Selling expenses</b> — marketing, distribution,
          sales commissions.</li>
      <li><b>Administrative expenses</b> — office costs, management
          salaries, professional fees, depreciation.</li>
      <li><b>Other operating income/expenses</b> — miscellaneous
          items not fitting the above categories.</li>
      <li><b>Operating profit (EBIT)</b> — Gross Profit minus
          operating expenses.</li>
      <li><b>Finance income / Finance costs</b> — interest earned
          and interest paid.</li>
      <li><b>Profit before tax</b></li>
      <li><b>Income tax expense</b></li>
      <li><b>Net profit</b> — the bottom line.</li>
    </ul>

    <p><b>How to read it:</b> Compare each line against the prior
    period or budget to spot trends. Watch the <b>gross margin
    percentage</b> (Gross Profit ÷ Revenue) and <b>operating margin</b>
    (Operating Profit ÷ Revenue) as key performance indicators.</p>

    <p><b>Tip:</b> The line items shown depend on the template
    built in the <em>IAS Income Statement Builder</em>. If a line
    appears blank, check that the relevant GL accounts are mapped
    in the template.</p>
    """,
)

_register(
    "dialog.ias_income_statement_builder",
    "IAS Income Statement Builder",
    "Build and customise the IAS income statement template.",
    """
    <p>The <b>IAS Income Statement Builder</b> lets you define and
    customise the structure of the IAS/IFRS income statement — creating
    the template that determines how your GL accounts are grouped into
    statement sections when the report is generated.</p>

    <p><b>How to use:</b></p>
    <ol>
      <li><b>Define sections</b> — create the major sections of the
          statement: Revenue, Cost of Sales, Gross Profit, Operating
          Expenses (with optional subsections like Selling Expenses,
          Administrative Expenses), Finance Income/Costs, Tax Expense,
          and Net Profit.</li>
      <li><b>Create line items</b> — within each section, add the
          individual lines that will appear on the report (e.g.
          <em>Sales Revenue</em>, <em>Service Revenue</em>,
          <em>Raw Material Costs</em>).</li>
      <li><b>Map GL accounts</b> — assign account codes or ranges
          to each line. For example, map accounts 701–707 to the
          Revenue section.</li>
      <li><b>Set display order</b> — drag or reorder lines within
          each section to control their sequence on the printed
          report.</li>
      <li><b>Configure sign behaviour</b> — specify whether each
          line should show its natural balance or be reversed for
          display (e.g. expenses shown as positive numbers).</li>
    </ol>

    <p><b>Template structure example:</b></p>
    <ul>
      <li><b>Revenue</b> (accounts 701–707) — subtotal</li>
      <li><b>Cost of Sales</b> (accounts 601–607) — subtotal</li>
      <li><b>Gross Profit</b> = Revenue − Cost of Sales</li>
      <li><b>Operating Expenses</b>
        <ul>
          <li>Selling Expenses (accounts 61x)</li>
          <li>Administrative Expenses (accounts 62x–65x)</li>
        </ul>
      </li>
      <li><b>Operating Profit</b></li>
      <li><b>Finance Costs</b> (accounts 67x)</li>
      <li><b>Profit Before Tax</b></li>
      <li><b>Income Tax</b> (accounts 89x)</li>
      <li><b>Net Profit</b></li>
    </ul>

    <p><b>Tip:</b> After building the template, use the
    <em>Template Preview</em> to verify completeness. Check that all
    revenue and expense accounts are mapped — unmapped accounts will
    be excluded from the report.</p>
    """,
)

_register(
    "dialog.ias_income_statement_mapping",
    "IAS Mapping Editor",
    "Map your chart of accounts to IAS/IFRS income statement sections so the report can be generated automatically.",
    """
    <p>The <b>IAS Mapping Editor</b> connects your general-ledger accounts to
    the sections of the IAS/IFRS income statement. Once every relevant account
    is mapped, the income statement report builds itself from posted journal
    data.</p>

    <p><b>Accounts Available (left panel)</b></p>
    <ul>
      <li>Lists every account in the company chart of accounts.</li>
      <li>Use the <em>Search</em> bar to filter by code or name.</li>
      <li>Select one or more accounts (hold Ctrl or Shift for multi-select),
          then configure the mapping on the right and click
          <em>Assign Selected Accounts</em>.</li>
      <li>The <b>Status</b> column tells you whether the account is
          <em>Relevant</em> (revenue/expense — should be mapped),
          <em>Control-only</em>, <em>Active</em>, or <em>Inactive</em>.</li>
      <li>The <b>Current Mapping</b> column shows the section an account is
          already assigned to, if any.</li>
    </ul>

    <p><b>Current Mappings (top-right panel)</b></p>
    <ul>
      <li>Shows every mapping that has been saved for this company.</li>
      <li><b>Double-click</b> a row to load it back into the editor for
          changes.</li>
      <li>Inactive mappings remain visible for review but are excluded from
          report calculations.</li>
    </ul>

    <p><b>Mapping Editor (bottom-right panel)</b></p>
    <ul>
      <li><b>Section</b> — the IAS statement line the account feeds into
          (Revenue, Cost of Sales, Finance Income, etc.).</li>
      <li><b>Subsection</b> — required when you choose <em>Operating
          Expenses</em>. Pick the appropriate sub-category: Selling &amp;
          Distribution, Administrative, Other Operating Expenses, or Other
          Operating Income.</li>
      <li><b>Sign Behavior</b> — <em>Normal</em> keeps the account's natural
          debit/credit direction. <em>Inverted</em> flips the sign, which is
          useful when an account's normal balance is the opposite of what the
          statement section expects.</li>
      <li><b>Display Order</b> — lower numbers appear first within the same
          section. Use multiples of 10 to leave room for future inserts.</li>
      <li><b>Active</b> — uncheck to exclude a mapping from the report
          without deleting it.</li>
    </ul>

    <p><b>Action buttons</b></p>
    <ul>
      <li><b>Assign Selected Accounts</b> — saves the editor settings for
          every account currently selected on the left. Creates new mappings
          or updates existing ones.</li>
      <li><b>Deactivate / Reactivate Mapping</b> — toggles the active state
          of the mapping selected in the <em>Current Mappings</em> table.</li>
      <li><b>Clear Editor</b> — resets all editor fields without saving.</li>
      <li><b>Refresh</b> — reloads all data from the database.</li>
    </ul>

    <p><b>Status bar</b></p>
    <p>The bottom of the dialog shows a summary: total mappings, unmapped
    relevant accounts, and any errors or warnings. Each account that is
    relevant to the income statement (typically classes 6, 7, and 8) but not
    yet mapped is counted as unmapped. Resolve all errors for a complete,
    accurate report.</p>

    <p><b>Tip:</b> Each account can be mapped to exactly one section. If you
    reassign an account, the previous mapping is replaced. Start by mapping
    all class-7 accounts to <em>Revenue</em>, then work through expense
    classes to the appropriate sections.</p>
    """,
)

_register(
    "dialog.ias_income_statement_line_detail",
    "IAS Income Statement Line Detail",
    "View detailed account-level breakdown for an income statement line.",
    """
    <p>When you click on a line in the IAS Income Statement (for example
    <em>Revenue</em> showing 12,500,000 XAF), this dialog opens to reveal
    every GL account that contributed to that figure.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Account code and name</b> — each GL account mapped to this
          statement section.</li>
      <li><b>Period balance</b> — the posted balance of that account for
          the selected date range.</li>
      <li><b>Contribution</b> — shows whether the account added to or
          reduced the line total (based on sign behaviour).</li>
    </ul>

    <p><b>Example:</b> Clicking the <em>Revenue</em> line might show:
    <br/>&#8195;701 — Sales of Finished Goods: 8,200,000 XAF
    <br/>&#8195;706 — Services Revenue: 3,100,000 XAF
    <br/>&#8195;707 — Miscellaneous Revenue: 1,200,000 XAF
    <br/>Total: 12,500,000 XAF — matching the statement line.</p>

    <p><b>Tip:</b> Use this drilldown to verify that the income statement
    is pulling the correct accounts. If an account appears in the wrong
    section, go to the IAS Mapping Editor to correct the mapping.</p>
    """,
)

_register(
    "dialog.ias_income_statement_template_preview",
    "IAS Income Statement Template Preview",
    "Preview the configured IAS income statement template.",
    """
    <p>This dialog displays the full structure of your IAS income statement
    template — showing every section, the order of lines within each
    section, and which GL accounts are mapped to each line. Use it to
    verify the template is complete and correctly configured before
    generating the actual report.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Section hierarchy</b> — Revenue, Cost of Sales, Gross Profit,
          Operating Expenses (with subsections), Finance Income/Costs,
          Tax Expense, and Net Profit.</li>
      <li><b>Mapped accounts</b> — the GL accounts assigned to each
          section, with their display order and sign behaviour.</li>
      <li><b>Unmapped accounts</b> — a count of relevant revenue and
          expense accounts not yet assigned to any section.</li>
    </ul>

    <p><b>Tip:</b> A template with unmapped accounts will produce an
    incomplete income statement. Resolve all unmapped accounts in the
    IAS Mapping Editor before relying on the report for financial
    reporting.</p>
    """,
)

_register(
    "dialog.ohada_income_statement_line_detail",
    "OHADA Income Statement Line Detail",
    "View detailed account-level breakdown for an OHADA income statement line.",
    """
    <p>When you click on a line in the OHADA Income Statement, this dialog
    reveals the individual GL accounts and their balances that make up
    that figure. The OHADA format groups expenses and revenue by nature
    (not function), so each line maps to specific SYSCOHADA account
    classes.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Account code and name</b> — each GL account contributing to
          the selected line.</li>
      <li><b>Posted balance</b> — the amount from posted journal entries
          within the selected period.</li>
    </ul>

    <p><b>Example:</b> Clicking <em>Purchases of Goods (TA)</em> might
    show:
    <br/>&#8195;601 — Purchases of Goods: 4,800,000 XAF
    <br/>&#8195;602 — Purchase of Raw Materials: 1,200,000 XAF
    <br/>Total: 6,000,000 XAF — matching the OHADA statement line.</p>

    <p><b>Tip:</b> If a line value looks wrong, check whether the
    correct class-6 or class-7 accounts are included. OHADA account
    groupings follow the SYSCOHADA plan — verify your chart of accounts
    codes match the expected ranges.</p>
    """,
)

_register(
    "dialog.ohada_income_statement_template_preview",
    "OHADA Income Statement Template Preview",
    "Preview the OHADA income statement template structure.",
    """
    <p>This dialog displays the full structure of your OHADA (SYSCOHADA)
    income statement template. The OHADA format presents charges and
    revenue <em>by nature</em> and computes several intermediate results:
    Operating Result, Financial Result, Extraordinary Result, and Net
    Result.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Statutory line items</b> — each line prescribed by the
          SYSCOHADA framework (e.g. TA — Sales of Goods, TB — Sales of
          Finished Products, RA — Purchases of Goods, etc.).</li>
      <li><b>Subtotals</b> — computed intermediate results (Value Added,
          EBITDA, Operating Result, etc.).</li>
      <li><b>Mapped accounts</b> — the GL accounts assigned to each
          statutory line.</li>
    </ul>

    <p><b>Tip:</b> The OHADA template is largely pre-configured based on
    the SYSCOHADA plan account code ranges. Review the preview to confirm
    all accounts are assigned correctly, especially if you have created
    custom accounts outside the standard code ranges.</p>
    """,
)

_register(
    "dialog.balance_sheet_template_preview",
    "Balance Sheet Template Preview",
    "Preview the balance sheet template structure.",
    """
    <p>This dialog displays the full structure of your balance sheet
    template — showing how GL accounts are grouped into asset, liability,
    and equity sections for financial reporting.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Asset sections</b> — Fixed Assets (class 2), Current Assets
          (class 3 and parts of class 4), and Cash &amp; Bank (class 5).</li>
      <li><b>Liability sections</b> — Long-term Liabilities (class 1),
          Current Liabilities (parts of class 4), and Provisions.</li>
      <li><b>Equity section</b> — Share Capital, Reserves, Retained
          Earnings, and Current Year Result.</li>
      <li><b>Mapped accounts</b> — each GL account assigned to a
          balance sheet line, with display order.</li>
    </ul>

    <p><b>Tip:</b> Every balance sheet account (classes 1–5) should be
    mapped. Unmapped accounts mean their balances will be missing from
    the report. Check the unmapped count and resolve any gaps before
    generating the balance sheet for management or statutory filing.</p>
    """,
)

_register(
    "dialog.balance_sheet_line_detail",
    "Balance Sheet Line Detail",
    "View detailed account-level breakdown for a balance sheet line.",
    """
    <p>When you click on a balance sheet line (for example <em>Trade
    Receivables</em> showing 3,400,000 XAF), this dialog opens to show
    every GL account that contributed to that figure.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Account code and name</b> — each GL account mapped to this
          balance sheet line.</li>
      <li><b>Balance</b> — the closing balance of that account as at the
          report date.</li>
      <li><b>Direction</b> — whether the account carries a debit or
          credit balance (highlighting any unusual reverse balances).</li>
    </ul>

    <p><b>Example:</b> Clicking <em>Trade Receivables</em> might show:
    <br/>&#8195;411 — Customers: 2,800,000 XAF (debit)
    <br/>&#8195;4181 — Accrued Revenue: 600,000 XAF (debit)
    <br/>Total: 3,400,000 XAF.
    A reverse-balance customer account (credit) would be flagged for
    investigation — it may indicate an over-payment.</p>

    <p><b>Tip:</b> Use this drilldown at period-end to verify balance
    sheet lines before management sign-off. Unusual balances on
    individual accounts are easier to spot in this detail view than
    on the summary report.</p>
    """,
)

_register(
    "dialog.ar_aging",
    "Accounts Receivable Aging",
    "View the AR aging report — outstanding customer balances by age.",
    """
    <p>The <b>AR Aging</b> report shows all outstanding customer invoices
    grouped by age bucket, helping you identify overdue receivables and
    prioritise collection efforts.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Customer</b> — name and code.</li>
      <li><b>Current</b> — invoices not yet due.</li>
      <li><b>1–30 days</b> — overdue by up to 30 days.</li>
      <li><b>31–60 days</b> — overdue by 31–60 days.</li>
      <li><b>61–90 days</b> — overdue by 61–90 days.</li>
      <li><b>Over 90 days</b> — seriously overdue.</li>
      <li><b>Total</b> — total outstanding per customer.</li>
    </ul>

    <p><b>Example:</b></p>
    <table>
      <tr><td>Brasseries du Cameroun</td><td>1,500,000</td>
          <td>800,000</td><td>0</td><td>0</td><td>0</td>
          <td>2,300,000</td></tr>
      <tr><td>SABC Douala</td><td>0</td><td>350,000</td>
          <td>1,200,000</td><td>0</td><td>0</td>
          <td>1,550,000</td></tr>
      <tr><td>Ets Nkamga</td><td>0</td><td>0</td><td>0</td>
          <td>450,000</td><td>300,000</td><td>750,000</td></tr>
    </table>
    <p>In this example, Ets Nkamga has 750,000 XAF overdue by more
    than 60 days and should be prioritised for follow-up.</p>

    <p><b>How to use:</b></p>
    <ul>
      <li>Select the aging date (usually today or month-end).</li>
      <li>Review totals by customer and age bracket.</li>
      <li>Click a customer row to drill down to individual invoices.</li>
      <li>Use the totals to assess collection risk and cash flow
          impact.</li>
    </ul>

    <p><b>Tip:</b> Run this report weekly in a growing business.
    Focus on the 60+ and 90+ columns — these represent the highest
    risk of non-payment and may require provision for doubtful debts.</p>
    """,
)

_register(
    "dialog.ap_aging",
    "Accounts Payable Aging",
    "View the AP aging report — outstanding supplier balances by age.",
    """
    <p>The <b>AP Aging</b> report shows all outstanding supplier bills
    grouped by age bucket, helping you manage payment scheduling and
    cash flow.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Supplier</b> — name and code.</li>
      <li><b>Current</b> — bills not yet due.</li>
      <li><b>1–30 days</b> — overdue by up to 30 days.</li>
      <li><b>31–60 days</b> — overdue by 31–60 days.</li>
      <li><b>61–90 days</b> — overdue by 61–90 days.</li>
      <li><b>Over 90 days</b> — seriously overdue.</li>
      <li><b>Total</b> — total outstanding per supplier.</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>Select the aging date.</li>
      <li>Review totals by supplier and age bracket.</li>
      <li>Click a supplier to drill down to individual bills.</li>
      <li>Identify which suppliers to pay first based on due dates
          and relationship importance.</li>
    </ul>

    <p><b>Example:</b> If a supplier shows 2,000,000 XAF in the
    61–90 day column, that bill is significantly overdue. Check
    whether the supplier has stopped deliveries or is charging
    late-payment penalties.</p>

    <p><b>Tip:</b> Compare AP aging against available cash to
    plan payment runs. Pay critical suppliers and overdue balances
    first to maintain good vendor relationships and avoid supply
    disruptions.</p>
    """,
)

_register(
    "dialog.customer_statement",
    "Customer Statement",
    "Generate a customer account statement.",
    """
    <p>The <b>Customer Statement</b> shows all transactions and the running
    balance for a selected customer over a date range. It can be sent to
    the customer as a formal record of their account.</p>

    <p><b>Statement contents:</b></p>
    <ul>
      <li><b>Opening balance</b> — amount owed at the start of the
          period.</li>
      <li><b>Invoices issued</b> — each invoice with date, number,
          and amount.</li>
      <li><b>Credit notes</b> — any credits applied.</li>
      <li><b>Payments received</b> — receipts allocated to this
          customer.</li>
      <li><b>Running balance</b> — cumulative balance after each
          transaction.</li>
      <li><b>Closing balance</b> — total amount currently owed.</li>
    </ul>

    <p><b>Example:</b>
    <br/>↕ 01 Mar — Opening balance: 3,500,000 XAF
    <br/>↕ 05 Mar — INV-2026-042: +2,500,000 → 6,000,000
    <br/>↕ 12 Mar — RCT-2026-018: −1,500,000 → 4,500,000
    <br/>↕ 20 Mar — INV-2026-055: +1,800,000 → 6,300,000
    <br/>↕ 31 Mar — Closing balance: 6,300,000 XAF</p>

    <p><b>Reconciliation:</b> Ask the customer to confirm the closing
    balance. If they disagree, compare transaction-by-transaction to
    find mismatches (e.g. unrecorded payments, disputed invoices).</p>

    <p><b>Tip:</b> Send statements monthly to all customers with
    outstanding balances. This encourages timely payment and helps
    identify errors early.</p>
    """,
)

_register(
    "dialog.supplier_statement",
    "Supplier Statement",
    "Generate a supplier account statement.",
    """
    <p>The <b>Supplier Statement</b> shows all transactions and the running
    balance for a selected supplier over a date range. Use it to verify
    your records against the supplier's own statement.</p>

    <p><b>Statement contents:</b></p>
    <ul>
      <li><b>Opening balance</b> — amount owed at the start of the
          period.</li>
      <li><b>Bills received</b> — each bill with date, reference,
          and amount.</li>
      <li><b>Credit notes</b> — any supplier credits applied.</li>
      <li><b>Payments made</b> — your payments to the supplier.</li>
      <li><b>Running balance</b> — cumulative balance after each
          transaction.</li>
      <li><b>Closing balance</b> — total amount currently owed.</li>
    </ul>

    <p><b>Example:</b>
    <br/>↕ 01 Mar — Opening balance: 1,200,000 XAF
    <br/>↕ 08 Mar — BILL-2026-031: +850,000 → 2,050,000
    <br/>↕ 15 Mar — PAY-2026-012: −1,200,000 → 850,000
    <br/>↕ 25 Mar — BILL-2026-045: +600,000 → 1,450,000
    <br/>↕ 31 Mar — Closing balance: 1,450,000 XAF</p>

    <p><b>Reconciliation:</b> Compare this statement against the
    supplier's statement item by item. Common discrepancies include:
    bills recorded in different periods, unrecorded credit notes,
    or payments not yet received by the supplier.</p>

    <p><b>Tip:</b> Reconcile supplier statements monthly, especially
    for major suppliers. This prevents surprises at year-end and
    ensures your AP balance is accurate.</p>
    """,
)

_register(
    "dialog.treasury_report",
    "Treasury Report",
    "View treasury and cash flow reports.",
    """
    <p>The <b>Treasury Report</b> provides a comprehensive view of your
    cash and bank position, showing balances, movements, and trends
    across all financial accounts.</p>

    <p><b>Report sections:</b></p>
    <ul>
      <li><b>Account balances</b> — opening and closing balance for
          each bank and cash account, with the net movement.</li>
      <li><b>Transaction summary</b> — total receipts and
          disbursements per account, with transaction counts.</li>
      <li><b>Cash flow analysis</b> — breakdown of cash inflows
          by source (customer receipts, other income) and outflows
          by type (supplier payments, payroll, taxes, etc.).</li>
    </ul>

    <p><b>Example summary for March 2026:</b>
    <br/>↕ Afriland First Bank (521100):
    <br/>↕  Opening: 8,500,000 XAF
    <br/>↕  Receipts: +6,200,000 (14 transactions)
    <br/>↕  Disbursements: −4,800,000 (22 transactions)
    <br/>↕  Closing: 9,900,000 XAF
    <br/>↕ Cash in Hand (571000):
    <br/>↕  Opening: 250,000 | Closing: 180,000
    <br/>↕ Total treasury: 10,080,000 XAF</p>

    <p><b>Use cases:</b></p>
    <ul>
      <li>Daily cash position check.</li>
      <li>Monthly bank reconciliation preparation.</li>
      <li>Cash flow forecasting input.</li>
      <li>Management reporting on liquidity.</li>
    </ul>

    <p><b>Tip:</b> Compare the closing balances shown here against
    your bank statements to identify any unrecorded transactions or
    timing differences.</p>
    """,
)

_register(
    "dialog.fixed_asset_register",
    "Fixed Asset Register Report",
    "View the complete fixed asset register with depreciation details.",
    """
    <p>The <b>Fixed Asset Register</b> report lists all fixed assets with
    their acquisition cost, accumulated depreciation, and net book value
    (NBV) as at the report date.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Asset number</b> — unique identifier.</li>
      <li><b>Asset name</b> — description.</li>
      <li><b>Category</b> — asset category (Vehicles, IT Equipment,
          Furniture, Buildings, etc.).</li>
      <li><b>Acquisition date</b> — when acquired.</li>
      <li><b>Acquisition cost</b> — original cost.</li>
      <li><b>Accumulated depreciation</b> — total depreciation
          charged to date.</li>
      <li><b>Net book value</b> — Cost − Accumulated Depreciation.</li>
      <li><b>Status</b> — Active, Fully Depreciated, or Disposed.</li>
    </ul>

    <p><b>Filters:</b></p>
    <ul>
      <li><b>Category</b> — show only assets in a specific category.</li>
      <li><b>Status</b> — active, fully depreciated, or disposed.</li>
      <li><b>Date range</b> — filter by acquisition date.</li>
    </ul>

    <p><b>Example:</b> The register might show:
    <br/>↕ FA-001 | Toyota Hilux | Vehicles | 15,000,000 cost |
    6,000,000 accum. depr. | 9,000,000 NBV | Active
    <br/>↕ FA-015 | HP Laptop | IT Equipment | 450,000 cost |
    450,000 accum. depr. | 0 NBV | Fully Depreciated</p>

    <p><b>Tip:</b> Run this report at year-end and provide it to
    auditors. Cross-check the total NBV against the fixed asset
    balance sheet accounts to ensure the register and ledger agree.</p>
    """,
)

_register(
    "dialog.depreciation_report",
    "Depreciation Report",
    "View depreciation charges for a period or date range.",
    """
    <p>The <b>Depreciation Report</b> shows depreciation charges broken
    down by asset and category for a selected period or date range.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Asset</b> — name and number of the asset.</li>
      <li><b>Category</b> — asset category.</li>
      <li><b>Method</b> — depreciation method (Straight-Line,
          Declining Balance, etc.).</li>
      <li><b>Period charge</b> — the depreciation amount for the
          selected period.</li>
      <li><b>Cumulative</b> — total depreciation to date.</li>
    </ul>

    <p><b>Useful for:</b></p>
    <ul>
      <li><b>Month-end journal verification</b> — confirm the
          depreciation journal entry amount matches this report.</li>
      <li><b>Asset-level tracking</b> — see exactly how much each
          asset is being depreciated.</li>
      <li><b>Category summaries</b> — total depreciation by asset
          type (e.g. all vehicles, all IT equipment).</li>
      <li><b>Audit support</b> — provide as evidence for the
          depreciation policy and calculations.</li>
    </ul>

    <p><b>Example:</b> March 2026 depreciation:
    <br/>↕ Vehicles: 450,000 XAF (3 assets)
    <br/>↕ IT Equipment: 125,000 XAF (8 assets)
    <br/>↕ Furniture: 45,000 XAF (12 assets)
    <br/>↕ Total: 620,000 XAF — should match the depreciation
    journal entry for March.</p>

    <p><b>Tip:</b> Run this report before and after each depreciation
    run to verify the calculations. If an asset was added or disposed
    mid-month, check that the pro-rata calculation is correct.</p>
    """,
)

_register(
    "dialog.stock_valuation",
    "Stock Valuation Report",
    "View inventory valuation across items and locations.",
    """
    <p>The <b>Stock Valuation</b> report shows the total value of
    inventory on hand, broken down by item and optionally by location.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Item code / name</b> — the inventory item.</li>
      <li><b>Category</b> — the item category.</li>
      <li><b>Location</b> — where the stock is held (if grouped by
          location).</li>
      <li><b>Quantity on hand</b> — current stock quantity.</li>
      <li><b>Unit cost</b> — the valuation cost per unit (based on
          the costing method: Weighted Average, FIFO, or Standard).</li>
      <li><b>Total value</b> — Quantity × Unit Cost.</li>
    </ul>

    <p><b>Summary:</b> The report footer shows the grand total
    inventory value. This figure should agree with the sum of your
    balance sheet inventory accounts (class 3).</p>

    <p><b>Example:</b>
    <br/>↕ Cement 50kg: 120 bags × 4,500 = 540,000 XAF
    <br/>↕ Steel Bar 12mm: 85 pcs × 12,000 = 1,020,000 XAF
    <br/>↕ Paint 20L White: 24 tins × 8,500 = 204,000 XAF
    <br/>↕ Grand total: 1,764,000 XAF</p>

    <p><b>Tip:</b> Run this report at month-end and compare the total
    against your GL inventory accounts. A discrepancy indicates
    unposted inventory documents or incorrect category GL mappings.</p>
    """,
)

_register(
    "dialog.stock_movement",
    "Stock Movement Report",
    "View inventory movement history over a period.",
    """
    <p>The <b>Stock Movement</b> report shows all inventory transactions
    that occurred during a date range — giving a complete picture of
    what came in, what went out, and what changed.</p>

    <p><b>Columns:</b></p>
    <ul>
      <li><b>Date</b> — when the movement occurred.</li>
      <li><b>Document reference</b> — the inventory document that
          recorded the movement.</li>
      <li><b>Item</b> — the item affected.</li>
      <li><b>Movement type</b> — Receipt, Issue, Adjustment, or
          Transfer.</li>
      <li><b>Location</b> — the location affected.</li>
      <li><b>Quantity</b> — the quantity moved (positive for in,
          negative for out).</li>
      <li><b>Unit cost</b> — the valuation cost at the time of
          movement.</li>
    </ul>

    <p><b>Filters:</b></p>
    <ul>
      <li><b>Item</b> — focus on a specific item's history.</li>
      <li><b>Location</b> — see movements at a specific warehouse.</li>
      <li><b>Movement type</b> — show only receipts, issues, etc.</li>
      <li><b>Date range</b> — the period to analyse.</li>
    </ul>

    <p><b>Example use case:</b> To understand why Cement 50kg stock
    dropped from 200 to 120 bags in March:
    <br/>↕ Filter: Item = Cement 50kg, Date = 01–31 March 2026
    <br/>↕ Results show: 3 receipts (+150 bags), 5 issues (−230 bags)
    <br/>Net movement: −80 bags, explaining the drop from 200 to 120.</p>

    <p><b>Tip:</b> This report is essential for inventory audits.
    Reconcile the opening quantity + net movements = closing quantity
    for each item to verify data integrity.</p>
    """,
)

_register(
    "dialog.payroll_summary_report",
    "Payroll Summary Report",
    "View aggregated payroll data across runs and periods.",
    """
    <p>The <b>Payroll Summary Report</b> aggregates payroll data across
    multiple runs and periods, providing management-level visibility
    into labour costs.</p>

    <p><b>Report sections:</b></p>
    <ul>
      <li><b>Total payroll cost by period</b> — gross salaries,
          employer contributions, and total cost per month.</li>
      <li><b>Department breakdown</b> — payroll cost by department
          or business unit.</li>
      <li><b>Statutory contributions</b> — totals for each
          statutory component:
        <ul>
          <li>CNPS (employer and employee shares)</li>
          <li>IRPP (employee income tax)</li>
          <li>CFC (Crédit Foncier du Cameroun)</li>
          <li>Any other configured statutory deductions</li>
        </ul>
      </li>
      <li><b>Year-to-date summaries</b> — cumulative totals from
          the start of the fiscal year.</li>
    </ul>

    <p><b>Example summary for March 2026:</b>
    <br/>↕ Gross salaries: 12,500,000 XAF
    <br/>↕ CNPS employer: 2,187,500 XAF (17.5%)
    <br/>↕ IRPP withheld: 1,450,000 XAF
    <br/>↕ CFC: 125,000 XAF
    <br/>↕ Total payroll cost: 16,262,500 XAF
    <br/>↕ YTD (Jan–Mar): 48,450,000 XAF</p>

    <p><b>Tip:</b> Compare the report totals against the payroll
    journal entries for the same period to verify that postings are
    complete and accurate. This report is also required for DGI
    statutory filings.</p>
    """,
)

_register(
    "dialog.financial_analysis",
    "Financial Analysis",
    "Explore financial ratios, trends, and insights.",
    """
    <p>The <b>Financial Analysis</b> workspace provides computed financial
    ratios, trend analysis, and automatically generated insights based on
    your posted accounting data.</p>

    <p><b>Ratio categories:</b></p>
    <ul>
      <li><b>Liquidity</b> — Current Ratio, Quick Ratio, Cash Ratio.
          Measures the company's ability to meet short-term
          obligations.</li>
      <li><b>Profitability</b> — Gross Margin, Net Profit Margin,
          Return on Equity, Return on Assets. Measures how
          effectively the company generates profit.</li>
      <li><b>Efficiency</b> — Receivables Turnover, Payables Turnover,
          Inventory Turnover. Measures how well the company uses
          its assets and manages working capital.</li>
      <li><b>Leverage</b> — Debt-to-Equity, Debt Ratio, Interest
          Coverage. Measures the company's financial risk from
          borrowing.</li>
    </ul>

    <p><b>Trends:</b> Period-over-period charts showing revenue growth,
    cost movement, margin evolution, and working capital changes. Trends
    are most useful when you have at least 3–6 months of posted data.</p>

    <p><b>Insights:</b> The system automatically scans your data for
    notable patterns and generates observations — e.g. <em>"Cash
    position declined 20% month-over-month"</em> or <em>"Receivables
    concentration: top customer is 55% of AR"</em>. Insights are
    colour-coded by severity.</p>

    <p><b>Tip:</b> Financial analysis reads from <b>posted data only</b>.
    Ensure all period-end entries (depreciation, accruals, adjustments)
    are posted before reviewing ratios and trends for accurate results.</p>
    """,
)

_register(
    "dialog.financial_analysis_detail",
    "Financial Analysis Detail",
    "View the detailed breakdown of a specific financial ratio or metric.",
    """
    <p>When you click on a ratio or metric in the Financial Analysis
    workspace, this dialog shows exactly how it was computed — the
    formula, the source account balances, and the resulting value.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Ratio name and category</b> — e.g. <em>Current Ratio</em>
          (Liquidity), <em>Net Profit Margin</em> (Profitability).</li>
      <li><b>Formula</b> — the calculation used, in plain terms
          (e.g. Current Assets &divide; Current Liabilities).</li>
      <li><b>Numerator accounts</b> — the GL accounts and balances
          that form the top of the ratio.</li>
      <li><b>Denominator accounts</b> — the GL accounts and balances
          that form the bottom.</li>
      <li><b>Result</b> — the computed ratio value, with a benchmark
          indicator where applicable (e.g. Current Ratio above 1.0
          is generally healthy).</li>
    </ul>

    <p><b>Example:</b> The Current Ratio detail might show:
    <br/>&#8195;Numerator (Current Assets): Cash 2,400,000 + Receivables
    3,100,000 + Inventory 1,800,000 = 7,300,000 XAF
    <br/>&#8195;Denominator (Current Liabilities): Payables 2,900,000 +
    Tax Due 600,000 + Short-term Loans 1,200,000 = 4,700,000 XAF
    <br/>&#8195;Current Ratio = 7,300,000 &divide; 4,700,000 = <b>1.55</b></p>

    <p><b>Tip:</b> If a ratio looks unexpected, check the source
    accounts here — a miscategorised account or unmapped balance sheet
    line can distort ratio calculations.</p>
    """,
)

_register(
    "dialog.financial_analysis_workspace",
    "Financial Analysis Workspace",
    "Interactive financial analysis workspace with charts and drilldowns.",
    """
    <p>The <b>Financial Analysis Workspace</b> provides an interactive
    environment for exploring financial ratios, charts, and trend data
    on a single screen.</p>

    <p><b>Workspace areas:</b></p>
    <ul>
      <li><b>Ratio cards</b> — summary tiles for key ratios with
          current value and trend indicator. Click a card to see
          the full calculation breakdown.</li>
      <li><b>Charts panel</b> — interactive visualisations showing
          trends over time (revenue, costs, margins, ratios). Hover
          for data labels; click for detail.</li>
      <li><b>Insights panel</b> — automatically generated
          observations about your financial data, colour-coded by
          severity (blue = informational, amber = caution,
          red = alert).</li>
      <li><b>Period selector</b> — choose the reporting date range
          and comparison period.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>Drill down</b> — click any ratio or chart element to
          see source account data.</li>
      <li><b>Compare periods</b> — select a comparison period to see
          change from prior month, quarter, or year.</li>
      <li><b>Print / Export</b> — generate a print-ready analysis
          document with all ratios, charts, and insights included.</li>
    </ul>

    <p><b>Tip:</b> Use this workspace for monthly management reviews.
    The combination of ratios, trends, and insights gives a
    comprehensive financial health overview on a single page.</p>
    """,
)

_register(
    "dialog.chart_detail",
    "Chart Detail",
    "View a chart or graph in expanded detail.",
    """
    <p>This dialog opens an enlarged version of a chart from a report or
    the analytics dashboard, making it easier to read labels, spot trends,
    and present to colleagues.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Full-size chart</b> — the same visualisation rendered at
          a larger scale with complete data labels on every data point.</li>
      <li><b>Data table</b> — an optional tabular view of the underlying
          numbers behind the chart. Toggle it to cross-check specific
          values.</li>
      <li><b>Period selector</b> — if available, adjust the date range
          directly from this view.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>Print</b> — send the chart to a printer.</li>
      <li><b>Export</b> — save as an image (PNG) or PDF for inclusion
          in presentations or management packs.</li>
    </ul>

    <p><b>Tip:</b> Use the data table toggle to verify chart values
    against your own calculations or source reports. This is especially
    useful during month-end review or board pack preparation.</p>
    """,
)

_register(
    "dialog.ledger_drilldown",
    "Ledger Drilldown",
    "View the source journal entries behind a report line.",
    """
    <p>The <b>Ledger Drilldown</b> shows the individual journal entry
    lines that make up a selected report value — providing full audit
    trail visibility from summary number down to every posted
    transaction.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Journal entry reference</b> — the entry number
          (e.g. JE-2026-0042).</li>
      <li><b>Date</b> — the posting date of each entry.</li>
      <li><b>Description</b> — the narration from the journal entry.</li>
      <li><b>Source document</b> — the originating document
          (invoice, bill, receipt, etc.) if applicable.</li>
      <li><b>Debit / Credit</b> — the individual amounts on each line.</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click on any amount in a report (trial balance, ledger,
          income statement, balance sheet) to open this drilldown.</li>
      <li>Review each posting to understand how the total was built.</li>
      <li>Click a journal entry reference to open the full journal
          entry for further inspection.</li>
    </ul>

    <p><b>Example:</b> Drilling down on account 601 — Purchases of
    Goods (balance 4,200,000 XAF) might show:
    <br/>&#8195;JE-2026-0102 — 15 Feb — <em>Stock purchase Ngum
    Trading</em> — Debit 1,800,000
    <br/>&#8195;JE-2026-0118 — 22 Feb — <em>Raw materials Douala
    Port</em> — Debit 2,400,000
    <br/>Total: 4,200,000 XAF.</p>

    <p><b>Tip:</b> The drilldown is the primary audit verification tool.
    When a report value looks unexpected, drill down to trace it back
    to the originating transactions and investigate individual entries.</p>
    """,
)

_register(
    "dialog.journal_source_detail",
    "Journal Source Detail",
    "View the source document for a journal entry.",
    """
    <p>Many journal entries are created automatically by source documents —
    a sales invoice, purchase bill, customer receipt, depreciation run, or
    payroll posting. This dialog shows the original document that created
    the selected journal entry, providing a complete audit trail from
    ledger back to source.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Source document type</b> — Sales Invoice, Purchase Bill,
          Customer Receipt, Supplier Payment, Depreciation Run,
          Payroll Run, Treasury Transaction, etc.</li>
      <li><b>Document reference</b> — the original document number
          (e.g. INV-2026-0042).</li>
      <li><b>Key details</b> — date, counterparty, amount, and status
          of the source document.</li>
    </ul>

    <p><b>Example:</b> A journal entry with reference JE-2026-0159 was
    generated by Sales Invoice INV-2026-0042. Opening the source detail
    shows the invoice: Customer <em>Ngum Trading</em>, dated 15 March
    2026, total 1,250,000 XAF, Status: Posted.</p>

    <p><b>Tip:</b> If a journal entry has no source document link, it
    was created as a manual journal entry (General, Adjustment, Opening,
    or Closing type). Manual entries show their own description instead.</p>
    """,
)

_register(
    "dialog.report_drilldown",
    "Report Drilldown",
    "Drill down into report line items for detail.",
    """
    <p>When you click on a value in a financial report (balance sheet,
    income statement, trial balance, or any summary report), the
    drilldown dialog opens to show the detailed data behind that number.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Account-level breakdown</b> — each GL account and its
          balance that contributes to the report line.</li>
      <li><b>Transaction list</b> — the individual posted journal entry
          lines that make up each account balance.</li>
      <li><b>Document references</b> — the source documents
          (invoices, bills, manual entries) for each transaction.</li>
    </ul>

    <p><b>How to use:</b></p>
    <ul>
      <li>Click any amount on a report to open the drilldown.</li>
      <li>Expand an account to see its individual transactions.</li>
      <li>Click a transaction reference to view the source journal
          entry or document.</li>
    </ul>

    <p><b>Tip:</b> Drilldowns are the primary audit verification tool.
    When a report value looks unexpected, drill down to trace it back
    to the originating transactions and documents.</p>
    """,
)

_register(
    "dialog.operational_report_line_detail",
    "Operational Report Line Detail",
    "View details behind an operational report figure.",
    """
    <p>Operational reports — such as AR Aging, AP Aging, Stock Valuation,
    and Payroll summaries — show aggregated figures. This drilldown reveals
    the individual documents and transactions behind a selected figure.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Source documents</b> — the invoices, bills, receipts,
          inventory movements, or payroll entries that built the figure.</li>
      <li><b>Key details per document</b> — reference, date, counterparty,
          amount, and current status.</li>
      <li><b>Calculation breakdown</b> — where the figure involves a
          computation (e.g. aging bucket classification), the logic is
          shown step by step.</li>
    </ul>

    <p><b>Example:</b> On the AR Aging report, clicking the 31–60 days
    column for customer <em>Mbeki Corp</em> (450,000 XAF) would show the
    two invoices that fall in that bucket:
    <br/>&#8195;INV-2026-0031 — 200,000 XAF — dated 25 Jan 2026 (34 days)
    <br/>&#8195;INV-2026-0038 — 250,000 XAF — dated 02 Feb 2026 (56 days)</p>

    <p><b>Tip:</b> Use this detail view to verify report figures before
    sharing with management. It's also useful for preparing collection
    lists or payment schedules from aging data.</p>
    """,
)

_register(
    "dialog.ratio_detail",
    "Ratio Detail",
    "View the calculation breakdown for a financial ratio.",
    """
    <p>This dialog shows the full calculation behind a financial ratio:
    the formula, the account balances that feed into it, and the
    resulting value with trend context.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Ratio category</b> — Liquidity, Profitability, Efficiency,
          or Leverage.</li>
      <li><b>Formula</b> — the standard calculation in plain terms.</li>
      <li><b>Numerator</b> — the accounts and balances forming the top
          of the ratio.</li>
      <li><b>Denominator</b> — the accounts and balances forming the
          bottom.</li>
      <li><b>Result</b> — the computed ratio value.</li>
      <li><b>Trend</b> — the ratio value for prior periods, showing
          the direction of change over time.</li>
      <li><b>Benchmark range</b> — where applicable, a reference range
          indicating healthy, cautionary, or concerning levels.</li>
    </ul>

    <p><b>Common ratios and what they mean:</b></p>
    <ul>
      <li><b>Current Ratio</b> (Current Assets &divide; Current
          Liabilities) — measures short-term liquidity. Above 1.0
          means the company can cover its immediate obligations.</li>
      <li><b>Debt-to-Equity</b> (Total Liabilities &divide; Equity) —
          measures financial leverage. Lower is generally safer.</li>
      <li><b>Net Profit Margin</b> (Net Profit &divide; Revenue) —
          measures how much of each franc of revenue becomes profit.</li>
      <li><b>Receivables Turnover</b> (Revenue &divide; Average
          Receivables) — measures how quickly customers are paying.</li>
    </ul>

    <p><b>Tip:</b> Ratios are most useful when tracked over multiple
    periods. A single-period ratio has limited value — the trend tells
    the real story.</p>
    """,
)

_register(
    "dialog.insight_detail",
    "Insight Detail",
    "View details behind a financial analysis insight.",
    """
    <p>The system automatically analyses your financial data each period
    and generates insights — observations about notable patterns, risks,
    or opportunities. This dialog shows the full detail behind a selected
    insight: what was detected, why it matters, and the supporting data.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Insight title</b> — a short description of the finding
          (e.g. <em>Revenue declined 15% vs. prior month</em>,
          <em>Receivables concentration risk — top customer is 60%
          of AR</em>).</li>
      <li><b>Severity</b> — colour-coded level: Informational (blue),
          Caution (amber), or Alert (red).</li>
      <li><b>Supporting data</b> — the specific account balances,
          ratios, or transaction patterns that triggered the insight.</li>
      <li><b>Context</b> — comparison against prior periods or
          benchmarks to show what changed.</li>
    </ul>

    <p><b>Examples of insights the system may generate:</b></p>
    <ul>
      <li><em>Cash position dropped below 30 days of operating
          expenses</em> — with the exact cash balance and
          average monthly expenses.</li>
      <li><em>Payables aging shifted — 40% of AP is now 60+
          days</em> — with the aging distribution breakdown.</li>
      <li><em>Gross margin improved 3 points to 42%</em> — with
          period-over-period revenue and COGS comparison.</li>
    </ul>

    <p><b>Tip:</b> Review insights as part of your month-end close
    routine. They surface patterns you might not notice by looking
    only at individual reports.</p>
    """,
)

_register(
    "dialog.report_print_preview",
    "Report Print Preview",
    "Preview a report before printing or exporting.",
    """
    <p>This dialog renders the report exactly as it will appear on paper
    or in a PDF file — with proper page breaks, headers, footers, and
    formatting.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Page layout</b> — the report formatted for your configured
          paper size (A4 by default), with company header, report title,
          date range, and page numbers.</li>
      <li><b>Data</b> — the same figures as the on-screen report,
          formatted for print legibility.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>Print</b> — send directly to a connected printer.</li>
      <li><b>Export to PDF</b> — save as a PDF file for archiving,
          email, or sharing with auditors.</li>
      <li><b>Page navigation</b> — for multi-page reports, use the
          Previous / Next controls to review each page.</li>
    </ul>

    <p><b>Tip:</b> Always preview before printing to catch layout
    issues. If columns appear truncated, try landscape orientation
    or reduce the number of displayed columns in the report
    settings.</p>
    """,
)

_register(
    "dialog.report_chart_print_preview",
    "Report Chart Print Preview",
    "Preview a chart for printing or export.",
    """
    <p>This dialog renders a chart from a report in a print-ready format
    — optimised for paper output with clean labels, high-contrast colours,
    and appropriate sizing.</p>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>Print</b> — send the chart directly to a printer.</li>
      <li><b>Export</b> — save as PDF or image (PNG) for inclusion
          in reports, presentations, or email attachments.</li>
    </ul>

    <p><b>Tip:</b> Charts exported from here are higher resolution
    than screenshots. Use the export function when preparing board
    packs or management reports that need professional-quality
    visuals.</p>
    """,
)

_register(
    "dialog.report_template_preview",
    "Report Template Preview",
    "Preview the structure of a report template.",
    """
    <p>This dialog displays the configuration of a report template —
    showing how account data is grouped, ordered, and presented in
    the final report output.</p>

    <p><b>What you'll see:</b></p>
    <ul>
      <li><b>Section hierarchy</b> — the major groupings in the report
          (e.g. Assets / Liabilities / Equity for a balance sheet, or
          Revenue / Expenses for an income statement).</li>
      <li><b>Line items</b> — the individual rows within each section,
          with their display order and formatting rules.</li>
      <li><b>Account mappings</b> — which GL accounts feed into each
          line, including sign behaviour and active status.</li>
      <li><b>Unmapped accounts</b> — any relevant accounts not yet
          assigned to a template line.</li>
    </ul>

    <p><b>Tip:</b> Review the template preview whenever you add new
    GL accounts to ensure they are captured in the correct report
    section. Missing mappings lead to incomplete financial statements.</p>
    """,
)

_register(
    "dialog.analysis_print_preview",
    "Analysis Print Preview",
    "Preview a financial analysis report for printing.",
    """
    <p>This dialog renders the complete financial analysis output in a
    print-ready format — ratios, charts, trend tables, and insights all
    laid out for paper or PDF delivery.</p>

    <p><b>What's included in the output:</b></p>
    <ul>
      <li><b>Ratio summary table</b> — all computed ratios with current
          values and trend indicators.</li>
      <li><b>Charts</b> — trend charts and composition charts rendered
          in high-resolution print-optimised format.</li>
      <li><b>Insights section</b> — automatically generated observations
          listed with severity and supporting data.</li>
      <li><b>Period context</b> — the date range and comparison periods
          used for the analysis.</li>
    </ul>

    <p><b>Actions:</b></p>
    <ul>
      <li><b>Print</b> — send to a connected printer.</li>
      <li><b>Export to PDF</b> — save for distribution to management,
          board members, or external auditors.</li>
    </ul>

    <p><b>Tip:</b> The analysis print output makes an effective
    addition to monthly management reporting packages. Export it
    alongside the balance sheet and income statement for a complete
    financial review document.</p>
    """,
)
