"""Test 1 - Brinson-Fachler sector attribution: Motilal Oswal Midcap Fund vs Nifty Midcap 150 (index-fund proxy).

Holdings-based, monthly, buy-and-hold: weights at month-end t, stock returns in month t+1 (price returns).
Window: holdings HOLD_START..(LAST_FULL_MONTH - 1) -> returns one month later (benchmark-proxy holdings start Sep-2019).
  w_p,i : fund weight in sector i, % of NAV; CASH (incl. TREPS, net receivables) = 1 - equity weight, earns RF.
  w_b,i : index-fund equity weights renormalised to 100% (an index holds no cash).
  R_x,i : weight-averaged return of PRICED holdings in sector i (unpriced weight dropped within the sector; coverage logged).
  Allocation  = (w_p,i - w_b,i)(R_b,i - R_b)
  Selection   = w_b,i (R_p,i - R_b,i)
  Interaction = (w_p,i - w_b,i)(R_p,i - R_b,i)        -> sum over i = R_p - R_b exactly.
  Sector held by only one side: if w_b,i = 0 set R_b,i := R_p,i (whole effect is allocation, e.g. cash);
                                if w_p,i = 0 set R_p,i := R_b,i (no selection possible).
Multi-period: Carino (1999) log-linking so linked effects add to cumulative R_P - R_B.
RF after Dec-2025 (IIMA ends): last available value carried forward (assumption).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import a_common as A



def sector_table(h: pd.DataFrame, r: pd.Series, include_cash: bool, rf: float) -> pd.DataFrame:
    h = h.assign(ret=h["isin_priced"].map(r))
    if not include_cash:
        h = h.assign(weight_nav=h["weight_nav"] / h["weight_nav"].sum())
    g = h.groupby("sector")
    w = g["weight_nav"].sum()
    pr = h.dropna(subset=["ret"])
    R = pr.groupby("sector").apply(lambda x: np.average(x["ret"], weights=x["weight_nav"]), include_groups=False)
    cov = pr.groupby("sector")["weight_nav"].sum() / w
    t = pd.DataFrame({"w": w, "R": R, "priced_share": cov})
    if include_cash:
        t.loc["Cash & equivalents"] = [1 - w.sum(), rf, 1.0]
    return t


def main() -> None:
    H = A.holdings()
    sr = A.stock_returns().set_index(["month_end", "isin"])["ret_m"]
    rf = A.factors()["RF"]
    nav = A.monthly_nav_returns()
    rows = []
    for t0 in pd.date_range(A.HOLD_START, A.LAST_FULL_MONTH - pd.offsets.MonthEnd(1), freq="ME"):
        t1 = t0 + pd.offsets.MonthEnd(1)
        rft = rf.get(t1, rf.iloc[-1])
        r1 = sr.xs(t1, level="month_end") if t1 in sr.index.get_level_values(0) else pd.Series(dtype=float)
        fp = H[(H["role"] == "target_midcap_fund") & (H["month_end"] == t0)]
        fb = H[(H["role"] == "benchmark_proxy_midcap150_index_fund") & (H["month_end"] == t0)]
        if fp.empty or fb.empty:
            continue
        P = sector_table(fp, r1, True, rft)
        B = sector_table(fb, r1, False, rft)
        S = P[["w", "R"]].add_suffix("_p").join(B[["w", "R"]].add_suffix("_b"), how="outer")
        S[["w_p", "w_b"]] = S[["w_p", "w_b"]].fillna(0)
        S["R_b"] = S["R_b"].where(S["w_b"] > 0, S["R_p"])
        S["R_p"] = S["R_p"].where(S["w_p"] > 0, S["R_b"])
        S[["R_p", "R_b"]] = S[["R_p", "R_b"]].fillna(0)
        Rp, Rb = (S["w_p"] * S["R_p"]).sum(), (S["w_b"] * S["R_b"]).sum()
        S["allocation"] = (S["w_p"] - S["w_b"]) * (S["R_b"] - Rb)
        S["selection"] = S["w_b"] * (S["R_p"] - S["R_b"])
        S["interaction"] = (S["w_p"] - S["w_b"]) * (S["R_p"] - S["R_b"])
        S["month"], S["Rp_total"], S["Rb_total"] = t1, Rp, Rb
        S["fund_priced_equity_share"] = fp.loc[fp["isin_priced"].notna(), "weight_nav"].sum() / fp["weight_nav"].sum()
        S["nav_ret_fund"] = nav.loc[t1, A.TARGET] if t1 in nav.index else np.nan
        S["nav_ret_bench"] = nav.loc[t1, A.PROXY["MID150"]] if t1 in nav.index else np.nan
        rows.append(S.reset_index().rename(columns={"index": "sector"}))
    M = pd.concat(rows, ignore_index=True)
    chk = M.groupby("month").apply(lambda g: (g[["allocation", "selection", "interaction"]].sum().sum()
                                                - (g["Rp_total"].iloc[0] - g["Rb_total"].iloc[0])), include_groups=False)
    assert chk.abs().max() < 1e-12, "Brinson identity failed"
    M.to_csv(A.out_dir("t1") / "brinson_monthly_by_sector.csv", index=False)

    # monthly totals + Carino linking
    T = M.groupby("month").agg(Rp=("Rp_total", "first"), Rb=("Rb_total", "first"), alloc=("allocation", "sum"),
                               sel=("selection", "sum"), inter=("interaction", "sum"),
                               nav_fund=("nav_ret_fund", "first"), nav_bench=("nav_ret_bench", "first"),
                               priced=("fund_priced_equity_share", "first"))
    RP, RB = (1 + T["Rp"]).prod() - 1, (1 + T["Rb"]).prod() - 1
    k = (np.log1p(RP) - np.log1p(RB)) / (RP - RB)
    kt = np.where(np.isclose(T["Rp"], T["Rb"]), 1 / (1 + T["Rp"]), (np.log1p(T["Rp"]) - np.log1p(T["Rb"])) / (T["Rp"] - T["Rb"]))
    T["carino_w"] = kt / k
    T.to_csv(A.out_dir("t1") / "brinson_monthly_totals.csv")
    M = M.merge(T["carino_w"], left_on="month", right_index=True)
    by_sec = M.assign(**{c + "_linked": M[c] * M["carino_w"] for c in ["allocation", "selection", "interaction"]}) \
        .groupby("sector").agg(avg_w_fund=("w_p", "mean"), avg_w_bench=("w_b", "mean"),
                               allocation=("allocation_linked", "sum"), selection=("selection_linked", "sum"),
                               interaction=("interaction_linked", "sum"))
    by_sec["total"] = by_sec[["allocation", "selection", "interaction"]].sum(axis=1)
    by_sec = by_sec.sort_values("total", ascending=False)
    by_sec.loc["TOTAL"] = by_sec.sum(numeric_only=True)
    by_sec.loc["TOTAL", ["avg_w_fund", "avg_w_bench"]] = np.nan
    by_sec.to_csv(A.out_dir("t1") / "brinson_cumulative_by_sector_carino.csv")
    yr = M.assign(year=M["month"].dt.year).groupby("year")[["allocation", "selection", "interaction"]].sum()
    yr["active_holdings_based"] = yr.sum(axis=1)
    yr.to_csv(A.out_dir("t1") / "brinson_by_calendar_year_arithmetic.csv")

    navP, navB = (1 + T["nav_fund"]).prod() - 1, (1 + T["nav_bench"]).prod() - 1
    yrs = len(T) / 12
    summ = {
        "months": len(T), "window": f"{T.index.min().date()}..{T.index.max().date()}",
        "holdings_fund_cum": RP, "holdings_bench_cum": RB, "holdings_active_cum": RP - RB,
        "linked_allocation": by_sec.loc["TOTAL", "allocation"], "linked_selection": by_sec.loc["TOTAL", "selection"],
        "linked_interaction": by_sec.loc["TOTAL", "interaction"],
        "nav_fund_cum": navP, "nav_bench_proxy_cum": navB, "nav_active_cum": navP - navB,
        "nav_fund_cagr": (1 + navP) ** (1 / yrs) - 1, "nav_bench_cagr": (1 + navB) ** (1 / yrs) - 1,
        "holdings_fund_cagr": (1 + RP) ** (1 / yrs) - 1, "holdings_bench_cagr": (1 + RB) ** (1 / yrs) - 1,
        "residual_fund_nav_minus_holdings_cagr": (1 + navP) ** (1 / yrs) - (1 + RP) ** (1 / yrs),
        "residual_bench_nav_minus_holdings_cagr": (1 + navB) ** (1 / yrs) - (1 + RB) ** (1 / yrs),
        "mean_fund_priced_equity_share": T["priced"].mean(),
        "corr_monthly_holdings_vs_nav_fund": T[["Rp", "nav_fund"]].corr().iloc[0, 1],
        "corr_monthly_holdings_vs_nav_bench": T[["Rb", "nav_bench"]].corr().iloc[0, 1],
    }
    pd.Series(summ).to_csv(A.out_dir("t1") / "brinson_summary.csv", header=["value"])
    print(pd.Series(summ).to_string())
    print(by_sec.round(4).to_string())
    print(yr.round(4).to_string())


if __name__ == "__main__":
    main()
