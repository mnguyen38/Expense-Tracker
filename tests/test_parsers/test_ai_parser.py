"""Tests for AI-powered statement parser."""

import json
import pytest
from unittest.mock import MagicMock, patch

from parsers.ai_parser import AIParser


class TestAIParser:
    """Tests for AIParser class."""

    @pytest.fixture
    def parser(self):
        """Create an AIParser with a mock API key."""
        return AIParser(api_key="test-api-key")

    @pytest.fixture
    def mock_ai_response(self):
        """Create a mock AI response."""
        return {
            "bank_name": "Test Bank",
            "currency": "USD",
            "statement_type": "checking",
            "statement_period": {
                "start": "2025-01-01",
                "end": "2025-01-31"
            },
            "opening_balance": 1000.00,
            "closing_balance": 1500.00,
            "transactions": [
                {
                    "date": "2025-01-15",
                    "description": "AMAZON PURCHASE",
                    "amount": -50.00,
                    "is_internal_transfer": False
                },
                {
                    "date": "2025-01-20",
                    "description": "DIRECT DEPOSIT",
                    "amount": 2000.00,
                    "is_internal_transfer": False
                },
                {
                    "date": "2025-01-25",
                    "description": "Transfer to Savings",
                    "amount": -500.00,
                    "is_internal_transfer": True
                }
            ]
        }

    # =========================================================================
    # Detection Tests
    # =========================================================================

    def test_detect_always_returns_low_confidence(self, parser):
        """Test that AI parser always returns low confidence as fallback."""
        assert parser.detect("Any bank statement text") == 0.1
        assert parser.detect("") == 0.1
        assert parser.detect("Bank of America") == 0.1

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        parser = AIParser(api_key="explicit-key")
        assert parser.api_key == "explicit-key"

    def test_init_from_environment(self, mock_env_vars):
        """Test initialization from environment variable."""
        parser = AIParser()
        assert parser.api_key == "test-api-key"

    def test_init_no_api_key(self, clean_env):
        """Test initialization without API key."""
        parser = AIParser()
        assert parser.api_key is None

    # =========================================================================
    # Parse Tests
    # =========================================================================

    def test_parse_requires_api_key(self, tmp_path, clean_env):
        """Test that parse raises error without API key."""
        parser = AIParser()
        pdf_path = tmp_path / "test.pdf"

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not found"):
            parser.parse(pdf_path, "Some statement text")

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_success(self, mock_anthropic, parser, mock_ai_response, tmp_path):
        """Test successful parsing."""
        # Set up mock
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(mock_ai_response))]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, "Sample bank statement text")

        assert result.bank_name == "Test Bank"
        assert result.currency == "USD"
        assert result.statement_type == "checking"
        assert result.opening_balance == 1000.00
        assert result.closing_balance == 1500.00

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_separates_transactions(self, mock_anthropic, parser, mock_ai_response, tmp_path):
        """Test that parse correctly separates expenses and income."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(mock_ai_response))]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, "Sample statement")

        # Should have 2 non-internal transactions
        assert len(result.expenses) == 1
        assert result.expenses[0]["description"] == "AMAZON PURCHASE"
        assert len(result.income) == 1
        assert result.income[0]["description"] == "DIRECT DEPOSIT"

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_filters_internal_transfers(self, mock_anthropic, parser, mock_ai_response, tmp_path):
        """Test that internal transfers are filtered from expenses/income."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(mock_ai_response))]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, "Sample statement")

        # Internal transfer should be in transactions but not in expenses
        assert len(result.transactions) == 3
        assert len(result.expenses) == 1  # Only the non-internal expense

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_handles_markdown_response(self, mock_anthropic, parser, mock_ai_response, tmp_path):
        """Test that markdown-wrapped JSON is handled correctly."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        # Wrap response in markdown code block
        markdown_response = f"```json\n{json.dumps(mock_ai_response)}\n```"
        mock_response.content = [MagicMock(text=markdown_response)]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, "Sample statement")

        assert result.bank_name == "Test Bank"

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_handles_invalid_json(self, mock_anthropic, parser, tmp_path):
        """Test that invalid JSON response raises error."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON")]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"

        with pytest.raises(ValueError, match="Failed to parse AI response as JSON"):
            parser.parse(pdf_path, "Sample statement")

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_truncates_long_text(self, mock_anthropic, parser, mock_ai_response, tmp_path):
        """Test that very long text is truncated."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(mock_ai_response))]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"
        long_text = "x" * 100000  # Very long text

        result = parser.parse(pdf_path, long_text)

        # Verify the API was called with truncated text
        call_args = mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "[truncated]" in prompt

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_generates_bank_id(self, mock_anthropic, parser, tmp_path):
        """Test that bank_id is generated from bank_name."""
        response = {
            "bank_name": "Wells Fargo Bank",
            "currency": "USD",
            "statement_type": "checking",
            "transactions": []
        }

        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(response))]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, "Sample statement")

        assert result.bank_id == "wells_fargo_bank"

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_detects_debt_payments(self, mock_anthropic, parser, tmp_path):
        """Test that debt payments are correctly identified."""
        response = {
            "bank_name": "Test Bank",
            "currency": "USD",
            "statement_type": "checking",
            "transactions": [
                {
                    "date": "2025-01-15",
                    "description": "STUDENT LOAN PAYMENT",
                    "amount": -500.00,
                    "is_internal_transfer": False
                }
            ]
        }

        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(response))]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, "Sample statement")

        assert len(result.debt_payments) == 1
        assert result.debt_payments[0]["description"] == "STUDENT LOAN PAYMENT"

    @patch("parsers.ai_parser.anthropic.Anthropic")
    def test_parse_credit_card_no_income(self, mock_anthropic, parser, tmp_path):
        """Test that credit card payments aren't counted as income."""
        response = {
            "bank_name": "Test Bank",
            "currency": "USD",
            "statement_type": "credit_card",
            "transactions": [
                {
                    "date": "2025-01-15",
                    "description": "PAYMENT THANK YOU",
                    "amount": 500.00,
                    "is_internal_transfer": False
                }
            ]
        }

        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(response))]
        mock_client.messages.create.return_value = mock_response

        pdf_path = tmp_path / "test.pdf"
        result = parser.parse(pdf_path, "Sample statement")

        assert len(result.income) == 0


class TestAIParserDefaults:
    """Test default values and attributes."""

    def test_default_attributes(self):
        """Test default parser attributes."""
        parser = AIParser(api_key="test")
        assert parser.bank_id == "ai_parsed"
        assert parser.bank_name == "AI Detected"
        assert parser.currency == "USD"
