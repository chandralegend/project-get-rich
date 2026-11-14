# Phase 3 findings: meta-labelling result and the agent layer

Date: 2026-11-14. Two parts: the pre-registered meta-label experiment (a null result), and the Claude agent layer (built, tested, and run live for the first time on the same day, see sections 2 and 4). The last section assesses the Agent SDK and subscription ideas.

## 1. Meta-labelling the trend rule: not shown

Pre-registered in [preregistration-meta-label.md](preregistration-meta-label.md) before running. Its SHA-256 was logged as an `eval.preregistered` event first, and the run checks the file still matches. Full table: [phase3-meta-results.md](phase3-meta-results.md).

| | Sharpe | at 2x costs | gain vs primary alone at 2x | Max DD | Excess R per entry | Deflated Sharpe | Null p |
|---|---:|---:|---:|---:|---:|---:|---:|
| meta: linear | 0.28 | 0.10 | -0.56 | 30% | -0.080 | 0.46 | 0.74 |
| meta: LightGBM | 0.65 | 0.47 | -0.20 | 28% | +0.037 | 0.75 | 0.39 |
| meta: fusion net | 0.10 | -0.10 | -0.76 | 39% | -0.108 | 0.29 | 0.95 |
| primary rule alone | 0.68 | 0.66 | n/a | 44% | n/a | 0.79 | n/a |

**No model meets any of the three pre-registered criteria** (a Sharpe gain of at least 0.10 at 2x costs, a permutation p below 0.05, a Deflated Sharpe of at least 0.90). The primary rule alone beat all three at 2x costs. The Deflated Sharpe here is deflated against 17 trials (every variant tried in Phases 1 to 3), tracked in [trials.json](trials.json).

Two honest notes. First, the LightGBM filter ended with about the same Sharpe as the rule alone (0.65 against 0.68) and a smaller drawdown (28% against 44%), but it earned half the return (11% against 22% a year) because it simply held less. That is de-risking, not skill, and the permutation test agrees (p = 0.39). I mention it because it is the kind of result that is easy to over-read. It was not one of the pre-registered criteria and I am not claiming it. Second, power was limited, as the pre-registration said: only edges of roughly 0.15 R per trade or more could be detected, so this is "no detectable edge of that size", not "no edge".

Together with Phase 2, this is two designs on the same price-and-volatility features with no detectable edge, which matches the earlier research.

## 2. The agent layer (built, tested, first live runs in section 4)

What exists, all under `src/getrich/llm/` and `src/getrich/agents/`:

| Piece | What it does |
|---|---|
| Local pre-filter | Drops near-duplicate news (word 3-gram similarity over 48 hours) and items with no market-relevant term, before any API call. On the 40 oldest real items it would drop 10 and send 30. |
| Haiku extraction | One item in, one schema-validated event out, appended to the hash-chained ledger with the item as evidence. |
| Sonnet briefing | Recent events plus a market snapshot in; a briefing, risk flags and shadow views out, written to the ledger and to `data/briefings/`. Skips the API call entirely when there are no usable events. |
| Outcome scoring | Resolves shadow views and risk flags against closed daily bars after their horizon, with fixed rules, and reports counts next to hit rates. |
| Spend cap | Every call is refused before the network if it could pass the monthly cap (default $30). Spend is read back from the event log. The watchdog raises a P1 at 80% and at the cap. |

Safeguards, each covered by tests with a fake SDK (nothing here has spent any money):
- **No tools, no sampling parameters, no prefill, no forced tool choice** in any request. Responses use structured outputs and are validated again locally. A refusal, truncation, invalid JSON or schema failure is logged and stored as failed, never trusted.
- **Untrusted text** is cleaned, length-limited and wrapped in delimiters it cannot forge. Obvious injection phrases are flagged and recorded. A test feeds a hostile item and checks that only schema fields are stored and the request carried no tools.
- **Second-order injection:** the briefing model sees summaries that Haiku wrote from web text, so any item flagged as suspicious is withheld from it entirely.
- **Evidence discipline:** the briefing can only cite item ids it was shown. Flags and views must cite at least one. The ledger itself refuses unknown evidence and look-ahead.
- **Dry runs** make no API call and leave no trace. The estimated cost for 30 real items is under one cent.

Costs, by my arithmetic from the published prices: Haiku extraction about $0.0003 per item, a Sonnet briefing about $0.02 to $0.03. Even a busy month is a few dollars, well inside the $30 cap.

**Not done, and why:**
- No real API call has been made. Add `ANTHROPIC_API_KEY=...` to `.env` (a key made just for this project, with a spend limit set in the Claude Console), run `uv run getrich agents-extract --dry-run`, then without `--dry-run`. Only then install the jobs with `ops/launchd/install.sh install-agents`.
- Embeddings and a sentiment model are not in the pre-filter yet, because the model downloads are large on this connection. They are needed for the Phase 2b text channel, not for this layer.
- The trade journal (role 2) has nothing to review until trades exist.
- Only central-bank feeds are collected. Crypto news feeds are excluded until their terms on storage and LLM use are read, so crypto-specific events (listings, hacks, stablecoin stress) are mostly invisible to the agents for now.
- A real-API run could still fail on request details I could not test, for example a parameter combination the live API rejects. The fake SDK tests prove my code, not the API's behaviour.

## 3. Your Agent SDK and subscription ideas

**What the docs say** (code.claude.com, read today):
- The Agent SDK is Claude Code as a library: it bundles the Claude Code binary and runs on your machine, with built-in tools to read, write and edit files, run shell commands and search the web.
- Permissions are evaluated in a fixed order: hooks, deny rules, ask rules, the permission mode, allow rules, then a `canUseTool` callback. A locked-down headless setup pairs `allowedTools` with `permissionMode: "dontAsk"`. Built-in tools can be hidden entirely with `tools` or `disallowedTools`. `allowedTools` does not constrain `bypassPermissions`.
- Custom tools are ordinary functions wrapped in an in-process MCP server (`@tool` and `create_sdk_mcp_server` in Python), named `mcp__<server>__<tool>`. A `readOnlyHint` annotation is metadata, not enforcement.
- It loads `.claude/` settings, skills and memory from the project and from `~/.claude/` by default, so a headless agent would need those pinned explicitly or it inherits your Claude Code environment.
- Authentication: the quickstart tells you to use an API key, and lists Bedrock, Vertex and Foundry as alternatives.

**On the subscription.** The legal page says OAuth sign-in is "intended exclusively" for subscription purchasers and "designed to support ordinary use of Claude Code and other native Anthropic applications". It says developers building products or services with the Agent SDK "should use API key authentication", and it bars third parties from routing users through plan credentials. It also says the advertised limits for Pro, Max and Ultra "assume ordinary, individual usage of Claude Code and the Agent SDK", and that nothing prevents a user from signing in to the unmodified Claude Code binary with their own subscription.

My reading, which is not legal advice: those restrictions target people offering Claude access to others, so your own personal use probably isn't what they aim at. But nothing affirmatively permits an unattended, scheduled agent on subscription credentials either, the page steers SDK use to API keys, and Anthropic reserves the right to enforce without notice. For an automated agent that has real risk (account action) and for a project whose rule is a hard spending cap there is a practical cost too: a subscription has usage windows, not per-token billing, so the cap in `budget.py` could not enforce anything, and the agent would draw on the same limits as your interactive Claude Code use. Anthropic's own page points to contacting sales for questions about permitted methods.

A split that stays clearly inside "ordinary use": scheduled unattended runs use an API key and the hard cap; anything you start yourself in an interactive Claude Code session (research, reviewing a briefing, ad hoc analysis) uses your subscription as normal.

**On the agent idea itself.** A research agent that can search the web and run analysis could find things the curated pipeline cannot, and it fits the "agents" role you chose. The costs are real: an agent loop with web content spends far more tokens than a one-shot call (by my rough arithmetic, tens to hundreds of thousands of input tokens per investigation, so fractions of a dollar to a dollar or so each), and web content is the worst-case untrusted input with tools attached. My recommendation is to add it as a separate, shadow-only "Investigator" next to the curated pipeline, not instead of it:
- tools limited to web search and fetch plus a few vetted read-only functions over our own data (no shell, no file writes, no Claude Code settings, no connectors);
- every tool call logged to the event log by a hook, per-run turn and cost limits, and a daily cap;
- fetched pages saved as timestamped news items so insights can cite them and be audited;
- final output a validated, typed insight written to the ledger and scored by the same scorecard, so it earns trust only if its forward results show lift.

I recommended the Messages API with server-side tools as the simpler option; you chose the Agent SDK, locked down, so that is what is built.

## 4. The Investigator (Agent SDK, locked down)

`uv run getrich investigate "<question>" [--max-usd 0.75] [--max-turns 15] [--dry-run]`. Code: `agents/investigator.py`, `investigator_policy.py`, `investigator_tools.py`.

**What the agent can do:** `WebSearch`, `WebFetch`, and three read-only functions over our own data (`get_snapshot`, `get_returns`, `get_events`, BTC and ETH only, bounded output). Nothing else exists for it.

**How it is contained** (three layers that do not depend on the model behaving):
1. *Availability:* `tools=["WebSearch","WebFetch"]`, so no shell, file or edit tools are loaded, plus an explicitly empty working directory.
2. *Permissions:* `dontAsk` mode with an exact allow list, every other built-in on the deny list, `setting_sources=[]`, `strict_mcp_config`, an empty Claude config directory, auto-memory off, claude.ai connectors off. Your `~/.claude`, skills, plugins and MCP servers are not inherited.
3. *Hooks in our process, before every call:* an exact tool allowlist; fetch URLs must be https, a normal hostname, no credentials, no non-standard port, no IP addresses, no local names, query string under 120 characters (so data cannot be smuggled out in a URL); per-run limits of 10 fetches and 8 searches. Every call, allowed or denied, is logged as an event.

**Evidence and trust:**
- Every fetched page is stored as a timestamped news item (source `web:<host>`), hidden from the curated extractor. The agent can only cite pages it actually fetched or event refs the events tool returned.
- A page containing injection phrases is flagged, the agent gets a warning, and that page can never be cited. Events our pipeline flagged as suspicious are withheld from the agent entirely.
- Output is a JSON schema, validated again locally. A citation that was not fetched rejects the whole run, and its cost still counts.
- Results go to the hash-chained ledger with `source: "investigator"`, so `agents-status` scores it separately from the briefing (`scorecard.by_source`). It earns trust only if its forward results show lift. It is shadow-only and cannot affect any order.

**Cost controls:** at most 3 runs a day, $0.75 and 15 turns per run, and the monthly cap check before it starts. The SDK's own budget limit is a client-side estimate that can overshoot, so if a run reports no cost it is charged the full per-run cap rather than zero.

**Verified:** 48 tests with a scripted fake agent that calls the real registered hooks (URL rules, allowlist, limits, evidence capture, injection handling, citations, failure and cost paths, lockdown options). The real SDK (0.2.182) also accepted these options and returned only an authentication error for a deliberately bogus key, so the option names and the empty config directory are accepted by the real binary.

**First live runs (2026-11-14, API key added):**
- *Extraction:* 85 real news items sent through Haiku, 33 events recorded, 0 failures, about $0.0002 per item, matching the estimate.
- *Briefing:* Sonnet, $0.021. The first call was rejected because a risk flag cited no evidence, so the rule changed: an individual flag or view that cites nothing, or cites something the model was not shown, is now dropped and counted (`dropped_ungrounded`) instead of discarding the whole briefing. Every other validation failure still rejects it. The briefing said plainly that the news did not explain the BTC and ETH sell-off. One flag it kept cites an event that is only loosely about its claim, which is a reminder that "has a citation" is not "is supported".
- *Investigator:* two runs. The first ($0.047) was rejected because the agent cited its own price-snapshot output; the prompt now says market-tool output is context, not a citation, and uncited items are dropped like the briefing's, except that citing a page flagged as hostile still rejects the whole run. The second ($0.100, 6 fetches, 2 searches, 0 denied calls) recorded 8 insights: it read crypto outlets, noticed the two outlets disagreed on whether the Fed had already hiked, said no primary source (Fed, BLS, CME) was among the pages, and listed what it could not settle. It returned no views. Whether any of this is right is for the scorecard to say, not for me.
- *Now verified against the real SDK:* the model loads and calls our market tools under the allowlist, `WebSearch` works (its input also carries a `mode` key), and the capture hook receives the `WebFetch` result as text under `url`.
- *Found and fixed:* a failed fetch (HTTP 403) arrives as ordinary text and was being stored as a page. Failed fetches are now skipped and logged as `investigator.fetch_failed`. One such row from the first live run is in `news_items` (source `web:www.fastcompany.com`); it is harmless but listed under that run's pages.

**Caveats that matter:**
- `WebFetch` returns a model-written extract of the page, not the raw text. What is stored as evidence is that extract, one layer removed from the source, and it can be stale (one fetched article was dated June 2025). Treat investigator evidence as secondary.
- The agent's sources were secondary outlets that disagreed with each other. It said so, which is the good behaviour, but its findings are unverified until scored.
- A run costs roughly $0.05 to $0.10 so far, well under the $0.75 limit. Total live spend today: about $0.20.

**Subscription:** this job needs an API key (see section 3). Using it inside your own interactive Claude Code sessions is separate and unaffected.

## Reproduce

```bash
uv run getrich run-meta                      # the pre-registered experiment (about 10 minutes)
uv run getrich agents-extract --dry-run      # what the extraction would do and cost
uv run getrich agents-briefing --dry-run
uv run getrich agents-status
uv run pytest                                # 232 tests, none of which call the real API
```
