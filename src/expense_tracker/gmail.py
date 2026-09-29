"""Gmail API integration for fetching Bank of America transaction alerts."""

import base64
import html as html_module
import re
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import default_home

# Gmail API scopes - read-only access to emails
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _token_file() -> Path:
    return default_home() / "gmail_token.json"


def _credentials_file() -> Path:
    return default_home() / "gmail_credentials.json"


def get_gmail_service():
    """
    Create and return a Gmail API service.

    First time: Opens browser for OAuth authentication.
    Subsequent times: Uses the stored token in the data directory.
    """
    creds = None
    token_file = _token_file()
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    # Refresh or get new credentials if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            credentials_file = _credentials_file()
            if not credentials_file.exists():
                raise FileNotFoundError(
                    f"Gmail credentials file not found: {credentials_file}\n\n"
                    "To set up Gmail access:\n"
                    "1. Go to https://console.cloud.google.com/apis/credentials\n"
                    "2. Create an OAuth 2.0 Client ID (Desktop application)\n"
                    f"3. Download the JSON and save it as {credentials_file}\n"
                    "4. Run `expense-tracker gmail` again to sign in"
                )

            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
            creds = flow.run_local_server(port=0)

        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_boa_alerts(days_back: int = 7, max_results: int = 100) -> list[dict]:
    """
    Fetch Bank of America transaction alert emails.

    Args:
        days_back: Number of days to look back for emails
        max_results: Maximum number of emails to fetch

    Returns:
        List of raw email data dictionaries
    """
    service = get_gmail_service()

    # Calculate date range
    after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")

    # Search for BoA alert emails
    # BoA sends from onlinebanking@ealerts.bankofamerica.com
    # Subject: "Credit card transaction exceeds alert limit you set"
    query = f"from:bankofamerica after:{after_date}"

    results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()

    messages = results.get("messages", [])

    emails = []
    for msg in messages:
        # Fetch full message
        full_msg = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        emails.append(full_msg)

    return emails


def parse_email_body(email_data: dict) -> str:
    """Extract text body from email data (handles both plain text and HTML)."""
    payload = email_data.get("payload", {})

    def get_body_from_parts(parts):
        """Recursively search for text content in parts."""
        plain_text = None
        html_text = None

        for part in parts:
            mime_type = part.get("mimeType", "")

            if mime_type == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    plain_text = base64.urlsafe_b64decode(data).decode("utf-8")

            elif mime_type == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    html_text = base64.urlsafe_b64decode(data).decode("utf-8")

            # Check nested parts
            if "parts" in part:
                nested_plain, nested_html = get_body_from_parts(part["parts"])
                if nested_plain:
                    plain_text = nested_plain
                if nested_html:
                    html_text = nested_html

        return plain_text, html_text

    # Try to get text from parts
    if "parts" in payload:
        plain_text, html_text = get_body_from_parts(payload["parts"])
        if plain_text:
            return plain_text
        if html_text:
            return _html_to_text(html_text)

    # Fall back to direct body data
    body_data = payload.get("body", {}).get("data", "")
    if body_data:
        content = base64.urlsafe_b64decode(body_data).decode("utf-8")
        if "<html" in content.lower():
            return _html_to_text(content)
        return content

    return ""


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text by removing tags and decoding entities."""
    # Remove style and script tags with content
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # Replace <br> and </p> with newlines
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</div>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</tr>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</td>", "\t", html, flags=re.IGNORECASE)

    # Remove all other HTML tags
    html = re.sub(r"<[^>]+>", "", html)

    # Decode HTML entities
    text = html_module.unescape(html)

    # Clean up whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)

    return text.strip()


def get_email_date(email_data: dict) -> datetime:
    """Extract date from email headers."""
    headers = email_data.get("payload", {}).get("headers", [])
    for header in headers:
        if header["name"].lower() == "date":
            # Parse email date format
            date_str = header["value"]
            # Remove timezone name in parentheses if present
            date_str = re.sub(r"\s*\([^)]+\)\s*$", "", date_str)
            try:
                return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
            except ValueError:
                try:
                    return datetime.strptime(date_str, "%d %b %Y %H:%M:%S %z")
                except ValueError:
                    pass

    # Fall back to internal date
    internal_date = email_data.get("internalDate")
    if internal_date:
        return datetime.fromtimestamp(int(internal_date) / 1000)

    return datetime.now()


def parse_boa_alert(email_data: dict) -> dict | None:
    """
    Parse a Bank of America transaction alert email.

    BoA format:
        Amount:	$23.34
        Date:	January 17, 2026
        Where:	PP APPLE.COM BILL

    Returns:
        Transaction dict with date, description, amount, or None if parsing fails
    """
    body = parse_email_body(email_data)
    email_date = get_email_date(email_data)

    if not body:
        return None

    transaction = {
        "email_id": email_data.get("id"),
        "email_date": email_date.isoformat(),
    }

    # Parse Amount: $XX.XX
    amount_match = re.search(r"Amount:\s*\$([0-9,]+\.?\d*)", body)
    if amount_match:
        amount_str = amount_match.group(1).replace(",", "")
        transaction["amount"] = -float(amount_str)  # Negative for spending
    else:
        return None  # Can't parse without amount

    # Parse Where: MERCHANT NAME
    where_match = re.search(r"Where:\s*(.+?)(?:\n|View|If you|$)", body, re.DOTALL)
    if where_match:
        transaction["description"] = where_match.group(1).strip()
    else:
        transaction["description"] = "Unknown Merchant"

    # Parse Date: January 17, 2026
    date_match = re.search(r"Date:\s*(\w+\s+\d{1,2},?\s+\d{4})", body)
    if date_match:
        try:
            parsed_date = datetime.strptime(date_match.group(1).replace(",", ""), "%B %d %Y")
            transaction["date"] = parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            transaction["date"] = email_date.strftime("%Y-%m-%d")
    else:
        transaction["date"] = email_date.strftime("%Y-%m-%d")

    return transaction


def fetch_and_parse_alerts(days_back: int = 7, debug: bool = False) -> list[dict]:
    """
    Fetch and parse all BoA transaction alerts.

    Args:
        days_back: Number of days to look back
        debug: Print debug info about parsing

    Returns:
        List of parsed transactions
    """
    emails = fetch_boa_alerts(days_back=days_back)

    transactions = []
    for email in emails:
        if debug:
            body = parse_email_body(email)
            print("\n--- Email body preview ---")
            print(body[:500] if body else "(empty)")
            print("--- End preview ---\n")
        txn = parse_boa_alert(email)
        if txn:
            transactions.append(txn)
        elif debug:
            print("  (Failed to parse this email)")

    # Sort by date (newest first)
    transactions.sort(key=lambda x: x["date"], reverse=True)

    return transactions
