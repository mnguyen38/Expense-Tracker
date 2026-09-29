"""Tests for Google Sheets integration."""

from unittest.mock import MagicMock, patch

import pytest

from expense_tracker.sheets import (
    CATEGORY_COLUMNS,
    INCOME_COLUMNS,
    NET_WORTH_COLUMNS,
    get_sheets_client,
    get_spreadsheet_id_from_url,
    get_statement_month,
    sync_income_to_sheet,
    sync_net_worth_to_sheet,
    sync_to_sheet,
)


class TestStatementMonth:
    """Tests for get_statement_month function."""

    def test_before_close_day(self):
        """Test transaction before statement close day."""
        # Jan 5 is before the 11th, so it's in January statement
        result = get_statement_month("2025-01-05")
        assert result == "1/2025"

    def test_on_close_day(self):
        """Test transaction on statement close day."""
        # Jan 11 is the close day, so it's in January statement
        result = get_statement_month("2025-01-11")
        assert result == "1/2025"

    def test_after_close_day(self):
        """Test transaction after statement close day."""
        # Jan 15 is after the 11th, so it's in February statement
        result = get_statement_month("2025-01-15")
        assert result == "2/2025"

    def test_december_year_boundary(self):
        """Test December transaction after close day goes to January next year."""
        # Dec 15 is after the 11th, so it's in January 2026 statement
        result = get_statement_month("2025-12-15")
        assert result == "1/2026"

    def test_december_before_close_day(self):
        """Test December transaction before close day stays in December."""
        # Dec 10 is before the 11th, so it's in December statement
        result = get_statement_month("2025-12-10")
        assert result == "12/2025"

    def test_last_day_of_month(self):
        """Test transaction on last day of month."""
        result = get_statement_month("2025-01-31")
        assert result == "2/2025"

    def test_first_day_of_month(self):
        """Test transaction on first day of month."""
        result = get_statement_month("2025-02-01")
        assert result == "2/2025"


class TestSpreadsheetIdFromUrl:
    """Tests for get_spreadsheet_id_from_url function."""

    def test_standard_url(self):
        """Test extracting ID from standard Google Sheets URL."""
        url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
        result = get_spreadsheet_id_from_url(url)
        assert result == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    def test_url_with_gid(self):
        """Test extracting ID from URL with gid parameter."""
        url = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0"
        result = get_spreadsheet_id_from_url(url)
        assert result == "abc123"

    def test_url_with_special_chars(self):
        """Test extracting ID with dashes and underscores."""
        url = "https://docs.google.com/spreadsheets/d/ab-cd_12-34/edit"
        result = get_spreadsheet_id_from_url(url)
        assert result == "ab-cd_12-34"

    def test_invalid_url_raises_error(self):
        """Test that invalid URL raises ValueError."""
        with pytest.raises(ValueError, match="Could not extract spreadsheet ID"):
            get_spreadsheet_id_from_url("https://google.com/invalid")


class TestColumnMappings:
    """Tests for column mapping constants."""

    def test_category_columns_complete(self):
        """Test that all expected categories have columns."""
        required_categories = [
            "Housing",
            "Groceries",
            "Eating Out",
            "Rideshare",
            "Entertainment",
            "Misc",
            "Apple",
            "Subscriptions",
        ]
        for cat in required_categories:
            assert cat in CATEGORY_COLUMNS

    def test_income_columns_complete(self):
        """Test that income columns are defined."""
        assert "Month" in INCOME_COLUMNS
        assert "Other Income" in INCOME_COLUMNS

    def test_net_worth_columns_complete(self):
        """Test that net worth columns are defined."""
        assert "Checking" in NET_WORTH_COLUMNS
        assert "Savings" in NET_WORTH_COLUMNS
        assert "Other Debt" in NET_WORTH_COLUMNS


class TestGetSheetsClient:
    """Tests for get_sheets_client function."""

    def test_missing_credentials_raises_error(self, tmp_path):
        """Test that missing credentials file raises error."""
        with pytest.raises(FileNotFoundError):
            get_sheets_client(tmp_path / "nonexistent.json")

    @patch("expense_tracker.sheets.gspread.authorize")
    @patch("expense_tracker.sheets.Credentials.from_service_account_file")
    def test_creates_client_with_credentials(self, mock_credentials, mock_authorize, tmp_path):
        """Test that client is created with valid credentials."""
        # Create a mock credentials file
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"type": "service_account"}')

        mock_creds = MagicMock()
        mock_credentials.return_value = mock_creds
        mock_client = MagicMock()
        mock_authorize.return_value = mock_client

        result = get_sheets_client(creds_file)

        assert result == mock_client
        mock_authorize.assert_called_once_with(mock_creds)


class TestSyncToSheet:
    """Tests for sync_to_sheet function."""

    @pytest.fixture
    def mock_worksheet(self):
        """Create a mock worksheet."""
        worksheet = MagicMock()
        worksheet.col_values.return_value = ["Month", "1/2025", "2/2025"]
        worksheet.acell.return_value = MagicMock(value="50.00")
        return worksheet

    @pytest.fixture
    def mock_spreadsheet(self, mock_worksheet):
        """Create a mock spreadsheet."""
        spreadsheet = MagicMock()
        spreadsheet.worksheet.return_value = mock_worksheet
        return spreadsheet

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_to_existing_month(self, mock_get_client, mock_spreadsheet, sample_categorized_transactions):
        """Test syncing to an existing month row."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        result = sync_to_sheet(
            spreadsheet_id="test-id",
            transactions=sample_categorized_transactions,
            month="1/2025",
            credentials_path=None,
        )

        assert result["month"] == "1/2025"
        assert result["row"] == 2  # Row 2 has "1/2025"

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_to_new_month(self, mock_get_client, mock_spreadsheet, sample_categorized_transactions):
        """Test syncing to a new month row."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        result = sync_to_sheet(
            spreadsheet_id="test-id",
            transactions=sample_categorized_transactions,
            month="3/2025",  # New month not in existing rows
            credentials_path=None,
        )

        assert result["month"] == "3/2025"
        assert result["row"] == 4  # Appended after existing 3 rows

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_calculates_totals(self, mock_get_client, mock_spreadsheet, sample_categorized_transactions):
        """Test that category totals are calculated."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        result = sync_to_sheet(
            spreadsheet_id="test-id",
            transactions=sample_categorized_transactions,
            month="1/2025",
            credentials_path=None,
        )

        assert result["total_spent"] > 0
        assert len(result["categories_updated"]) > 0

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_replace_mode(self, mock_get_client, mock_spreadsheet, sample_categorized_transactions):
        """Test replace mode clears existing values."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        result = sync_to_sheet(
            spreadsheet_id="test-id",
            transactions=sample_categorized_transactions,
            month="1/2025",
            mode="replace",
            credentials_path=None,
        )

        assert result["mode"] == "replace"
        # Verify batch_update was called (for clearing)
        mock_spreadsheet.worksheet.return_value.batch_update.assert_called()


class TestSyncIncomeToSheet:
    """Tests for sync_income_to_sheet function."""

    @pytest.fixture
    def mock_worksheet(self):
        """Create a mock worksheet."""
        worksheet = MagicMock()
        worksheet.col_values.return_value = ["Month", "1/2025", "2/2025"]
        worksheet.acell.return_value = MagicMock(value="100.00")
        return worksheet

    @pytest.fixture
    def mock_spreadsheet(self, mock_worksheet):
        """Create a mock spreadsheet."""
        spreadsheet = MagicMock()
        spreadsheet.worksheet.return_value = mock_worksheet
        return spreadsheet

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_income_empty_list(self, mock_get_client):
        """Test syncing empty income list."""
        result = sync_income_to_sheet(
            spreadsheet_id="test-id",
            income_transactions=[],
            month="1/2025",
        )

        assert result["total_income"] == 0
        assert result["row"] is None

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_income_calculates_total(
        self, mock_get_client, mock_spreadsheet, sample_income_transactions
    ):
        """Test that income total is calculated."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        result = sync_income_to_sheet(
            spreadsheet_id="test-id",
            income_transactions=sample_income_transactions,
            month="1/2025",
            mode="replace",
        )

        assert result["total_income"] == 3650.00  # 3500 + 150
        assert result["transactions_count"] == 2

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_income_add_mode(self, mock_get_client, mock_spreadsheet, sample_income_transactions):
        """Test add mode adds to existing value."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        result = sync_income_to_sheet(
            spreadsheet_id="test-id",
            income_transactions=sample_income_transactions,
            month="1/2025",
            mode="add",
        )

        # Should add to existing 100.00
        assert result["total_income"] == 3750.00  # 100 + 3500 + 150


class TestSyncNetWorthToSheet:
    """Tests for sync_net_worth_to_sheet function."""

    @pytest.fixture
    def mock_worksheet(self):
        """Create a mock worksheet."""
        worksheet = MagicMock()
        worksheet.col_values.return_value = ["Month", "1/2025", "2/2025"]
        return worksheet

    @pytest.fixture
    def mock_spreadsheet(self, mock_worksheet):
        """Create a mock spreadsheet."""
        spreadsheet = MagicMock()
        spreadsheet.worksheet.return_value = mock_worksheet
        return spreadsheet

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_net_worth(self, mock_get_client, mock_spreadsheet, sample_balances):
        """Test syncing net worth data."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        result = sync_net_worth_to_sheet(
            spreadsheet_id="test-id",
            balances=sample_balances,
            month="1/2025",
        )

        assert result["month"] == "1/2025"
        assert result["checking_balance"] == 5432.10
        assert result["savings_balance"] == 12000.00
        assert result["credit_card_balance"] == 1234.56
        assert result["debt_payments"] == 850.00  # 500 + 350

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_net_worth_partial_balances(self, mock_get_client, mock_spreadsheet):
        """Test syncing with partial balance data."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        balances = {
            "checking_balance": 1000.00,
            "savings_balance": None,
            "credit_card_balance": None,
            "debt_payments": [],
        }

        result = sync_net_worth_to_sheet(
            spreadsheet_id="test-id",
            balances=balances,
            month="1/2025",
        )

        assert result["checking_balance"] == 1000.00
        assert result["savings_balance"] is None
        assert result["debt_payments"] == 0

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_sync_net_worth_creates_new_row(self, mock_get_client, mock_spreadsheet):
        """Test that new month row is created if not exists."""
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        balances = {
            "checking_balance": 1000.00,
            "savings_balance": None,
            "credit_card_balance": None,
            "debt_payments": [],
        }

        result = sync_net_worth_to_sheet(
            spreadsheet_id="test-id",
            balances=balances,
            month="3/2025",  # New month
        )

        assert result["row"] == 4  # Appended


class TestAutoMonthDetection:
    """Tests for automatic month detection from transactions."""

    @patch("expense_tracker.sheets.get_sheets_client")
    def test_auto_detect_month_from_transactions(self, mock_get_client):
        """Test that month is auto-detected from transaction dates."""
        mock_client = MagicMock()
        mock_spreadsheet = MagicMock()
        mock_worksheet = MagicMock()
        mock_worksheet.col_values.return_value = ["Month"]
        mock_spreadsheet.worksheet.return_value = mock_worksheet
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        transactions = [
            {"date": "2025-01-05", "description": "Test", "amount": -10.00, "category": "Misc"},
            {"date": "2025-01-08", "description": "Test", "amount": -20.00, "category": "Misc"},
        ]

        result = sync_to_sheet(
            spreadsheet_id="test-id",
            transactions=transactions,
            month=None,  # Auto-detect
        )

        assert result["month"] == "1/2025"
