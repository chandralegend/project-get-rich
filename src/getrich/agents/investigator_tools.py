"""Read-only tools the Investigator can call over OUR OWN data. No writes, no files, no network, bounded output.

The handlers are plain functions so they can be tested without the SDK; build_server() wraps them in an in-process MCP
server (the SDK's @tool and create_sdk_mcp_server) named `market`, so the agent sees mcp__market__get_snapshot etc.
"""

from __future__ import annotations

import json

from ..eval.data import load_bars
from ..store.db import connect
from . import briefing
from .investigator_policy import MARKET_SERVER, RunState

SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
MAX_CHARS = 6000
MAX_DAYS = 120
MAX_HOURS = 72
MAX_EVENTS = 25


def _clip(text: str) -> str:
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n[truncated]"


def _asset(value) -> str:
    if value not in SYMBOLS:
        raise ValueError(f"asset must be one of {sorted(SYMBOLS)}")
    return value


def snapshot_text(asset: str) -> str:
    asset = _asset(asset)
    return _clip(json.dumps(briefing.market_snapshot({asset: SYMBOLS[asset]})[asset], indent=1))


def returns_text(asset: str, days: int = 30) -> str:
    asset = _asset(asset)
    days = max(5, min(int(days), MAX_DAYS))
    close = load_bars(SYMBOLS[asset], "1d")["close"]
    ret = close.pct_change().dropna().iloc[-days:]
    return _clip(json.dumps([[str(d.date()), round(float(r), 4)] for d, r in ret.items()]))


def events_text(state: RunState, hours: int = 24) -> str:
    hours = max(1, min(int(hours), MAX_HOURS))
    with connect() as con:
        events, withheld = briefing.gather_events(con, hours)
    events = events[:MAX_EVENTS]
    state.event_refs.update(e["ref"] for e in events)          # these refs may now be cited as evidence
    return _clip(json.dumps({"events": events, "withheld_as_suspicious": withheld}, indent=1))


def build_server(state: RunState):
    from claude_agent_sdk import ToolAnnotations, create_sdk_mcp_server, tool

    ro = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    asset_schema = {"type": "string", "enum": sorted(SYMBOLS)}

    def wrap(fn):
        def run(args):
            try:
                return {"content": [{"type": "text", "text": fn(args)}]}
            except Exception as exc:                    # a tool failure is information for the agent, not a crash
                return {"content": [{"type": "text", "text": f"tool error: {type(exc).__name__}: {exc}"}], "is_error": True}
        return run

    snap = wrap(lambda a: snapshot_text(a.get("asset")))
    rets = wrap(lambda a: returns_text(a.get("asset"), a.get("days", 30)))
    evts = wrap(lambda a: events_text(state, a.get("hours", 24)))

    @tool("get_snapshot", "Latest closed-bar market snapshot for BTC or ETH: price, returns, volatility, trend votes, drawdown.",
          {"type": "object", "properties": {"asset": asset_schema}, "required": ["asset"]}, annotations=ro)
    async def get_snapshot(args):
        return snap(args)

    @tool("get_returns", "Daily close-to-close returns for BTC or ETH over the last N days (5 to 120).",
          {"type": "object", "properties": {"asset": asset_schema, "days": {"type": "integer", "minimum": 5, "maximum": MAX_DAYS}},
           "required": ["asset"]}, annotations=ro)
    async def get_returns(args):
        return rets(args)

    @tool("get_events", "Recent news events our own pipeline classified (central banks and more). Each has a 'ref' you may cite as evidence.",
          {"type": "object", "properties": {"hours": {"type": "integer", "minimum": 1, "maximum": MAX_HOURS}}}, annotations=ro)
    async def get_events(args):
        return evts(args)

    return create_sdk_mcp_server(name=MARKET_SERVER, version="1.0.0", tools=[get_snapshot, get_returns, get_events])
