# Binance terms review

Read on 2026-11-14. This is an engineering reading of the documents, not legal advice. Terms change without notice, so re-read them before real money moves and about once a quarter after.

## What was read

| Document | Version | How it was read |
|---|---|---|
| [Terms of Use](https://www.binance.com/en/terms) (74-page PDF) | Effective 27 Oct 2026 | Searched for API, automation, conduct, eligibility, data and licence clauses. The whole text was not read. |
| [API Key Terms](https://www.binance.com/en/about-legal/terms-binance-api) (6 pages) | v2.0, effective 9 Jul 2026 | Read in full. |
| [Binance Vision dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md) | Updated 26 Aug 2026 | Read earlier (see ARCHITECTURE.md). |

Not read: the current List of Prohibited Countries, the Spot and Futures product terms, fee schedules, and the endpoint-level API documentation (rate limits and fair use).

Both agreements are written for Binance's Abu Dhabi (ADGM) entities, and the Terms of Use say "Local Terms" may supplement them. I could not tell from the documents which entity or local terms apply to a Sri Lankan account.

## Findings

1. **Automated trading is allowed.** The Terms of Use say Binance provides technology for "constructing automated trading systems", as is, and takes no responsibility for how they run. API access is "subject to separate API terms and our approval" (clause 14.1.2). The API Key Terms let you create several keys with different permissions (clause 2.1).
2. **Conduct rules.** The API Key Terms forbid market manipulation, insider trading, front running, pump and dump, wash trading and spoofing (clause 3.2(h)). The Terms of Use let Binance act on suspected "Improper Intent", which includes market abuse. A slow daily strategy is far from this, but the engine must never produce behaviour that looks like wash trading (self-trades) or spoofing (placing and quickly cancelling orders).
3. **You carry the risk.** You are liable for every order placed with your keys, whoever placed it (clause 2.5). Binance may revoke or disable a key at any time without notice (clause 6) and may amend the API Key Terms without notice (clause 10).
4. **Key handling.** Clause 4 lists what Binance expects: one key per purpose, no unnecessary permissions, delete unused keys, use an IP allowlist, never put keys in public repositories, and do not store keys "in cloud-based venues". It recommends an RSA key pair.
5. **Eligibility and legality.** You must not be in a jurisdiction where it would be illegal under applicable law for you to use Binance, or on the List of Prohibited Countries (Terms of Use clause 2.1(f); API Key Terms clause 9.3). Sri Lanka is not named anywhere in the Terms of Use. The current Prohibited Countries list was not re-read today (the research agent read a version dated 5 Jan 2026). The first limb connects to your own legal question, and I take no view on it.
6. **Third-party tools.** If you give keys to an order-management provider, it may add fees that Binance collects for it (clause 2.6). Do not hand keys to third-party bots.
7. **Reusing market data is not addressed.** Neither agreement explicitly covers storing public market data from unauthenticated endpoints. The API Key Terms limit use of "API related data" broadly (clauses 3.1, 3.2(b) and (e)), but they govern API keys, and the collector uses no key. The Vision files are the explicit case: personal backtesting only, no live trading use. Collecting public klines for personal research looks reasonable but is not confirmed. For certainty, ask Binance support in writing.

## What this changes in the project

| Change | Where |
|---|---|
| Risk gate gets a **conduct guard**: self-trade prevention, a minimum order lifetime, and a cap on the cancel-to-fill ratio | ARCHITECTURE.md 4.4 |
| **Local-only key storage.** macOS Keychain can sync to iCloud, which would count as a cloud venue. Use a local-only keychain or a file with `0600` permissions, never iCloud Keychain | Phase 4 |
| **Separate keys** for any read-only use and for trading, trade-only, no withdrawal permission | Phase 4 |
| **IP allowlist caveat.** If your home IP changes, an allowlist breaks. Check whether your ISP gives a stable address, or route trading through a VPS with a fixed IP | Phase 4 |
| **Never give keys to third parties**, and never commit them (the repo is public; `.env` is gitignored) | Always |
| **Assume keys can vanish.** Server-side stops stay on the exchange, and the engine must handle a revoked key as an incident | Phase 4 |
| **Re-check the terms** about quarterly and before going live; record the version dates above | Operations |

## Open questions

- Which Binance entity and local terms apply to your account, and is Sri Lanka on the current Prohibited Countries list?
- Does Binance accept Ed25519 keys? The terms only recommend RSA. Check in the API Management screen.
- Do the futures product terms differ for Sri Lankan residents?
- Is storing public market data for model training acceptable? Ask support if it matters to you.
