#!/usr/bin/env python3
"""
Build data/us_semi_tariff_china.csv from official effective dates.
Format: year_month, us_semi_tariff_china (ad valorem rate in %).

Reliable sources:
- USTR Section 301 China List 1: effective 2018-07-06, 25% (FR 2018-07-10).
- USTR Section 301 semiconductor increase: 50% effective 2025-01-01 (Biden admin, 2024).
- HTS 8541, 8542 (semiconductors) subject to Section 301 when listed.

Run from repo root: python scripts/build_us_semi_tariff_china.py [--output path] [--start YYYY-MM] [--end YYYY-MM]
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Same effective dates as backend/app/services/us_semi_tariff_source.py
EFFECTIVE_DATES = [
    ("2018-07", 25.0),   # Section 301 List 1 (USTR, FR 2018-07-10)
    ("2025-01", 50.0),   # Section 301 semiconductor increase (USTR, 2024)
]


def rate_at(ym: str) -> float:
    r = 0.0
    for eff_ym, rate in sorted(EFFECTIVE_DATES, key=lambda x: x[0]):
        if eff_ym <= ym:
            r = rate
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description="Build US semi tariff (China) CSV from USTR/FR effective dates.")
    ap.add_argument("--output", "-o", default="data/us_semi_tariff_china.csv", help="Output CSV path")
    ap.add_argument("--start", default="2018-01", help="Start year_month (YYYY-MM)")
    ap.add_argument("--end", default="2026-12", help="End year_month (YYYY-MM)")
    args = ap.parse_args()

    start_y, start_m = map(int, args.start.split("-"))
    end_y, end_m = map(int, args.end.split("-"))

    year_months = []
    y, m = start_y, start_m
    while (y, m) <= (end_y, end_m):
        year_months.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    rows = [{"year_month": ym, "us_semi_tariff_china": rate_at(ym)} for ym in year_months]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("year_month,us_semi_tariff_china\n")
        for row in rows:
            f.write(f"{row['year_month']},{row['us_semi_tariff_china']}\n")
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
