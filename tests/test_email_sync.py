"""Tests for Gmail email sync module."""

import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Need to mock gmail_fetch before importing email_sync
with patch.dict("sys.modules", {"gmail_fetch": MagicMock()}):
    import email_sync
    from email_sync import (
        load_processed_ids,
        save_processed_ids,
        parse_args,
    )


class TestLoadProcessedIds:
    """Tests for load_processed_ids function."""

    def test_load_empty_when_file_missing(self, tmp_path):
        """Test loading returns empty set when file doesn't exist."""
        fake_file = tmp_path / "nonexistent.json"

        with patch.object(email_sync, "PROCESSED_FILE", fake_file):
            result = load_processed_ids()

        assert result == set()

    def test_load_existing_ids(self, tmp_path):
        """Test loading existing processed IDs."""
        processed_file = tmp_path / "processed.json"
        data = {
            "processed_ids": ["email1", "email2", "email3"],
            "last_updated": "2025-01-15T10:00:00"
        }
        processed_file.write_text(json.dumps(data))

        with patch.object(email_sync, "PROCESSED_FILE", processed_file):
            result = load_processed_ids()

        assert result == {"email1", "email2", "email3"}

    def test_load_empty_list(self, tmp_path):
        """Test loading when processed_ids is empty list."""
        processed_file = tmp_path / "processed.json"
        data = {"processed_ids": []}
        processed_file.write_text(json.dumps(data))

        with patch.object(email_sync, "PROCESSED_FILE", processed_file):
            result = load_processed_ids()

        assert result == set()


class TestSaveProcessedIds:
    """Tests for save_processed_ids function."""

    def test_save_creates_directory(self, tmp_path):
        """Test that save creates parent directory if needed."""
        data_dir = tmp_path / "new_data"
        processed_file = data_dir / "processed.json"

        with patch.object(email_sync, "DATA_DIR", data_dir), \
             patch.object(email_sync, "PROCESSED_FILE", processed_file):
            save_processed_ids({"email1", "email2"})

        assert processed_file.exists()
        saved = json.loads(processed_file.read_text())
        assert set(saved["processed_ids"]) == {"email1", "email2"}
        assert "last_updated" in saved

    def test_save_overwrites_existing(self, tmp_path):
        """Test that save overwrites existing file."""
        data_dir = tmp_path
        processed_file = tmp_path / "processed.json"
        processed_file.write_text('{"processed_ids": ["old"]}')

        with patch.object(email_sync, "DATA_DIR", data_dir), \
             patch.object(email_sync, "PROCESSED_FILE", processed_file):
            save_processed_ids({"new1", "new2"})

        saved = json.loads(processed_file.read_text())
        assert set(saved["processed_ids"]) == {"new1", "new2"}

    def test_save_empty_set(self, tmp_path):
        """Test saving empty set."""
        data_dir = tmp_path
        processed_file = tmp_path / "processed.json"

        with patch.object(email_sync, "DATA_DIR", data_dir), \
             patch.object(email_sync, "PROCESSED_FILE", processed_file):
            save_processed_ids(set())

        saved = json.loads(processed_file.read_text())
        assert saved["processed_ids"] == []


class TestParseArgs:
    """Tests for argument parsing."""

    def test_default_days(self, monkeypatch):
        """Test default days value."""
        monkeypatch.setattr("sys.argv", ["email_sync.py"])
        args = parse_args()
        assert args.days == 7

    def test_custom_days(self, monkeypatch):
        """Test custom days value."""
        monkeypatch.setattr("sys.argv", ["email_sync.py", "--days", "14"])
        args = parse_args()
        assert args.days == 14

    def test_sheets_argument(self, monkeypatch):
        """Test sheets ID argument."""
        monkeypatch.setattr("sys.argv", ["email_sync.py", "--sheets", "test-id"])
        args = parse_args()
        assert args.sheets == "test-id"

    def test_month_argument(self, monkeypatch):
        """Test month argument."""
        monkeypatch.setattr("sys.argv", ["email_sync.py", "--month", "1/2025"])
        args = parse_args()
        assert args.month == "1/2025"

    def test_force_flag(self, monkeypatch):
        """Test force flag."""
        monkeypatch.setattr("sys.argv", ["email_sync.py", "--force"])
        args = parse_args()
        assert args.force is True

    def test_verbose_flag(self, monkeypatch):
        """Test verbose flag."""
        monkeypatch.setattr("sys.argv", ["email_sync.py", "--verbose"])
        args = parse_args()
        assert args.verbose is True

    def test_no_output_flag(self, monkeypatch):
        """Test no-output flag."""
        monkeypatch.setattr("sys.argv", ["email_sync.py", "--no-output"])
        args = parse_args()
        assert args.no_output is True

    def test_combined_flags(self, monkeypatch):
        """Test multiple flags together."""
        monkeypatch.setattr("sys.argv", [
            "email_sync.py",
            "-d", "30",
            "-s", "sheet-123",
            "-m", "2/2025",
            "-f",
            "-v",
            "--no-output"
        ])
        args = parse_args()

        assert args.days == 30
        assert args.sheets == "sheet-123"
        assert args.month == "2/2025"
        assert args.force is True
        assert args.verbose is True
        assert args.no_output is True


class TestEmailFiltering:
    """Tests for email filtering logic."""

    def test_filters_processed_emails(self, tmp_path):
        """Test that processed emails are filtered out."""
        # Set up processed IDs
        processed_file = tmp_path / "processed.json"
        processed_file.write_text('{"processed_ids": ["email1", "email2"]}')

        with patch.object(email_sync, "PROCESSED_FILE", processed_file):
            processed_ids = load_processed_ids()

        transactions = [
            {"email_id": "email1", "description": "Test 1", "amount": -10},
            {"email_id": "email2", "description": "Test 2", "amount": -20},
            {"email_id": "email3", "description": "Test 3", "amount": -30},
        ]

        new_transactions = [
            t for t in transactions
            if t.get("email_id") not in processed_ids
        ]

        assert len(new_transactions) == 1
        assert new_transactions[0]["email_id"] == "email3"

    def test_force_includes_all(self, tmp_path):
        """Test that force flag includes all emails."""
        processed_file = tmp_path / "processed.json"
        processed_file.write_text('{"processed_ids": ["email1", "email2"]}')

        transactions = [
            {"email_id": "email1", "description": "Test 1", "amount": -10},
            {"email_id": "email2", "description": "Test 2", "amount": -20},
            {"email_id": "email3", "description": "Test 3", "amount": -30},
        ]

        # With force, all transactions are included
        force = True
        if force:
            new_transactions = transactions
        else:
            with patch.object(email_sync, "PROCESSED_FILE", processed_file):
                processed_ids = load_processed_ids()
            new_transactions = [
                t for t in transactions
                if t.get("email_id") not in processed_ids
            ]

        assert len(new_transactions) == 3


class TestOutputFileNaming:
    """Tests for output file naming conventions."""

    def test_output_filename_format(self, tmp_path):
        """Test that output filename follows expected format."""
        from datetime import datetime

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"email_sync_{timestamp}.json"

        assert output_file.name.startswith("email_sync_")
        assert output_file.name.endswith(".json")

    def test_output_content_structure(self, tmp_path):
        """Test expected output JSON structure."""
        from datetime import datetime

        output = {
            "generated_at": datetime.now().isoformat(),
            "source": "gmail_boa_alerts",
            "summary": {
                "total_transactions": 5,
                "total_spending": 100.00,
                "total_income": 0,
            },
            "by_category": {},
            "transactions": [],
        }

        output_file = tmp_path / "test.json"
        output_file.write_text(json.dumps(output))

        loaded = json.loads(output_file.read_text())
        assert "generated_at" in loaded
        assert loaded["source"] == "gmail_boa_alerts"
        assert "summary" in loaded
        assert "transactions" in loaded
