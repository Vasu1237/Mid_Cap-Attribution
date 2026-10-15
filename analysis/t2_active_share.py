"""Test 2 - Active share (Cremers & Petajisto 2009) vs Nifty Midcap 150 (index-fund holdings proxy), monthly.

AS = 1/2 * sum_i |w_p,i - w_b,i| over the union of securities (ISIN-level, after ISIN remap).
  * 'equity' version: fund equity weights renormalised to 100% (standard; ignores cash).
  * 'nav' version: fund weights as % of NAV, cash counted as a non-benchmark position.
Benchmark weights renormalised to 100% equity. Window: Sep-2019..Sep-2026 (proxy holdings available).
Also: number of stocks, top-10 weight, number/weight of fund holdings that are in the benchmark.
"""
from __future__ import annotations

import pandas as pd

import a_common as A


def main() -> None:
    H = A.holdings()
    H["key"] = H["isin_priced"].fillna(H["isin"])
    rows = []
    for d, g in H.groupby("month_end"):
        p = g[g["role"] == "target_midcap_fund"].groupby("key")["weight_nav"].sum()
        b = g[g["role"] == "benchmark_proxy_midcap150_index_fund"].groupby("key")["weight_nav"].sum()
        if p.empty or b.empty:
            continue
        b = b / b.sum()
        pe = p / p.sum()
        u = pe.index.union(b.index)
        as_eq = 0.5 * (pe.reindex(u, fill_value=0) - b.reindex(u, fill_value=0)).abs().sum()
        cash = 1 - p.sum()
        as_nav = 0.5 * ((p.reindex(u, fill_value=0) - b.reindex(u, fill_value=0)).abs().sum() + max(cash, 0))
        inb = p.index.isin(b.index)
        rows.append({"month_end": d, "active_share_equity": as_eq, "active_share_nav_incl_cash": as_nav,
                     "n_stocks_fund": len(p), "n_stocks_bench": len(b), "fund_cash_weight": cash,
                     "top10_weight_fund_equity": pe.nlargest(10).sum(), "n_fund_in_bench": int(inb.sum()),
                     "fund_equity_weight_in_bench": pe[inb].sum()})
    T = pd.DataFrame(rows)
    T.to_csv(A.out_dir("t2") / "active_share_monthly.csv", index=False)
    s = T.describe().T[["mean", "min", "50%", "max"]]
    s.to_csv(A.out_dir("t2") / "active_share_summary.csv")
    y = T.assign(year=T["month_end"].dt.year).groupby("year")[["active_share_equity", "n_stocks_fund",
                                                               "top10_weight_fund_equity", "fund_equity_weight_in_bench", "fund_cash_weight"]].mean()
    y.to_csv(A.out_dir("t2") / "active_share_by_year.csv")
    print(s.round(3).to_string())
    print(y.round(3).to_string())


if __name__ == "__main__":
    main()
