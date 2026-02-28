#!/usr/bin/env python3
"""
Populate external_drivers.csv for the learn period (e.g. 2023) and forecast period (e.g. 2024).
Uses pre-determined indices from the registry; optional overrides CSV to fill or override values.

Usage:
  # From project root (backend on path)
  python scripts/populate_external_drivers.py

  # With overrides (wide: year_month, tax_index, industry_sentiment, trade_policy)
  python scripts/populate_external_drivers.py --overrides data/external_drivers_overrides.csv

  # Custom output path
  python scripts/populate_external_drivers.py --output data/external_drivers.csv

Environment:
  DATA_DIR          default: ./data
  EXTERNAL_DRIVERS_PATH  default: $DATA_DIR/external_drivers.csv
"""

import argparse
import sys
from pathlib import Path

# Allow running from project root with backend on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.config import DATA_DIR, MONTH_COLS, FORECAST_MONTHS, EXTERNAL_DRIVERS_PATH
from app.services.external_drivers_subsystem import (
    get_required_year_months,
    populate,
)


def main():
    parser = argparse.ArgumentParser(description="Populate external drivers CSV for learn + forecast periods.")
    parser.add_argument("--overrides", type=Path, default=None, help="CSV with year_month and index columns to override defaults")
    parser.add_argument("--output", type=Path, default=None, help="Output CSV path (default: data/external_drivers.csv)")
    args = parser.parse_args()

    learn_months = list(MONTH_COLS)
    forecast_months = list(FORECAST_MONTHS)

    overrides_path = args.overrides
    if overrides_path and not overrides_path.is_absolute():
        overrides_path = ROOT / overrides_path
    output_path = args.output
    if output_path and not output_path.is_absolute():
        output_path = ROOT / output_path
    else:
        output_path = EXTERNAL_DRIVERS_PATH

    df = populate(
        learn_months=learn_months,
        forecast_months=forecast_months,
        overrides_path=overrides_path,
        output_path=output_path,
    )
    print(f"Wrote {len(df)} rows to {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
