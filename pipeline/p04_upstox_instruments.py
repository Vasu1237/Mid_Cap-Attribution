"""Pipeline 4 - ISIN master from the public Upstox instrument files (no token needed).

Source: https://assets.upstox.com/market-quote/instruments/exchange/{NSE,BSE}.json.gz (current listings only).
Used by p05 to map old ISINs (pre face-value split / rename) to the live ISIN under which Upstox keeps the history.
Output: data/processed/isin_master.csv (isin, exchange, symbol, name, instrument_key) - company equity (INE*) only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> p3config

import pandas as pd

from p3config import RAW, TODAY, cached_get, gunzip_json, log, save_processed

URL = "https://assets.upstox.com/market-quote/instruments/exchange/{ex}.json.gz"


def main() -> None:
    fr = []
    for ex in ("NSE", "BSE"):
        d = pd.DataFrame(gunzip_json(cached_get(URL.format(ex=ex), RAW / "upstox" / f"{ex}_instruments_{TODAY}.json.gz")))
        d = d[(d["segment"] == f"{ex}_EQ") & d["isin"].astype(str).str.startswith("INE")]
        fr.append(pd.DataFrame({"isin": d["isin"], "exchange": ex, "symbol": d["trading_symbol"], "name": d["name"],
                                "instrument_key": d["instrument_key"]}))
    m = pd.concat(fr, ignore_index=True).drop_duplicates(["isin", "exchange"])
    log("p04_instruments", "master", f"{m['isin'].nunique()} company ISINs listed on NSE/BSE today")
    save_processed(m, "isin_master")


if __name__ == "__main__":
    main()
