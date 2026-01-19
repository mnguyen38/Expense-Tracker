"""Process the latest month's statement and prepare next month's folder."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Month names for folder structure
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def parse_month_arg(month_str: str) -> tuple[int, int] | None:
    """
    Parse a month argument like 'December 2025' or '12/2025'.

    Returns:
        Tuple of (year, month_index 0-11) or None if invalid
    """
    month_str = month_str.strip()

    # Try "MonthName Year" format (e.g., "December 2025")
    for idx, month_name in enumerate(MONTHS):
        if month_str.lower().startswith(month_name.lower()):
            parts = month_str.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return (int(parts[1]), idx)

    # Try "M/YYYY" format (e.g., "12/2025")
    if "/" in month_str:
        parts = month_str.split("/")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            month_num = int(parts[0])
            if 1 <= month_num <= 12:
                return (int(parts[1]), month_num - 1)

    return None


def find_latest_month_folder(statements_dir: Path) -> tuple[Path, int, int] | None:
    """
    Find the latest month folder in the statements directory.

    Returns:
        Tuple of (folder_path, year, month_index) or None if not found
    """
    if not statements_dir.exists():
        return None

    # Find all year folders
    year_folders = sorted(
        [f for f in statements_dir.iterdir() if f.is_dir() and f.name.isdigit()],
        key=lambda x: int(x.name),
        reverse=True
    )

    if not year_folders:
        return None

    # Check each year folder starting from most recent
    for year_folder in year_folders:
        year = int(year_folder.name)

        # Find month folders in this year (in reverse order)
        for month_idx in range(11, -1, -1):
            month_name = MONTHS[month_idx]
            month_folder = year_folder / month_name
            if month_folder.exists() and month_folder.is_dir():
                # Check if it has any PDFs
                pdfs = list(month_folder.glob("*.pdf"))
                if pdfs:
                    return (month_folder, year, month_idx)

    return None


def get_next_month(year: int, month_idx: int) -> tuple[int, int, str]:
    """
    Get the next month's year, index, and name.

    Args:
        year: Current year
        month_idx: Current month index (0-11)

    Returns:
        Tuple of (next_year, next_month_idx, next_month_name)
    """
    if month_idx == 11:  # December
        return (year + 1, 0, MONTHS[0])  # January of next year
    else:
        return (year, month_idx + 1, MONTHS[month_idx + 1])


def create_next_month_folder(statements_dir: Path, year: int, month_idx: int) -> Path:
    """Create the folder for the next month."""
    next_year, next_month_idx, next_month_name = get_next_month(year, month_idx)

    next_folder = statements_dir / str(next_year) / next_month_name
    next_folder.mkdir(parents=True, exist_ok=True)

    return next_folder


def main():
    import os
    from main import main as run_parser
    from sheets import get_spreadsheet_id_from_url

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Process a month's bank statement and prepare next month's folder"
    )
    parser.add_argument(
        "month",
        nargs="?",
        help="Month to process (e.g., 'December 2025' or '12/2025'). Defaults to latest."
    )
    args = parser.parse_args()

    statements_dir = Path(__file__).parent.parent / "statements"

    # If month specified, use that; otherwise find latest
    if args.month:
        parsed = parse_month_arg(args.month)
        if not parsed:
            print(f"Invalid month format: {args.month}")
            print("Use 'December 2025' or '12/2025'")
            sys.exit(1)

        year, month_idx = parsed
        month_name = MONTHS[month_idx]
        folder_path = statements_dir / str(year) / month_name

        if not folder_path.exists():
            print(f"Folder not found: {folder_path}")
            sys.exit(1)

        pdfs = list(folder_path.glob("*.pdf"))
        if not pdfs:
            print(f"No PDFs found in: {folder_path}")
            sys.exit(1)
    else:
        # Find the latest month with PDFs
        result = find_latest_month_folder(statements_dir)

        if not result:
            print("No statement folders found with PDFs.")
            print(f"Expected structure: {statements_dir}/YYYY/MonthName/*.pdf")
            sys.exit(1)

        folder_path, year, month_idx = result
        month_name = MONTHS[month_idx]

    print("=" * 50)
    print(f"PROCESSING: {month_name} {year}")
    print("=" * 50)

    # List PDFs found
    pdfs = list(folder_path.glob("*.pdf"))
    print(f"\nFound {len(pdfs)} PDF(s) in {folder_path}:")
    for pdf in pdfs:
        print(f"  - {pdf.name}")

    # Get sheet ID from environment
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if sheet_id and "docs.google.com" in sheet_id:
        sheet_id = get_spreadsheet_id_from_url(sheet_id)

    # Build arguments for main parser
    # Statement month format: M/YYYY (e.g., "1/2026" for January 2026)
    statement_month = f"{month_idx + 1}/{year}"

    # Override sys.argv to pass arguments to the parser
    sys.argv = [
        "main.py",
        str(folder_path),
        "--verbose",
    ]

    if sheet_id:
        sys.argv.extend(["--sheets", sheet_id])
        sys.argv.extend(["--month", statement_month])

    print(f"\nStatement month: {statement_month}")
    print()

    # Run the parser
    run_parser()

    # Create next month's folder (if it doesn't exist)
    next_year, next_month_idx, next_month_name = get_next_month(year, month_idx)
    next_folder = statements_dir / str(next_year) / next_month_name

    if not next_folder.exists():
        print("\n" + "=" * 50)
        print("PREPARING NEXT MONTH")
        print("=" * 50)

        next_folder.mkdir(parents=True, exist_ok=True)
        print(f"Created folder: {next_folder}")
        print(f"\nReady for {next_month_name} {next_year} statement.")


if __name__ == "__main__":
    main()
