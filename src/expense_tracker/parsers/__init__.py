"""
Statement parser registry with auto-detection and hybrid parsing.

Usage:
    from expense_tracker.parsers import parse_statement

    result = parse_statement("path/to/statement.pdf")
    # Returns ParseResult with standardized fields

Adding a new bank parser:
    1. Create a new file in parsers/ (e.g., chase.py)
    2. Define a class that implements StatementParser protocol
    3. The parser will be auto-discovered and used when it matches

The system uses a hybrid approach:
    - Optimized regex parsers are tried first (if confidence > 0.7)
    - AI parser is used as fallback for unknown formats
"""

import importlib
import pkgutil
from pathlib import Path

import pdfplumber

from .ai_parser import AIParser
from .base import BaseParser, ParseResult, StatementParser

# Registry of discovered parsers
_PARSERS: list[StatementParser] = []
_DISCOVERED = False


def _discover_parsers():
    """Auto-discover all parser classes in this package."""
    global _PARSERS, _DISCOVERED

    if _DISCOVERED:
        return

    package_dir = Path(__file__).parent

    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        # Skip special modules
        if module_name in ("__init__", "base", "ai_parser"):
            continue

        try:
            module = importlib.import_module(f".{module_name}", __package__)

            # Find classes that look like parsers
            for attr_name in dir(module):
                if not attr_name.endswith("Parser"):
                    continue

                attr = getattr(module, attr_name)

                # Check if it's a class with required methods
                if (
                    isinstance(attr, type)
                    and attr is not BaseParser
                    and hasattr(attr, "detect")
                    and hasattr(attr, "parse")
                ):
                    _PARSERS.append(attr())

        except Exception as e:
            print(f"Warning: Could not load parser module {module_name}: {e}")

    _DISCOVERED = True


def _extract_text(pdf_path: Path) -> str:
    """Extract text from PDF using pdfplumber."""
    all_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_text += text + "\n"
    return all_text


def parse_statement(pdf_path: str | Path, model: str | None = None) -> dict:
    """
    Parse a bank statement PDF and return standardized transaction data.

    This function auto-detects the bank and uses the appropriate parser.
    If no optimized parser matches with high confidence, it falls back to
    the AI-powered universal parser.

    Args:
        pdf_path: Path to the PDF statement file

    Returns:
        Dictionary with standardized fields (backwards compatible):
        - statement_type: "checking", "savings", or "credit_card"
        - expenses: List of expense transactions
        - income: List of income transactions
        - debt_payments: List of debt payment transactions
        - all_transactions: All parsed transactions
        - ending_balance: Account balance (if available)
        - bank_id: Detected bank identifier
        - bank_name: Detected bank name
        - currency: Detected currency
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Discover parsers if not already done
    _discover_parsers()

    # Extract text from PDF
    text = _extract_text(pdf_path)

    # Find best matching parser
    best_parser = None
    best_score = 0.0

    for parser in _PARSERS:
        try:
            score = parser.detect(text)
            if score > best_score:
                best_score = score
                best_parser = parser
        except Exception as e:
            print(f"Warning: {parser.bank_name} detection failed: {e}")
            continue

    # Use optimized parser if confidence is high enough (> 0.7)
    if best_parser and best_score >= 0.7:
        result = best_parser.parse(pdf_path, text)
    else:
        # Fall back to AI parser
        ai_parser = AIParser(model=model)
        result = ai_parser.parse(pdf_path, text)

    # Return as dict for backwards compatibility
    return result.to_dict()


def get_available_parsers() -> list[dict]:
    """Get list of available optimized parsers."""
    _discover_parsers()
    return [
        {
            "bank_id": p.bank_id,
            "bank_name": p.bank_name,
            "currency": p.currency,
        }
        for p in _PARSERS
    ]


# Export key classes
__all__ = [
    "parse_statement",
    "get_available_parsers",
    "ParseResult",
    "StatementParser",
    "BaseParser",
    "AIParser",
]
