"""Token prices in US dollars per million tokens, used to compute and CAP spend.

Source: the Claude API reference cached 2026-10-06 (Haiku 5.5 at $0.10 / $0.50 for prompts up to 100K tokens and
$0.50 / $2.50 beyond; Sonnet 5.5 at $2 / $10). Prices change: re-check the pricing page before relying on the cap
for real money. Unknown models fail closed (KeyError) rather than being priced at zero. Prompt-cache discounts are
ignored, so the computed cost is an upper bound.
"""

from __future__ import annotations

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"

# model: (input, output, long_input, long_output, long_prompt_threshold_tokens)
PRICES: dict[str, tuple[float, float, float, float, int]] = {
    HAIKU: (0.10, 0.50, 0.50, 2.50, 100_000),
    SONNET: (2.00, 10.00, 2.00, 10.00, 10**12),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out, long_in, long_out, threshold = PRICES[model]
    if input_tokens > threshold:
        price_in, price_out = long_in, long_out
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
