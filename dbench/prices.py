"""List prices on the run date, US dollars per million tokens. Check each page on the day and update.

Jev: $0.042 input, output free (OpenRouter and LiteLLM listings, Oct 2026). Image pricing unpublished.
Decisions: $0.10 input, output free (OpenAI Decisions API guide).
Opus 5.5: $4 input, $20 output (thinking billed as output), $0.20 cache read, $5 cache write (5 minute).
"""
PRICES = {
    "jev": {"input": 0.042, "output": 0.0, "cache_read": 0.042, "cache_write": 0.042},
    "decisions": {"input": 0.10, "output": 0.0, "cache_read": 0.10, "cache_write": 0.10},
    "opus": {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0},
}
PRICES_CHECKED = "2026-10-16"


def cost_usd(system: str, input_tokens: int, output_tokens: int = 0, cache_read: int = 0, cache_write: int = 0) -> float:
    p = PRICES[system]
    return (input_tokens * p["input"] + output_tokens * p["output"]
            + cache_read * p["cache_read"] + cache_write * p["cache_write"]) / 1_000_000
