import os
from pathlib import Path

_default_data = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR = Path(os.getenv("DATA_DIR", str(_default_data)))
PLAN_PATH = DATA_DIR / "dp.csv"
SHIPMENT_PATH = DATA_DIR / "shipment.csv"
# Linkage report: copy output/linkage_report.csv to data/ for Docker, or set LINKAGE_PATH.
LINKAGE_PATH = Path(os.getenv("LINKAGE_PATH", str(DATA_DIR / "linkage_report.csv")))
# External drivers (taxation, industry sentiment, trade policy): optional CSV with year_month + driver columns.
EXTERNAL_DRIVERS_PATH = Path(os.getenv("EXTERNAL_DRIVERS_PATH", str(DATA_DIR / "external_drivers.csv")))

# Local doc repo for US–China relationship: folders/files named MM_YYYY (e.g. 01_2023, 12_2024) hold documents per month.
TRADE_POLICY_DOCS_PATH = Path(os.getenv("TRADE_POLICY_DOCS_PATH", str(DATA_DIR / "trade_policy_docs")))

MONTH_COLS = [f"2023-{m:02d}" for m in range(1, 13)]
FORECAST_MONTHS = [f"2024-{m:02d}" for m in range(1, 13)]
