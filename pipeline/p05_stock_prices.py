"""Pipeline 5 - Monthly stock returns for every security held by the fund or the benchmark proxy.

Source: Upstox v3 historical-candle API (daily, split/bonus-adjusted, NOT dividend-adjusted -> price returns).
  https://api.upstox.com/v3/historical-candle/{NSE_EQ|BSE_EQ}|{ISIN}/days/1/{to}/{from}
  Needs env var UPSTOX_ACCESS_TOKEN (personal, expires daily). Upstox limits: 50/s, 500/min, 2000/30min; we use
  5/s, 450/min, 1900/30min. <= 10 years per request -> 2 chunks per ISIN. ~420 ISINs -> ~20-40 minutes.
Seed mode (used to build the committed snapshot): `--local-prices FILE.csv` (columns date, isin, close) reads daily
  closes from a CSV previously downloaded from the same Upstox endpoint instead of calling the API.
ISIN changes: portfolios carry the ISIN valid at the time; after a face-value split the ISIN changes (e.g. Coforge
  INE591G01017 -> INE591G01025) and Upstox keeps the whole history under the new ISIN. An unpriced ISIN is mapped to a
  live ISIN (data/processed/isin_master.csv) with the same 9-character prefix (issuer + equity security type) ONLY if
  exactly one exists and the first word of the company names agrees, or via the documented RENAMES below.
  Everything else stays unpriced (delisted/merged) and its weight is reported.
Return month m = close(last trading day of m) / close(last trading day of m-1) - 1 (NaN across missing months).
Outputs: data/processed/stock_returns_monthly.csv, isin_remap.csv, price_coverage.csv; adds `isin_priced` to
  holdings_monthly.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> p3config

import argparse
import json
from pathlib import Path

import pandas as pd

from p3config import RAW, TODAY, RateLimiter, cached_get, log, processed, save_processed, upstox_token

URL = "https://api.upstox.com/v3/historical-candle/{key}/days/1/{to}/{frm}"
CHUNKS = [("2013-01-01", "2022-12-31"), ("2023-01-01", TODAY)]
# Corporate renames where the name test legitimately fails (same issuer prefix; live ISIN confirmed in Upstox master)
RENAMES = {"INE591G01017": "INE591G01025",  # NIIT Technologies -> Coforge
           "INE466L01020": "INE466L01038"}  # IIFL Wealth Management -> 360 ONE WAM


def first_word(s) -> str:
    return str(s).upper().replace("THE ", "").split()[0] if isinstance(s, str) and s.strip() else ""


class ApiPrices:
    def __init__(self) -> None:
        self.hdr = {"Authorization": f"Bearer {upstox_token()}", "Accept": "application/json"}
        self.lim = RateLimiter((5, 1.0), (450, 60.0), (1900, 1800.0))
        self.cache: dict[str, pd.DataFrame] = {}

    def get(self, isin: str) -> pd.DataFrame:
        if isin in self.cache:
            return self.cache[isin]
        out = pd.DataFrame(columns=["date", "close"])
        for seg in ("NSE_EQ", "BSE_EQ"):
            fr = []
            for frm, to in CHUNKS:
                try:
                    d = json.loads(cached_get(URL.format(key=f"{seg}%7C{isin}", to=to, frm=frm),
                                              RAW / "upstox" / "candles" / f"{seg}_{isin}_{frm}_{to}.json", self.hdr, self.lim))
                except Exception:  # noqa: BLE001 - invalid instrument key for this segment
                    fr = []
                    break
                c = d.get("data", {}).get("candles", [])
                if c:
                    fr.append(pd.DataFrame({"date": pd.to_datetime([x[0][:10] for x in c]), "close": [x[4] for x in c]}))
            if fr:
                out = pd.concat(fr).drop_duplicates("date")
                break
        self.cache[isin] = out
        return out


class LocalPrices:
    def __init__(self, path: Path) -> None:
        self.px = {}
        for ch in pd.read_csv(path, usecols=["date", "isin", "close"], parse_dates=["date"], chunksize=2_000_000):
            for i, g in ch.groupby("isin"):
                self.px.setdefault(i, []).append(g[["date", "close"]])
        self.px = {i: pd.concat(v) for i, v in self.px.items()}

    def get(self, isin: str) -> pd.DataFrame:
        return self.px.get(isin, pd.DataFrame(columns=["date", "close"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local-prices", type=Path, help="CSV (date, isin, close) from the same Upstox endpoint")
    args = ap.parse_args()
    src = LocalPrices(args.local_prices) if args.local_prices else ApiPrices()
    mode = f"local file {args.local_prices.name}" if args.local_prices else "Upstox API"
    H = pd.read_csv(processed("holdings_monthly"), parse_dates=["month_end"])
    if "isin_priced" in H:
        H = H.drop(columns=["isin_priced"])
    master = pd.read_csv(processed("isin_master")).drop_duplicates("isin")
    master["prefix"] = master["isin"].str[:9]
    names = H.drop_duplicates("isin").set_index("isin")["name"]
    prices, rows = {}, []
    for isin in sorted(H["isin"].unique()):
        p = src.get(isin)
        if len(p):
            prices[isin] = p
            continue
        if isin in RENAMES:
            cand, how = RENAMES[isin], "documented rename"
        else:
            c = master[(master["prefix"] == isin[:9]) & (master["isin"] != isin)]
            ok = len(c) == 1 and first_word(c["name"].iloc[0]) == first_word(names.get(isin))
            cand = c["isin"].iloc[0] if ok else None
            how = "prefix+name" if ok else ("ambiguous" if len(c) > 1 else ("name mismatch" if len(c) else "none"))
        if cand is not None:
            q = src.get(cand)
            if len(q):
                prices[cand] = q
            else:
                cand, how = None, how + " (no prices for mapped ISIN)"
        rows.append({"isin_reported": isin, "name": names.get(isin), "isin_priced": cand, "match": how})
    remap = pd.DataFrame(rows)
    log("p05_prices", "isin_remap", f"source={mode}; {len(remap)} ISINs without own price history; remapped "
        f"{remap['isin_priced'].notna().sum()}; rule: unique same-prefix live ISIN with matching first name word, or RENAMES")
    save_processed(remap, "isin_remap")
    H["isin_priced"] = H["isin"].map(dict(zip(remap["isin_reported"], remap["isin_priced"])))
    H.loc[H["isin_priced"].isna() & H["isin"].isin(list(prices)), "isin_priced"] = H["isin"]
    px = pd.concat([v.assign(isin=k) for k, v in prices.items()]).sort_values(["isin", "date"])
    m = px.groupby(["isin", px["date"].dt.to_period("M")])["close"].last().reset_index()
    m["ret_m"] = m.groupby("isin")["close"].pct_change()
    gap = m.groupby("isin")["date"].diff().apply(lambda x: x.n if pd.notna(x) else 1)
    m.loc[gap > 1, "ret_m"] = None
    m["month_end"] = m["date"].dt.to_timestamp("M")
    save_processed(m[["month_end", "isin", "close", "ret_m"]], "stock_returns_monthly")
    cov = H.assign(p=H["isin_priced"].notna()).groupby(["role", "month_end"]).apply(
        lambda g: (g["weight_nav"] * g["p"]).sum() / g["weight_nav"].sum(), include_groups=False).rename("priced_weight_share").reset_index()
    log("p05_prices", "coverage", "mean priced share of equity weight: " + cov.groupby("role")["priced_weight_share"].mean().round(3).to_string().replace("\n", "; "))
    save_processed(cov, "price_coverage")
    save_processed(H, "holdings_monthly")


if __name__ == "__main__":
    main()
