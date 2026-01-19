"""AI-powered transaction categorization using Claude."""

import json
import os
from typing import Optional

import anthropic

# Categories matching Google Sheet columns
CATEGORIES = [
    "Housing",
    "Gas (Home)",
    "Electric",
    "Internet",
    "Insurance",
    "Groceries",
    "Eating Out",
    "Phone",
    "Rideshare",
    "Public Transit",
    "Entertainment",
    "Clothing",
    "Self Care",
    "Dry Cleaning",
    "Gym",
    "Music",
    "Education",
    "Medical",
    "Gifts",
    "Apple",         # Apple services: iCloud, Apple Music, App Store, Apple One
    "Fees",
    "Travel",        # Flights, hotels, travel bookings
    "Subscriptions", # Non-Apple software subscriptions
    "Misc",
]

BATCH_SIZE = 25


def categorize_transactions(transactions: list[dict], api_key: Optional[str] = None) -> list[dict]:
    """
    Categorize transactions using Claude AI.

    Args:
        transactions: List of transaction dicts with 'date', 'description', 'amount'
        api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)

    Returns:
        Transactions with added 'category' field
    """
    if not transactions:
        return []

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found. Set it as an environment variable or pass it directly.")

    client = anthropic.Anthropic(api_key=api_key)
    categorized = []

    # Process in batches to reduce API calls
    for i in range(0, len(transactions), BATCH_SIZE):
        batch = transactions[i:i + BATCH_SIZE]
        categories = _categorize_batch(client, batch)

        for txn, category in zip(batch, categories):
            categorized.append({**txn, "category": category})

    return categorized


def _categorize_batch(client: anthropic.Anthropic, transactions: list[dict]) -> list[str]:
    """Categorize a batch of transactions with a single API call."""

    # Build the transaction list for the prompt
    txn_list = "\n".join(
        f"{i+1}. {txn['description']} (${abs(txn['amount']):.2f})"
        for i, txn in enumerate(transactions)
    )

    prompt = f"""Categorize each transaction into exactly one of these categories:
{', '.join(CATEGORIES)}

Category guidance:
- Housing: rent, mortgage, loan payments (State Financial, student loans), property-related
- Eating Out: restaurants, cafes, food delivery (Deliveroo, UberEats), bars
- Groceries: supermarkets, grocery stores (Tesco, Whole Foods, etc.)
- Rideshare: Uber, Lyft, taxis
- Public Transit: buses, trains, metro, TFL
- Phone: mobile phone bills (Verizon, AT&T, etc.)
- Internet: home internet service
- Music: Spotify subscription only
- Entertainment: movies, games, museums, theme parks, Netflix streaming
- Clothing: apparel, shoes, fashion stores (JD Sports, MUJI, etc.)
- Self Care: beauty, haircuts, spa
- Education: courses, books (Waterstones), tutorials
- Medical: healthcare, pharmacy, doctors
- Travel: flights (Ryanair, EasyJet), hotels, Airbnb, Trip.com, airport lounges, travel eSIM (Airalo)
- Apple: ALL Apple charges - iCloud, Apple Music, Apple One, App Store purchases, apple.com
- Subscriptions: non-Apple software/service subscriptions (Claude AI, MongoDB, Amazon Prime, Displate, ChatGPT, Patreon)
- Misc: anything that doesn't fit other categories

Transactions:
{txn_list}

Respond with ONLY a JSON array of category strings, one per transaction, in the same order.
Example response: ["Eating Out", "Rideshare", "Groceries"]

JSON array:"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse the response
    response_text = response.content[0].text.strip()

    try:
        categories = json.loads(response_text)
        if not isinstance(categories, list):
            raise ValueError("Response is not a list")

        # Validate and normalize categories
        validated = []
        for cat in categories:
            if cat in CATEGORIES:
                validated.append(cat)
            else:
                # Find closest match or default to Misc
                validated.append(_find_closest_category(cat))

        # Ensure we have the right number of categories
        while len(validated) < len(transactions):
            validated.append("Misc")

        return validated[:len(transactions)]

    except (json.JSONDecodeError, ValueError):
        # If parsing fails, return all as "Misc"
        return ["Misc"] * len(transactions)


def _find_closest_category(category: str) -> str:
    """Find the closest matching category."""
    category_lower = category.lower()
    for cat in CATEGORIES:
        if cat.lower() in category_lower or category_lower in cat.lower():
            return cat
    return "Misc"


def get_summary(transactions: list[dict]) -> dict:
    """
    Generate a spending summary by category.

    Args:
        transactions: List of categorized transaction dicts

    Returns:
        Dictionary with category totals and overall stats
    """
    summary = {
        "by_category": {},
        "total_spending": 0.0,
        "total_income": 0.0,
        "transaction_count": len(transactions),
    }

    for txn in transactions:
        category = txn.get("category", "Misc")
        amount = txn.get("amount", 0)

        if category not in summary["by_category"]:
            summary["by_category"][category] = {
                "total": 0.0,
                "count": 0,
                "transactions": []
            }

        summary["by_category"][category]["total"] += amount
        summary["by_category"][category]["count"] += 1
        summary["by_category"][category]["transactions"].append({
            "date": txn.get("date"),
            "description": txn.get("description"),
            "amount": amount
        })

        if amount < 0:
            summary["total_spending"] += abs(amount)
        else:
            summary["total_income"] += amount

    # Round totals
    summary["total_spending"] = round(summary["total_spending"], 2)
    summary["total_income"] = round(summary["total_income"], 2)
    for cat in summary["by_category"]:
        summary["by_category"][cat]["total"] = round(summary["by_category"][cat]["total"], 2)

    return summary
