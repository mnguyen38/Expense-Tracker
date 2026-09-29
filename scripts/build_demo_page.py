"""
Build docs/index.html: the dashboard filled with synthetic demo data, for GitHub Pages.

Usage:
    python scripts/build_demo_page.py
"""

import tempfile
from pathlib import Path

from expense_tracker.config import Config
from expense_tracker.demo import build_demo
from expense_tracker.ledger import Ledger
from expense_tracker.report import demo_banner, write_dashboard

REPO_URL = "https://github.com/mnguyen38/Expense-Tracker"
OUT = Path(__file__).resolve().parent.parent / "docs" / "index.html"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config = Config(home=Path(tmp))
        with Ledger(":memory:") as ledger:
            count = build_demo(ledger, config)
            write_dashboard(ledger, config, OUT, banner=demo_banner(REPO_URL), demo=True)
    print(f"Wrote {OUT} ({count} synthetic transactions)")


if __name__ == "__main__":
    main()
