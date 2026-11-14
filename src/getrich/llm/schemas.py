"""JSON schemas for the structured outputs, and the validators that re-check them locally.

The API's structured outputs already constrain the response, but model output is still untrusted data, so every
field is validated again here before anything is stored. Numeric ranges and string lengths are checked here rather
than in the schema because those keywords are not relied on server-side.
"""

from __future__ import annotations

ASSETS = ["BTC", "ETH", "CRYPTO_MARKET", "GOLD", "SILVER", "USD", "EUR", "JPY", "GBP", "US_EQUITIES", "RATES", "NONE"]
EVENT_TYPES = ["rate_decision", "inflation_data", "employment_data", "central_bank_speech", "regulation",
               "exchange_listing_delisting", "security_incident", "stablecoin_stress", "etf_flows", "macro_other",
               "geopolitical", "other"]
DIRECTIONS = ["risk_on", "risk_off", "neutral", "unclear"]
HORIZONS = ["intraday", "1-5d", "1-4w", "longer"]
LEVELS = ["low", "medium", "high"]
SUMMARY_MAX = 240

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "assets": {"type": "array", "items": {"type": "string", "enum": ASSETS}},
        "event_type": {"type": "string", "enum": EVENT_TYPES},
        "direction": {"type": "string", "enum": DIRECTIONS},
        "horizon": {"type": "string", "enum": HORIZONS},
        "magnitude": {"type": "string", "enum": LEVELS},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
        "injection_flag": {"type": "boolean"},
    },
    "required": ["relevant", "assets", "event_type", "direction", "horizon", "magnitude", "confidence", "summary", "injection_flag"],
    "additionalProperties": False,
}

FLAGS = ["event_risk", "volatility_spike", "liquidity", "regulatory", "security_incident", "stablecoin_depeg", "macro_event", "other"]
REGIMES = ["calm", "trending_up", "trending_down", "choppy", "stressed", "unclear"]
VIEW_ASSETS = ["BTC", "ETH"]
VIEW_DIRECTIONS = ["up", "down", "flat"]
VIEW_HORIZONS = [1, 3, 7, 14]
BRIEF_TEXT_MAX = 1600

BRIEFING_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "regime": {"type": "string", "enum": REGIMES},
        "risk_flags": {"type": "array", "items": {"type": "object", "properties": {
            "asset": {"type": "string", "enum": ["BTC", "ETH", "CRYPTO_MARKET", "GOLD", "USD"]},
            "flag": {"type": "string", "enum": FLAGS},
            "severity": {"type": "string", "enum": LEVELS},
            "reason": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        }, "required": ["asset", "flag", "severity", "reason", "evidence"], "additionalProperties": False}},
        "views": {"type": "array", "items": {"type": "object", "properties": {
            "asset": {"type": "string", "enum": VIEW_ASSETS},
            "direction": {"type": "string", "enum": VIEW_DIRECTIONS},
            "horizon_days": {"type": "integer", "enum": VIEW_HORIZONS},
            "confidence": {"type": "number"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        }, "required": ["asset", "direction", "horizon_days", "confidence", "evidence"], "additionalProperties": False}},
        "watch_next": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "summary", "regime", "risk_flags", "views", "watch_next"],
    "additionalProperties": False,
}


def _unit(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and 0.0 <= float(x) <= 1.0


def validate_extraction(d) -> list[str]:
    if not isinstance(d, dict):
        return ["not an object"]
    errs = []
    for key in EXTRACTION_SCHEMA["required"]:
        if key not in d:
            errs.append(f"missing {key}")
    if errs:
        return errs
    if not isinstance(d["relevant"], bool) or not isinstance(d["injection_flag"], bool):
        errs.append("booleans must be booleans")
    if not isinstance(d["assets"], list) or not d["assets"] or any(a not in ASSETS for a in d["assets"]):
        errs.append("assets must be a non-empty list of known assets")
    for key, allowed in (("event_type", EVENT_TYPES), ("direction", DIRECTIONS), ("horizon", HORIZONS), ("magnitude", LEVELS)):
        if d[key] not in allowed:
            errs.append(f"{key} not allowed: {d[key]!r}")
    if not _unit(d["confidence"]):
        errs.append("confidence must be within 0 to 1")
    if not isinstance(d["summary"], str) or len(d["summary"]) > SUMMARY_MAX:
        errs.append(f"summary must be text of at most {SUMMARY_MAX} characters")
    return errs


def validate_briefing(d, allowed_evidence: set[str]) -> list[str]:
    if not isinstance(d, dict):
        return ["not an object"]
    errs = [f"missing {k}" for k in BRIEFING_SCHEMA["required"] if k not in d]
    if errs:
        return errs
    for key in ("headline", "summary"):
        if not isinstance(d[key], str) or not d[key].strip() or len(d[key]) > BRIEF_TEXT_MAX:
            errs.append(f"{key} must be non-empty text of at most {BRIEF_TEXT_MAX} characters")
    if d["regime"] not in REGIMES:
        errs.append("regime not allowed")
    for i, f in enumerate(d["risk_flags"] if isinstance(d["risk_flags"], list) else []):
        if f.get("flag") not in FLAGS or f.get("severity") not in LEVELS or f.get("asset") not in ("BTC", "ETH", "CRYPTO_MARKET", "GOLD", "USD"):
            errs.append(f"risk_flags[{i}] has a value that is not allowed")
        if not isinstance(f.get("reason"), str) or len(f["reason"]) > SUMMARY_MAX:
            errs.append(f"risk_flags[{i}].reason too long")
        if not f.get("evidence"):
            errs.append(f"risk_flags[{i}] cites no evidence")
        errs += [f"risk_flags[{i}] cites unknown evidence {e!r}" for e in f.get("evidence", []) if e not in allowed_evidence]
    for i, v in enumerate(d["views"] if isinstance(d["views"], list) else []):
        if v.get("asset") not in VIEW_ASSETS or v.get("direction") not in VIEW_DIRECTIONS or v.get("horizon_days") not in VIEW_HORIZONS:
            errs.append(f"views[{i}] has a value that is not allowed")
        if not _unit(v.get("confidence")):
            errs.append(f"views[{i}].confidence must be within 0 to 1")
        if not v.get("evidence"):
            errs.append(f"views[{i}] cites no evidence")
        errs += [f"views[{i}] cites unknown evidence {e!r}" for e in v.get("evidence", []) if e not in allowed_evidence]
    if not isinstance(d["watch_next"], list) or any(not isinstance(w, str) or len(w) > SUMMARY_MAX for w in d["watch_next"]):
        errs.append("watch_next must be a list of short text")
    return errs


INVESTIGATION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "claim": {"type": "string"},
            "asset": {"type": "string", "enum": ["BTC", "ETH", "CRYPTO_MARKET", "GOLD", "USD", "RATES"]},
            "direction": {"type": "string", "enum": DIRECTIONS},
            "confidence": {"type": "number"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        }, "required": ["claim", "asset", "direction", "confidence", "evidence"]}},
        "risk_flags": {"type": "array", "items": {"type": "object", "properties": {
            "asset": {"type": "string", "enum": ["BTC", "ETH", "CRYPTO_MARKET", "GOLD", "USD"]},
            "flag": {"type": "string", "enum": FLAGS},
            "severity": {"type": "string", "enum": LEVELS},
            "reason": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        }, "required": ["asset", "flag", "severity", "reason", "evidence"]}},
        "views": {"type": "array", "items": {"type": "object", "properties": {
            "asset": {"type": "string", "enum": VIEW_ASSETS},
            "direction": {"type": "string", "enum": VIEW_DIRECTIONS},
            "horizon_days": {"type": "integer", "enum": VIEW_HORIZONS},
            "confidence": {"type": "number"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        }, "required": ["asset", "direction", "horizon_days", "confidence", "evidence"]}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "findings", "risk_flags", "views", "open_questions"],
}


def validate_investigation(d, allowed_evidence: set[str]) -> list[str]:
    """Evidence entries must be pages the agent actually fetched or refs a market tool returned. Anything else is rejected."""
    if not isinstance(d, dict):
        return ["not an object"]
    errs = [f"missing {k}" for k in INVESTIGATION_SCHEMA["required"] if k not in d]
    if errs:
        return errs
    if not isinstance(d["summary"], str) or not d["summary"].strip() or len(d["summary"]) > BRIEF_TEXT_MAX:
        errs.append("summary must be non-empty text within the length limit")

    def check_evidence(label, item):
        ev = item.get("evidence")
        if not isinstance(ev, list) or not ev:
            errs.append(f"{label} cites no evidence")
            return
        errs.extend(f"{label} cites {e!r}, which was not fetched or returned by a tool" for e in ev if e not in allowed_evidence)

    for i, f in enumerate(d["findings"] if isinstance(d["findings"], list) else []):
        if f.get("asset") not in ("BTC", "ETH", "CRYPTO_MARKET", "GOLD", "USD", "RATES") or f.get("direction") not in DIRECTIONS:
            errs.append(f"findings[{i}] has a value that is not allowed")
        if not isinstance(f.get("claim"), str) or not f["claim"].strip() or len(f["claim"]) > 400:
            errs.append(f"findings[{i}].claim must be short text")
        if not _unit(f.get("confidence")):
            errs.append(f"findings[{i}].confidence must be within 0 to 1")
        check_evidence(f"findings[{i}]", f)
    for i, f in enumerate(d["risk_flags"] if isinstance(d["risk_flags"], list) else []):
        if f.get("flag") not in FLAGS or f.get("severity") not in LEVELS or f.get("asset") not in ("BTC", "ETH", "CRYPTO_MARKET", "GOLD", "USD"):
            errs.append(f"risk_flags[{i}] has a value that is not allowed")
        if not isinstance(f.get("reason"), str) or len(f["reason"]) > SUMMARY_MAX:
            errs.append(f"risk_flags[{i}].reason too long")
        check_evidence(f"risk_flags[{i}]", f)
    for i, v in enumerate(d["views"] if isinstance(d["views"], list) else []):
        if v.get("asset") not in VIEW_ASSETS or v.get("direction") not in VIEW_DIRECTIONS or v.get("horizon_days") not in VIEW_HORIZONS:
            errs.append(f"views[{i}] has a value that is not allowed")
        if not _unit(v.get("confidence")):
            errs.append(f"views[{i}].confidence must be within 0 to 1")
        check_evidence(f"views[{i}]", v)
    if not isinstance(d["open_questions"], list) or any(not isinstance(q, str) or len(q) > SUMMARY_MAX for q in d["open_questions"]):
        errs.append("open_questions must be a list of short text")
    return errs
