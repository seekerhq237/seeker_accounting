"""
CLI dispatcher for the Seeker Accounting License Manager.

Usage:
    python -m tools.license_manager <command> [options]

Commands:
    init-keys       Generate Ed25519 signing keypair (one-time setup)
    issue           Issue a new signed license key
    list            List all issued licenses
    show <id>       Show details for a specific license
    revoke <id>     Mark a license as revoked
    note <id>       Update the notes on a license
    export <id>     Export a license key to a .lic file
    verify <key>    Verify a license key against the public key
    stats           Show summary statistics

Run any command with --help for details.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROG = "python -m tools.license_manager"
import sys as _sys
# When frozen (PyInstaller EXE), use a 'keys/' folder next to the EXE.
# When running from source, anchor to the project root.
if getattr(_sys, 'frozen', False):
    _DEFAULT_KEYS_DIR = Path(_sys.executable).resolve().parent / "keys"
else:
    # tools/license_manager/ -> tools/ -> project root
    _DEFAULT_KEYS_DIR = Path(__file__).resolve().parent.parent.parent / "keys"


def _resolve_keys_dir(args: argparse.Namespace) -> Path:
    return Path(args.keys_dir).resolve()


# ══════════════════════════════════════════════════════════════════════════════
#  Command implementations
# ══════════════════════════════════════════════════════════════════════════════

def _cmd_init_keys(args: argparse.Namespace) -> int:
    from .crypto import generate_keypair

    keys_dir = _resolve_keys_dir(args)
    print(f"\n  Generating Ed25519 keypair in {keys_dir}/\n")

    try:
        result = generate_keypair(keys_dir)
    except FileExistsError as exc:
        print(f"  ERROR: {exc}")
        return 1

    print(f"  Private key : {result.private_key}")
    print(f"  Public key  : {result.public_key}")
    print()
    print(f"  Public key hex (embed in key_validator.py):")
    print(f"    {result.public_key_hex}")
    print()
    print("  IMPORTANT: Keep the private key file secure and offline.")
    print("             It must never be shipped with the application.")
    print()
    return 0


def _cmd_issue(args: argparse.Namespace) -> int:
    from .crypto import sign_license
    from .formatter import format_issued_key
    from .ledger import LedgerStore

    keys_dir = _resolve_keys_dir(args)
    private_key_path = keys_dir / "seeker_license_private.pem"

    if not private_key_path.exists():
        print(f"\n  ERROR: Private key not found at {private_key_path}")
        print(f"  Run:   {_PROG} init-keys")
        return 1

    customer: str = args.customer or ""
    email: str = args.email or ""
    expiry_days: int = args.expiry_days
    edition: int = args.edition
    notes: str = args.notes or ""

    if not customer and not args.no_prompt:
        customer = input("  Customer name: ").strip()
    if not email and not args.no_prompt:
        email = input("  Customer email: ").strip()

    try:
        key_string, issued_date, expires_date = sign_license(
            private_key_path=private_key_path,
            expiry_days=expiry_days,
            edition=edition,
        )
    except Exception as exc:
        print(f"\n  ERROR: Failed to sign license: {exc}")
        return 1

    ledger = LedgerStore(keys_dir)
    record = ledger.add(
        key=key_string,
        customer=customer,
        email=email,
        edition=edition,
        issued_at=issued_date,
        expires_at=expires_date,
        notes=notes,
    )

    print(format_issued_key(record))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    from .formatter import format_table
    from .ledger import LedgerStore

    keys_dir = _resolve_keys_dir(args)
    ledger = LedgerStore(keys_dir)

    if args.query:
        records = ledger.search(args.query)
        print(f"\n  Search: \"{args.query}\"\n")
    elif args.active:
        records = ledger.active_records()
        print("\n  Filter: active only\n")
    else:
        records = ledger.all_records()
        print()

    print(format_table(records))
    print()
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    from .formatter import format_detail
    from .ledger import LedgerStore

    keys_dir = _resolve_keys_dir(args)
    ledger = LedgerStore(keys_dir)
    record = ledger.get_by_id(args.id)

    if record is None:
        print(f"\n  ERROR: License #{args.id} not found.\n")
        return 1

    print(format_detail(record))
    return 0


def _cmd_revoke(args: argparse.Namespace) -> int:
    from .ledger import LedgerStore

    keys_dir = _resolve_keys_dir(args)
    ledger = LedgerStore(keys_dir)

    try:
        record = ledger.revoke(args.id)
    except (KeyError, ValueError) as exc:
        print(f"\n  ERROR: {exc}\n")
        return 1

    print(f"\n  License #{record.id} has been marked as REVOKED.")
    print(f"  Customer : {record.customer or '—'}")
    print(f"  Revoked  : {record.revoked_at}")
    print()
    print("  Note: Revocation is a ledger-only record. The key will still")
    print("  work in offline validation unless the public key is rotated.")
    print()
    return 0


def _cmd_note(args: argparse.Namespace) -> int:
    from .ledger import LedgerStore

    keys_dir = _resolve_keys_dir(args)
    ledger = LedgerStore(keys_dir)

    notes_text: str = args.text
    if not notes_text:
        notes_text = input("  Enter notes: ").strip()

    try:
        record = ledger.update_notes(args.id, notes_text)
    except KeyError as exc:
        print(f"\n  ERROR: {exc}\n")
        return 1

    print(f"\n  License #{record.id} notes updated.\n")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from .ledger import LedgerStore

    keys_dir = _resolve_keys_dir(args)
    ledger = LedgerStore(keys_dir)
    record = ledger.get_by_id(args.id)

    if record is None:
        print(f"\n  ERROR: License #{args.id} not found.\n")
        return 1

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        safe_customer = "".join(
            c if c.isalnum() or c in "-_ " else "" for c in (record.customer or "license")
        ).strip().replace(" ", "_") or "license"
        filename = f"seeker_license_{record.id}_{safe_customer}.lic"
        out_path = Path.cwd() / filename

    out_path.write_text(record.key + "\n", encoding="utf-8")

    print(f"\n  Exported license #{record.id} to:")
    print(f"    {out_path}")
    print(f"\n  Customer : {record.customer or '—'}")
    print(f"  Expires  : {record.expires_at}")
    print()
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from .crypto import verify_license
    from .formatter import format_verification

    keys_dir = _resolve_keys_dir(args)
    public_key_path = keys_dir / "seeker_license_public.pem"

    if not public_key_path.exists():
        print(f"\n  ERROR: Public key not found at {public_key_path}")
        return 1

    key_string: str = args.key
    if not key_string:
        key_string = input("  Paste the license key: ").strip()
    if not key_string:
        print("\n  ERROR: No key provided.\n")
        return 1

    try:
        payload = verify_license(key_string, public_key_path)
    except ValueError as exc:
        print(f"\n  ✗ Verification FAILED: {exc}\n")
        return 1

    print(format_verification(
        key_string=key_string,
        edition=payload.edition,
        issued_at=payload.issued_at,
        expires_at=payload.expires_at,
    ))
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    import datetime

    from .ledger import LedgerStore

    keys_dir = _resolve_keys_dir(args)
    ledger = LedgerStore(keys_dir)
    records = ledger.all_records()

    if not records:
        print("\n  No licenses have been issued yet.\n")
        return 0

    today = datetime.date.today()
    total = len(records)
    active = sum(1 for r in records if r.status == "active")
    revoked = sum(1 for r in records if r.status == "revoked")
    expired = sum(
        1 for r in records
        if r.status == "active"
        and datetime.date.fromisoformat(r.expires_at) < today
    )
    valid = active - expired

    print()
    print("  License Ledger Statistics")
    print("  ─────────────────────────")
    print(f"  Total issued   : {total}")
    print(f"  Active (valid) : {valid}")
    print(f"  Active (expired): {expired}")
    print(f"  Revoked        : {revoked}")
    print(f"  Ledger file    : {ledger.path}")
    print()
    return 0


# ══════════════════════════════════════════════════════════════════════════════
#  Argument parser
# ══════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Seeker Accounting — License Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            f"  {_PROG} init-keys\n"
            f"  {_PROG} issue --customer \"Acme Corp\" --email admin@acme.com\n"
            f"  {_PROG} issue --customer \"Beta Ltd\" --expiry-days 90\n"
            f"  {_PROG} list\n"
            f"  {_PROG} list --active\n"
            f"  {_PROG} list --search acme\n"
            f"  {_PROG} show 1\n"
            f"  {_PROG} export 1\n"
            f"  {_PROG} export 1 --output ./delivery/client.lic\n"
            f"  {_PROG} revoke 3\n"
            f"  {_PROG} verify SEEKER-...\n"
            f"  {_PROG} stats\n"
        ),
    )
    parser.add_argument(
        "--keys-dir",
        default=str(_DEFAULT_KEYS_DIR),
        help=f"Directory for keys and ledger (default: {_DEFAULT_KEYS_DIR})",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── init-keys ─────────────────────────────────────────────────────
    sub.add_parser(
        "init-keys",
        help="Generate Ed25519 signing keypair (one-time setup)",
    )

    # ── issue ─────────────────────────────────────────────────────────
    p_issue = sub.add_parser(
        "issue",
        help="Issue a new signed license key",
    )
    p_issue.add_argument("--customer", "-c", default="", help="Customer or company name")
    p_issue.add_argument("--email", "-e", default="", help="Customer email address")
    p_issue.add_argument("--expiry-days", "-d", type=int, default=365, help="Days until expiry (default: 365)")
    p_issue.add_argument("--edition", type=int, default=1, help="Edition byte (default: 1 = standard)")
    p_issue.add_argument("--notes", "-n", default="", help="Optional notes")
    p_issue.add_argument("--no-prompt", action="store_true", help="Skip interactive prompts")

    # ── list ──────────────────────────────────────────────────────────
    p_list = sub.add_parser(
        "list",
        help="List all issued licenses",
    )
    p_list.add_argument("--active", action="store_true", help="Show only active licenses")
    p_list.add_argument("--search", "-s", dest="query", default="", help="Search by customer, email, or notes")

    # ── show ──────────────────────────────────────────────────────────
    p_show = sub.add_parser(
        "show",
        help="Show details for a specific license",
    )
    p_show.add_argument("id", type=int, help="License ID")

    # ── revoke ────────────────────────────────────────────────────────
    p_revoke = sub.add_parser(
        "revoke",
        help="Mark a license as revoked in the ledger",
    )
    p_revoke.add_argument("id", type=int, help="License ID to revoke")

    # ── note ──────────────────────────────────────────────────────────
    p_note = sub.add_parser(
        "note",
        help="Update the notes on a license",
    )
    p_note.add_argument("id", type=int, help="License ID")
    p_note.add_argument("text", nargs="?", default="", help="New notes text")

    # ── export ────────────────────────────────────────────────────────
    p_export = sub.add_parser(
        "export",
        help="Export a license key to a .lic file",
    )
    p_export.add_argument("id", type=int, help="License ID to export")
    p_export.add_argument("--output", "-o", default="", help="Output file path (default: auto-named in cwd)")

    # ── verify ────────────────────────────────────────────────────────
    p_verify = sub.add_parser(
        "verify",
        help="Verify a license key against the public key",
    )
    p_verify.add_argument("key", nargs="?", default="", help="License key string (prompted if omitted)")

    # ── stats ─────────────────────────────────────────────────────────
    sub.add_parser(
        "stats",
        help="Show summary statistics",
    )

    return parser


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

_DISPATCH = {
    "init-keys": _cmd_init_keys,
    "issue": _cmd_issue,
    "list": _cmd_list,
    "show": _cmd_show,
    "revoke": _cmd_revoke,
    "note": _cmd_note,
    "export": _cmd_export,
    "verify": _cmd_verify,
    "stats": _cmd_stats,
}


def _run_one(parser: argparse.ArgumentParser, argv: list[str]) -> int:
    """Parse *argv* and dispatch a single command.  Returns exit code."""
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        # argparse calls sys.exit on --help or parse errors — absorb it
        return 0

    if not args.command:
        parser.print_help()
        return 0

    handler = _DISPATCH.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\n  Cancelled.\n")
        return 130
    except Exception as exc:
        print(f"\n  UNEXPECTED ERROR: {exc}\n")
        return 1


_INTERACTIVE_BANNER = r"""
  ╔══════════════════════════════════════════════════════════╗
  ║         Seeker Accounting — License Manager              ║
  ╚══════════════════════════════════════════════════════════╝

  Commands:
    init-keys                  Generate signing keypair
    issue                      Issue a new license key
    list [--active] [--search] List licenses
    show <id>                  Show license details
    revoke <id>                Revoke a license
    note <id> [text]           Update notes
    export <id> [-o path]      Export key to .lic file
    verify [key]               Verify a license key
    stats                      Summary statistics

  Type 'help' for full help, 'exit' to quit.
"""


def _interactive(parser: argparse.ArgumentParser) -> None:
    """REPL loop for interactive (double-click) usage."""
    import shlex

    print(_INTERACTIVE_BANNER)

    while True:
        try:
            line = input("  license-mgr> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        lower = line.lower()
        if lower in ("exit", "quit", "q"):
            break
        if lower in ("help", "?"):
            parser.print_help()
            print()
            continue

        try:
            argv = shlex.split(line)
        except ValueError as exc:
            print(f"  Parse error: {exc}\n")
            continue

        _run_one(parser, argv)
        print()

    print("\n  Goodbye.\n")


def main() -> None:
    parser = _build_parser()

    # No CLI args → interactive mode (e.g. double-clicked the exe)
    if len(sys.argv) <= 1:
        _interactive(parser)
        return

    exit_code = _run_one(parser, sys.argv[1:])
    sys.exit(exit_code)
