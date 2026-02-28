"""
External drivers subsystem: pre-determined indices, populator for learn + forecast periods.
Designed to evolve into an agent guiding users in choosing indices and populating values.
"""

from pathlib import Path
import pandas as pd
from app.config import DATA_DIR, MONTH_COLS, FORECAST_MONTHS, EXTERNAL_DRIVERS_PATH

# Pre-determined set of external indices (id = column name in CSV).
# source: active source used when no override is provided (e.g. from UI).
# suggested_sources: options shown to users; they can pick one or provide their own (custom).
# Future: agent can suggest additional indices; registry could be loaded from YAML/DB.
# Single source of truth for learn and forecast: indices table (external_drivers.csv).
# tax_index removed; superseded by us_semi_tariff_china.
EXTERNAL_INDICES_REGISTRY = [
    {
        "id": "industry_sentiment",
        "name": "Industry sentiment",
        "description": "Industry-wide sentiment or confidence (e.g. 0–100).",
        "default_value": 50.0,
        "unit": "score",
        "deterministic": True,
        "source": {"type": "builtin", "builder": "industry_sentiment_composite", "label": "Composite from KPMG confidence + electronics PMI (CSV)"},
        "suggested_sources": [
            {"id": "mock", "label": "Placeholder (demo values)", "type": "mock"},
            {"id": "custom", "label": "Your own (URL or file path)", "type": "custom"},
        ],
    },
    {
        "id": "trade_policy",
        "name": "US–China relationship",
        "description": "Broader US–China relationship; qualitative (policy stance, tension). Use starter sources or your own; process text into a numeric score.",
        "default_value": 1.0,
        "unit": "qualitative",
        "deterministic": False,
        "source": {"type": "mock", "label": "Placeholder or process text below"},
        "suggested_sources": [
            {"id": "mock", "label": "Placeholder (demo values)", "type": "mock"},
            {"id": "custom", "label": "Your own (URL or file path)", "type": "custom"},
        ],
        "starter_sources": [
            {"id": "csis", "label": "CSIS (China)", "url": "https://www.csis.org/regions/asia/china", "description": "Strategic and economic analysis; data-driven research on China"},
            {"id": "cfr", "label": "CFR (China)", "url": "https://www.cfr.org/asia/china", "description": "Policy analysis, backgrounders, and articles on China"},
            {"id": "pew", "label": "Pew Research (China global image)", "url": "https://www.pewresearch.org/topic/international-affairs/global-image-of-countries/china-global-image/", "description": "Public opinion and surveys on global views of China"},
        ],
        "text_to_numeric_scale": {"min": 1, "max": 5, "description": "1 = most cooperative, 5 = most confrontational"},
    },
    {
        "id": "us_semi_tariff_china",
        "name": "US import tax (semiconductor, China)",
        "description": "US ad valorem tariff rate (%) for semiconductor goods (HTS 8541, 8542) from China (Section 301). Deterministic: use built-in or CSV.",
        "default_value": 0.0,
        "unit": "%",
        "deterministic": True,
        "source": {"type": "builtin", "builder": "us_semi_tariff_china", "label": "Curated from USTR/FR effective dates"},
        "suggested_sources": [
            {"id": "builtin_ustr_fr", "label": "Curated from USTR/FR effective dates (built-in)", "type": "builtin", "builder": "us_semi_tariff_china"},
        ],
    },
]


def get_registry() -> list[dict]:
    """Return the list of registered external indices (for API schema and populator)."""
    return list(EXTERNAL_INDICES_REGISTRY)


def get_required_year_months(
    learn_months: list[str] | None = None,
    forecast_months: list[str] | None = None,
) -> list[str]:
    """Return sorted year_month list covering learn and forecast periods."""
    learn = learn_months or list(MONTH_COLS)
    forecast = forecast_months or list(FORECAST_MONTHS)
    combined = sorted(set(learn) | set(forecast))
    return combined


def build_drivers_df(
    year_months: list[str],
    overrides: pd.DataFrame | None = None,
    registry: list[dict] | None = None,
) -> pd.DataFrame:
    """
    Build external_drivers DataFrame for given year_months.
    Uses default_value from registry per index; overrides (long: year_month, index_id, value) replace where provided.
    """
    reg = registry or get_registry()
    index_ids = [r["id"] for r in reg]
    defaults = {r["id"]: r["default_value"] for r in reg}

    rows = []
    for ym in year_months:
        row = {"year_month": ym}
        for iid in index_ids:
            row[iid] = defaults.get(iid, 0.0)
        rows.append(row)
    df = pd.DataFrame(rows)

    if overrides is not None and not overrides.empty and "year_month" in overrides.columns:
        # Wide overrides: year_month + one column per index_id
        for iid in index_ids:
            if iid in overrides.columns:
                ov = overrides[["year_month", iid]].dropna(subset=[iid])
                if not ov.empty:
                    ov = ov.set_index("year_month")[iid]
                    df = df.set_index("year_month")
                    df[iid] = ov.reindex(df.index).fillna(df[iid]).values
                    df = df.reset_index()
        # Long overrides: year_month, index_id, value
        if "index_id" in overrides.columns and "value" in overrides.columns:
            piv = overrides.pivot_table(index="year_month", columns="index_id", values="value")
            for col in piv.columns:
                if col in df.columns:
                    df = df.set_index("year_month")
                    df[col] = piv[col].reindex(df.index).fillna(df[col]).values
                    df = df.reset_index()

    return df


def load_overrides_from_csv(path: Path) -> pd.DataFrame:
    """Load overrides from CSV: either wide (year_month, index1, index2...) or long (year_month, index_id, value)."""
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    if "year_month" not in df.columns:
        return pd.DataFrame()
    df["year_month"] = df["year_month"].astype(str)
    return df


def write_drivers_csv(df: pd.DataFrame, path: Path | None = None, registry: list[dict] | None = None) -> Path:
    """Write drivers DataFrame to CSV. Only year_month and registered index columns are persisted (single source of truth)."""
    path = path or EXTERNAL_DRIVERS_PATH
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    reg = registry or get_registry()
    index_ids = [r["id"] for r in reg]
    cols = ["year_month"] + [c for c in index_ids if c in df.columns]
    df = df[cols].copy()
    df.to_csv(path, index=False)
    return path


def load_drivers_csv(path: Path | None = None) -> pd.DataFrame:
    """Load current external_drivers CSV (for API GET)."""
    path = path or EXTERNAL_DRIVERS_PATH
    if not Path(path).exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    return df


def reset_drivers_csv(path: Path | None = None) -> Path:
    """Clear external_drivers CSV (header-only with year_month). Returns path written."""
    path = path or EXTERNAL_DRIVERS_PATH
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(columns=["year_month"])
    df.to_csv(path, index=False)
    return path


def populate(
    learn_months: list[str] | None = None,
    forecast_months: list[str] | None = None,
    overrides_path: Path | None = None,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """
    Populate external drivers for learn + forecast periods and write CSV.
    Returns the built DataFrame.
    """
    year_months = get_required_year_months(learn_months, forecast_months)
    overrides = load_overrides_from_csv(Path(overrides_path)) if overrides_path else None
    df = build_drivers_df(year_months, overrides=overrides)
    write_drivers_csv(df, path=output_path)
    return df


def fetch_and_populate(
    index_ids: list[str],
    learn_months: list[str] | None = None,
    forecast_months: list[str] | None = None,
    output_path: Path | None = None,
    source_overrides: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """
    Fetch raw data from configured sources for selected indices and merge into external_drivers CSV.
    Only the fetched index columns are updated; other columns (if present) are preserved.
    source_overrides: optional { index_id: { "type": "url", "url": "..." } | { "type": "file", "path": "..." } }
    for user-chosen or custom sources; only indices in index_ids are included.
    """
    from app.services.external_drivers_fetchers import fetch_and_build_df

    path = output_path or EXTERNAL_DRIVERS_PATH
    path = Path(path)
    year_months = get_required_year_months(learn_months, forecast_months)
    fetched = fetch_and_build_df(index_ids, year_months=year_months, source_overrides=source_overrides)
    if fetched.empty:
        return pd.DataFrame()

    existing = load_drivers_csv(path) if path.exists() else pd.DataFrame()
    reg = get_registry()
    all_index_ids = [r["id"] for r in reg]

    if existing.empty:
        # Build full drivers from registry for year_months, then overwrite with fetched columns
        existing = build_drivers_df(year_months, registry=reg)
    else:
        # Ensure we have all year_months (add missing with defaults)
        existing["year_month"] = existing["year_month"].astype(str)
        missing_ym = sorted(set(year_months) - set(existing["year_month"].unique()))
        if missing_ym:
            defaults = {r["id"]: r["default_value"] for r in reg}
            for ym in missing_ym:
                row = {"year_month": ym, **{iid: defaults.get(iid, 0.0) for iid in all_index_ids}}
                existing = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
            existing = existing.sort_values("year_month").reset_index(drop=True)

    # Merge fetched columns into existing (only indices we just fetched)
    fetched_idx = fetched.set_index("year_month")
    for col in fetched.columns:
        if col == "year_month":
            continue
        default = next((r.get("default_value", 0.0) for r in reg if r["id"] == col), 0.0)
        s = fetched_idx[col].reindex(existing["year_month"]).ffill()
        mapped = existing["year_month"].map(s)
        existing[col] = mapped.fillna(default)

    write_drivers_csv(existing, path=path)
    return existing


def update_values(values: list[dict], path: Path | None = None) -> pd.DataFrame:
    """
    Update driver values from a list of records [{ year_month, industry_sentiment?, trade_policy?, us_semi_tariff_china?, ... }].
    Merges with existing CSV (or builds from registry for missing months). Writes back to CSV.
    """
    path = path or EXTERNAL_DRIVERS_PATH
    path = Path(path)
    existing = load_drivers_csv(path) if path.exists() else pd.DataFrame()
    reg = get_registry()
    index_ids = [r["id"] for r in reg]

    if not values:
        return existing
    new_df = pd.DataFrame(values)
    if "year_month" not in new_df.columns:
        return existing
    new_df["year_month"] = new_df["year_month"].astype(str)

    if existing.empty:
        year_months = sorted(new_df["year_month"].unique())
        existing = build_drivers_df(year_months, registry=reg)
    # Update existing with new values (only columns that exist in new_df and registry)
    for _, row in new_df.iterrows():
        ym = row["year_month"]
        mask = existing["year_month"] == ym
        if not mask.any():
            defaults = {r["id"]: r["default_value"] for r in reg}
            new_row = {"year_month": ym, **{iid: defaults.get(iid, 0.0) for iid in index_ids}}
            for iid in index_ids:
                if iid in row and pd.notna(row[iid]):
                    new_row[iid] = float(row[iid])
            existing = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)
        else:
            for iid in index_ids:
                if iid in row and iid in existing.columns and pd.notna(row[iid]):
                    existing.loc[mask, iid] = float(row[iid])
    existing = existing.sort_values("year_month").reset_index(drop=True)
    write_drivers_csv(existing, path=path)
    return existing
