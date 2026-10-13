"""Deterministic usage and cost accounting helpers."""

from __future__ import annotations

from dataclasses import dataclass


MODEL_RATES_USD_PER_MILLION = {
    "claude-opus-5-5": {"input": 15.0, "output": 75.0},
    "gpt-4o-transcribe": {"input": 0.0, "output": 0.0},
}


@dataclass(frozen=True)
class Usage:
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    units: float = 0.0
    cost_estimate: float = 0.0


def estimate_cost(provider: str, model: str, tokens_in: int = 0, tokens_out: int = 0, units: float = 0.0) -> Usage:
    rate = MODEL_RATES_USD_PER_MILLION.get(model, {"input": 0.0, "output": 0.0})
    cost = tokens_in / 1_000_000 * rate["input"] + tokens_out / 1_000_000 * rate["output"]
    return Usage(provider, model, tokens_in, tokens_out, units, round(cost, 8))
