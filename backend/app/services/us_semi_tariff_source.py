"""
US import tariff rate for semiconductor goods manufactured in China.
Built from official effective dates (no external API); reproducible and auditable.

Reliable sources:
- USTR Section 301 China: List 1 effective 2018-07-06 (25%). FRN 2018-0026.
- USTR Section 301 semiconductor increase: 50% effective 2025-01-01 (Biden admin, Sept 2024 FR).
- HTS 8541, 8542 (semiconductors) subject to Section 301 when listed.
"""

from __future__ import annotations

import pandas as pd

# (year_month, rate_pct): from this month onward, the ad valorem rate applies.
# Update when new FR notices change rates.
EFFECTIVE_DATES = [
    ("2018-07", 25.0),   # Section 301 List 1 (USTR, FR 2018-07-10)
    ("2025-01", 50.0),   # Section 301 semiconductor increase (USTR, 2024)
]


def build_us_semi_tariff_china_series(year_months: list[str]) -> pd.Series:
    """
    Return a Series (index=year_month) of US ad valorem tariff rate (%)
    for semiconductor goods from China. Fills requested year_months using EFFECTIVE_DATES.
    """
    if not year_months:
        return pd.Series(dtype=float)
    # Sort effective dates; for each ym use the latest effective date that is <= ym
    sorted_eff = sorted(EFFECTIVE_DATES, key=lambda x: x[0])
    result = {}
    for ym in year_months:
        rate = 0.0
        for eff_ym, r in sorted_eff:
            if eff_ym <= ym:
                rate = r
        result[ym] = rate
    return pd.Series(result)


def write_csv(path: str | None = None, year_months: list[str] | None = None) -> pd.DataFrame:
    """
    Build the tariff series for given year_months and write CSV with columns
    year_month, us_semi_tariff_china. If year_months is None, use 2018-01 through 2026-12.
    Returns the DataFrame.
    """
    if year_months is None:
        year_months = []
        for y in range(2018, 2027):
            for m in range(1, 13):
                year_months.append(f"{y}-{m:02d}")
    df = pd.DataFrame({"year_month": year_months})
    df["us_semi_tariff_china"] = build_us_semi_tariff_china_series(year_months).values
    if path:
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    return df
