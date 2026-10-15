"""Shared inputs for the analysis (Motilal Oswal Midcap Fund, Direct Growth). Reads only data/processed/.

Monthly return convention: month-end NAV (last available NAV in the calendar month) / previous month-end NAV - 1.
The last month is kept only if NAVs exist up to its final 3 calendar days (otherwise it is incomplete and dropped).
Factors: IIMA Indian Fama-French-Momentum (data/processed/factors_iima.csv, decimals). RF = IIMA 91-day T-bill.

Sample windows are DERIVED from the data (so a rebuild with newer data extends every test automatically):
  FUND_START     first full month of the fund's NAV
  BENCH_START    first full month of the Midcap 150 index-fund NAV (benchmark-relative tests)
  HOLD_START     first month with both fund and benchmark-proxy holdings (Brinson / active share)
  STYLE_START    first month in which every style index fund has a return
  FACTOR_END     last month of the IIMA factor file
  LAST_FULL_MONTH last complete month of NAV data
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from p3config import FUND, PROXY_CODES, RESULTS, processed  # noqa: E402

RES = RESULTS
_N = pd.read_csv(processed("nav_daily"), parse_dates=["date"])
TARGET = _N.loc[_N["amfi_code"] == FUND["amfi_code"], "nav_name"].iloc[0]
PROXY = {k: _N.loc[_N["amfi_code"] == c, "nav_name"].iloc[0] for c, k in PROXY_CODES.items()}
_last = _N["date"].max()
LAST_FULL_MONTH = (_last + pd.offsets.MonthEnd(0)) if (_last + pd.offsets.MonthEnd(0) - _last).days <= 3 \
    else (_last - pd.offsets.MonthEnd(1))


def monthly_nav_returns() -> pd.DataFrame:
    """Wide monthly returns: one column per NAV series (nav_name), indexed by month-end."""
    me = _N.groupby(["nav_name", _N["date"].dt.to_period("M")])["nav"].last().unstack(0)
    r = me.pct_change(fill_method=None)
    r.index = r.index.to_timestamp("M")
    for c in r.columns:  # first month of each series is a partial month from launch
        first = me[c].first_valid_index()
        if first is not None:
            r.loc[first.to_timestamp("M"), c] = np.nan
    return r[r.index <= LAST_FULL_MONTH]


def factors() -> pd.DataFrame:
    return pd.read_csv(processed("factors_iima"), parse_dates=["month_end"]).set_index("month_end")


def peer_names() -> list[str]:
    return sorted(_N.loc[_N["role"].isin(["category_peer", "target"]), "nav_name"].unique())


_R = monthly_nav_returns()
FUND_START = _R[TARGET].first_valid_index()
BENCH_START = _R[PROXY["MID150"]].first_valid_index()
STYLE_START = _R[[PROXY[k] for k in ("N50", "NN50", "MID150", "SC250")]].dropna().index.min()
FACTOR_END = factors().index.max()


# ---- sector roll-up of AMFI industry labels (labels changed over the years; mapping is analyst judgement) ----
SECTOR_MAP = {
    "Financials": ["finance", "banks", "insurance", "capital markets", "financial technology (fintech)", "financial services"],
    "Information Technology": ["it - software", "software", "it - services", "information technology", "it - hardware", "engineering services"],
    "Consumer Discretionary": ["consumer durables", "retailing", "auto components", "auto ancillaries", "auto", "automobiles",
                               "automobile and auto components", "leisure services", "textile products", "textiles & apparels",
                               "entertainment", "media & entertainment", "hotels, resorts and other recreational activities",
                               "hotels/ resorts and other recreational activities", "consumer services", "other consumer services"],
    "Consumer Staples": ["consumer non durables", "agricultural food & other products", "beverages", "personal products",
                         "food products", "cigarettes & tobacco products"],
    "Health Care": ["healthcare services", "pharmaceuticals & biotechnology", "pharmaceuticals", "healthcare"],
    "Industrials": ["industrial products", "electrical equipment", "construction", "industrial capital goods",
                    "agricultural, commercial & construction vehicles", "aerospace & defense", "industrial manufacturing",
                    "construction project", "capital goods", "commercial services", "transportation", "transport services",
                    "transport infrastructure", "services", "trading", "diversified", "miscellaneous"],
    "Materials": ["chemicals & petrochemicals", "chemicals", "cement & cement products", "cement", "pesticides",
                  "fertilizers & agrochemicals", "fertilisers", "ferrous metals", "non - ferrous metals", "minerals & mining",
                  "metals & minerals trading", "metals & mining"],
    "Energy & Utilities": ["gas", "power", "petroleum products", "oil", "oil gas & consumable fuels"],
    "Real Estate": ["realty"],
    "Telecom": ["telecom - services", "telecom - equipment & accessories", "telecommunication"],
}
_LOOKUP = {k: s for s, ks in SECTOR_MAP.items() for k in ks}


def sector_of(industry) -> str:
    key = re.sub(r"\s+", " ", str(industry)).strip().lower()
    return _LOOKUP.get(key, "UNMAPPED")


def holdings() -> pd.DataFrame:
    H = pd.read_csv(processed("holdings_monthly"), parse_dates=["month_end"])
    H["sector"] = H["industry"].map(sector_of)
    return H


_H = pd.read_csv(processed("holdings_monthly"), usecols=["role", "month_end"], parse_dates=["month_end"]).drop_duplicates()
HOLD_START = _H[_H["role"] == "benchmark_proxy_midcap150_index_fund"]["month_end"].min()


def stock_returns() -> pd.DataFrame:
    return pd.read_csv(processed("stock_returns_monthly"), parse_dates=["month_end"])


def ols_nw(y: pd.Series, X: pd.DataFrame, lags: int | None = None):
    """OLS with Newey-West (HAC) standard errors; lag = floor(4*(T/100)^(2/9)) unless given."""
    import statsmodels.api as sm
    d = pd.concat([y, X], axis=1).dropna()
    T = len(d)
    L = lags if lags is not None else int(np.floor(4 * (T / 100) ** (2 / 9)))
    m = sm.OLS(d.iloc[:, 0], sm.add_constant(d.iloc[:, 1:])).fit(cov_type="HAC", cov_kwds={"maxlags": L})
    return m, T, L


def out_dir(name: str) -> Path:
    p = RES / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def windows() -> dict:
    return {"FUND_START": FUND_START.date(), "BENCH_START": BENCH_START.date(), "HOLD_START": HOLD_START.date(),
            "STYLE_START": STYLE_START.date(), "FACTOR_END": FACTOR_END.date(), "LAST_FULL_MONTH": LAST_FULL_MONTH.date()}
