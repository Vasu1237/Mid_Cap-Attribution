"""Charts for the write-up:
  t0/growth_of_100.png   - fund vs Midcap 150 proxy vs category median (benchmark window)
  t0/drawdowns.png       - drawdown from running peak, fund vs benchmark proxy
  t1/brinson_by_sector.png - Brinson-Fachler sector effects (Carino-linked)
  t2/active_share.png    - monthly active share, cash, top-10 concentration
"""
from __future__ import annotations

import matplotlib
import pandas as pd

import a_common as A

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def overview() -> None:
    r = A.monthly_nav_returns().loc[A.BENCH_START:]
    peers = [c for c in A.peer_names() if c != A.TARGET]
    med = r[peers].median(axis=1)
    g = pd.DataFrame({"Motilal Oswal Midcap Fund": r[A.TARGET], "Nifty Midcap 150 (index-fund proxy)": r[A.PROXY["MID150"]],
                      "Mid Cap category median (monthly)": med}).fillna(0)
    lvl = 100 * (1 + g).cumprod()
    start = pd.DataFrame(100.0, index=[A.BENCH_START - pd.offsets.MonthEnd(1)], columns=lvl.columns)
    lvl = pd.concat([start, lvl])
    lvl.to_csv(A.out_dir("t0") / "growth_of_100.csv")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for c, st in zip(lvl.columns, ["-", "--", ":"]):
        ax.plot(lvl.index, lvl[c], st, label=f"{c}: {lvl[c].iloc[-1]:.0f}")
    ax.set_ylabel("Value of Rs 100 invested")
    ax.set_title(f"Growth of Rs 100, {lvl.index[0]:%b-%Y} to {lvl.index[-1]:%b-%Y} (Direct plans, after fees)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(A.out_dir("t0") / "growth_of_100.png", dpi=150)
    dd = lvl[lvl.columns[:2]] / lvl[lvl.columns[:2]].cummax() - 1
    fig, ax = plt.subplots(figsize=(9, 3.5))
    for c, st in zip(dd.columns, ["-", "--"]):
        ax.plot(dd.index, dd[c] * 100, st, label=f"{c} (max {dd[c].min() * 100:.0f}%)")
    ax.set_ylabel("Drawdown from peak, %")
    ax.set_title("Drawdowns (month-end NAV)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(A.out_dir("t0") / "drawdowns.png", dpi=150)


def main() -> None:
    overview()
    b = pd.read_csv(A.out_dir("t1") / "brinson_cumulative_by_sector_carino.csv", index_col=0).drop("TOTAL")
    b = b.sort_values("total")
    fig, ax = plt.subplots(figsize=(9, 5))
    b[["allocation", "selection", "interaction"]].mul(100).plot.barh(stacked=True, ax=ax,
                                                                     color=["#c97b63", "#4c78a8", "#9ecae9"])
    ax.scatter(b["total"] * 100, range(len(b)), color="black", zorder=3, s=14, label="total")
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_xlabel(f"Cumulative contribution to active return, % points (Carino-linked, {A.BENCH_START:%b-%Y}..{A.LAST_FULL_MONTH:%b-%Y})")
    ax.set_title("Brinson-Fachler attribution: MO Midcap Fund vs Nifty Midcap 150 (proxy)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(A.out_dir("t1") / "brinson_by_sector.png", dpi=150)

    a = pd.read_csv(A.out_dir("t2") / "active_share_monthly.csv", parse_dates=["month_end"])
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(a["month_end"], a["active_share_equity"] * 100, label="Active share (equity, %)")
    ax.plot(a["month_end"], a["fund_cash_weight"] * 100, label="Cash & equivalents (% NAV)")
    ax.plot(a["month_end"], a["top10_weight_fund_equity"] * 100, label="Top-10 weight (% equity)", alpha=0.7)
    ax.set_ylim(0, 100)
    ax.set_title("MO Midcap Fund: active share vs Nifty Midcap 150 (proxy), cash and concentration")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(A.out_dir("t2") / "active_share.png", dpi=150)


if __name__ == "__main__":
    main()
