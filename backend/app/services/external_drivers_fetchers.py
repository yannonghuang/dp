"""
Fetch raw data for external driver indices from configured sources.
Backend is in charge of fetching; UI sends selected indices and backend populates.
"""

from pathlib import Path
import pandas as pd
from app.services.external_drivers_subsystem import get_registry, get_required_year_months


def _mock_series(year_months: list[str], index_id: str, default_value: float) -> pd.Series:
    """Generate a placeholder series (e.g. slight trend) for demo. Replace with real API/file later."""
    reg = next((r for r in get_registry() if r["id"] == index_id), None)
    base = float(default_value) if reg is None else reg.get("default_value", default_value)
    n = len(year_months)
    # Simple trend: base + small linear drift so values vary by month
    step = (base * 0.08 / (n - 1)) if n > 1 else 0.0
    vals = [base + i * step for i in range(n)]
    return pd.Series(vals, index=year_months)


def fetch_index(index_id: str, year_months: list[str], source: dict | None = None) -> pd.Series | None:
    """
    Fetch one index series for given year_months from its source.
    source: { "type": "mock" } | { "type": "url", "url": "..." } | { "type": "file", "path": "..." }
            | { "type": "builtin", "builder": "us_semi_tariff_china" }
    Returns Series (index=year_month) or None to use default.
    """
    reg = next((r for r in get_registry() if r["id"] == index_id), None)
    default_value = reg.get("default_value", 0.0) if reg else 0.0
    src = source or (reg.get("source") if reg else None)

    if not src or src.get("type") == "mock":
        return _mock_series(year_months, index_id, default_value)

    if src.get("type") == "builtin":
        builder = src.get("builder")
        if builder == "us_semi_tariff_china" and index_id == "us_semi_tariff_china":
            from app.services.us_semi_tariff_source import build_us_semi_tariff_china_series
            return build_us_semi_tariff_china_series(year_months)
        if builder == "industry_sentiment_composite" and index_id == "industry_sentiment":
            from app.services.industry_sentiment_source import build_industry_sentiment_series
            return build_industry_sentiment_series(year_months)
        return _mock_series(year_months, index_id, default_value)

    if src.get("type") == "url":
        url = src.get("url")
        if not url:
            return _mock_series(year_months, index_id, default_value)
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=10) as resp:
                # Expect CSV with year_month and column matching index_id (or "value")
                df = pd.read_csv(resp)
                df.columns = [c.strip() for c in df.columns]
                if "year_month" not in df.columns:
                    return _mock_series(year_months, index_id, default_value)
                col = index_id if index_id in df.columns else "value"
                if col not in df.columns:
                    return _mock_series(year_months, index_id, default_value)
                s = df.set_index("year_month")[col]
                return s.reindex(year_months).fillna(default_value)
        except Exception:
            return _mock_series(year_months, index_id, default_value)

    if src.get("type") == "file":
        path = Path(src.get("path", ""))
        if not path.exists():
            # Resolve relative to repo data dir (backend/app/services -> repo/data)
            base = Path(__file__).resolve().parent.parent.parent / "data"
            path = base / path.name if path.name else base / path
        if not path.exists():
            return _mock_series(year_months, index_id, default_value)
        try:
            df = pd.read_csv(path)
            df.columns = [c.strip() for c in df.columns]
            if "year_month" not in df.columns:
                return _mock_series(year_months, index_id, default_value)
            col = index_id if index_id in df.columns else "value"
            if col not in df.columns:
                return _mock_series(year_months, index_id, default_value)
            df["year_month"] = df["year_month"].astype(str)
            s = df.set_index("year_month")[col]
            return s.reindex(year_months).ffill().fillna(default_value)
        except Exception:
            return _mock_series(year_months, index_id, default_value)

    return _mock_series(year_months, index_id, default_value)


def _resolve_source(index_id: str, source_override: dict | None, registry_entry: dict | None) -> dict | None:
    """Resolve effective source: override (user choice) or registry default. For type 'custom', override must contain url or path."""
    if source_override is not None:
        t = source_override.get("type")
        if t == "mock":
            return {"type": "mock"}
        if t == "builtin" and source_override.get("builder"):
            return {"type": "builtin", "builder": source_override["builder"]}
        if t == "url" and source_override.get("url"):
            return {"type": "url", "url": source_override["url"]}
        if t == "file" and source_override.get("path"):
            return {"type": "file", "path": source_override["path"]}
        if t == "custom":
            if source_override.get("url"):
                return {"type": "url", "url": source_override["url"]}
            if source_override.get("path"):
                return {"type": "file", "path": source_override["path"]}
    return registry_entry.get("source") if registry_entry else None


def fetch_and_build_df(
    index_ids: list[str],
    year_months: list[str] | None = None,
    source_overrides: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """
    Fetch data for selected indices from their sources and build a single DataFrame.
    source_overrides: optional { index_id: { type, url? } | { type, path? } } for user-chosen or custom sources.
    Columns: year_month + one per index_id. Only selected indices are included.
    """
    reg = get_registry()
    valid_ids = [r["id"] for r in reg]
    selected = [i for i in index_ids if i in valid_ids]
    if not selected:
        return pd.DataFrame()

    year_months = year_months or get_required_year_months()
    overrides = source_overrides or {}
    df = pd.DataFrame({"year_month": year_months})

    for index_id in selected:
        r = next((x for x in reg if x["id"] == index_id), None)
        source = _resolve_source(index_id, overrides.get(index_id), r)
        series = fetch_index(index_id, year_months, source=source)
        if series is not None:
            df[index_id] = series.values
        else:
            default = r.get("default_value", 0.0) if r else 0.0
            df[index_id] = default

    return df
