"""Reproduce every P3 result from the committed data snapshot - one command.

    python run_all.py                     # analysis (tests 1-5 + charts) from data/processed, then execute the notebook
    python run_all.py --no-notebook       # analysis only
    python run_all.py --rebuild           # re-download everything first (AMFI, MOAMC, Upstox, IIMA), then analyse
                                          # needs env var UPSTOX_ACCESS_TOKEN for stock prices; ~1.5-2 hours (slow servers)
    python run_all.py --rebuild --local-prices FILE.csv   # rebuild, but take daily closes (date,isin,close) from FILE

Outputs: results/t0..t5 (CSV tables + PNG charts), notebooks/P3_walkthrough.ipynb (executed, with charts),
logs/transformations.csv (every pipeline/analysis step).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PIPELINE = ["p01_amfi_nav", "p02_moamc_portfolios_download", "p03_moamc_portfolios_parse", "p04_upstox_instruments",
            "p05_stock_prices", "p06_iima_factors", "p07_manifest"]
ANALYSIS = ["t1_brinson", "t2_active_share", "t3_style", "t4_alpha_capture", "t5_skill_luck", "t6_charts"]


def run(script: Path, *extra: str) -> None:
    t = time.time()
    print(f"\n=== {script.relative_to(ROOT)} {' '.join(extra)}", flush=True)
    r = subprocess.run([sys.executable, "-W", "ignore", str(script), *extra], cwd=ROOT)
    if r.returncode:
        sys.exit(f"FAILED: {script.name} (exit {r.returncode})")
    print(f"    ok ({time.time() - t:.0f}s)")


def execute_notebook(path: Path) -> None:
    try:
        import nbformat
        from nbclient import NotebookClient
    except ImportError:
        print("nbformat/nbclient not installed - skipping notebook (pip install -r requirements.txt)")
        return
    print(f"\n=== executing {path.relative_to(ROOT)}", flush=True)
    nb = nbformat.read(path, as_version=4)
    NotebookClient(nb, timeout=1800, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}}).execute()
    nbformat.write(nb, path)
    print("    ok")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true", help="re-download and rebuild data/processed first")
    ap.add_argument("--local-prices", type=Path, help="with --rebuild: daily closes CSV (date,isin,close) instead of the Upstox API")
    ap.add_argument("--no-notebook", action="store_true", help="do not execute the walkthrough notebook")
    a = ap.parse_args()
    if a.rebuild:
        for s in PIPELINE:
            extra = ("--local-prices", str(a.local_prices)) if (s == "p05_stock_prices" and a.local_prices) else ()
            run(ROOT / "pipeline" / f"{s}.py", *extra)
    for s in ANALYSIS:
        run(ROOT / "analysis" / f"{s}.py")
    if not a.no_notebook:
        execute_notebook(ROOT / "notebooks" / "P3_walkthrough.ipynb")
    print("\nDone. Tables and charts are in results/; start with README.md and notebooks/P3_walkthrough.ipynb.")


if __name__ == "__main__":
    main()
