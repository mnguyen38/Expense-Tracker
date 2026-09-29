"""Google Sheets integration for expense tracking."""

import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from .config import default_home

# Bank statement closes on the 11th of each month
# Dec 12 - Jan 11 = January statement
# Jan 12 - Feb 11 = February statement
STATEMENT_CLOSE_DAY = 11

# Google Sheets API scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column mapping: category name -> column letter
# NOTE: You'll need to add "Travel" and "Subscriptions" columns to your Google Sheet
CATEGORY_COLUMNS = {
    "Housing": "D",
    "Gas (Home)": "E",
    "Electric": "F",
    "Internet": "G",
    "Insurance": "H",
    "Groceries": "I",
    "Eating Out": "J",
    "Phone": "K",
    "Rideshare": "L",
    "Public Transit": "M",
    "Entertainment": "N",
    "Clothing": "O",
    "Self Care": "P",
    "Dry Cleaning": "Q",
    "Gym": "R",
    "Music": "S",
    "Education": "T",
    "Medical": "U",
    "Gifts": "V",
    "Apple": "W",
    "Fees": "X",
    "Misc": "Y",
    "Travel": "Z",
    "Subscriptions": "AA",
}


def get_statement_month(date_str: str) -> str:
    """
    Convert a transaction date to its statement month.

    Statements close on STATEMENT_CLOSE_DAY (the 11th), so:
    - Dec 12 - Jan 11 → "1/2026" (January statement)
    - Jan 12 - Feb 11 → "2/2026" (February statement)

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Month string like "1/2026"
    """
    date = datetime.strptime(date_str, "%Y-%m-%d")

    if date.day <= STATEMENT_CLOSE_DAY:
        # Transaction is in current month's statement
        return f"{date.month}/{date.year}"
    else:
        # Transaction is in next month's statement
        if date.month == 12:
            return f"1/{date.year + 1}"
        else:
            return f"{date.month + 1}/{date.year}"


def _infer_statement_month(transactions: list[dict]) -> str | None:
    """Most common statement month among the transactions' dates."""
    dates = [t["date"] for t in transactions if t.get("date")]
    if not dates:
        return None
    return Counter(get_statement_month(d) for d in dates).most_common(1)[0][0]


def _find_or_create_month_row(worksheet, month: str) -> int:
    """Return the 1-indexed row whose column A equals `month`, appending one if absent."""
    month_col = worksheet.col_values(1)
    # Limit scan to first 500 rows to avoid scanning entire worksheet
    for i, cell in enumerate(month_col[:500]):
        if cell == month:
            return i + 1

    row_idx = len(month_col) + 1
    worksheet.update_cell(row_idx, 1, month)
    return row_idx


def get_sheets_client(credentials_path: str | Path | None = None) -> gspread.Client:
    """
    Create an authenticated Google Sheets client.

    Args:
        credentials_path: Path to service account JSON file.
                         Defaults to GOOGLE_CREDENTIALS_PATH env var or credentials.json

    Returns:
        Authenticated gspread client
    """
    if credentials_path is None:
        credentials_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", default_home() / "credentials.json")

    credentials_path = Path(credentials_path)
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google credentials not found at {credentials_path}\n"
            "Please download your service account JSON from Google Cloud Console."
        )

    credentials = Credentials.from_service_account_file(str(credentials_path), scopes=SCOPES)
    return gspread.authorize(credentials)


def sync_to_sheet(
    spreadsheet_id: str,
    transactions: list[dict],
    month: str | None = None,
    credentials_path: str | Path | None = None,
    mode: str = "add",
) -> dict:
    """
    Sync categorized transactions to a Google Sheet.

    Args:
        spreadsheet_id: The Google Sheet ID (from the URL)
        transactions: List of categorized transaction dicts
        month: Month string like "1/2026" (defaults to current month from transactions)
        credentials_path: Path to service account JSON
        mode: "add" to add to existing values (email sync),
              "replace" to overwrite (statement sync - source of truth)

    Returns:
        Dict with sync results
    """
    client = get_sheets_client(credentials_path)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet("Out")  # Use "Out" worksheet

    if month is None:
        month = _infer_statement_month(transactions)

    row_idx = _find_or_create_month_row(worksheet, month)

    # Aggregate spending by category
    category_totals = {}
    for txn in transactions:
        category = txn.get("category", "Misc")
        amount = txn.get("amount", 0)

        # Only count spending (negative amounts)
        if amount < 0:
            if category not in category_totals:
                category_totals[category] = 0.0
            category_totals[category] += abs(amount)

    # If mode is "replace", clear all category columns first
    if mode == "replace":
        clear_updates = []
        for col in CATEGORY_COLUMNS.values():
            clear_updates.append({"range": f"{col}{row_idx}", "values": [[0]]})
        # Note: Column C has its own formula, don't touch it
        worksheet.batch_update(clear_updates)

    # If mode is "add", get existing values and add to them
    if mode == "add":
        for category in category_totals:
            if category in CATEGORY_COLUMNS:
                col = CATEGORY_COLUMNS[category]
                cell = f"{col}{row_idx}"
                existing = worksheet.acell(cell).value
                if existing:
                    try:
                        category_totals[category] += float(existing)
                    except (ValueError, TypeError):
                        pass  # Keep new value if existing is not a number

    # Update each category column
    updates = []
    for category, total in category_totals.items():
        if category not in CATEGORY_COLUMNS:
            print(f"Warning: Category '{category}' not in CATEGORY_COLUMNS mapping, skipping")
            continue
        col = CATEGORY_COLUMNS[category]
        cell = f"{col}{row_idx}"
        updates.append({"range": cell, "values": [[round(total, 2)]]})

    # Calculate total spent for display (Column C has its own formula in the sheet)
    total_spent = sum(category_totals.values())

    # Batch update all cells
    if updates:
        worksheet.batch_update(updates)

    return {
        "month": month,
        "row": row_idx,
        "total_spent": round(total_spent, 2),
        "categories_updated": list(category_totals.keys()),
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
        "mode": mode,
    }


def get_spreadsheet_id_from_url(url: str) -> str:
    """Extract spreadsheet ID from a Google Sheets URL."""
    # URL format: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit...
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract spreadsheet ID from URL: {url}")


# Income sheet column mapping
# Columns: Month, Gross Income, 401k Match, Fed Income Tax, Social Security, Medicare, State Income Tax, Other Income
INCOME_COLUMNS = {
    "Month": "A",
    "Gross Income": "B",
    "401k Match": "C",
    "Fed Income Tax": "D",
    "Social Security": "E",
    "Medicare": "F",
    "State Income Tax": "G",
    "Other Income": "H",
}


def sync_income_to_sheet(
    spreadsheet_id: str,
    income_transactions: list[dict],
    month: str | None = None,
    credentials_path: str | Path | None = None,
    mode: str = "add",
) -> dict:
    """
    Sync income transactions to the "In" sheet.

    Deposits from checking/savings accounts go to "Other Income" column.

    Args:
        spreadsheet_id: The Google Sheet ID (from the URL)
        income_transactions: List of income transaction dicts (positive amounts)
        month: Month string like "1/2026" (defaults to current month from transactions)
        credentials_path: Path to service account JSON
        mode: "add" to add to existing values, "replace" to overwrite

    Returns:
        Dict with sync results
    """
    if not income_transactions:
        return {
            "month": month,
            "row": None,
            "total_income": 0,
            "message": "No income transactions to sync",
        }

    client = get_sheets_client(credentials_path)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet("In")

    if month is None:
        month = _infer_statement_month(income_transactions)

    row_idx = _find_or_create_month_row(worksheet, month)

    # Calculate total income from deposits (positive amounts)
    total_income = sum(t.get("amount", 0) for t in income_transactions if t.get("amount", 0) > 0)

    # Get current value in Other Income column
    other_income_col = INCOME_COLUMNS["Other Income"]
    cell = f"{other_income_col}{row_idx}"

    if mode == "add":
        existing = worksheet.acell(cell).value
        if existing:
            try:
                total_income += float(existing)
            except (ValueError, TypeError):
                pass
    # If mode is "replace", we just use the new total

    # Update Other Income column
    worksheet.update_acell(cell, round(total_income, 2))

    return {
        "month": month,
        "row": row_idx,
        "total_income": round(total_income, 2),
        "transactions_count": len(income_transactions),
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
        "mode": mode,
    }


# Net Worth sheet column mapping
NET_WORTH_COLUMNS = {
    "Month": "A",
    "Checking": "B",
    "Savings": "C",
    "IRA": "D",
    "401(k)": "E",
    "HSA": "F",
    "Taxable": "G",
    "Other Investments": "H",
    "Asset Value": "I",
    "Asset Debt": "J",
    "Other Debt": "K",
    "Savings Ctb": "L",
    "IRA Ctb": "M",
    "401(k) Ctb": "N",
    "401(k) Match": "O",
    "HSA Ctb": "P",
    "Taxable Ctb": "Q",
    "Other Ctb": "R",
    "Asset Debt Pmt": "S",
    "Other Debt Pmt": "T",
}


def sync_net_worth_to_sheet(
    spreadsheet_id: str,
    balances: dict,
    month: str,
    credentials_path: str | Path | None = None,
) -> dict:
    """
    Sync account balances to the "Net Worth" sheet.

    Args:
        spreadsheet_id: The Google Sheet ID
        balances: Dict with keys like 'checking_balance', 'savings_balance', 'debt_payments'
        month: Month string like "1/2026"
        credentials_path: Path to service account JSON

    Returns:
        Dict with sync results
    """
    client = get_sheets_client(credentials_path)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet("Net Worth")

    row_idx = _find_or_create_month_row(worksheet, month)

    updates = []

    # Update Checking balance
    if balances.get("checking_balance") is not None:
        col = NET_WORTH_COLUMNS["Checking"]
        updates.append({"range": f"{col}{row_idx}", "values": [[round(balances["checking_balance"], 2)]]})

    # Update Savings balance
    if balances.get("savings_balance") is not None:
        col = NET_WORTH_COLUMNS["Savings"]
        updates.append({"range": f"{col}{row_idx}", "values": [[round(balances["savings_balance"], 2)]]})

    # Update Credit Card balance (debt owed goes to Other Debt)
    if balances.get("credit_card_balance") is not None:
        col = NET_WORTH_COLUMNS["Other Debt"]
        updates.append({"range": f"{col}{row_idx}", "values": [[round(balances["credit_card_balance"], 2)]]})

    # Update debt payments (loan payments go to Other Debt Pmt)
    if balances.get("debt_payments"):
        total_debt_pmt = sum(abs(p.get("amount", 0)) for p in balances["debt_payments"])
        col = NET_WORTH_COLUMNS["Other Debt Pmt"]
        updates.append({"range": f"{col}{row_idx}", "values": [[round(total_debt_pmt, 2)]]})

    # Batch update all cells
    if updates:
        worksheet.batch_update(updates)

    return {
        "month": month,
        "row": row_idx,
        "checking_balance": balances.get("checking_balance"),
        "savings_balance": balances.get("savings_balance"),
        "credit_card_balance": balances.get("credit_card_balance"),
        "debt_payments": round(sum(abs(p.get("amount", 0)) for p in balances.get("debt_payments", [])), 2),
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
    }
