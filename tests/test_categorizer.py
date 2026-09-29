"""Tests for AI-powered transaction categorizer."""

import json
from unittest.mock import MagicMock, patch

import pytest

from expense_tracker.categorizer import (
    BATCH_SIZE,
    CATEGORIES,
    _categorize_batch,
    _find_closest_category,
    categorize_transactions,
    get_summary,
)


class TestCategories:
    """Tests for category constants."""

    def test_categories_not_empty(self):
        """Test that CATEGORIES list is not empty."""
        assert len(CATEGORIES) > 0

    def test_required_categories_present(self):
        """Test that key categories are present."""
        required = ["Housing", "Groceries", "Eating Out", "Rideshare", "Misc", "Subscriptions"]
        for cat in required:
            assert cat in CATEGORIES

    def test_batch_size_reasonable(self):
        """Test that batch size is reasonable."""
        assert BATCH_SIZE > 0
        assert BATCH_SIZE <= 50


class TestFindClosestCategory:
    """Tests for _find_closest_category function."""

    def test_exact_match(self):
        """Test exact category match."""
        assert _find_closest_category("Housing") == "Housing"
        assert _find_closest_category("Groceries") == "Groceries"

    def test_case_insensitive_match(self):
        """Test case-insensitive matching."""
        assert _find_closest_category("housing") == "Housing"
        assert _find_closest_category("GROCERIES") == "Groceries"

    def test_partial_match(self):
        """Test partial matching."""
        assert _find_closest_category("Eating") == "Eating Out"
        assert _find_closest_category("eating out somewhere") == "Eating Out"

    def test_no_match_returns_misc(self):
        """Test that unmatched categories return Misc."""
        assert _find_closest_category("Unknown Category XYZ") == "Misc"
        assert _find_closest_category("Random") == "Misc"


class TestCategorizeBatch:
    """Tests for _categorize_batch function."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Anthropic client."""
        client = MagicMock()
        return client

    def test_categorize_batch_success(self, mock_client, sample_transactions):
        """Test successful batch categorization."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='["Rideshare", "Groceries", "Entertainment", "Misc", "Subscriptions"]')
        ]
        mock_client.messages.create.return_value = mock_response

        result = _categorize_batch(mock_client, sample_transactions)

        assert len(result) == 5
        assert result[0] == "Rideshare"
        assert result[1] == "Groceries"
        assert result[4] == "Subscriptions"

    def test_categorize_batch_validates_categories(self, mock_client, sample_transactions):
        """Test that invalid categories are normalized."""
        mock_response = MagicMock()
        # Include an invalid category
        mock_response.content = [
            MagicMock(text='["Rideshare", "Invalid", "Entertainment", "Misc", "Subscriptions"]')
        ]
        mock_client.messages.create.return_value = mock_response

        result = _categorize_batch(mock_client, sample_transactions)

        assert len(result) == 5
        # "Invalid" should be converted to closest match or Misc
        assert result[1] in CATEGORIES

    def test_categorize_batch_pads_missing(self, mock_client, sample_transactions):
        """Test that missing categories are padded with Misc."""
        mock_response = MagicMock()
        # Return fewer categories than transactions
        mock_response.content = [MagicMock(text='["Rideshare", "Groceries"]')]
        mock_client.messages.create.return_value = mock_response

        result = _categorize_batch(mock_client, sample_transactions)

        assert len(result) == 5
        assert result[0] == "Rideshare"
        assert result[1] == "Groceries"
        assert result[2] == "Misc"  # Padded

    def test_categorize_batch_truncates_extra(self, mock_client, sample_transactions):
        """Test that extra categories are truncated."""
        mock_response = MagicMock()
        # Return more categories than transactions
        mock_response.content = [
            MagicMock(
                text='["Rideshare", "Groceries", "Entertainment", "Misc", "Subscriptions", "Extra1", "Extra2"]'
            )
        ]
        mock_client.messages.create.return_value = mock_response

        result = _categorize_batch(mock_client, sample_transactions)

        assert len(result) == 5

    def test_categorize_batch_handles_invalid_json(self, mock_client, sample_transactions):
        """Test handling of invalid JSON response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON")]
        mock_client.messages.create.return_value = mock_response

        result = _categorize_batch(mock_client, sample_transactions)

        # Should return all Misc
        assert len(result) == 5
        assert all(cat == "Misc" for cat in result)

    def test_categorize_batch_handles_non_list_response(self, mock_client, sample_transactions):
        """Test handling when response is not a list."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"category": "Housing"}')]
        mock_client.messages.create.return_value = mock_response

        result = _categorize_batch(mock_client, sample_transactions)

        # Should return all Misc
        assert len(result) == 5
        assert all(cat == "Misc" for cat in result)


class TestCategorizeTransactions:
    """Tests for categorize_transactions function."""

    def test_empty_transactions(self):
        """Test with empty transaction list."""
        result = categorize_transactions([])
        assert result == []

    def test_requires_api_key(self, sample_transactions, clean_env):
        """Test that missing API key raises error."""
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not found"):
            categorize_transactions(sample_transactions)

    def test_accepts_explicit_api_key(self, sample_transactions):
        """Test that explicit API key is used."""
        with patch("expense_tracker.categorizer.anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='["Misc"]' * 5)]
            mock_client.messages.create.return_value = mock_response

            # This should not raise an error
            categorize_transactions(sample_transactions[:1], api_key="explicit-key")

            mock_anthropic.assert_called_with(api_key="explicit-key")

    @patch("expense_tracker.categorizer.anthropic.Anthropic")
    def test_adds_category_to_transactions(self, mock_anthropic, sample_transactions):
        """Test that category is added to each transaction."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='["Rideshare", "Groceries", "Entertainment", "Misc", "Subscriptions"]')
        ]
        mock_client.messages.create.return_value = mock_response

        result = categorize_transactions(sample_transactions, api_key="test-key")

        assert len(result) == 5
        for txn in result:
            assert "category" in txn
            assert txn["category"] in CATEGORIES

    @patch("expense_tracker.categorizer.anthropic.Anthropic")
    def test_preserves_original_fields(self, mock_anthropic, sample_transactions):
        """Test that original transaction fields are preserved."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='["Rideshare", "Groceries", "Entertainment", "Misc", "Subscriptions"]')
        ]
        mock_client.messages.create.return_value = mock_response

        result = categorize_transactions(sample_transactions, api_key="test-key")

        for i, txn in enumerate(result):
            assert txn["date"] == sample_transactions[i]["date"]
            assert txn["description"] == sample_transactions[i]["description"]
            assert txn["amount"] == sample_transactions[i]["amount"]

    @patch("expense_tracker.categorizer.anthropic.Anthropic")
    def test_batches_large_lists(self, mock_anthropic):
        """Test that large transaction lists are batched."""
        # Create more transactions than BATCH_SIZE
        transactions = [
            {"date": f"2025-01-{i:02d}", "description": f"Test {i}", "amount": -10.0}
            for i in range(1, BATCH_SIZE + 10)
        ]

        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(["Misc"] * BATCH_SIZE))]
        mock_client.messages.create.return_value = mock_response

        result = categorize_transactions(transactions, api_key="test-key")

        # Should have made 2 API calls (1 full batch + 1 partial)
        assert mock_client.messages.create.call_count == 2
        assert len(result) == BATCH_SIZE + 9


class TestGetSummary:
    """Tests for get_summary function."""

    def test_empty_transactions(self):
        """Test summary with empty transactions."""
        result = get_summary([])

        assert result["total_spending"] == 0.0
        assert result["total_income"] == 0.0
        assert result["transaction_count"] == 0
        assert result["by_category"] == {}

    def test_calculates_total_spending(self, sample_categorized_transactions):
        """Test that total spending is calculated correctly."""
        result = get_summary(sample_categorized_transactions)

        # All amounts are negative except none in this fixture
        expected_spending = sum(abs(t["amount"]) for t in sample_categorized_transactions)
        assert result["total_spending"] == round(expected_spending, 2)

    def test_calculates_total_income(self):
        """Test that total income is calculated correctly."""
        transactions = [
            {"date": "2025-01-15", "description": "DEPOSIT", "amount": 2000.00, "category": "Misc"},
            {"date": "2025-01-16", "description": "UBER", "amount": -25.00, "category": "Rideshare"},
        ]
        result = get_summary(transactions)

        assert result["total_income"] == 2000.00
        assert result["total_spending"] == 25.00

    def test_groups_by_category(self, sample_categorized_transactions):
        """Test that transactions are grouped by category."""
        result = get_summary(sample_categorized_transactions)

        assert "Rideshare" in result["by_category"]
        assert "Groceries" in result["by_category"]
        assert result["by_category"]["Rideshare"]["count"] == 1
        assert result["by_category"]["Groceries"]["count"] == 1

    def test_category_totals(self, sample_categorized_transactions):
        """Test that category totals are correct."""
        result = get_summary(sample_categorized_transactions)

        assert result["by_category"]["Rideshare"]["total"] == -25.50
        assert result["by_category"]["Groceries"]["total"] == -87.23

    def test_includes_transaction_details(self, sample_categorized_transactions):
        """Test that transaction details are included in category."""
        result = get_summary(sample_categorized_transactions)

        assert len(result["by_category"]["Rideshare"]["transactions"]) == 1
        txn = result["by_category"]["Rideshare"]["transactions"][0]
        assert txn["description"] == "UBER TRIP"
        assert txn["amount"] == -25.50

    def test_handles_missing_category(self):
        """Test handling transactions without category."""
        transactions = [
            {"date": "2025-01-15", "description": "TEST", "amount": -10.00},
        ]
        result = get_summary(transactions)

        assert "Misc" in result["by_category"]
        assert result["by_category"]["Misc"]["count"] == 1

    def test_rounds_totals(self):
        """Test that totals are rounded to 2 decimal places."""
        transactions = [
            {"date": "2025-01-15", "description": "TEST1", "amount": -10.333, "category": "Misc"},
            {"date": "2025-01-16", "description": "TEST2", "amount": -10.666, "category": "Misc"},
        ]
        result = get_summary(transactions)

        # 10.333 + 10.666 = 20.999
        assert result["total_spending"] == 21.0
        assert result["by_category"]["Misc"]["total"] == -21.0


class TestGetSummaryWithMixedTransactions:
    """Tests for get_summary with mixed expense/income transactions."""

    def test_mixed_transactions(self):
        """Test summary with both expenses and income."""
        transactions = [
            {"date": "2025-01-01", "description": "SALARY", "amount": 5000.00, "category": "Misc"},
            {"date": "2025-01-05", "description": "RENT", "amount": -1500.00, "category": "Housing"},
            {"date": "2025-01-10", "description": "GROCERIES", "amount": -200.00, "category": "Groceries"},
            {"date": "2025-01-15", "description": "REFUND", "amount": 50.00, "category": "Misc"},
        ]
        result = get_summary(transactions)

        assert result["total_income"] == 5050.00
        assert result["total_spending"] == 1700.00
        assert result["transaction_count"] == 4

    def test_net_calculation(self):
        """Test that we can calculate net from summary."""
        transactions = [
            {"date": "2025-01-01", "description": "SALARY", "amount": 3000.00, "category": "Misc"},
            {"date": "2025-01-05", "description": "RENT", "amount": -1000.00, "category": "Housing"},
        ]
        result = get_summary(transactions)

        net = result["total_income"] - result["total_spending"]
        assert net == 2000.00


class TestStructuredOutput:
    """Categorization requests are constrained to the category list."""

    def test_schema_restricts_to_categories(self, sample_transactions):
        from expense_tracker.categorizer import CATEGORY_SCHEMA

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({"categories": ["Rideshare"] * 5}))]
        mock_client.messages.create.return_value = mock_response

        result = _categorize_batch(mock_client, sample_transactions)

        assert result == ["Rideshare"] * 5
        fmt = mock_client.messages.create.call_args.kwargs["output_config"]["format"]
        assert fmt["schema"] == CATEGORY_SCHEMA
        item = CATEGORY_SCHEMA["properties"]["merchants"]["items"]
        assert item["properties"]["category"]["enum"] == CATEGORIES
        assert item["required"] == ["name", "category"]

    def test_model_can_be_overridden(self, sample_transactions, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"categories": []}')]
        mock_client.messages.create.return_value = mock_response

        _categorize_batch(mock_client, sample_transactions)

        assert mock_client.messages.create.call_args.kwargs["model"] == "claude-opus-5"


class TestMerchantNames:
    """Claude returns a clean name with each category, and never sees personal fields."""

    def _client(self, payload):
        client = MagicMock()
        response = MagicMock()
        response.content = [MagicMock(text=json.dumps(payload))]
        client.messages.create.return_value = response
        return client

    def test_names_come_back_with_categories(self):
        txns = [
            {"description": "PL*StateFinancia DES:WEB PMTS", "amount": -3850.0},
            {"description": "easyJetKBQTWC2 Luton", "amount": -241.08},
        ]
        client = self._client(
            {
                "merchants": [
                    {"name": "State Financial", "category": "Housing"},
                    {"name": "easyJet", "category": "Travel"},
                ]
            }
        )
        assert _categorize_batch(client, txns, with_names=True) == [
            ("Housing", "State Financial"),
            ("Travel", "easyJet"),
        ]
        assert _categorize_batch(client, txns) == ["Housing", "Travel"]

    def test_personal_fields_never_reach_the_prompt(self):
        txns = [
            {
                "description": "PL*PAYLEASE DES:WEB PMTS ID:LS92D8 INDN:Jane Doe CO ID:9000287225",
                "amount": -2.58,
            }
        ]
        client = self._client({"merchants": [{"name": "PayLease", "category": "Housing"}]})
        _categorize_batch(client, txns, with_names=True)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Jane Doe" not in prompt and "LS92D8" not in prompt and "9000287225" not in prompt
        assert "PAYLEASE" in prompt

    def test_categorize_transactions_carries_the_name(self):
        with patch("expense_tracker.categorizer.anthropic.Anthropic") as anthropic_cls:
            anthropic_cls.return_value = self._client(
                {"merchants": [{"name": "Whole Foods", "category": "Groceries"}]}
            )
            out = categorize_transactions(
                [{"description": "WHOLEFDS SYM 10031", "amount": -12.0}], api_key="k"
            )
        assert out[0]["category"] == "Groceries" and out[0]["merchant_name"] == "Whole Foods"

    def test_suggest_names_batches_and_pads(self):
        from expense_tracker.categorizer import suggest_names

        with patch("expense_tracker.categorizer.anthropic.Anthropic") as anthropic_cls:
            anthropic_cls.return_value = self._client({"names": ["Ovpay"]})
            names = suggest_names(["NLOVLD5D9X4PRQYJZ7 WWW.OVPAY.NL", "SHOP 2/ LOUNGE 2"], api_key="k")
        assert names == ["Ovpay", None]
