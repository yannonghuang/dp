"""
Analysis API: volume time series (historic shipments + forecast) for charts.
Returns data rolled up by plant / series / model for overlay plots.
"""

import math
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from app.services.hierarchy import LEVELS
from app.services.forecast_xgb import (
    get_historic_actuals_at_level,
    get_forecast_at_level,
)
from app.config import MONTH_COLS, FORECAST_MONTHS

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


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


def _group_key(row: dict, level: str) -> str:
    """Build a unique key for the rollup level (e.g. '1000' for plant, '1000 | SeriesA' for series)."""
    if level == "plant":
        return str(int(row.get("Plant", 0)))
    if level == "series":
        return f"{int(row.get('Plant', 0))} | {row.get('Series', '')}"
    if level == "model":
        return f"{int(row.get('Plant', 0))} | {row.get('Series', '')} | {row.get('Model', '')}"
    # sku: include Version
    return f"{int(row.get('Plant', 0))} | {row.get('Series', '')} | {row.get('Model', '')} | {row.get('Version', '')}"


@router.get("/volume-timeseries")
def volume_timeseries(
    level: str = Query("plant", description="Rollup level: sku | model | series | plant"),
    model: str = Query("xgb", description="Forecast model: xgb | lgbm"),
):
    """
    Return volume time series for historic shipments (2023) and forecast (2024),
    rolled up by the given level, for overlay charts.
    """
    if level not in LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {LEVELS}")

    historic_long = get_historic_actuals_at_level(level=level)
    forecast_wide = get_forecast_at_level(level=level, include_product_id=False, model=model)

    year_months_historic = list(MONTH_COLS)
    year_months_forecast = list(FORECAST_MONTHS)

    # Melt forecast wide to long: group keys + year_month + volume
    month_cols = [c for c in forecast_wide.columns if c in FORECAST_MONTHS]
    id_cols = [c for c in forecast_wide.columns if c not in month_cols]
    if not month_cols or not id_cols:
        forecast_long = pd.DataFrame(columns=["year_month", "volume"])
    else:
        forecast_long = forecast_wide.melt(
            id_vars=id_cols,
            value_vars=month_cols,
            var_name="year_month",
            value_name="volume",
        )
        forecast_long["volume"] = pd.to_numeric(forecast_long["volume"], errors="coerce").fillna(0).astype(int)

    # Collect all group keys from historic and forecast
    keys_seen = set()
    if not historic_long.empty and "volume" in historic_long.columns:
        for _, r in historic_long.iterrows():
            keys_seen.add(_group_key(r.to_dict(), level))
    if not forecast_long.empty:
        for _, r in forecast_long.iterrows():
            keys_seen.add(_group_key(r.to_dict(), level))

    # Build series list: for each key, arrays of historic and forecast by month
    series_list = []
    for key in sorted(keys_seen):
        historic_vals = [None] * len(year_months_historic)
        if not historic_long.empty:
            for _, r in historic_long.iterrows():
                if _group_key(r.to_dict(), level) == key:
                    ym = str(r["year_month"])
                    if ym in year_months_historic:
                        idx = year_months_historic.index(ym)
                        historic_vals[idx] = int(r["volume"]) if r["volume"] is not None else 0

        forecast_vals = [None] * len(year_months_forecast)
        if not forecast_long.empty:
            for _, r in forecast_long.iterrows():
                if _group_key(r.to_dict(), level) == key:
                    ym = str(r["year_month"])
                    if ym in year_months_forecast:
                        idx = year_months_forecast.index(ym)
                        forecast_vals[idx] = int(r["volume"]) if r["volume"] is not None else 0

        series_list.append({
            "key": key,
            "label": key,
            "historic": _json_safe(historic_vals),
            "forecast": _json_safe(forecast_vals),
        })

    return {
        "level": level,
        "model": model,
        "year_months_historic": year_months_historic,
        "year_months_forecast": year_months_forecast,
        "series": _json_safe(series_list),
    }
