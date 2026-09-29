"""AI-powered transaction categorization using Claude."""

import os

import anthropic

from .config import DEFAULT_CATEGORIES
from .ledger import redact
from .llm import request_json

CATEGORIES = list(DEFAULT_CATEGORIES)

BATCH_SIZE = 25


def category_schema(names: list[str]) -> dict:
    """Structured-output schema: a clean name and one category (from `names`) per transaction."""
    return {
        "type": "object",
        "properties": {
            "merchants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {"type": "string", "enum": names},
                    },
                    "required": ["name", "category"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["merchants"],
        "additionalProperties": False,
    }


NAMES_SCHEMA = {
    "type": "object",
    "properties": {"names": {"type": "array", "items": {"type": "string"}}},
    "required": ["names"],
    "additionalProperties": False,
}

NAMING_GUIDE = """A clean merchant name is what a person would call the business:
- Keep the brand's own spelling and capitals: "easyJetKBQTWC2 Luton" -> "easyJet", "WHOLEFDS SYM 10031" -> "Whole Foods".
- Drop processors, store numbers, codes, towns and web addresses: "PL*StateFinancia DES:WEB PMTS" -> "State Financial",
  "AMAZON PRIME*5B34562Q3 Amzn.com/bill" -> "Amazon Prime", "UBER *TRIP HELP.UBER.COM" -> "Uber".
- Name what it is when there's no brand: "WIRE TYPE:INTL IN" -> "International wire", "Shop 2/ Lounge 2 Schiphol Airp" -> "Schiphol Airport Lounge".
- Never invent a business that isn't in the text; if it's unclear, just tidy the text. At most 4 words."""


CATEGORY_SCHEMA = category_schema(CATEGORIES)


def categorize_transactions(
    transactions: list[dict],
    api_key: str | None = None,
    categories: dict[str, str] | None = None,
    model: str | None = None,
) -> list[dict]:
    """
    Categorize transactions using Claude AI.

    Args:
        transactions: List of transaction dicts with 'description' and 'amount'
        api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        categories: Category name -> hint (defaults to the built-in list)
        model: Claude model id (defaults to ANTHROPIC_MODEL or the built-in default)

    Returns:
        Transactions with an added 'category' field
    """
    if not transactions:
        return []

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found. Set it as an environment variable or pass it directly."
        )

    client = anthropic.Anthropic(api_key=api_key)
    categorized = []

    # Process in batches to reduce API calls
    for i in range(0, len(transactions), BATCH_SIZE):
        batch = transactions[i : i + BATCH_SIZE]
        results = _categorize_batch(client, batch, categories, model, with_names=True)

        for txn, (category, name) in zip(batch, results, strict=True):
            categorized.append({**txn, "category": category, "merchant_name": name})

    return categorized


def _categorize_batch(
    client: anthropic.Anthropic,
    transactions: list[dict],
    categories: dict[str, str] | None = None,
    model: str | None = None,
    with_names: bool = False,
) -> list:
    """
    Categorize a batch of transactions with a single API call.

    Returns one category per transaction, or (category, clean name or None) pairs
    when `with_names` is set.
    """
    categories = categories or DEFAULT_CATEGORIES
    names = list(categories)

    txn_list = "\n".join(
        f"{i + 1}. {redact(txn['description'])} (${abs(txn['amount']):.2f})"
        for i, txn in enumerate(transactions)
    )
    guidance = "\n".join(f"- {name}: {hint}" if hint else f"- {name}" for name, hint in categories.items())

    prompt = f"""For each personal-finance transaction, give a clean merchant name and exactly one category.

Categories:
{guidance}

{NAMING_GUIDE}

Transactions:
{txn_list}

Return one entry per transaction, in the same order."""

    fallback = "Misc" if "Misc" in names else names[-1]

    def finish(pairs: list) -> list:
        # Exactly one entry per transaction
        pairs = pairs[: len(transactions)] + [(fallback, None)] * (len(transactions) - len(pairs))
        return pairs if with_names else [cat for cat, _ in pairs]

    try:
        data = request_json(client, prompt, category_schema(names), max_tokens=4096, model=model)
    except ValueError as e:
        # Unparseable or truncated reply: keep going rather than lose the batch
        print(f"  Warning: categorization failed for {len(transactions)} transactions ({e})")
        return finish([])

    if isinstance(data, dict) and isinstance(data.get("merchants"), list):
        raw = [
            (m.get("category"), m.get("name")) if isinstance(m, dict) else (m, None)
            for m in data["merchants"]
        ]
    else:
        # Older reply shapes: {"categories": [...]} or a bare list
        results = data.get("categories") if isinstance(data, dict) else data
        if not isinstance(results, list):
            return finish([])
        raw = [(cat, None) for cat in results]

    # Normalize anything outside the category list (e.g. if schemas are unsupported)
    pairs = [
        (cat if cat in names else _find_closest_category(str(cat), names), (name or "").strip()[:60] or None)
        for cat, name in raw
    ]
    return finish(pairs)


def suggest_names(
    descriptions: list[str],
    api_key: str | None = None,
    model: str | None = None,
    batch_size: int = 40,
) -> list[str | None]:
    """Ask Claude for a clean display name for each raw description (None where it can't say)."""
    if not descriptions:
        return []
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found. Set it as an environment variable or pass it directly."
        )
    client = anthropic.Anthropic(api_key=api_key)

    out: list[str | None] = []
    for i in range(0, len(descriptions), batch_size):
        batch = descriptions[i : i + batch_size]
        listing = "\n".join(f"{n + 1}. {redact(d)}" for n, d in enumerate(batch))
        prompt = f"""Give a clean merchant name for each bank transaction description.

{NAMING_GUIDE}

Descriptions:
{listing}

Return one name per description, in the same order."""
        try:
            data = request_json(client, prompt, NAMES_SCHEMA, max_tokens=4096, model=model)
            names = data.get("names", []) if isinstance(data, dict) else []
        except ValueError as e:
            print(f"  Warning: naming failed for {len(batch)} merchants ({e})")
            names = []
        names = [(str(n).strip()[:60] or None) if n else None for n in names[: len(batch)]]
        out += names + [None] * (len(batch) - len(names))
    return out


def _find_closest_category(category: str, names: list[str] | None = None) -> str:
    """Find the closest matching category name, or Misc."""
    names = names or CATEGORIES
    category_lower = category.lower()
    for cat in names:
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
            summary["by_category"][category] = {"total": 0.0, "count": 0, "transactions": []}

        summary["by_category"][category]["total"] += amount
        summary["by_category"][category]["count"] += 1
        summary["by_category"][category]["transactions"].append(
            {"date": txn.get("date"), "description": txn.get("description"), "amount": amount}
        )

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
