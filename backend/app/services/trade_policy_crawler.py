"""
Crawler for US–China relationship doc repo: fetch reliable public sources and save to MM_YYYY folders.
Uses starter_sources from trade_policy registry; respects basic rate limiting.

Important: Source pages (CFR, CSIS, Pew) show current/latest content, not historical content per month.
So we support two modes:
- snapshot_only=True (default): fetch each URL once and save only to the current month folder (e.g. 02_2026).
  Dates then match: the folder is the month of the crawl, and the content is from that time.
- snapshot_only=False: for each month in [start, end], fetch the same URLs and save to that month's folder.
  Every folder gets the same current snapshot (content does not match folder date); only use if you run
  the crawler monthly over time to build a time series.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

from app.config import TRADE_POLICY_DOCS_PATH
from app.services.external_drivers_subsystem import get_registry

# Default delay between requests (seconds) to be polite.
DEFAULT_DELAY = 2.0

USER_AGENT = "Mozilla/5.0 (compatible; TradePolicyDocBot/1.0; +https://github.com/your-org/dp)"

# Cancel flag: when set, crawl_range stops after the current month.
_crawl_cancel_requested = False


def request_crawl_cancel() -> None:
    """Ask the running crawl to stop after the current month."""
    global _crawl_cancel_requested
    _crawl_cancel_requested = True


def clear_crawl_cancel() -> None:
    """Clear the cancel flag (call at start of a new crawl)."""
    global _crawl_cancel_requested
    _crawl_cancel_requested = False


def _year_month_to_mm_yyyy(year_month: str) -> str:
    """Convert YYYY-MM to MM_YYYY."""
    y, m = year_month.split("-")
    return f"{m}_{y}"


def _extract_text_from_html(html: str) -> str:
    """Extract main text from HTML; strip scripts and nav."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)[:50000]
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:50000]


def _fetch_url(url: str, timeout: int = 20) -> str:
    """Fetch URL and return response text. Raises on non-2xx or timeout."""
    import requests
    # Prefer a common browser User-Agent so some sites don't block
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.text


def get_crawl_urls() -> list[tuple[str, str]]:
    """Return list of (source_id, url) from trade_policy starter_sources."""
    reg = next((r for r in get_registry() if r["id"] == "trade_policy"), None)
    if not reg:
        return []
    sources = reg.get("starter_sources") or []
    return [(s["id"], s["url"]) for s in sources if s.get("url")]


def crawl_month(
    year_month: str,
    repo_path: Path | None = None,
    urls: list[tuple[str, str]] | None = None,
    delay: float = DEFAULT_DELAY,
    max_articles_per_month: int | None = None,
    errors: list[tuple[str, str]] | None = None,
) -> int:
    """
    For one month (YYYY-MM), create folder MM_YYYY, fetch up to max_articles_per_month URLs, save text to source_id.txt.
    If errors list is provided, append (source_id, error_message) for each failed fetch or empty content.
    Returns number of files written.
    """
    path = (repo_path or TRADE_POLICY_DOCS_PATH).resolve()
    path.mkdir(parents=True, exist_ok=True)
    mm_yyyy = _year_month_to_mm_yyyy(year_month)
    folder = path / mm_yyyy
    folder.mkdir(parents=True, exist_ok=True)
    urls = urls or get_crawl_urls()
    if max_articles_per_month is not None and max_articles_per_month >= 1:
        urls = urls[:max_articles_per_month]
    written = 0
    for source_id, url in urls:
        safe_id = re.sub(r"[^\w-]", "_", source_id)
        out_file = folder / f"{safe_id}.txt"
        try:
            html = _fetch_url(url)
            text = _extract_text_from_html(html)
            if text:
                out_file.write_text(text, encoding="utf-8")
                written += 1
            elif errors is not None:
                errors.append((source_id, "empty content after fetch"))
        except Exception as e:
            if errors is not None:
                errors.append((source_id, str(e)))
        time.sleep(delay)
    return written


def _current_year_month() -> str:
    """Return current YYYY-MM from server date."""
    now = datetime.now()
    return f"{now.year}-{now.month:02d}"


def crawl_range(
    start_ym: str,
    end_ym: str,
    repo_path: Path | None = None,
    delay: float = DEFAULT_DELAY,
    max_duration_seconds: float | None = None,
    max_articles_per_month: int | None = None,
    snapshot_only: bool = True,
) -> tuple[dict[str, int], bool, str | None, list[tuple[str, str]]]:
    """
    Fetch source pages and save to doc repo.
    - If snapshot_only=True (default): fetch each URL once, save only to current month folder (e.g. 02_2026).
      Content and folder date match (current snapshot).
    - If snapshot_only=False: for each month in [start_ym, end_ym], fetch same URLs and save to that folder.
      Every folder gets the same current content; only sensible if you run the crawler monthly over time.
    Returns (result dict, cancelled, halt_reason, errors).
    """
    global _crawl_cancel_requested
    clear_crawl_cancel()
    start_time = time.monotonic()

    if snapshot_only:
        # One folder = current month; fetch once per source.
        ym = _current_year_month()
        last_errors: list[tuple[str, str]] = []
        written = crawl_month(
            ym,
            repo_path=repo_path,
            delay=delay,
            max_articles_per_month=max_articles_per_month,
            errors=last_errors,
        )
        return {ym: written}, False, None, last_errors

    sy, sm = map(int, start_ym.split("-"))
    ey, em = map(int, end_ym.split("-"))
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    result = {}
    last_errors = []
    for ym in months:
        if _crawl_cancel_requested:
            return result, True, "cancel", last_errors
        if max_duration_seconds is not None and max_duration_seconds > 0:
            if (time.monotonic() - start_time) >= max_duration_seconds:
                return result, True, "time_limit", last_errors
        last_errors = []
        result[ym] = crawl_month(
            ym,
            repo_path=repo_path,
            delay=delay,
            max_articles_per_month=max_articles_per_month,
            errors=last_errors,
        )
    return result, False, None, last_errors
