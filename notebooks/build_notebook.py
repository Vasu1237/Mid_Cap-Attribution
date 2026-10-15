"""Builds notebooks/P3_walkthrough.ipynb (un-executed). `python run_all.py` executes it so outputs/charts are saved.

Edit the cells here, then run:  python notebooks/build_notebook.py && python run_all.py
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("""# Does Motilal Oswal Midcap Fund show skill? A reproducible walkthrough

**Question.** Where does the fund's return come from (sectors vs stock picks), how different is it from its benchmark,
what style does it behave like, and is its alpha distinguishable from luck?

**Fund.** Motilal Oswal Midcap Fund – Direct Plan Growth (AMFI 127042). **Benchmark:** Nifty Midcap 150 TRI.

**How this notebook works.** Every section re-runs the project's own analysis script (`analysis/t*.py`) on the
committed data snapshot in `data/processed/`, then shows the key tables and charts. Nothing is hard-coded: if you
rebuild the data (`python run_all.py --rebuild`), every number below updates.

> Data notes: benchmark and style indices are **index-fund NAV proxies** (official TRI downloads are not permitted
> from niftyindices.com); stock returns exclude dividends; factors are from the IIMA data library."""),
    code("""import sys, io, contextlib
from pathlib import Path
import pandas as pd
from IPython.display import Image, display, Markdown

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "analysis"))
import a_common as A

pd.set_option("display.width", 160); pd.set_option("display.max_columns", 20)

def quiet(module):
    \"\"\"Run an analysis script's main() without its console printout.\"\"\"
    with contextlib.redirect_stdout(io.StringIO()):
        module.main()

def show(path, width=850):
    display(Image(filename=str(A.RES / path), width=width))

display(Markdown("**Sample windows (derived from the data):**"))
pd.Series(A.windows())"""),
    md("## 0. Data snapshot\nRow counts, date ranges and SHA-256 checksums of every analysis input (`data/processed/MANIFEST.csv`)."),
    code("""pd.read_csv(ROOT / "data/processed/MANIFEST.csv")[["file", "rows", "columns", "date_range", "built"]]"""),
    md("## 1. The big picture\nGrowth of ₹100 since the benchmark proxy starts, and drawdowns. The charts are produced by `analysis/t6_charts.py`."),
    code("""import t1_brinson, t2_active_share, t3_style, t4_alpha_capture, t5_skill_luck, t6_charts
quiet(t1_brinson); quiet(t2_active_share)   # t6 draws charts from t1/t2 outputs
quiet(t6_charts)
show("t0/growth_of_100.png"); show("t0/drawdowns.png")"""),
    md(r"""## 2. Brinson-Fachler sector attribution (holdings-based)

For each month, sector weights at the previous month-end ($w$) and next-month stock returns ($R$):

* **Allocation** $=(w_{p,i}-w_{b,i})(R_{b,i}-R_b)$: did the fund overweight sectors that beat the benchmark?
* **Selection** $=w_{b,i}(R_{p,i}-R_{b,i})$: did its stocks beat the benchmark's stocks within each sector?
* **Interaction** $=(w_{p,i}-w_{b,i})(R_{p,i}-R_{b,i})$

They sum exactly to $R_p-R_b$ each month (checked in code); months are linked with Carino's method. Cash is a
sector earning the T-bill rate. The **return gap** compares actual NAV returns with this holdings-based return
(it captures intra-month trading, fees and dividends)."""),
    code("""s = pd.read_csv(A.RES / "t1/brinson_summary.csv", index_col=0)["value"]
display(s.to_frame())
display(pd.read_csv(A.RES / "t1/brinson_cumulative_by_sector_carino.csv", index_col=0).round(3))
show("t1/brinson_by_sector.png")
pd.read_csv(A.RES / "t1/brinson_by_calendar_year_arithmetic.csv").round(3)"""),
    md(r"""## 3. Active share (Cremers & Petajisto 2009)

$AS=\tfrac12\sum_i|w_{p,i}-w_{b,i}|$ over all stocks held by the fund or the benchmark proxy. 0 = index clone,
1 = no overlap; above ~0.8 is usually called concentrated stock-picking."""),
    code("""display(pd.read_csv(A.RES / "t2/active_share_summary.csv", index_col=0).round(3))
show("t2/active_share.png")
pd.read_csv(A.RES / "t2/active_share_by_year.csv").round(3)"""),
    md(r"""## 4. Returns-based style analysis (Sharpe 1992)

Find non-negative weights summing to 1 on style indices (Nifty 50, Next 50, Midcap 150, Smallcap 250, cash) that
best replicate the fund's monthly returns. $R^2$ = share explained by style; $1-R^2$ = selection."""),
    code("""quiet(t3_style)
display(pd.read_csv(A.RES / "t3/style_full_period.csv", index_col=0).round(4))
show("t3/style_rolling_36m.png")"""),
    md(r"""## 5. Four-factor alpha and capture ratios

$r_{fund}-r_f=\alpha+\beta_1 MKT+\beta_2 SMB+\beta_3 HML+\beta_4 WML+\varepsilon$ with IIMA Indian factors and
Newey-West standard errors. **Control:** the same regression on the passive Midcap 150 index fund. If the passive
fund also shows "alpha", the model is mispricing mid caps, not detecting skill."""),
    code("""quiet(t4_alpha_capture)
display(pd.read_csv(A.RES / "t4/carhart_alpha.csv").set_index("series").T)
display(pd.read_csv(A.RES / "t4/up_down_capture.csv").set_index("vs").T)
show("t4/rolling_36m_alpha.png")"""),
    md("""## 6. Skill vs luck (bootstrap, Kosowski et al. 2006; Fama & French 2010)

Set every mid-cap fund's alpha to zero, resample months jointly (same months for all funds and factors), and
re-estimate the t-statistics 2,000 times. If the fund's actual t is rarely reached by these luck-only runs, it is
evidence of skill. Run twice: against the IIMA factors, and against the passive mid-cap benchmark itself."""),
    code("""quiet(t5_skill_luck)
for model in ["carhart_iima", "benchmark_mid150"]:
    display(Markdown(f"**Model: {model}**"))
    display(pd.read_csv(A.RES / f"t5/{model}/target_summary.csv", index_col=0))
    display(pd.read_csv(A.RES / f"t5/{model}/cross_section_percentiles.csv").round(3))
    show(f"t5/{model}/target_t_vs_bootstrap.png", width=650)"""),
    md("## 7. Category league table (benchmark-relative model)"),
    code("""pd.read_csv(A.RES / "t5/benchmark_mid150/category_alpha_t_and_bootstrap_p.csv", index_col=0).round(3)"""),
    md("""## 8. Reading the results

* The fund beat its benchmark after fees, mainly by **falling less in down months** (down-capture < up-capture).
* **Stock selection was strong**, but **sector and cash bets cost about as much** as selection added (Brinson).
* **High active share** (~0.8): the fund is genuinely different from its index.
* The IIMA four-factor alpha looks large and significant, but the **passive mid-cap index fund also earns "alpha"**
  in that model, and almost every mid-cap fund looks skilled. Against the mid-cap benchmark, the fund's alpha is
  **not distinguishable from luck**.

See `docs/findings.md` for the full write-up and `README.md` for data sources and caveats."""),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                                                "language_info": {"name": "python"}})
nbf.write(nb, Path(__file__).with_name("P3_walkthrough.ipynb"))
print("written notebooks/P3_walkthrough.ipynb")
