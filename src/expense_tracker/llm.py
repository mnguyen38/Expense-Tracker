"""Shared Claude client helpers: model selection and schema-constrained JSON calls."""

import json
import os

import anthropic

# Overridden by `model` in config.toml or ANTHROPIC_MODEL.
DEFAULT_MODEL = "claude-sonnet-5"


def get_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL


def request_json(
    client: anthropic.Anthropic,
    prompt: str,
    schema: dict,
    max_tokens: int,
    model: str | None = None,
) -> dict | list:
    """
    Call Claude with structured outputs so the reply is constrained to `schema`.

    Raises:
        ValueError: if the reply was cut off, refused, or is not valid JSON.
    """
    response = client.messages.create(
        model=model or get_model(),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )

    if response.stop_reason == "max_tokens":
        raise ValueError(
            f"AI response was truncated at {max_tokens} tokens; "
            "the statement may have too many transactions for one request."
        )
    if response.stop_reason == "refusal":
        raise ValueError("The model declined to process this request.")

    text = next((b.text for b in response.content if isinstance(getattr(b, "text", None), str)), "").strip()

    # Tolerate a markdown fence in case structured outputs are unavailable (e.g. a proxy)
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse AI response as JSON: {e}") from e
