"""Test email notification sending (manual integration test)."""

import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from notifications import send_email
import os


@pytest.mark.skip(reason="Manual integration test - requires SMTP credentials")
def test_email():
    """Send a test email notification."""
    notify_email = os.environ.get("NOTIFY_EMAIL")

    if not notify_email:
        print("Error: NOTIFY_EMAIL must be set in .env")
        return False

    print(f"Sending to: {notify_email}")
    print()

    subject = "Test from Expense Tracker"
    message = "Email notifications are working!\n\nThis is a test message from your expense tracker."
    print(f"Subject: {subject}")
    print(f"Message: {message}")
    print()

    try:
        success = send_email(notify_email, subject, message)
        if success:
            print("Email sent successfully!")
            return True
        else:
            print("Email failed to send.")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    test_email()
