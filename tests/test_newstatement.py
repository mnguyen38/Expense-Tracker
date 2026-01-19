"""Tests for new statement processor module."""

import pytest
from pathlib import Path

from newstatement import (
    parse_month_arg,
    find_latest_month_folder,
    get_next_month,
    create_next_month_folder,
    MONTHS,
)


class TestMonths:
    """Tests for MONTHS constant."""

    def test_months_count(self):
        """Test that all 12 months are defined."""
        assert len(MONTHS) == 12

    def test_months_order(self):
        """Test months are in correct order."""
        assert MONTHS[0] == "January"
        assert MONTHS[5] == "June"
        assert MONTHS[11] == "December"


class TestParseMonthArg:
    """Tests for parse_month_arg function."""

    def test_parse_month_name_format(self):
        """Test parsing 'December 2025' format."""
        result = parse_month_arg("December 2025")
        assert result == (2025, 11)  # December is index 11

    def test_parse_month_name_case_insensitive(self):
        """Test parsing with different case."""
        result = parse_month_arg("january 2025")
        assert result == (2025, 0)

        result = parse_month_arg("MARCH 2026")
        assert result == (2026, 2)

    def test_parse_slash_format(self):
        """Test parsing 'M/YYYY' format."""
        result = parse_month_arg("12/2025")
        assert result == (2025, 11)

        result = parse_month_arg("1/2026")
        assert result == (2026, 0)

    def test_parse_double_digit_month(self):
        """Test parsing double-digit month number."""
        result = parse_month_arg("01/2025")
        assert result == (2025, 0)

    def test_parse_invalid_format(self):
        """Test parsing invalid format returns None."""
        assert parse_month_arg("Invalid") is None
        assert parse_month_arg("2025") is None
        assert parse_month_arg("") is None

    def test_parse_invalid_month_number(self):
        """Test parsing invalid month number."""
        assert parse_month_arg("13/2025") is None
        assert parse_month_arg("0/2025") is None

    def test_parse_with_whitespace(self):
        """Test parsing with extra whitespace."""
        result = parse_month_arg("  December 2025  ")
        assert result == (2025, 11)


class TestFindLatestMonthFolder:
    """Tests for find_latest_month_folder function."""

    def test_find_latest_with_pdfs(self, tmp_path):
        """Test finding folder with PDFs."""
        # Create folder structure
        statements_dir = tmp_path / "statements"
        dec_folder = statements_dir / "2025" / "December"
        dec_folder.mkdir(parents=True)
        (dec_folder / "statement.pdf").touch()

        result = find_latest_month_folder(statements_dir)
        assert result is not None
        path, year, month_idx = result
        assert year == 2025
        assert month_idx == 11
        assert path == dec_folder

    def test_find_latest_skips_empty_folders(self, tmp_path):
        """Test that empty folders are skipped."""
        statements_dir = tmp_path / "statements"

        # Create December (empty) and November (with PDF)
        dec_folder = statements_dir / "2025" / "December"
        dec_folder.mkdir(parents=True)

        nov_folder = statements_dir / "2025" / "November"
        nov_folder.mkdir(parents=True)
        (nov_folder / "statement.pdf").touch()

        result = find_latest_month_folder(statements_dir)
        path, year, month_idx = result
        assert month_idx == 10  # November

    def test_find_latest_across_years(self, tmp_path):
        """Test finding latest folder across multiple years."""
        statements_dir = tmp_path / "statements"

        # Create folders for 2024 and 2025
        old_folder = statements_dir / "2024" / "December"
        old_folder.mkdir(parents=True)
        (old_folder / "statement.pdf").touch()

        new_folder = statements_dir / "2025" / "January"
        new_folder.mkdir(parents=True)
        (new_folder / "statement.pdf").touch()

        result = find_latest_month_folder(statements_dir)
        path, year, month_idx = result
        assert year == 2025
        assert month_idx == 0  # January

    def test_find_none_when_dir_missing(self, tmp_path):
        """Test returns None when directory doesn't exist."""
        statements_dir = tmp_path / "nonexistent"
        result = find_latest_month_folder(statements_dir)
        assert result is None

    def test_find_none_when_no_year_folders(self, tmp_path):
        """Test returns None when no year folders exist."""
        statements_dir = tmp_path / "statements"
        statements_dir.mkdir()
        result = find_latest_month_folder(statements_dir)
        assert result is None

    def test_find_none_when_no_pdfs(self, tmp_path):
        """Test returns None when no PDFs exist."""
        statements_dir = tmp_path / "statements"
        folder = statements_dir / "2025" / "December"
        folder.mkdir(parents=True)
        # Folder exists but no PDFs

        result = find_latest_month_folder(statements_dir)
        assert result is None


class TestGetNextMonth:
    """Tests for get_next_month function."""

    def test_mid_year(self):
        """Test getting next month mid-year."""
        year, month_idx, name = get_next_month(2025, 5)  # June
        assert year == 2025
        assert month_idx == 6
        assert name == "July"

    def test_december_to_january(self):
        """Test December to January transition."""
        year, month_idx, name = get_next_month(2025, 11)  # December
        assert year == 2026
        assert month_idx == 0
        assert name == "January"

    def test_january(self):
        """Test January to February."""
        year, month_idx, name = get_next_month(2025, 0)  # January
        assert year == 2025
        assert month_idx == 1
        assert name == "February"

    def test_november(self):
        """Test November to December."""
        year, month_idx, name = get_next_month(2025, 10)  # November
        assert year == 2025
        assert month_idx == 11
        assert name == "December"


class TestCreateNextMonthFolder:
    """Tests for create_next_month_folder function."""

    def test_create_folder_same_year(self, tmp_path):
        """Test creating next month folder within same year."""
        statements_dir = tmp_path / "statements"
        statements_dir.mkdir()

        result = create_next_month_folder(statements_dir, 2025, 5)  # June -> July

        assert result.exists()
        assert result == statements_dir / "2025" / "July"

    def test_create_folder_year_boundary(self, tmp_path):
        """Test creating folder across year boundary."""
        statements_dir = tmp_path / "statements"
        statements_dir.mkdir()

        result = create_next_month_folder(statements_dir, 2025, 11)  # Dec -> Jan 2026

        assert result.exists()
        assert result == statements_dir / "2026" / "January"

    def test_create_folder_creates_parent(self, tmp_path):
        """Test that parent year folder is created."""
        statements_dir = tmp_path / "statements"
        # Don't create statements_dir yet

        result = create_next_month_folder(statements_dir, 2025, 6)

        assert result.exists()
        assert (statements_dir / "2025").exists()

    def test_create_folder_idempotent(self, tmp_path):
        """Test that creating existing folder is idempotent."""
        statements_dir = tmp_path / "statements"
        existing_folder = statements_dir / "2025" / "July"
        existing_folder.mkdir(parents=True)

        # Should not raise error
        result = create_next_month_folder(statements_dir, 2025, 5)

        assert result.exists()
        assert result == existing_folder


class TestStatementMonthFormat:
    """Tests for statement month format calculation."""

    def test_january_statement(self):
        """Test January statement month format."""
        month_idx = 0  # January
        year = 2026
        statement_month = f"{month_idx + 1}/{year}"
        assert statement_month == "1/2026"

    def test_december_statement(self):
        """Test December statement month format."""
        month_idx = 11  # December
        year = 2025
        statement_month = f"{month_idx + 1}/{year}"
        assert statement_month == "12/2025"


class TestEdgeCases:
    """Edge case tests."""

    def test_parse_month_with_extra_text(self):
        """Test parsing month with extra text after."""
        # Should match even with extra text
        result = parse_month_arg("December 2025 statement")
        assert result is not None
        assert result[1] == 11  # December

    def test_find_latest_with_non_year_folders(self, tmp_path):
        """Test that non-year folders are ignored."""
        statements_dir = tmp_path / "statements"
        (statements_dir / "notes").mkdir(parents=True)
        (statements_dir / "backup").mkdir(parents=True)

        dec_folder = statements_dir / "2025" / "December"
        dec_folder.mkdir(parents=True)
        (dec_folder / "statement.pdf").touch()

        result = find_latest_month_folder(statements_dir)
        assert result is not None
        _, year, _ = result
        assert year == 2025

    def test_find_latest_multiple_pdfs(self, tmp_path):
        """Test folder with multiple PDFs is still found."""
        statements_dir = tmp_path / "statements"
        dec_folder = statements_dir / "2025" / "December"
        dec_folder.mkdir(parents=True)
        (dec_folder / "checking.pdf").touch()
        (dec_folder / "savings.pdf").touch()
        (dec_folder / "credit_card.pdf").touch()

        result = find_latest_month_folder(statements_dir)
        assert result is not None
        path, _, _ = result
        pdfs = list(path.glob("*.pdf"))
        assert len(pdfs) == 3
