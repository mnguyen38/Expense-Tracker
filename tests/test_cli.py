"""CLI tests: real PDFs through the whole app, with Claude stubbed out."""

import csv
import io
import json
from unittest.mock import patch

import pytest

fpdf = pytest.importorskip("fpdf")

from expense_tracker.cli import main  # noqa: E402
from expense_tracker.config import load_config  # noqa: E402
from expense_tracker.ledger import Ledger  # noqa: E402

from .test_integration import BOA_CHECKING_LINES, _write_pdf  # noqa: E402

CATEGORY_FOR = {"TRADER": "Groceries", "LOAN": "Housing"}


def fake_categorize(transactions, **kwargs):
    fake_categorize.calls += 1
    out = []
    for t in transactions:
        category = next((c for k, c in CATEGORY_FOR.items() if k in t["description"]), "Misc")
        out.append({**t, "category": category})
    return out


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPENSE_TRACKER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_categorize.calls = 0
    with patch("expense_tracker.categorizer.categorize_transactions", fake_categorize):
        yield tmp_path / "home"


@pytest.fixture
def pdf(tmp_path):
    return _write_pdf(tmp_path / "march.pdf", BOA_CHECKING_LINES)


def run(*argv) -> int:
    return main(list(argv))


def test_init_writes_editable_config(home, capsys):
    assert run("init") == 0
    assert (home / "config.toml").exists()
    assert (home / "ledger.db").exists()
    assert run("init") == 0
    assert "already exists" in capsys.readouterr().out


def test_import_summary_and_idempotency(home, pdf, capsys):
    assert run("import", str(pdf), "--no-alerts") == 0
    out = capsys.readouterr().out
    assert "Bank of America | checking | Mar 2026" in out
    assert "Balances reconcile" in out
    assert "Total Spending: $161.45" in out
    assert "Groceries" in out

    assert run("import", str(pdf)) == 0
    assert "Already imported" in capsys.readouterr().out

    with Ledger(home / "ledger.db") as ledger:
        assert len(ledger.transactions()) == 4


def test_known_merchants_skip_the_ai(home, pdf, capsys):
    run("import", str(pdf), "--no-alerts")
    assert fake_categorize.calls == 1
    run("import", str(pdf), "--force", "--no-alerts")
    assert fake_categorize.calls == 1  # every merchant came from a saved rule
    assert "2 from saved rules, 0 by Claude" in capsys.readouterr().out


def test_categorize_learns_a_rule(home, pdf, capsys):
    run("import", str(pdf), "--no-alerts")
    with Ledger(home / "ledger.db") as ledger:
        txn = next(t for t in ledger.transactions() if "TRADER" in t["description"])

    assert run("categorize", str(txn["id"]), "eating out") == 0
    assert "Rule saved: TRADER JOES -> Eating Out" in capsys.readouterr().out

    run("rules")
    assert "your correction" in capsys.readouterr().out
    assert run("categorize", str(txn["id"]), "Not A Category") == 1


def test_export_csv_and_json(home, pdf, capsys):
    run("import", str(pdf), "--no-alerts")
    capsys.readouterr()

    run("export", "-m", "3/2026")
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert {r["kind"] for r in rows} == {"income", "expense", "transfer"}

    run("export", "-f", "json", "-o", str(home / "out.json"))
    assert len(json.loads((home / "out.json").read_text())) == 4


def test_report_writes_dashboard(home, pdf):
    run("import", str(pdf), "--no-alerts")
    assert run("report", "-o", str(home / "d.html")) == 0
    html = (home / "d.html").read_text(encoding="utf-8")
    assert '<span class="title">Expense Tracker</span>' in html
    assert "TRADER JOES" in html
    assert "</script>" not in html.split("const DATA = ")[1].split(";\nconst EDITABLE")[0]


def test_empty_ledger_gives_a_helpful_error(home, capsys):
    assert run("summary") == 1
    assert "Import a statement first" in capsys.readouterr().err


def test_bad_month_is_rejected(home, pdf, capsys):
    assert run("import", str(pdf), "-m", "13/2026") == 1
    assert "Invalid month" in capsys.readouterr().out


def test_demo_data_reconciles(home):
    from expense_tracker.demo import build_demo

    config = load_config()
    with Ledger(":memory:") as ledger:
        count = build_demo(ledger, config, months=3)
        assert count > 60
        # One statement deliberately "loses" a transaction to show the warning path
        assert [s["reconciled"] for s in ledger.statements()] == [1, 0, 1]
        assert not ledger.uncategorized_expenses()
    assert fake_categorize.calls == 0  # the demo never needs an API key


def test_names_and_rename_commands(home, pdf, capsys):
    run("import", str(pdf), "--no-alerts")
    with patch(
        "expense_tracker.categorizer.suggest_names", lambda d, **kw: [f"Name {i}" for i in range(len(d))]
    ):
        assert run("names") == 0
    assert "Named" in capsys.readouterr().out
    with Ledger(home / "ledger.db") as ledger:
        txn = next(t for t in ledger.transactions() if "TRADER" in t["description"])
    assert run("rename", str(txn["id"]), "Trader Joe's") == 0
    assert 'shown as "Trader Joe\'s"' in capsys.readouterr().out
    assert run("rename", str(txn["id"])) == 0
    assert "automatic name" in capsys.readouterr().out
