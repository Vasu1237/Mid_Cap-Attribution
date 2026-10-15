"""Pipeline 3 - Parse MOAMC month-end portfolio workbooks into holdings for:
  * target: Motilal Oswal Midcap Fund (earlier names: MOSt Focused Midcap 30 Fund, Midcap 30 Fund)
  * benchmark proxy: Motilal Oswal Nifty Midcap 150 Index Fund (holds the index -> proxy for benchmark weights)
Each workbook has one sheet per scheme; the scheme is identified from its title rows (not the sheet code, which can
change). Columns are located from the header row containing 'ISIN'. Rows kept = those with an Indian equity ISIN.
Also extracted per month: AUM (grand total, Rs lakh), Direct-plan TER, portfolio turnover, stated benchmark.
Files are untrusted downloads: read with pandas only (no macros executed).
Outputs: data/processed/holdings_monthly.csv, fund_monthly_meta.csv, portfolio_parse_misses.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> p3config

import re
import warnings

import pandas as pd

from p3config import RAW, log, processed, save_processed

warnings.filterwarnings("ignore")
TARGET = re.compile(r"motilal oswal (most focused )?mid\s*cap\s*(30\s*)?fund", re.I)
PROXY = re.compile(r"nifty\s*midcap\s*150 index fund", re.I)
EXCLUDE = re.compile(r"index|etf|large|momentum|plus|g-sec|fund of fund", re.I)
ISIN = re.compile(r"^INE[0-9A-Z]{9}$")
MONTHS = {m: i for i, m in enumerate(["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                                      "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], 1)}


def as_of(head: str) -> pd.Timestamp | None:
    m = re.search(r"AS ON\s+([A-Z]+)\s*(\d{1,2})?,?\s*(\d{4})", head.upper())
    if m and m.group(1) in MONTHS:
        return pd.Timestamp(int(m.group(3)), MONTHS[m.group(1)], 1) + pd.offsets.MonthEnd(0)
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", head)
    return pd.Timestamp(int(m.group(3)), int(m.group(2)), 1) + pd.offsets.MonthEnd(0) if m else None


def classify(s: pd.DataFrame) -> str | None:
    """Role of a scheme sheet from its title row (first top row naming a Motilal Oswal scheme, not the AMC lines)."""
    lines = (re.sub(r"^\s*(back to index|YO\d+)\s*", "", " ".join(str(v) for v in row if str(v) != "nan"), flags=re.I)
             for row in s.head(12).values.tolist())
    title = next((ln for ln in lines if re.match(r"\s*motilal oswal .*(fund|etf)", ln, re.I)
                  and not re.search(r"asset management", ln, re.I)), "")
    title = re.sub(r"\(formerly known as[^)]*\)", "", title, flags=re.I)
    if PROXY.search(title):
        return "benchmark_proxy_midcap150_index_fund"
    if TARGET.search(title) and not EXCLUDE.search(title):
        return "target_midcap_fund"
    return None


def parse_sheet(s: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    txt = s.astype(str)
    hdr_rows = txt.index[txt.apply(lambda r: r.str.strip().str.upper().str.match(r"^ISIN( CODE)?$").any(), axis=1)]
    if not len(hdr_rows):
        return pd.DataFrame(), {}
    h = [str(c).strip().lower() for c in s.iloc[hdr_rows[0]]]
    col = lambda *k: next((i for i, c in enumerate(h) if all(x in c for x in k)), None)  # noqa: E731
    ci, cn, cind, cq, cv, cp = col("isin"), col("name"), col("industry"), col("quantity"), col("market"), col("% to"),
    if cp is None:
        cp = col("net asset")
    rows = []
    for _, r in s.iloc[hdr_rows[0] + 1:].iterrows():
        isin = str(r.iloc[ci]).strip()
        if ISIN.match(isin):
            rows.append({"isin": isin, "name": r.iloc[cn] if cn is not None else None,
                         "industry": r.iloc[cind] if cind is not None else None,
                         "quantity": pd.to_numeric(r.iloc[cq], errors="coerce") if cq is not None else None,
                         "value_lakh": pd.to_numeric(r.iloc[cv], errors="coerce") if cv is not None else None,
                         "pct_nav_raw": pd.to_numeric(r.iloc[cp], errors="coerce") if cp is not None else None})
    meta = {}
    flat = [" ".join(str(v) for v in row if str(v) != "nan") for row in s.values.tolist()]
    for i, line in enumerate(flat):
        lu = line.upper()
        if "GRAND TOTAL" in lu:
            nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", line.replace(",", ""))]
            if nums:
                meta["aum_lakh"] = max(nums)
        if lu.startswith("DIRECT PLAN :") or lu.startswith("DIRECT PLAN:"):
            v = re.findall(r"\d*\.\d+", line)
            meta.setdefault("ter_direct", float(v[0]) if v else None)
        if "PORTFOLIO TURNOVER" in lu:
            v = re.findall(r"\d*\.\d+|\d+", line.split("Ratio")[-1] if "Ratio" in line else line)
            meta.setdefault("turnover", float(v[-1]) if v else None)
        if "BENCHMARK NAME" in lu:
            meta["benchmark"] = line.split("-", 1)[-1].strip() if "-" in line else line
    return pd.DataFrame(rows), meta


def main() -> None:
    files = pd.read_csv(processed("portfolio_files"), parse_dates=["publish_date"])
    hold, meta_rows, misses = [], [], []
    files = files[~files["file"].str.contains("fortnight|forthnight", case=False)]
    for _, f in files[files["downloaded"]].iterrows():
        p = RAW / "moamc" / "files" / f["file"]
        try:
            x = pd.ExcelFile(p)
        except Exception as e:  # noqa: BLE001
            misses.append((f["file"], f"unreadable: {str(e)[:60]}"))
            continue
        found = set()
        for sh in x.sheet_names:
            try:
                s = x.parse(sh, header=None, nrows=400)
            except Exception:  # noqa: BLE001
                continue
            head = " ".join(str(v) for v in s.head(12).values.ravel() if str(v) != "nan")
            role = classify(s)
            if not role or role in found:
                continue
            h, meta = parse_sheet(s)
            if h.empty:
                continue
            d = as_of(head)
            found.add(role)
            h["role"], h["month_end"], h["file"] = role, d, f["file"]
            hold.append(h)
            meta_rows.append({"role": role, "month_end": d, "file": f["file"], "n_holdings": len(h),
                              "pct_sum_raw": h["pct_nav_raw"].sum(), **meta})
        if "target_midcap_fund" not in found:
            misses.append((f["file"], "target sheet not found"))
    H = pd.concat(hold, ignore_index=True)
    # % to net assets is stored either as percent (94.8) or fraction (0.948) depending on the year
    scale = H.groupby(["role", "month_end", "file"])["pct_nav_raw"].transform("sum")  # per file: formats differ by file
    H["weight_nav"] = H["pct_nav_raw"] / scale.where(scale <= 2, 100).where(scale > 2, 1)
    M = pd.DataFrame(meta_rows)
    # one source file per (role, month): if a month appears in several files (factsheet, half-yearly, re-uploads),
    # keep the file with the most holdings so rows are never mixed across files
    M = M.sort_values(["role", "month_end", "n_holdings"], ascending=[True, True, False]).drop_duplicates(["role", "month_end"])
    n0 = len(H)
    H = H.merge(M[["role", "month_end", "file"]], on=["role", "month_end", "file"])
    H = H.drop_duplicates(["role", "month_end", "isin"], keep="first")
    log("p03_parse", "holdings", f"{H.groupby('role').month_end.nunique().to_dict()} months; one file per role-month", n0, len(H))
    log("p03_parse", "misses", f"{len(misses)} files without target sheet: {misses[:6]}")
    save_processed(H, "holdings_monthly")
    save_processed(M, "fund_monthly_meta")
    save_processed(pd.DataFrame(misses, columns=["file", "issue"]), "portfolio_parse_misses")


if __name__ == "__main__":
    main()
