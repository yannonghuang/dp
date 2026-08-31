import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from app.services.forecast_xgb import get_historic_actuals_at_level
from app.services.hierarchy import LEVELS

router = APIRouter(prefix="/api/history", tags=["history"])


def _json_safe(obj):
  if isinstance(obj, dict):
    return {k: _json_safe(v) for k, v in obj.items()}
  if isinstance(obj, list):
    return [_json_safe(v) for v in obj]
  if isinstance(obj, float) and (pd.isna(obj) or not pd.isfinite(obj)):
    return None
  if pd.isna(obj):
    return None
  return obj


@router.get("/shipments")
def shipments(level: str = Query("plant", description="Rollup level: sku | model | series | plant")):
  """
  Past shipments: actual quantities by year_month (2023) at the given level.
  Returns wide table: one row per key (Plant / Plant+Series / Plant+Series+Model / SKU), columns year_month.
  """
  if level not in LEVELS:
    raise HTTPException(status_code=400, detail=f"level must be one of {LEVELS}")

  hist = get_historic_actuals_at_level(level=level)
  if hist.empty:
    return {"level": level, "rows": [], "columns": []}

  # Drop plan_qty if present; history should only show actuals
  if "plan_qty" in hist.columns:
    hist = hist.drop(columns=["plan_qty"])

  # hist: group columns + year_month + volume
  group_cols = [c for c in hist.columns if c not in ("year_month", "volume")]
  if not group_cols:
    raise HTTPException(status_code=500, detail="No grouping columns found for history")

  wide = hist.pivot_table(
    index=group_cols,
    columns="year_month",
    values="volume",
    aggfunc="sum",
    fill_value=0,
  ).reset_index()

  # Ensure deterministic column order: group keys then sorted year_month
  month_cols = sorted([c for c in wide.columns if c not in group_cols])
  cols = group_cols + month_cols
  wide = wide[cols]

  return {
    "level": level,
    "rows": _json_safe(wide.to_dict(orient="records")),
    "columns": cols,
  }

