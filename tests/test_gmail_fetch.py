"""Tests for parsing Bank of America alert emails (no Gmail API calls)."""

import base64

from expense_tracker.gmail import _html_to_text, get_email_date, parse_boa_alert, parse_email_body


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _email(body: str, mime: str = "text/plain", date: str = "Sat, 17 Jan 2026 14:03:00 -0500") -> dict:
    return {
        "id": "msg-1",
        "internalDate": "1768676580000",
        "payload": {
            "headers": [{"name": "Date", "value": date}],
            "parts": [{"mimeType": mime, "body": {"data": _b64(body)}}],
        },
    }


ALERT_TEXT = "Amount:\t$1,023.34\nDate:\tJanuary 17, 2026\nWhere:\tPP APPLE.COM BILL\nView details"


class TestParseBoaAlert:
    def test_parses_amount_date_and_merchant(self):
        txn = parse_boa_alert(_email(ALERT_TEXT))

        assert txn["amount"] == -1023.34
        assert txn["date"] == "2026-01-17"
        assert txn["description"] == "PP APPLE.COM BILL"
        assert txn["email_id"] == "msg-1"

    def test_html_only_email(self):
        html = (
            "<html><body><p>Amount: $5.00</p><p>Date: March 3, 2026</p>"
            "<p>Where: BLUE BOTTLE</p></body></html>"
        )
        txn = parse_boa_alert(_email(html, mime="text/html"))

        assert txn["amount"] == -5.00
        assert txn["description"] == "BLUE BOTTLE"

    def test_non_transaction_email_is_skipped(self):
        assert parse_boa_alert(_email("Your statement is ready to view.")) is None

    def test_falls_back_to_email_date(self):
        txn = parse_boa_alert(_email("Amount: $9.99\nWhere: NETFLIX\n"))
        assert txn["date"] == "2026-01-17"


class TestEmailHelpers:
    def test_nested_multipart_prefers_plain_text(self):
        email = {
            "payload": {
                "parts": [
                    {
                        "mimeType": "multipart/alternative",
                        "parts": [
                            {"mimeType": "text/html", "body": {"data": _b64("<b>html</b>")}},
                            {"mimeType": "text/plain", "body": {"data": _b64("plain")}},
                        ],
                    }
                ]
            }
        }
        assert parse_email_body(email) == "plain"

    def test_html_to_text_strips_tags_and_entities(self):
        text = _html_to_text("<style>x{}</style><p>Tom &amp; Jerry</p><br>Next")
        assert text == "Tom & Jerry\n\nNext"

    def test_email_date_with_timezone_name(self):
        date = get_email_date(_email("", date="Sat, 17 Jan 2026 14:03:00 -0500 (EST)"))
        assert (date.year, date.month, date.day, date.hour) == (2026, 1, 17, 14)
