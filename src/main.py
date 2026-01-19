"""Bank statement parser CLI."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from parsers import parse_statement
from categorizer import categorize_transactions, get_summary
from notifications import check_spending_threshold


# Number of output files to keep per type (statement_, email_sync_)
MAX_OUTPUT_FILES = 5


def cleanup_output_folder(output_dir: Path, keep: int = MAX_OUTPUT_FILES) -> int:
    """
    Clean up old output files, keeping only the most recent ones.

    Args:
        output_dir: Path to output directory
        keep: Number of files to keep per prefix type

    Returns:
        Number of files deleted
    """
    if not output_dir.exists():
        return 0

    deleted = 0
    prefixes = ["statement_", "email_sync_"]

    for prefix in prefixes:
        files = sorted(
            output_dir.glob(f"{prefix}*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )

        # Delete all but the most recent 'keep' files
        for old_file in files[keep:]:
            old_file.unlink()
            deleted += 1

    return deleted


def main():
    # Load .env file from project root
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    args = parse_args()

    output_dir = Path(args.output)

    # Handle --clean flag (wipe all output files)
    if args.clean:
        output_dir.mkdir(parents=True, exist_ok=True)
        deleted = cleanup_output_folder(output_dir, keep=0)
        print(f"Deleted {deleted} output file(s)")
        return

    # Require input path when not using --clean
    if not args.input:
        print("Error: input path is required")
        print("Usage: python src/main.py <path_to_pdf_or_directory>")
        sys.exit(1)

    # Ensure output directory exists (only if we'll write output)
    if not args.no_output:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Collect PDF files
    input_path = Path(args.input)
    if input_path.is_file():
        pdf_files = [input_path]
    elif input_path.is_dir():
        pdf_files = list(input_path.glob("*.pdf"))
        if not pdf_files:
            print(f"No PDF files found in {input_path}")
            sys.exit(1)
    else:
        print(f"Input path not found: {input_path}")
        sys.exit(1)

    all_expenses = []
    all_income = []
    all_transactions = []
    all_debt_payments = []
    balances = {
        "checking_balance": None,
        "savings_balance": None,
        "credit_card_balance": None,
        "debt_payments": [],
    }

    # Track currencies seen
    currencies_seen = set()

    # Parse each PDF
    for pdf_path in pdf_files:
        print(f"Parsing: {pdf_path.name}")
        try:
            result = parse_statement(pdf_path)
            statement_type = result["statement_type"]
            expenses = result["expenses"]
            income = result["income"]
            transactions = result["all_transactions"]
            debt_payments = result.get("debt_payments", [])
            ending_balance = result.get("ending_balance")
            bank_name = result.get("bank_name", "Unknown")
            currency = result.get("currency", "USD")
            currencies_seen.add(currency)

            # Currency symbol mapping
            currency_symbols = {"USD": "$", "GBP": "£", "EUR": "€"}
            symbol = currency_symbols.get(currency, currency + " ")

            print(f"  Bank: {bank_name}")
            print(f"  Type: {statement_type} ({currency})")
            print(f"  Expenses: {len(expenses)}, Income: {len(income)}")
            if ending_balance is not None:
                print(f"  Ending Balance: {symbol}{ending_balance:,.2f}")

            all_expenses.extend(expenses)
            all_income.extend(income)
            all_transactions.extend(transactions)
            all_debt_payments.extend(debt_payments)

            # Track balances by account type
            if statement_type == "checking" and ending_balance is not None:
                balances["checking_balance"] = ending_balance
            elif statement_type == "savings" and ending_balance is not None:
                balances["savings_balance"] = ending_balance
            elif statement_type == "credit_card" and ending_balance is not None:
                balances["credit_card_balance"] = ending_balance

        except Exception as e:
            print(f"  Error parsing {pdf_path.name}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()

    # Collect debt payments for Net Worth tracking
    balances["debt_payments"] = all_debt_payments

    if not all_transactions:
        print("No transactions found in any PDF files.")
        sys.exit(1)

    print(f"\nTotal: {len(all_expenses)} expenses, {len(all_income)} income transactions")

    # Categorize expenses with AI
    categorized = []
    if all_expenses:
        print("\nCategorizing expenses with Claude AI...")
        try:
            categorized = categorize_transactions(all_expenses)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("\nNo expenses to categorize.")

    # Generate summary
    summary = get_summary(categorized) if categorized else {
        "transaction_count": 0,
        "total_spending": 0,
        "total_income": sum(t.get("amount", 0) for t in all_income),
        "by_category": {},
    }

    # Calculate total income from deposits
    total_income = sum(t.get("amount", 0) for t in all_income)

    # Build output
    output = {
        "generated_at": datetime.now().isoformat(),
        "source_files": [str(p.name) for p in pdf_files],
        "summary": {
            "total_expenses": len(all_expenses),
            "total_income_transactions": len(all_income),
            "total_spending": summary["total_spending"],
            "total_income": total_income,
        },
        "balances": {
            "checking": balances["checking_balance"],
            "savings": balances["savings_balance"],
            "credit_card": balances["credit_card_balance"],
            "debt_payments": sum(abs(p.get("amount", 0)) for p in balances["debt_payments"]),
        },
        "by_category": summary["by_category"],
        "expenses": categorized,
        "income": all_income,
    }

    # Write output (unless --no-output)
    if not args.no_output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"statement_{timestamp}.json"

        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\nResults saved to: {output_file}")

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total Spending: ${summary['total_spending']:,.2f}")
    print(f"Total Income:   ${total_income:,.2f}")
    print(f"Net:            ${total_income - summary['total_spending']:,.2f}")

    if summary["by_category"]:
        print("\nBy Category:")
        print("-" * 50)

        # Sort categories by total (most spending first)
        sorted_cats = sorted(
            summary["by_category"].items(),
            key=lambda x: abs(x[1]["total"]),
            reverse=True
        )

        for category, data in sorted_cats:
            print(f"  {category:20} ${abs(data['total']):>10,.2f}  ({data['count']} transactions)")

    if all_income:
        print("\nIncome Deposits:")
        print("-" * 50)
        for txn in all_income:
            print(f"  {txn['date']}  ${txn['amount']:>10,.2f}  {txn['description'][:40]}")

    # Print account balances
    if balances["checking_balance"] is not None or balances["savings_balance"] is not None or balances["credit_card_balance"] is not None:
        print("\nAccount Balances:")
        print("-" * 50)
        if balances["checking_balance"] is not None:
            print(f"  Checking:    ${balances['checking_balance']:>10,.2f}")
        if balances["savings_balance"] is not None:
            print(f"  Savings:     ${balances['savings_balance']:>10,.2f}")
        if balances["credit_card_balance"] is not None:
            print(f"  Credit Card: ${balances['credit_card_balance']:>10,.2f} (debt)")
        if balances["debt_payments"]:
            total_debt = sum(abs(p.get("amount", 0)) for p in balances["debt_payments"])
            print(f"  Debt Pmts:   ${total_debt:>10,.2f}")

    # Check spending thresholds and send SMS notifications
    if args.month and summary["total_spending"] > 0:
        notified = check_spending_threshold(
            total_spent=summary["total_spending"],
            month=args.month,
        )
        if notified:
            print(f"\nSpending Alerts Sent: {', '.join(f'${t:,.0f}' for t in notified)}")

    # Sync to Google Sheets if requested
    if args.sheets:
        print("\n" + "=" * 50)
        print("SYNCING TO GOOGLE SHEETS")
        print("=" * 50)
        try:
            from sheets import sync_to_sheet, sync_income_to_sheet, sync_net_worth_to_sheet, get_spreadsheet_id_from_url

            # Handle URL or ID
            sheet_id = args.sheets
            if "docs.google.com" in sheet_id:
                sheet_id = get_spreadsheet_id_from_url(sheet_id)

            # Sync expenses to "Out" sheet
            if categorized:
                print("\nSyncing expenses to 'Out' sheet...")
                result = sync_to_sheet(
                    spreadsheet_id=sheet_id,
                    transactions=categorized,
                    month=args.month,
                    mode="replace",  # Statement is source of truth, overrides email tracker
                )
                print(f"  Month: {result['month']} (row {result['row']})")
                print(f"  Total Spent: ${result['total_spent']:,.2f}")
                print(f"  Categories: {', '.join(result['categories_updated'])}")

            # Sync income to "In" sheet
            if all_income:
                print("\nSyncing income to 'In' sheet...")
                income_result = sync_income_to_sheet(
                    spreadsheet_id=sheet_id,
                    income_transactions=all_income,
                    month=args.month,
                    mode="replace",  # Statement is source of truth
                )
                print(f"  Month: {income_result['month']} (row {income_result['row']})")
                print(f"  Total Income (Other): ${income_result['total_income']:,.2f}")
                print(f"  Transactions: {income_result['transactions_count']}")

            # Sync balances to "Net Worth" sheet
            if balances["checking_balance"] is not None or balances["savings_balance"] is not None or balances["credit_card_balance"] is not None or balances["debt_payments"]:
                print("\nSyncing to 'Net Worth' sheet...")
                try:
                    nw_result = sync_net_worth_to_sheet(
                        spreadsheet_id=sheet_id,
                        balances=balances,
                        month=args.month,
                    )
                    print(f"  Month: {nw_result['month']} (row {nw_result['row']})")
                    if nw_result['checking_balance'] is not None:
                        print(f"  Checking: ${nw_result['checking_balance']:,.2f}")
                    if nw_result['savings_balance'] is not None:
                        print(f"  Savings: ${nw_result['savings_balance']:,.2f}")
                    if nw_result.get('credit_card_balance') is not None:
                        print(f"  Credit Card Debt: ${nw_result['credit_card_balance']:,.2f}")
                    if nw_result['debt_payments'] > 0:
                        print(f"  Debt Payments: ${nw_result['debt_payments']:,.2f}")
                except Exception as e:
                    print(f"  Warning: Could not sync to Net Worth sheet: {e}")

            print(f"\nSpreadsheet: https://docs.google.com/spreadsheets/d/{sheet_id}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("\nTo set up Google Sheets sync:")
            print("1. Create a service account at console.cloud.google.com")
            print("2. Download the JSON key file as 'credentials.json'")
            print("3. Share your Google Sheet with the service account email")
            sys.exit(1)
        except Exception as e:
            print(f"Error syncing to Google Sheets: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse bank statement PDFs and categorize transactions using AI"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="PDF file or directory containing PDF files"
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory for JSON files (default: output)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed error messages"
    )
    parser.add_argument(
        "-s", "--sheets",
        metavar="SHEET_ID_OR_URL",
        help="Google Sheet ID or URL to sync results to"
    )
    parser.add_argument(
        "-m", "--month",
        metavar="M/YYYY",
        help="Month for Google Sheets row (e.g., '1/2026'). Auto-detected if not specified."
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Skip writing JSON output file"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete all output files and exit"
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
