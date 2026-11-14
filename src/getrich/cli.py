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
    if args.cmd == "doctor":
        from .ops import doctor

        for status_, name, detail in doctor.run():
            print(f"[{status_:<4}] {name}: {detail}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
