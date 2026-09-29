"""Tests for base parser classes and utilities."""

import pytest

from expense_tracker.parsers.base import BaseParser, ParseResult


class TestParseResult:
    """Tests for ParseResult dataclass."""

    def test_create_parse_result(self):
        """Test creating a ParseResult with required fields."""
        result = ParseResult(
            bank_id="test_bank",
            bank_name="Test Bank",
            currency="USD",
            statement_type="checking",
        )
        assert result.bank_id == "test_bank"
        assert result.bank_name == "Test Bank"
        assert result.currency == "USD"
        assert result.statement_type == "checking"
        assert result.transactions == []
        assert result.expenses == []
        assert result.income == []

    def test_parse_result_with_transactions(self):
        """Test ParseResult with transaction data."""
        transactions = [{"date": "2025-01-15", "description": "Test", "amount": -50.00}]
        result = ParseResult(
            bank_id="test",
            bank_name="Test",
            currency="USD",
            statement_type="checking",
            transactions=transactions,
            closing_balance=1000.00,
        )
        assert len(result.transactions) == 1
        assert result.closing_balance == 1000.00

    def test_to_dict_conversion(self):
        """Test converting ParseResult to dictionary."""
        result = ParseResult(
            bank_id="boa",
            bank_name="Bank of America",
            currency="USD",
            statement_type="credit_card",
            statement_period=("2025-01-01", "2025-01-31"),
            opening_balance=500.00,
            closing_balance=750.00,
            transactions=[{"date": "2025-01-15", "description": "Test", "amount": -25.00}],
            expenses=[{"date": "2025-01-15", "description": "Test", "amount": -25.00}],
            income=[],
            debt_payments=[],
        )
        d = result.to_dict()

        assert d["bank_id"] == "boa"
        assert d["bank_name"] == "Bank of America"
        assert d["currency"] == "USD"
        assert d["statement_type"] == "credit_card"
        assert d["statement_period"] == ("2025-01-01", "2025-01-31")
        assert d["opening_balance"] == 500.00
        assert d["closing_balance"] == 750.00
        assert d["ending_balance"] == 750.00  # Backwards compat alias
        assert len(d["all_transactions"]) == 1
        assert len(d["expenses"]) == 1

    def test_to_dict_with_none_values(self):
        """Test to_dict handles None values correctly."""
        result = ParseResult(
            bank_id="test",
            bank_name="Test",
            currency="USD",
            statement_type="checking",
        )
        d = result.to_dict()

        assert d["opening_balance"] is None
        assert d["closing_balance"] is None
        assert d["statement_period"] is None


class TestBaseParser:
    """Tests for BaseParser utility methods."""

    @pytest.fixture
    def parser(self):
        """Create a BaseParser instance for testing."""
        parser = BaseParser()
        parser.internal_transfer_patterns = [
            r"transfer to savings",
            r"transfer from checking",
            r"online transfer",
        ]
        return parser

    def test_default_attributes(self):
        """Test default BaseParser attributes."""
        parser = BaseParser()
        assert parser.bank_id == "unknown"
        assert parser.bank_name == "Unknown Bank"
        assert parser.currency == "USD"

    def test_is_internal_transfer_match(self, parser):
        """Test detecting internal transfers."""
        assert parser.is_internal_transfer("ONLINE TRANSFER TO SAVINGS") is True
        assert parser.is_internal_transfer("Transfer from Checking") is True
        assert parser.is_internal_transfer("online transfer") is True

    def test_is_internal_transfer_no_match(self, parser):
        """Test non-transfer transactions."""
        assert parser.is_internal_transfer("AMAZON.COM PURCHASE") is False
        assert parser.is_internal_transfer("UBER TRIP") is False
        assert parser.is_internal_transfer("DIRECT DEPOSIT") is False

    def test_is_internal_transfer_empty_patterns(self):
        """Test with no transfer patterns defined."""
        parser = BaseParser()
        parser.internal_transfer_patterns = []
        assert parser.is_internal_transfer("ONLINE TRANSFER") is False

    def test_is_debt_payment_match(self):
        """Test detecting debt payments."""
        parser = BaseParser()
        assert parser.is_debt_payment("STUDENT LOAN PAYMENT") is True
        assert parser.is_debt_payment("State Financial Services") is True
        assert parser.is_debt_payment("MORTGAGE PAYMENT") is True
        assert parser.is_debt_payment("Sallie Mae") is True

    def test_is_debt_payment_no_match(self):
        """Test non-debt transactions."""
        parser = BaseParser()
        assert parser.is_debt_payment("AMAZON.COM") is False
        assert parser.is_debt_payment("UBER TRIP") is False
        assert parser.is_debt_payment("NETFLIX") is False

    def test_parse_amount_simple(self):
        """Test parsing simple amounts."""
        parser = BaseParser()
        assert parser.parse_amount("100.00") == 100.00
        assert parser.parse_amount("25.50") == 25.50
        assert parser.parse_amount("0.99") == 0.99

    def test_parse_amount_with_commas(self):
        """Test parsing amounts with thousands separators."""
        parser = BaseParser()
        assert parser.parse_amount("1,000.00") == 1000.00
        assert parser.parse_amount("25,432.50") == 25432.50
        assert parser.parse_amount("1,234,567.89") == 1234567.89

    def test_parse_amount_with_currency_symbols(self):
        """Test parsing amounts with currency symbols."""
        parser = BaseParser()
        assert parser.parse_amount("$100.00") == 100.00
        assert parser.parse_amount("£50.00") == 50.00
        assert parser.parse_amount("€25.99") == 25.99
        assert parser.parse_amount("$1,234.56") == 1234.56

    def test_parse_amount_with_whitespace(self):
        """Test parsing amounts with whitespace."""
        parser = BaseParser()
        assert parser.parse_amount(" 100.00 ") == 100.00
        assert parser.parse_amount("$ 50.00") == 50.00

    def test_separate_transactions_basic(self, parser):
        """Test separating transactions into expenses, income, debt."""
        transactions = [
            {"description": "AMAZON.COM", "amount": -50.00},
            {"description": "DIRECT DEPOSIT", "amount": 2000.00},
            {"description": "UBER", "amount": -25.00},
        ]
        expenses, income, debt = parser.separate_transactions(transactions, "checking")

        assert len(expenses) == 2
        assert len(income) == 1
        assert len(debt) == 0
        assert income[0]["description"] == "DIRECT DEPOSIT"

    def test_separate_transactions_with_debt(self, parser):
        """Test separating transactions with debt payments."""
        transactions = [
            {"description": "STUDENT LOAN PAYMENT", "amount": -500.00},
            {"description": "NETFLIX", "amount": -15.99},
        ]
        expenses, income, debt = parser.separate_transactions(transactions, "checking")

        assert len(expenses) == 2
        assert len(income) == 0
        assert len(debt) == 1
        assert debt[0]["description"] == "STUDENT LOAN PAYMENT"

    def test_separate_transactions_filters_internal(self, parser):
        """Test that internal transfers are filtered out."""
        transactions = [
            {"description": "AMAZON.COM", "amount": -50.00},
            {"description": "ONLINE TRANSFER TO SAVINGS", "amount": -500.00},
            {"description": "DIRECT DEPOSIT", "amount": 2000.00},
        ]
        expenses, income, debt = parser.separate_transactions(transactions, "checking")

        assert len(expenses) == 1
        assert expenses[0]["description"] == "AMAZON.COM"
        assert len(income) == 1

    def test_separate_transactions_credit_card(self, parser):
        """Test that income is not tracked for credit card statements."""
        transactions = [
            {"description": "AMAZON.COM", "amount": -50.00},
            {"description": "PAYMENT THANK YOU", "amount": 500.00},  # Payment on card
        ]
        expenses, income, debt = parser.separate_transactions(transactions, "credit_card")

        assert len(expenses) == 1
        assert len(income) == 0  # Payments aren't income for credit cards

    def test_separate_transactions_marks_internal(self, parser):
        """Test that internal transfers are marked."""
        transactions = [
            {"description": "ONLINE TRANSFER TO SAVINGS", "amount": -500.00},
        ]
        parser.separate_transactions(transactions, "checking")

        assert transactions[0].get("is_internal") is True

    def test_separate_transactions_empty_list(self, parser):
        """Test with empty transaction list."""
        expenses, income, debt = parser.separate_transactions([], "checking")

        assert expenses == []
        assert income == []
        assert debt == []

    def test_separate_transactions_zero_amount(self, parser):
        """Test transactions with zero amount."""
        transactions = [
            {"description": "ZERO AMOUNT TXN", "amount": 0},
        ]
        expenses, income, debt = parser.separate_transactions(transactions, "checking")

        # Zero amount is neither expense nor income
        assert len(expenses) == 0
        assert len(income) == 0


class TestReconcile:
    """Balance reconciliation catches missing or misread transactions."""

    def _result(self, statement_type, opening, closing, amounts):
        return ParseResult(
            bank_id="test",
            bank_name="Test",
            currency="USD",
            statement_type=statement_type,
            opening_balance=opening,
            closing_balance=closing,
            transactions=[{"amount": a} for a in amounts],
        )

    def test_bank_account_balances(self):
        result = self._result("checking", 1000.0, 1450.0, [-50.0, 1000.0, -500.0])
        assert result.reconcile() is True
        assert result.warnings == []

    def test_bank_account_missing_transaction(self):
        result = self._result("checking", 1000.0, 1400.0, [-50.0, 1000.0, -500.0])
        assert result.reconcile() is False
        assert "off by -50.00" in result.warnings[0]

    def test_credit_card_balance_is_debt(self):
        # Owed 500, paid 500, spent 120 -> owe 120
        result = self._result("credit_card", 500.0, 120.0, [500.0, -100.0, -20.0])
        assert result.reconcile() is True

    def test_float_rounding_within_tolerance(self):
        result = self._result("savings", 0.0, 0.3, [0.1, 0.1, 0.1])
        assert result.reconcile() is True

    def test_missing_balance_is_inconclusive(self):
        result = self._result("checking", None, 1450.0, [-50.0])
        assert result.reconcile() is None
        assert result.warnings == []

    def test_warnings_in_dict(self):
        result = self._result("checking", 0.0, 10.0, [])
        result.reconcile()
        assert len(result.to_dict()["warnings"]) == 1
