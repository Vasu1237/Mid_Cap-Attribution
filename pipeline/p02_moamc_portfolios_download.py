"""Pipeline 2 - Download MOAMC month-end portfolio disclosures (SEBI-mandated public disclosure, all schemes per file).

Source: motilaloswalmf.com > Downloads > Scheme Portfolio Details. The file list comes from the site's own document
API (search-documents.json?category=month end portfolio), which the downloads page calls.
robots.txt (checked 2026-10-15): "User-agent: * Allow: /". The legal-disclaimer page
did not render, so written terms could NOT be read - flagged in README. Polite: 1 request/second, cached, month-end
files only (fortnightly reports skipped).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> p3config

import json
import urllib.parse

import pandas as pd

from p3config import TODAY, RAW, RateLimiter, cached_get, log, save_processed

BASE = "https://www.motilaloswalmf.com"
LIST = BASE + "/content/aem-cloud-dept-backend-motilal-oswal/api/search-documents.json?year=&category=month%20end%20portfolio&month=&type=mf"


def main() -> None:
    lim = RateLimiter((1, 1.0))
    docs = json.loads(cached_get(LIST, RAW / "moamc" / f"doclist_{TODAY}.json"))["results"]
    keep = [d for d in docs if "fortnight" not in (d["title"] + d["path"]).lower()]
    rows = []
    for d in keep:
        name = d["path"].rsplit("/", 1)[-1]
        dest = RAW / "moamc" / "files" / f"{d['publishDate'][6:]}{d['publishDate'][3:5]}{d['publishDate'][:2]}_{name}"
        url = BASE + urllib.parse.quote(d["path"])
        ok = True
        try:
            cached_get(url, dest, limiter=lim)
        except Exception as e:  # noqa: BLE001
            ok = False
            log("p02_portfolios", "error", f"{name}: {str(e)[:80]}")
        rows.append({"publish_date": pd.to_datetime(d["publishDate"], dayfirst=True), "title": d["title"], "file": dest.name,
                     "mime": d["mimeType"], "downloaded": ok, "url": url})
    df = pd.DataFrame(rows).sort_values("publish_date")
    log("p02_portfolios", "download", f"{df.downloaded.sum()}/{len(df)} month-end files ({df.publish_date.min().date()}..{df.publish_date.max().date()})")
    save_processed(df, "portfolio_files")


if __name__ == "__main__":
    main()
