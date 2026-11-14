"""Thin wrapper over the Anthropic SDK: budget check, structured output, validation, logging, typed failures.

Design rules (ARCHITECTURE.md): Claude only produces typed, validated JSON that is stored as data. It has no tools,
no network access of its own, and nothing it returns is ever executed or treated as an instruction. Every call is
logged with its tokens and computed cost so the monthly cap can be enforced from the log.

Request shape follows the Claude API reference: `output_config.format` with a JSON schema, `effort` inside
`output_config`, no `thinking` parameter (the models' default is used), no sampling parameters, no prefill, no forced
tool choice. A `refusal` stop reason is handled, not assumed away.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from ..obs.events import emit
from . import budget, pricing

SERVICE = "llm"


class LLMError(RuntimeError):
    pass


class Refusal(LLMError):
    pass


class ClaudeLLM:
    def __init__(self, sdk: Any = None):
        self._sdk = sdk

    def _client(self):
        if self._sdk is None:
            import anthropic

            self._sdk = anthropic.Anthropic(max_retries=2, timeout=120.0)
        return self._sdk

    @staticmethod
    def estimate_cost(model: str, system: str, user: str, max_tokens: int) -> float:
        """Worst case: about 3 characters per input token, and the whole output allowance used."""
        return pricing.cost_usd(model, int((len(system) + len(user)) / 3) + 50, max_tokens)

    def call_json(self, *, purpose: str, model: str, system: str, user: str, schema: dict,
                  validate: Callable[[Any], list[str]], max_tokens: int = 1200, effort: str = "low",
                  item_id: str | None = None) -> tuple[dict, dict]:
        """Returns (validated data, call info). Raises BudgetExceeded, Refusal or LLMError."""
        est = self.estimate_cost(model, system, user, max_tokens)
        budget.check(est)                                   # refuses BEFORE any network call
        sdk = self._client()
        started = time.monotonic()
        try:
            resp = sdk.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}, "effort": effort},
            )
        except Exception as exc:
            emit("llm.error", service=SERVICE, level="error", item_id=item_id, purpose=purpose, model=model,
                 error=f"{type(exc).__name__}: {str(exc)[:300]}")
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        usage = getattr(resp, "usage", None)
        tin, tout = int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)
        info = {"purpose": purpose, "model": model, "tokens_in": tin, "tokens_out": tout,
                "cost_usd": pricing.cost_usd(model, tin, tout), "latency_s": round(time.monotonic() - started, 2),
                "stop_reason": getattr(resp, "stop_reason", None), "request_id": getattr(resp, "_request_id", None)}

        def log(schema_ok: bool, note: str = "") -> None:
            emit("llm.call", service=SERVICE, item_id=item_id, schema_ok=schema_ok, note=note, **info)

        if info["stop_reason"] == "refusal":
            log(False, "refusal")
            raise Refusal("the model declined this request")
        if info["stop_reason"] == "max_tokens":
            log(False, "max_tokens")
            raise LLMError("output was cut off at max_tokens")
        text = next((b.text for b in getattr(resp, "content", []) if getattr(b, "type", None) == "text"), None)
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            log(False, "not json")
            raise LLMError("response was not valid JSON") from None
        errors = validate(data)
        if errors:
            log(False, "; ".join(errors)[:300])
            raise LLMError("response failed validation: " + "; ".join(errors)[:300])
        log(True)
        return data, info
