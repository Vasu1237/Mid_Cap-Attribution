"""Pipeline 6 - Indian Fama-French-Momentum factors (IIMA), monthly, survivorship-bias adjusted.

Source: https://faculty.iima.ac.in/iffm/Indian-Fama-French-Momentum/ (cite Agarwalla, Jacob & Varma 2013).
Release pinned in p3config.IIMA_RELEASE (values can be revised between releases). Columns: MF (= MKT-RF), SMB, HML,
WML, RF in % per month -> converted to decimals.
Output: data/processed/factors_iima.csv (month_end, MKT_RF, SMB, HML, WML, RF)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> p3config

import io

import pandas as pd

from p3config import IIMA_RELEASE, RAW, cached_get, log, save_processed

FILE = f"{IIMA_RELEASE}_FourFactors_and_Market_Returns_Monthly_SurvivorshipBiasAdjusted.csv"
URL = "https://faculty.iima.ac.in/iffm/Indian-Fama-French-Momentum/DATA/" + FILE


def main() -> None:
    df = pd.read_csv(io.BytesIO(cached_get(URL, RAW / "iima" / FILE)))
    df.columns = [c.strip() for c in df.columns]
    df["month_end"] = pd.to_datetime(df["Date"].astype(str)) + pd.offsets.MonthEnd(0)
    out = df.rename(columns={"MF": "MKT_RF"})[["month_end", "MKT_RF", "SMB", "HML", "WML", "RF"]]
    out[["MKT_RF", "SMB", "HML", "WML", "RF"]] /= 100
    out = out[out["month_end"] >= "2012-01-31"]
    log("p06_iima", "factors", f"release {IIMA_RELEASE}: {out.month_end.min().date()}..{out.month_end.max().date()}, % -> decimal")
    save_processed(out, "factors_iima")


if __name__ == "__main__":
    main()
