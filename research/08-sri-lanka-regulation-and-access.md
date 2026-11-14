# 08 - Sri Lanka regulation, funding and access (Binance + MT5 + cTrader)

Date: 2026-11-14. Track scope: legal/regulatory position, tax, Binance access, MT5 and cTrader broker access, scam risks, community, for a Sri Lankan resident trading for personal use. **This is factual research, not legal, tax or investment advice.** No accounts were opened, no forms submitted, no trades placed.

Evidence tags: **[seen]** = I read the primary page/PDF text myself this session; **[snippet]** = only a web-search summary of the page, not read in full; **[secondary]** = news, law-firm, review or affiliate site; **[unverified]** = could not confirm.

---

## 1. TL;DR

1. **Binance is accessible to Sri Lankan residents in practice.** Binance's own "List of Prohibited Countries" (updated 5 Jan 2026) names only the US, Canada, Netherlands, Cuba, North Korea, Iran and occupied Ukrainian regions; Sri Lanka is not on it [seen, rendered the PDF]. Local-currency access is via **P2P bank transfer / eZ Cash / mCash** because Sri Lankan bank cards are barred from crypto by CBSL Direction No. 3 of 2021 [seen via CBSL 29 Mar 2023 release; FactCrescendo 8 Aug 2026].
2. **Crypto position: grey but not prohibited.** CBSL says crypto is not legal tender, unlicensed and unprotected, but has not banned holding or investing; the Governor said in Sept 2025 there is no legal barrier to investing because no specific law covers it. A VASP regime (SEC as regulator) is being drafted (Cabinet, 27 Jul 2026). Nothing enacted yet.
3. **Forex/CFD trading with offshore brokers (the MT5/cTrader plan) is the legally worse-positioned leg.** CBSL's public notice of 21 Oct 2019 says a person in or resident in Sri Lanka is "not permitted" to undertake forex trading or remit funds abroad for it, and that doing so is a **violation of the Foreign Exchange Act (FEA)** [seen, full text extracted]. No CBSL notice since then withdraws or softens that, and I found no reported prosecution of an individual retail trader (absence of evidence, not a safe harbour). Broker "Sri Lanka is legal" claims on affiliate sites are marketing and carry no regulatory weight.
4. **Funding is the practical choke point.** Rupees cannot freely be converted and sent abroad for investment: Regulations No. 1 of 2026 (gazette 2493/36, 18 Jun 2026) let resident individuals convert rupees for overseas investment **only into employer share plans (ESOP/ESOS)** [seen]. A resident's Personal Foreign Currency Account (PFCA) can remit abroad for capital transactions up to **USD 25,000** under the s.22 Order of 18 Jun 2026, valid six months from 20 Jun 2026 (so expires about 20 Dec 2026, expect a re-issue) [seen]. Whether a broker deposit counts as a "capital transaction" is my inference, not stated in the Order.
5. **Biggest risks, ranked:** (a) FEA exposure for offshore forex/CFD and for rupee-to-offshore flows via P2P/crypto (CBSL can penalise; Cabinet approved in principle on 18 Aug 2026 to re-criminalise "serious" FX violations, aimed mainly at import-payment fraud, individual scope unclear); (b) bank-account freezes when P2P counterparties are scammers or mule accounts; (c) offshore-entity broker risk (Seychelles/Belize/Bahamas/Vanuatu regulators, no Sri Lankan recourse); (d) tax ambiguity on crypto and trading profits; (e) scam ecosystem around WhatsApp/Telegram "AI trading".
6. **For this project:** backtest and paper trading carry zero regulatory exposure and can be fully built (Binance Spot Testnet, broker demo accounts, free data). Treat live trading as gated on written confirmation from a Sri Lankan accountant/lawyer and, ideally, CBSL's Department of Foreign Exchange (questions in section 9). A conservative live path is **crypto spot on Binance with money that never came from a rupee-to-offshore conversion**, small size, with records; offshore CFD/forex is the part CBSL has explicitly flagged.

---

## 2. Regulatory findings (source, date, stance)

| # | Source | Date | Stance | Tag |
|---|---|---|---|---|
| 1 | CBSL "Notice to the Public: Unauthorized Foreign Exchange Trading" https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/press/notices/notice_20191021_unauthorized_foreign_exchange_trading_e.pdf | 21 Oct 2019 (from file name; body undated) | **Prohibition asserted + warning.** Licensed banks (ADs) may deal in FX under FEA; "any other person in, or resident in Sri Lanka is not permitted" to undertake forex trading, remit funds abroad for it, or receive profits; no permission granted for ADs to facilitate; engaging is a FEA violation; CBSL may act against both promoters and participants. Complaints to Dept of Foreign Exchange (dfe@cbsl.lk). | seen |
| 2 | CBSL press release on illegal forex trading (reported by Finance Magnates, 31 May 2012; file press_20120530) | 30/31 May 2012 | Under the old Exchange Control Act (repealed by FEA 2017), unapproved forex trading and remitting for it was a "punishable offence". Historical; shows consistent stance. | seen (Finance Magnates page) |
| 3 | CBSL "Public Awareness on Virtual Currencies" https://www.cbsl.gov.lk/en/news/public-awareness-on-virtual-currencies-in-sri-lanka | 16 Apr 2018 | Warning. No licence/authorisation to any virtual-currency scheme or ICO; "significant risks". | seen |
| 4 | CBSL "Risks of using and investing in Cryptocurrency" https://www.cbsl.gov.lk/en/news/risks-of-using-and-investing-in-cryptocurrency-20230329 | 29 Mar 2023 | Warning, **no blanket ban**. Not legal tender, not an asset class recognised in Sri Lanka, no licensed exchanges/custody/mining; debit/credit cards may not be used for crypto under **Directions No. 03 of 2021 (FEA)**; crypto via informal channels can drain FX reserves. | seen |
| 5 | CBSL press, Aug 2023 "Public complaints on unlawful pyramid schemes" https://www.cbsl.gov.lk/en/node/15008 | 24 Aug 2023 | Warning: schemes falsely claim CBSL approval; CBSL denies. | seen |
| 6 | CBSL FIU notice "Protecting the public from crypto investment scams" (PDF notice_20240114) | 14 Jan 2024 | Warning; names entities breaching Banking Act s.83C. | snippet |
| 7 | CBSL Governor Weerasinghe, Ada Derana https://www.adaderana.lk/news.php?nid=112860 ; Sunday Times 28 Sep 2025 | 24 Sep 2025 | Crypto cannot be used for payments; **investing has no legal barrier because no law covers it**; "can be held as an asset"; VASPs to register with FIU/CBSL. | seen |
| 8 | Gazette 2493/36, Regulations No. 1 of 2026 (Overseas Investments by Residents) https://dfe.lk/web/images/rdevelopment/1e053526afc012cd3d06e03a8270234c-2493-36-E.pdf | 18 Jun 2026 | Rescinds Regs No. 1 of 2021. Resident individuals (excl. emigrants/non-nationals) may convert rupees for overseas investment **only in overseas ESOP/ESOS**. Nothing on trading/crypto/derivatives. | seen |
| 9 | Gazette 2493/38, Order under s.22 FEA https://dfe.lk/web/images/rdevelopment/f7da0aaf5dc576c2c00b6d9d21909da0-2493-38-E.pdf | 18 Jun 2026; valid 6 months from 20 Jun 2026 | Outward remittances on **capital transactions through PFCAs capped at USD 25,000** (or equivalent); Outward Investment Account payments suspended except named corporate/ESOP cases; BFCA cap USD 500,000. Prior orders: USD 20,000 PFCA cap (2023-2025 [secondary]); Dec 2025 order 2467/67 [snippet] showed USD 25,000. | seen |
| 10 | Colombo Chief Magistrate, Rs 290m fraud via Binance accounts (Daily Mirror) https://www.dailymirror.lk/breaking-news/Court-warns-funds-leaving-Sri-Lanka-through-Cryptocurrency/108-335172 | 13 Mar 2026 | Court said FEA loopholes let money leave via crypto; directed CBSL/CID to raise awareness and act to prevent similar frauds "through Binance platforms". No new restriction reported. Binance replied 17 Mar 2026 (cooperating; issue is specific users) https://www.dailymirror.lk/print/front-page/Binance-responds-to-cryptocurrency-allegations/238-335533 | seen |
| 11 | Daily FT, "Govt to bring back criminal sanctions for FX violations" https://www.ft.lk/top-story/Govt-to-bring-back-criminal-sanctions-for-FX-violations/26-795053 ; newswire.lk 18 Aug 2026 | 24 Jul 2026; Cabinet policy approval reported 18 Aug 2026 | Plan to amend FEA so "serious" offences (fraud, false documents, fake import advance payments, ~USD 715m case) are criminal again; procedural breaches stay civil. Article does not mention individuals, trading or crypto. No bill text found. | seen (FT); snippet (newswire) |
| 12 | Cabinet approval of VASP regime, Daily FT https://www.ft.lk/front-page/Cabinet-backs-legal-framework-to-regulate-virtual-asset-service-providers/44-795284 | 29 Jul 2026 (Cabinet met 27 Jul) | **SEC Sri Lanka** to be regulator, coordinated with CBSL, FIU, IRD. Notes Sri Lankans use offshore exchanges and P2P outside any framework. Does not say crypto is illegal. | seen |
| 13 | Sunday Times "New law to register, report, tax virtual assets" https://www.sundaytimes.lk/260906/business-times/new-law-to-register-report-tax-virtual-assets-655629.html | 6 Sep 2026 | Drafting instructed; "mandatory registration, reporting standards and taxation mechanisms"; aims to close P2P/offshore compliance gap; local banks face restrictions on direct crypto transactions; no deadlines. | seen |
| 14 | Prevention of Money Laundering (Amendment) Bill bringing VASPs into AML law; third FATF mutual-evaluation prep (Daily FT, Sunday Times, Mar-Oct 2026) | Mar-Oct 2026 | Interim AML step; no licensing regime yet. | snippet |
| 15 | SEC Sri Lanka scam alerts: Blue Ocean Securities/BOMate (Nov 2025), Gladius South Asia (Dec 2025), Evolute (Jun 2026) | Nov 2025-Jun 2026 | Warnings about unlicensed platforms; CID complaint filed in Blue Ocean case. | snippet |

**What is NOT clear (grey areas):**
- Whether CBSL's 2019 "forex trading" language covers **CFDs on metals, indices, crypto**, or only spot currency trading. Brokers' retail products are typically CFDs; the notice does not define the term.
- Whether the notice is enforced against individual retail clients of offshore brokers. I found no reported case; I did not search court records.
- Whether depositing from a PFCA to a broker is a "capital transaction" counted against the USD 25,000 cap, or whether profits repatriated back to a PFCA are "income from forex trading" the 2019 notice says residents may not receive.
- Whether P2P rupee-to-USDT purchases (an effective rupee-to-offshore transfer) are treated by CBSL as FEA breaches for individuals. The March 2026 magistrate's remarks suggest the system sees it as a loophole, not as lawful.
- The IMF programme: I did not research IMF capital-flow measures this session. **[gap]**
- The 2023 card direction text itself was not read; I rely on CBSL's own 2023 release quoting it.

---

## 3. Tax notes (not tax advice)

- **Framework:** Inland Revenue Act No. 24 of 2017, amended by Act No. 2 of 2025 (certified 20 Mar 2025, effective 1 Apr 2025) and Act No. 11 of 2026 (certified 3 Jun 2026) [KPMG US Tax Newsflash https://kpmg.com/us/en/taxnewsflash/news/2026/06/sri-lanka-tax-amendments-enacted.html - seen].
- **Personal relief** LKR 1.8m from Y/A 2025/26; first slabs 6% then 18% (KPMG) [snippet/secondary]. Check current slab table.
- **Capital gains tax:** 15% for individuals/partnerships from 3 Jun 2026 (was 10%); covers investment "capital assets" incl. securities and financial assets; resident individuals exempt up to LKR 50,000 per asset and LKR 600,000 per year of total gains (Daily FT column https://www.ft.lk/columns/Capital-Gains-Tax-takes-sharp-turn-What-Sri-Lanka-s-new-2026-rates-mean-for-investors/4-797664 - seen). The column does not say crypto or forex/CFD gains are covered.
- **Foreign-source income:** Act No. 2 of 2025 removed a prior exemption for foreign-source/foreign-service income; a 15% concessionary rate for foreign-currency income remitted through a bank is described by KPMG/IRD notice PN/IT/2025-01 (26 Mar 2025) [secondary via search summary; I did not read the Act]. It is not established that trading gains qualify.
- **Crypto:** No crypto-specific tax rules. An opinion column by a tax practitioner (Daily FT, 23 Jun 2026, https://www.ft.lk/columns/Financial-frauds--Why-crypto-tax-enforcement-is-Sri-Lanka-s-strongest-weapon/4-793689 - seen) says the IRD works on the premise crypto is an "intangible asset" (CGT) or trading profit depending on circumstances, with no IRD circular cited, no place on the return to disclose crypto, and few people reporting. KPMG's head of tax said on 21 Nov 2025 Budget 2026 had no crypto tax provisions and a law amendment is needed (Daily Mirror https://www.dailymirror.lk/business/No-provisions-for-taxing-cryptocurrencies-in-Budget-2026-says-tax-expert/215-325611 - seen). The pending VASP law is meant to add "taxation mechanisms".
- **Record-keeping implication:** keep per-trade exchange/broker statements, deposit/withdrawal proofs, USD/LKR rates on the date, source-of-funds evidence (for banks and for FEA), and your own timestamped ledger. The project's append-only trade ledger doubles as tax evidence.
- **For an accountant to confirm:** classification of CFD/forex/crypto gains (capital vs trading income vs "other income"), applicable rate (15% CGT vs slab rates vs foreign-source rate), whether losses can offset, how to disclose offshore accounts on the return, and whether a TIN is now needed for bank/exchange onboarding (Act 11 of 2026 makes TIN verification mandatory for specified transactions from 1 Apr 2026).

---

## 4. Binance access findings

| Item | Finding | Source / tag |
|---|---|---|
| Supported jurisdiction | Sri Lanka **not** on Binance's prohibited list (US, Canada, Netherlands, Cuba, North Korea, Iran, Crimea/DNR/LNR) | Binance PDF updated 5 Jan 2026 [seen; page https://www.binance.com/en/about-legal/list-of-prohibited-countries renders the PDF] |
| Ban rumour | Claim that Binance/Bybit were "banned" in Sri Lanka rated Misleading; no law prohibits trading on them; not on the Aug 2026 gambling blocklist | FactCrescendo 8 Aug 2026 https://srilanka.factcrescendo.com/english/?p=20042 [seen] |
| KYC | Binance requires KYC; Sri Lanka-specific document list not confirmed | [unverified; do not sign up] |
| LKR routes | P2P is the main route; bank transfers and mobile wallets (eZ Cash, mCash). Bybit runs a rupee P2P too. Cards barred (Directions No. 3 of 2021). No direct bank deposit of rupees. | FactCrescendo [seen]; CBSL 2023 [seen] |
| Freezes | No documented wave of bank freezes of ordinary P2P traders found. Binance's own help text says P2P sellers had accounts frozen when buyers were scammed elsewhere and reported it [snippet]. Sri Lankan banks freeze and blacklist accounts used as mule accounts (Sunday Times 13 Sep 2026 https://www.sundaytimes.lk/260913/business-times/digital-scammers-exploit-lankans-through-bank-accounts-656351.html [seen]). | mixed |
| Legal-enforcement context | Rs 290m fraud case via Binance accounts, magistrate urged action (Mar 2026); 19 suspects bailed | Daily Mirror [seen] |
| API | Production API restrictions specific to Sri Lanka: none found, not confirmed [unverified]. Spot Testnet: https://testnet.binance.vision ; REST `https://testnet.binance.vision/api`, WS `wss://stream.testnet.binance.vision`; virtual funds only; `/api` endpoints only (no `/sapi`); resets roughly monthly; no country restriction mentioned on the docs page | developers.binance.com testnet general-info [seen]; Sri Lanka access to the testnet itself not tested |
| Futures/derivatives | Binance's prohibited list is account-level and does not carve out derivatives for Sri Lanka. A separate per-country futures restriction list could not be found on Binance's site; aggregator lists do not name Sri Lanka. Whether futures are enabled for a Sri Lankan account is **[unverified]**; confirm in-app before designing around perps. | Binance PDF [seen]; datawallet (27 Jul 2026) [secondary] |
| Banks/accounts | Local banks restricted on direct crypto transactions (Sunday Times 6 Sep 2026) | [seen] |

**Design implications:** use the Spot Testnet for execution-layer development. For live, expect P2P onboarding of funds (counterparty and bank-freeze risk; use only your own named bank account; never lend your account). Keep P2P ad counterparties' details and chat/records.

---

## 5. MT5 broker comparison (Sri Lanka)

Method: official footers/legal pages read via a browser tab; no sign-up flows touched. "Sri Lanka supported" = whether the broker's own pages or restricted-country text exclude or include Sri Lanka. **No MT5 broker states "Sri Lankan clients are accepted via entity X" on a page I could read.** The country dropdown at registration is the real test (not done; no sign-ups).

| Broker | Sri Lanka | Entities seen (regulator) | Min deposit | Instruments | EA / API | Funding from SL | Notes |
|---|---|---|---|---|---|---|---|
| **Exness** | Not named restricted. Footer: no services to USA, Iran, North Korea, EU, UK "and others". Help-centre lists show Sri Lanka for Trade app and affiliate availability [snippet]. Verdict: **likely Y, not confirmed** | Exness (SC) Ltd (Seychelles FSA SD025); Exness B.V. (Curacao CBCS); Exness (VG) Ltd (BVI FSC); Exness (BZ) Ltd (legal-docs page). Which one serves SL not stated; (SC) is commonly cited [secondary] | $10 Standard / $200 Pro [secondary, conflicting] | FX, metals, indices, stocks, crypto CFDs [secondary] | EAs on MT4/MT5 desktop (help centre [seen]); Exness VPS; "API Terms of Use" document exists | Local banks, cards, Skrill/Neteller, USDT [secondary]; help centre says methods depend on registered region | Not CBSL-licensed [secondary]. https://www.exness.com/legal-documents/ ; help centre https://get.exness.help |
| **XM** | Sinhala-language site exists (https://www.xm.com/si/), restricted territories listed: USA, Canada, Israel, Iran (plus sanctioned). Sri Lanka appears in referral/loyalty terms [snippet]. **Likely Y** | XM Global Ltd (Belize FSC, licence 8557558) named on the Sinhala page; group also has CySEC, DFSA, FSCA, FSA Seychelles, FSC Mauritius, BVI entities (regulation page [seen]). Entity serving SL not stated | $5 [secondary] | FX, metals, indices, stocks, commodities (1,400+ assets claimed) | Client agreement not readable (403) [unverified] | Not found | Offshore entity |
| **IC (IC Markets Global, now ic.com)** | Restricted: USA, Canada, Iran, North Korea "such as"; SL not named. Listed under Sri Lanka in cTrader directory. **Likely Y** | Raw Trading Ltd, Seychelles FSA SD018 [seen on ic.com] (rebranded to ic.com Jul 2026 per cTrader news) | $0 on cTrader directory; MT5 minimum [unverified] | FX, metals, indices, commodities, crypto, shares (2,850+ instruments claimed) | Site states over two-thirds of trades are automated; EAs OK in practice; terms [unverified] | Not found | Seychelles regulator |
| **Pepperstone** | International site entity Pepperstone Markets Ltd, Bahamas SCB SIA-F217 [seen]; no named restrictions on the page; listed under Sri Lanka in cTrader directory | Bahamas for international clients [seen]; also ASIC, FCA, CySEC, DFSA, CMA Kenya entities | $0 (directory) | FX, indices, commodities, shares, crypto | Algorithmic tools; cTrader Automate | Not found | Retail loss disclosure: 80-82% lose money |
| **FP Markets** | Excludes Afghanistan, Cuba, Iraq, Iran, Liberia, Libya, Myanmar, Palestine, Russia, Somalia, Syria, Sudan, Yemen, USA, EEA, FATF/EU/UN-list jurisdictions; SL not named [seen]. Listed under Sri Lanka in cTrader directory | FP Markets Ltd (St Lucia, site operator); First Prudential Markets Ltd (Seychelles FSA SD130); ASIC, FSCA entities | $100 (directory) | 10,000+ instruments claimed | Open to EAs [unverified] | Not found | |
| **FBS** | Excludes USA, EU, UK, Israel, India, Iran, Myanmar; SL not named [seen]. Listed on affiliate sites [secondary] | FBS Markets Inc, Belize FSC | $1 [secondary] | FX, metals, indices, energies, stocks, crypto | [unverified] | Not found | Third-party reviews flag red flags (BehindMLM) [snippet]; treat with caution |
| **Deriv** | Sinhala site exists (https://deriv.com/si); no restricted list read; terms say service only to residents of certain countries [snippet]. Listed under Sri Lanka in cTrader directory | Deriv (BVI) Ltd, Deriv Investments (Cayman), Deriv (Mauritius), Deriv (V) Vanuatu, Deriv Investment Bank (Labuan) etc. (footer [seen]) | $5 (cTrader directory) | FX, metals, indices, stocks, crypto, derived (synthetic) indices | MT5 and cTrader; Deriv API exists | Deriv P2P and payment agents exist [snippet] | Synthetic indices are not market-derived: unsuitable for the project's market-edge work |

**Other MT5-capable names** appear in comparison sites (Tickmill, HFM, Vantage, etc.) but I did not verify them. Equities/ETF CFD breadth, swap-free (Islamic) accounts and per-pair XAUUSD/EURUSD spreads were **not verified** for any broker; compare on the broker's live spread page and demo account. Spread claims on affiliate pages should be ignored.

Entity caution (applies to all): non-EU/UK clients are generally served by offshore entities (Seychelles, Belize, Bahamas, Vanuatu, BVI, Curacao). The 2019 CBSL notice says CBSL has not authorised any bank to facilitate forex trading for residents; none of these brokers is regulated in Sri Lanka and Sri Lankan regulators have no jurisdiction to compel withdrawals.

---

## 6. cTrader brokers (added at coordinator's request)

**Why it matters:** cTrader's Open API is cross-platform (any language; JSON or Protobuf; official SDKs in C# and Python), so it avoids the Windows-only MT5 Python package. Spotware's docs say the API is "supported by all trading accounts of any cTrader-affiliated brokers", so **in principle any live or demo account at a cTrader broker can use it with a cTrader ID** (https://help.ctrader.com/open-api/ , seen 14 Nov 2026). Rate limits per connection: 50 non-historical and 5 historical requests per second. Broker-level contractual limits on automated trading, scalping or news trading are in each broker's client agreement and were **not verified** for any broker.

**Country-filtered directory evidence:** cTrader's own directory https://ctrader.com/brokers?country=LK (Sri Lanka filter) listed **52 brokers**, versus 39 for `?country=JP`, so the filter genuinely varies by country [seen 14 Nov 2026]. The directory disclaims verifying regulatory status. Brokers shown for Sri Lanka include FxPro (flagged "Local choice"), Fusion Markets ("Local choice"), IC, Deriv, BlackBull, FP Markets, GO Markets, Pepperstone, TradeView Markets, Blueberry, Axiory, Purple Trading, FP Trading, Opo Finance, FIBO, APFX and a long tail of small brokers. **Skilling, Exness and XM did not appear in the list of 52** (Skilling is not a Sri Lanka-listed cTrader broker on this evidence).

| Broker | Listed for Sri Lanka on cTrader directory | Entity/regulator that serves Sri Lankans | Min deposit (directory) | Commissions / spreads seen | Funding from SL | cTrader Open API / cBots |
|---|---|---|---|---|---|---|
| **FxPro** | Yes ("Local choice") | Directory regulators: FCA UK, SCB Bahamas (+1). Entity for SL not stated; FxPro site says offerings depend on residence and entity; CFDs not offered in USA, Iran, Canada [seen] | $100 | FX $3.5/side/lot; metals/gold $35 per $1M/side; "from 0.2 pips". Directory shows headline max leverage 1:30 but table 1:1000 FX / 1:200 metals: inconsistent, **verify**. XAUUSD/EURUSD live spreads unverified | Not found [unverified] | API per Spotware yes; "Cloud cBots" badge; broker T&C [unverified] |
| **Fusion Markets** | Yes ("Local choice") | International: Gleneagle Securities Pty Ltd trading as Fusion Markets (Vanuatu VFSC, co. 40256); Fusion Markets International Ltd (Seychelles FSA SD096) [seen on fusionmarkets.com]. SL not in its excluded list (Afghanistan, Congo, Iran, Iraq, Japan, Myanmar, NZ, N. Korea, Russia, Spain, Ukraine, USA, etc.) | $0 | FX/metals $2.25/side; "from 0.0 pips"; leverage table 1:30 FX (likely a regulated-entity default) vs headline 1:500 | Not found; directory flags crypto deposits generally | As above; cloud cBots badge |
| **IC (IC Markets Global)** | Yes | Raw Trading Ltd, Seychelles FSA SD018 [seen]; also ASIC, CySEC entities for other clients | $0 | $3/side per 100k FX/metals (Raw); "from 0.0 pips"; leverage FX/metals 1:500, indices/commodities 1:200 | Not found | Automated trading is explicitly promoted on ic.com; copy trading, cloud cBots badge |
| **Pepperstone** | Yes | Pepperstone Markets Ltd, Bahamas SCB SIA-F217 for international [seen]; directory also lists ASIC, CySEC, FCA, DFSA; which one serves SL is **unverified** | $0 | Razor: $3/side FX; "from 0.0 pips"; headline leverage 1:30 vs 1:500 table (inconsistent) | Not found | cTrader Automate; algorithmic section on site; broker T&C unverified |
| **FP Markets** | Yes | FP Markets Ltd (Saint Lucia); First Prudential Markets Ltd (Seychelles FSA SD130); ASIC, CySEC, FSCA, CMA entities (directory) | $100 | Raw $3/side; metals/gold $3/side; leverage 1:500 FX/metals | Not found | Cloud cBots badge |
| **Deriv** | Yes | Multiple offshore entities (BVI, Vanuatu, Labuan, Mauritius, Cayman) [footer seen]; SL entity not stated | $5 | Zero commission, spread-only; leverage 1:200 FX/metals | Not found | cTrader + MT5; synthetic indices not relevant |
| **BlackBull** | Yes | Directory shows FMA New Zealand only; entity actually serving non-NZ clients **unverified** | $0 | $3/side FX/metals | Directory flags crypto deposits | cloud cBots badge |
| **GO Markets** | Yes | Multiple (CySEC, FSC Mauritius, ASIC, FSA Seychelles, FSA St Vincent, +4) | $0 | from 0.1 pips; $2.5/side GO Plus+ | Not found | cloud cBots badge |
| **Skilling** | **Not seen** in Sri Lanka filter | n/a | n/a | n/a | n/a | n/a |

Not verified for any cTrader broker: XAUUSD and EURUSD average spreads (the directory shows only "from 0.0 pips" marketing and commissions), funding routes from Sri Lanka (local banks, Skrill, Neteller, USDT), whether the Sri Lankan-facing entity restricts scalping/EAs/API, and swap-free availability. Do a read-only check of each short-listed broker's client agreement and funding page for "Sri Lanka" and "algorithmic/automated trading", and test spreads on a demo cTrader account (demo has no regulatory exposure).

**Practical read:** for macOS-first development, cTrader brokers listed for Sri Lanka with zero or low minimum and raw-spread accounts (IC, Pepperstone, Fusion, FP Markets) fit best; all are offshore-entity relationships for Sri Lankan clients, so the 2019 CBSL notice applies equally to all of them.

---

## 7. Scam checklist and verification

**Patterns reported in Sri Lanka**
- WhatsApp/Telegram/Facebook "signal" or "AI trading" groups; Sri Lanka Police listed crypto/forex investment scams on Telegram and Facebook among nine online-fraud categories (Jan 2026) and warned about Telegram/WhatsApp scams (Oct 2025, May 2026) [snippet].
- Fake trading apps and unlicensed "securities firms": SEC alerts on Blue Ocean Securities/BOMate (Nov 2025, CID complaint), Gladius South Asia (Dec 2025), Quantum AI, Evolute (Jun 2026) [snippet].
- Pyramid/Ponzi schemes: MTFE (Metaverse Foreign Exchange; collapsed Aug 2023, CBSL probe, travel bans) [Sunday Times 27 Aug 2023, snippet]; OnmaxDT (CBSL concluded Banking Act breach, directors remanded Nov 2023, US accounts frozen) [snippet]; Sports Chain crypto scheme (Rs 8bn allegation, 2022) [snippet].
- CBSL warned that schemes claim CBSL approval or tax compliance falsely (24 Aug 2023) [seen].
- Mule accounts: people recruited to "receive commissions"; accounts used to move fraud money into crypto; permanent blocking and blacklisting of ID documents (Sunday Times 13 Sep 2026) [seen].

**Checklist**
1. No guaranteed or fixed returns, "AI robot" claims, or pressure from unsolicited contacts; no one else managing your account or holding your login.
2. Never lend, rent or "receive for" your bank account or P2P ads.
3. Verify the regulator on the **regulator's own register** (FSA Seychelles, Belize FSC, Bahamas SCB, ASIC, FCA etc.), match the exact legal-entity name on your client agreement to the register, and confirm the entity serving Sri Lanka. Offshore licences give weak protection.
4. Check SEC Sri Lanka alerts and the IOSCO I-SCAN database (https://www.iosco.org/i-scan/) for the name. CBSL publishes no list of "approved forex brokers" because none is authorised.
5. Withdrawal red flags: requirement to pay "tax" or "fees" to withdraw (CBSL says this is a scam pattern), withdrawal only via a different method than deposit without explanation, bonuses with trading-volume lock-ins, delayed KYC after profit, sudden "account upgrade" fees.
6. Test with a small deposit and a small withdrawal before sizing up.
7. Keep records; report fraud to CERT, CCID or the CBSL Department of Foreign Exchange (dfe@cbsl.lk).

---

## 8. Community findings

What I could and could not access:
- **Reddit (r/srilanka), Facebook groups, X, Telegram, TikTok, Instagram:** not accessed. Web search surfaced no r/srilanka threads; I did not try to open Reddit directly (earlier tracks reported it blocked). **No first-hand Sri Lankan trader posts were obtained.**
- **News/analysis seen:** Sunday Times (5 Oct 2025) describes inflation and rupee weakness pushing young professionals and small business owners to crypto as a store of value, mostly through offshore exchanges and P2P, estimating over 320,000 Sri Lankan holders (South Asian Journal of Finance estimate), and quotes a financial lawyer that users have no legal protection if funds vanish [seen]. Daily Mirror (snippet) says the SEC chief noted younger people are drawn to global crypto platforms outside local protection. FactCrescendo (8 Aug 2026) says Binance P2P is the most-used feature in Sri Lanka.
- **Broker affiliate/review pages** (comparebroker.io, issuu "Exness legal in Sri Lanka" docs, daytrading.com/lk, tradersunion) are marketing; discard for legal or availability claims. No independent first-person Sri Lankan withdrawal experiences were found; the single first-person account found was a non-Sri Lankan forum post about Skrill/Neteller.

---

## 9. Questions to confirm (CBSL / accountant / broker)

**CBSL Department of Foreign Exchange (dfe@cbsl.lk) or a Sri Lankan lawyer**
1. Is the 21 Oct 2019 notice still CBSL's current position for a resident individual trading CFDs/forex with an offshore broker using money already in a PFCA?
2. May a PFCA remit funds abroad to a broker or exchange within the USD 25,000 capital-transaction cap, and may profits be credited back?
3. Are P2P rupee-to-crypto purchases treated as FEA breaches for the buyer, or only when proceeds leave the country?
4. Does the Cabinet-approved criminalisation (Aug 2026) reach individual overseas payments?
5. After the 20 Dec 2026 expiry, what replaces the s.22 Order?

**Accountant**
6. Tax classification and rate for crypto, CFD and forex gains; loss treatment.
7. How to disclose offshore broker/exchange accounts and PFCA balances on the return; whether a TIN is needed.
8. Record formats the IRD accepts.

**Broker/exchange (written, via support chat saved as a record)**
9. Which legal entity serves a Sri Lankan-resident client, and under which regulator?
10. Are EAs, cBots, Open API and scalping permitted on that entity's accounts?
11. Which deposit and withdrawal methods are available for Sri Lanka; same-method withdrawal rules; fees.
12. Binance: is Futures enabled for Sri Lanka-resident accounts; is API trading enabled on a new account?

---

## 10. Open gaps

- IMF programme capital-flow provisions not researched.
- Binance Futures availability for Sri Lanka, Sri Lanka KYC document rules, and API availability for new Sri Lankan accounts not confirmed from an official page.
- Binance and several broker pages needed a real browser; Exness help pages and XM/Deriv terms PDFs were partly blocked (403), so entity-per-country mappings and EA/scalping clauses are unverified.
- Spreads (XAUUSD, EURUSD), swap-free terms and Sri Lanka-specific funding methods unverified for all brokers.
- The Jan 2024 CBSL FIU crypto notice, the Dec 2025 s.22 Order, the Jun 2025 order, SEC alerts and PMLA amendment status are snippet-only.
- Tax: I did not read the Acts; foreign-source rate and crypto treatment rely on secondary sources.
- No court or enforcement-record search for individual FEA actions over forex/crypto; no first-hand community evidence.

## 11. Sources (all seen 2026-11-14)

CBSL: notice_20191021 PDF (text extracted) ; https://www.cbsl.gov.lk/en/news/public-awareness-on-virtual-currencies-in-sri-lanka ; https://www.cbsl.gov.lk/en/news/risks-of-using-and-investing-in-cryptocurrency-20230329 ; https://www.cbsl.gov.lk/en/node/15008 . DFE gazettes: https://dfe.lk/web/index.php?option=com_rdevelopment&task=allgazettes&Itemid=483&lang=en (2493/36, /37, /38 PDFs). News: Daily FT 24 Jul, 29 Jul, 2026; Sunday Times 5 Oct 2025, 28 Sep 2025, 6 Sep 2026, 13 Sep 2026; Daily Mirror 13 Mar, 17 Mar, 21 Nov 2025; Ada Derana 24 Sep 2025; FactCrescendo 8 Aug 2026; Finance Magnates (2012 release). Binance: prohibited-countries PDF (5 Jan 2026), testnet docs. Brokers: xm.com regulation page and /si, exness.com legal documents and help centre, ic.com, fpmarkets.com, fbs.com, fusionmarkets.com, pepperstone.com/en, fxpro.com, deriv.com, ctrader.com/brokers?country=LK and per-broker pages, help.ctrader.com/open-api. Tax: KPMG US Tax Newsflash (Jun 2026), Daily FT CGT column, Daily FT crypto-tax column (23 Jun 2026), Daily Mirror 21 Nov 2025.
