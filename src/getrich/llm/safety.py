"""Untrusted-text handling. Everything fetched from the web is hostile input.

The real defences are structural: the model is only asked to fill a fixed schema, enums constrain every field that
matters, free text is length-limited and stored as data, and nothing downstream ever executes or follows it. This
module adds the cheap layers on top: cleaning the text, and flagging the obvious injection patterns so they show up
in the log and in the stored insight.
"""

from __future__ import annotations

import re

MAX_ITEM_CHARS = 6000
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_WS = re.compile(r"[ \t\r\f\v]+")
_FENCE = re.compile(r"(<<<+|>>>+|```+)")

INJECTION_PATTERNS = {
    "ignore_instructions": re.compile(r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)", re.I),
    "disregard_instructions": re.compile(r"disregard\s+.{0,40}(instructions?|rules?|system)", re.I),
    "role_tags": re.compile(r"</?\s*(system|assistant|developer)\s*>", re.I),
    "new_instructions": re.compile(r"(new|updated)\s+instructions?\s*:", re.I),
    "you_are_now": re.compile(r"\byou\s+are\s+now\b", re.I),
    "reveal_secrets": re.compile(r"(reveal|print|show|send|output)\s+.{0,30}(api[\s_-]?key|secret|password|system\s+prompt|credentials)", re.I),
    "trade_command": re.compile(r"\b(buy|sell|place|execute|submit)\s+(an?\s+)?(order|trade)\b.{0,40}\b(now|immediately)\b", re.I),
}


def sanitize(text: str, limit: int = MAX_ITEM_CHARS) -> str:
    text = _CTRL.sub(" ", text or "")
    text = _FENCE.sub(" ", text)          # our own delimiters cannot be forged from inside the item
    text = _WS.sub(" ", text).strip()
    return text[:limit]


def injection_flags(text: str) -> list[str]:
    return [name for name, pat in INJECTION_PATTERNS.items() if pat.search(text or "")]
