"""Sync transactions from Gmail BoA alerts and update Google Sheets."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

from gmail_fetch import fetch_and_parse_alerts
from categorizer import categorize_transactions, get_summary
from sheets import sync_to_sheet, get_spreadsheet_id_from_url
from main import cleanup_output_folder, MAX_OUTPUT_FILES

# Default Google Sheet ID from environment
DEFAULT_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")


# File to track processed email IDs (avoid duplicates)
DATA_DIR = Path(__file__).parent.parent / "data"
PROCESSED_FILE = DATA_DIR / "processed_emails.json"


def load_processed_ids() -> set:
    """Load set of already processed email IDs."""
    if not PROCESSED_FILE.exists():
        return set()
    with open(PROCESSED_FILE) as f:
        data = json.load(f)
        return set(data.get("processed_ids", []))


def save_processed_ids(ids: set):
    """Save processed email IDs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_FILE, "w") as f:
        json.dump({
            "processed_ids": list(ids),
            "last_updated": datetime.now().isoformat(),
        }, f, indent=2)


def main():
    args = parse_args()

    print("=" * 50)
    print("SYNCING FROM GMAIL BOA ALERTS")
    print("=" * 50)

    # Fetch transactions from Gmail
    try:
        print(f"\nFetching BoA alerts from the last {args.days} days...")
        transactions = fetch_and_parse_alerts(days_back=args.days)
    except FileNotFoundError as e:
        print(f"\nSetup required:\n{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError fetching emails: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    if not transactions:
        print("No transaction alerts found.")
        return

    print(f"Found {len(transactions)} transaction alerts")

    # Filter out already processed emails (unless --force flag)
    processed_ids = load_processed_ids()

    if args.force:
        print("  (--force: reprocessing all emails)")
        new_transactions = transactions
    else:
        new_transactions = [
            t for t in transactions
            if t.get("email_id") not in processed_ids
        ]

        if len(new_transactions) < len(transactions):
            print(f"  ({len(transactions) - len(new_transactions)} already processed, skipping)")

    if not new_transactions:
        print("No new transactions to process.")
        return

    print(f"\nProcessing {len(new_transactions)} new transactions...")
    transactions = new_transactions

    # Categorize with AI
    print("\nCategorizing transactions with Claude AI...")
    try:
        categorized = categorize_transactions(transactions)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Generate summary
    summary = get_summary(categorized)

    # Save to output file (unless --no-output)
    if not args.no_output:
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"email_sync_{timestamp}.json"

        output = {
            "generated_at": datetime.now().isoformat(),
            "source": "gmail_boa_alerts",
            "summary": {
                "total_transactions": summary["transaction_count"],
                "total_spending": summary["total_spending"],
                "total_income": summary["total_income"],
            },
            "by_category": summary["by_category"],
            "transactions": categorized,
        }

        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\nResults saved to: {output_file}")

        # Auto-cleanup old files
        cleanup_output_folder(output_dir)

    # Print summary
    print("\n" + "=" * 50)
    print("SPENDING SUMMARY")
    print("=" * 50)
    print(f"Total Spending: ${summary['total_spending']:,.2f}")
    print("\nBy Category:")
    print("-" * 50)

    sorted_cats = sorted(
        summary["by_category"].items(),
        key=lambda x: abs(x[1]["total"]),
        reverse=True
    )

    for category, data in sorted_cats:
        print(f"  {category:20} ${abs(data['total']):>10,.2f}  ({data['count']} transactions)")

    # Sync to Google Sheets if requested
    if args.sheets:
        print("\n" + "=" * 50)
        print("SYNCING TO GOOGLE SHEETS")
        print("=" * 50)
        try:
            sheet_id = args.sheets
            if "docs.google.com" in sheet_id:
                sheet_id = get_spreadsheet_id_from_url(sheet_id)

            result = sync_to_sheet(
                spreadsheet_id=sheet_id,
                transactions=categorized,
                month=args.month,
            )
            print(f"Synced to: {result['spreadsheet_url']}")
            print(f"Month: {result['month']} (row {result['row']})")
            print(f"Total Spent: ${result['total_spent']:,.2f}")
            print(f"Categories updated: {', '.join(result['categories_updated'])}")
        except Exception as e:
            print(f"Error syncing to Google Sheets: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    # Mark emails as processed
    processed_ids = load_processed_ids()
    for txn in categorized:
        if "email_id" in txn:
            processed_ids.add(txn["email_id"])
    save_processed_ids(processed_ids)

    print(f"\nMarked {len(categorized)} transactions as processed")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync transactions from Gmail BoA alerts and update Google Sheets"
    )
    parser.add_argument(
        "-d", "--days",
        type=int,
        default=7,
        help="Number of days to look back for emails (default: 7)"
    )
    parser.add_argument(
        "-s", "--sheets",
        metavar="SHEET_ID_OR_URL",
        default=DEFAULT_SHEET_ID,
        help="Google Sheet ID or URL to sync results to (default: GOOGLE_SHEET_ID env var)"
    )
    parser.add_argument(
        "-m", "--month",
        metavar="M/YYYY",
        help="Month for Google Sheets row (e.g., '1/2026'). Auto-detected if not specified."
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force reprocess all alerts, including previously processed ones"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed error messages"
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Skip writing JSON output file"
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
