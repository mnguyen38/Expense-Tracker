#!/usr/bin/env python3
"""
Quick runner for expense tracker.

Usage:
    python run.py              # Process latest month
    python run.py 12/2025      # Process December 2025
    python run.py 1/2026       # Process January 2026
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Ensure src is in the Python path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv

# Load .env
load_dotenv(Path(__file__).parent / ".env")

STATEMENTS_DIR = Path(__file__).parent / "statements"
MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}


def get_month_folder(month_str: str = None) -> tuple[Path, str]:
    """
    Get the folder path for a given month.

    Args:
        month_str: Month in format "M/YYYY" (e.g., "12/2025") or None for latest

    Returns:
        Tuple of (folder_path, month_str for sheets)
    """
    if month_str:
        # Parse provided month
        parts = month_str.split("/")
        if len(parts) != 2:
            print(f"Error: Invalid month format '{month_str}'. Use M/YYYY (e.g., 12/2025)")
            sys.exit(1)

        try:
            month = int(parts[0])
            year = int(parts[1])
        except ValueError:
            print(f"Error: Invalid month format '{month_str}'. Use M/YYYY (e.g., 12/2025)")
            sys.exit(1)

        month_name = MONTH_NAMES.get(month)
        if not month_name:
            print(f"Error: Invalid month number {month}")
            sys.exit(1)

        folder = STATEMENTS_DIR / str(year) / month_name
        return folder, f"{month}/{year}"

    else:
        # Find the latest month folder
        latest_folder = None
        latest_date = None

        for year_dir in sorted(STATEMENTS_DIR.iterdir(), reverse=True):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue

            year = int(year_dir.name)

            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue

                # Find month number from name
                month_num = None
                for num, name in MONTH_NAMES.items():
                    if name.lower() == month_dir.name.lower():
                        month_num = num
                        break

                if month_num is None:
                    continue

                # Check if folder has PDFs
                pdfs = list(month_dir.glob("*.pdf"))
                if not pdfs:
                    continue

                folder_date = datetime(year, month_num, 1)
                if latest_date is None or folder_date > latest_date:
                    latest_date = folder_date
                    latest_folder = month_dir

        if latest_folder is None:
            print("Error: No statement folders found")
            sys.exit(1)

        month_str = f"{latest_date.month}/{latest_date.year}"
        return latest_folder, month_str


def main():
    # Handle --help
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("Examples:")
        print("  python run.py              # Process latest month")
        print("  python run.py 12/2025      # Process December 2025")
        print("  python run.py 1/2026       # Process January 2026")
        print()
        print("Statements folder structure: statements/YYYY/MonthName/")
        print("Sheet ID is read from GOOGLE_SHEET_ID in .env")
        sys.exit(0)

    # Get month argument if provided
    month_arg = sys.argv[1] if len(sys.argv) > 1 else None

    # Get folder and month string
    folder, month_str = get_month_folder(month_arg)

    if not folder.exists():
        print(f"Error: Folder not found: {folder}")
        sys.exit(1)

    pdfs = list(folder.glob("*.pdf"))
    if not pdfs:
        print(f"Error: No PDFs found in {folder}")
        sys.exit(1)

    # Get sheet ID from env
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")

    print(f"Processing: {folder}")
    print(f"Month: {month_str}")
    print(f"PDFs: {len(pdfs)}")
    print()

    # Build arguments for main.py
    from main import main as run_main

    # Override sys.argv for argparse
    args = [
        "main.py",
        str(folder),
        "-m", month_str,
    ]

    if sheet_id:
        args.extend(["-s", sheet_id])

    sys.argv = args
    run_main()


if __name__ == "__main__":
    main()
