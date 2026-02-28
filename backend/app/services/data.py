"""
Load plan (dp.csv) and shipment (shipment.csv); build SKU-level and plant-level series.
"""

from pathlib import Path
import pandas as pd
from app.config import PLAN_PATH, SHIPMENT_PATH, MONTH_COLS, EXTERNAL_DRIVERS_PATH


def _parse_quantity(val):
    if pd.isna(val) or val == "" or (isinstance(val, str) and str(val).strip() == ""):
        return 0
    s = str(val).strip().replace(",", "")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def load_plan(path: Path | None = None) -> pd.DataFrame:
    path = path or PLAN_PATH
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8", dtype=str)
    df = df.dropna(axis=1, how="all")
    attr = ["Category", "Plant", "Customer", "Territory", "Series", "Model", "Version", "状态", "Application", "备注"]
    month_cols = [c for c in df.columns if c in MONTH_COLS]
    cols = [c for c in df.columns if c in attr or c in month_cols]
    df = df[cols].copy()
    for c in month_cols:
        df[c] = df[c].map(_parse_quantity)
    if "Plant" in df.columns:
        df["Plant"] = pd.to_numeric(df["Plant"], errors="coerce").fillna(0).astype(int)
    if "Customer" in df.columns:
        df["Customer"] = pd.to_numeric(df["Customer"], errors="coerce").fillna(0).astype(int)
    return df


def load_shipments(path: Path | None = None) -> pd.DataFrame:
    path = path or SHIPMENT_PATH
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]

    def parse_date(s):
        if pd.isna(s):
            return pd.NaT
        s = str(s).strip()
        try:
            return pd.to_datetime(s, format="%m/%d/%y")
        except Exception:
            try:
                return pd.to_datetime(s)
            except Exception:
                return pd.NaT

    df["ship_date"] = df["DATE_ID_SHIPPED"].map(parse_date)
    df = df.dropna(subset=["ship_date"])
    df["year_month"] = df["ship_date"].dt.to_period("M").astype(str)
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    if "LOCATION_ID" in df.columns:
        df["LOCATION_ID"] = pd.to_numeric(df["LOCATION_ID"], errors="coerce").fillna(0).astype(int)
    return df


def plan_to_sku_monthly(plan: pd.DataFrame) -> pd.DataFrame:
    """Reshape plan to long: one row per (Plant, Series, Model, Version, year_month) with plan_qty."""
    month_cols = [c for c in plan.columns if c in MONTH_COLS]
    if not month_cols:
        return pd.DataFrame()
    id_cols = [c for c in plan.columns if c not in month_cols]
    long = plan.melt(
        id_vars=id_cols,
        value_vars=month_cols,
        var_name="year_month",
        value_name="plan_qty",
    )
    long["plan_qty"] = pd.to_numeric(long["plan_qty"], errors="coerce").fillna(0).astype(int)
    sku_cols = ["Plant", "Series", "Model", "Version"] if "Version" in long.columns else ["Plant", "Series", "Model"]
    sku_cols = [c for c in sku_cols if c in long.columns]
    return long.groupby(sku_cols + ["year_month"], as_index=False)["plan_qty"].sum()


def load_external_drivers(path: Path | None = None) -> pd.DataFrame:
    """
    Load external drivers by year_month. Indices table (CSV) is the single source of truth for learn and forecast.
    Only columns that are in the external indices registry are used (e.g. industry_sentiment, trade_policy, us_semi_tariff_china).
    CSV must have column 'year_month' and optional numeric columns. Returns empty DataFrame if file missing or invalid.
    """
    from app.services.external_drivers_subsystem import get_registry

    path = path or EXTERNAL_DRIVERS_PATH
    if not path or not Path(path).exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    if "year_month" not in df.columns:
        return pd.DataFrame()
    df["year_month"] = df["year_month"].astype(str)
    # Only use driver columns that are in the registry (single source of truth)
    registered_ids = {r["id"] for r in get_registry()}
    driver_cols = [c for c in df.columns if c != "year_month" and c in registered_ids]
    for c in driver_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["year_month"] + driver_cols] if driver_cols else df[["year_month"]].copy()


def actuals_by_plant_month(shipments: pd.DataFrame) -> pd.DataFrame:
    """Actuals by Plant and year_month (2023)."""
    agg = (
        shipments.groupby(["LOCATION_ID", "year_month"], as_index=False)["Quantity"]
        .sum()
        .rename(columns={"Quantity": "actual_qty", "LOCATION_ID": "Plant"})
    )
    return agg[agg["year_month"].str.startswith("2023-")].copy()


def sku_level_actuals_from_plan_proportion(
    plan_sku: pd.DataFrame, actual_plant: pd.DataFrame
) -> pd.DataFrame:
    """Derive SKU-level 'actuals' by scaling plant actuals by plan proportion per (Plant, year_month)."""
    plan_plant_month = plan_sku.groupby(["Plant", "year_month"], as_index=False)["plan_qty"].sum()
    plan_plant_month = plan_plant_month.rename(columns={"plan_qty": "plant_plan"})
    merged = plan_sku.merge(plan_plant_month, on=["Plant", "year_month"], how="left")
    merged = merged.merge(
        actual_plant.rename(columns={"actual_qty": "plant_actual"}),
        on=["Plant", "year_month"],
        how="left",
    )
    merged["plant_actual"] = merged["plant_actual"].fillna(0)
    merged["plant_plan"] = merged["plant_plan"].replace(0, float("nan"))
    merged["actual_qty"] = (merged["plan_qty"] / merged["plant_plan"] * merged["plant_actual"]).fillna(0).astype(int)
    return merged[["Plant", "Series", "Model", "Version", "year_month", "plan_qty", "actual_qty"]]


def _real_sku_actual_from_shipment_linkage(
    shipments: pd.DataFrame,
    linkage: pd.DataFrame,
    plan_sku: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build real SKU-level actuals from shipment + linkage.
    linkage must have columns: Plant (or LOCATION_ID), PRODUCT_ID, Model.
    Returns (Plant, Series, Model, Version, year_month, actual_qty) for linked lines only; 2023 months only.
    """
    if shipments.empty or linkage.empty or plan_sku.empty:
        return pd.DataFrame()
    # linkage: (Plant, Model, PRODUCT_ID); join with shipment on (LOCATION_ID=Plant, PRODUCT_ID)
    link = linkage.copy()
    link["LOCATION_ID"] = pd.to_numeric(link["Plant"], errors="coerce").fillna(0).astype(int)
    link = link[["LOCATION_ID", "PRODUCT_ID", "Model"]].drop_duplicates()
    ship = shipments[["LOCATION_ID", "PRODUCT_ID", "year_month", "Quantity"]].copy()
    ship["LOCATION_ID"] = pd.to_numeric(ship["LOCATION_ID"], errors="coerce").fillna(0).astype(int)
    ship["PRODUCT_ID"] = ship["PRODUCT_ID"].astype(str)
    link["PRODUCT_ID"] = link["PRODUCT_ID"].astype(str)
    ship_link = ship.merge(link, on=["LOCATION_ID", "PRODUCT_ID"], how="inner")
    if ship_link.empty:
        return pd.DataFrame()
    # (Plant, Model) -> (Series, Version) from plan_sku
    plan_pm = plan_sku[["Plant", "Series", "Model", "Version"]].drop_duplicates(subset=["Plant", "Model"])
    ship_link["Plant"] = ship_link["LOCATION_ID"]
    ship_link = ship_link.merge(plan_pm, on=["Plant", "Model"], how="inner")
    real = (
        ship_link.groupby(["Plant", "Series", "Model", "Version", "year_month"], as_index=False)["Quantity"]
        .sum()
        .rename(columns={"Quantity": "actual_qty"})
    )
    real = real[real["year_month"].str.startswith("2023-")].copy()
    return real


def sku_level_actuals_from_shipment_linkage(
    shipments: pd.DataFrame,
    linkage: pd.DataFrame,
    plan_sku: pd.DataFrame,
    actual_plant: pd.DataFrame,
) -> pd.DataFrame:
    """
    SKU-level actuals using real shipment data where linkage exists, and plan proportion for unlinked.
    linkage must have columns: Plant, PRODUCT_ID, Model.
    Returns same schema as sku_level_actuals_from_plan_proportion.
    """
    real = _real_sku_actual_from_shipment_linkage(shipments, linkage, plan_sku)
    # Start from plan_sku; attach real actuals where we have them
    sku = plan_sku.merge(
        real[["Plant", "Series", "Model", "Version", "year_month", "actual_qty"]],
        on=["Plant", "Series", "Model", "Version", "year_month"],
        how="left",
    )
    sku["actual_qty"] = sku["actual_qty"].fillna(0).astype(int)
    # For each (Plant, year_month): allocate unlinked quantity by plan proportion to SKUs with no real actual
    plan_plant_month = plan_sku.groupby(["Plant", "year_month"], as_index=False)["plan_qty"].sum()
    plan_plant_month = plan_plant_month.rename(columns={"plan_qty": "plant_plan"})
    sku = sku.merge(plan_plant_month, on=["Plant", "year_month"], how="left")
    sku = sku.merge(
        actual_plant.rename(columns={"actual_qty": "plant_actual"}),
        on=["Plant", "year_month"],
        how="left",
    )
    sku["plant_actual"] = sku["plant_actual"].fillna(0)
    linked_total = sku.groupby(["Plant", "year_month"])["actual_qty"].sum().reset_index()
    linked_total = linked_total.rename(columns={"actual_qty": "linked_total"})
    sku = sku.merge(linked_total, on=["Plant", "year_month"], how="left")
    sku["unlinked"] = (sku["plant_actual"] - sku["linked_total"]).clip(lower=0)
    sku["plant_plan"] = sku["plant_plan"].replace(0, float("nan"))
    mask = (sku["actual_qty"] == 0) & (sku["plant_plan"] > 0)
    sku.loc[mask, "actual_qty"] = (
        sku.loc[mask, "unlinked"] * sku.loc[mask, "plan_qty"] / sku.loc[mask, "plant_plan"]
    ).round().astype(int)
    return sku[["Plant", "Series", "Model", "Version", "year_month", "plan_qty", "actual_qty"]]
