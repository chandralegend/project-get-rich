"""Command line entry point: `getrich <command>`."""

from __future__ import annotations

import argparse
import json
import sys

from . import config


def _fmt_verdict(v: dict) -> str:
    lines = [("APPROVED" if v["approved"] else "REJECTED") + f": qty {v['qty']:g}  notional ~{v['notional']:.2f}  risk {v['risk_amount']:.2f} ({v['risk_fraction']:.2%} of equity)"]
    lines += [f"  ok   {c['check']}" + (f": {c['detail']}" if c["check"] == "sizing" else "") if c["ok"] else f"  FAIL {c['check']}: {c['detail']}" for c in v["checks"]]
    lines += [f"  note: {r}" for r in v["reasons"] if not any(r.startswith(c["check"] + ":") for c in v["checks"] if not c["ok"])]
    return "\n".join(lines)


def _forecast_command(args) -> int:
    from .forecast import fetch, models, report

    if args.cmd == "forecast-fetch":
        entry = fetch.fetch_weights(args.model)
        for repo, info in entry["repos"].items():
            print(repo, info["revision"][:12], f"{sum(f['size'] for f in info['files']) / 1e6:.1f} MB", [f["name"] for f in info["files"]])
        return 0
    if args.cmd == "forecast-fetch-code":
        info = fetch.fetch_code()
        print(f"cloned {info['repo']} at {info['commit'][:12]}; {len(info['python_files'])} python files to review before running:")
        print("\n".join("  " + p for p in info["python_files"]))
        return 0
    if args.cmd == "forecast-eval":
        out = report.run_all()
        text = report.to_markdown(out)
        print(text)
        if args.write:
            (config.root() / "docs" / "forecast-eval.md").write_text(text)
            print("wrote docs/forecast-eval.md")
        return 0
    # forecast-run
    import pandas as pd

    from .eval.data import load_bars
    from .forecast import generate

    problems = fetch.verify(args.model)
    if args.model.startswith("kronos"):
        problems += fetch.verify_code()
    if problems:
        print("\n".join(problems))
        return 2
    fc = models.get(args.model)
    since = pd.Timestamp(args.since, tz="UTC") if args.since else None
    for sym in ("BTCUSDT", "ETHUSDT"):
        c = generate.generate(fc, sym, load_bars(sym, "1d"), stride=args.stride, since=since, max_new=args.max_new,
                              progress=lambda done, total, s=sym: print(f"  {s}: {done}/{total}", flush=True))
        print(f"{args.model} {sym}: {len(c)} forecasts cached")
    return 0


def _trading_command(args) -> int:
    from .trading import book, limits as tl, service, venues
    from .trading.types import OrderIntent

    def broker():
        try:
            return venues.get_broker(args.venue)
        except RuntimeError as exc:                         # e.g. testnet keys not set
            print(exc)
            raise SystemExit(2)

    if args.cmd == "limits-pin":
        print("pinned", tl.pin()[:12])
        return 0
    if args.cmd == "propose":
        intent = OrderIntent(args.symbol.upper(), args.side, args.stop, args.take_profit, args.qty, args.risk, source="manual", reason=args.reason)
        order_id, v = service.propose(intent, broker=broker())
        print(f"proposal {order_id} ({args.venue})\n{_fmt_verdict(v)}")
        if v["approved"]:
            print(f"\nTo place it (valid 15 minutes):  getrich approve {order_id}\nTo drop it:                      getrich reject {order_id}")
        return 0 if v["approved"] else 1
    if args.cmd == "approve":
        o = book.get_order(args.order_id)
        if o is None:
            print("no such order")
            return 2
        print(f"{o['side'].upper()} {o['qty']:g} {o['symbol']} ({o['venue']})  stop {o['stop_price']}  take profit {o['take_profit']}  status {o['status']}\nreason: {o['reason'] or '-'}")
        if not args.yes:
            if not sys.stdin.isatty():
                print("refusing: approval needs an interactive terminal (or --yes in your own script)")
                return 2
            if input("type 'yes' to approve: ").strip().lower() != "yes":
                print("not approved")
                return 1
        res = service.approve(args.order_id, broker=broker())
        print(res["note"], f"| equity now {res['equity']:.2f}" if res.get("ok") else "")
        return 0 if res["ok"] else 1
    if args.cmd == "reject":
        print(service.reject(args.order_id, args.reason)["note"])
        return 0
    if args.cmd == "orders":
        for o in book.list_orders(args.limit, args.venue):
            print(f"{o['order_id']}  {o['created_at']:%m-%d %H:%M}  {o['venue']:6} {o['side']:4} {o['symbol']:8} qty {o['qty'] or 0:<10g} {o['status']:17} {o['detail'] or ''}")
        return 0
    if args.cmd == "paper-tick":
        print(service.tick(broker=broker()) or "no stops or take profits triggered")
        return 0
    if args.cmd == "kill":
        print(service.kill(broker=broker()))
        return 0
    if args.cmd == "unkill":
        print("kill switch cleared" if service.unkill() else "kill switch was not on")
        return 0
    if args.cmd == "unhalt":
        print("drawdown halt cleared" if service.unhalt() else "no drawdown halt was latched")
        return 0
    # positions
    st = service._state(broker(), ["BTCUSDT", "ETHUSDT"], book.utcnow())
    r = book.realized_summary(args.venue)
    lim, why = tl.load()
    print(f"{args.venue} equity {st.equity:.2f} (start {book.start_equity():.2f}, peak {st.peak_equity:.2f})  cash {st.cash:.2f}  exposure {st.exposure:.2f} ({st.exposure / st.equity:.1%})")
    print(f"realised {r['realized_pnl']:+.2f}  fees {r['fees_paid']:.2f}  fills {r['fills']}")
    for p in st.positions.values():
        px = st.prices.get(p.symbol, (p.avg_price,))[0]
        print(f"  {p.symbol}: {p.qty:g} @ {p.avg_price:.2f}  now {px:.2f}  unrealised {(px - p.avg_price) * p.qty:+.2f}  stop {p.stop_price}  take profit {p.take_profit}")
    print("limits:", f"{lim.profile} (exposure {lim.max_exposure_fraction:.0%}, drawdown halt {lim.account_drawdown_halt:.0%}, daily halt {lim.daily_loss_halt:.1%}, risk per trade {lim.risk_per_trade:.2%}), pinned" if lim else f"NOT USABLE: {why}")
    print("KILL SWITCH ON" if st.killed else "kill switch off", "|", "DRAWDOWN HALT LATCHED" if st.halt_latched else "no drawdown halt")
    return 0


def main(argv: list[str] | None = None) -> int:
    config.load_env()
    p = argparse.ArgumentParser(prog="getrich", description="Local-first research and trading system")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("collect-binance", help="fetch closed Binance klines (public REST, no key)")
    b.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    b.add_argument("--timeframe", nargs="+", default=["1d"], help="one or more, e.g. 1d 1h")
    b.add_argument("--start", default="2020-01-01", help="first date to fetch when a symbol has no data yet")
    sub.add_parser("collect-news", help="fetch central-bank RSS feeds into the store")
    sub.add_parser("collect-webnews", help="fetch open web news headlines (GDELT and Google News RSS) by topic")
    sub.add_parser("watchdog", help="run all health checks once, raise or clear alerts")
    sub.add_parser("status", help="show the status screen")
    sub.add_parser("ingest-events", help="load the JSONL event log into DuckDB")
    sub.add_parser("doctor", help="check this Mac against the hardening list")
    g = sub.add_parser("gate", help="evaluate the Phase 0 exit gate from the event log")
    g.add_argument("--since", help="ISO time the unattended week started (default: when the launchd jobs were installed)")
    a = sub.add_parser("ack", help="record that you confirmed something only you can check")
    a.add_argument("item")
    a.add_argument("--note", default="")
    pr = sub.add_parser("propose", help="propose a PAPER order: runs the risk gate and prints its verdict. Nothing is submitted until you approve it")
    pr.add_argument("side", choices=["buy", "sell"])
    pr.add_argument("symbol", help="BTCUSDT or ETHUSDT")
    pr.add_argument("--stop", type=float, help="stop price (required for a buy)")
    pr.add_argument("--take-profit", type=float)
    pr.add_argument("--qty", type=float, help="quantity; omit to size from the risk budget. The gate can only reduce it")
    pr.add_argument("--risk", type=float, help="risk fraction of equity; can only lower the default 0.5%%")
    pr.add_argument("--reason", default="")
    pr.add_argument("--venue", choices=["paper", "testnet"], default="paper", help="paper = local simulator (default); testnet = Binance Spot Testnet, virtual money")
    ap = sub.add_parser("approve", help="approve a proposed order (asks you to type yes; needs an interactive terminal)")
    ap.add_argument("order_id")
    ap.add_argument("--yes", action="store_true", help="skip the prompt (for your own scripts; never used by the agents)")
    ap.add_argument("--venue", choices=["paper", "testnet"], default="paper", help="paper = local simulator (default); testnet = Binance Spot Testnet, virtual money")
    rj = sub.add_parser("reject", help="reject a proposed order")
    rj.add_argument("order_id")
    rj.add_argument("--reason", default="")
    ordp = sub.add_parser("orders", help="recent orders and their status")
    ordp.add_argument("--limit", type=int, default=15)
    ordp.add_argument("--venue", choices=["paper", "testnet"], default=None)
    rp = sub.add_parser("replay", help="replay stored BTC/ETH history through the real risk gate and paper broker; checks invariants, compares with the baselines")
    rp.add_argument("--write", action="store_true", help="write docs/phase4-replay.md")
    ff = sub.add_parser("forecast-fetch", help="DOWNLOAD a forecaster's weights from Hugging Face into the local cache and record their hashes (the only command that downloads models)")
    ff.add_argument("model", choices=["kronos_small", "chronos2", "timesfm25"])
    sub.add_parser("forecast-fetch-code", help="git-clone the Kronos source into models/kronos-src for review; never runs it")
    fr = sub.add_parser("forecast-run", help="generate walk-forward forecasts for a model (runs in its own process; weights must be fetched first)")
    fr.add_argument("model", choices=["kronos_small", "chronos2", "timesfm25"])
    fr.add_argument("--stride", type=int, default=None, help="forecast every Nth day (default depends on the model)")
    fr.add_argument("--since", default=None, help="only origins on or after this date, e.g. 2025-08-02")
    fr.add_argument("--max-new", type=int, default=None, help="stop after this many new forecasts per symbol (for a timing trial)")
    fe = sub.add_parser("forecast-eval", help="score cached forecasts against a random walk; writes docs/forecast-eval.md with --write")
    fe.add_argument("--write", action="store_true")
    nf = sub.add_parser("news-fetch", help="fetch the daily GDELT news series (volume and tone per topic) used by the PI-Net news channel; slow on purpose, cached")
    nf.add_argument("--refresh", action="store_true", help="refetch series that are already cached")
    ns = sub.add_parser("news-study", help="exploratory: do the daily GDELT news features line up with forward BTC/ETH returns at all? writes docs/news-study.md with --write")
    ns.add_argument("--write", action="store_true")
    ns.add_argument("--partial", action="store_true", help="use whichever GDELT series are cached (exploratory)")
    pr = sub.add_parser("preregister", help="log the SHA-256 of a pre-registration file so later edits are visible; the experiment refuses to run on an unlogged file")
    pr.add_argument("file", nargs="?", default="docs/preregistration-news-forecast.md")
    rvt = sub.add_parser("replay-voltarget", help="replay the volatility-scaled trend strategy through the real gate and approved limits; writes docs/phase4-voltarget.md with --write")
    rvt.add_argument("--write", action="store_true")
    ps = sub.add_parser("portfolio-study", help="run the PRE-REGISTERED wider-universe trend and momentum study; writes docs/portfolio-study.md")
    ps.add_argument("--no-register", action="store_true", help="do not add the strategies to the trial registry")
    pt = sub.add_parser("pinet-train", help="EXPLORATORY: train the PI-Net with a selected forecaster and/or news channel, compare with the baseline on identical rows (CPCV + strategy backtest); not registered")
    pt.add_argument("--forecaster", choices=["chronos2", "timesfm25", "kronos_small", "none"], default="chronos2", help="pretrained forecaster whose cached forecasts become a channel")
    pt.add_argument("--news", choices=["gdelt", "gdelt-partial", "none"], default="gdelt", help="news channel; gdelt-partial uses whichever series are cached (exploratory)")
    pt.add_argument("--models", default="lgbm", help="comma-separated: linear, lgbm, fusion")
    pt.add_argument("--null", type=int, default=0, help="shift-null draws per run (0 = skip)")
    pt.add_argument("--save", action="store_true", help="also fit a final model on all rows and save it under data/models/pinet/")
    pe = sub.add_parser("pinet-experiment", help="run the PRE-REGISTERED ablation (baseline, +forecaster, +news, +both; three models); writes docs/news-forecast-results.md")
    pe.add_argument("--forecaster", choices=["chronos2", "timesfm25", "kronos_small"], default="chronos2")
    pe.add_argument("--no-register", action="store_true", help="do not add the variants to the trial registry")
    posp = sub.add_parser("positions", help="account: equity, open positions, realised result, halts")
    posp.add_argument("--venue", choices=["paper", "testnet"], default="paper", help="paper = local simulator (default); testnet = Binance Spot Testnet, virtual money")
    tk = sub.add_parser("paper-tick", help="check for triggered stops and take profits (stored bars for paper, the exchange for testnet); snapshot equity")
    tk.add_argument("--venue", choices=["paper", "testnet"], default="paper", help="paper = local simulator (default); testnet = Binance Spot Testnet, virtual money")
    kl = sub.add_parser("kill", help="KILL SWITCH: flatten every position on the venue and block new ones")
    kl.add_argument("--venue", choices=["paper", "testnet"], default="paper", help="paper = local simulator (default); testnet = Binance Spot Testnet, virtual money")

    sub.add_parser("unkill", help="clear the kill switch")
    sub.add_parser("unhalt", help="clear the account drawdown halt after you have reviewed it")
    sub.add_parser("limits-pin", help="pin the current config/limits.toml as the one the risk gate trusts")
    sub.add_parser("ledger-verify", help="verify the insight ledger's hash chain")
    sub.add_parser("validate-harness", help="prove the evaluation harness can tell skill from luck (synthetic controls)")
    sub.add_parser("run-baselines", help="run the baseline strategies on stored BTC/ETH data and print the report")
    p2 = sub.add_parser("run-phase2", help="evaluate the PI-Net v1 models on real data against the baselines")
    p2.add_argument("--null-linear", type=int, default=100)
    p2.add_argument("--null-lgbm", type=int, default=40)
    p2.add_argument("--null-fusion", type=int, default=0)
    p2.add_argument("--write", action="store_true", help="write docs/phase2-results.md")
    ae = sub.add_parser("agents-extract", help="pre-filter new news and classify it with Haiku into the insight ledger")
    ae.add_argument("--limit", type=int, default=40)
    ae.add_argument("--dry-run", action="store_true", help="no API call, no changes: show counts and estimated cost")
    ab = sub.add_parser("agents-briefing", help="write the daily briefing, risk flags and shadow views with Sonnet")
    ab.add_argument("--hours", type=int, default=24)
    ab.add_argument("--dry-run", action="store_true")
    inv = sub.add_parser("investigate", help="shadow-only research agent (Claude Agent SDK, locked down): web search and fetch plus read-only market tools")
    inv.add_argument("question")
    inv.add_argument("--max-usd", type=float, default=0.75, help="hard cost limit for this run")
    inv.add_argument("--max-turns", type=int, default=15)
    inv.add_argument("--dry-run", action="store_true", help="no agent is started: show the lockdown configuration that would be used")
    sub.add_parser("agents-score", help="score matured shadow views and risk flags against what prices did")
    sub.add_parser("agents-status", help="Claude spend against the cap, ledger contents and the scorecard")
    sub.add_parser("run-meta", help="run the pre-registered meta-label experiment and judge it by its own criteria")
    d = sub.add_parser("derive-limits", help="derive proposed risk limits from the baseline strategy's history")
    d.add_argument("--write", action="store_true", help="write docs/risk-limits-proposal.md and config/limits.proposed.toml")
    la = sub.add_parser("limits-approve", help="approve a risk-limit profile: writes config/limits.toml and logs the decision")
    la.add_argument("--profile", required=True, choices=["minimal", "conservative", "moderate", "full"])
    la.add_argument("--replace", action="store_true", help="overwrite an existing config/limits.toml")
    la.add_argument("--risk-per-trade", type=float, default=None, help="fraction of equity at risk if a stop is hit, e.g. 0.02 for 2% (default 0.005, ceiling 0.05)")
    args = p.parse_args(argv)

    if args.cmd == "collect-binance":
        from .collectors import binance

        ok, summaries = True, {}
        for tf in args.timeframe:
            tf_ok, summaries[tf] = binance.collect(args.symbols, tf, args.start)
            ok = ok and tf_ok
        print(("OK " if ok else "FAILED ") + str(summaries if len(summaries) > 1 else summaries[args.timeframe[0]]))
        return 0 if ok else 1
    if args.cmd in ("propose", "approve", "reject", "orders", "positions", "paper-tick", "kill", "unkill", "unhalt", "limits-pin"):
        return _trading_command(args)
    if args.cmd == "news-fetch":
        from .news import gdelt_timeline

        res = gdelt_timeline.fetch_all(refresh=args.refresh, progress=lambda name, mode, n: print(f"  fetched {name}/{mode} ({n})", flush=True))
        print(res)
        return 0
    if args.cmd == "news-study":
        from .news import study

        res = study.run(partial=args.partial)
        text = study.to_markdown(res)
        print(text)
        if args.write:
            (config.root() / "docs" / "news-study.md").write_text(text)
            print("wrote docs/news-study.md")
        return 0
    if args.cmd == "preregister":
        from .eval import channel_ablation

        print("logged", channel_ablation.register_prereg(args.file))
        return 0
    if args.cmd == "replay-voltarget":
        from .trading import replay_voltarget

        out = replay_voltarget.run_all()
        text = replay_voltarget.to_markdown(out)
        print(text)
        if args.write:
            (config.root() / "docs" / "phase4-voltarget.md").write_text(text)
            print("wrote docs/phase4-voltarget.md")
        return 0
    if args.cmd == "portfolio-study":
        from .eval import portfolio_study

        res = portfolio_study.run(register=not args.no_register)
        text = portfolio_study.to_markdown(res)
        print(text)
        (config.root() / "docs" / "portfolio-study.md").write_text(text)
        print("wrote docs/portfolio-study.md")
        return 0
    if args.cmd == "pinet-train":
        from .eval import channel_ablation

        fm = None if args.forecaster == "none" else args.forecaster
        nw = None if args.news == "none" else args.news
        res = channel_ablation.train(fm, nw, tuple(m for m in args.models.split(",") if m), save_dir=config.root() / "data" / "models" / "pinet" if args.save else None,
                                     null_count=args.null)
        print(channel_ablation.train_markdown(res))
        return 0
    if args.cmd == "pinet-experiment":
        from .eval import channel_ablation

        res = channel_ablation.run(foundation=args.forecaster, news="gdelt", register=not args.no_register)
        text = channel_ablation.to_markdown(res)
        print(text)
        (config.root() / "docs" / "news-forecast-results.md").write_text(text)
        print("wrote docs/news-forecast-results.md")
        return 0
    if args.cmd in ("forecast-fetch", "forecast-fetch-code", "forecast-run", "forecast-eval"):
        return _forecast_command(args)
    if args.cmd == "replay":
        from .trading import replay_report

        out = replay_report.run_all()
        text = replay_report.to_markdown(out)
        print(text)
        if args.write:
            (config.root() / "docs" / "phase4-replay.md").write_text(text)
            print("wrote docs/phase4-replay.md")
        return 0 if all(not d["result"].violations for d in out["runs"].values()) else 1
    if args.cmd == "collect-webnews":
        from .collectors import webnews

        ok, summary = webnews.collect()
        print(("OK " if ok else "PARTIAL ") + str(summary))
        return 0
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
    if args.cmd == "run-baselines":
        from .eval import baseline_report

        res = baseline_report.run()
        print(baseline_report.to_markdown(res))
        return 0
    if args.cmd in ("agents-extract", "agents-briefing") and not getattr(args, "dry_run", False):
        import os

        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            print("No Anthropic credentials found. Add ANTHROPIC_API_KEY=... to the gitignored .env file in the project folder. "
                  "Use a key created just for this project, with a spend limit set in the Claude Console.")
            return 2
    if args.cmd == "investigate":
        import os

        from .agents import investigator

        if not args.dry_run and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            print("No Anthropic credentials found. Unattended and scripted runs need an API key (ANTHROPIC_API_KEY in the gitignored .env), "
                  "created just for this project with a spend limit in the Claude Console.")
            return 2
        res = investigator.investigate(args.question, max_usd=args.max_usd, max_turns=args.max_turns, dry_run=args.dry_run)
        print(json.dumps(res, indent=2, default=str) if res.get("status") == "dry_run" else res)
        if res.get("path"):
            print(open(res["path"]).read())
        return 0 if res.get("status") in ("recorded", "dry_run") else 1
    if args.cmd == "agents-extract":
        from .agents import extract

        res = extract.extract_pending(limit=args.limit, dry_run=args.dry_run)
        print(res)
        return 0
    if args.cmd == "agents-briefing":
        from .agents import briefing

        res = briefing.run(hours=args.hours, dry_run=args.dry_run)
        print(res)
        if res.get("path"):
            print(open(res["path"]).read())
        return 0
    if args.cmd == "agents-score":
        from .agents import scoring

        print(scoring.score())
        return 0
    if args.cmd == "agents-status":
        from .agents import scoring
        from .llm import budget
        from .store.db import connect

        with connect() as con:
            spent, cap = budget.month_spend_con(con), budget.monthly_cap()
            kinds = con.execute("SELECT json_extract_string(payload, '$.kind'), count(*) FROM insights GROUP BY 1 ORDER BY 1").fetchall()
            status_counts = con.execute("SELECT status, count(*) FROM item_processing GROUP BY 1 ORDER BY 1").fetchall()
            card = scoring.scorecard(con)
        print(f"Claude spend this month: ${spent:.4f} of ${cap:.2f} ({spent / cap:.0%})")
        print("ledger:", dict(kinds) or "empty")
        print("news items:", dict(status_counts) or "none processed")
        print("scorecard:", card)
        return 0
    if args.cmd == "run-meta":
        from .eval import meta_report

        res = meta_report.run()
        text = meta_report.to_markdown(res)
        print(text)
        (config.root() / "docs" / "phase3-meta-results.md").write_text(text)
        print("wrote docs/phase3-meta-results.md")
        return 0
    if args.cmd == "run-phase2":
        from .eval import phase2_report

        res = phase2_report.run({"linear": args.null_linear, "lgbm": args.null_lgbm, "fusion": args.null_fusion})
        text = phase2_report.to_markdown(res)
        print(text)
        if args.write:
            (config.root() / "docs" / "phase2-results.md").write_text(text)
            print("wrote docs/phase2-results.md")
        return 0
    if args.cmd == "derive-limits":
        from pathlib import Path

        from .eval import baseline_report, limits

        res = baseline_report.run()
        trend = res["returns"][[c for c in res["returns"].columns if c.endswith(":trend")]]
        derived = limits.derive(trend, limits.load_hourly(["BTCUSDT", "ETHUSDT"]))
        text = limits.to_markdown(derived)
        print(text)
        if args.write:
            root = config.root()
            (root / "docs").mkdir(exist_ok=True)
            (root / "config").mkdir(exist_ok=True)
            (root / "docs" / "risk-limits-proposal.md").write_text(text)
            (root / "config" / "limits.proposed.toml").write_text(limits.to_toml(derived, derived["recommended"]))
            (root / "docs" / "phase1-baselines.md").write_text(baseline_report.to_markdown(res))
            print(f"\nwrote docs/risk-limits-proposal.md, docs/phase1-baselines.md and config/limits.proposed.toml")
        return 0
    if args.cmd == "limits-approve":
        import hashlib

        from .eval import baseline_report, limits
        from .obs.events import emit

        target = config.root() / "config" / "limits.toml"
        if target.exists() and not args.replace:
            print(f"{target} already exists; pass --replace to overwrite it")
            return 2
        res = baseline_report.run()
        trend = res["returns"][[c for c in res["returns"].columns if c.endswith(":trend")]]
        derived = limits.derive(trend, limits.load_hourly(["BTCUSDT", "ETHUSDT"]))
        text = limits.to_toml(derived, args.profile, approved=True, risk_per_trade=args.risk_per_trade)
        target.parent.mkdir(exist_ok=True)
        target.write_text(text)
        p_ = derived["profiles"][args.profile]
        emit("limits.approved", service="operator", profile=args.profile, sha256=hashlib.sha256(text.encode()).hexdigest(),
             max_exposure_fraction=p_["exposure_cap"], account_drawdown_halt=p_["proposed_account_drawdown_halt"],
             daily_loss_halt=p_["proposed_daily_loss_halt"], gap_fits_inside_halt=p_["gap_fits_inside_halt"],
             risk_per_trade=args.risk_per_trade if args.risk_per_trade is not None else 0.005)
        from .trading import limits as trading_limits

        pinned = trading_limits.pin()          # the approval is what pins the file the risk gate will trust
        print(f"approved profile '{args.profile}' -> {target} (pinned {pinned[:12]})\n{text}")
        if not p_["gap_fits_inside_halt"]:
            print("note: at this profile a repeat of the worst historical 24-hour fall (x1.5) would exceed the drawdown halt")
        return 0
    if args.cmd == "validate-harness":
        from .eval import validate

        checks = validate.run()
        for c in checks:
            print(f"{'PASS' if c.passed else 'FAIL'}  {c.name}\n      {c.detail}")
        ok = all(c.passed for c in checks)
        print(f"\nHARNESS VALIDATION: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
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
