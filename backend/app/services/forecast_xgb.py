"""
XGBoost and LightGBM demand forecast at SKU level (Plant, Series, Model, Version).
Uses 2023 plan + scaled actuals; predicts 2024 monthly; supports rollup.
Optionally expands by shipment PRODUCT_ID using linkage report.
"""

import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
from pathlib import Path
from app.config import MONTH_COLS, FORECAST_MONTHS, LINKAGE_PATH

FEATURE_COLS = ["month", "lag_1", "lag_12", "mean_2023"]
MODELS = ("xgb", "lgbm")
from app.services.data import (
    load_plan,
    load_shipments,
    plan_to_sku_monthly,
    actuals_by_plant_month,
    sku_level_actuals_from_plan_proportion,
    sku_level_actuals_from_shipment_linkage,
    load_external_drivers,
)
from app.services.hierarchy import rollup_forecast, rollup_actuals_long


def load_linkage_product_ids(path: Path | None = None) -> pd.DataFrame:
    """
    Load linkage report; return (Plant, Model, PRODUCT_ID). Used to attach PRODUCT_ID to forecast.
    Tries LINKAGE_PATH, then project output/linkage_report.csv if not found.
    """
    path = path or LINKAGE_PATH
    p = Path(path) if path else None
    if not p:
        return pd.DataFrame()
    if not p.exists():
        # Fallback for local run: linkage script writes to output/
        fallback = Path(__file__).resolve().parent.parent.parent / "output" / "linkage_report.csv"
        p = fallback if fallback.exists() else p
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    df.columns = [c.strip() for c in df.columns]
    model_col = "matched_Model_best" if "matched_Model_best" in df.columns else "matched_Model"
    if model_col not in df.columns or "PRODUCT_ID" not in df.columns or "LOCATION_ID" not in df.columns:
        return pd.DataFrame()
    df = df[df[model_col].notna()].copy()
    df["Plant"] = pd.to_numeric(df["LOCATION_ID"], errors="coerce").fillna(0).astype(int)
    df["Model"] = df[model_col].astype(str)
    return df[["Plant", "Model", "PRODUCT_ID"]].drop_duplicates()


def expand_forecast_by_product_id(fc: pd.DataFrame, linkage: pd.DataFrame) -> pd.DataFrame:
    """
    Expand forecast so each row has a PRODUCT_ID. For each (Plant, Series, Model, Version) we attach
    all PRODUCT_IDs that link to (Plant, Model); one row per PRODUCT_ID (same forecast values).
    Rows with no linked PRODUCT_ID get PRODUCT_ID = None.
    """
    if fc.empty or linkage.empty:
        fc = fc.copy()
        fc["PRODUCT_ID"] = None
        return fc
    month_cols = [c for c in fc.columns if c in FORECAST_MONTHS]
    # (Plant, Model) -> list of PRODUCT_ID
    plant_model_to_ids = linkage.groupby(["Plant", "Model"])["PRODUCT_ID"].apply(list).to_dict()
    rows = []
    for _, r in fc.iterrows():
        plant, model = int(r["Plant"]), str(r["Model"])
        pids = plant_model_to_ids.get((plant, model), None)
        if not pids:
            row = r.to_dict()
            row["PRODUCT_ID"] = None
            rows.append(row)
            continue
        for pid in pids:
            row = r.to_dict()
            row["PRODUCT_ID"] = pid
            rows.append(row)
    out = pd.DataFrame(rows)
    return out


def _build_sku_series(sku_month: pd.DataFrame, target_col: str = "actual_qty") -> pd.DataFrame:
    """Pivot to wide: index = (Plant, Series, Model, Version), columns = year_month."""
    wide = sku_month.pivot_table(
        index=["Plant", "Series", "Model", "Version"],
        columns="year_month",
        values=target_col,
        aggfunc="sum",
        fill_value=0,
    )
    return wide


def _wide_to_features(wide: pd.DataFrame, year: int = 2023) -> pd.DataFrame:
    """Build feature rows for each SKU and month (2024-01..2024-12). One row = one (sku, fc_month)."""
    ym_cols = [f"{year}-{m:02d}" for m in range(1, 13)]
    ym_cols = [c for c in ym_cols if c in wide.columns]
    if not ym_cols:
        return pd.DataFrame()
    records = []
    for idx, row in wide.iterrows():
        vals = row[ym_cols].values.astype(float)
        mean_2023 = float(np.mean(vals))
        for fc_m in range(1, 13):
            lag_12 = vals[fc_m - 1]
            lag_1 = vals[(fc_m - 2) % 12] if fc_m >= 2 else vals[11]
            records.append({
                "Plant": idx[0],
                "Series": idx[1],
                "Model": idx[2],
                "Version": idx[3],
                "year_month": f"2024-{fc_m:02d}",
                "month": fc_m,
                "lag_1": lag_1,
                "lag_12": lag_12,
                "mean_2023": mean_2023,
            })
    return pd.DataFrame(records)


def _model_feature_cols(features: pd.DataFrame) -> list[str]:
    """Base features plus any external-driver columns from the indices table (e.g. industry_sentiment, trade_policy, us_semi_tariff_china)."""
    base = [c for c in FEATURE_COLS if c in features.columns]
    skip = {"Plant", "Series", "Model", "Version", "year_month", "target", "forecast"}
    extra = [c for c in features.columns if c not in FEATURE_COLS and c not in skip and pd.api.types.is_numeric_dtype(features[c])]
    return base + extra


def _train_predict_xgb(features: pd.DataFrame, target: pd.Series, feature_cols: list[str] | None = None) -> np.ndarray:
    """Train XGBoost and return predictions for the same feature set. Uses feature_cols or auto-detected model cols."""
    if len(features) == 0 or target is None or len(target) == 0:
        return np.array([])
    cols = feature_cols or _model_feature_cols(features)
    cols = [c for c in cols if c in features.columns]
    if not cols:
        return target.values
    X = features[cols].fillna(0)
    y = target
    model = xgb.XGBRegressor(n_estimators=50, max_depth=4, learning_rate=0.1, random_state=42)
    model.fit(X, y)
    return model.predict(X)


def _train_predict_lgb(features: pd.DataFrame, target: pd.Series, feature_cols: list[str] | None = None) -> np.ndarray:
    """Train LightGBM and return predictions for the same feature set. Uses feature_cols or auto-detected model cols."""
    if len(features) == 0 or target is None or len(target) == 0:
        return np.array([])
    cols = feature_cols or _model_feature_cols(features)
    cols = [c for c in cols if c in features.columns]
    if not cols:
        return target.values
    X = features[cols].fillna(0)
    y = target
    model = lgb.LGBMRegressor(
        n_estimators=50,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
        verbosity=-1,
    )
    model.fit(X, y)
    return model.predict(X)


def _compute_fit_kpis(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute MAE, RMSE, MAPE (and n) from true vs predicted. MAPE avoids div-by-zero by excluding zeros."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    n = len(y_true)
    if n == 0:
        return {"n": 0, "mae": None, "rmse": None, "mape": None}
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    nonzero = y_true != 0
    if nonzero.sum() > 0:
        mape = float(np.mean(np.abs((y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero])) * 100)
    else:
        mape = None
    return {"n": n, "mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 4) if mape is not None else None}


def forecast_sku(
    plan_sku: pd.DataFrame,
    sku_actual: pd.DataFrame,
    forecast_year: int = 2024,
    model: str = "xgb",
    external_drivers_path=None,
) -> tuple[pd.DataFrame, dict]:
    """
    Forecast at SKU level using XGBoost or LightGBM. Uses actual_qty (or plan_qty) as history.
    Optionally merges external drivers from the indices table (industry_sentiment, trade_policy, us_semi_tariff_china, etc.) by year_month.
    Returns (forecast_df, kpis): forecast_df has Plant, Series, Model, Version, 2024-01..2024-12;
    kpis has n, mae, rmse, mape (in-sample fit vs target).
    """
    if model not in MODELS:
        model = "xgb"
    train_pred = _train_predict_xgb if model == "xgb" else _train_predict_lgb
    if "actual_qty" in sku_actual.columns and sku_actual["actual_qty"].sum() > 0:
        hist = sku_actual.copy()
        hist["qty"] = hist["actual_qty"]
    else:
        hist = plan_sku.copy()
        hist["qty"] = hist["plan_qty"]
    wide = _build_sku_series(hist.rename(columns={"qty": "actual_qty"}), target_col="actual_qty")
    if wide.empty:
        return pd.DataFrame(), {}
    feats = _wide_to_features(wide, year=2023)
    if feats.empty:
        return pd.DataFrame(), {}

    # Merge external drivers by year_month (industry-wide: same value for all SKUs in that month)
    drivers = load_external_drivers(external_drivers_path)
    if not drivers.empty:
        driver_cols = [c for c in drivers.columns if c != "year_month"]
        feats = feats.merge(drivers[["year_month"] + driver_cols], on="year_month", how="left")

    feats["target"] = feats["lag_12"]
    model_cols = _model_feature_cols(feats)
    pred = train_pred(feats, feats["target"], feature_cols=model_cols)
    feats["forecast"] = np.maximum(0, np.round(pred)).astype(int)
    kpis = _compute_fit_kpis(feats["target"].values, pred)
    out = feats.pivot_table(
        index=["Plant", "Series", "Model", "Version"],
        columns="year_month",
        values="forecast",
        aggfunc="sum",
    )
    out = out.reset_index()
    return out, kpis


def forecast_sku_xgb(
    plan_sku: pd.DataFrame,
    sku_actual: pd.DataFrame,
    forecast_year: int = 2024,
    external_drivers_path=None,
) -> pd.DataFrame:
    """XGBoost forecast at SKU level. Returns DataFrame only (backward compatible)."""
    fc, _ = forecast_sku(plan_sku, sku_actual, forecast_year=forecast_year, model="xgb", external_drivers_path=external_drivers_path)
    return fc


def run_forecast_pipeline(
    plan_path=None,
    shipment_path=None,
    linkage_path=None,
    external_drivers_path=None,
    include_product_id: bool = True,
    model: str = "xgb",
) -> pd.DataFrame:
    """Load data, build SKU actuals, run XGBoost or LightGBM, return SKU-level forecast. Optionally expand by PRODUCT_ID and merge external drivers."""
    plan = load_plan(plan_path)
    shipments = load_shipments(shipment_path)
    if plan.empty:
        return pd.DataFrame()
    plan_sku = plan_to_sku_monthly(plan)
    if plan_sku.empty:
        return pd.DataFrame()
    actual_plant = actuals_by_plant_month(shipments)
    linkage = load_linkage_product_ids(linkage_path)
    if not linkage.empty and not shipments.empty:
        sku_actual = sku_level_actuals_from_shipment_linkage(
            shipments, linkage, plan_sku, actual_plant
        )
    else:
        sku_actual = sku_level_actuals_from_plan_proportion(plan_sku, actual_plant)
    fc, _ = forecast_sku(plan_sku, sku_actual, forecast_year=2024, model=model, external_drivers_path=external_drivers_path)
    if fc.empty:
        return fc
    if include_product_id:
        fc = expand_forecast_by_product_id(fc, linkage)
    return fc


def run_forecast_compare(
    plan_path=None,
    shipment_path=None,
    linkage_path=None,
    external_drivers_path=None,
    include_product_id: bool = False,
) -> dict:
    """
    Run both XGBoost and LightGBM, return forecasts and in-sample fit KPIs for comparison.
    Returns: { "xgb": { "forecast": df, "kpis": { n, mae, rmse, mape } }, "lgbm": { ... } }.
    By default does not expand by PRODUCT_ID to keep response smaller; set include_product_id=True to include.
    """
    plan = load_plan(plan_path)
    shipments = load_shipments(shipment_path)
    if plan.empty:
        return {"xgb": {"forecast": [], "kpis": {}}, "lgbm": {"forecast": [], "kpis": {}}}
    plan_sku = plan_to_sku_monthly(plan)
    if plan_sku.empty:
        return {"xgb": {"forecast": [], "kpis": {}}, "lgbm": {"forecast": [], "kpis": {}}}
    actual_plant = actuals_by_plant_month(shipments)
    linkage = load_linkage_product_ids(linkage_path)
    if not linkage.empty and not shipments.empty:
        sku_actual = sku_level_actuals_from_shipment_linkage(
            shipments, linkage, plan_sku, actual_plant
        )
    else:
        sku_actual = sku_level_actuals_from_plan_proportion(plan_sku, actual_plant)

    out = {}
    for m in MODELS:
        fc, kpis = forecast_sku(plan_sku, sku_actual, forecast_year=2024, model=m, external_drivers_path=external_drivers_path)
        if include_product_id:
            fc = expand_forecast_by_product_id(fc, linkage)
        out[m] = {"forecast": fc, "kpis": kpis}
    return out


def get_forecast_at_level(
    level: str,
    plan_path=None,
    shipment_path=None,
    linkage_path=None,
    external_drivers_path=None,
    include_product_id: bool = True,
    model: str = "xgb",
) -> pd.DataFrame:
    """Get 2024 forecast rolled up at level: sku | model | series | plant. PRODUCT_ID included when linkage exists."""
    fc = run_forecast_pipeline(
        plan_path=plan_path,
        shipment_path=shipment_path,
        linkage_path=linkage_path,
        external_drivers_path=external_drivers_path,
        include_product_id=include_product_id,
        model=model,
    )
    if fc.empty:
        return pd.DataFrame()
    return rollup_forecast(fc, level)


def get_historic_actuals_at_level(
    level: str,
    plan_path=None,
    shipment_path=None,
    linkage_path=None,
) -> pd.DataFrame:
    """Get historic actuals (2023) rolled up at level. Returns long format: group keys + year_month + volume."""
    plan = load_plan(plan_path)
    shipments = load_shipments(shipment_path)
    if plan.empty or shipments.empty:
        return pd.DataFrame()
    plan_sku = plan_to_sku_monthly(plan)
    if plan_sku.empty:
        return pd.DataFrame()
    actual_plant = actuals_by_plant_month(shipments)
    linkage = load_linkage_product_ids(linkage_path)
    if not linkage.empty:
        sku_actual = sku_level_actuals_from_shipment_linkage(
            shipments, linkage, plan_sku, actual_plant
        )
    else:
        sku_actual = sku_level_actuals_from_plan_proportion(plan_sku, actual_plant)
    if sku_actual.empty:
        return pd.DataFrame()
    return rollup_actuals_long(sku_actual, level)
