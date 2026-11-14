# 09 - Execution stack for Binance + MetaTrader 5 on a Mac (replaces the NautilusTrader + IBKR assumption in 06)

Date: 2026-11-14. Research only: no accounts, keys or trades were created. Engineering research, not investment advice.

**Evidence tags.** `[seen]` = I read the page/API response today. `[fetch-summary]` = page read through WebFetch, whose small model summarised it (I did not read the raw page); treat exact numbers as likely but not byte-verified. `[snippet]` = search-result text only. `[unverified]` = not checked, or from memory. Reddit, X and Instagram were not tried or reachable (consistent with the other agents); I did not try to circumvent that. HN was reachable via the Algolia API but has almost nothing on MT5 or Binance bots.

Local facts I read from the machine this agent runs on (probably yours, `[seen]`): macOS 26.5 (Darwin 25.5.0), Apple M4, 16 GB, Rosetta 2 installed, Docker at `/usr/local/bin/docker`, no Wine/Colima, `uv` and Homebrew present. `pmset -g` shows `sleep 1`, `autorestart 0`, and `AutomaticallyInstallMacOSUpdates = 1`. So today this Mac is set up to sleep after a minute idle, not restart after power loss, and auto-install macOS updates. Section 7 turns that into a checklist.

---

## 1. TL;DR and recommended stack

**Recommendation (solo builder, slow/low-turnover strategies, Mac M4 16 GB, free data):**

1. **Framework: a thin custom event-driven engine with a `Broker` interface** (option iii). It has one deterministic risk gate in front of every order, one OMS/state store (SQLite WAL + append-only event log), and three broker implementations: `SimBroker` (backtest/paper), `BinanceBroker`, `Mt5Broker`. Use **vectorbt only for research sweeps** (option vi). Borrow ideas, not code, from Freqtrade (dry-run, `stoploss_on_exchange` lifecycle, FreqAI-style scheduled retraining), Hummingbot (executors) and Vibe-Trading (demo/live identity guard).
   - NautilusTrader is the credible alternative if you want maximum engine rigor and accept writing an MT5 adapter (see section 3). I do not recommend it as the first build, because (a) it has no MT5 adapter, (b) it is mid v1->v2 transition (stable 1.231.0 on 2026-08-02, `2.0.0rc9` on 2026-11-10), (c) its adapter guide is Rust-in-tree, and (d) with hourly-to-daily strategies its parity advantage is small compared with its integration cost.
2. **Binance: spot + USDⓈ-M futures via one adapter built on the official modular SDKs or ccxt.** Both were fresh as of this week (official `binance-sdk-spot 13.6.0` and `binance-sdk-derivatives-trading-usds-futures 18.3.1` released 2026-11-12; ccxt 4.5.92 on 2026-11-04). Decide with a one-day spike (section 4.8). Use **Ed25519 API keys, trade-only permission, no withdrawal permission, IP-restricted**, kept in macOS Keychain.
3. **MT5: run MT5 on a small Windows VPS, not Wine on the Mac.** On the VPS run (a) a tiny gateway service using the **official Windows-native `MetaTrader5` Python package**, reachable only over a private tunnel (Tailscale or SSH), and (b) later a small **MQL5 "guardian" EA** as an independent last line of defence. Python on the Mac sends *intents*; the Mac-side risk gate approves them; the gateway re-checks hard limits and attaches server-side SL/TP on every order. Rough cost USD 5-30/month for a 2-4 GB Windows VPS `[snippet]` (section 2). For development and demo you can use `siliconmetatrader5` on the Mac (Wine under Rosetta), but I would not make it the unattended 24/5 path.
4. **Why not run MT5 locally on the Mac for live:** the only Mac-native route is Wine (official installer, or wrappers on top), and there are first-hand 2025-26 failure reports: MT5 build 5.0.0.3331 refused to start after an auto-upgrade on macOS 15.5 (2025-06-09); MT5 build 5834 crashed on every Buy/Sell press on macOS Tahoe 26.5 (2026-05-28, no confirmed fix); a MetaQuotes forum moderator called the Wine installer "less reliable for intensive trading especially with EAs and DLLs" (2025-09-02). Your Mac is on 26.5. Apple also plans to cut Rosetta 2 to a games-only subset in macOS 28 (fall 2027), and the Wine-based wrappers depend on it today (section 2).
5. **Real money last.** Binance Spot/Futures demo and MT5 demo prove plumbing, not profitability (section 5). Micro-live calibrates costs.

**Biggest risks:** MT5 bridge fragility; Binance API churn (the Dec 2025 conditional-order migration broke Freqtrade, Nautilus and ccxt users' stops for days); a Mac that sleeps or reboots; and the "local-first" purity trade-off of a Windows VPS (it holds your MT5 login but no LLM, news or model).

---

## 2. MT5 on macOS Apple Silicon: all options

### 2.1 What exactly is the Python limitation (b)

- PyPI `MetaTrader5` latest is **5.0.6231, uploaded 2026-09-27**; its only files are `win_amd64` wheels (cp310-cp314 seen; classifiers list 3.6-3.14) `[seen]` (https://pypi.org/project/MetaTrader5/).
- MetaQuotes' docs say the package obtains data "via interprocessor communication directly from the MetaTrader 5 terminal" and `initialize()` connects to a running terminal `[fetch-summary]` (https://www.mql5.com/en/docs/python_metatrader5). So it is a client for a local Windows `terminal64.exe` process, not a broker/server API. No macOS, Linux or ARM wheel exists, so `pip install` fails on a Mac (MQL5 thread 2022-05 to 2025-04, https://www.mql5.com/en/forum/425741 `[fetch-summary]`).
- It is functionally complete for our needs: `copy_rates_*`, `copy_ticks_*`, `symbol_info_tick`, `order_check`, `order_send` (with `sl`, `tp`, `deviation`, `type_filling`, `magic`), `positions_get`, `history_deals_get` `[fetch-summary]` (https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py).
- Known flakiness on current builds, even on native Windows: `initialize()` returning `(-10005, 'IPC timeout')` on build 6231 (2026-10-05) and 6249; the only observed fix was manually logging into a demo account once so the terminal had account state; no root cause given (https://www.mql5.com/en/forum/517620 `[fetch-summary]`). Implication: your gateway needs a watchdog that restarts the terminal and re-initialises, and a fresh VPS needs a manual first login.

### 2.2 Comparison table

Maintenance data from GitHub API / PyPI `[seen]` unless noted.

| Option | How Python talks to MT5 | Pros | Cons / failure modes | Maintenance (as of 2026-11-14) | Unattended 24/5? |
|---|---|---|---|---|---|
| **(a) Official macOS MT5 (Wine inside the app)** | No native Python path. Need Windows Python inside the same Wine prefix + an RPyC/REST bridge (e.g. `meta-trader-mcp setup-wine`), or an MQL5 EA using native sockets (`SocketConnect/Send/Read`, EA/scripts only, max 128 sockets, address must be allow-listed in terminal settings `[fetch-summary]`, https://www.mql5.com/en/docs/network/socketcreate) | Official installer; free; same app brokers recommend. Min macOS Catalina; all Apple CPUs `[fetch-summary]` (https://www.metatrader5.com/en/terminal/help/start_advanced/install_mac) | Wine breakage tied to macOS point releases: "Bad system call" after auto-upgrade on macOS 15.5 (https://www.mql5.com/en/forum/488554); Buy/Sell crash on macOS 26.5, build 5834, no confirmed fix; WebView2 runtime missing under Wine 11.14 (https://www.mql5.com/en/forum/510357). Moderator advice: Wine 11.3+, disable auto-update. MT5 auto-update is a hazard | MetaQuotes ships Wine-based installer; Wine-version dependent | **No.** Fine for manual demo/charting |
| **(b) Official `MetaTrader5` pkg on the Mac** | n/a | n/a | Windows x86-64 wheels only (2.1) | PyPI 5.0.6231, 2026-09-27 | Not possible directly |
| **(c) CrossOver / Wine wrappers** | Same as (a): Windows Python in the bottle + bridge | CrossOver is commercial; CodeWeavers says CrossOver 27 ARM64 runs without Rosetta `[snippet]` (https://www.codeweavers.com/blog/mjohnson/2026/06/11/whats-in-and-whats-out-for-crossover-27, 403 on direct fetch) | One MQL5 forum reply cited by the Dec-2024 thread said Rosetta and CrossOver "probably won't work" (second-hand, https://www.mql5.com/en/forum/478849). MetaQuotes moderator suggests CrossOver for the macOS 15.5 crash (https://www.mql5.com/en/forum/488554). Whisky-style wrappers: not researched `[unverified]` | n/a | Not recommended |
| **(d) Windows 11 ARM VM (Parallels / VMware Fusion / UTM)** | Run Windows Python + MT5 *inside* the VM; expose a REST/socket gateway to macOS (the pattern one MQL5 user reported as "faster and more reliable" than native, on an Intel Mac + Fusion, https://www.mql5.com/en/forum/425741) | Real Windows userland; MT5 x64 runs under Windows-on-ARM emulation; a MetaQuotes moderator reported MT5 "runs well" on M1-M3 under Parallels (2025-09-02, https://www.mql5.com/en/forum/494485 `[fetch-summary]`) | Parallels KB (last reviewed 2023-08-10): MT4 and then-recent MT5 builds failed to launch on Windows 11 Arm; workaround = older build (https://kb.parallels.com/129408/). I found **no report** of `pip install MetaTrader5` working on Windows-on-ARM; plausible via an x64 Python, but `[unverified]`. Needs your Mac awake 24/5 and VM auto-start. Parallels does not include a Windows licence; Windows 11 Pro Arm needs its own licence (https://www.parallels.com/products/desktop/microsoft-authorized-solution-windows-11-arm/ `[fetch-summary]`). VMware Fusion Pro is free for all uses per VMware FAQ `[snippet]` (https://www.vmware.com/docs/desktop-hypervisor-faqs) | Parallels/Fusion actively maintained | Possible but ties production to a laptop-class host; acceptable only as dev/demo or fallback |
| **(e1) `siliconmetatrader5`** (PyPI 1.3.0, 2026-11-05; repo `bahadirumutiscimen/silicon-metatrader5`, 43 stars, created 2025-12-15, one maintainer, PyPI classifier "Beta", licence **PolyForm Noncommercial**, fine for personal use) | RPyC bridge on 127.0.0.1 exposing the official-package API; same function names | Best-packaged Mac route: v1.3 "Mac native mode" runs MT5 in Wine 11 under Rosetta 2, no VM/Docker; desktop app, `smt5` CLI, health checks; can also manage a Linux/Windows VPS over SSH; `server_now()` helpers for broker-clock bars. Vendor benchmark claims: startup 55 s -> 20 s, bridge round trip 11 ms -> 0.8 ms (vendor numbers, not independently run) `[seen]` | Inherits all Wine/macOS/Rosetta risks of (a). Single maintainer, 5 weeks old in current form. Its own materials point to a real Windows server for 24/7 | Active (6 releases Dec 2025-Nov 2026) | Dev/demo yes; live unattended on Mac no |
| **(e2) `mt5linux`** (`lucas-campagna/mt5linux`, 239 stars, MIT, PyPI 1.1.1 2026-08-04, pushed 2026-10-27, 5 open issues `[fetch-summary]`) | Wine + `mt5server.exe` + RPyC on port 18812; Docker option | Simple, MIT | Linux-targeted; README does not mention macOS/Apple Silicon `[fetch-summary]`. A forum commenter said it "doesn't work either" (search snippet, no thread) `[snippet]` | Active | Best used on a Linux x86 host, not a Mac |
| **(e3) `meta-trader-mcp`** (PyPI 1.2.2, 2026-06-15, MIT, one maintainer) | Windows Python created inside the official macOS app's Wine prefix + loopback bridge | Only the macOS path is "tested & validated" (macOS 26, Wine 11) | Optimisation results not supported on macOS; third party; weeks-old | Active but young | No |
| **(e4) `mt5-httpapi`** (`psyb0t/mt5-httpapi`, 30 stars, WTFPL, created 2026-02-15, Show HN same day) | REST + MCP to real Windows MT5 in a QEMU/KVM VM inside Docker | "No Wine"; Strategy Tester, EA deploy, REST; token auth | Requires Linux with `/dev/kvm`; macOS not mentioned, so not Mac-usable `[fetch-summary]`; pre-5.0 API churn | Active | On a Linux box only |
| **(e5) `gmag11/MetaTrader5-Docker`** | VNC web UI; no Python bridge by itself | 419 stars, MIT | Last push 2025-12-20; x86 image, ARM behaviour `[unverified]` | Slow | No |
| **(e6) ZeroMQ / socket EA bridges** | EA inside MT5 talks to Python over ZMQ/socket | Decouples Python from the flaky IPC; EA keeps running if Python dies | `khramkov/MQL5-JSON-API`, `miya779/python3-mql5-zeromq-connector` and ~18 other MT4/5 bridge repos were **taken down by a MetaQuotes DMCA on 2023-11-07** (claimed Manager-API misuse) `[seen]` (https://github.com/github/dmca/blob/master/2023/11/2023-11-07-metatrader.md). `darwinex/dwx-zeromq-connector` (374 stars, BSD-3) last push 2022-05-25; `dingmaotu/mql-zmq` last push 2023-12-19 and needs DLLs (fragile on Wine/ARM). **Write your own** over MQL5-native sockets (no DLL) | Third-party bridges are stale or removed | Good pattern, but write it yourself |
| **(f) MetaApi (cloud)** | Third-party cloud runs MT terminals and exposes a websocket/REST API | No infrastructure to run | **Violates local-first**: your broker credentials live in a vendor cloud (page did not address credential storage `[fetch-summary]`, but a cloud MT terminal needs your login by construction `[unverified]`). Paid; a single May-2026 blog claims USD 15-50 per account/month, unconfirmed `[snippet]` | Commercial | Works, but flag against local-first; not recommended |
| **(g) Windows VPS: MT5 + gateway or EA** | Official Windows Python package against a local terminal on the VPS, or an MQL5 EA; your Mac talks to the gateway over Tailscale/SSH | Official, supported path; no emulation; static IP; MT5 stays up when the Mac sleeps; server-side SL/TP | Costs money; password lives on VPS; terminal needs a signed-in desktop session (auto-login) and a watchdog; IPC-timeout bug class (2.1); Windows updates/reboots to schedule; you must harden RDP/SSH | Windows/MT5 maintained by vendors | **Yes: most robust for a solo builder** |
| **(h) Avoid MT5** | See 2.4 | | | | |

**VPS prices seen (all `[snippet]` from listing/review sites, verify on provider pages):** FxSVPS "Economy Pro" 2 GB RAM, 2 vCPU about USD 5.38/month on a 24-month promo (https://www.whtop.com/plans/fxsvps.com/92879); DropVPS 2 GB USD 19.99; Photon VPS 2 GB USD 25.95; one guide says ForexVPS.net around USD 30 for 2 GB; Contabo lists Windows Server as an add-on from about USD 5.50 on top of the base plan (see https://serverspace.us/about/blog/best-forex-vps-hosting-providers-for-2026-mt4-mt5-ready/ and https://bearhost.com/blogs/best-cheap-forex-vps-mt4-mt5-2026). Guides suggest 4 GB for comfort; 2 GB Windows idles at roughly 1.5-2 GB. MetaQuotes' own VPS service page returned 404, so its price and constraints are not verified. Your broker may offer a free VPS above a deposit/volume threshold `[unverified]`.

### 2.3 Rosetta and Wine timeline (affects options a, c, e1, e3)

- macOS 27 is the last release with full Rosetta 2; macOS 28 (expected fall 2027) keeps only a reduced Rosetta for older games `[snippet]` (https://www.macrumors.com/2025/06/10/apple-to-phase-out-rosetta-2/, https://www.macrumors.com/2026/06/12/macos-golden-gate-rosetta-support `[fetch-summary]`). Apple has not said whether the pieces Wine needs survive (https://developer.apple.com/forums/thread/830692 `[snippet]`).
- CodeWeavers says CrossOver's ARM64 build will not need Rosetta `[snippet]`. MetaQuotes' official Mac installer bundles its own Wine; whether it will go ARM64-native is `[unverified]`.
- So any Wine-on-Mac plan has roughly a 12-month runway before a re-platform risk.

### 2.4 Alternatives that avoid MT5 (technical API quality only; availability to Sri Lankans is another agent's job)

- **cTrader Open API** (Spotware): JSON or Protobuf over TCP/WebSocket, OAuth with cTrader ID, demo and live, official C# and Python SDKs, 50 req/s for real-time and 5 req/s for historical per connection `[fetch-summary]` (https://help.ctrader.com/open-api/). Python SDK `ctrader-open-api` (Twisted-based, async, protobuf bundled) `[snippet/fetch-summary]` (https://github.com/spotware/OpenApiPy). Runs natively on macOS, which is a real engineering advantage. Needs a cTrader broker.
- **Deriv API**: WebSocket + REST, demo supported, but I could not extract auth/limits details from the docs index page `[fetch-summary]` (https://developers.deriv.com/docs/). Quality `[unverified]`.
- **OANDA**: the Python `oanda/v20-python` repo was last pushed **2021-08-01** `[seen]`; LEAN lists OANDA as a supported brokerage `[fetch-summary]`. API itself not re-checked.
- **Broker REST/FIX**: not researched.
- Net: if your broker offers cTrader, the cTrader Open API removes the entire Windows/Wine problem. Ask the Sri Lanka-regulation agent whether any reachable broker offers it, as that would change the recommendation (open question 1).

### 2.5 Recommended MT5 pattern (robust, solo-friendly)

```
Mac (brain, always the decision-maker)            Windows VPS (execution shim only)
 engine -> risk gate -> Mt5Broker  --Tailscale-->  gateway.py (FastAPI/ZMQ, auth token)
   ^ heartbeat + state pull        <------------     |-- official MetaTrader5 pkg -> terminal64.exe -> broker
                                                     |-- hard limits (lots, orders/min, symbol allow-list,
                                                     |     SL mandatory, daily equity stop)
                                                     '-- (phase 2) MQL5 guardian EA: closes positions w/o SL,
                                                          enforces equity stop, honours a global-variable halt
```

- Orders always carry `sl` and `tp` (server-side at the broker). Check `symbol_info().trade_stops_level` / `trade_freeze_level`, filling mode flags (FOK/IOC/Return), and run `order_check()` before `order_send()` (MQL5 constants: https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants `[fetch-summary]`).
- Idempotency: put a deterministic `magic` + `comment` (client order id) on every order; after any timeout, query `positions_get/orders_get/history_deals_get` before retrying.
- Gateway watchdog: restart terminal and re-`initialize()` on IPC error; alert on retcodes other than DONE; heartbeat to the Mac every 10-30 s; if heartbeat is lost for N minutes, stop accepting new entries (existing server-side SL/TP stay).
- Keep the gateway tiny (a few hundred lines) and version-pinned; do not depend on third-party MT5 bridges (DMCA history, single maintainers).
- Dev/demo on the Mac: `siliconmetatrader5` is the quickest way to call the same API from macOS; keep your `Mt5Broker` talking to an abstract client so the gateway and the Mac bridge are interchangeable.

---

## 3. Framework decision

### 3.1 Comparison table

Stats from GitHub API `[seen]` on 2026-11-14.

| Option | Stars / last push / licence | Binance | MT5 | Backtest-paper-live parity | Mac M4 | Risk-gate and kill-switch integration | Verdict |
|---|---|---|---|---|---|---|---|
| **(i) NautilusTrader** | 31.5k / 2026-11-14 / LGPL-3.0. PyPI stable **1.231.0 (2026-08-02)**, `2.0.0rc9` (2026-11-10); wheels incl. `macosx_26_0_arm64`, Python >=3.12 | Listed **Stable**; spot, USDⓈ-M, COIN-M; testnet and Demo; Ed25519 recommended; commands are never auto-retried after ambiguous results; algo-order endpoint used for conditional futures orders; bracket orders "planned but currently denied"; no margin trading `[fetch-summary]` (https://nautilustrader.io/docs/latest/integrations/binance/) | **No adapter** (integrations page lists no MT5/OANDA/cTrader) `[fetch-summary]`. Writing one means an in-tree Rust adapter per the developer guide (config, instruments, data client, execution client, reconciliation, PyO3, conformance/DST tests); Python out-of-tree interface page exists but I did not read it `[fetch-summary]` | Best by design: same kernel; docs warn live differs in venue, timing, reconciliation | Good, native wheels | Risk engine exists but its live docs page does not describe a kill switch or HALTED states (build your own; `shutdown_on_error` only) `[fetch-summary]`. One `LiveNode` per process | Strong for Binance-only; MT5 adapter is weeks of work (my estimate, `[unverified]`). Live issues still open: Binance Spot SBE 3:6 decode failure opened 2026-11-13 (#5664), multi-assets mode unsupported (#5369) |
| **(ii) Freqtrade + separate MT5 path** | 56.9k / 2026-11-12 / **GPL-3.0**; release 2026.10 (2026-10-30) | Mature spot + futures; dry-run; Telegram/WebUI; FreqAI retraining; futures needs one-way + single-asset mode; `stoploss_on_exchange` limit/market (https://www.freqtrade.io/en/stable/exchanges/, `/freqai/` `[fetch-summary]`) | None | Dry-run vs live is a mode flag, but backtests use its own fill logic; FreqAI example "not designed to be run in production" | Docker recommended; fine | It owns the strategy loop; LLM/risk-gate integration is via callbacks and the REST API; two systems means two risk gates | Good crypto-only bot; wrong core for a unified two-venue risk-gated system. Dec 2025: stops on Binance futures failed with -4120 (issue #12610, opened 2025-12-09, closed 2025-12-13); then orphaned conditional orders (#12681, closed 2026-01-11) `[seen]` |
| **(iii) Thin custom engine + broker interface** | n/a | ccxt (44.9k, MIT, 4.5.92 on 2026-11-04) or official SDKs | Your gateway client (section 2.5) | You write one `Broker` interface and one `SimBroker`; parity is a test you own (replay recorded fills through both) | Trivial | **One gate, one kill switch, by construction** | **Recommended.** Cost: you own OMS state machine, reconciliation, idempotency. Mitigated by slow strategies and few instruments |
| **(iv) LEAN CLI** | 22.5k / 2026-11-13 / Apache-2.0 | Binance spot/futures supported `[fetch-summary]` (https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages) | **Not listed**; QC says brokerages can be requested | Strong | Docker | Locked into QC algorithm framework; track 06 flagged a possible paid seat for local live (unverified there) | Not for this pair |
| **(v) Vibe-Trading (HKUDS)** | 38.2k / 2026-11-13 / MIT; created 2026-04-01; releases v0.1.19 (2026-11-05); 24 open issues | README lists Binance Read/Sim/Live | README lists MT5 Read/Sim/Live via the **Windows-only** `MetaTrader5` package (its own `_client.py` raises a dependency error if the package is missing) `[seen]` | Research/backtest tool with agent front end; maintainers say live broker trading "is experimental and not verified by us against a real broker account" `[fetch-summary]` (https://github.com/HKUDS/Vibe-Trading) | Python | Has a mandate (symbol/order/exposure limits) and kill switch concepts | Honest read: an LLM research harness with experimental execution, v0.1.x. Read it for ideas (demo/live identity guard via `trade_mode` + pinned login; lot ceiling; fail-closed reads). Do not run real money through it. Also overlaps your own agent layer |
| **(vi) vectorbt (OSS)** | 9.8k / 2026-11-11 / Apache + Commons Clause (SPDX NOASSERTION); 1.2.1 | data-agnostic | data-agnostic | None (research only) | Numba works on M-series | n/a | Use for sweeps; re-implement winners in the engine and require parity within tolerance |

Other references: **Hummingbot** 21.2k stars, Apache-2.0, pushed 2026-11-13, v2.17.0 (2026-09-22): market-making and "V2 controllers/executors" (grid, DCA, TWAP), `binance_perpetual` connector, Docker deploy, "one bot per install", paper trading on live data without keys `[fetch-summary]` (https://github.com/hummingbot/hummingbot). Borrow the *executor* concept (order lifecycle objects with their own timeouts and cancel logic). **python-binance** 7.2k, MIT, last push 2026-06-08 (v1.0.37), i.e. five months quiet through the algo-order and listenKey changes; I would not pick it. **binance-connector-python** (legacy) 3.0k, v3.13.0 2026-04-30; Binance's newer modular SDKs are the active line.

### 3.2 Why (iii), stated plainly

- Your hard requirements are a **deterministic, LLM-proof risk gate** and a **kill switch** that spans two very different venues. Every off-the-shelf engine puts its own order manager between your strategy and the broker, so you would still be bolting a gate onto someone else's loop.
- Your strategies are slow (master report), so the main things Nautilus buys (nanosecond event ordering, Rust speed, tick-level fill simulation) are not your bottleneck.
- The real engineering risk is **venue-specific order semantics** (Binance conditional-order migration; MT5 filling modes, stops level, hedging vs netting). That risk is the same under every framework, and you must understand it either way.
- What you give up: a battle-tested OMS and reconciliation. Counter-measures: SQLite append-only event log, deterministic client order ids, mandatory startup reconciliation against broker state, property tests, and a canary test suite that places and cancels 1-lot/min-notional orders on Binance demo and MT5 demo every deploy.
- Reconsider Nautilus if: you later add many Binance symbols with intraday logic and need book-level simulation, or if a Python/out-of-tree MT5 adapter appears.

### 3.3 Minimal architecture and risk-gate placement

```
 Collectors (news, prices) -> local store (Parquet + SQLite)  [no execution rights]
 Agent/model layer (Claude + forecasts + classifier)        -> emits TargetIntent objects only
                                                              (symbol, side, size hint, thesis_id, max_hold, stop distance)
 Intent -> Sizing (vol-target, fractional Kelly cap) -> **RISK GATE (deterministic code, no LLM)**
      checks: mode assertion (paper/live), symbol allow-list, per-trade risk %, gross/net/correlated exposure,
              daily/weekly loss halt, max open orders, order rate, data-freshness, spread/cost cap, session/news blackout,
              mandatory protective stop present, min-notional/lot step, funding/swap cap
 -> OMS (state machine: NEW > SENT > ACKED > PARTIAL > FILLED/CANCELED/REJECTED/UNKNOWN; write-ahead before send)
 -> Broker interface: SimBroker | BinanceBroker | Mt5Broker (client of the VPS gateway)
 -> Venue (protective orders live ON the venue)
 Reconciler (every N s + on reconnect) <- broker positions/orders/fills;  Watchdog/heartbeat -> alerts;  Kill switch
```

Placement rules:
1. **The gate is the only code path that can call `Broker.submit()`** (broker objects are not importable by agent code; enforce with module boundaries and a test).
2. **Gate decisions are logged with inputs**, and a rejected intent is information for the learning loop, never silently retried.
3. **Two gates on MT5:** the Mac-side gate plus the gateway/EA hard limits (lots, symbol list, SL required, equity stop). A compromised or buggy Mac cannot exceed them. Binance has no equivalent middle tier, so keep the key trade-only, whitelisted to the execution host, and small.
4. **Kill switch layers:** (1) flag file/DB flag checked by the gate (halt new orders); (2) auto-trip rules (loss, error rate, stale data, reconciliation mismatch, clock drift); (3) `flatten-and-halt` command callable by Telegram (authenticated chat id + confirmation word); (4) venue-side protective orders so a dead process is not naked; (5) out-of-band: revoke the Binance API key from the Binance app, disable trading on the MT5 account / close from the MT5 mobile app. Layers 4-5 must work with the Mac off.

### 3.4 Broker-side protective orders

**Binance USDⓈ-M futures (changed 2025-12-09):**
- Conditional types (`STOP_MARKET`, `TAKE_PROFIT_MARKET`, `STOP`, `TAKE_PROFIT`, `TRAILING_STOP_MARKET`) must go through **`POST /fapi/v1/algoOrder`** with `algoType=CONDITIONAL`; sending them to `/fapi/v1/order` or `batchOrders` returns `-4120` `[seen via changelog fetch]` (https://developers.binance.com/docs/derivatives/change-log, announced 2025-11-06). Untriggered algo orders cannot be modified (cancel and replace); the conditional limit is 200 across symbols (2025-12-29); since 2026-06-20 algo placement counts on the order-rate counters (weight 1 on 10 s and 1 min counters, 0 on IP weight).
- Parameters I read: `closePosition=true` (close whole position; cannot be combined with `quantity` or `reduceOnly`; restrictions in Hedge mode), or `reduceOnly=true` with quantity (not allowed in Hedge mode), `workingType=MARK_PRICE|CONTRACT_PRICE` (default CONTRACT_PRICE), `priceProtect`, `clientAlgoId` (unique among open orders, up to 36 chars), recvWindow max 60000 ms `[fetch-summary]` (https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order).
- **No native OCO on futures:** SL and TP are two orders; you must cancel the survivor when the other triggers. Freqtrade #12681 is exactly this bug class (orphaned conditional orders, repeated re-creation). Your reconciler must treat "protective order without position" and "position without protective order" as incidents.
- Recommended default: one-way mode, `STOP_MARKET` + `closePosition=true` on `MARK_PRICE`, with a periodic verifier that fetches algo orders and positions. A stop-market can still slip badly in gaps/thin books.
- Order-rejection for exempt flows: error `-1008` (system throttling) exempts close-position, reduce-only and cancel orders `[fetch-summary]`.

**Binance spot:**
- Spot supports `orderList/oco`, `orderList/oto`, OTOCO, OPO and OPOCO (OPO on all symbols since about 2025-12-18); `MAX_NUM_ORDER_LISTS` 20 per symbol `[seen/fetch-summary]` (https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md, CHANGELOG). Entry + OCO (TP limit + stop-loss-limit/stop) is the standard pattern. Spot is long-only (no shorting without margin).

**MT5:** protective SL/TP are fields on the position and live on the broker's server, so they trigger even if your VPS dies. Verify after every fill that the position shows the SL/TP (`positions_get`), use `deviation` for entry slippage, mind stops level (minimum distance) and freeze level, and check account type (netting vs hedging) because it changes how SL/TP and partial closes behave `[unverified for your broker]`.

---

## 4. Binance specifics

### 4.1 Spot vs USDⓈ-M futures

| | Spot | USDⓈ-M futures |
|---|---|---|
| Use for | Long-only inventory, simple OCO exits | Shorting, hedging, funding/carry research, leverage (keep it tiny) |
| Fees (VIP0) | 0.100% maker / 0.100% taker; BNB discount 25% -> 0.075% `[fetch-summary]` (https://www.binance.com/en/fee/schedule) | 0.02% maker / 0.05% taker, BNB 10% discount; the FAQ page labels these as a hypothetical example, so confirm in your account's fee tier `[fetch-summary]` (https://www.binance.com/en/support/faq/detail/360033544231). Funding payments apply (not modelled in demo, see section 5) |
| Rate limits | 6,000 weight/min per IP, 10 orders/s and 100,000 orders/day (via NautilusTrader's adapter docs); `RAW_REQUESTS` raised to 300,000 per 5 min and successful order place/cancel weight 0 since 2026-04-02 `[fetch-summary]` | 2,400 weight/min per IP; order counters 300 per 10 s, 1,200 per min; counted per account `[fetch-summary]` (https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info). 429 = back off; repeated -> 418 IP ban from 2 min up to 3 days |
| Order types | MARKET, LIMIT, STOP_LOSS(_LIMIT), TAKE_PROFIT(_LIMIT), OCO/OTO/OTOCO/OPO(CO), pegged (2025-08-28), iceberg | MARKET, LIMIT, algo conditional types, `reduceOnly`, `closePosition`, modify endpoints (`reduceOnly` added 2026-09-15) |
| User-data stream | `listenKey` methods **retired 2026-02-20**; use WebSocket API `userDataStream.subscribe` (2026-02-20 changelog) | WebSocket base paths split into `/public`, `/market`, `/private` (2026-03-05; legacy URL decommissioned 2026-04-23) |

### 4.2 WebSocket reliability facts (spot docs `[seen]`, https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md)
- A single stream connection is valid for **24 hours**; expect to reconnect. Server pings every **20 seconds**; you must pong promptly. Limit of **5 incoming messages/second** per connection; up to **1,024 streams** per connection. Futures raised max streams per connection from 200 to 1,024 on 2025-07-02 `[fetch-summary]`.
- New in 2026: a `serverShutdown` event ("reconnect promptly", 2026-05-06), and "WebSocket Streams upgrade (2026-07-09): connections may drop" `[fetch-summary]`. Design: reconnect with jittered backoff, resubscribe, then **resync the order book and reconcile orders/positions via REST** before trusting state.

### 4.3 What changed in 2025-2026 that matters (changelogs via fetch; dates as reported)
- 2025-11-06 announced, **2025-12-09** effective: futures conditional orders -> Algo Service (section 3.4).
- 2026-02-20: spot `listenKey` user-data methods retired; `!ticker@arr` retired 2026-03-26; `/api/v1` retired 2026-03-25.
- ~2026-01-15: payloads must be **percent-encoded before signing** or you get -1022 `[fetch-summary]`.
- SBE schemas retire on a rolling basis (3:0 2026-02-19, 3:1 2026-06-29, 3:2 2026-09-25, 3:3 2026-11-09); SBE 3:6 is rolling out about now (2026-11-11 entry) and **already broke Nautilus's spot `exchangeInfo` decode on `2.0.0rc8`** (issue #5664, 2026-11-13). Lesson: use JSON endpoints unless you need SBE, pin your SDK, and run a daily canary.
- Futures history limits tightened (`userTrades` 6 -> 3 months on 2026-08-26; `historicalTrades` 3 -> 1 month, weight 20 -> 200). Store your own fills; do not rely on the exchange as your ledger.
- Futures testnet: official docs are internally inconsistent (general-info says `https://demo-fapi.binance.com`; the algo-order page says `https://testnet.binancefuture.com`); a third-party Korean guide dated 2026-08-30 says `testnet.binancefuture.com` now redirects to `demo.binance.com`, with demo keys separate from spot testnet keys `[snippet/fetch-summary]` (https://algolab.co.kr/blog/binance-testnet-api-guide-2026). Treat the URLs as configuration, and verify at integration time.
- **Real evidence of fragility:** all three major open-source stacks were hit by the Dec-2025 migration: Freqtrade #12610 (closed in 4 days), Nautilus #3287 (opened 2025-12-09, closed 2025-12-18), python-binance #1645 (2025-12-10). ccxt kept merging algo-order fixes through 2026-10-31 (e.g. wrong filled quantity on USDⓈ-M algo orders, #31078) `[seen]`.

### 4.4 Testnets and demo (fidelity)
- **Spot Testnet** (`testnet.binance.vision`): periodically wiped (about monthly, no notice; keys survive); IP/order limits and filters "generally the same as production"; only `/api`, not `/sapi`; the docs describe no matching-engine differences (silence, not proof of fidelity); changelog warns it "is not always synced with the live exchange" `[seen/fetch-summary]` (https://developers.binance.com/docs/binance-spot-api-docs/testnet/general-info, https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/testnet/CHANGELOG.md).
- **Binance Demo Trading** (spot and futures, `demo.binance.com`, `demo-api.binance.com`, `demo-fapi.binance.com`): virtual balances, resettable; Binance's own FAQ says there may be "discrepancies in the chart data, actual order book pricing, and trade order execution" and that demo performance "isn't a reliable indicator of live results"; features such as Grid, TWAP, webhook unavailable on futures demo `[fetch-summary]` (https://www.binance.com/en/support/faq/detail/9be58f73e5e14338809e3b705b9687dd). Availability is country-dependent (another agent covers Sri Lanka).
- What I could not find: any official statement on whether demo models funding payments, slippage vs depth, or partial fills. Third-party guides say simulators generally do not `[snippet]`. Assume **not modelled** until you measure it.

### 4.5 Python libs health (2026-11-14, `[seen]`)
| Lib | Version / date | Notes |
|---|---|---|
| `ccxt` | 4.5.92, 2026-11-04; 44.9k stars; MIT | Fast cadence (4.5.91 on 2026-10-29). Algo-order handling still being patched in Aug-Oct 2026 -> verify stop placement with a canary after every upgrade |
| `binance-sdk-spot` / `binance-sdk-derivatives-trading-usds-futures` | 13.6.0 / 18.3.1, both 2026-11-12 | Official, modular, changelog-tracking; my lean for order-critical paths `[unverified fit]` |
| `binance-connector` (legacy) | 3.13.0, 2026-04-30 | Superseded by the modular SDKs |
| `python-binance` | 1.0.37, 2026-06-08; 7.2k stars | Quiet five months; pass |
| `ccxt.pro` | bundled in ccxt | Whether its user-data stream already uses the post-listenKey WebSocket API: `[unverified]`, test it |

### 4.6 Keys and permissions (Binance FAQ `[fetch-summary]`, https://www.binance.com/en/support/faq/detail/360002502072)
- HMAC keys with unrestricted IP access are **read-only**; to get trading you add an IPv4 restriction, or use a **self-generated Ed25519/RSA key**. **Withdrawal permission requires IP restriction**: never enable it for this bot. Keys created before enabling a Futures account cannot be granted Futures permission. Nautilus docs: HMAC deprecated, RSA unsupported, Ed25519 recommended `[fetch-summary]`.
- Practical: generate Ed25519 keypair locally, register public key, give **Enable Spot & Margin Trading / Enable Futures** only, IP-whitelist the execution host's static IP (a dynamic home IP is awkward; a static VPS egress IP solves it; Sri Lankan ISP specifics `[unverified]`). Use a **dedicated sub-account** with only the trading capital (sub-account support not checked in this FAQ `[unverified]`).

### 4.7 Freqtrade-specific gotchas worth stealing
Freqtrade docs: futures require one-way mode + single-asset mode (it checks, does not change); blacklist `BNB/<stake>` if you pay fees in BNB or the position can become unsellable; do not hand-tune ccxt `rateLimit` `[fetch-summary]` (https://www.freqtrade.io/en/stable/exchanges/). Binance blocks API access by server country (list non-exhaustive); relevant if you consider a VPS location.

### 4.8 One-day spike to decide the Binance library
Place/verify/cancel on Binance Demo: (1) market entry with `closePosition` STOP_MARKET algo order on `MARK_PRICE`; (2) fetch algo order by `clientAlgoId`; (3) kill the process mid-flight and reconcile; (4) spot OCO; (5) user-data stream through a forced disconnect. Pick whichever of ccxt or the official SDK passes with least glue code.

---

## 5. Paper-vs-live gaps and calibrating costs

### 5.1 Binance
- **Demo/testnet:** fills against a synthetic or demo book `[unverified how]`; no real queue position, market impact or latency; funding, borrowing, ADL and liquidation engine behaviour not documented as modelled; monthly resets wipe state, so your local ledger must reconcile on start (guide advice, https://algolab.co.kr/blog/binance-testnet-api-guide-2026).
- **Live-only costs and risks:** taker/maker fees and BNB-discount mechanics; spread and depth slippage (especially alt pairs, stop-market in gaps); **funding** payments every funding interval; partial fills on limit orders; min-notional/lot-size rejections; rate-limit bans (418); WAF 403s; maintenance windows; exchange-side stop trigger on mark vs last price.
- **What demo is good for:** auth/signing, retries/backoff, order-state machine, reconnect and reconciliation drills, kill switch drills, rate-limit handling. Not P&L.

### 5.2 MT5 demo
- Execution mode (Request/Instant/Market/Exchange) determines whether you get requotes (Instant) or market fills at the broker's price (Market) `[fetch-summary]` (https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants); many brokers' demo servers fill internally without touching liquidity providers, so demo slippage/latency is optimistic, and spreads "may be similar but not guaranteed" to match live `[snippet]` (https://www.mql5.com/en/blogs/post/681051 and related; mostly broker blogs and forum posts, low evidential weight). I found nothing reliable on last-look behaviour `[unverified]`.
- Swap (rollover) is symbol-specific (points, currency, or interest modes; triple-swap day) and visible via `symbol_info()`; realised swap shows on deals. Commission per lot is per account type.
- Retcodes you will see live and rarely on demo: requote, price changed/off, reject, no money, market closed, invalid fill mode, invalid stops. Handle each explicitly.

### 5.3 Calibrating costs from micro-live (works for both venues)
1. Record for every order: decision timestamp and mid/last, submit timestamp, ack timestamp, fill price(s) and sizes, fees/commission, spread at submit and at fill, order type, retcode/error codes, funding/swap actually charged.
2. Compute **implementation shortfall** per fill: `(fill - decision_mid) * side` in bps, plus fees, plus funding/swap over hold period. Aggregate per symbol and hour-of-day with median and p90, not mean.
3. Fit the backtest cost model: `cost = half_spread + a * vol * sqrt(size/ADV) + fee + funding`, initialised from live medians; keep p90 as the stress case. Re-fit monthly; flag drift.
4. Trade the **smallest legal size** for 4-8 weeks across the instrument/hour mix you intend to use. Promotion gate: live median cost <= backtest assumption plus tolerance; reject rate and requote rate below thresholds you set in advance.
5. On MT5, run a **demo vs live comparison on the same broker, same minute, same symbol** for a fixed set of micro-lots to estimate the demo-to-live gap, and never reuse demo slippage as a live estimate.

---

## 6. Community findings (what I actually found)

**Reached:** MQL5 forum threads (fetched), Parallels KB, Wine bug list (snippets), GitHub issues (API), HN Algolia (thin), Binance changelogs. **Not reachable / not tried:** Reddit, X, Instagram. Elite Trader, Forex Factory, and Discord were not searched.

**MT5 on Mac/Linux from Python**
- 2022-05 to 2025-04 MQL5 thread: no native path on M1; suggestions were Windows Python under Wine, or a Windows VM with a REST wrapper; the one working report (Intel Mac + VMware Fusion + REST wrapper) found it "faster and more reliable" than running everything natively (https://www.mql5.com/en/forum/425741).
- 2024-12-28 thread: a user asks about Parallels vs Wine vs Rosetta on an M2 Max; replies are second-hand and "no firsthand report of a working setup or of stability over time" (https://www.mql5.com/en/forum/478849).
- 2025-06-09: MT5 5.0.0.3331 would not start after auto-upgrade on macOS 15.5 ("Bad system call"); moderator blamed Wine vs macOS; fix = complete uninstall and reinstall; advice to disable auto-update (https://www.mql5.com/en/forum/488554).
- 2026-05-28 onward: macOS Tahoe 26.5 on M2, MT5 5834 crashes on Buy/Sell; moderator: "highly recommended to have Wine 11.3+ and Windows 11"; Aug 2026 user got build 6116 running on Wine 11.14 but WebView2 runtime missing; no confirmed fix (https://www.mql5.com/en/forum/510357). Search snippets also reference other post-26.5 Wine crashes on M2/M3 `[snippet]`.
- 2025-09-02: moderator says Parallels + Windows 11 ARM works well on M1-M3, native Wine installer "less reliable for intensive trading especially with EAs and DLLs" (https://www.mql5.com/en/forum/494485). Python not discussed. Parallels' own KB (2023-08-10) describes MT4/MT5 launch failures on Windows-on-ARM and an older-build workaround (https://kb.parallels.com/129408/).
- Wine bug tracker and MQL5 Linux threads: MT5 exiting silently after unknown periods on Ubuntu; stability varying by Wine stable/devel/staging; one commenter prefers a VM where stability matters `[snippet]` (e.g. https://www.mql5.com/en/forum/371932, https://list.winehq.org/hyperkitty/list/wine-bugs@list.winehq.org/thread/BYEK6SJZB2AKCCYWZDRVSESCWPDQWQ7U/).
- 2026-10-05: Windows IPC timeout -10005 on builds 6231/6249 (https://www.mql5.com/en/forum/517620).
- 2023-11-07: MetaQuotes DMCA removed ~20 MT4/MT5 bridge and "manager API" repos, including ZeroMQ and JSON-API bridges (link in 2.2). Show HN for `mt5-httpapi` (2026-02-20) drew 1 point and no discussion.

**Binance bots live**
- Freqtrade #12610 (17 comments): since 2025-12-09 stop-loss placement failed with `-4120` on USDⓈ-M futures; #12681: duplicate/orphaned conditional stops from fetch/cancel failures (Docker on macOS host, interval 60 s), closed 2026-01-11 (https://github.com/freqtrade/freqtrade/issues/12610, /12681).
- Nautilus #3287 (same break, closed 2025-12-18), #5377 (futures user-data stream recovery retrying forever on a stale listen key, 2026-10), #5664 (SBE 3:6 break, open) (https://github.com/nautechsystems/nautilus_trader/issues).
- python-binance: #1645 STOP_MARKET not working after the migration; #1668 listenKey deprecation (https://github.com/sammchardy/python-binance/issues).
- HN thread on NautilusTrader (2025-08-06, 208 points): a commenter from a quant firm said the hard part is integration, since the framework's OMS and the broker's OMS may not match; another who traded crypto for six years said standard strategies "failed out of sample" and what worked was structural edge (rebates, latency, arbitrage) (https://news.ycombinator.com/item?id=44810552). Anecdotes, not evidence.
- I did not find documented stories of Binance bots blowing up due to the Mac itself sleeping; the Mac home-server auto-update-then-login-screen failure is documented in a blog `[snippet]` (https://maju-tech.blogspot.com/2026/04/mac-mini-home-server-went-offline-macos.html).

---

## 7. Unattended operation on a Mac: checklist

Observed on this Mac: `sleep 1`, `autorestart 0`, auto-install macOS updates on, Rosetta present.

**Power and sleep**
- [ ] `sudo pmset -a sleep 0` and `sudo pmset -a disksleep 0`; confirm with `pmset -g`. If it is a laptop: keep on AC; closed-lid operation needs an external display or `sudo pmset -a disablesleep 1` `[unverified on 26.5]`. Use `caffeinate -s` only as a backup, not the fix (community guides disagree on caffeinate `[snippet]`).
- [ ] `sudo pmset -a autorestart 1` (restart after power failure). macOS 26.5 reportedly added a separate Energy setting for the same thing, and one M4 mini owner reported pmset autorestart not taking effect; check both and test by pulling power `[snippet]` (https://hometechops.com/mac/mac-mini-auto-power-on-restart-tahoe).
- [ ] FileVault blocks unattended login after a power loss; either disable FileVault on the production host or accept manual unlock and design around it `[snippet]`.
- [ ] UPS if it is a desktop; second uplink (phone hotspot) for the Binance path.

**Updates**
- [ ] Turn off automatic macOS install/restart (Settings > General > Software Update > Automatic updates); schedule monthly maintenance windows with positions flat or fully protected. A macOS update that restarts into the login screen can leave services dead `[snippet]`. Pin Python and library versions; do not run `pip install -U` on the live host.

**Process supervision**
- [ ] Run the engine as a **LaunchDaemon or LaunchAgent with `KeepAlive`**, logging to files with rotation; auto-login if you use LaunchAgents. One process per role (engine, reconciler, alerter), not one giant script.
- [ ] A **deadman/heartbeat** that is *outside* the Mac (a pinging service you control or a third-party free tier `[unverified which]`); alert if the heartbeat stops.
- [ ] Clock: verify NTP sync; Binance rejects timestamps outside `recvWindow` (default 5,000 ms) `[fetch-summary]`.

**Alerting (Telegram bot)**
- [ ] Bot via Telegram Bot API `[unverified, standard]`: alerts for fills, rejects, stop-missing incidents, reconciliation mismatches, heartbeat loss, daily P&L, halt state; commands `/status`, `/halt`, `/flatten` restricted to your chat id with a confirmation word. Alerts must not contain keys or full account numbers.

**Secrets (macOS Keychain)**
- [ ] Store the Binance Ed25519 private key and MT5 gateway token in Keychain (`security add-generic-password`, or Python `keyring`); never in `.env` committed to git; separate demo and live entries and make the process assert which one it loaded. Demo and testnet keys are separate from live keys (https://algolab.co.kr/blog/binance-testnet-api-guide-2026 `[fetch-summary]`).
- [ ] Binance: trade-only, **no withdrawal permission ever**, IP-restricted, dedicated sub-account `[unverified]`, small balance. Rotate keys on a schedule; know how to revoke from your phone.
- [ ] VPS: key-only SSH or Tailscale-only access, no public RDP, Windows firewall locked down, separate non-admin account if feasible, MT5 password unique to this broker account.

**Move to an always-on box?** Decision rule: run on the Mac through the paper phase and log uptime. If measured availability is below about 99% over 30 days, or the Mac is a laptop you travel with, move the engine to a small Linux VPS or a spare Mac mini at home with a UPS. In any case the **MT5 side already lives on the Windows VPS**, and a static VPS egress IP also makes Binance IP whitelisting trivial. Whether your Binance region accepts VPS IPs is a regulation-track question.

---

## 8. Risks and open questions

**Risks**
1. MT5 bridge fragility (IPC timeouts, terminal restarts, Wine regressions). Mitigate with the VPS gateway, watchdog, server-side SL/TP, guardian EA, and no dependence on third-party bridges.
2. Binance API churn. Expect at least one breaking change per quarter (2025-12 conditional orders, 2026-02 listenKey, 2026-03 WS paths, 2026-11 SBE). Mitigate with canary tests and verifiers.
3. Stops that fail silently (orphaned or missing algo orders). Reconciler must alert on both mismatch directions.
4. Costs: retail FX/CFD base rates are poor (master report: 55-80% of CFD accounts lose money); keep turnover low and costs measured.
5. Local-first compromise: Windows VPS holds an MT5 login. Contain with a capital-limited account, gateway hard limits and no LLM or data on it.
6. Wine/Rosetta runway: macOS 28 (fall 2027) reduces Rosetta; any Mac-local MT5 plan may need re-platforming.
7. Third-party tool risk: `siliconmetatrader5`, `meta-trader-mcp`, `mt5-httpapi` are single-maintainer and young; MetaQuotes has used DMCA against bridge repos before.
8. Licence notes: Freqtrade GPL-3.0 (fine privately), Nautilus LGPL-3.0, `siliconmetatrader5` PolyForm Noncommercial (personal use only).

**Open questions for the user / other tracks**
1. Which MT5 broker(s), and do any offer **cTrader** or a REST/FIX API reachable from Sri Lanka? That could remove the Windows layer entirely.
2. Binance access/demo availability and which entity/account type applies in Sri Lanka (regulation agent). Also whether Binance Futures USDⓈ-M is permitted for you.
3. Is the M4 a MacBook or a Mac mini, and is it realistically on 24/7 at a stable-IP location?
4. Account type at the MT5 broker: netting vs hedging, execution mode, min lot, stops level, swap-free option, commission per lot, whether a free broker VPS exists (all `[unverified]`).
5. Whether ccxt.pro or the official SDK handles the post-listenKey user-data stream cleanly (spike in 4.8).
6. Whether NautilusTrader's out-of-tree Python adapter interface (page not read) makes an MT5 adapter a few days rather than weeks; worth one afternoon of reading if you want to keep Nautilus as Plan B.
7. MetaQuotes' own VPS service (page 404 for me) and pricing/limits; MetaApi current pricing and credential model.

---

## 9. Source list (principal)

- MetaTrader5 package: https://pypi.org/project/MetaTrader5/ ; https://www.mql5.com/en/docs/python_metatrader5 ; order_send: https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py ; sockets: https://www.mql5.com/en/docs/network/socketcreate ; constants: https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants
- MetaQuotes Mac install: https://www.metatrader5.com/en/terminal/help/start_advanced/install_mac
- MQL5 forum: 425741, 478849, 488554, 494485, 510357, 517620 under https://www.mql5.com/en/forum/
- Parallels: https://kb.parallels.com/129408/ ; https://www.parallels.com/products/desktop/microsoft-authorized-solution-windows-11-arm/ ; VMware FAQ https://www.vmware.com/docs/desktop-hypervisor-faqs
- Rosetta: https://www.macrumors.com/2025/06/10/apple-to-phase-out-rosetta-2/ ; https://www.macrumors.com/2026/06/12/macos-golden-gate-rosetta-support
- Bridges: https://github.com/bahadirumutiscimen/silicon-metatrader5 ; https://pypi.org/project/siliconmetatrader5/ ; https://github.com/lucas-campagna/mt5linux ; https://github.com/psyb0t/mt5-httpapi ; https://www.pypi.org/project/meta-trader-mcp/ ; https://github.com/github/dmca/blob/master/2023/11/2023-11-07-metatrader.md
- cTrader: https://help.ctrader.com/open-api/ ; https://github.com/spotware/OpenApiPy ; Deriv: https://developers.deriv.com/docs/ ; MetaApi: https://metaapi.cloud/
- Binance: https://developers.binance.com/docs/derivatives/change-log ; https://github.com/binance/binance-spot-api-docs (CHANGELOG, rest-api.md, web-socket-streams.md, testnet/, demo-mode/) ; https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info ; https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order ; https://www.binance.com/en/support/faq/detail/360002502072 ; https://www.binance.com/en/fee/schedule ; https://www.binance.com/en/support/faq/detail/9be58f73e5e14338809e3b705b9687dd
- Frameworks: https://nautilustrader.io/docs/latest/integrations/ ; https://nautilustrader.io/docs/latest/integrations/binance/ ; https://nautilustrader.io/docs/latest/concepts/live/ ; https://nautilustrader.io/docs/latest/developer_guide/adapters/ ; https://www.freqtrade.io/en/stable/ ; https://github.com/hummingbot/hummingbot ; https://github.com/HKUDS/Vibe-Trading ; https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages
- Issues: freqtrade #12610, #12681; nautilus_trader #3287, #5664, #5377; python-binance #1645, #1668; ccxt #31078
- HN: https://news.ycombinator.com/item?id=44810552 ; https://news.ycombinator.com/item?id=47089440
- Mac unattended: https://hometechops.com/mac/mac-mini-auto-power-on-restart-tahoe ; https://maju-tech.blogspot.com/2026/04/mac-mini-home-server-went-offline-macos.html
- Package stats: GitHub API and PyPI JSON queried 2026-11-14.
