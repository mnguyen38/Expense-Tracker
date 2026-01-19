"""Universal AI-powered statement parser using Claude."""

import json
import os
from pathlib import Path

import anthropic

from .base import BaseParser, ParseResult


class AIParser(BaseParser):
    """
    Universal parser that uses Claude AI to extract transactions from any bank statement.
    This is the fallback parser when no optimized parser matches with high confidence.
    """

    bank_id = "ai_parsed"
    bank_name = "AI Detected"
    currency = "USD"  # Will be overridden by AI detection

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def detect(self, text: str) -> float:
        """
        AI parser is the universal fallback - always returns low confidence
        so optimized parsers take precedence when available.
        """
        # Return 0.1 so this parser is only used as fallback
        return 0.1

    def parse(self, pdf_path: Path, text: str) -> ParseResult:
        """Parse any bank statement using Claude AI."""
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Set it as an environment variable."
            )

        client = anthropic.Anthropic(api_key=self.api_key)

        # Truncate text if too long (keep first and last parts for context)
        max_chars = 50000
        if len(text) > max_chars:
            half = max_chars // 2
            text = text[:half] + "\n\n... [truncated] ...\n\n" + text[-half:]

        prompt = f"""Analyze this bank statement and extract all transactions.

STATEMENT TEXT:
{text}

Return a JSON object with this EXACT structure (no markdown, just raw JSON):
{{
    "bank_name": "detected bank name (e.g., Bank of America, HSBC, Chase)",
    "currency": "USD or GBP or EUR etc",
    "statement_type": "checking or savings or credit_card",
    "statement_period": {{
        "start": "YYYY-MM-DD or null if not found",
        "end": "YYYY-MM-DD or null if not found"
    }},
    "opening_balance": number or null,
    "closing_balance": number or null,
    "transactions": [
        {{
            "date": "YYYY-MM-DD",
            "description": "merchant/payee name (clean it up, remove extra codes)",
            "amount": number,
            "is_internal_transfer": true or false
        }}
    ]
}}

CRITICAL RULES:
1. Expenses/withdrawals/purchases MUST be NEGATIVE amounts
2. Income/deposits/credits MUST be POSITIVE amounts
3. Internal transfers between accounts (e.g., "transfer to savings", "payment to credit card"): set is_internal_transfer=true
4. Parse ALL transactions - don't skip any
5. Use ISO date format YYYY-MM-DD
6. Clean up merchant names - remove reference numbers, card digits, location codes where possible
7. For credit card statements: purchases are expenses (negative), payments are positive
8. Detect the currency from symbols (£, $, €) or bank name/location

Return ONLY the JSON object, no explanation or markdown."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Clean up response - remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            # Remove first and last lines (```json and ```)
            response_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            # Return minimal valid result instead of crashing
            print(f"Warning: Failed to parse AI response as JSON: {e}")
            return ParseResult(
                bank_id="unknown",
                bank_name="Unknown",
                currency="USD",
                statement_type="unknown",
                transactions=[],
                expenses=[],
                income=[],
                debt_payments=[],
            )

        # Build transactions list
        transactions = []
        for txn in data.get("transactions", []):
            transactions.append({
                "date": txn.get("date", ""),
                "description": txn.get("description", ""),
                "amount": float(txn.get("amount", 0)),
                "is_internal": txn.get("is_internal_transfer", False),
            })

        # Separate into expenses/income/debt_payments
        expenses = []
        income = []
        debt_payments = []
        statement_type = data.get("statement_type", "checking")

        for txn in transactions:
            if txn.get("is_internal"):
                continue

            amount = txn.get("amount", 0)
            description = txn.get("description", "")

            if amount < 0:
                expenses.append(txn)
                if self.is_debt_payment(description):
                    debt_payments.append(txn)
            elif amount > 0 and statement_type in ("checking", "savings"):
                income.append(txn)

        # Extract period
        period = data.get("statement_period", {})
        statement_period = None
        if period and period.get("start") and period.get("end"):
            statement_period = (period["start"], period["end"])

        # Generate bank_id from bank_name
        bank_name = data.get("bank_name", "Unknown Bank")
        bank_id = bank_name.lower().replace(" ", "_").replace(".", "")[:20]

        return ParseResult(
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
