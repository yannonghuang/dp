"""
Product hierarchy: Series -> Model -> Version (SKU). Rollup forecast at different levels.
"""

import pandas as pd
from app.config import FORECAST_MONTHS

# Rollup levels: sku = (Plant, Series, Model, Version), model = (Plant, Series, Model), series = (Plant, Series), plant = (Plant)
LEVELS = ["sku", "model", "series", "plant"]


def get_hierarchy_from_plan(plan_sku: pd.DataFrame) -> list[dict]:
    """Return unique hierarchy nodes: list of {plant, series, model, version}."""
    cols = ["Plant", "Series", "Model", "Version"]
    cols = [c for c in cols if c in plan_sku.columns]
    if not cols:
        return []
    nodes = plan_sku[cols].drop_duplicates().sort_values(cols)
    return nodes.to_dict("records")


def rollup_forecast(forecast_df: pd.DataFrame, level: str) -> pd.DataFrame:
    """
    forecast_df must have columns: Plant, Series, Model, Version, 2024-01..2024-12.
    Optional PRODUCT_ID: when present, dedupe by (Plant, Series, Model, Version) before summing
    so we don't double-count (same forecast repeated per PRODUCT_ID).
    level: 'sku' | 'model' | 'series' | 'plant'
    """
    month_cols = [c for c in forecast_df.columns if c in FORECAST_MONTHS]
    if not month_cols:
        return forecast_df
    if level == "sku":
        return forecast_df.copy()
    # When PRODUCT_ID is present, multiple rows per (Plant, Series, Model, Version) have same forecast
    df = forecast_df.copy()
    if "PRODUCT_ID" in df.columns:
        sku_cols = [c for c in ["Plant", "Series", "Model", "Version"] if c in df.columns]
        df = df.drop_duplicates(subset=sku_cols + month_cols, keep="first")
    if level == "model":
        group = ["Plant", "Series", "Model"]
    elif level == "series":
        group = ["Plant", "Series"]
    elif level == "plant":
        group = ["Plant"]
    else:
        return forecast_df
    group = [c for c in group if c in df.columns]
    return df.groupby(group, as_index=False)[month_cols].sum()


def rollup_actuals_long(actuals_long: pd.DataFrame, level: str) -> pd.DataFrame:
    """
    Roll up long-format actuals (Plant, Series, Model, Version, year_month, actual_qty) by level.
    Returns long format: group keys + year_month + volume.
    """
    if actuals_long.empty or "year_month" not in actuals_long.columns:
        return actuals_long
    qty_col = "actual_qty" if "actual_qty" in actuals_long.columns else "volume"
    if qty_col not in actuals_long.columns:
        return actuals_long
    if level == "sku":
        return actuals_long.rename(columns={qty_col: "volume"}) if qty_col != "volume" else actuals_long.copy()
    if level == "model":
        group = ["Plant", "Series", "Model"]
    elif level == "series":
        group = ["Plant", "Series"]
    elif level == "plant":
        group = ["Plant"]
    else:
        return actuals_long
    group = [c for c in group if c in actuals_long.columns]
    out = actuals_long.groupby(group + ["year_month"], as_index=False)[qty_col].sum()
    return out.rename(columns={qty_col: "volume"})
