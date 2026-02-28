#!/usr/bin/env python3
"""
Quick test for the US–China doc repo crawler: fetch one month with one source.
Run from project root with backend on PYTHONPATH, e.g.:
  cd /path/to/dp && PYTHONPATH=backend python scripts/test_trade_policy_crawl.py

Uses a temp directory by default so the real doc repo is not modified.
"""

import os
import sys
import tempfile
from pathlib import Path

# Allow running from repo root with backend on path
if __name__ == "__main__":
    backend = Path(__file__).resolve().parent.parent / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

from app.services.trade_policy_crawler import (
    get_crawl_urls,
    crawl_month,
)


def main() -> None:
    urls = get_crawl_urls()
    if not urls:
        print("No crawl URLs (trade_policy starter_sources missing or no url).")
        sys.exit(1)
    print(f"Testing {len(urls)} source(s): {[u[0] for u in urls]}")
    print()

    use_temp = os.environ.get("CRAWL_TEST_USE_REAL_REPO", "").lower() not in ("1", "true", "yes")
    if use_temp:
        with tempfile.TemporaryDirectory() as tmp:
            repo_path = Path(tmp)
            print(f"Using temp repo: {repo_path}")
            written = crawl_month(
                "2024-01",
                repo_path=repo_path,
                max_articles_per_month=1,
                delay=1.0,
            )
            print(f"Files written for 2024-01: {written}")
            if written > 0:
                month_dir = repo_path / "01_2024"
                for f in month_dir.iterdir():
                    size = f.stat().st_size
                    print(f"  {f.name}: {size} bytes")
                print("\nTest passed (crawler fetched at least one source).")
            else:
                print("No files written (sites may block non-browser requests or timeout). Try from UI with Crawl & save.")
    else:
        from app.config import TRADE_POLICY_DOCS_PATH
        print(f"Using real repo: {TRADE_POLICY_DOCS_PATH}")
        written = crawl_month(
            "2024-01",
            repo_path=TRADE_POLICY_DOCS_PATH,
            max_articles_per_month=2,
            delay=1.0,
        )
        print(f"Files written for 2024-01: {written}")
    print("\nSuggested reliable sources (tested):")
    print("  1. CSIS China — https://www.csis.org/regions/asia/china")
    print("  2. CFR China  — https://www.cfr.org/asia/china")
    print("  3. Pew China global image — https://www.pewresearch.org/topic/international-affairs/global-image-of-countries/china-global-image/")


if __name__ == "__main__":
    main()
