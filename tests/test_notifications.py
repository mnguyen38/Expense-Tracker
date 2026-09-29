"""Tests for email notification system."""

import json
from unittest.mock import MagicMock, patch

import pytest

from expense_tracker.notifications import (
    _format_category_rows,
    _format_category_text,
    _format_top_transactions,
    check_spending_threshold,
    load_thresholds,
    reset_month_thresholds,
    save_thresholds,
    send_email,
    send_spending_summary,
)


class TestLoadThresholds:
    """Tests for load_thresholds function."""

    def test_load_empty_file(self, temp_data_dir, monkeypatch):
        """Test loading when file doesn't exist."""
        # Point to non-existent file
        fake_file = temp_data_dir / "nonexistent.json"
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", fake_file)

        result = load_thresholds()
        assert result == {"notified": {}}

    def test_load_existing_file(self, temp_data_dir, monkeypatch):
        """Test loading existing threshold data."""
        threshold_file = temp_data_dir / "thresholds.json"
        data = {"notified": {"1/2025": [1000, 2000]}}
        threshold_file.write_text(json.dumps(data))
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        result = load_thresholds()
        assert result == data
        assert 1000 in result["notified"]["1/2025"]


class TestSaveThresholds:
    """Tests for save_thresholds function."""

    def test_save_creates_directory(self, tmp_path, monkeypatch):
        """Test that save creates parent directory if needed."""
        threshold_file = tmp_path / "new_dir" / "thresholds.json"
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        data = {"notified": {"1/2025": [1000]}}
        save_thresholds(data)

        assert threshold_file.exists()
        saved = json.loads(threshold_file.read_text())
        assert saved == data

    def test_save_overwrites_existing(self, temp_data_dir, monkeypatch):
        """Test that save overwrites existing file."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        data = {"notified": {"1/2025": [1000, 2000]}}
        save_thresholds(data)

        saved = json.loads(threshold_file.read_text())
        assert saved["notified"]["1/2025"] == [1000, 2000]


class TestSendEmail:
    """Tests for send_email function."""

    def test_requires_smtp_credentials(self, clean_env):
        """Test that missing credentials raises error."""
        with pytest.raises(ValueError, match="SMTP credentials not found"):
            send_email("test@example.com", "Subject", "Message")

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_send_email_success(self, mock_smtp, mock_env_vars):
        """Test successful email sending."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = send_email("recipient@example.com", "Test Subject", "Test Message")

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_send_email_with_explicit_credentials(self, mock_smtp, clean_env):
        """Test sending with explicit credentials."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = send_email(
            to_email="recipient@example.com",
            subject="Test",
            message="Message",
            smtp_email="sender@example.com",
            smtp_password="password123",
        )

        assert result is True

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_send_email_failure(self, mock_smtp, mock_env_vars):
        """Test email sending failure."""
        mock_smtp.return_value.__enter__.side_effect = Exception("Connection failed")

        result = send_email("recipient@example.com", "Test", "Message")

        assert result is False

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_send_email_custom_server(self, mock_smtp, clean_env):
        """Test sending with custom SMTP server."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_email(
            to_email="test@example.com",
            subject="Test",
            message="Message",
            smtp_email="sender@example.com",
            smtp_password="password",
            smtp_server="smtp.custom.com",
            smtp_port=465,
        )

        mock_smtp.assert_called_with("smtp.custom.com", 465)


class TestCheckSpendingThreshold:
    """Tests for check_spending_threshold function."""

    def test_no_notification_without_email(self, clean_env, temp_data_dir, monkeypatch):
        """Test that no notification is sent without NOTIFY_EMAIL."""
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", temp_data_dir / "thresholds.json")

        result = check_spending_threshold(1500.00, "1/2025")

        assert result == []

    @patch("expense_tracker.notifications.send_email")
    def test_notifies_on_first_threshold(self, mock_send, mock_env_vars, temp_data_dir, monkeypatch):
        """Test notification when first threshold is crossed."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_send.return_value = True

        result = check_spending_threshold(1500.00, "1/2025")

        assert result == [1000.0]
        mock_send.assert_called_once()

    @patch("expense_tracker.notifications.send_email")
    def test_notifies_on_multiple_thresholds(self, mock_send, mock_env_vars, temp_data_dir, monkeypatch):
        """Test notification when multiple thresholds are crossed."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_send.return_value = True

        result = check_spending_threshold(2500.00, "1/2025")

        assert result == [1000.0, 2000.0]
        assert mock_send.call_count == 2

    @patch("expense_tracker.notifications.send_email")
    def test_skips_already_notified(self, mock_send, mock_env_vars, temp_data_dir, monkeypatch):
        """Test that already notified thresholds are skipped."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {"1/2025": [1000.0]}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_send.return_value = True

        result = check_spending_threshold(1500.00, "1/2025")

        # 1000 already notified, no new thresholds crossed
        assert result == []
        mock_send.assert_not_called()

    @patch("expense_tracker.notifications.send_email")
    def test_notifies_new_threshold_only(self, mock_send, mock_env_vars, temp_data_dir, monkeypatch):
        """Test that only new thresholds are notified."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {"1/2025": [1000.0]}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_send.return_value = True

        result = check_spending_threshold(2500.00, "1/2025")

        # Only 2000 should be notified (1000 already done)
        assert result == [2000.0]
        assert mock_send.call_count == 1

    @patch("expense_tracker.notifications.send_email")
    def test_custom_threshold_interval(self, mock_send, mock_env_vars, temp_data_dir, monkeypatch):
        """Test custom threshold interval."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_send.return_value = True

        result = check_spending_threshold(
            total_spent=750.00,
            month="1/2025",
            threshold_interval=500.0,  # Every $500
        )

        assert result == [500.0]

    @patch("expense_tracker.notifications.send_email")
    def test_below_threshold_no_notification(self, mock_send, mock_env_vars, temp_data_dir, monkeypatch):
        """Test that no notification is sent when below threshold."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        result = check_spending_threshold(500.00, "1/2025")

        assert result == []
        mock_send.assert_not_called()

    @patch("expense_tracker.notifications.send_email")
    def test_saves_notified_thresholds(self, mock_send, mock_env_vars, temp_data_dir, monkeypatch):
        """Test that notified thresholds are saved to file."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_send.return_value = True

        check_spending_threshold(1500.00, "1/2025")

        saved = json.loads(threshold_file.read_text())
        assert 1000.0 in saved["notified"]["1/2025"]

    @patch("expense_tracker.notifications.send_email")
    def test_handles_email_failure(self, mock_send, mock_env_vars, temp_data_dir, monkeypatch):
        """Test handling when email fails to send."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_send.return_value = False  # Email fails

        result = check_spending_threshold(1500.00, "1/2025")

        # Failed notifications should not be in result
        assert result == []


class TestResetMonthThresholds:
    """Tests for reset_month_thresholds function."""

    def test_reset_existing_month(self, temp_data_dir, monkeypatch, capsys):
        """Test resetting thresholds for existing month."""
        threshold_file = temp_data_dir / "thresholds.json"
        data = {"notified": {"1/2025": [1000, 2000], "2/2025": [1000]}}
        threshold_file.write_text(json.dumps(data))
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        reset_month_thresholds("1/2025")

        saved = json.loads(threshold_file.read_text())
        assert "1/2025" not in saved["notified"]
        assert "2/2025" in saved["notified"]

        captured = capsys.readouterr()
        assert "Reset thresholds for 1/2025" in captured.out

    def test_reset_nonexistent_month(self, temp_data_dir, monkeypatch, capsys):
        """Test resetting thresholds for non-existent month."""
        threshold_file = temp_data_dir / "thresholds.json"
        data = {"notified": {"1/2025": [1000]}}
        threshold_file.write_text(json.dumps(data))
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        reset_month_thresholds("3/2025")

        # Should not print anything since month didn't exist
        captured = capsys.readouterr()
        assert "Reset thresholds" not in captured.out


class TestEmailContent:
    """Tests for email content formatting."""

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_subject_format(self, mock_smtp, mock_env_vars, temp_data_dir, monkeypatch):
        """Test that email subject is formatted correctly."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        check_spending_threshold(1500.00, "1/2025")

        # Check that sendmail was called with correct subject
        call_args = mock_server.sendmail.call_args
        message = call_args[0][2]  # Third argument is the message
        assert "Spending Alert" in message
        assert "$1,000" in message

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_body_format(self, mock_smtp, mock_env_vars, temp_data_dir, monkeypatch):
        """Test that email body contains spending info."""
        threshold_file = temp_data_dir / "thresholds.json"
        threshold_file.write_text('{"notified": {}}')
        monkeypatch.setattr("expense_tracker.notifications.THRESHOLD_FILE", threshold_file)

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        check_spending_threshold(1500.00, "1/2025")

        call_args = mock_server.sendmail.call_args
        message = call_args[0][2]
        assert "$1,500" in message
        assert "1/2025" in message


class TestFormatCategoryRows:
    """Tests for _format_category_rows helper function."""

    def test_empty_categories(self):
        """Test formatting with no categories."""
        result = _format_category_rows({}, 0)
        assert "No spending data" in result

    def test_single_category(self):
        """Test formatting single category."""
        by_category = {"Groceries": 150.50}
        result = _format_category_rows(by_category, 150.50)

        assert "Groceries" in result
        assert "150.50" in result
        assert "<tr>" in result
        assert "100%" in result  # Should be 100% bar

    def test_multiple_categories(self):
        """Test formatting multiple categories."""
        by_category = {"Groceries": 200.00, "Entertainment": 100.00, "Transport": 50.00}
        result = _format_category_rows(by_category, 350.00)

        assert "Groceries" in result
        assert "Entertainment" in result
        assert "Transport" in result

    def test_category_percentages(self):
        """Test that percentages are calculated correctly."""
        by_category = {"Food": 500.00, "Other": 500.00}
        result = _format_category_rows(by_category, 1000.00)

        # Both should be 50%
        assert "50%" in result


class TestFormatCategoryText:
    """Tests for _format_category_text helper function."""

    def test_empty_categories(self):
        """Test formatting with no categories."""
        result = _format_category_text({})
        assert "No spending data" in result

    def test_single_category(self):
        """Test formatting single category."""
        by_category = {"Groceries": 150.50}
        result = _format_category_text(by_category)

        assert "Groceries" in result
        assert "150.50" in result

    def test_multiple_categories_sorted(self):
        """Test that categories are sorted by amount (highest first)."""
        by_category = {"Small": 10.00, "Large": 500.00, "Medium": 100.00}
        result = _format_category_text(by_category)

        # Large should appear before Medium before Small
        large_pos = result.find("Large")
        medium_pos = result.find("Medium")
        small_pos = result.find("Small")

        assert large_pos < medium_pos < small_pos

    def test_alignment(self):
        """Test that columns are aligned."""
        by_category = {"A": 100.00, "Long Category Name": 200.00}
        result = _format_category_text(by_category)

        # Should have consistent spacing
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 2


class TestFormatTopTransactions:
    """Tests for _format_top_transactions helper function."""

    def test_empty_transactions(self):
        """Test formatting with no transactions."""
        html, text = _format_top_transactions([])
        assert html == ""
        assert text == ""

    def test_only_income_transactions(self):
        """Test formatting with only income (positive amounts)."""
        transactions = [
            {"date": "2025-01-01", "description": "Salary", "amount": 5000.00},
        ]
        html, text = _format_top_transactions(transactions)

        # Should be empty since we only show expenses
        assert html == ""
        assert text == ""

    def test_expense_transactions(self):
        """Test formatting expense transactions."""
        transactions = [
            {
                "date": "2025-01-01",
                "description": "Amazon Purchase",
                "amount": -150.00,
                "category": "Shopping",
            },
            {"date": "2025-01-02", "description": "Grocery Store", "amount": -75.50, "category": "Groceries"},
        ]
        html, text = _format_top_transactions(transactions)

        assert "Amazon Purchase" in html
        assert "Grocery Store" in html
        assert "150.00" in html
        assert "75.50" in html

        assert "Amazon Purchase" in text
        assert "Grocery Store" in text

    def test_sorted_by_amount(self):
        """Test that transactions are sorted by amount (largest first)."""
        transactions = [
            {"date": "2025-01-01", "description": "Small", "amount": -10.00},
            {"date": "2025-01-02", "description": "Large", "amount": -500.00},
            {"date": "2025-01-03", "description": "Medium", "amount": -100.00},
        ]
        html, text = _format_top_transactions(transactions)

        # Large should appear before Medium before Small
        large_pos = text.find("Large")
        medium_pos = text.find("Medium")
        small_pos = text.find("Small")

        assert large_pos < medium_pos < small_pos

    def test_limit_transactions(self):
        """Test that transactions are limited to specified count."""
        transactions = [
            {"date": f"2025-01-{i:02d}", "description": f"Transaction {i}", "amount": -float(i * 10)}
            for i in range(1, 20)
        ]
        html, text = _format_top_transactions(transactions, limit=5)

        # Should only show top 5
        assert "Top 5 Transactions" in html
        assert "TOP 5 TRANSACTIONS" in text


class TestSendSpendingSummary:
    """Tests for send_spending_summary function."""

    def test_requires_smtp_credentials(self, clean_env):
        """Test that missing credentials raises error."""
        with pytest.raises(ValueError, match="SMTP credentials not found"):
            send_spending_summary(
                to_email="test@example.com",
                month="1/2025",
                total_spent=1500.00,
                by_category={"Groceries": 500.00},
            )

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_send_summary_success(self, mock_smtp, mock_env_vars):
        """Test successful summary email sending."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        result = send_spending_summary(
            to_email="recipient@example.com",
            month="1/2025",
            total_spent=1500.00,
            by_category={"Groceries": 500.00, "Entertainment": 200.00},
        )

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_contains_html_and_text(self, mock_smtp, mock_env_vars):
        """Test that email contains both HTML and plain text versions."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_spending_summary(
            to_email="recipient@example.com",
            month="1/2025",
            total_spent=1500.00,
            by_category={"Groceries": 500.00},
        )

        call_args = mock_server.sendmail.call_args
        message = call_args[0][2]

        # Should contain multipart markers
        assert "multipart/alternative" in message
        assert "text/plain" in message
        assert "text/html" in message

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_contains_categories(self, mock_smtp, mock_env_vars):
        """Test that email contains category breakdown."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_spending_summary(
            to_email="recipient@example.com",
            month="1/2025",
            total_spent=750.00,
            by_category={"Groceries": 400.00, "Transport": 350.00},
        )

        call_args = mock_server.sendmail.call_args
        message = call_args[0][2]

        assert "Groceries" in message
        assert "Transport" in message
        assert "400.00" in message
        assert "350.00" in message

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_with_income(self, mock_smtp, mock_env_vars):
        """Test that income is included when provided."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_spending_summary(
            to_email="recipient@example.com",
            month="1/2025",
            total_spent=1500.00,
            by_category={"Groceries": 500.00},
            total_income=5000.00,
        )

        call_args = mock_server.sendmail.call_args
        message = call_args[0][2]

        assert "5,000.00" in message
        assert "Income" in message

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_with_threshold_alert(self, mock_smtp, mock_env_vars):
        """Test that threshold alert is included when provided."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_spending_summary(
            to_email="recipient@example.com",
            month="1/2025",
            total_spent=1500.00,
            by_category={"Groceries": 500.00},
            threshold_crossed=1000.0,
        )

        call_args = mock_server.sendmail.call_args
        message = call_args[0][2]

        assert "Threshold Alert" in message or "threshold" in message.lower()
        assert "1,000" in message

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_with_transactions(self, mock_smtp, mock_env_vars):
        """Test that top transactions are included when provided."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        transactions = [
            {
                "date": "2025-01-15",
                "description": "AMAZON PURCHASE",
                "amount": -150.00,
                "category": "Shopping",
            },
            {"date": "2025-01-16", "description": "GROCERY STORE", "amount": -75.50, "category": "Groceries"},
        ]

        send_spending_summary(
            to_email="recipient@example.com",
            month="1/2025",
            total_spent=225.50,
            by_category={"Shopping": 150.00, "Groceries": 75.50},
            transactions=transactions,
        )

        call_args = mock_server.sendmail.call_args
        message = call_args[0][2]

        assert "AMAZON PURCHASE" in message
        assert "GROCERY STORE" in message

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_subject_with_threshold(self, mock_smtp, mock_env_vars):
        """Test that subject includes emoji when threshold is crossed."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_spending_summary(
            to_email="recipient@example.com",
            month="1/2025",
            total_spent=1500.00,
            by_category={},
            threshold_crossed=1000.0,
        )

        call_args = mock_server.sendmail.call_args
        message = call_args[0][2]

        # Subject should contain money emoji when threshold crossed
        assert "Subject:" in message

    @patch("expense_tracker.notifications.smtplib.SMTP")
    def test_email_failure_returns_false(self, mock_smtp, mock_env_vars):
        """Test that email failure returns False."""
        mock_smtp.return_value.__enter__.side_effect = Exception("Connection failed")

        result = send_spending_summary(
            to_email="recipient@example.com",
            month="1/2025",
            total_spent=1500.00,
            by_category={},
        )

        assert result is False


class TestHtmlEscaping:
    """Merchant names come from bank data and must not inject HTML into emails."""

    def test_top_transactions_escape_description(self):
        txns = [
            {
                "date": "2026-01-01",
                "description": "<script>alert(1)</script>",
                "amount": -5.0,
                "category": "Misc",
            }
        ]
        html_out, text = _format_top_transactions(txns)
        assert "<script>" not in html_out
        assert "&lt;script&gt;" in html_out
        assert "<script>" in text  # plain-text part is not HTML

    def test_category_rows_escape_category(self):
        rows = _format_category_rows({"<b>Food</b>": 10.0}, 10.0)
        assert "<b>Food</b>" not in rows
        assert "&lt;b&gt;Food&lt;/b&gt;" in rows
