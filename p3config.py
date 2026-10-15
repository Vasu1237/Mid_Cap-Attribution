"""Project-wide configuration and helpers for the P3 replication package.

Every path is relative to this file, so the repository works wherever it is cloned.

    data/raw/        untouched downloads (HTTP cache; git-ignored, rebuilt by `python run_all.py --rebuild`)
    data/processed/  analysis inputs (committed snapshot, stable file names; see data/processed/MANIFEST.csv)
    results/         every table (.csv) and chart (.png) produced by analysis/t*.py
    logs/            transformations.csv - one line per transformation step (git-ignored)
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"
for _d in (RAW, PROCESSED, RESULTS, LOGS):
    _d.mkdir(parents=True, exist_ok=True)

TODAY = dt.date.today().isoformat()
UA = "Mozilla/5.0 (academic replication package; P3 MOAMC fund attribution)"

# ---- study definition ----
FUND = {"name": "Motilal Oswal Midcap Fund - Direct Plan - Growth", "amfi_code": 127042, "isin": "INF247L01445",
        "benchmark": "Nifty Midcap 150 TRI"}
# MOAMC index funds (Direct plan) whose NAVs proxy the index TRIs (TRI download from niftyindices.com is not permitted)
PROXY_CODES = {147622: "MID150", 147794: "N50", 147796: "NN50", 147625: "N500", 147623: "SC250"}
AMFI_CATEGORY = "Equity Scheme - Mid Cap Fund"
IIMA_RELEASE = "2025-12"  # IIMA Indian Fama-French-Momentum release used (pin for reproducibility)


def log(item: str, step: str, detail: str, rows_in: int | None = None, rows_out: int | None = None) -> None:
    """Append one transformation to logs/transformations.csv and echo it."""
    path = LOGS / "transformations.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "item", "step", "detail", "rows_in", "rows_out"])
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), item, step, detail, rows_in, rows_out])
    print(f"[{item}] {step}: {detail}" + (f" ({rows_in} -> {rows_out})" if rows_in is not None else ""))


def save_processed(df, name: str) -> Path:
    """Write an analysis input to data/processed/<name>.csv (stable name, overwritten on rebuild)."""
    p = PROCESSED / f"{name}.csv"
    df.to_csv(p, index=False)
    log(name, "save", str(p.relative_to(ROOT)), rows_out=len(df))
    return p


def processed(name: str) -> Path:
    p = PROCESSED / f"{name}.csv"
    if not p.exists():
        raise FileNotFoundError(f"{p.relative_to(ROOT)} missing - run `python run_all.py --rebuild` (see README)")
    return p


class RateLimiter:
    """Sliding-window limiter supporting several (max_calls, seconds) windows."""

    def __init__(self, *windows: tuple[int, float]):
        self.windows = windows
        self.calls: list[float] = []

    def wait(self) -> None:
        while True:
            now = time.monotonic()
            longest = max(s for _, s in self.windows)
            self.calls = [t for t in self.calls if now - t < longest]
            sleep = 0.0
            for n, s in self.windows:
                recent = [t for t in self.calls if now - t < s]
                if len(recent) >= n:
                    sleep = max(sleep, s - (now - recent[0]) + 0.01)
            if sleep <= 0:
                self.calls.append(now)
                return
            time.sleep(sleep)


def cached_get(url: str, cache_file: Path, headers: dict | None = None,
               limiter: RateLimiter | None = None, retries: int = 4, timeout: int = 120) -> bytes:
    """GET url, caching the raw bytes to cache_file. Cached files are never re-downloaded."""
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return cache_file.read_bytes()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    h = {"User-Agent": UA}
    h.update(headers or {})
    for attempt in range(retries):
        if limiter:
            limiter.wait()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                data = r.read()
            tmp = cache_file.with_suffix(cache_file.suffix + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, cache_file)
            return data
        except HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt * 5)
                continue
            raise
    raise RuntimeError("unreachable")


def gunzip_json(b: bytes):
    return json.loads(gzip.decompress(b))


def upstox_token() -> str:
    """Upstox API access token from the UPSTOX_ACCESS_TOKEN environment variable (never stored in the repo)."""
    t = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    if not t:
        raise SystemExit("Set UPSTOX_ACCESS_TOKEN (daily token from your Upstox developer app) to rebuild stock prices.\n"
                         "Not needed to reproduce the results: the committed data/processed snapshot is enough.")
    return t
