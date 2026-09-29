"""Tests for parser registry and dispatch module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from expense_tracker import parsers
from expense_tracker.parsers import BaseParser, ParseResult, get_available_parsers, parse_statement


class TestParserDiscovery:
    """Tests for parser auto-discovery."""

    def test_get_available_parsers(self):
        """Test that get_available_parsers returns parser info."""
        available = get_available_parsers()

        assert isinstance(available, list)
        # Should have at least the BoA parser
        assert len(available) >= 1

        # Check structure
        for parser_info in available:
            assert "bank_id" in parser_info
            assert "bank_name" in parser_info
            assert "currency" in parser_info

    def test_boa_parser_discovered(self):
        """Test that BoA parser is discovered."""
        available = get_available_parsers()
        bank_ids = [p["bank_id"] for p in available]

        assert "boa" in bank_ids


class TestTextExtraction:
    """Tests for PDF text extraction."""

    @patch("expense_tracker.parsers.pdfplumber.open")
    def test_extract_text_single_page(self, mock_pdfplumber):
        """Test extracting text from single page PDF."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page 1 content"

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdfplumber.return_value = mock_pdf

        result = parsers._extract_text(Path("test.pdf"))
        assert "Page 1 content" in result

    @patch("expense_tracker.parsers.pdfplumber.open")
    def test_extract_text_multiple_pages(self, mock_pdfplumber):
        """Test extracting text from multi-page PDF."""
        mock_pages = [MagicMock(), MagicMock()]
        mock_pages[0].extract_text.return_value = "Page 1"
        mock_pages[1].extract_text.return_value = "Page 2"

        mock_pdf = MagicMock()
        mock_pdf.pages = mock_pages
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdfplumber.return_value = mock_pdf

        result = parsers._extract_text(Path("test.pdf"))
        assert "Page 1" in result
        assert "Page 2" in result

    @patch("expense_tracker.parsers.pdfplumber.open")
    def test_extract_text_handles_none(self, mock_pdfplumber):
        """Test that None text from page is handled."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = None

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdfplumber.return_value = mock_pdf

        result = parsers._extract_text(Path("test.pdf"))
        assert result == "\n"


class TestParseStatement:
    """Tests for main parse_statement function."""

    def test_parse_statement_file_not_found(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_statement("nonexistent.pdf")

    @patch("expense_tracker.parsers.pdfplumber.open")
    def test_parse_statement_uses_best_parser(self, mock_pdfplumber, boa_checking_text, tmp_path):
        """Test that parser with highest confidence is used."""
        # Create a temp PDF file
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        # Mock PDF extraction to return BoA text
        mock_page = MagicMock()
        mock_page.extract_text.return_value = boa_checking_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdfplumber.return_value = mock_pdf

        result = parse_statement(pdf_path)

        assert result["bank_id"] == "boa"
        assert result["bank_name"] == "Bank of America"

    @patch("expense_tracker.parsers.AIParser")
    @patch("expense_tracker.parsers.pdfplumber.open")
    def test_parse_statement_falls_back_to_ai(self, mock_pdfplumber, mock_ai_parser, tmp_path):
        """Test fallback to AI parser when no optimized parser matches."""
        # Create a temp PDF file
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        # Mock PDF extraction with unknown bank text
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Unknown Bank Statement"

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdfplumber.return_value = mock_pdf

        # Mock AI parser
        mock_parser_instance = MagicMock()
        mock_parser_instance.parse.return_value = ParseResult(
            bank_id="ai_parsed",
            bank_name="AI Detected",
            currency="USD",
            statement_type="checking",
        )
        mock_ai_parser.return_value = mock_parser_instance

        result = parse_statement(pdf_path)

        assert result["bank_id"] == "ai_parsed"
        mock_parser_instance.parse.assert_called_once()

    @patch("expense_tracker.parsers.pdfplumber.open")
    def test_parse_statement_returns_dict(self, mock_pdfplumber, boa_checking_text, tmp_path):
        """Test that parse_statement returns a dictionary."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_page = MagicMock()
        mock_page.extract_text.return_value = boa_checking_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdfplumber.return_value = mock_pdf

        result = parse_statement(pdf_path)

        assert isinstance(result, dict)
        assert "expenses" in result
        assert "income" in result
        assert "all_transactions" in result

    @patch("expense_tracker.parsers.pdfplumber.open")
    def test_parse_statement_accepts_string_path(self, mock_pdfplumber, boa_checking_text, tmp_path):
        """Test that parse_statement accepts string path."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_page = MagicMock()
        mock_page.extract_text.return_value = boa_checking_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdfplumber.return_value = mock_pdf

        # Pass as string instead of Path
        result = parse_statement(str(pdf_path))

        assert isinstance(result, dict)


class TestModuleExports:
    """Tests for module exports."""

    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        assert "parse_statement" in parsers.__all__
        assert "get_available_parsers" in parsers.__all__
        assert "ParseResult" in parsers.__all__
        assert "StatementParser" in parsers.__all__
        assert "BaseParser" in parsers.__all__
        assert "AIParser" in parsers.__all__

    def test_can_import_classes(self):
        """Test that key classes can be imported."""
        from expense_tracker.parsers import AIParser, ParseResult

        assert ParseResult is not None
        assert BaseParser is not None
        assert AIParser is not None
