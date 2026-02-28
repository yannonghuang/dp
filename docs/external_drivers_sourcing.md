# External drivers: locating sources and turning them into numerics

Two practical questions: (1) how to find relevant raw info sources for each index, and (2) how to turn that info into numbers that feed into the forecast models.

---

## 1. How to locate relevant raw info sources

**By index type**

| Index | Type | Where to look |
|-------|------|----------------|
| **us_semi_tariff_china** | Quantitative (rates, dates) | **Official:** USTR Section 301, Federal Register, USITC HTS. No public API; use effective dates (documented in `backend/app/services/us_semi_tariff_source.py`) or curated CSV. |
| **trade_policy** (US–China relationship) | Qualitative | **Policy / think tanks:** Pew, CFR, CSIS, Brookings (US–China reports, surveys). **News / sentiment:** Reuters, Bloomberg (qualitative → you code to a scale). **Surveys:** business sentiment, policy uncertainty indices. |
| **industry_sentiment** | Quantitative or qualitative | **Surveys:** PMI, industry confidence indices (often 0–100). **Central banks / stats:** regional manufacturing indices. **Custom:** internal surveys or expert scores. |

**General approach**

- **Quantitative (rates, volumes, %):** Prefer official or widely cited series (USTR, OECD, BEA, Census). Check for CSV/API; if not, use effective dates or annual series and map to `year_month`.
- **Qualitative (relationship, tension, sentiment):** Use policy reports, surveys, or news; you define a numeric scale and code periods (see below).
- **Hybrid:** e.g. tariff rate (quantitative) + policy narrative (qualitative) → single “trade policy” score you maintain in a spreadsheet or CSV.

**Useful search terms**

- US–China: “US China relations index”, “US China trade tension”, “Pew US China survey”, “geopolitical risk US China”.
- Industry: “manufacturing PMI”, “industry confidence index”, “business sentiment [sector]”.
- Tariff / tax: “Section 301 effective date”, “HTS 8541 8542”, “semiconductor tariff China”.

---

## 2. How to turn raw info into numerics for the model

The pipeline expects **one number per index per month**: CSV with `year_month` (e.g. `2023-01`) and one column per index (`trade_policy`, `industry_sentiment`, `us_semi_tariff_china`). All values must be **numeric** (integer or float).

**Quantitative sources (already numeric)**

- **Rates, %, counts:** Use as-is. Map to `year_month`: one value per month (repeat annual value for all 12 months, or interpolate if you have quarterly).
- **Effective dates (e.g. tariffs):** Assign a value from the date onward (e.g. 25 → 25% from 2018-07). Our `us_semi_tariff_china` builder does this from USTR/FR dates.

**Qualitative → numeric (coding)**

1. **Define a scale** (e.g. 1–5 or 0–100):  
   - 1 = cooperative / low tension, 5 = confrontational / high tension.  
   - Or 0–100: 0 = most negative, 100 = most positive.
2. **Assign a number to each period** (month or quarter):  
   - Read reports/surveys/news for that period; label as “more cooperative” vs “more confrontational”; map to your scale.
3. **Write a CSV:** `year_month`, `trade_policy` (and other indices). One row per month; use the same value for all months in a quarter if you only have quarterly judgment.
4. **Feed into the app:** Use **Indices** → “Your own (qualitative scale: URL or file path)” and point to your CSV, or paste values via **Update values** / API.

**Example: US–China relationship (qualitative)**

- Scale: 1 = very cooperative, 5 = very confrontational.
- You code: 2023-01–2023-06 → 3; 2023-07–2024-12 → 4 (e.g. after a specific policy shift).
- CSV:

```text
year_month,trade_policy
2023-01,3
2023-02,3
...
2023-06,3
2023-07,4
...
2024-12,4
```

**Example: industry sentiment (0–100)**

- Source: PMI or survey index already 0–100.
- If you only have quarterly: use that value for all three months (e.g. 2023-Q1 = 52 → 2023-01, 2023-02, 2023-03 = 52).

**Rules of thumb**

- **Stability:** Prefer a stable rule (e.g. “quarterly survey → same value for each month in quarter”) so backfills stay consistent.
- **Missing months:** The pipeline merges on `year_month`; missing months can be left out (model may not use that month) or forward-filled when you build the CSV.
- **Units:** Model only sees numbers; document the scale (e.g. “1–5, 5 = most confrontational”) in your process or in the index description in the registry.

---

## 3. Local doc repo (US–China, automated)

For **trade_policy** (US–China relationship) you can use a **local document repository** plus a **crawler** for a smoother, repeatable pipeline:

1. **Setup:** A folder (e.g. `data/trade_policy_docs`, or set `TRADE_POLICY_DOCS_PATH`) acts as the doc repo.
2. **Structure:** Under that folder, use **folders or files** named **MM_YYYY** (e.g. `01_2023`, `02_2023`, …, `12_2024`). Each holds documents pertinent to that month:
   - **Folder:** e.g. `01_2023/` containing `.txt`, `.md`, or `.html` files. All are read and concatenated for that month.
   - **Single file:** e.g. `01_2023.txt` or `01_2023.md` at the repo root.
3. **Backend:** Reads from the repo month-by-month, runs text→numeric (LLM when `OPENAI_API_KEY` is set), and writes indices to `external_drivers.csv`. API: `POST /api/external-drivers/process-doc-repo` (optional `start`/`end` in YYYY-MM).
4. **Crawler:** A robot fetches reliable public sources (Pew, CFR, CSIS). These pages show **current** content, not historical content per month. By default (**snapshot_only=True**), the crawler fetches once and saves only to the **current month** folder (e.g. `02_2026`), so the folder date matches the content. Set `snapshot_only=False` to fill every month in the date range with the same snapshot (only useful if you run the crawler monthly over time to build a time series). API: `POST /api/external-drivers/doc-repo/crawl` with `start`, `end`, and optional `snapshot_only`.

**UX (Indices page):** For US–China relationship, the card shows the repo path and month count, plus **Crawl & save** (uses effective dates) and **Generate indices from doc repo**. So: set effective dates → Crawl & save → Generate indices from doc repo → indices table updates.

**Tested reliable sources (crawler):** The registry uses these URLs (verified reachable and with usable content for text→numeric):

1. **CSIS (China)** — https://www.csis.org/regions/asia/china — Strategic and economic analysis; data-driven research on China.
2. **CFR (China)** — https://www.cfr.org/asia/china — Policy analysis, backgrounders, and articles on China.
3. **Pew Research (China global image)** — https://www.pewresearch.org/topic/international-affairs/global-image-of-countries/china-global-image/ — Public opinion and surveys on global views of China.

To test the crawler locally: `PYTHONPATH=backend python3 scripts/test_trade_policy_crawl.py` (uses a temp dir; set `CRAWL_TEST_USE_REAL_REPO=1` to write to the real doc repo). If you get 0 files, run **Crawl & save** from the Indices UI (browser) or check network/firewall.

---

## 4. Feeding into this repo

- **Indices table = single source of truth:** `data/external_drivers.csv` (or path in `EXTERNAL_DRIVERS_PATH`). Columns: `year_month` plus registered index ids (`industry_sentiment`, `trade_policy`, `us_semi_tariff_china`).
- **Ways to populate:**  
  - **UI:** Indices → choose source (built-in, file, URL, or “Your own”) → Fetch & populate; or Configure (US semi tariff) → set dates → Apply.  
  - **API:** `POST /api/external-drivers/fetch` with `indices` and optional `source_overrides`; or `POST /api/external-drivers/values` with rows.  
  - **Script/CSV:** Build a CSV with the same columns and overwrite or merge into `external_drivers.csv`; or use `scripts/populate_external_drivers.py` with an overrides file.
- Only **registered** index columns are used for learn/forecast; unregistered columns in the CSV are ignored.
