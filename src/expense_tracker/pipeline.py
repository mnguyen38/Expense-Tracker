"""Import workflow shared by the CLI and the web app: parse, store, categorize, sync."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import Config
from .ledger import Ledger, budget_month, merchant_key
from .parsers import parse_statement


@dataclass
class ImportResult:
    file_name: str
    skipped: bool = False
    month: str = ""
    bank_name: str = ""
    statement_type: str = ""
    currency: str = "USD"
    closing_balance: float | None = None
    expense_count: int = 0
    income_count: int = 0
    transaction_count: int = 0
    reconciled: bool | None = None  # None when the statement shows no balances
    warnings: list[str] = field(default_factory=list)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_month(value: str) -> str:
    """Accept 'M/YYYY', 'MM/YYYY' or 'YYYY-MM' and return 'YYYY-MM'."""
    value = value.strip()
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", value):
        month, year = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"(\d{4})-(\d{1,2})", value):
        year, month = int(m.group(1)), int(m.group(2))
    else:
        raise ValueError(f"Invalid month '{value}'. Use M/YYYY (e.g. 1/2026) or YYYY-MM.")
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid month number in '{value}'")
    return f"{year}-{month:02d}"


def sheets_month(month: str) -> str:
    """'2026-01' -> '1/2026', the row label used by the Sheets template."""
    year, mon = month.split("-")
    return f"{int(mon)}/{year}"


def statement_month(parsed: dict, close_day: int) -> str:
    """A statement belongs to the month its period ends in (Dec 12 - Jan 11 -> January)."""
    period = parsed.get("statement_period")
    if period and period[1]:
        return period[1][:7]
    dates = [
        t["date"]
        for t in parsed.get("all_transactions", [])
        if re.match(r"\d{4}-\d{2}-\d{2}", t.get("date", ""))
    ]
    if dates:
        return budget_month(max(dates), close_day)
    return date.today().strftime("%Y-%m")


def import_statement(
    ledger: Ledger,
    config: Config,
    pdf_path: Path,
    month: str | None = None,
    force: bool = False,
) -> ImportResult:
    """Parse one PDF and store it. Re-importing the same file is a no-op unless `force`."""
    pdf_path = Path(pdf_path)
    digest = file_sha256(pdf_path)
    if ledger.has_statement(digest):
        if not force:
            return ImportResult(file_name=pdf_path.name, skipped=True)
        ledger.delete_statement(digest)

    parsed = parse_statement(pdf_path, model=config.model)
    month = normalize_month(month) if month else statement_month(parsed, config.statement_close_day)
    ledger.add_statement(parsed, pdf_path.name, digest, month)

    return ImportResult(
        file_name=pdf_path.name,
        month=month,
        bank_name=parsed.get("bank_name", ""),
        statement_type=parsed.get("statement_type", ""),
        currency=parsed.get("currency", "USD"),
        closing_balance=parsed.get("closing_balance"),
        expense_count=len(parsed.get("expenses", [])),
        income_count=len(parsed.get("income", [])),
        transaction_count=len(parsed.get("all_transactions", [])),
        reconciled=_reconciled(parsed),
        warnings=list(parsed.get("warnings", [])),
    )


def _reconciled(parsed: dict) -> bool | None:
    if parsed.get("opening_balance") is None or parsed.get("closing_balance") is None:
        return None
    return not parsed.get("warnings")


def categorize_pending(ledger: Ledger, config: Config, api_key: str | None = None) -> dict:
    """
    Categorize every uncategorized expense.

    Known merchants are resolved from saved rules for free; only new merchants go
    to Claude, one request per unique merchant, and the answers are saved as rules.
    """
    from .categorizer import categorize_transactions

    pending = ledger.uncategorized_expenses()
    stats = {"by_rule": 0, "by_ai": 0, "ai_merchants": 0}
    unknown: dict[str, list] = {}

    for row in pending:
        key = merchant_key(row["description"])
        rule = ledger.get_rule(key) if key else None
        if rule and rule["category"] in config.categories:
            ledger.set_category(row["id"], rule["category"], "rule")
            stats["by_rule"] += 1
        else:
            unknown.setdefault(key or row["description"], []).append(row)

    if not unknown:
        return stats

    samples = [
        {"description": rows[0]["description"], "amount": rows[0]["amount"]} for rows in unknown.values()
    ]
    results = categorize_transactions(
        samples, api_key=api_key, categories=config.categories, model=config.model
    )

    for rows, result in zip(unknown.values(), results, strict=True):
        for row in rows:
            ledger.set_category(row["id"], result["category"], "ai")
            stats["by_ai"] += 1
        key = merchant_key(rows[0]["description"])
        ledger.save_rule(key, result["category"], "ai")
        if result.get("merchant_name"):
            ledger.save_name(key, result["merchant_name"], "ai")
    stats["ai_merchants"] = len(unknown)
    return stats


def _google_module(name: str):
    """Import an optional Google integration, with install instructions if it's missing."""
    import importlib

    try:
        return importlib.import_module(f".{name}", __package__)
    except ImportError as e:
        raise ValueError(
            f'Google integrations aren\'t installed ({e.name} is missing). Run: pip install "expense-tracker[google]"'
        ) from e


def name_merchants(ledger: Ledger, config: Config, api_key: str | None = None, redo: bool = False) -> dict:
    """
    Give every merchant a clean display name with one batched Claude request.

    Skips merchants that already have a name (all of them with `redo`, except ones
    you renamed yourself). Returns {key: name} for the names that were saved.
    """
    from .categorizer import suggest_names

    have = ledger.name_sources()
    todo: dict[str, str] = {}
    for t in ledger.transactions():
        if t["kind"] == "transfer":
            continue
        key = merchant_key(t["description"])
        if not key or key in todo or (key in have and (not redo or have[key] == "user")):
            continue
        todo[key] = t["description"]
    if not todo:
        return {}

    names = suggest_names(list(todo.values()), api_key=api_key, model=config.model)
    saved = {}
    for key, name in zip(todo, names, strict=True):
        if name and ledger.save_name(key, name, "ai"):
            saved[key] = name
    return saved


def rename_merchant(ledger: Ledger, txn_id: int, name: str) -> tuple[str, int]:
    """
    Show a transaction's merchant under your own name, everywhere it appears.

    An empty name removes your rename. Returns (merchant key, transactions affected).
    """
    txn = ledger.get_transaction(txn_id)
    if txn is None:
        raise ValueError(f"No transaction with id {txn_id}")
    key = merchant_key(txn["description"])
    if not key:
        raise ValueError("This transaction has no merchant to rename")
    name = " ".join((name or "").split())
    if len(name) > 60:
        raise ValueError("Names can be at most 60 characters")
    if name:
        ledger.save_name(key, name, "user")
    else:
        ledger.delete_name(key)
    count = sum(1 for t in ledger.transactions() if merchant_key(t["description"]) == key)
    return key, count


def import_email_alerts(ledger: Ledger, config: Config, days: int) -> tuple[int, int]:
    """Pull Bank of America alert emails from Gmail. Returns (found, newly added)."""
    fetch_and_parse_alerts = _google_module("gmail").fetch_and_parse_alerts

    alerts = fetch_and_parse_alerts(days_back=days)
    added = ledger.add_email_transactions(alerts, close_day=config.statement_close_day)
    return len(alerts), added


def sync_month_to_sheets(ledger: Ledger, config: Config, month: str, sheet_id: str) -> dict:
    """Write one month's totals into the Google Sheets budget template (Out, In, Net Worth tabs)."""
    sheets = _google_module("sheets")

    if "docs.google.com" in sheet_id:
        sheet_id = sheets.get_spreadsheet_id_from_url(sheet_id)

    label = sheets_month(month)
    expenses = [dict(t) for t in ledger.transactions(month, kinds=("expense",))]
    income = [dict(t) for t in ledger.transactions(month, kinds=("income",))]
    summary = ledger.month_summary(month)
    result = {"month": label, "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}"}

    if expenses:
        result["out"] = sheets.sync_to_sheet(sheet_id, expenses, month=label, mode="replace")
    if income:
        result["in"] = sheets.sync_income_to_sheet(sheet_id, income, month=label, mode="replace")

    balances = summary["balances"]
    debt = [{"amount": -summary["debt_payments"]}] if summary["debt_payments"] else []
    if any(v is not None for v in balances.values()) or debt:
        result["net_worth"] = sheets.sync_net_worth_to_sheet(
            sheet_id,
            {
                "checking_balance": balances["checking"],
                "savings_balance": balances["savings"],
                "credit_card_balance": balances["credit_card"],
                "debt_payments": debt,
            },
            month=label,
        )
    return result


def recent_months(close_day: int, today: date | None = None) -> set[str]:
    """The current budget month and the previous one."""
    today = today or date.today()
    current = budget_month(today.isoformat(), close_day)
    year, month = map(int, current.split("-"))
    previous = f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"
    return {current, previous}


def send_threshold_alerts(ledger: Ledger, config: Config, month: str) -> list[float]:
    """
    Email an alert for each new spending threshold crossed this month.

    Only the current budget month and the one that just closed alert; importing
    older statements never sends mail about months that are long over.
    """
    from .notifications import check_spending_threshold

    if config.alert_threshold <= 0 or month not in recent_months(config.statement_close_day):
        return []
    total = ledger.month_summary(month)["total_spending"]
    return check_spending_threshold(
        total_spent=total,
        month=sheets_month(month),
        threshold_interval=config.alert_threshold,
        state_file=config.alerts_path,
    )
