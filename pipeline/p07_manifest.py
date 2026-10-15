"""Pipeline 7 - Manifest of the analysis inputs (data/processed/MANIFEST.csv): rows, columns, date range, SHA-256.

Lets anyone verify that their rebuilt inputs match the committed snapshot (or see exactly what changed).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> p3config

import pandas as pd  # noqa: E402

from p3config import PROCESSED, TODAY, log  # noqa: E402


def main() -> None:
    rows = []
    for p in sorted(PROCESSED.glob("*.csv")):
        if p.name == "MANIFEST.csv":
            continue
        df = pd.read_csv(p, low_memory=False)
        dcol = next((c for c in ("month_end", "date", "publish_date") if c in df.columns), None)
        rng = f"{pd.to_datetime(df[dcol]).min().date()}..{pd.to_datetime(df[dcol]).max().date()}" if dcol else ""
        rows.append({"file": p.name, "rows": len(df), "columns": len(df.columns), "date_range": rng,
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "built": TODAY})
    pd.DataFrame(rows).to_csv(PROCESSED / "MANIFEST.csv", index=False)
    log("p07_manifest", "write", f"{len(rows)} files")


if __name__ == "__main__":
    main()
