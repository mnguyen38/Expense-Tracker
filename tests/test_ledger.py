"""Tests for the SQLite ledger and merchant-rule helpers."""

import pytest

from expense_tracker.ledger import Ledger, budget_month, classify, merchant_key


@pytest.fixture
def ledger():
    with Ledger(":memory:") as db:
        yield db


def _statement(txns, statement_type="checking", opening=1000.0, closing=None, warnings=None):
    closing = opening + sum(t["amount"] for t in txns) if closing is None else closing
    return {
        "bank_name": "Test Bank",
        "statement_type": statement_type,
        "currency": "USD",
        "statement_period": ("2026-01-01", "2026-01-31"),
        "opening_balance": opening,
        "closing_balance": closing,
        "all_transactions": txns,
        "debt_payments": [t for t in txns if "LOAN" in t["description"]],
        "warnings": warnings or [],
    }


TXNS = [
    {"date": "2026-01-02", "description": "PAYROLL", "amount": 3000.0},
    {"date": "2026-01-03", "description": "CHECKCARD 0103 TRADER JOE'S #552", "amount": -50.0},
    {"date": "2026-01-09", "description": "TRADER JOE'S #101 SEATTLE", "amount": -25.0},
    {"date": "2026-01-10", "description": "STUDENT LOAN PMT", "amount": -200.0},
    {"date": "2026-01-11", "description": "TRANSFER TO SAVINGS", "amount": -500.0, "is_internal": True},
]


class TestHelpers:
    def test_merchant_key_ignores_store_numbers_and_card_noise(self):
        assert merchant_key("CHECKCARD 0103 TRADER JOE'S #552") == "TRADER JOE S"
        assert merchant_key("TRADER JOE'S #101 SEATTLE") == "TRADER JOE S"
        assert merchant_key("PP*APPLE.COM/BILL") == "APPLE COM BILL"

    @pytest.mark.parametrize(
        ("day", "close_day", "expected"),
        [("2026-01-05", 31, "2026-01"), ("2026-01-12", 11, "2026-02"), ("2026-12-20", 11, "2027-01")],
    )
    def test_budget_month(self, day, close_day, expected):
        assert budget_month(day, close_day) == expected

    def test_classify(self):
        assert classify({"amount": -5}, "checking") == "expense"
        assert classify({"amount": 5}, "checking") == "income"
        assert classify({"amount": 5}, "credit_card") == "other"
        assert classify({"amount": -5, "is_internal": True}, "checking") == "transfer"


class TestStatements:
    def test_add_statement_classifies_transactions(self, ledger):
        ledger.add_statement(_statement(TXNS), "jan.pdf", "hash1", "2026-01")

        kinds = [t["kind"] for t in ledger.transactions("2026-01")]
        assert kinds == ["income", "expense", "expense", "expense", "transfer"]
        assert ledger.has_statement("hash1")
        assert ledger.statements()[0]["reconciled"] == 1

    def test_month_summary(self, ledger):
        ledger.add_statement(_statement(TXNS), "jan.pdf", "hash1", "2026-01")
        s = ledger.month_summary("2026-01")

        assert s["total_spending"] == 275.0  # transfer excluded
        assert s["total_income"] == 3000.0
        assert s["debt_payments"] == 200.0
        assert s["balances"]["checking"] == 3225.0
        assert s["by_category"]["Uncategorized"]["count"] == 3

    def test_unreconciled_statement_is_flagged(self, ledger):
        ledger.add_statement(_statement(TXNS, closing=1.0, warnings=["off"]), "jan.pdf", "h", "2026-01")
        assert ledger.statements()[0]["reconciled"] == 0

    def test_deleting_statement_removes_its_transactions(self, ledger):
        ledger.add_statement(_statement(TXNS), "jan.pdf", "hash1", "2026-01")
        ledger.delete_statement("hash1")
        assert ledger.transactions() == []


class TestEmailAlerts:
    ALERTS = [
        {"email_id": "a", "date": "2026-02-03", "description": "UBER TRIP", "amount": -20.0},
        {"email_id": "b", "date": "2026-02-04", "description": "CHIPOTLE", "amount": -12.0},
    ]

    def test_duplicates_are_skipped(self, ledger):
        assert ledger.add_email_transactions(self.ALERTS) == 2
        assert ledger.add_email_transactions(self.ALERTS) == 0

    def test_statement_supersedes_alerts_for_its_month(self, ledger):
        ledger.add_email_transactions(self.ALERTS)
        assert ledger.month_summary("2026-02")["total_spending"] == 32.0

        feb = [{"date": "2026-02-03", "description": "UBER TRIP", "amount": -20.0}]
        ledger.add_statement(_statement(feb), "feb.pdf", "hash2", "2026-02")
        assert ledger.month_summary("2026-02")["total_spending"] == 20.0  # not double counted


class TestRules:
    def test_user_rule_is_not_overwritten_by_ai(self, ledger):
        ledger.save_rule("TRADER JOE S", "Groceries", "user")
        ledger.save_rule("TRADER JOE S", "Eating Out", "ai")
        assert ledger.get_rule("TRADER JOE S")["category"] == "Groceries"

    def test_recategorize_merchant_skips_manual_edits(self, ledger):
        ledger.add_statement(_statement(TXNS), "jan.pdf", "hash1", "2026-01")
        tj = [t for t in ledger.transactions() if "TRADER" in t["description"]]
        ledger.set_category(tj[0]["id"], "Gifts", "user")

        assert ledger.recategorize_merchant("TRADER JOE S", "Groceries") == 1
        categories = {t["id"]: t["category"] for t in ledger.transactions()}
        assert categories[tj[0]["id"]] == "Gifts"
        assert categories[tj[1]["id"]] == "Groceries"

    def test_delete_rule(self, ledger):
        ledger.save_rule("UBER TRIP", "Rideshare", "ai")
        assert ledger.delete_rule("UBER TRIP") is True
        assert ledger.delete_rule("UBER TRIP") is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CHECKCARD 0305 TRADER JOE'S #552 PORTLAND OR", "Trader Joe's"),
        ("RENT - MAPLE COURT APARTMENTS", "Maple Court Apartments"),
        ("PAYROLL DEPOSIT - ACME ROBOTICS INC", "Acme Robotics Inc"),
        ("APPLE.COM/BILL ICLOUD 200GB", "Apple.com"),
        ("SQ *BLUE BOTTLE COFFEE", "Blue Bottle Coffee"),
        ("CVS PHARMACY #8841", "CVS Pharmacy"),
        ("CARNIVAL - DELUXE SUITE", "Carnival - Deluxe Suite"),  # non-generic lead is kept
        ("PL*PAYLEASE DES:WEB PMTS ID:AB12CD INDN:JANE DOE CO ID:900", "Paylease"),
        ("COMCAST-XFINITY DES:CABLE SVCS ID:123", "Comcast-Xfinity"),
        ("WIRE TYPE:INTL IN DATE:260107 TIME:0452 ET TRN:20260107", "International wire received"),
        ("ANTHROPIC ANTHROPIC.COMCA", "Anthropic"),
        ("UBER *TRIP HELP.UBER.COM Amsterdam", "Uber"),
        ("NLOVLD5D9X4PRQYJZ7 WWW.OVPAY.NL", "Ovpay.nl"),
        ("IKEA LTD BRIGHTON BRIGHTON", "IKEA Ltd Brighton"),
        ("MARKS&SPENCER PLC BRIGHTON", "Marks&Spencer Plc Brighton"),
        ("SumUp *JP Gifts Brighton", "Jp Gifts Brighton"),
    ],
)
def test_display_name(raw, expected):
    from expense_tracker.ledger import display_name

    assert display_name(raw) == expected


class TestNames:
    def test_user_rename_beats_the_ai(self, ledger):
        assert ledger.save_name("PL STATEFINANCIA DES", "State Financial", "ai")
        assert ledger.save_name("PL STATEFINANCIA DES", "My Mortgage", "user")
        assert not ledger.save_name("PL STATEFINANCIA DES", "Statefinancia", "ai")
        assert ledger.names() == {"PL STATEFINANCIA DES": "My Mortgage"}

    def test_names_are_tidied_and_capped(self, ledger):
        ledger.save_name("K", "  Whole   Foods  " + "x" * 80, "ai")
        assert ledger.names()["K"].startswith("Whole Foods x") and len(ledger.names()["K"]) == 60
        assert not ledger.save_name("K2", "   ", "ai")

    def test_redact_strips_personal_fields(self):
        from expense_tracker.ledger import redact

        raw = "PL*PAYLEASE DES:WEB PMTS ID:LS92D8 INDN:Jane Doe CO ID:9000287225 WEB"
        assert redact(raw) == "PL*PAYLEASE DES:WEB PMTS"
        assert redact("Credit Adjustment Acct # 466017533874 Claim") == "Credit Adjustment Claim"
        assert redact("PAYMENT FROM CHK 3861 CONF#1adnouovz") == "PAYMENT FROM CHK 3861"
