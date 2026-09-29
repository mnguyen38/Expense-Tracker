"""Local SQLite ledger: imported statements, transactions, and learned category rules."""

import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS statements (
    id              INTEGER PRIMARY KEY,
    file_name       TEXT NOT NULL,
    file_hash       TEXT NOT NULL UNIQUE,
    bank_name       TEXT,
    account_type    TEXT,
    currency        TEXT,
    period_start    TEXT,
    period_end      TEXT,
    month           TEXT NOT NULL,
    opening_balance REAL,
    closing_balance REAL,
    reconciled      INTEGER,
    warnings        TEXT NOT NULL DEFAULT '[]',
    imported_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY,
    statement_id    INTEGER REFERENCES statements(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,           -- 'statement' or 'email'
    source_ref      TEXT,                    -- e.g. Gmail message id, for de-duplication
    date            TEXT NOT NULL,
    month           TEXT NOT NULL,           -- budget month, YYYY-MM
    description     TEXT NOT NULL,
    amount          REAL NOT NULL,           -- negative = money out
    kind            TEXT NOT NULL,           -- expense | income | transfer | other
    is_debt_payment INTEGER NOT NULL DEFAULT 0,
    account_type    TEXT,
    category        TEXT,
    category_source TEXT,                    -- ai | rule | user
    UNIQUE (source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_transactions_month ON transactions(month);

CREATE TABLE IF NOT EXISTS rules (
    merchant_key TEXT PRIMARY KEY,
    category     TEXT NOT NULL,
    source       TEXT NOT NULL,              -- ai (learned) or user (correction)
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS names (
    merchant_key TEXT PRIMARY KEY,
    name         TEXT NOT NULL,              -- how the merchant is shown
    source       TEXT NOT NULL,              -- ai (suggested) or user (renamed)
    updated_at   TEXT NOT NULL
);
"""

# Card-network and processor noise that shouldn't distinguish merchants
_NOISE_TOKENS = {"CHECKCARD", "POS", "PURCHASE", "DEBIT", "CARD", "SQ", "TST", "PP", "PAYPAL", "RECURRING"}


def redact(description: str) -> str:
    """
    Drop account holder and reference fields before a description leaves the machine.

    "PL*PAYLEASE DES:WEB PMTS ID:LS92D8 INDN:JANE DOE CO ID:9000" -> "PL*PAYLEASE DES:WEB PMTS"
    """
    text = re.split(r"\s+INDN:", description)[0]
    text = re.sub(
        r"\b(?:CO )?ID:\S+|\bTRN:\S+|\bCONF#\S+|\bACCT\s*#?\s*\d+|\b\d{9,}\b", "", text, flags=re.IGNORECASE
    )
    return " ".join(text.split())


def merchant_key(description: str) -> str:
    """
    Normalize a transaction description to a merchant key for rule matching.

    "CHECKCARD 0305 TRADER JOE'S #552 PORTLAND OR" -> "TRADER JOE S"
    """
    tokens = re.sub(r"[^A-Z ]+", " ", description.upper()).split()
    tokens = [t for t in tokens if t not in _NOISE_TOKENS]
    return " ".join(tokens[:3])


def budget_month(day: str, close_day: int = 31) -> str:
    """
    Budget month (YYYY-MM) for a transaction date, given the statement close day.

    With close_day=11, Jan 5 -> 2026-01 but Jan 12 -> 2026-02.
    """
    d = date.fromisoformat(day[:10])
    if d.day <= close_day:
        return f"{d.year}-{d.month:02d}"
    return f"{d.year + 1}-01" if d.month == 12 else f"{d.year}-{d.month + 1:02d}"


_PREFIX = re.compile(
    r"^(?:(?:CHECKCARD|POS|PURCHASE|DEBIT|CARD|RECURRING)\s+(?:\d{4}\s+)?)+"
    r"|^(?:PP|PL|SQ|TST|SP|SUMUP|PAYPAL)\s*\*\s*|^PP\s+"
)
_KEEP_UPPER = {"USA", "AMC", "CVS", "PGE", "REI", "IKEA", "ATM", "LLC", "TJ"}
# "RENT - MAPLE COURT APARTMENTS": the payee is after the dash when the part before is generic
_GENERIC_LEAD = {
    "RENT",
    "PAYROLL",
    "DEPOSIT",
    "DIRECT",
    "PAYMENT",
    "PMT",
    "ACH",
    "AUTOPAY",
    "BILL",
    "ONLINE",
    "TRANSFER",
}


def display_name(description: str) -> str:
    """
    A readable merchant name for display.

    "CHECKCARD 0305 TRADER JOE'S #552 PORTLAND OR" -> "Trader Joe's"
    "APPLE.COM/BILL ICLOUD" -> "Apple.com"
    "RENT - MAPLE COURT APARTMENTS" -> "Maple Court Apartments"
    """
    text = description.strip().upper()
    if wire := re.match(r"WIRE TYPE:(\w+) (IN|OUT)\b", text):
        kind = "International" if wire.group(1).startswith("INTL") else "Domestic"
        return f"{kind} wire {'received' if wire.group(2) == 'IN' else 'sent'}"
    text = text.split(" DES:")[0]  # ACH: "PAYEE DES:WEB PMTS ID:... INDN:..."
    text = _PREFIX.sub("", text)
    lead, sep, rest = text.partition(" - ")
    if sep and rest and set(lead.split()) <= _GENERIC_LEAD:
        text = rest

    tokens = text.split()
    domain_at = next((i for i, t in enumerate(tokens) if i > 0 and _DOMAIN.fullmatch(t)), None)
    if domain_at is not None:
        if len(tokens[0]) >= 12 and re.search(r"\d", tokens[0]):
            # "NLOV5D9X4PRQYJZ7 WWW.OVPAY.NL": a reference code, then the merchant's site
            return _pretty(re.sub(r"^WWW\.", "", tokens[domain_at].split("/")[0]))
        # Drop the web address and anything after it ("ANTHROPIC ANTHROPIC.COMCA", "... UBER.COM CA")
        tokens = tokens[:domain_at]
    # Collapse a doubled town ("IKEA LTD BRIGHTON BRIGHTON")
    if len(tokens) > 2 and tokens[-1] == tokens[-2]:
        tokens.pop()

    # Cut at the first store number, reference or path-like suffix
    text = re.split(r"\s*[#*/]|\s+\S*\d", " ".join(tokens), maxsplit=1)[0].strip(" -.")
    return _pretty(text) if text else description.strip()


_DOMAIN = re.compile(r"(?:WWW\.)?[A-Z0-9-]+(?:\.[A-Z]{2,})+[A-Z]*(?:/\S*)?")


def _pretty(text: str) -> str:
    """Title-case words, including each part of "COMCAST-XFINITY" or "MARKS&SPENCER"."""

    def word(w: str) -> str:
        if w in _KEEP_UPPER:
            return w
        return re.sub(r"[A-Za-z][^-&]*", lambda m: m.group(0).capitalize(), w.lower())

    return " ".join(word(w) for w in text.split())


def month_label(month: str) -> str:
    """'2026-01' -> 'Jan 2026'."""
    return datetime.strptime(month, "%Y-%m").strftime("%b %Y")


def classify(txn: dict, statement_type: str | None) -> str:
    """Decide whether a transaction is spending, income, an internal transfer, or neither."""
    if txn.get("is_internal"):
        return "transfer"
    amount = txn.get("amount", 0)
    if amount < 0:
        return "expense"
    if amount > 0 and statement_type in ("checking", "savings", None):
        return "income"
    return "other"  # e.g. a payment received on a credit card


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------ imports

    def has_statement(self, file_hash: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM statements WHERE file_hash = ?", (file_hash,)).fetchone()
        return row is not None

    def delete_statement(self, file_hash: str) -> None:
        self.conn.execute("DELETE FROM statements WHERE file_hash = ?", (file_hash,))
        self.conn.commit()

    def add_statement(self, parsed: dict, file_name: str, file_hash: str, month: str) -> int:
        """Store a parsed statement (ParseResult.to_dict()) and its transactions."""
        period = parsed.get("statement_period") or (None, None)
        warnings = parsed.get("warnings", [])
        reconciled = None
        if parsed.get("opening_balance") is not None and parsed.get("closing_balance") is not None:
            reconciled = 0 if warnings else 1

        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO statements (file_name, file_hash, bank_name, account_type, currency,
                       period_start, period_end, month, opening_balance, closing_balance,
                       reconciled, warnings, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    file_name,
                    file_hash,
                    parsed.get("bank_name"),
                    parsed.get("statement_type"),
                    parsed.get("currency"),
                    period[0],
                    period[1],
                    month,
                    parsed.get("opening_balance"),
                    parsed.get("closing_balance"),
                    reconciled,
                    json.dumps(warnings),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            statement_id = cur.lastrowid
            debt_ids = {id(t) for t in parsed.get("debt_payments", [])}
            for txn in parsed.get("all_transactions", []):
                self._insert_txn(
                    txn,
                    source="statement",
                    month=month,
                    kind=classify(txn, parsed.get("statement_type")),
                    statement_id=statement_id,
                    account_type=parsed.get("statement_type"),
                    is_debt_payment=id(txn) in debt_ids,
                )
        return statement_id

    def add_email_transactions(self, txns: Iterable[dict], close_day: int = 31) -> int:
        """Store transactions from email alerts, skipping ones already imported. Returns count added."""
        added = 0
        with self.conn:
            for txn in txns:
                cur = self._insert_txn(
                    txn,
                    source="email",
                    month=budget_month(txn["date"], close_day),
                    kind=classify(txn, None),
                    source_ref=txn.get("email_id"),
                    account_type="credit_card",
                )
                added += cur.rowcount
        return added

    def _insert_txn(self, txn, *, source, month, kind, statement_id=None, source_ref=None,
                    account_type=None, is_debt_payment=False):  # fmt: skip
        return self.conn.execute(
            """INSERT OR IGNORE INTO transactions (statement_id, source, source_ref, date, month,
                   description, amount, kind, is_debt_payment, account_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                statement_id,
                source,
                source_ref,
                txn.get("date", ""),
                month,
                txn.get("description", ""),
                float(txn.get("amount", 0)),
                kind,
                int(is_debt_payment),
                account_type,
            ),
        )

    # --------------------------------------------------------------- categories

    def uncategorized_expenses(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM transactions WHERE kind = 'expense' AND category IS NULL ORDER BY date"
        ).fetchall()

    def set_category(self, txn_id: int, category: str, source: str) -> None:
        self.conn.execute(
            "UPDATE transactions SET category = ?, category_source = ? WHERE id = ?",
            (category, source, txn_id),
        )
        self.conn.commit()

    def get_transaction(self, txn_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()

    def get_rule(self, key: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM rules WHERE merchant_key = ?", (key,)).fetchone()

    def save_rule(self, key: str, category: str, source: str) -> None:
        """Remember a merchant's category. A user correction is never overwritten by the AI."""
        if not key:
            return
        existing = self.get_rule(key)
        if existing and existing["source"] == "user" and source != "user":
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO rules (merchant_key, category, source, updated_at) VALUES (?, ?, ?, ?)",
            (key, category, source, datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()

    # -------------------------------------------------------------------- names

    def names(self) -> dict[str, str]:
        """Merchant key -> display name, for merchants that have been named."""
        return {
            r["merchant_key"]: r["name"] for r in self.conn.execute("SELECT merchant_key, name FROM names")
        }

    def name_sources(self) -> dict[str, str]:
        return {
            r["merchant_key"]: r["source"]
            for r in self.conn.execute("SELECT merchant_key, source FROM names")
        }

    def save_name(self, key: str, name: str, source: str) -> bool:
        """Remember how to show a merchant. A user's rename is never overwritten by the AI."""
        name = " ".join((name or "").split())[:60]
        if not key or not name:
            return False
        existing = self.conn.execute("SELECT source FROM names WHERE merchant_key = ?", (key,)).fetchone()
        if existing and existing["source"] == "user" and source != "user":
            return False
        self.conn.execute(
            "INSERT OR REPLACE INTO names (merchant_key, name, source, updated_at) VALUES (?, ?, ?, ?)",
            (key, name, source, datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return True

    def delete_name(self, key: str) -> bool:
        cur = self.conn.execute("DELETE FROM names WHERE merchant_key = ?", (key,))
        self.conn.commit()
        return cur.rowcount > 0

    def rules(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM rules ORDER BY source DESC, merchant_key").fetchall()

    def delete_rule(self, key: str) -> bool:
        cur = self.conn.execute("DELETE FROM rules WHERE merchant_key = ?", (key,))
        self.conn.commit()
        return cur.rowcount > 0

    def recategorize_merchant(self, key: str, category: str, source: str = "user") -> int:
        """Apply a category to every expense from the same merchant that wasn't set by hand."""
        ids = [
            row["id"]
            for row in self.conn.execute(
                "SELECT id, description FROM transactions WHERE kind = 'expense' "
                "AND COALESCE(category_source, '') != 'user'"
            )
            if merchant_key(row["description"]) == key
        ]
        for txn_id in ids:
            self.set_category(txn_id, category, source)
        return len(ids)

    # ------------------------------------------------------------------ queries

    def months(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT month FROM transactions ORDER BY month").fetchall()
        return [r["month"] for r in rows]

    def transactions(
        self,
        month: str | None = None,
        kinds: tuple[str, ...] | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> list[sqlite3.Row]:
        """
        Transactions that count toward the budget.

        A month's statements are the source of truth: once one is imported, email
        alerts for that month are ignored so nothing is counted twice.
        """
        sql = """
            SELECT * FROM transactions t
            WHERE (t.source = 'statement' OR NOT EXISTS (
                SELECT 1 FROM transactions s WHERE s.source = 'statement' AND s.month = t.month))
        """
        params: list = []
        if month:
            sql += " AND t.month = ?"
            params.append(month)
        if kinds:
            sql += f" AND t.kind IN ({','.join('?' * len(kinds))})"
            params.extend(kinds)
        if category:
            sql += " AND t.category = ?"
            params.append(category)
        if search:
            sql += " AND t.description LIKE ?"
            params.append(f"%{search}%")
        sql += " ORDER BY t.date, t.id"
        return self.conn.execute(sql, params).fetchall()

    def statements(self, month: str | None = None) -> list[sqlite3.Row]:
        if month:
            return self.conn.execute(
                "SELECT * FROM statements WHERE month = ? ORDER BY id", (month,)
            ).fetchall()
        return self.conn.execute("SELECT * FROM statements ORDER BY month, id").fetchall()

    def month_summary(self, month: str) -> dict:
        """Totals for one budget month, in the shape the reports and Sheets sync use."""
        expenses = self.transactions(month, kinds=("expense",))
        income = self.transactions(month, kinds=("income",))

        by_category: dict[str, dict] = {}
        for t in expenses:
            cat = by_category.setdefault(t["category"] or "Uncategorized", {"total": 0.0, "count": 0})
            cat["total"] += abs(t["amount"])
            cat["count"] += 1
        for cat in by_category.values():
            cat["total"] = round(cat["total"], 2)

        balances = {"checking": None, "savings": None, "credit_card": None}
        for s in self.statements(month):
            if s["account_type"] in balances and s["closing_balance"] is not None:
                balances[s["account_type"]] = s["closing_balance"]

        return {
            "month": month,
            "total_spending": round(sum(abs(t["amount"]) for t in expenses), 2),
            "total_income": round(sum(t["amount"] for t in income), 2),
            "expense_count": len(expenses),
            "income_count": len(income),
            "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1]["total"])),
            "debt_payments": round(sum(abs(t["amount"]) for t in expenses if t["is_debt_payment"]), 2),
            "balances": balances,
        }
