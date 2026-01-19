"""Bank of America statement parser - optimized regex-based parser."""

import re
from datetime import datetime
from pathlib import Path

from .base import BaseParser, ParseResult


class BOAParser(BaseParser):
    """
    Optimized parser for Bank of America statements.
    Supports credit card, checking, and savings statements.
    """

    bank_id = "boa"
    bank_name = "Bank of America"
    currency = "USD"

    # BoA-specific internal transfer patterns
    internal_transfer_patterns = [
        r"Online Banking transfer",
        r"Mobile Banking payment to CRD",
        r"Mobile Banking payment to CHK",
        r"Mobile Banking payment to SAV",
        r"transfer to CHK",
        r"transfer to SAV",
        r"transfer to CRD",
        r"transfer from CHK",
        r"transfer from SAV",
        r"payment to CRD \d+",
    ]

    def detect(self, text: str) -> float:
        """
        Return confidence score for Bank of America statement.
        """
        text_lower = text.lower()
        score = 0.0

        # Strong indicators
        if "bank of america" in text_lower:
            score += 0.5
        if "bankofamerica.com" in text_lower:
            score += 0.3

        # Account type indicators
        if "advantage checking" in text_lower or "safebalance" in text_lower:
            score += 0.2
        if "advantage savings" in text_lower:
            score += 0.2
        if "purchases and adjustments" in text_lower:
            score += 0.2

        return min(score, 1.0)

    def parse(self, pdf_path: Path, text: str) -> ParseResult:
        """Parse Bank of America statement."""
        # Extract statement period
        statement_year, statement_start_month = self._extract_statement_period(text)

        # Detect statement type
        statement_type = self._detect_statement_type(text)

        # Parse based on statement type
        if statement_type == "credit_card":
            transactions = self._parse_credit_card_statement(
                text, statement_year, statement_start_month
            )
            closing_balance = self._extract_credit_card_balance(text)
        else:
            transactions = self._parse_bank_account_statement(
                text, statement_type, statement_year, statement_start_month
            )
            closing_balance = self._extract_ending_balance(text)

        # Separate into expenses/income/debt_payments
        expenses, income, debt_payments = self.separate_transactions(
            transactions, statement_type
        )

        # Extract statement period dates
        statement_period = self._extract_period_dates(text)

        return ParseResult(
            bank_id=self.bank_id,
            bank_name=self.bank_name,
            currency=self.currency,
            statement_type=statement_type,
            statement_period=statement_period,
            opening_balance=None,  # BoA doesn't show opening balance clearly
            closing_balance=closing_balance,
            transactions=transactions,
            expenses=expenses,
            income=income,
            debt_payments=debt_payments,
        )

    def _detect_statement_type(self, text: str) -> str:
        """Detect the type of BoA statement."""
        text_lower = text.lower()

        if "credit card" in text_lower or "purchases and adjustments" in text_lower:
            return "credit_card"
        elif "safebalance" in text_lower or "advantage checking" in text_lower:
            return "checking"
        elif "advantage savings" in text_lower:
            return "savings"
        else:
            return "credit_card"  # Default

    def _extract_statement_period(self, text: str) -> tuple[int, int]:
        """Extract the year and start month from statement period header."""
        pattern = r"(\w+)\s+\d+\s*[-–]\s*\w+\s+\d+,?\s*(\d{4})"
        match = re.search(pattern, text)
        if match:
            start_month_name = match.group(1)
            year = int(match.group(2))
            month_map = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12
            }
            start_month = month_map.get(start_month_name.lower(), 1)
            return year, start_month
        return datetime.now().year, 1

    def _extract_period_dates(self, text: str) -> tuple[str, str] | None:
        """Extract statement period as ISO date strings."""
        # Pattern: "December 12 - January 11, 2026"
        pattern = r"(\w+)\s+(\d+)\s*[-–]\s*(\w+)\s+(\d+),?\s*(\d{4})"
        match = re.search(pattern, text)
        if match:
            start_month_name = match.group(1)
            start_day = int(match.group(2))
            end_month_name = match.group(3)
            end_day = int(match.group(4))
            year = int(match.group(5))

            month_map = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12
            }
            start_month = month_map.get(start_month_name.lower(), 1)
            end_month = month_map.get(end_month_name.lower(), 1)

            # Handle year boundary (Dec-Jan)
            start_year = year - 1 if start_month > end_month else year

            start_date = f"{start_year}-{start_month:02d}-{start_day:02d}"
            end_date = f"{year}-{end_month:02d}-{end_day:02d}"
            return (start_date, end_date)
        return None

    def _extract_ending_balance(self, text: str) -> float | None:
        """Extract the ending balance from a bank account statement."""
        pattern = r"Ending balance on .+?\$?([\d,]+\.\d{2})"
        match = re.search(pattern, text)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _extract_credit_card_balance(self, text: str) -> float | None:
        """Extract the new balance from a credit card statement."""
        # Try various "New Balance" patterns
        patterns = [
            r"New Balance Total\s+\$?([\d,]+\.\d{2})",
            r"New Balance\s+\$?([\d,]+\.\d{2})",
            r"Statement Balance\s+\$?([\d,]+\.\d{2})",
            r"Total New Balance\s+\$?([\d,]+\.\d{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1).replace(",", ""))
        return None

    def _parse_boa_date(self, date_str: str, statement_year: int, statement_start_month: int) -> str:
        """Parse MM/DD date and infer year based on statement period."""
        try:
            month, day = map(int, date_str.split("/"))

            if statement_start_month >= 10:
                # Statement spans year boundary (e.g., Dec-Jan)
                if month <= 3:
                    year = statement_year
                else:
                    year = statement_year - 1
            else:
                year = statement_year

            return f"{year}-{month:02d}-{day:02d}"
        except (ValueError, AttributeError):
            return date_str

    def _parse_credit_card_statement(
        self, text: str, statement_year: int, statement_start_month: int
    ) -> list[dict]:
        """Parse credit card statement and return transactions."""
        transactions = []
        lines = text.split("\n")

        in_payments_section = False
        in_purchases_section = False

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Detect section headers
            if "Payments and Other Credits" in line:
                in_payments_section = True
                in_purchases_section = False
                i += 1
                continue
            elif "Purchases and Adjustments" in line:
                in_payments_section = False
                in_purchases_section = True
                i += 1
                continue
            elif "TOTAL PAYMENTS" in line or "TOTAL PURCHASES" in line or "Interest Charged" in line:
                in_payments_section = False
                in_purchases_section = False
                i += 1
                continue

            if not (in_payments_section or in_purchases_section):
                i += 1
                continue

            # Try to parse transaction line
            txn_match = re.match(
                r"^(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(.+?)\s+(\d{4})\s+(\d{4})\s+([-]?[\d,]+\.?\d*)\s*$",
                line
            )

            if txn_match:
                trans_date_str = txn_match.group(1)
                description = txn_match.group(3).strip()
                amount_str = txn_match.group(6).replace(",", "")

                date = self._parse_boa_date(trans_date_str, statement_year, statement_start_month)

                try:
                    amount = float(amount_str)
                except ValueError:
                    i += 1
                    continue

                # Check for foreign currency
                foreign_amount = None
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    foreign_match = re.match(r"^([\d,]+\.?\d*)\s+([A-Z]{3})$", next_line)
                    if foreign_match:
                        foreign_amount = f"{foreign_match.group(1)} {foreign_match.group(2)}"

                # For purchases, amounts should be negative (spending)
                if in_purchases_section and amount > 0:
                    amount = -amount
                elif in_payments_section and amount < 0:
                    amount = abs(amount)

                transactions.append({
                    "date": date,
                    "description": description,
                    "amount": amount,
                    "foreign_amount": foreign_amount
                })

            i += 1

        return transactions

    def _parse_bank_account_statement(
        self, text: str, account_type: str, statement_year: int, statement_start_month: int
    ) -> list[dict]:
        """Parse checking or savings account statement."""
        transactions = []
        lines = text.split("\n")

        in_deposits_section = False
        in_withdrawals_section = False

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Detect section headers
            if "Deposits and other additions" in line:
                in_deposits_section = True
                in_withdrawals_section = False
                i += 1
                continue
            elif "Withdrawals and other subtractions" in line:
                in_deposits_section = False
                in_withdrawals_section = True
                i += 1
                continue
            elif "ATM and debit card subtractions" in line:
                i += 1
                continue
            elif "Other subtractions" in line:
                i += 1
                continue
            elif "Total deposits" in line or "Total ATM" in line or "Total other" in line:
                i += 1
                continue
            elif "Braille and Large Print" in line or "This page intentionally" in line:
                in_deposits_section = False
                in_withdrawals_section = False
                i += 1
                continue

            if not (in_deposits_section or in_withdrawals_section):
                i += 1
                continue

            # Try to parse transaction line (MM/DD/YY Description Amount)
            txn_match = re.match(
                r"^(\d{2}/\d{2}/\d{2})\s+(.+?)\s+([-]?[\d,]+\.?\d{2})\s*$",
                line
            )

            if txn_match:
                date_str = txn_match.group(1)
                description = txn_match.group(2).strip()
                amount_str = txn_match.group(3).replace(",", "")

                # Parse MM/DD/YY date
                try:
                    month, day, year = date_str.split("/")
                    year = int(year)
                    if year < 100:
                        year += 2000
                    date = f"{year}-{int(month):02d}-{int(day):02d}"
                except ValueError:
                    date = date_str

                try:
                    amount = float(amount_str)
                except ValueError:
                    i += 1
                    continue

                # Deposits are positive, withdrawals are negative
                if in_withdrawals_section and amount > 0:
                    amount = -amount

                transactions.append({
                    "date": date,
                    "description": description,
                    "amount": amount,
                    "account_type": account_type,
                })

            i += 1

        return transactions
