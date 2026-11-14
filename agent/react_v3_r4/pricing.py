"""USD cost accounting for react-v1 runs.

Prices are sourced, not estimated — each entry cites the vendor pricing page it was read from and
the date it was checked, per CLAUDE.md ("never invent numbers... mark every claim as checked").
Re-check before using these numbers in a paper; vendors change prices (Gemini 3.8 Flash's prices
below are already flagged as introductory-until-2027 on the source page).

This module is additive: it only turns existing `usage_metrics` dicts (from SREGym's
`clients/harness/token_usage.py`) into a cost. It does not change what the agent does.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input_per_1m: float
    output_per_1m: float
    source: str
    checked: str
    note: str = ""


# model_id (as passed via AGENT_MODEL_ID / LiteLLM string) -> Price.
# `output_per_1m` already includes reasoning/thinking tokens per the source page, so we do not
# add a separate reasoning-token rate.
PRICES: dict[str, Price] = {
    "gemini-3.5-flash-lite": Price(
        input_per_1m=0.30,
        output_per_1m=2.50,
        source="https://ai.google.dev/gemini-api/docs/pricing",
        checked="2026-10-24",
        note="also free-of-charge tier available; this is the paid-tier rate used for sponsor sizing",
    ),
    "gemini-3.8-flash": Price(
        input_per_1m=0.75,
        output_per_1m=3.75,
        source="https://ai.google.dev/gemini-api/docs/pricing",
        checked="2026-10-24",
        note="introductory price through 2026-12-31; rises to $1.50/$7.50 per 1M on 2027-01-01 — "
        "re-check before quoting in the paper or a sponsor ask made after that date",
    ),
}


def cost_usd(model_id: str, usage: dict) -> float | None:
    """Cost in USD for one `usage_metrics` dict (from token_usage.aggregate_usage), or None if the
    model has no price entry or the usage has no token counts (both are "don't know", not zero)."""
    price = PRICES.get(model_id)
    if price is None:
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None and output_tokens is None:
        return None
    total = 0.0
    if input_tokens is not None:
        total += input_tokens / 1_000_000 * price.input_per_1m
    if output_tokens is not None:
        total += output_tokens / 1_000_000 * price.output_per_1m
    return round(total, 6)


def price_note(model_id: str) -> str | None:
    """One line to attach to a run's metadata so a cost number is never read without its caveat."""
    price = PRICES.get(model_id)
    if price is None:
        return None
    return f"{model_id}: ${price.input_per_1m}/1M in, ${price.output_per_1m}/1M out (checked {price.checked}, {price.source}){' — ' + price.note if price.note else ''}"
