"""Pipeline 1 - Daily Direct-Growth NAVs from AMFI: the target fund, every fund in the AMFI 'Mid Cap Fund' category
(peers + skill-vs-luck universe), and MOAMC index funds used as TRI proxies.

Source: AMFI (amfiindia.com). Terms of use (checked 2026-10-15): personal, non-commercial use permitted; robots.txt
disallows only /admin, /login, /search.
  * Scheme list + categories: https://portal.amfiindia.com/spages/NAVAll.txt
  * History: https://www.amfiindia.com/api/nav-history?query_type=historical_period&from_date=..&to_date=..&sd_id=<code>
    (the request made by AMFI's own NAV-history page). Range must be < 5 years -> 1-year chunks; 1 request/second;
    the server takes ~6 s per request, so a full rebuild takes ~40 minutes.
The API returns only the plan whose code is sent, so each scheme's Direct-Growth code is taken from NAVAll (or probed
when NAVAll leaves plan/option blank). Kept: plans named 'Direct' that are not IDCW/dividend/bonus.
Outputs: data/processed/nav_daily.csv, data/processed/midcap_category_schemes.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> p3config

import json
import re

import pandas as pd

from p3config import AMFI_CATEGORY, FUND, PROXY_CODES, RAW, TODAY, RateLimiter, cached_get, log, save_processed

API = "https://www.amfiindia.com/api/nav-history?query_type=historical_period&from_date={f}&to_date={t}&sd_id={c}"
NAVALL = "https://portal.amfiindia.com/spages/NAVAll.txt"
FIRST_YEAR = 2013  # Direct plans exist from 1-Jan-2013


def direct_growth(nav_name: str) -> bool:
    """Direct plan, not an income-distribution/bonus option ('Growth' is often omitted, e.g. '... - Direct Plan')."""
    return bool(re.search(r"direct", nav_name, re.I)) and not re.search(r"idcw|dividend|bonus|payout|reinvest", nav_name, re.I)


def category_schemes(text: str) -> pd.DataFrame:
    rows, cat = [], None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"Open Ended Schemes\s*\((.*)\)", line)
        if m:
            cat = m.group(1).strip()
            continue
        p = line.split(";")
        if len(p) >= 8 and p[0].isdigit():
            rows.append({"code": int(p[0]), "isin": p[1], "name": p[3].strip(), "plan": p[4], "option": p[5], "category": cat})
    return pd.DataFrame(rows)


def main() -> None:
    lim = RateLimiter((1, 1.0))
    text = cached_get(NAVALL, RAW / "amfi" / f"NAVAll_{TODAY}.txt").decode("utf-8", errors="replace")
    allf = category_schemes(text)
    mid = allf[allf["category"] == AMFI_CATEGORY]
    codes = {}
    for name, g in mid.groupby("name"):
        dg = g[g["plan"].fillna("").str.contains("direct", case=False) & g["option"].fillna("").str.contains("growth", case=False)]
        if len(dg):
            codes[int(dg["code"].iloc[0])] = name
            continue
        for c in g["code"]:  # plan/option blank in NAVAll: probe one recent quarter and read the plan name
            d = json.loads(cached_get(API.format(f="2026-01-01", t="2026-03-31", c=c), RAW / "amfi" / "probe" / f"{c}.json", limiter=lim))
            if direct_growth(" ".join(x.get("nav_name", "") for x in (d.get("data") or {}).get("nav_groups", []))):
                codes[int(c)] = name
                break
    codes.update({c: f"index-fund proxy {k}" for c, k in PROXY_CODES.items()})
    log("p01_nav", "universe", f"{AMFI_CATEGORY}: {len(codes) - len(PROXY_CODES)} schemes (Direct-Growth codes) + {len(PROXY_CODES)} index-fund proxies")
    save_processed(mid, "midcap_category_schemes")
    out, missing = [], []
    for code, name in codes.items():
        got = 0
        for y in range(FIRST_YEAR, int(TODAY[:4]) + 1):
            f, t = f"{y}-01-01", min(f"{y}-12-31", TODAY)
            d = json.loads(cached_get(API.format(f=f, t=t, c=code), RAW / "amfi" / "hist" / f"{code}_{y}_{t}.json", limiter=lim))
            for g in (d.get("data") or {}).get("nav_groups", []):
                if direct_growth(g.get("nav_name", "")):
                    for r in g.get("historical_records", []):
                        out.append({"amfi_code": code, "scheme": name, "nav_name": g["nav_name"], "date": r["date"], "nav": r["nav"]})
                        got += 1
        if not got:
            missing.append(name)
    df = pd.DataFrame(out)
    df["date"] = pd.to_datetime(df["date"])
    n0 = len(df)
    df = df.drop_duplicates(["nav_name", "date"]).sort_values(["nav_name", "date"])
    bad = df[df["nav"] <= 0]
    df = df[df["nav"] > 0]
    log("p01_nav", "clean", f"dedupe (nav_name,date); dropped {len(bad)} non-positive NAVs {bad[['nav_name', 'date']].astype(str).values.tolist()}; "
        f"no Direct-Growth found for {missing}", n0, len(df))
    df["role"] = df["amfi_code"].map(lambda c: "target" if c == FUND["amfi_code"] else ("tri_proxy" if c in PROXY_CODES else "category_peer"))
    df["proxy"] = df["amfi_code"].map(PROXY_CODES)
    save_processed(df, "nav_daily")


if __name__ == "__main__":
    main()
