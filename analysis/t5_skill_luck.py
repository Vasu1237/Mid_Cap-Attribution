"""Test 5 - Skill vs luck: bootstrap of Carhart alpha t-statistics across the AMFI 'Mid Cap Fund' category.

Method (Kosowski, Timmermann, Wermers & White 2006; Fama & French 2010):
 1. For each Direct-Growth mid-cap fund with >= 36 months in Mar-2014..Dec-2025, OLS Carhart regression on IIMA factors
    -> alpha_i, t_i (OLS t; iid bootstrap below destroys autocorrelation, so OLS t is the consistent comparator).
 2. Impose zero true alpha: r~_it = r_it - alpha_i.
 3. B bootstrap runs: draw 142 calendar months with replacement (same draw for all funds AND factors -> keeps
    cross-fund correlation, FF 2010); for each fund keep its available months in the draw (needs >= 30), re-estimate t.
 4. Fund-level p (KTWW): share of runs where the target's simulated t >= its actual t.
    Cross-section (FF 2010): actual t at percentiles vs mean simulated percentiles, and share of runs with
    simulated percentile >= actual.
Universe caveat: funds alive today only (AMFI category list) -> survivorship bias; merged/closed mid-cap schemes absent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import a_common as A

B, SEED, MIN_OBS, MIN_BOOT = 2000, 20261015, 36, 30
F = ["MKT_RF", "SMB", "HML", "WML"]
PCTS = [5, 10, 25, 50, 75, 90, 95]


def ols_alpha_t(y: np.ndarray, X: np.ndarray) -> tuple[float, float]:
    Xc = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    e = y - Xc @ beta
    s2 = e @ e / (len(y) - Xc.shape[1])
    cov = s2 * np.linalg.inv(Xc.T @ Xc)
    return beta[0], beta[0] / np.sqrt(cov[0, 0])


def main() -> None:
    run("carhart_iima", A.FUND_START, A.FACTOR_END)
    run("benchmark_mid150", A.BENCH_START, A.LAST_FULL_MONTH)


def run(model: str, start, end) -> None:
    """model 'carhart_iima': IIMA 4 factors. model 'benchmark_mid150': single factor = Midcap 150 index-fund proxy
    excess return (robustness: does the fund beat a passive mid-cap fund? RF carried forward after Dec-2025)."""
    r = A.monthly_nav_returns()
    fac = A.factors().reindex(pd.date_range(start, end, freq="ME")).ffill()
    if model == "benchmark_mid150":
        fac = fac.assign(BM_RF=r[A.PROXY["MID150"]].reindex(fac.index) - fac["RF"]).dropna(subset=["BM_RF"])
        cols = ["BM_RF"]
    else:
        cols = F
    funds = [c for c in A.peer_names() if r[c].reindex(fac.index).notna().sum() >= MIN_OBS]
    Y = r.reindex(fac.index)[funds].sub(fac["RF"], axis=0)
    X = fac[cols].values
    act = {}
    for f in funds:
        m = Y[f].notna().values
        a, t = ols_alpha_t(Y[f].values[m], X[m])
        act[f] = (a, t, int(m.sum()))
    A_ = pd.DataFrame(act, index=["alpha_m", "t_ols", "months"]).T
    Y0 = Y - A_["alpha_m"]  # zero-alpha returns
    rng = np.random.default_rng(SEED)
    T = len(fac)
    print(f"===== {model}: {len(funds)} funds, {fac.index.min():%Y-%m}..{fac.index.max():%Y-%m}")
    sim = np.full((B, len(funds)), np.nan)
    Yv, Mv = Y0.values, Y0.notna().values
    for b in range(B):
        idx = rng.integers(0, T, T)
        for j in range(len(funds)):
            m = Mv[idx, j]
            if m.sum() >= MIN_BOOT:
                sim[b, j] = ols_alpha_t(Yv[idx, j][m], X[idx][m])[1]
    S = pd.DataFrame(sim, columns=funds)
    out = A.out_dir(f"t5/{model}")
    A_["alpha_annualised"] = (1 + A_["alpha_m"]) ** 12 - 1
    A_["p_boot_fund_level"] = [(S[f] >= A_.loc[f, "t_ols"]).mean() for f in funds]
    A_["rank_t_in_category"] = A_["t_ols"].rank(ascending=False).astype(int)
    A_ = A_.sort_values("t_ols", ascending=False)
    A_.to_csv(out / "category_alpha_t_and_bootstrap_p.csv")
    act_p = np.percentile(A_["t_ols"], PCTS)
    sim_p = np.nanpercentile(S.values, PCTS, axis=1)  # per run
    X5 = pd.DataFrame({"pct": PCTS, "actual_t": act_p, "sim_mean_t": sim_p.mean(axis=1),
                       "share_sim_ge_actual": [(sim_p[i] >= act_p[i]).mean() for i in range(len(PCTS))]})
    X5.to_csv(out / "cross_section_percentiles.csv", index=False)
    tgt = A.TARGET
    summ = pd.Series({"funds_in_test": len(funds), "bootstrap_runs": B, "seed": SEED, "model": model, "window": f"{fac.index.min():%Y-%m}..{fac.index.max():%Y-%m}",
                      "target_alpha_annualised": A_.loc[tgt, "alpha_annualised"], "target_t_ols": A_.loc[tgt, "t_ols"],
                      "target_rank": A_.loc[tgt, "rank_t_in_category"],
                      "target_p_boot (share of luck-only runs with t >= actual)": A_.loc[tgt, "p_boot_fund_level"],
                      "target_sim_t_95th_pct": S[tgt].quantile(0.95)})
    summ.to_csv(out / "target_summary.csv", header=["value"])
    print(summ.to_string())
    print(A_.round(3).to_string())
    print(X5.round(3).to_string(index=False))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(S[tgt].dropna(), bins=60, color="lightsteelblue", label="zero-alpha bootstrap t (luck only)")
    ax.axvline(A_.loc[tgt, "t_ols"], color="red", label=f"actual t = {A_.loc[tgt, 't_ols']:.2f}")
    ax.set_title(f"Motilal Oswal Midcap Fund: alpha t vs luck distribution ({model})")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "target_t_vs_bootstrap.png", dpi=150)


if __name__ == "__main__":
    main()
