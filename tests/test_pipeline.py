"""Tests for month handling and Google Sheets sync in the import pipeline."""

from unittest.mock import patch

import pytest

from expense_tracker.config import Config
from expense_tracker.ledger import Ledger
from expense_tracker.pipeline import (
    normalize_month,
    recent_months,
    send_threshold_alerts,
    sheets_month,
    statement_month,
    sync_month_to_sheets,
)


@pytest.mark.parametrize(
    ("raw", "expected"), [("1/2026", "2026-01"), ("12/2025", "2025-12"), ("2026-3", "2026-03")]
)
def test_normalize_month(raw, expected):
    assert normalize_month(raw) == expected


@pytest.mark.parametrize("raw", ["13/2026", "January", "2026/01"])
def test_normalize_month_rejects(raw):
    with pytest.raises(ValueError):
        normalize_month(raw)


def test_sheets_month():
    assert sheets_month("2026-01") == "1/2026"


def test_statement_month_prefers_period_end():
    parsed = {"statement_period": ("2025-12-12", "2026-01-11"), "all_transactions": []}
    assert statement_month(parsed, 31) == "2026-01"


def test_statement_month_falls_back_to_latest_transaction():
    parsed = {"all_transactions": [{"date": "2026-01-05"}, {"date": "2026-01-20"}, {"date": "bad"}]}
    assert statement_month(parsed, 11) == "2026-02"


def test_sync_month_to_sheets_writes_all_three_tabs(tmp_path):
    config = Config(home=tmp_path)
    with Ledger(":memory:") as ledger:
        ledger.add_statement(
            {
                "bank_name": "B",
                "statement_type": "checking",
                "opening_balance": 100.0,
                "closing_balance": 1050.0,
                "all_transactions": [
                    {"date": "2026-01-02", "description": "PAYROLL", "amount": 1000.0},
                    {"date": "2026-01-03", "description": "LOAN", "amount": -50.0},
                ],
                "debt_payments": [],
            },
            "jan.pdf",
            "h",
            "2026-01",
        )
        ledger.set_category(2, "Housing", "user")

        with (
            patch("expense_tracker.sheets.sync_to_sheet") as out,
            patch("expense_tracker.sheets.sync_income_to_sheet") as inc,
            patch("expense_tracker.sheets.sync_net_worth_to_sheet") as nw,
        ):
            result = sync_month_to_sheets(
                ledger, config, "2026-01", "https://docs.google.com/spreadsheets/d/abc123/edit"
            )

    assert result["month"] == "1/2026"
    assert out.call_args.args[0] == "abc123"
    assert out.call_args.kwargs == {"month": "1/2026", "mode": "replace"}
    assert out.call_args.args[1][0]["category"] == "Housing"
    assert inc.call_args.args[1][0]["amount"] == 1000.0
    assert nw.call_args.args[1]["checking_balance"] == 1050.0


def test_recent_months_are_current_and_previous():
    from datetime import date

    assert recent_months(31, date(2026, 1, 5)) == {"2026-01", "2025-12"}
    assert recent_months(11, date(2026, 9, 26)) == {"2026-10", "2026-09"}


def test_importing_old_statements_never_emails(tmp_path, monkeypatch):
    """A back-catalogue import must not send alerts about months long past."""
    sent = []
    monkeypatch.setattr(
        "expense_tracker.notifications.check_spending_threshold", lambda **kw: sent.append(kw) or [1000.0]
    )
    config = Config(home=tmp_path)
    with Ledger(":memory:") as ledger:
        assert send_threshold_alerts(ledger, config, "2019-03") == []
        this_month = sorted(recent_months(config.statement_close_day))[-1]
        assert send_threshold_alerts(ledger, config, this_month) == [1000.0]
    assert len(sent) == 1


def _ledger_with(txns):
    ledger = Ledger(":memory:")
    ledger.add_statement(
        {"bank_name": "B", "statement_type": "checking", "all_transactions": txns, "debt_payments": []},
        "s.pdf",
        "h",
        "2026-01",
    )
    return ledger


def test_categorizing_saves_claudes_names(tmp_path):
    from expense_tracker.pipeline import categorize_pending

    ledger = _ledger_with([{"date": "2026-01-02", "description": "easyJetKBQTWC2 Luton", "amount": -241.08}])
    fake = lambda txns, **kw: [{**t, "category": "Travel", "merchant_name": "easyJet"} for t in txns]  # noqa: E731
    with patch("expense_tracker.categorizer.categorize_transactions", fake):
        categorize_pending(ledger, Config(home=tmp_path))
    assert list(ledger.names().values()) == ["easyJet"]


def test_name_merchants_names_each_merchant_once_and_keeps_user_names(tmp_path):
    from expense_tracker.ledger import merchant_key
    from expense_tracker.pipeline import name_merchants

    ledger = _ledger_with(
        [
            {"date": "2026-01-02", "description": "WHOLEFDS SYM 10031", "amount": -20.0},
            {"date": "2026-01-03", "description": "WHOLEFDS SYM 10031", "amount": -30.0},
            {"date": "2026-01-04", "description": "PAYROLL DEPOSIT - ACME", "amount": 900.0},
            {"date": "2026-01-05", "description": "TRANSFER TO SAV", "amount": -50.0, "is_internal": True},
        ]
    )
    ledger.save_name(merchant_key("PAYROLL DEPOSIT - ACME"), "Salary", "user")
    asked = []

    def fake(descriptions, **kw):
        asked.extend(descriptions)
        return ["Whole Foods" for _ in descriptions]

    with patch("expense_tracker.categorizer.suggest_names", fake):
        saved = name_merchants(ledger, Config(home=tmp_path))
        again = name_merchants(ledger, Config(home=tmp_path))
        redo = name_merchants(ledger, Config(home=tmp_path), redo=True)
    assert asked.count("WHOLEFDS SYM 10031") == 2  # once, then again only for --redo
    assert "TRANSFER TO SAV" not in asked and "PAYROLL DEPOSIT - ACME" not in asked
    assert list(saved.values()) == ["Whole Foods"] and again == {} and list(redo.values()) == ["Whole Foods"]
    assert ledger.names()[merchant_key("PAYROLL DEPOSIT - ACME")] == "Salary"


def test_rename_merchant_applies_to_every_transaction_and_can_be_undone():
    from expense_tracker.ledger import merchant_key
    from expense_tracker.pipeline import rename_merchant

    ledger = _ledger_with(
        [
            {"date": "2026-01-02", "description": "SHOP 2/ LOUNGE 2 SCHIPHOL", "amount": -20.0},
            {"date": "2026-01-09", "description": "SHOP 2/ LOUNGE 2 SCHIPHOL", "amount": -25.0},
        ]
    )
    key, count = rename_merchant(ledger, 1, "Schiphol Lounge")
    assert count == 2 and ledger.names()[key] == "Schiphol Lounge"
    rename_merchant(ledger, 1, "")
    assert key not in ledger.names() and key == merchant_key("SHOP 2/ LOUNGE 2 SCHIPHOL")
    with pytest.raises(ValueError, match="60"):
        rename_merchant(ledger, 1, "x" * 61)
    with pytest.raises(ValueError, match="No transaction"):
        rename_merchant(ledger, 99, "X")


def test_report_prefers_stored_names(tmp_path):
    from expense_tracker.ledger import merchant_key
    from expense_tracker.report import dashboard_data

    ledger = _ledger_with(
        [
            {"date": "2026-01-02", "description": "PL*StateFinancia DES:WEB PMTS", "amount": -3850.0},
            {"date": "2026-01-03", "description": "CVS PHARMACY #8841", "amount": -9.0},
        ]
    )
    ledger.save_name(merchant_key("PL*StateFinancia DES:WEB PMTS"), "State Financial", "ai")
    merchants = [t["merchant"] for t in dashboard_data(ledger, Config(home=tmp_path))["transactions"]]
    assert merchants == ["State Financial", "CVS Pharmacy"]  # stored name, then the built-in tidy-up
