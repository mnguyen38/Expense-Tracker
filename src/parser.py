"""
Backwards-compatible wrapper for the new parsers module.

This module redirects to the new parsers package for backwards compatibility.
New code should import directly from parsers:

    from parsers import parse_statement
"""

from parsers import parse_statement, ParseResult, BaseParser

__all__ = ["parse_statement", "ParseResult", "BaseParser"]
