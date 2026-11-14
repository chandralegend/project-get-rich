"""Command line entry point: `getrich <command>`."""

from __future__ import annotations

import argparse
import sys

from . import config


def main(argv: list[str] | None = None) -> int:
    config.load_env()
    p = argparse.ArgumentParser(prog="getrich", description="Local-first research and trading system")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("collect-binance", help="fetch closed Binance klines (public REST, no key)")
    b.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    b.add_argument("--timeframe", default="1d")
    b.add_argument("--start", default="2020-01-01", help="first date to fetch when a symbol has no data yet")
    sub.add_parser("collect-news", help="fetch central-bank RSS feeds into the store")
    sub.add_parser("watchdog", help="run all health checks once, raise or clear alerts")
    sub.add_parser("status", help="show the status screen")
    sub.add_parser("ingest-events", help="load the JSONL event log into DuckDB")
    sub.add_parser("doctor", help="check this Mac against the hardening list")
    g = sub.add_parser("gate", help="evaluate the Phase 0 exit gate from the event log")
    g.add_argument("--since", help="ISO time the unattended week started (default: when the launchd jobs were installed)")
    a = sub.add_parser("ack", help="record that you confirmed something only you can check")
    a.add_argument("item")
    a.add_argument("--note", default="")
    sub.add_parser("ledger-verify", help="verify the insight ledger's hash chain")
    args = p.parse_args(argv)

    if args.cmd == "collect-binance":
        from .collectors import binance

        ok, summary = binance.collect(args.symbols, args.timeframe, args.start)
        print(("OK " if ok else "FAILED ") + str(summary))
        return 0 if ok else 1
    if args.cmd == "collect-news":
        from .collectors import news

        ok, summary = news.collect()
        print(("OK " if ok else "PARTIAL/FAILED ") + str(summary))
        return 0 if ok else 1
    if args.cmd == "watchdog":
        from .ops import watchdog

        alerts = watchdog.run()
        for a in alerts:
            print(f"{a.severity} {a.key}: {a.message} -> {a.action}")
        return 0
    if args.cmd == "status":
        from .obs import status

        status.render()
        return 0
    if args.cmd == "ingest-events":
        from .obs.ingest import ingest_events
        from .store.db import connect

        with connect() as con:
            print(f"added {ingest_events(con)} events")
        return 0
    if args.cmd == "gate":
        from datetime import datetime, timezone

        from .obs.events import utcnow
        from .obs.ingest import ingest_events
        from .ops import gate
        from .store.db import connect

        since = datetime.fromisoformat(args.since).astimezone(timezone.utc) if args.since else gate.DEFAULT_SINCE
        with connect() as con:
            ingest_events(con)
            results = gate.evaluate(con, since, utcnow())
        colour = {"PASS": "\033[32m", "FAIL": "\033[31m", "PENDING": "\033[33m", "MANUAL": "\033[36m", "WARN": "\033[33m"}
        for r in results:
            print(f"{colour.get(r.status, '')}{r.status:<8}\033[0m {r.name}: {r.detail}")
        verdict = gate.overall(results)
        print(f"\nPHASE 0 GATE: {verdict}")
        return 0 if verdict != "FAIL" else 1
    if args.cmd == "ack":
        from .ops import gate

        try:
            gate.record_ack(args.item, args.note)
        except ValueError as exc:
            print(exc)
            return 2
        print(f"recorded: {gate.ACK_ITEMS[args.item]}")
        return 0
    if args.cmd == "ledger-verify":
        from .store.db import connect
        from .store.ledger import verify_chain

        with connect() as con:
            ok, n, bad = verify_chain(con)
        print(f"{n} insights, chain intact" if ok else f"CHAIN BROKEN at seq {bad} ({n} rows checked)")
        return 0 if ok else 1
    if args.cmd == "doctor":
        from .ops import doctor

        for status_, name, detail in doctor.run():
            print(f"[{status_:<4}] {name}: {detail}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
