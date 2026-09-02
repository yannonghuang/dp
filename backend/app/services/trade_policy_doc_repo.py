"""
Local doc repo for US–China relationship (trade_policy).
- Repo path: TRADE_POLICY_DOCS_PATH (e.g. data/trade_policy_docs).
- Folders and/or files named MM_YYYY (e.g. 01_2023, 02_2023, ..., 12_2024) hold documents for that month.
- Backend reads from these to generate indices (text → numeric per month).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import TRADE_POLICY_DOCS_PATH

# Match MM_YYYY (e.g. 01_2023, 12_2024) for folder or filename (without extension).
MONTH_FOLDER_PATTERN = re.compile(r"^(0[1-9]|1[0-2])_(\d{4})$")

TEXT_EXTENSIONS = {".txt", ".md", ".html", ".htm"}


def _mm_yyyy_to_year_month(mm_yyyy: str) -> str:
    """Convert MM_YYYY to YYYY-MM."""
    m, y = mm_yyyy.split("_")
    return f"{y}-{m}"


def list_month_folders(repo_path: Path | None = None) -> list[str]:
    """
    List month folders in the repo (MM_YYYY). Returns sorted list of YYYY-MM.
    Checks both direct folders and direct files named MM_YYYY.*.
    """
    path = (repo_path or TRADE_POLICY_DOCS_PATH).resolve()
    if not path.exists() or not path.is_dir():
        return []
    seen: set[str] = set()
    # Directories named MM_YYYY
    for child in path.iterdir():
        if child.is_dir() and MONTH_FOLDER_PATTERN.match(child.name):
            ym = _mm_yyyy_to_year_month(child.name)
            seen.add(ym)
    # Files named MM_YYYY.ext
    for child in path.iterdir():
        if child.is_file():
            base = child.stem
            if MONTH_FOLDER_PATTERN.match(base):
                ym = _mm_yyyy_to_year_month(base)
                seen.add(ym)
    return sorted(seen)


def read_month_docs(repo_path: Path | None, year_month: str) -> str:
    """
    Read all document text for a given month. year_month is YYYY-MM.
    Looks for folder MM_YYYY (e.g. 01_2023) or file MM_YYYY.* and concatenates text.
    """
    path = (repo_path or TRADE_POLICY_DOCS_PATH).resolve()
    if not path.exists() or not path.is_dir():
        return ""
    m, y = year_month.split("-")
    mm_yyyy = f"{m}_{y}"
    parts: list[str] = []

    # Folder MM_YYYY: read all .txt, .md, .html
    folder = path / mm_yyyy
    if folder.is_dir():
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix.lower() in TEXT_EXTENSIONS:
                try:
                    parts.append(f.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass

    # Single file MM_YYYY.ext at repo root
    for ext in TEXT_EXTENSIONS:
        f = path / f"{mm_yyyy}{ext}"
        if f.is_file():
            try:
                parts.append(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
            break  # one file per month at root is enough

    return "\n\n".join(parts).strip()


def generate_indices_from_repo(
    index_id: str = "trade_policy",
    repo_path: Path | None = None,
    start_ym: str | None = None,
    end_ym: str | None = None,
    drivers_path: Path | None = None,
):
    """
    Read doc repo month-by-month, run text→numeric for each month, write to external_drivers.csv.
    Returns (applied_count, rows_in_csv).
    """
    from app.services.external_drivers_subsystem import get_registry, update_values
    from app.services.text_to_numeric import text_to_numeric
    from app.config import EXTERNAL_DRIVERS_PATH

    reg = next((r for r in get_registry() if r["id"] == index_id), None)
    if reg is None:
        raise ValueError(f"Unknown index_id: {index_id}")
    if reg.get("deterministic", True):
        raise ValueError(f"Index {index_id} is deterministic; use fetch or CSV")

    months = list_month_folders(repo_path)
    if not months:
        return 0, 0
    if start_ym:
        months = [m for m in months if m >= start_ym]
    if end_ym:
        months = [m for m in months if m <= end_ym]
    if not months:
        return 0, 0

    path = drivers_path or EXTERNAL_DRIVERS_PATH

    def _score_month(ym: str) -> dict:
        text = read_month_docs(repo_path, ym)
        value, _ = text_to_numeric(index_id, text or "(no content)", ym)
        return {"year_month": ym, index_id: value}

    # Each call is a blocking LLM request; run months concurrently so total
    # latency is roughly max(per-call latency) instead of sum(per-call latency).
    with ThreadPoolExecutor(max_workers=min(8, len(months))) as executor:
        rows = list(executor.map(_score_month, months))

    df = update_values(rows, path=path)
    return len(rows), len(df)
