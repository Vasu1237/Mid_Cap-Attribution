# Data sources, access terms and proxies

Checked 2026-10-15. Each pipeline script's docstring repeats the details relevant to it.

| Data | Source | Terms / access | Script |
|---|---|---|---|
| Daily NAVs: fund, all AMFI "Mid Cap Fund" schemes, MOAMC index funds | AMFI: `portal.amfiindia.com/spages/NAVAll.txt` (scheme list), and `www.amfiindia.com/api/nav-history?...&sd_id=<code>` (the request AMFI's own NAV-history page makes) | Terms permit personal, non-commercial use. robots.txt disallows only /admin, /login, /search. Sent at ≤1 request per second; the server takes ~6 s each; ranges under 5 years | `pipeline/p01_amfi_nav.py` |
| Monthly portfolios of the fund and the Nifty Midcap 150 index fund (ISIN, AMFI industry, quantity, value, % NAV, TER, turnover, AUM, stated benchmark) | motilaloswalmf.com > Downloads > Scheme Portfolio Details (SEBI-mandated monthly disclosure). File list from the site's document API | robots.txt allows all crawlers. **I couldn't read the written terms (the legal-disclaimer page doesn't render).** 181 month-end files at 1 request/second; fortnightly reports skipped | `p02`, `p03` |
| ISIN master (to map old ISINs after splits and renames) | Upstox public instrument files `assets.upstox.com/market-quote/instruments/exchange/{NSE,BSE}.json.gz` | Public file, no token | `p04` |
| Daily stock prices for every holding | Upstox v3 historical-candle API | Needs a personal API token. Documented limits 50/s, 500/min, 2,000/30 min; the script uses 5/s, 450/min, 1,900/30 min | `p05` |
| Four factors + risk-free rate | IIMA Indian Fama-French-Momentum library (survivorship-bias-adjusted monthly file, release pinned in `p3config.py`) | Free; cite Agarwalla, Jacob & Varma (2013) | `p06` |

## Proxies (state these in any write-up)
- **Benchmark TRI.** niftyindices.com forbids automated collection without written consent, so I use the NAV of the **Motilal Oswal Nifty Midcap 150 Index Fund (Direct)**. That equals the TRI minus its TER (~0.2–0.3% a year) and tracking error. It starts Sep 2019, so the benchmark-relative tests start Oct 2019.
- **Benchmark weights and sectors** come from that index fund's monthly holdings: 150 stocks, with AMFI industries.
- **Style indices:** Nifty 50, Nifty Next 50, Nifty 500 and Smallcap 250, all via MOAMC index-fund NAVs (from Sep/Dec 2019).
- **Stock returns are price returns**, without dividends. This applies to both the fund and the benchmark side of the Brinson calculation. The benchmark's holdings-based return trails its NAV by ~0.6% a year, which is about its dividend yield.
- **Sectors:** 78 AMFI industry labels (renamed over the years) rolled up into 10 sectors by my own judgement, listed in `analysis/a_common.py`. Attribution splits depend on the grouping; totals don't.
- **ISIN changes:** after face-value splits, old portfolio ISINs are mapped to the live ISIN with the same 9-character issuer prefix, but only when the mapping is unique and the names agree. Two documented renames are added explicitly. The full table is `data/processed/isin_remap.csv`.
- **Risk-free rate after Dec 2025** (where IIMA ends): the last value is carried forward in the benchmark-relative tests.
- **Survivorship:** the peer universe is the AMFI Mid Cap category *as of the snapshot date*. Merged or closed schemes are absent.
