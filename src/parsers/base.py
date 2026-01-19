"""Base classes and types for statement parsers."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable
import re


@dataclass
class ParseResult:
    """Standardized result from any statement parser."""

    # Bank identification
    bank_id: str                    # "boa", "hsbc_uk", "chase", etc.
    bank_name: str                  # "Bank of America", "HSBC UK"
    currency: str                   # "USD", "GBP", "EUR"

    # Statement metadata
    statement_type: str             # "checking", "savings", "credit_card"
    statement_period: tuple[str, str] | None = None  # (start_date, end_date) ISO format

    # Balances
    opening_balance: float | None = None
    closing_balance: float | None = None

    # Transactions (all amounts: negative=expense, positive=income)
    transactions: list[dict] = field(default_factory=list)
    expenses: list[dict] = field(default_factory=list)
    income: list[dict] = field(default_factory=list)
    debt_payments: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for backwards compatibility."""
        return {
            "bank_id": self.bank_id,
            "bank_name": self.bank_name,
            "currency": self.currency,
            "statement_type": self.statement_type,
            "statement_period": self.statement_period,
            "opening_balance": self.opening_balance,
            "ending_balance": self.closing_balance,  # Alias for backwards compat
            "closing_balance": self.closing_balance,
            "all_transactions": self.transactions,
            "expenses": self.expenses,
            "income": self.income,
            "debt_payments": self.debt_payments,
        }


@runtime_checkable
class StatementParser(Protocol):
    """Protocol defining what a statement parser must implement."""

    bank_id: str
    bank_name: str
    currency: str

    def detect(self, text: str) -> float:
        """
        Return confidence score 0.0-1.0 that this parser handles the statement.
        Higher scores indicate better match.
        """
        ...

    def parse(self, pdf_path: Path, text: str) -> ParseResult:
        """Parse the statement and return standardized result."""
        ...


class BaseParser:
    """
    Optional base class with common utilities.
    Parsers can inherit from this or implement StatementParser protocol directly.
    """

    bank_id: str = "unknown"
    bank_name: str = "Unknown Bank"
    currency: str = "USD"

    # Override in subclasses with bank-specific patterns
    internal_transfer_patterns: list[str] = []
    debt_payment_keywords: list[str] = ["loan", "mortgage", "student", "financial", "sallie"]

    def is_internal_transfer(self, description: str) -> bool:
        """Check if transaction is an internal transfer between accounts."""
        for pattern in self.internal_transfer_patterns:
            if re.search(pattern, description, re.IGNORECASE):
                return True
        return False

    def is_debt_payment(self, description: str) -> bool:
        """Check if transaction is a debt/loan payment."""
        desc_lower = description.lower()
        return any(kw in desc_lower for kw in self.debt_payment_keywords)

    def parse_amount(self, amount_str: str) -> float:
        """Parse amount string, handling commas and currency symbols."""
        cleaned = re.sub(r"[£$€,\s]", "", amount_str)
        return float(cleaned)

    def separate_transactions(
        self,
        transactions: list[dict],
        statement_type: str
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """
        Separate transactions into expenses, income, and debt payments.
        Filters out internal transfers.

        Returns:
            Tuple of (expenses, income, debt_payments)
        """
        expenses = []
        income = []
        debt_payments = []

        for txn in transactions:
            description = txn.get("description", "")
            amount = txn.get("amount", 0)

            # Skip internal transfers
            if self.is_internal_transfer(description):
                txn["is_internal"] = True
                continue

            if amount < 0:
                # Negative = expense
                expenses.append(txn)
                if self.is_debt_payment(description):
                    debt_payments.append(txn)
            elif amount > 0 and statement_type in ("checking", "savings"):
                # Positive in bank account = income (deposits)
                income.append(txn)

        return expenses, income, debt_payments
