"""Test 4 - Four-factor (Carhart) alpha with Newey-West SEs, rolling 36-month alpha, up/down capture.

r_fund - RF = a + b1 MKT_RF + b2 SMB + b3 HML + b4 WML + e     (IIMA factors, survivorship-bias adjusted, monthly)
Windows: full = Mar-2014..Dec-2025 (fund's first full month .. last IIMA month);
         sub   = Oct-2019..Dec-2025 (same window as the benchmark-relative tests).
Control: the same regression on the Nifty Midcap 150 index-fund proxy (a passive fund should show alpha ~ 0 minus TER).
Up/down capture (geometric, Morningstar convention): vs Midcap 150 proxy (Oct-2019..Sep-2026) and vs IIMA market
return MKT_RF+RF (Mar-2014..Dec-2025). Up month = benchmark return >= 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import a_common as A

F = ["MKT_RF", "SMB", "HML", "WML"]


def carhart(y: pd.Series, f: pd.DataFrame, label: str) -> dict:
    m, T, L = A.ols_nw(y - f["RF"], f[F])
    d = {"series": label, "start": y.dropna().index.min().date(), "end": f.index.max().date(), "months": T, "nw_lags": L,
         "alpha_monthly": m.params["const"], "alpha_annualised": (1 + m.params["const"]) ** 12 - 1,
         "alpha_t_nw": m.tvalues["const"], "alpha_p_nw": m.pvalues["const"], "adj_R2": m.rsquared_adj}
    for k in F:
        d[f"beta_{k}"], d[f"t_{k}"] = m.params[k], m.tvalues[k]
    return d


def capture(f: pd.Series, b: pd.Series) -> dict:
    d = pd.concat([f, b], axis=1).dropna()
    d.columns = ["f", "b"]
    up, dn = d[d["b"] >= 0], d[d["b"] < 0]
    g = lambda s: (1 + s).prod() ** (1 / len(s)) - 1  # noqa: E731
    return {"months": len(d), "up_months": len(up), "down_months": len(dn),
            "up_capture": g(up["f"]) / g(up["b"]), "down_capture": g(dn["f"]) / g(dn["b"]),
            "fund_cagr": (1 + d["f"]).prod() ** (12 / len(d)) - 1, "bench_cagr": (1 + d["b"]).prod() ** (12 / len(d)) - 1,
            "batting_avg": (d["f"] > d["b"]).mean()}


def main() -> None:
    r = A.monthly_nav_returns()
    fac = A.factors()
    fund, mid = r[A.TARGET], r[A.PROXY["MID150"]]
    f_full = fac.loc[A.FUND_START:A.FACTOR_END]
    f_sub = fac.loc[A.BENCH_START:A.FACTOR_END]
    rows = [carhart(fund.reindex(f_full.index), f_full, "Fund (full)"),
            carhart(fund.reindex(f_sub.index), f_sub, "Fund (benchmark window)"),
            carhart(mid.reindex(f_sub.index), f_sub, "Midcap 150 index-fund proxy [control]")]
    T = pd.DataFrame(rows)
    T.to_csv(A.out_dir("t4") / "carhart_alpha.csv", index=False)
    print(T.T.to_string())

    # rolling 36-month alpha (OLS point estimates; NW t for each window)
    y = (fund - fac["RF"]).loc[A.FUND_START:A.FACTOR_END]
    roll = []
    for i in range(36, len(y) + 1):
        idx = y.index[i - 36:i]
        m, _, _ = A.ols_nw(y.loc[idx], fac.loc[idx, F])
        roll.append({"window_end": idx[-1], "alpha_annualised": (1 + m.params["const"]) ** 12 - 1,
                     "alpha_t_nw": m.tvalues["const"], "beta_mkt": m.params["MKT_RF"]})
    R = pd.DataFrame(roll)
    R.to_csv(A.out_dir("t4") / "rolling_36m_alpha.csv", index=False)
    print(R.iloc[::12].round(3).to_string(index=False))

    bw = f"{A.BENCH_START:%b-%Y}..{A.LAST_FULL_MONTH:%b-%Y}"
    fw = f"{A.FUND_START:%b-%Y}..{A.FACTOR_END:%b-%Y}"
    caps = pd.DataFrame([{"vs": f"Nifty Midcap 150 proxy ({bw})", **capture(fund.loc[A.BENCH_START:], mid.loc[A.BENCH_START:])},
                         {"vs": f"IIMA market MKT_RF+RF ({fw})",
                          **capture(fund.loc[A.FUND_START:A.FACTOR_END], (fac["MKT_RF"] + fac["RF"]).loc[A.FUND_START:A.FACTOR_END])}])
    caps.to_csv(A.out_dir("t4") / "up_down_capture.csv", index=False)
    print(caps.T.to_string())

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(R["window_end"], R["alpha_annualised"] * 100)
    ax.axhline(0, color="grey", lw=0.8)
    sig = R["alpha_t_nw"].abs() > 1.96
    ax.scatter(R.loc[sig, "window_end"], R.loc[sig, "alpha_annualised"] * 100, s=8, color="red", label="|t_NW| > 1.96")
    ax.set_ylabel("4-factor alpha, % p.a.")
    ax.set_title("Motilal Oswal Midcap Fund - rolling 36-month Carhart alpha (IIMA factors)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(A.out_dir("t4") / "rolling_36m_alpha.png", dpi=150)


if __name__ == "__main__":
    main()
