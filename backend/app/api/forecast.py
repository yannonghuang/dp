import math
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from app.config import PLAN_PATH, SHIPMENT_PATH, DATA_DIR
from app.services.data import load_plan, plan_to_sku_monthly
from app.services.hierarchy import get_hierarchy_from_plan, LEVELS, rollup_forecast
from app.services.forecast_xgb import (
    run_forecast_pipeline,
    get_forecast_at_level,
    run_forecast_compare,
    MODELS,
)

router = APIRouter(prefix="/api", tags=["forecast"])


def _json_safe(obj):
    """Replace nan/inf with None so JSON serialization works."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if pd.isna(obj):
        return None
    return obj


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/hierarchy")
def hierarchy():
    """Return product hierarchy (Series -> Model -> Version) from plan."""
    plan = load_plan()
    if plan.empty:
        raise HTTPException(status_code=503, detail="Plan data not loaded (missing dp.csv)")
    plan_sku = plan_to_sku_monthly(plan)
    if plan_sku.empty:
        return {"nodes": [], "levels": LEVELS}
    nodes = get_hierarchy_from_plan(plan_sku)
    return {"nodes": nodes, "levels": LEVELS}


@router.get("/forecast")
def forecast(
    level: str = Query("sku", description="Rollup level: sku | model | series | plant"),
    model: str = Query("xgb", description="Model: xgb | lgbm"),
):
    """Return 2024 forecast at given hierarchy level (XGBoost or LightGBM, SKU-level then rollup)."""
    if level not in LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {LEVELS}")
    if model not in MODELS:
        model = "xgb"
    df = get_forecast_at_level(level=level, model=model)
    if df.empty:
        raise HTTPException(status_code=503, detail="Forecast failed (check data in /data)")
    rows = _json_safe(df.to_dict(orient="records"))
    return {"level": level, "model": model, "rows": rows}


@router.get("/forecast/sku")
def forecast_sku_endpoint(
    model: str = Query("xgb", description="Model: xgb | lgbm"),
):
    """Return full SKU-level 2024 forecast (Plant, Series, Model, Version, 2024-01..2024-12)."""
    if model not in MODELS:
        model = "xgb"
    df = run_forecast_pipeline(model=model)
    if df.empty:
        raise HTTPException(status_code=503, detail="Forecast failed (check data)")
    return {"model": model, "rows": _json_safe(df.to_dict(orient="records"))}


@router.get("/forecast/compare")
def forecast_compare(
    include_product_id: bool = Query(False, description="Include PRODUCT_ID expansion in forecast rows"),
):
    """Run both XGBoost and LightGBM; return forecasts and in-sample fit KPIs (MAE, RMSE, MAPE) for comparison."""
    result = run_forecast_compare(include_product_id=include_product_id)
    xgb_fc = result["xgb"]["forecast"]
    lgbm_fc = result["lgbm"]["forecast"]
    return {
        "comparison": {
            "xgb": {
                "kpis": _json_safe(result["xgb"]["kpis"]),
                "total_volume_2024": int(xgb_fc[[c for c in xgb_fc.columns if c.startswith("2024-")]].sum().sum()) if not xgb_fc.empty else 0,
            },
            "lgbm": {
                "kpis": _json_safe(result["lgbm"]["kpis"]),
                "total_volume_2024": int(lgbm_fc[[c for c in lgbm_fc.columns if c.startswith("2024-")]].sum().sum()) if not lgbm_fc.empty else 0,
            },
        },
        "rows_xgb": _json_safe(xgb_fc.to_dict(orient="records")) if not xgb_fc.empty else [],
        "rows_lgbm": _json_safe(lgbm_fc.to_dict(orient="records")) if not lgbm_fc.empty else [],
    }
