# News feed terms review (2026-11-14)

Question: may a private individual's local research tool poll a public RSS feed, store the headline and short summary, and send that text to an LLM API to classify it? Each site's own terms, robots file and feed were read by a research helper on 2026-11-14 (page text, not memory). This is a reading of published text, not legal advice. Terms change, so re-read before relying on any of it.

## Decision

Collect only sources whose own text permits copying. Do not collect crypto news outlets. A public RSS feed is not a licence, and four of the five outlets prohibit automated access or copying in their terms.

## Crypto news outlets: not collected

| Outlet | Feed | Verdict | What decides it |
|---|---|---|---|
| CoinDesk | `coindesk.com/arc/outboundfeeds/rss/` works | Prohibited as written | Terms bar a "robot, spider, scraper, or other automated means" without written permission. Its robots file also disallows `ClaudeBot` and `anthropic-ai`. |
| Cointelegraph | `cointelegraph.com/rss` works | Prohibited | Terms bar "automated scraping" and use of content in the "operation of artificial intelligence systems" without written consent. |
| Decrypt | `decrypt.co/feed` works | Prohibited as written | Terms name RSS feeds as a covered service and bar automated collection and caching without written consent. |
| The Block | `theblock.co/rss.xml` works | Prohibited | Terms bar "systematic or automated data collection" and processing content "using artificial intelligence or machine learning". Its robots file says the opposite (`ai-input=yes`), but the terms are the stricter text. |
| Bitcoin Magazine | `bitcoinmagazine.com/feed` works | Unclear | The terms page is an unfinished template (the governing-law clause still reads "[Insert Jurisdiction]") and says nothing on scraping or AI. Excluded rather than assumed. A footer link points to `b.tc/terms`, which was not read. |

Consequence: crypto-specific events (listings, hacks, stablecoin stress) are still mostly invisible to the extractor. The Investigator can read those outlets when it fetches a page for a single question, which is a different act from bulk collection, but its output should be treated as secondary evidence. If crypto coverage matters, the routes that remain are a licensed news API, an outlet's written permission, or primary sources (exchange announcements, regulator releases).

## Primary sources: collected

| Source key | Feed | Reuse text | Notes |
|---|---|---|---|
| `fed.press` | `federalreserve.gov/feeds/press_all.xml` | Public domain, cite the Board (`federalreserve.gov/disclaimer.htm`) | Already collected. |
| `fed.speeches` | `federalreserve.gov/feeds/speeches.xml` | Same | The testimony feed is sparse and has placeholder dates (1899), so it is not collected. Placeholder dates are now ignored for every feed. |
| `ecb.press`, `boe.news` | as before | Read in Phase 0 | Unchanged. |
| `boc.press` | `bankofcanada.ca/content_type/press-releases/feed/` | May be freely used, copied, distributed, attribution required (`bankofcanada.ca/terms/`) | Do not circumvent request limits. Polling once an hour or less is far inside that. |
| `boj.news` | `boj.or.jp/en/rss/whatsnew.xml` | May be copied with the source credited, except for commercial use (`boj.or.jp/en/about/copyright.htm`) | Headlines only, and many items are statistics files, which the pre-filter drops. Content may not be altered, and only titles are stored. |
| `sec.press` | `sec.gov/news/pressreleases.rss` | Public information that may be copied, cite the SEC (`sec.gov/privacy.htm`) | Off by default. The SEC asks automated clients to declare a User-Agent with contact details and says it does not allow "unclassified" bots. It turns on only when `GETRICH_CONTACT` is set in `.env`, and the contact string is sent to the SEC only. Limit is 10 requests per second. |

## Not collected: no usable feed

- **CFTC:** no working RSS feed (the listed URL returns an empty filter page). Its robots file sets `ai-train=no` and disallows `ClaudeBot`.
- **Treasury and OFAC:** email alerts only, no feed. No reuse statement was found, so public-domain status is unconfirmed.

## Gaps in this review

- The Fed's and BoJ's robots files return 404, so their robots rules are unknown. Their copyright pages permit copying.
- Attribution is required by most of these sources. Stored items keep their source key and URL, and the briefing and Investigator reports name the source.
- Storing a short summary and sending it to an LLM for classification is not addressed by any of the primary-source texts. The reuse statements are broad (copy and distribute), and this is personal, non-commercial use, but it remains your call.
