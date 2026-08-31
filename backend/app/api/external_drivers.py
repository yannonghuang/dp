"""
External drivers API: schema (indices), get/update values, populate.
Designed so a future agent can use GET schema to guide users and POST to persist choices.

Future agent extension (not implemented):
  - GET /api/external-drivers/suggest — agent suggests indices or values from context.
  - POST /api/external-drivers/guide — agent guides user through choosing indices and populating.
"""

import csv
import io
import math
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.services.external_drivers_subsystem import (
    get_registry,
    get_required_year_months,
    load_drivers_csv,
    populate,
    reset_drivers_csv,
    update_values,
    fetch_and_populate,
)
from app.services.i18n import t, translate_registry

router = APIRouter(prefix="/api/external-drivers", tags=["external-drivers"])


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if pd.isna(obj):
        return None
    return obj


@router.get("/schema")
def get_schema(lang: str = Query("en", description="UI language for names/descriptions: en or zh")):
    """
    Return the pre-determined set of external indices (id, name, description, default_value, unit).
    Future: agent can extend or suggest indices; this is the source of truth for "available indices".
    """
    registry = translate_registry(get_registry(), lang)
    year_months = get_required_year_months()
    return {
        "indices": registry,
        "required_year_months": year_months,
        "learn_period": year_months[:12] if len(year_months) >= 12 else year_months,
        "forecast_period": [ym for ym in year_months if ym.startswith("2024-")] or year_months[-12:],
    }


@router.post("/reset")
def post_reset(lang: str = Query("en")):
    """Clear the indices table (external_drivers.csv). Writes header-only file."""
    reset_drivers_csv()
    return {"message": t("indices_cleared", lang)}


@router.get("")
def get_values(
    start: str | None = Query(None, description="Start year_month e.g. 2023-01"),
    end: str | None = Query(None, description="End year_month e.g. 2024-12"),
    lang: str = Query("en"),
):
    """Return current external driver values (from CSV). Optional start/end filter."""
    df = load_drivers_csv()
    if df.empty:
        return {"rows": [], "message": t("no_drivers_file", lang)}
    if start:
        df = df[df["year_month"] >= start]
    if end:
        df = df[df["year_month"] <= end]
    return {"rows": _json_safe(df.to_dict(orient="records"))}


class UpdateValuesBody(BaseModel):
    values: list[dict]  # [{ year_month, industry_sentiment?, trade_policy?, us_semi_tariff_china? }, ...]


@router.post("/values")
def post_values(body: UpdateValuesBody):
    """Update external driver values. Merges with existing CSV. Each row can have year_month + any index columns."""
    if not body.values:
        raise HTTPException(status_code=400, detail="values must be non-empty")
    df = update_values(body.values)
    return {"rows": len(df), "message": "Updated external_drivers.csv", "sample": _json_safe(df.head(3).to_dict(orient="records"))}


class FetchBody(BaseModel):
    indices: list[str]  # e.g. ["industry_sentiment", "us_semi_tariff_china"]
    source_overrides: dict[str, dict] | None = None  # e.g. { "tax_index": { "type": "url", "url": "..." } } or { "type": "custom", "url": "..." }
    lang: str = "en"


@router.post("/fetch")
def post_fetch(body: FetchBody):
    """
    Backend fetches raw data from configured sources for selected indices and populates external_drivers.csv.
    Use source_overrides to pick a suggested source or your own (type "custom" with "url" or "path").
    Only indices in body.indices are included. Use GET /schema to see available indices and suggested_sources.
    """
    from app.config import EXTERNAL_DRIVERS_PATH
    if not body.indices:
        raise HTTPException(status_code=400, detail="indices must be non-empty")
    try:
        df = fetch_and_populate(
            index_ids=body.indices,
            output_path=EXTERNAL_DRIVERS_PATH,
            source_overrides=body.source_overrides,
        )
        if df.empty:
            raise HTTPException(status_code=400, detail="No valid indices selected or fetch failed")
        return {
            "rows": len(df),
            "indices": list(df.columns.drop("year_month")),
            "path": str(EXTERNAL_DRIVERS_PATH),
            "message": t("fetched_and_populated", body.lang),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/populate")
def post_populate(
    overrides_path: str | None = Query(None, description="Optional path to overrides CSV (relative to DATA_DIR)"),
):
    """
    Populate external_drivers.csv for learn + forecast periods using registry defaults and optional overrides.
    Writes to EXTERNAL_DRIVERS_PATH. Future: agent could trigger this after guiding user to choose indices.
    """
    from pathlib import Path
    from app.config import DATA_DIR, EXTERNAL_DRIVERS_PATH
    overrides = Path(DATA_DIR) / overrides_path if overrides_path else None
    if overrides_path and not overrides.exists():
        raise HTTPException(status_code=400, detail=f"Overrides file not found: {overrides}")
    df = populate(overrides_path=overrides, output_path=EXTERNAL_DRIVERS_PATH)
    return {"rows": len(df), "path": str(EXTERNAL_DRIVERS_PATH), "message": "Populated external_drivers.csv"}


class ProcessTextBody(BaseModel):
    index_id: str  # e.g. "trade_policy"
    text: str
    year_month: str | None = None  # e.g. "2024-01"; optional, for apply


@router.post("/process-text")
def post_process_text(body: ProcessTextBody):
    """
    Convert raw text to a numeric score for a non-deterministic index (e.g. US–China relationship).
    Uses LLM when OPENAI_API_KEY is set; otherwise returns stub. Returns value and optional year_month.
    """
    from app.services.text_to_numeric import text_to_numeric
    reg = next((r for r in get_registry() if r["id"] == body.index_id), None)
    if reg is None:
        raise HTTPException(status_code=400, detail="Unknown index_id")
    if reg.get("deterministic", True):
        raise HTTPException(status_code=400, detail="Index is deterministic; use fetch or CSV for numeric data")
    value, ym = text_to_numeric(body.index_id, body.text, body.year_month)
    return {"value": value, "year_month": ym, "index_id": body.index_id}


class ProcessTextAndApplyBody(BaseModel):
    index_id: str
    text: str
    year_month: str  # required for apply


@router.post("/process-text-and-apply")
def post_process_text_and_apply(body: ProcessTextAndApplyBody):
    """
    Process text to a numeric score and write that value into external_drivers.csv for the given year_month.
    """
    from app.config import EXTERNAL_DRIVERS_PATH
    from app.services.text_to_numeric import text_to_numeric
    reg = next((r for r in get_registry() if r["id"] == body.index_id), None)
    if reg is None:
        raise HTTPException(status_code=400, detail="Unknown index_id")
    if reg.get("deterministic", True):
        raise HTTPException(status_code=400, detail="Index is deterministic; use fetch or CSV")
    value, _ = text_to_numeric(body.index_id, body.text, body.year_month)
    df = update_values([{**{"year_month": body.year_month}, **{body.index_id: value}}], path=EXTERNAL_DRIVERS_PATH)
    return {"value": value, "year_month": body.year_month, "index_id": body.index_id, "rows": len(df)}


class ProcessTextBatchItem(BaseModel):
    year_month: str  # YYYY-MM
    text: str


class ProcessTextBatchBody(BaseModel):
    index_id: str
    items: list[ProcessTextBatchItem]  # [{ year_month, text }, ...]


@router.post("/process-text-batch")
def post_process_text_batch(body: ProcessTextBatchBody):
    """
    Process multiple (year_month, text) items to numeric scores and write all into external_drivers.csv.
    Smoother for volumes: one request → month-by-month indices.
    """
    from app.config import EXTERNAL_DRIVERS_PATH
    from app.services.text_to_numeric import text_to_numeric
    reg = next((r for r in get_registry() if r["id"] == body.index_id), None)
    if reg is None:
        raise HTTPException(status_code=400, detail="Unknown index_id")
    if reg.get("deterministic", True):
        raise HTTPException(status_code=400, detail="Index is deterministic; use fetch or CSV")
    if not body.items:
        raise HTTPException(status_code=400, detail="items must be non-empty")
    rows = []
    for item in body.items:
        value, _ = text_to_numeric(body.index_id, item.text, item.year_month)
        rows.append({"year_month": item.year_month, body.index_id: value})
    df = update_values(rows, path=EXTERNAL_DRIVERS_PATH)
    sample = _json_safe(df.tail(5).to_dict(orient="records")) if not df.empty else []
    return {"applied": len(rows), "index_id": body.index_id, "rows": len(df), "sample": sample}


def _parse_text_batch_csv(content: str) -> list[tuple[str, str]]:
    """Parse CSV with header year_month, text (or raw_text). Returns list of (year_month, text)."""
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    text_col = None
    for row in reader:
        ym = (row.get("year_month") or row.get("year-month") or "").strip()
        if not ym:
            continue
        if text_col is None:
            text_col = "text" if "text" in row else "raw_text" if "raw_text" in row else next((k for k in row if k != "year_month" and k != "year-month"), None)
        text = (row.get(text_col) or "").strip() if text_col else ""
        if text:
            rows.append((ym, text))
    return rows


@router.post("/process-text-file")
async def post_process_text_file(
    file: UploadFile = File(...),
    index_id: str = Form(...),
):
    """
    Upload a CSV with columns year_month and text (or raw_text); process each row to a numeric score and write to external_drivers.csv.
    Smoother for volumes: one file → month-by-month indices.
    """
    from app.config import EXTERNAL_DRIVERS_PATH
    from app.services.text_to_numeric import text_to_numeric
    reg = next((r for r in get_registry() if r["id"] == index_id), None)
    if reg is None:
        raise HTTPException(status_code=400, detail="Unknown index_id")
    if reg.get("deterministic", True):
        raise HTTPException(status_code=400, detail="Index is deterministic; use fetch or CSV")
    content = (await file.read()).decode("utf-8", errors="replace")
    items = _parse_text_batch_csv(content)
    if not items:
        raise HTTPException(status_code=400, detail="CSV must have header year_month, text (or raw_text) and at least one data row")
    rows = []
    for ym, text in items:
        value, _ = text_to_numeric(index_id, text, ym)
        rows.append({"year_month": ym, index_id: value})
    df = update_values(rows, path=EXTERNAL_DRIVERS_PATH)
    sample = _json_safe(df.tail(5).to_dict(orient="records")) if not df.empty else []
    return {"applied": len(rows), "index_id": index_id, "rows": len(df), "sample": sample}


# ---- Doc repo (US–China local docs: MM_YYYY folders) ----
@router.get("/doc-repo")
def get_doc_repo():
    """
    Return local doc repo path and list of month folders (YYYY-MM) found.
    Repo holds folders/files named MM_YYYY (e.g. 01_2023, 12_2024) for documents per month.
    """
    from app.config import TRADE_POLICY_DOCS_PATH
    from app.services.trade_policy_doc_repo import list_month_folders
    path = TRADE_POLICY_DOCS_PATH.resolve()
    months = list_month_folders(path)
    return {"path": str(path), "month_folders": months}


class ProcessDocRepoBody(BaseModel):
    index_id: str = "trade_policy"
    start: str | None = None  # YYYY-MM filter
    end: str | None = None    # YYYY-MM filter
    lang: str = "en"


@router.post("/process-doc-repo")
def post_process_doc_repo(body: ProcessDocRepoBody):
    """
    Read doc repo month-by-month, run text→numeric for each month, write to external_drivers.csv.
    Repo must have folders/files named MM_YYYY (e.g. 01_2023) with .txt, .md, or .html inside.
    """
    from app.services.trade_policy_doc_repo import generate_indices_from_repo
    try:
        applied, total = generate_indices_from_repo(
            index_id=body.index_id,
            start_ym=body.start,
            end_ym=body.end,
        )
        return {"applied": applied, "rows": total, "index_id": body.index_id, "message": t("generated_from_doc_repo", body.lang, applied=applied)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DocRepoCrawlBody(BaseModel):
    start: str  # YYYY-MM
    end: str    # YYYY-MM
    # When True (default): fetch once and save only to current month folder so content date matches folder.
    # When False: save same current snapshot into every month in [start, end] (content won't match folder dates).
    snapshot_only: bool = True
    # Condition-based halt (optional)
    max_duration_seconds: float | None = None
    max_minutes: float | None = None
    max_hours: float | None = None
    max_articles_per_month: int | None = None
    lang: str = "en"


@router.post("/doc-repo/crawl")
def post_doc_repo_crawl(body: DocRepoCrawlBody):
    """
    Crawl reliable public sources (Pew, CFR, CSIS) and save to doc repo.
    By default (snapshot_only=True): fetches once and saves to current month folder only, so folder date matches content.
    Set snapshot_only=False to fill every month in [start, end] with the same current snapshot (run monthly to build a time series).
    Condition-based halt: max_hours, max_minutes, max_duration_seconds, max_articles_per_month. To stop: POST /doc-repo/crawl/cancel.
    """
    from app.services.trade_policy_crawler import crawl_range
    months = _year_months_from_range(body.start, body.end)
    if not months:
        raise HTTPException(status_code=400, detail="Invalid start/end; use YYYY-MM")

    max_sec = body.max_duration_seconds
    if body.max_hours is not None and body.max_hours > 0:
        max_sec = body.max_hours * 3600.0
    elif body.max_minutes is not None and body.max_minutes > 0:
        max_sec = body.max_minutes * 60.0

    try:
        result, cancelled, halt_reason, errors = crawl_range(
            body.start,
            body.end,
            max_duration_seconds=max_sec,
            max_articles_per_month=body.max_articles_per_month,
            snapshot_only=body.snapshot_only,
        )
        total_files = sum(result.values())
        if body.snapshot_only and result:
            ym = next(iter(result))
            msg = t("crawl_snapshot_saved", body.lang, ym=ym, total=total_files)
        else:
            msg = t("crawled_count", body.lang, months=len(result), total=total_files)
        if cancelled:
            if halt_reason == "time_limit":
                msg = t("crawl_stopped_time_limit", body.lang, months=len(result), total=total_files)
            else:
                msg = t("crawl_cancelled", body.lang, months=len(result), total=total_files)
        if total_files == 0 and errors:
            err_detail = "; ".join(f"{s}: {m}" for s, m in errors[:5])
            msg += t("no_files_written_errors", body.lang, err_detail=err_detail)
        return {
            "months": len(result),
            "files_written": total_files,
            "per_month": result,
            "cancelled": cancelled,
            "halt_reason": halt_reason,
            "errors": [{"source": s, "message": m} for s, m in errors],
            "message": msg,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/doc-repo/crawl/cancel")
def post_doc_repo_crawl_cancel(lang: str = Query("en")):
    """
    Request the running crawl to stop after the current month. No-op if no crawl is running.
    """
    from app.services.trade_policy_crawler import request_crawl_cancel
    request_crawl_cancel()
    return {"message": t("cancel_requested", lang)}


def _year_months_from_range(start: str, end: str) -> list[str]:
    """Return list of year_month from start to end (inclusive). Format YYYY-MM."""
    try:
        sy, sm = map(int, start.split("-"))
        ey, em = map(int, end.split("-"))
    except (ValueError, AttributeError):
        return []
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


@router.get("/us-semi-tariff-china")
def get_us_semi_tariff_china_preview(
    start: str = Query("2018-01", description="Start year_month (YYYY-MM)"),
    end: str = Query("2026-12", description="End year_month (YYYY-MM)"),
    lang: str = Query("en"),
):
    """
    Preview curated US import tariff rate (%) for semiconductor goods from China.
    Raw data is built from USTR/FR effective dates on the backend; returns rows for the given date range.
    """
    from app.services.us_semi_tariff_source import (
        build_us_semi_tariff_china_series,
        EFFECTIVE_DATES,
    )
    year_months = _year_months_from_range(start, end)
    if not year_months:
        raise HTTPException(status_code=400, detail="Invalid start/end; use YYYY-MM")
    series = build_us_semi_tariff_china_series(year_months)
    rows = [{"year_month": ym, "us_semi_tariff_china": float(series[ym])} for ym in year_months]
    effective_dates = [{"year_month": ym, "rate_pct": r} for ym, r in EFFECTIVE_DATES]
    return {
        "rows": _json_safe(rows),
        "effective_dates": effective_dates,
        "message": t("curated_from_ustr_fr", lang),
    }


class UsSemiTariffApplyBody(BaseModel):
    start: str | None = None  # YYYY-MM
    end: str | None = None    # YYYY-MM
    lang: str = "en"


@router.post("/us-semi-tariff-china/apply")
def post_us_semi_tariff_china_apply(body: UsSemiTariffApplyBody):
    """
    Fetch curated US semi tariff (China) for the given date range (or learn+forecast if omitted),
    merge into external_drivers.csv, and return updated row count.
    """
    from app.config import EXTERNAL_DRIVERS_PATH

    try:
        if body.start and body.end:
            year_months = _year_months_from_range(body.start, body.end)
            if not year_months:
                raise HTTPException(status_code=400, detail="Invalid start/end; use YYYY-MM")
            learn_months = year_months
            forecast_months = []
        else:
            learn_months = None
            forecast_months = None  # use default learn + forecast

        df = fetch_and_populate(
            index_ids=["us_semi_tariff_china"],
            learn_months=learn_months,
            forecast_months=forecast_months,
            output_path=EXTERNAL_DRIVERS_PATH,
            source_overrides={"us_semi_tariff_china": {"type": "builtin", "builder": "us_semi_tariff_china"}},
        )
        if df.empty:
            raise HTTPException(status_code=400, detail="Apply failed")
        return {
            "rows": len(df),
            "message": t("us_semi_applied", body.lang),
            "sample": _json_safe(df.tail(3).to_dict(orient="records")),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
