"""User configuration: where data lives, which model to use, and the category list."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "claude-sonnet-5"

# Category name -> hint for the AI. Order is the display order.
DEFAULT_CATEGORIES: dict[str, str] = {
    "Housing": "rent, mortgage, property-related costs",
    "Gas (Home)": "home gas utility",
    "Electric": "electricity utility",
    "Internet": "home internet service",
    "Insurance": "health, renters, car or life insurance",
    "Groceries": "supermarkets and grocery stores",
    "Eating Out": "restaurants, cafes, bars, food delivery",
    "Phone": "mobile phone bills",
    "Rideshare": "Uber, Lyft, taxis",
    "Public Transit": "buses, trains, metro",
    "Entertainment": "movies, games, museums, events, video streaming",
    "Clothing": "apparel, shoes, fashion stores",
    "Self Care": "beauty, haircuts, spa",
    "Dry Cleaning": "laundry and dry cleaning",
    "Gym": "gym and fitness memberships",
    "Education": "courses, books, tuition",
    "Medical": "healthcare, pharmacy, doctors",
    "Gifts": "gifts and donations",
    "Fees": "bank fees, interest, late fees",
    "Travel": "flights, hotels, Airbnb, travel bookings",
    "Subscriptions": "software, cloud storage, music and app subscriptions",
    "Misc": "anything that doesn't fit another category",
}

CONFIG_TEMPLATE = """\
# Expense Tracker configuration. Edit freely; delete a key to use its default.

# Claude model for statement extraction and categorization
model = "{model}"

# Day of the month your statements close (1-31). A transaction after this day
# counts toward the next month. 31 means plain calendar months.
statement_close_day = {close_day}

# Email an alert each time a month's spending crosses a multiple of this amount.
# Needs NOTIFY_EMAIL, SMTP_EMAIL and SMTP_PASSWORD in .env. 0 turns alerts off.
alert_threshold = {alert_threshold}

currency_symbol = "{currency_symbol}"

# Google Sheets budget template to sync to (optional)
sheets_id = "{sheets_id}"

# Spending categories: name = "hint that helps the AI choose it".
# Add, rename or remove freely. Keep a "Misc" category as the fallback.
[categories]
{categories}
"""


def default_home() -> Path:
    return Path(os.environ.get("EXPENSE_TRACKER_HOME") or Path.home() / ".expense-tracker")


@dataclass
class Config:
    home: Path
    model: str = DEFAULT_MODEL
    statement_close_day: int = 31
    alert_threshold: float = 1000.0
    currency_symbol: str = "$"
    sheets_id: str = ""
    categories: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CATEGORIES))

    @property
    def config_path(self) -> Path:
        return self.home / "config.toml"

    @property
    def db_path(self) -> Path:
        return self.home / "ledger.db"

    @property
    def alerts_path(self) -> Path:
        return self.home / "alerts.json"

    @property
    def category_names(self) -> list[str]:
        return list(self.categories)

    def write(self) -> Path:
        """Write this config as a commented TOML file (used by `init`)."""
        self.home.mkdir(parents=True, exist_ok=True)
        categories = "\n".join(
            f"{_toml_key(name)} = {_toml_str(hint)}" for name, hint in self.categories.items()
        )
        self.config_path.write_text(
            CONFIG_TEMPLATE.format(
                model=self.model,
                close_day=self.statement_close_day,
                alert_threshold=_format_number(self.alert_threshold),
                currency_symbol=self.currency_symbol,
                sheets_id=self.sheets_id,
                categories=categories,
            ),
            encoding="utf-8",
        )
        return self.config_path


def load_config(home: Path | None = None) -> Config:
    """
    Load config.toml from the data directory, falling back to defaults.

    Environment variables (also read from .env in the working directory or the
    data directory) override the file: ANTHROPIC_MODEL, GOOGLE_SHEET_ID.
    """
    home = Path(home) if home else default_home()
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(home / ".env")

    config = Config(home=home)
    path = config.config_path
    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for key in ("model", "statement_close_day", "alert_threshold", "currency_symbol", "sheets_id"):
            if key in data:
                setattr(config, key, data[key])
        if data.get("categories"):
            config.categories = {str(k): str(v) for k, v in data["categories"].items()}

    if not 1 <= int(config.statement_close_day) <= 31:
        raise ValueError(f"statement_close_day must be 1-31, got {config.statement_close_day}")
    if "Misc" not in config.categories:
        config.categories["Misc"] = "anything that doesn't fit another category"

    config.model = os.environ.get("ANTHROPIC_MODEL") or config.model
    config.sheets_id = os.environ.get("GOOGLE_SHEET_ID") or config.sheets_id
    return config


def _toml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_key(name: str) -> str:
    return name if name.replace("_", "").replace("-", "").isalnum() else _toml_str(name)


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)
