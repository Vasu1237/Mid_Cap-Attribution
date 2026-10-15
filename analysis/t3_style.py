"""Test 3 - Returns-based style analysis (Sharpe 1992).

min_w Var(R_fund - sum_k w_k R_k)  s.t. w_k >= 0, sum_k w_k = 1   (quadratic programme, SLSQP)
Style assets (MOAMC index-fund NAVs as TRI proxies): Nifty 50, Nifty Next 50 (together = Nifty 100 large caps),
Nifty Midcap 150, Nifty Smallcap 250, and Cash = monthly 91-day T-bill (IIMA RF; carried forward after Dec-2025).
Window: Jan-2020..Sep-2026 (first full month of the Nifty 50 index fund is Jan-2020); also rolling 36 months.
Style R^2 = 1 - Var(residual)/Var(fund); 1 - R^2 = share of variance from selection (Sharpe's 'selection').
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import a_common as A

STYLES = ["N50", "NN50", "MID150", "SC250"]


def solve(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    k = X.shape[1]
    obj = lambda w: np.var(y - X @ w)  # noqa: E731
    res = minimize(obj, np.full(k, 1 / k), method="SLSQP", bounds=[(0, 1)] * k,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}], options={"ftol": 1e-12, "maxiter": 500})
    return res.x


def main() -> None:
    r = A.monthly_nav_returns()
    rf = A.factors()["RF"].reindex(r.index).ffill()
    D = pd.DataFrame({k: r[A.PROXY[k]] for k in STYLES})
    D["CASH"] = rf
    D["FUND"] = r[A.TARGET]
    D = D.loc[A.STYLE_START:].dropna()
    cols = STYLES + ["CASH"]
    w = solve(D["FUND"].values, D[cols].values)
    resid = D["FUND"] - D[cols].values @ w
    r2 = 1 - resid.var() / D["FUND"].var()
    out = pd.Series(w, index=cols)
    full = pd.concat([out, pd.Series({"R2": r2, "selection_1_minus_R2": 1 - r2, "months": len(D),
                                      "mean_monthly_residual (style alpha)": resid.mean(),
                                      "annualised_tracking_error_vs_style": resid.std() * np.sqrt(12)})])
    full.to_csv(A.out_dir("t3") / "style_full_period.csv", header=["value"])
    roll = []
    for i in range(36, len(D) + 1):
        s = D.iloc[i - 36:i]
        wi = solve(s["FUND"].values, s[cols].values)
        e = s["FUND"] - s[cols].values @ wi
        roll.append({"window_end": s.index[-1], **dict(zip(cols, wi)), "R2": 1 - e.var() / s["FUND"].var()})
    R = pd.DataFrame(roll)
    R.to_csv(A.out_dir("t3") / "style_rolling_36m.csv", index=False)
    print(full.round(4).to_string())
    print(R.iloc[::6].round(3).to_string(index=False))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.stackplot(R["window_end"], *[R[c] for c in cols], labels=["Nifty 50", "Nifty Next 50", "Midcap 150", "Smallcap 250", "Cash"])
    ax.set_ylim(0, 1)
    ax.set_title("Motilal Oswal Midcap Fund - rolling 36-month style weights (Sharpe 1992)")
    ax.legend(loc="upper left", fontsize=8, ncol=5)
    fig.tight_layout()
    fig.savefig(A.out_dir("t3") / "style_rolling_36m.png", dpi=150)


if __name__ == "__main__":
    main()
