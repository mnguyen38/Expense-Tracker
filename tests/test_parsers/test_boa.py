"""Tests for Bank of America statement parser."""

import pytest

from expense_tracker.parsers.boa import BOAParser


class TestBOAParser:
    """Tests for BOAParser class."""

    @pytest.fixture
    def parser(self):
        """Create a BOAParser instance."""
        return BOAParser()

    # =========================================================================
    # Detection Tests
    # =========================================================================

    def test_detect_boa_checking(self, parser, boa_checking_text):
        """Test detection of BoA checking statement."""
        confidence = parser.detect(boa_checking_text)
        # Should have high confidence (Bank of America + account type indicator)
        assert confidence >= 0.5

    def test_detect_boa_credit_card(self, parser, boa_credit_card_text):
        """Test detection of BoA credit card statement."""
        confidence = parser.detect(boa_credit_card_text)
        assert confidence >= 0.5

    def test_detect_boa_savings(self, parser, boa_savings_text):
        """Test detection of BoA savings statement."""
        confidence = parser.detect(boa_savings_text)
        assert confidence >= 0.5

    def test_detect_non_boa_statement(self, parser):
        """Test detection returns 0 for non-BoA statements."""
        text = """
        Chase Bank
        Monthly Statement
        Account Number: 123456789
        """
        confidence = parser.detect(text)
        assert confidence == 0.0

    def test_detect_partial_match(self, parser):
        """Test detection with Bank of America but no account type."""
        text = "Bank of America Some Generic Document"
        confidence = parser.detect(text)
        # Should get 0.5 for "Bank of America" match
        assert confidence == 0.5

    def test_detect_with_bankofamerica_domain(self, parser):
        """Test detection with bankofamerica.com."""
        text = "Visit bankofamerica.com for more information"
        confidence = parser.detect(text)
        assert confidence == 0.3

    # =========================================================================
    # Statement Type Detection Tests
    # =========================================================================

    def test_detect_statement_type_credit_card(self, parser):
        """Test detecting credit card statement type."""
        text = "Credit Card Statement Account Number ending in: 1234"
        result = parser._detect_statement_type(text)
        assert result == "credit_card"

    def test_detect_statement_type_credit_card_with_purchases(self, parser):
        """Test detecting credit card from purchases section."""
        text = "Purchases and Adjustments"
        result = parser._detect_statement_type(text)
        assert result == "credit_card"

    def test_detect_statement_type_checking(self, parser):
        """Test detecting checking statement type."""
        text = "Your Advantage Checking Account Statement"
        result = parser._detect_statement_type(text)
        assert result == "checking"

    def test_detect_statement_type_checking_safebalance(self, parser):
        """Test detecting checking with SafeBalance."""
        text = "Your SafeBalance Banking Account"
        result = parser._detect_statement_type(text)
        assert result == "checking"

    def test_detect_statement_type_savings(self, parser):
        """Test detecting savings statement type."""
        text = "Your Advantage Savings Account Statement"
        result = parser._detect_statement_type(text)
        assert result == "savings"

    def test_detect_statement_type_unknown_defaults_credit_card(self, parser):
        """Test unknown statement type defaults to credit_card."""
        text = "Some Random Bank Document"
        result = parser._detect_statement_type(text)
        assert result == "credit_card"

    # =========================================================================
    # Statement Period Extraction Tests
    # =========================================================================

    def test_extract_statement_period_december_january(self, parser):
        """Test extracting period spanning year boundary."""
        # Note: Pattern expects "Month DD - Month DD, YYYY" without year before dash
        text = "Statement period: December 11 - January 10, 2026"
        year, month = parser._extract_statement_period(text)
        assert year == 2026
        assert month == 12  # December (1-indexed)

    def test_extract_statement_period_mid_year(self, parser):
        """Test extracting period within same year."""
        text = "Statement period: June 11 - July 10, 2025"
        year, month = parser._extract_statement_period(text)
        assert year == 2025
        assert month == 6  # June (1-indexed)

    def test_extract_statement_period_not_found(self, parser):
        """Test default values when period not found."""
        text = "No date information here"
        year, month = parser._extract_statement_period(text)
        # Defaults to current year and month 1
        assert month == 1

    # =========================================================================
    # Balance Extraction Tests
    # =========================================================================

    def test_extract_ending_balance(self, parser):
        """Test extracting ending balance from checking statement."""
        text = "Ending balance on January 10, 2026              $6,762.77"
        balance = parser._extract_ending_balance(text)
        assert balance == 6762.77

    def test_extract_ending_balance_no_comma(self, parser):
        """Test extracting ending balance without comma."""
        text = "Ending balance on January 10, 2026              $762.50"
        balance = parser._extract_ending_balance(text)
        assert balance == 762.50

    def test_extract_ending_balance_not_found(self, parser):
        """Test None returned when balance not found."""
        text = "No balance information"
        balance = parser._extract_ending_balance(text)
        assert balance is None

    def test_extract_credit_card_balance(self, parser):
        """Test extracting credit card new balance."""
        text = "New Balance Total                           $1,234.56"
        balance = parser._extract_credit_card_balance(text)
        assert balance == 1234.56

    def test_extract_credit_card_balance_alt_format(self, parser):
        """Test extracting credit card balance with alternate format."""
        text = "Statement Balance                           $567.89"
        balance = parser._extract_credit_card_balance(text)
        assert balance == 567.89

    def test_extract_credit_card_balance_not_found(self, parser):
        """Test None when credit card balance not found."""
        text = "No balance information"
        balance = parser._extract_credit_card_balance(text)
        assert balance is None

    # =========================================================================
    # Date Parsing Tests
    # =========================================================================

    def test_parse_boa_date_same_year(self, parser):
        """Test parsing date within same year as statement."""
        result = parser._parse_boa_date("06/15", 2025, 6)
        assert result == "2025-06-15"

    def test_parse_boa_date_year_boundary_december(self, parser):
        """Test parsing December date when statement spans year boundary."""
        result = parser._parse_boa_date("12/20", 2026, 12)
        assert result == "2025-12-20"

    def test_parse_boa_date_year_boundary_january(self, parser):
        """Test parsing January date when statement spans year boundary."""
        result = parser._parse_boa_date("01/05", 2026, 12)
        assert result == "2026-01-05"

    def test_parse_boa_date_invalid(self, parser):
        """Test parsing invalid date returns original string."""
        result = parser._parse_boa_date("invalid", 2025, 1)
        assert result == "invalid"

    # =========================================================================
    # Full Parse Tests
    # =========================================================================

    def test_parse_checking_statement(self, parser, tmp_path):
        """Test parsing a complete checking statement with proper text."""
        text = """
Bank of America
Your Advantage Checking Account Statement
Account number: 1234567890

Statement period: December 11, 2025 - January 10, 2026

Beginning balance on December 11, 2025         $5,000.00

Deposits and other credits
12/15  Direct Deposit EMPLOYER INC                    2,500.00

Withdrawals and other debits
12/20  Debit Card Purchase WHOLE FOODS               -87.23

Ending balance on January 10, 2026              $6,762.77
"""
        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, text)

        assert result.bank_id == "boa"
        assert result.bank_name == "Bank of America"
        assert result.currency == "USD"
        assert result.statement_type == "checking"

    def test_parse_credit_card_statement(self, parser, tmp_path):
        """Test parsing a credit card statement."""
        text = """
Bank of America
Credit Card Statement

Account Number ending in: 1234

Statement Closing Date: January 10, 2026
Payment Due Date: February 5, 2026

Purchases and Adjustments

01/02  AMAZON.COM*123ABC    SEATTLE WA           45.99
01/05  UBER   *TRIP         SAN FRANCISCO        25.50

New Balance Total                           $1,234.56
"""
        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, text)

        assert result.bank_id == "boa"
        assert result.statement_type == "credit_card"
        assert result.closing_balance == 1234.56

    def test_parse_savings_statement(self, parser, tmp_path):
        """Test parsing a savings statement."""
        text = """
Bank of America
Your Advantage Savings Account Statement
Account number: 9876543210

Statement period: December 11, 2025 - January 10, 2026

Beginning balance on December 11, 2025        $11,500.00

Deposits and other credits
12/22  Online Transfer from Checking               500.00

Ending balance on January 10, 2026            $12,000.00
"""
        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, text)

        assert result.statement_type == "savings"
        assert result.closing_balance == 12000.00

    def test_parse_result_to_dict(self, parser, tmp_path):
        """Test that parse result converts to dict correctly."""
        text = """
Bank of America
Your Advantage Checking Account Statement
Account number: 1234567890

Ending balance on January 10, 2026              $6,762.77
"""
        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, text)
        d = result.to_dict()

        assert "bank_id" in d
        assert "expenses" in d
        assert "income" in d
        assert "ending_balance" in d


class TestBOAParserInternalTransfers:
    """Tests for internal transfer detection in BOAParser."""

    @pytest.fixture
    def parser(self):
        return BOAParser()

    def test_detects_online_transfer(self, parser):
        """Test detecting online transfer."""
        assert parser.is_internal_transfer("Online Banking transfer to SAV") is True

    def test_detects_transfer_to_account(self, parser):
        """Test detecting transfer to specific account."""
        assert parser.is_internal_transfer("transfer to CHK 1234") is True

    def test_detects_transfer_from_account(self, parser):
        """Test detecting transfer from account."""
        assert parser.is_internal_transfer("transfer from SAV 5678") is True

    def test_regular_purchase_not_transfer(self, parser):
        """Test that regular purchases aren't flagged as transfers."""
        assert parser.is_internal_transfer("AMAZON.COM AMZN.COM/BILL") is False
        assert parser.is_internal_transfer("UBER TRIP") is False


class TestBOAParserEdgeCases:
    """Edge case tests for BOAParser."""

    @pytest.fixture
    def parser(self):
        return BOAParser()

    def test_empty_text(self, parser, tmp_path):
        """Test parsing empty text."""
        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, "")
        # Empty text defaults to credit_card type
        assert result.statement_type == "credit_card"
        assert len(result.transactions) == 0

    def test_malformed_amounts(self, parser):
        """Test parsing handles malformed amounts."""
        # The parser should handle amounts with extra whitespace
        assert parser.parse_amount("  $100.00  ") == 100.00

    def test_large_amounts(self, parser):
        """Test parsing large amounts."""
        assert parser.parse_amount("$1,234,567.89") == 1234567.89


class TestBOAParserPeriodDates:
    """Tests for period date extraction."""

    @pytest.fixture
    def parser(self):
        return BOAParser()

    def test_extract_period_dates_year_boundary(self, parser):
        """Test extracting period dates across year boundary."""
        text = "December 12 - January 11, 2026"
        result = parser._extract_period_dates(text)
        assert result is not None
        start, end = result
        assert start == "2025-12-12"
        assert end == "2026-01-11"

    def test_extract_period_dates_same_year(self, parser):
        """Test extracting period dates within same year."""
        text = "June 12 - July 11, 2025"
        result = parser._extract_period_dates(text)
        assert result is not None
        start, end = result
        assert start == "2025-06-12"
        assert end == "2025-07-11"

    def test_extract_period_dates_not_found(self, parser):
        """Test None when period not found."""
        text = "No period information"
        result = parser._extract_period_dates(text)
        assert result is None


class TestPeriodFormats:
    """Bank-account and credit-card statements write their period differently."""

    def test_checking_period_with_full_dates(self):
        from expense_tracker.parsers.boa import BOAParser

        text = "Your Adv Plus Banking\nfor December 19, 2025 to January 20, 2026\nAccount number"
        assert BOAParser()._extract_period_dates(text) == ("2025-12-19", "2026-01-20")

    def test_credit_card_period_across_year_end(self):
        from expense_tracker.parsers.boa import BOAParser

        text = "Statement\nDecember 12 - January 11, 2026\n"
        assert BOAParser()._extract_period_dates(text) == ("2025-12-12", "2026-01-11")
