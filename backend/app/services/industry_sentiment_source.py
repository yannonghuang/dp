"""
Industry sentiment (semiconductor) composite:
- Annual anchor from KPMG/GSA semiconductor confidence index (0–100).
- Monthly shape from an electronics/tech PMI (50 = neutral).

This module expects two optional CSVs under DATA_DIR:
- kpmg_semi_confidence.csv: year,confidence
- electronics_pmi.csv: year_month,pmi

If they are missing or incomplete, falls back to a flat series using the
registry default_value for industry_sentiment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from app.config import DATA_DIR
from app.services.external_drivers_subsystem import get_registry

KPMG_PATH = DATA_DIR / "kpmg_semi_confidence.csv"
PMI_PATH = DATA_DIR / "electronics_pmi.csv"


def _load_kpmg_confidence() -> dict[int, float]:
  """Load {year: confidence} from CSV if present."""
  if not KPMG_PATH.exists():
    return {}
  df = pd.read_csv(KPMG_PATH)
  if "year" not in df.columns or "confidence" not in df.columns:
    return {}
  out: dict[int, float] = {}
  for _, row in df.iterrows():
    try:
      y = int(row["year"])
      c = float(row["confidence"])
      out[y] = c
    except Exception:
      continue
  return out


def _load_pmi() -> pd.Series:
  """Load monthly PMI series indexed by year_month if present."""
  if not PMI_PATH.exists():
    return pd.Series(dtype=float)
  df = pd.read_csv(PMI_PATH)
  if "year_month" not in df.columns or "pmi" not in df.columns:
    return pd.Series(dtype=float)
  df["year_month"] = df["year_month"].astype(str)
  s = df.set_index("year_month")["pmi"].astype(float)
  return s


def _pmi_component(pmi: float) -> float:
  """
  Map PMI to a 0–100 component.
  40 -> 0, 50 -> 50, 60 -> 100 (clipped).
  """
  val = (pmi - 40.0) * 5.0
  return max(0.0, min(100.0, val))


def build_industry_sentiment_series(year_months: Iterable[str]) -> pd.Series:
  """
  Build monthly industry_sentiment series for the requested year_months.

  For each month m in year y:
    sentiment(m) = 0.5 * KPMG_conf[y] + 0.5 * pmi_component(PMI[m])

  If KPMG or PMI data is missing, falls back to a flat series using the
  registry default_value for industry_sentiment.
  """
  year_months = [str(ym) for ym in year_months]
  if not year_months:
    return pd.Series(dtype=float)

  # Default from registry
  reg = next((r for r in get_registry() if r["id"] == "industry_sentiment"), None)
  default_val = float(reg.get("default_value", 50.0)) if reg else 50.0

  kpmg = _load_kpmg_confidence()
  pmi_series = _load_pmi()

  if not kpmg or pmi_series.empty:
    # No composite inputs; return flat default
    return pd.Series([default_val for _ in year_months], index=year_months)

  out_vals: list[float] = []
  for ym in year_months:
    try:
      y = int(ym.split("-")[0])
    except Exception:
      out_vals.append(default_val)
      continue
    conf = kpmg.get(y, default_val)
    pmi_val = float(pmi_series.get(ym, pmi_series.mean() if not pmi_series.empty else 50.0))
    pmi_comp = _pmi_component(pmi_val)
    sentiment = 0.5 * conf + 0.5 * pmi_comp
    out_vals.append(float(sentiment))

  return pd.Series(out_vals, index=year_months)

