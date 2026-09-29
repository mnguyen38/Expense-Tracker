"""Command-line interface: `expense-tracker <command>`."""

import argparse
import csv
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__
from .config import Config, load_config
from .ledger import Ledger, merchant_key, month_label
from .pipeline import (
    categorize_pending,
    import_email_alerts,
    import_statement,
    name_merchants,
    normalize_month,
    rename_merchant,
    send_threshold_alerts,
    sync_month_to_sheets,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    # Windows consoles default to a legacy code page; don't crash on merchant names
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    if args.home:
        # Modules that locate credentials read this too
        os.environ["EXPENSE_TRACKER_HOME"] = str(Path(args.home).resolve())

    try:
        config = load_config()
        return args.func(args, config) or 0
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            raise
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="expense-tracker",
        description="Import bank statement PDFs, categorize spending with Claude, and see where your money goes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--home", metavar="DIR", help="data directory (default: ~/.expense-tracker or $EXPENSE_TRACKER_HOME)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show full tracebacks on errors")
    sub = parser.add_subparsers(title="commands", metavar="<command>")

    p = sub.add_parser("init", help="create the data directory and a config file you can edit")
    p.add_argument("--force", action="store_true", help="overwrite an existing config.toml")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("demo", help="try it with six months of synthetic data (no API key needed)")
    p.add_argument("--serve", action="store_true", help="open the web app instead of a static report")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("import", help="import statement PDFs (files or folders)")
    p.add_argument("paths", nargs="+", help="PDF files or folders of PDFs")
    p.add_argument(
        "-m", "--month", help="budget month for these statements, e.g. 1/2026 (default: statement end date)"
    )
    p.add_argument("--force", action="store_true", help="re-import files that were already imported")
    p.add_argument("--sheets", action="store_true", help="also sync the affected months to Google Sheets")
    p.add_argument("--no-alerts", action="store_true", help="don't send spending threshold emails")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("summary", help="print a month's spending summary")
    p.add_argument("-m", "--month", help="month, e.g. 1/2026 (default: latest)")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("report", help="write the monthly report as one HTML file")
    p.add_argument("-o", "--output", help="output file (default: <home>/dashboard.html)")
    p.add_argument("--open", action="store_true", help="open it in your browser")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("serve", help="run the local web app (upload statements, edit categories)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("transactions", aliases=["txns"], help="list transactions with their ids")
    p.add_argument("-m", "--month", help="month, e.g. 1/2026 (default: latest)")
    p.add_argument("-c", "--category", help="only this category")
    p.add_argument("-s", "--search", help="description contains this text")
    p.set_defaults(func=cmd_transactions)

    p = sub.add_parser("categorize", help="fix a transaction's category; the merchant is remembered")
    p.add_argument("id", type=int, help="transaction id (see `transactions`)")
    p.add_argument("category", help="new category name")
    p.add_argument(
        "--only-this", action="store_true", help="don't apply to other transactions or learn a rule"
    )
    p.set_defaults(func=cmd_categorize)

    p = sub.add_parser("names", help="have Claude give every merchant a clean display name")
    p.add_argument(
        "--redo", action="store_true", help="rename merchants Claude already named (never your own renames)"
    )
    p.set_defaults(func=cmd_names)

    p = sub.add_parser("rename", help="show a merchant under your own name")
    p.add_argument("id", type=int, help="any transaction id from that merchant (see `transactions`)")
    p.add_argument("name", nargs="?", default="", help="the name to show; leave out to undo your rename")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("rules", help="list learned merchant -> category rules")
    p.add_argument("--delete", metavar="MERCHANT", help="forget the rule for this merchant key")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("export", help="export transactions as CSV or JSON")
    p.add_argument("-m", "--month", help="only this month")
    p.add_argument("-f", "--format", choices=["csv", "json"], default="csv")
    p.add_argument("-o", "--output", help="output file (default: stdout)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("sync-sheets", help="write a month into the Google Sheets budget template")
    p.add_argument("-m", "--month", help="month, e.g. 1/2026 (default: latest)")
    p.add_argument("--sheet", help="sheet ID or URL (default: sheets_id in config)")
    p.set_defaults(func=cmd_sync_sheets)

    p = sub.add_parser("gmail", help="import Bank of America alert emails from Gmail")
    p.add_argument("-d", "--days", type=int, default=7, help="days to look back (default: 7)")
    p.add_argument("--sheets", action="store_true", help="also sync the affected months to Google Sheets")
    p.set_defaults(func=cmd_gmail)

    p = sub.add_parser("email-summary", help="email an HTML spending summary to NOTIFY_EMAIL")
    p.add_argument("-m", "--month", help="month, e.g. 1/2026 (default: latest)")
    p.set_defaults(func=cmd_email_summary)

    return parser


# ---------------------------------------------------------------------- commands


def cmd_init(args, config: Config) -> int:
    if config.config_path.exists() and not args.force:
        print(f"Config already exists: {config.config_path} (use --force to overwrite)")
    else:
        print(f"Wrote {config.write()}")
    Ledger(config.db_path).close()
    print(f"Ledger:  {config.db_path}")
    print(f"\nNext: add ANTHROPIC_API_KEY=... to {config.home / '.env'} (or your environment), then run")
    print("  expense-tracker import statement.pdf")
    print("Or look around first with sample data: expense-tracker demo")
    return 0


def cmd_demo(args, config: Config) -> int:
    import shutil
    import tempfile

    from .demo import build_demo
    from .report import write_dashboard

    # Never mix demo data into the real ledger
    home = Path(tempfile.gettempdir()) / "expense-tracker-demo"
    shutil.rmtree(home, ignore_errors=True)
    demo_config = Config(home=home, categories=config.categories, currency_symbol=config.currency_symbol)
    with Ledger(demo_config.db_path) as ledger:
        count = build_demo(ledger, demo_config)
    print(f"Created a demo ledger with {count} synthetic transactions in {home}")

    if args.serve:
        from .web import serve

        serve(demo_config, port=args.port, demo=True)
        return 0
    with Ledger(demo_config.db_path) as ledger:
        path = write_dashboard(ledger, demo_config, demo=True)
    print(f"Opening {path}")
    webbrowser.open(path.resolve().as_uri())
    return 0


def cmd_import(args, config: Config) -> int:
    pdfs = _collect_pdfs(args.paths)
    months: set[str] = set()
    failed = 0

    with Ledger(config.db_path) as ledger:
        for pdf in pdfs:
            print(f"Importing {pdf.name} ...", end="", flush=True)
            started = time.monotonic()
            try:
                result = import_statement(ledger, config, pdf, month=args.month, force=args.force)
                print(f" done in {time.monotonic() - started:.0f}s")
            except Exception as e:  # keep going with the other files
                failed += 1
                print(f"\n  Error: {e}")
                if args.verbose:
                    raise
                continue
            if result.skipped:
                print("  Already imported (use --force to re-import)")
                continue
            months.add(result.month)
            print(
                f"  {result.bank_name} | {result.statement_type.replace('_', ' ')} | {month_label(result.month)}"
            )
            print(
                f"  {_plural(result.transaction_count, 'transaction')}: "
                f"{_plural(result.expense_count, 'expense')}, {result.income_count} income"
            )
            if result.reconciled:
                print(f"  {_mark(True)} Balances reconcile: every transaction is accounted for")
            elif result.reconciled is None:
                print("  - No opening/closing balance on this statement, so it couldn't be checked")
            for warning in result.warnings:
                print(f"  {_mark(False)} {warning}")

        _categorize(ledger, config)
        _name_new_merchants(ledger, config)

        for month in sorted(months):
            print()
            _print_summary(ledger, config, month)
            if not args.no_alerts:
                for threshold in send_threshold_alerts(ledger, config, month):
                    print(f"  Alert emailed: spending passed {config.currency_symbol}{threshold:,.0f}")
            if args.sheets:
                _sync(ledger, config, month, config.sheets_id)

    if months:
        print("\nExplore it: expense-tracker serve   (or `expense-tracker report --open` for a static page)")
    return 1 if failed and not months else 0


def cmd_summary(args, config: Config) -> int:
    with Ledger(config.db_path) as ledger:
        month = _resolve_month(ledger, args.month)
        _print_summary(ledger, config, month)
    return 0


def cmd_report(args, config: Config) -> int:
    from .report import write_dashboard

    with Ledger(config.db_path) as ledger:
        path = write_dashboard(ledger, config, Path(args.output) if args.output else None)
    print(f"Report written to {path}")
    if args.open:
        webbrowser.open(path.resolve().as_uri())
    return 0


def cmd_serve(args, config: Config) -> int:
    from .web import serve

    serve(config, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_transactions(args, config: Config) -> int:
    with Ledger(config.db_path) as ledger:
        month = _resolve_month(ledger, args.month)
        rows = ledger.transactions(month, category=args.category, search=args.search)
        sym = config.currency_symbol
        print(f"{'ID':>5}  {'Date':10}  {'Amount':>11}  {'Category':16}  Description")
        for t in rows:
            if t["kind"] == "transfer":
                continue
            category = t["category"] or ("(income)" if t["kind"] == "income" else "")
            amount = f"{'-' if t['amount'] < 0 else ''}{sym}{abs(t['amount']):,.2f}"
            print(f"{t['id']:>5}  {t['date']:10}  {amount:>11}  {category[:16]:16}  {t['description']}")
    return 0


def cmd_categorize(args, config: Config) -> int:
    category = _match_category(args.category, config)
    with Ledger(config.db_path) as ledger:
        txn = ledger.get_transaction(args.id)
        if txn is None:
            raise ValueError(f"No transaction with id {args.id}")
        ledger.set_category(args.id, category, "user")
        print(f"#{args.id} {txn['description']} -> {category}")
        if not args.only_this:
            key = merchant_key(txn["description"])
            ledger.save_rule(key, category, "user")
            others = ledger.recategorize_merchant(key, category)
            print(f"Rule saved: {key} -> {category}" + (f" (updated {others} more)" if others else ""))
    return 0


def cmd_names(args, config: Config) -> int:
    with Ledger(config.db_path) as ledger:
        print("Asking Claude for clean merchant names...")
        saved = name_merchants(ledger, config, redo=args.redo)
    if not saved:
        print("Every merchant already has a name.")
        return 0
    print(f"Named {_plural(len(saved), 'merchant')}, e.g.:")
    for name in list(saved.values())[:8]:
        print(f"  {name}")
    return 0


def cmd_rename(args, config: Config) -> int:
    with Ledger(config.db_path) as ledger:
        _, count = rename_merchant(ledger, args.id, args.name)
    what = f"shown as {args.name!r}" if args.name.strip() else "back to its automatic name"
    print(f"Merchant {what} ({_plural(count, 'transaction')})")
    return 0


def cmd_rules(args, config: Config) -> int:
    with Ledger(config.db_path) as ledger:
        if args.delete:
            found = ledger.delete_rule(args.delete.upper())
            print("Deleted." if found else f"No rule for '{args.delete}'.")
            return 0 if found else 1
        rows = ledger.rules()
        if not rows:
            print("No rules yet. They are learned as statements are categorized.")
        for r in rows:
            print(
                f"{r['merchant_key']:32}  {r['category']:16}  ({'your correction' if r['source'] == 'user' else 'learned'})"
            )
    return 0


def cmd_export(args, config: Config) -> int:
    fields = ["id", "date", "month", "description", "amount", "kind", "category", "category_source", "source"]
    with Ledger(config.db_path) as ledger:
        month = normalize_month(args.month) if args.month else None
        rows = [{f: t[f] for f in fields} for t in ledger.transactions(month)]

    out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout  # noqa: SIM115
    try:
        if args.format == "json":
            json.dump(rows, out, indent=2)
            out.write("\n")
        else:
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    finally:
        if args.output:
            out.close()
            print(f"Exported {len(rows)} transactions to {args.output}", file=sys.stderr)
    return 0


def cmd_sync_sheets(args, config: Config) -> int:
    sheet_id = args.sheet or config.sheets_id
    if not sheet_id:
        raise ValueError("No sheet given. Pass --sheet or set sheets_id in config.toml.")
    with Ledger(config.db_path) as ledger:
        _sync(ledger, config, _resolve_month(ledger, args.month), sheet_id)
    return 0


def cmd_gmail(args, config: Config) -> int:
    with Ledger(config.db_path) as ledger:
        print(f"Checking Gmail for alerts from the last {args.days} days...")
        found, added = import_email_alerts(ledger, config, args.days)
        print(f"{found} alerts found, {added} new")
        if added:
            _categorize(ledger, config)
        if args.sheets and added:
            _sync(ledger, config, _resolve_month(ledger, None), config.sheets_id)
    return 0


def cmd_email_summary(args, config: Config) -> int:
    from .notifications import send_spending_summary

    notify_email = os.environ.get("NOTIFY_EMAIL")
    if not notify_email:
        raise ValueError("Set NOTIFY_EMAIL (and SMTP_EMAIL, SMTP_PASSWORD) in .env first.")
    with Ledger(config.db_path) as ledger:
        month = _resolve_month(ledger, args.month)
        s = ledger.month_summary(month)
        sent = send_spending_summary(
            to_email=notify_email,
            month=month_label(month),
            total_spent=s["total_spending"],
            by_category={c: d["total"] for c, d in s["by_category"].items()},
            transactions=[dict(t) for t in ledger.transactions(month, kinds=("expense",))],
            total_income=s["total_income"],
        )
    print(f"Summary {'sent to ' + notify_email if sent else 'failed to send'}")
    return 0 if sent else 1


# ----------------------------------------------------------------------- helpers


def _collect_pdfs(paths: list[str]) -> list[Path]:
    pdfs: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            pdfs.extend(sorted(p for p in path.rglob("*") if p.suffix.lower() == ".pdf"))
        elif path.is_file():
            pdfs.append(path)
        else:
            raise FileNotFoundError(f"Not found: {path}")
    if not pdfs:
        raise FileNotFoundError("No PDF files found")
    return pdfs


def _resolve_month(ledger: Ledger, month: str | None) -> str:
    if month:
        return normalize_month(month)
    months = ledger.months()
    if not months:
        raise ValueError(
            "The ledger is empty. Import a statement first: expense-tracker import statement.pdf"
        )
    return months[-1]


def _match_category(name: str, config: Config) -> str:
    for category in config.categories:
        if category.lower() == name.lower():
            return category
    raise ValueError(f"Unknown category '{name}'. Choose from: {', '.join(config.categories)}")


def _categorize(ledger: Ledger, config: Config) -> None:
    pending = len(ledger.uncategorized_expenses())
    if not pending:
        return
    print(f"\nCategorizing {pending} expenses...")
    stats = categorize_pending(ledger, config)
    print(
        f"  {stats['by_rule']} from saved rules, {stats['by_ai']} by Claude ({stats['ai_merchants']} new merchants)"
    )


def _name_new_merchants(ledger: Ledger, config: Config) -> None:
    """Name merchants that categorizing didn't (income, card payments); skipped without an API key."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        saved = name_merchants(ledger, config)
    except Exception as e:  # naming is a nicety; never fail an import over it
        print(f"  (Couldn't name new merchants: {e})")
        return
    if saved:
        print(f"  Named {_plural(len(saved), 'new merchant')}")


def _sync(ledger: Ledger, config: Config, month: str, sheet_id: str) -> None:
    if not sheet_id:
        print("  Skipping Google Sheets: set sheets_id in config.toml")
        return
    print(f"Syncing {month_label(month)} to Google Sheets...")
    result = sync_month_to_sheets(ledger, config, month, sheet_id)
    parts = [name for name in ("out", "in", "net_worth") if name in result]
    print(f"  Updated {', '.join(parts) or 'nothing'}: {result['spreadsheet_url']}")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _mark(ok: bool) -> str:
    """A check or warning marker, falling back to ASCII on consoles that can't show symbols."""
    symbol = "\u2713" if ok else "\u26a0"
    try:
        symbol.encode(sys.stdout.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        return "OK" if ok else "WARNING:"
    return symbol


def _print_summary(ledger: Ledger, config: Config, month: str) -> None:
    s = ledger.month_summary(month)
    sym = config.currency_symbol
    print("=" * 50)
    print(f"{month_label(month).upper()} SUMMARY")
    print("=" * 50)
    print(f"Total Spending: {sym}{s['total_spending']:,.2f}")
    print(f"Total Income:   {sym}{s['total_income']:,.2f}")
    net = s["total_income"] - s["total_spending"]
    print(f"Net:            {'+' if net >= 0 else '-'}{sym}{abs(net):,.2f}")
    if s["by_category"]:
        print("\nBy Category:")
        print("-" * 50)
        for category, data in s["by_category"].items():
            print(f"  {category:20} {sym}{data['total']:>10,.2f}  ({_plural(data['count'], 'transaction')})")
    balances = {k: v for k, v in s["balances"].items() if v is not None}
    if balances:
        print("\nBalances:")
        for account, value in balances.items():
            print(f"  {account.replace('_', ' ').title():12} {sym}{value:>10,.2f}")
    for st in ledger.statements(month):
        if st["reconciled"] == 0:
            print(
                f"\n  {_mark(False)} {st['file_name']} doesn't reconcile; some transactions may be missing."
            )


if __name__ == "__main__":
    sys.exit(main())
