# Expense Tracker

Tool used for streamline the process of keeping track of expenses. Used in conjunction with Google Sheets template: https://docs.google.com/spreadsheets/d/1SB7cCd_Rk9HHEtjDYb_mGKYBR-68Y-Dqe1IuPMHQg_E/copy. Uses Claude for categorizing transactions. 

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## Features

- **PDF Parsing** - Works with any bank statement format using AI-powered extraction
- **Spending Categorization** - Claude automatically categorizes your transactions
- **Google Sheets Sync** - Optional integration to track expenses in spreadsheets
- **Email Sync** - Fetch transactions from email notifications
- **SMS Alerts** - Get notified when spending crosses thresholds

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/expense-tracker.git
cd expense-tracker

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your Anthropic API key

# Run the CLI
python src/main.py statement.pdf
```

## Usage

```bash
# Parse a single PDF
python src/main.py statement.pdf

# Parse all PDFs in a directory
python src/main.py ./statements/

# Parse and sync to Google Sheets
python src/main.py statement.pdf -s SHEET_ID -m 1/2026

# Show help
python src/main.py --help
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-o, --output DIR` | Output directory for JSON files (default: output) |
| `-s, --sheets ID` | Google Sheet ID or URL to sync results to |
| `-m, --month M/YYYY` | Month for Google Sheets row (e.g., '1/2026') |
| `-v, --verbose` | Show detailed error messages |
| `--no-output` | Skip writing JSON output file |
| `--clean` | Delete all output files and exit |

## Requirements

- **Python 3.10+**
- **Anthropic API Key** - (https://console.anthropic.com/settings/keys)
- **Google Cloud credentials** (optional but required if used together with provided spreadsheet)

## Configuration

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_SHEET_ID=your-sheet-id
```

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `GOOGLE_SHEET_ID` | No | Google Sheet ID for sync |

## Project Structure

```
expense-tracker/
├── src/
│   ├── main.py              # CLI entry point
│   ├── parsers/             # Bank statement parsers
│   │   ├── base.py          # Base parser class
│   │   ├── ai_parser.py     # Universal AI parser
│   │   └── boa.py           # Bank of America parser
│   ├── categorizer.py       # AI categorization logic
│   ├── sheets.py            # Google Sheets integration
│   ├── email_sync.py        # Email transaction sync
│   └── notifications.py     # SMS alerts
├── tests/                   # Test suite
├── requirements.txt
└── README.md
```

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=html
```

## Adding a New Bank Parser Example

Create optimized parsers for specific banks:

```python
# src/parsers/chase.py
from .base import BaseParser, ParseResult

class ChaseParser(BaseParser):
    bank_id = "chase"
    bank_name = "Chase"
    currency = "USD"

    def detect(self, text: str) -> float:
        if "JPMorgan Chase" in text:
            return 1.0
        return 0.0

    def parse(self, pdf_path, text) -> ParseResult:
        # Custom parsing logic
        ...
```

Parsers are auto-discovered and used when they return high confidence. Currently implemented a parser for BoA.

## License

MIT License - see [LICENSE](LICENSE) for details.
