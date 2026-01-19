"""Shared pytest fixtures for expense tracker tests."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_transactions():
    """Sample transactions for testing categorization."""
    return [
        {"date": "2025-01-15", "description": "UBER TRIP", "amount": -25.50},
        {"date": "2025-01-16", "description": "WHOLE FOODS MARKET", "amount": -87.23},
        {"date": "2025-01-17", "description": "NETFLIX.COM", "amount": -15.99},
        {"date": "2025-01-18", "description": "SHELL GAS STATION", "amount": -45.00},
        {"date": "2025-01-19", "description": "APPLE.COM/BILL", "amount": -9.99},
    ]


@pytest.fixture
def sample_categorized_transactions():
    """Sample categorized transactions."""
    return [
        {"date": "2025-01-15", "description": "UBER TRIP", "amount": -25.50, "category": "Rideshare"},
        {"date": "2025-01-16", "description": "WHOLE FOODS MARKET", "amount": -87.23, "category": "Groceries"},
        {"date": "2025-01-17", "description": "NETFLIX.COM", "amount": -15.99, "category": "Entertainment"},
        {"date": "2025-01-18", "description": "SHELL GAS STATION", "amount": -45.00, "category": "Misc"},
        {"date": "2025-01-19", "description": "APPLE.COM/BILL", "amount": -9.99, "category": "Apple"},
    ]


@pytest.fixture
def sample_income_transactions():
    """Sample income transactions."""
    return [
        {"date": "2025-01-01", "description": "EMPLOYER DIRECT DEP", "amount": 3500.00},
        {"date": "2025-01-15", "description": "VENMO PAYMENT", "amount": 150.00},
    ]


@pytest.fixture
def sample_balances():
    """Sample account balances."""
    return {
        "checking_balance": 5432.10,
        "savings_balance": 12000.00,
        "credit_card_balance": 1234.56,
        "debt_payments": [
            {"description": "STUDENT LOAN", "amount": -500.00},
            {"description": "CAR PAYMENT", "amount": -350.00},
        ],
    }


# ============================================================================
# Bank Statement Text Fixtures
# ============================================================================

@pytest.fixture
def boa_checking_text():
    """Sample Bank of America checking statement text."""
    return """
Bank of America
Your Advantage Checking Account Statement
Account number: 1234567890

Statement period: December 11, 2025 - January 10, 2026

Beginning balance on December 11, 2025         $5,000.00

Deposits and other credits
12/15  Direct Deposit EMPLOYER INC                    2,500.00

Withdrawals and other debits
12/20  Debit Card Purchase WHOLE FOODS               -87.23
12/22  Online Transfer to Savings                   -500.00
12/28  Check 1234                                   -150.00

Ending balance on January 10, 2026              $6,762.77
"""


@pytest.fixture
def boa_credit_card_text():
    """Sample Bank of America credit card statement text."""
    return """
Bank of America
Credit Card Statement

Account Number ending in: 1234

Statement Closing Date: January 10, 2026
Payment Due Date: February 5, 2026

Previous Balance                              $500.00
Payments and Credits                         -$500.00
Purchases and Adjustments                   +$1,234.56
Fees Charged                                    $0.00

New Balance Total                           $1,234.56

Transactions

01/02  AMAZON.COM*123ABC    SEATTLE WA           45.99
01/05  UBER   *TRIP         SAN FRANCISCO        25.50
01/08  APPLE.COM/BILL       866-712-7753          9.99
"""


@pytest.fixture
def boa_savings_text():
    """Sample Bank of America savings statement text."""
    return """
Bank of America
Your Advantage Savings Account Statement
Account number: 9876543210

Statement period: December 11, 2025 - January 10, 2026

Beginning balance on December 11, 2025        $11,500.00

Deposits and other credits
12/22  Online Transfer from Checking               500.00

Ending balance on January 10, 2026            $12,000.00
"""


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for testing AI features."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='["Rideshare", "Groceries", "Entertainment"]')]
    mock_client.messages.create.return_value = mock_response
    return mock_client


@pytest.fixture
def mock_gspread_client():
    """Mock gspread client for testing Google Sheets."""
    mock_client = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()

    # Set up the mock chain
    mock_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_worksheet.col_values.return_value = ["Month", "1/2025", "2/2025", "3/2025"]
    mock_worksheet.row_values.return_value = ["1/2025", "", "", ""]

    return mock_client


@pytest.fixture
def mock_smtp():
    """Mock SMTP server for testing email notifications."""
    with patch("smtplib.SMTP") as mock:
        mock_server = MagicMock()
        mock.return_value.__enter__.return_value = mock_server
        yield mock_server


# ============================================================================
# Temporary File Fixtures
# ============================================================================

@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def temp_statements_dir(tmp_path):
    """Create a temporary statements directory with sample structure."""
    statements_dir = tmp_path / "statements"
    statements_dir.mkdir()

    # Create a sample month folder
    month_folder = statements_dir / "2025" / "December"
    month_folder.mkdir(parents=True)

    return statements_dir


@pytest.fixture
def temp_threshold_file(temp_data_dir):
    """Create a temporary threshold tracking file."""
    threshold_file = temp_data_dir / "spending_thresholds.json"
    threshold_file.write_text(json.dumps({"notified": {}}))
    return threshold_file


# ============================================================================
# Environment Fixtures
# ============================================================================

@pytest.fixture
def mock_env_vars():
    """Set up mock environment variables."""
    env_vars = {
        "ANTHROPIC_API_KEY": "test-api-key",
        "SMTP_EMAIL": "test@example.com",
        "SMTP_PASSWORD": "test-password",
        "NOTIFY_EMAIL": "notify@example.com",
        "GOOGLE_SHEET_ID": "test-sheet-id",
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def clean_env():
    """Ensure certain environment variables are not set."""
    vars_to_clear = ["ANTHROPIC_API_KEY", "SMTP_EMAIL", "SMTP_PASSWORD", "NOTIFY_EMAIL"]
    original_values = {k: os.environ.get(k) for k in vars_to_clear}

    for var in vars_to_clear:
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]
