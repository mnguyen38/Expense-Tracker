"""Send one test email to NOTIFY_EMAIL to check the SMTP settings in your .env."""

import os
import sys

from expense_tracker.config import load_config
from expense_tracker.notifications import send_email


def main() -> int:
    load_config()  # loads .env from the current directory and the data directory
    notify_email = os.environ.get("NOTIFY_EMAIL")
    if not notify_email:
        print("Error: NOTIFY_EMAIL must be set in .env")
        return 1

    print(f"Sending test email to {notify_email}...")
    ok = send_email(notify_email, "Test from Expense Tracker", "Email notifications are working!")
    print("Sent." if ok else "Failed to send.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
