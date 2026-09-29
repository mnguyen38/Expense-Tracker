"""Synthetic demo data, so the dashboard can be tried without an API key or real statements."""

import calendar
import random
from datetime import date

from .config import Config
from .ledger import Ledger, merchant_key
from .pipeline import categorize_pending

BANK = "Northwind Community Bank"

# (description, category, (low, high) amount, times per month)
RECURRING = [
    ("RENT - MAPLE COURT APARTMENTS", "Housing", (1650, 1650), 1),
    ("PGE ELECTRIC AUTOPAY", "Electric", (48, 96), 1),
    ("COMCAST XFINITY INTERNET", "Internet", (65, 65), 1),
    ("VERIZON WIRELESS", "Phone", (55, 55), 1),
    ("PLANET FITNESS MONTHLY", "Gym", (24.99, 24.99), 1),
    ("SPOTIFY USA", "Subscriptions", (11.99, 11.99), 1),
    ("APPLE.COM/BILL ICLOUD", "Subscriptions", (2.99, 2.99), 1),
    ("NETFLIX.COM", "Entertainment", (15.49, 15.49), 1),
]
VARIABLE = [
    ("TRADER JOE'S #552", "Groceries", (28, 95), 4),
    ("WHOLE FOODS MKT #10233", "Groceries", (35, 140), 2),
    ("CHIPOTLE 1187", "Eating Out", (11, 16), 3),
    ("BLUE BOTTLE COFFEE", "Eating Out", (5, 8), 5),
    ("SUSHI RAN", "Eating Out", (40, 110), 1),
    ("UBER *TRIP", "Rideshare", (12, 38), 3),
    ("TRIMET TICKET", "Public Transit", (2.8, 5.6), 4),
    ("CVS PHARMACY #8841", "Medical", (8, 45), 1),
    ("UNIQLO PORTLAND", "Clothing", (30, 120), 1),
    ("AMC THEATRES 2231", "Entertainment", (18, 36), 1),
    ("POWELL'S BOOKS", "Education", (15, 60), 1),
]
OCCASIONAL = [
    ("DELTA AIR LINES", "Travel", (220, 480)),
    ("AIRBNB * HM4Q2", "Travel", (310, 690)),
    ("REI #11 PORTLAND", "Clothing", (60, 210)),
    ("GREAT CLIPS", "Self Care", (22, 30)),
    ("ETSY GIFT ORDER", "Gifts", (25, 80)),
]
# Merchants seen for the first time in the latest month, as if Claude had sorted them
NEWCOMERS = [
    ("NEW SEASONS MARKET #4", "Groceries", (38, 92)),
    ("CITY BIKE REPAIR", "Misc", (35, 75)),
]
PAYROLL = ("PAYROLL DEPOSIT - ACME ROBOTICS INC", 2875.40)


def _months_back(n: int) -> list[tuple[int, int]]:
    """The last `n` complete months, oldest first."""
    today = date.today()
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    out = []
    for _ in range(n):
        out.append((y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return list(reversed(out))


def build_demo(ledger: Ledger, config: Config, months: int = 6, seed: int = 7) -> int:
    """
    Fill the ledger with `months` of demo statements. Returns transaction count.

    One month has a bonus, one a trip, one is lean, and the second-to-last
    statement is missing a transaction so the reconciliation warning shows.
    """
    rng = random.Random(seed)  # noqa: S311 - reproducible fake data, not security
    balance = 3250.00
    count = 0
    periods = _months_back(months)

    for i, (year, month) in enumerate(periods):
        prefix = f"{year}-{month:02d}"
        lean = i == 1
        # (description, amount, day of month)
        entries = [(PAYROLL[0], PAYROLL[1], 1), (PAYROLL[0], PAYROLL[1], 15)]
        if i == 2:
            entries.append(("ACME ROBOTICS INC BONUS", 1500.00, 15))
        entries += [
            ("VENMO CASHOUT", rng.uniform(20, 90), rng.randint(1, 28)) for _ in range(rng.randint(0, 2))
        ]
        for desc, _, (lo, hi), times in RECURRING:
            entries += [(desc, -rng.uniform(lo, hi), rng.randint(1, 28)) for _ in range(times)]
        for desc, _, (lo, hi), times in VARIABLE:
            n = max(0, times + rng.randint(-1, 1) - (1 if lean else 0))
            entries += [(desc, -rng.uniform(lo, hi), rng.randint(1, 28)) for _ in range(n)]
        if i == len(periods) - 1:
            entries += [(desc, -rng.uniform(lo, hi), rng.randint(1, 28)) for desc, _, (lo, hi) in NEWCOMERS]
        trips = OCCASIONAL[:2] if i == 4 else rng.sample(OCCASIONAL[2:], 0 if lean else rng.randint(0, 2))
        entries += [(desc, -rng.uniform(lo, hi), rng.randint(1, 28)) for desc, _, (lo, hi) in trips]

        txns = [
            {"date": f"{prefix}-{day:02d}", "description": desc, "amount": round(amount, 2)}
            for desc, amount, day in entries
        ]
        txns.append(
            {
                "date": f"{prefix}-20",
                "description": "TRANSFER TO SAVINGS",
                "amount": -400.0,
                "is_internal": True,
            }
        )
        txns.sort(key=lambda t: t["date"])

        opening = balance
        balance = round(opening + sum(t["amount"] for t in txns), 2)
        warnings = []
        if i == len(periods) - 2:
            # Simulate a line the parser couldn't read
            missing = next(t for t in txns if t["description"].startswith("WHOLE FOODS"))
            txns.remove(missing)
            warnings.append(
                f"Balances do not reconcile: off by {missing['amount']:,.2f}. "
                "Some transactions may be missing or misread."
            )

        parsed = {
            "bank_name": BANK,
            "statement_type": "checking",
            "currency": "USD",
            "statement_period": (f"{prefix}-01", f"{prefix}-{calendar.monthrange(year, month)[1]:02d}"),
            "opening_balance": opening,
            "closing_balance": balance,
            "all_transactions": txns,
            "debt_payments": [],
            "warnings": warnings,
        }
        ledger.add_statement(parsed, f"northwind-{prefix}.pdf", f"demo-{prefix}", prefix)
        count += len(txns)

    # Teach the demo merchants' categories so categorization needs no API call
    for desc, category, *_ in RECURRING + VARIABLE + OCCASIONAL:
        ledger.save_rule(merchant_key(desc), category, "ai")
    for t in ledger.uncategorized_expenses():
        for desc, category, _ in NEWCOMERS:
            if merchant_key(t["description"]) == merchant_key(desc):
                ledger.set_category(t["id"], category, "ai")
                ledger.save_rule(merchant_key(desc), category, "ai")
    categorize_pending(ledger, config)
    return count
