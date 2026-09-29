"""Universal AI-powered statement parser using Claude."""

import os
from pathlib import Path

import anthropic

from ..llm import request_json
from .base import BaseParser, ParseResult

# Output-token ceiling for one extraction; a truncated reply raises instead of
# silently dropping transactions.
MAX_OUTPUT_TOKENS = 16000

_NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}
_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}

# JSON schema enforced through structured outputs, so the reply always parses
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "bank_name": {"type": "string"},
        "currency": {"type": "string"},
        "statement_type": {"type": "string", "enum": ["checking", "savings", "credit_card"]},
        "statement_period": {
            "type": "object",
            "properties": {"start": _NULLABLE_STRING, "end": _NULLABLE_STRING},
            "required": ["start", "end"],
            "additionalProperties": False,
        },
        "opening_balance": _NULLABLE_NUMBER,
        "closing_balance": _NULLABLE_NUMBER,
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                    "is_internal_transfer": {"type": "boolean"},
                },
                "required": ["date", "description", "amount", "is_internal_transfer"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "bank_name",
        "currency",
        "statement_type",
        "statement_period",
        "opening_balance",
        "closing_balance",
        "transactions",
    ],
    "additionalProperties": False,
}

PROMPT_TEMPLATE = """Extract every transaction from this bank statement.

<statement>
{text}
</statement>

Rules:
- Expenses, withdrawals and purchases are NEGATIVE amounts; income, deposits and credits are POSITIVE.
- On credit card statements, purchases are negative and payments to the card are positive.
- Mark transfers between the account holder's own accounts (e.g. "transfer to savings",
  "payment to credit card") with is_internal_transfer=true.
- Include every transaction; the balances are checked against their sum afterwards.
- Dates are ISO YYYY-MM-DD. statement_period start/end are null if not shown.
- Clean merchant names: drop reference numbers, card digits and location codes.
- opening_balance / closing_balance are the statement's beginning and ending balances
  (for credit cards: previous and new balance owed), or null if absent.
- Detect currency from symbols (£, $, €) or the bank's location; use the ISO code."""


class AIParser(BaseParser):
    """
    Universal parser that uses Claude AI to extract transactions from any bank statement.
    This is the fallback parser when no optimized parser matches with high confidence.
    """

    bank_id = "ai_parsed"
    bank_name = "AI Detected"
    currency = "USD"  # Will be overridden by AI detection

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model

    def detect(self, text: str) -> float:
        """
        AI parser is the universal fallback - always returns low confidence
        so optimized parsers take precedence when available.
        """
        return 0.1

    def parse(self, pdf_path: Path, text: str) -> ParseResult:
        """Parse any bank statement using Claude AI."""
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found. Set it as an environment variable.")

        client = anthropic.Anthropic(api_key=self.api_key)
        data = request_json(
            client,
            PROMPT_TEMPLATE.format(text=text),
            EXTRACTION_SCHEMA,
            max_tokens=MAX_OUTPUT_TOKENS,
            model=self.model,
        )

        transactions = [
            {
                "date": txn.get("date", ""),
                "description": txn.get("description", ""),
                "amount": float(txn.get("amount", 0)),
                "is_internal": txn.get("is_internal_transfer", False),
            }
            for txn in data.get("transactions", [])
        ]

        statement_type = data.get("statement_type", "checking")
        expenses, income, debt_payments = self.separate_transactions(transactions, statement_type)

        period = data.get("statement_period") or {}
        statement_period = None
        if period.get("start") and period.get("end"):
            statement_period = (period["start"], period["end"])

        bank_name = data.get("bank_name", "Unknown Bank")
        bank_id = bank_name.lower().replace(" ", "_").replace(".", "")[:20]

        result = ParseResult(
            bank_id=bank_id,
            bank_name=bank_name,
            currency=data.get("currency", "USD"),
            statement_type=statement_type,
            statement_period=statement_period,
            opening_balance=data.get("opening_balance"),
            closing_balance=data.get("closing_balance"),
            transactions=transactions,
            expenses=expenses,
            income=income,
            debt_payments=debt_payments,
        )
        result.reconcile()
        return result
