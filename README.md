# Demand Forecast

Full-stack demand forecast: **SKU-level** (Plant × Series × Model × Version) with **hierarchy rollup** (Series → Model → Version), powered by **XGBoost**.  
Frontend: **Next.js**, Backend: **FastAPI**, Deployment: **Docker Compose**.

## Data

- **data/dp.csv**: Plan by Plant, Customer, Territory, **Series**, **Model**, **Version**, monthly 2023-01..2023-12.
- **data/shipment.csv**: Shipments: LOCATION_ID, PRODUCT_ID, DATE_ID_SHIPPED, CUSTOMER_ID, Quantity.
- **data/external_drivers.csv** (optional): **Indices table** — single source of truth for learn and forecast. Must have column `year_month` (e.g. `2023-01`, `2024-01`) and numeric columns for registered indices (e.g. `industry_sentiment`, `trade_policy`, `us_semi_tariff_china`). One row per month. Only columns in the registry are used; these are merged into the forecast features (industry-wide). Set `EXTERNAL_DRIVERS_PATH` or place at `data/external_drivers.csv`.

  **Populating external drivers:** A subsystem fills learn + forecast periods from a pre-determined set of indices (see **External drivers subsystem** below). Run `python scripts/populate_external_drivers.py` from project root (with `backend` on `PYTHONPATH`) or call `POST /api/external-drivers/populate`. Optional overrides CSV (same columns as `external_drivers.csv`) can supply or override values.

Product hierarchy: **Series → Model → Version** (SKU = Plant + Series + Model + Version). Forecast can be rolled up at **sku | model | series | plant**.

## Quick start (Docker Compose)

### Dev (default) — local mounts + hot reload

```bash
cd /path/to/dp
docker compose up --build
```

- **Backend**: `./backend/app` mounted at `/app/app`; uvicorn runs with `--reload` (code changes restart the server).
- **Frontend**: `./frontend` mounted at `/app`; Next.js runs `npm run dev` (hot reload). `node_modules` lives in a named volume so installs persist.
- **Data**: `./data` mounted at `/data` in the backend (read-write so external_drivers.csv can be updated from the UI).

- **Frontend**: http://localhost:3000  
- **Backend API**: http://localhost:8000 — docs at http://localhost:8000/docs  

### Prod — built images, no source mounts

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

- **Backend**: No app mount; uvicorn runs without `--reload`.
- **Frontend**: Built standalone Next.js app; no source mount; `next start` (or standalone server).
- **Data**: `./data` still mounted at `/data` for the backend.

## Backend (FastAPI)

- **Port**: 8000  
- **Endpoints**:
  - `GET /api/health` — health check
  - `GET /api/hierarchy` — product hierarchy nodes and rollup levels
  - `GET /api/forecast?level=sku|model|series|plant` — 2024 forecast at chosen level (XGBoost)
  - `GET /api/forecast/sku` — full SKU-level 2024 forecast
  - **External drivers:** `GET /api/external-drivers/schema` — list of indices (id, name, description, default_value); `GET /api/external-drivers?start=&end=` — current values; `POST /api/external-drivers/values` — update values (merge with CSV); `POST /api/external-drivers/populate` — (re)populate CSV for learn + forecast periods.

- **Algorithm**: XGBoost at SKU level using 2023 plan + scaled actuals (plant actual × plan proportion). Features: month, lag_1 (prior month), lag_12 (same month last year), mean_2023. Predictions rolled up at model / series / plant as requested.

- **PRODUCT_ID in forecast**: If a linkage report exists, the forecast table includes shipment **PRODUCT_ID** (e.g. 500-3186). Run `python scripts/explore_model_description_linkage.py` to generate `output/linkage_report.csv`. For Docker, copy it to `data/linkage_report.csv` or set `LINKAGE_PATH`. At SKU level the table has one row per (Plant, Series, Model, Version, PRODUCT_ID); rollups (model/series/plant) aggregate correctly without double-counting.

- **Data path**: Set `DATA_DIR` (default: project `data/` when run locally; in Docker use `/data` via volume).

## Frontend (Next.js)

- **Port**: 3000  
- **App**: Single page — “Demand Forecast 2024” table and a **Rollup level** dropdown (sku, model, series, plant). Table shows Plant, Series, Model, Version, PRODUCT_ID (when linkage exists), 2024-01..2024-12, and Total.

- **Local dev** (backend on host):  
  `cd frontend && npm install && npm run dev`  
  Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local` so the app calls the backend.

## Project layout

```
dp/
├── data/
│   ├── dp.csv
│   └── shipment.csv
├── backend/                 # FastAPI + XGBoost
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── schemas.py
│       ├── api/forecast.py
│       └── services/
│           ├── data.py       # load plan/shipment, SKU monthly
│           ├── hierarchy.py  # rollup levels
│           └── forecast_xgb.py
├── frontend/                # Next.js
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   └── src/app/
│       ├── layout.tsx
│       ├── page.tsx         # forecast table + level selector
│       └── globals.css
├── demand_planning/         # CLI / library (plant-level, no XGBoost)
│   ├── loaders.py
│   └── forecast.py
├── docker-compose.yml
├── run.py                   # CLI: python run.py
└── README.md
```

## CLI (optional)

From project root, without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py [--method naive_seasonal|plan_adjusted|simple_average]
```

This uses the existing **plant-level** forecast (naive/plan_adjusted/simple_average) and writes `output/forecast_2024*.csv`. The **SKU-level XGBoost** forecast and rollup are available only via the FastAPI backend and the Next.js UI.

## External drivers subsystem

External drivers (taxation, industry sentiment, trade policy) are populated for **learn** (e.g. 2023) and **forecast** (e.g. 2024) periods. For **how to find raw sources** and **how to turn them into numerics** for the model, see [docs/external_drivers_sourcing.md](docs/external_drivers_sourcing.md).

- **Pre-determined indices:** `industry_sentiment`, `trade_policy` (US–China relationship, qualitative), `us_semi_tariff_china` (see `backend/app/services/external_drivers_subsystem.py`). Tax/tariff is covered by `us_semi_tariff_china`. Each has a default value and optional suggested sources (built-in, file, URL, or custom).
- **US import tax (semiconductor, China):** Index `us_semi_tariff_china` is the US ad valorem tariff rate (%) for semiconductor goods (HTS 8541, 8542) from China (Section 301). Raw data is built from **reliable official effective dates** (USTR/FR): 25% from 2018-07, 50% from 2025-01. Use **Indices** in the UI and choose “Curated from USTR/FR effective dates (built-in)” or “CSV in repo”; or run `python3 scripts/build_us_semi_tariff_china.py` to (re)generate `data/us_semi_tariff_china.csv` (format: `year_month`, `us_semi_tariff_china`). Sources are documented in `backend/app/services/us_semi_tariff_source.py` and the script.
- **Populate:** Run `python scripts/populate_external_drivers.py` from project root (with `backend` on path), or `POST /api/external-drivers/populate`. To fetch from chosen sources (including built-in tariff series), use **Indices** → select index(es) and source → “Fetch & populate”, or `POST /api/external-drivers/fetch` with `indices` and optional `source_overrides`.
- **Non-deterministic indices** (e.g. US–China relationship): System provides **starter info sources** (Pew, CFR, CSIS); users can add their own. **Process text → numeric:** paste text (e.g. from a report) and the system converts it to a score via LLM when `OPENAI_API_KEY` is set (otherwise a stub value is returned). Use **Indices** → select the index → paste text → “Convert to number” → “Apply to drivers”. For **volumes** (month-by-month indices): **Batch import** — upload a CSV or paste one with columns `year_month` and `text` (or `raw_text`); one request processes all rows and writes to the indices table. API: `POST /api/external-drivers/process-text`, `POST /api/external-drivers/process-text-and-apply`, `POST /api/external-drivers/process-text-batch`, `POST /api/external-drivers/process-text-file` (multipart CSV). Set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`, default `gpt-4o-mini`) for LLM-based conversion.
- **API:** `GET /api/external-drivers/schema` returns the index registry (with `suggested_sources`, `starter_sources`, `deterministic`) and required year_months; `GET /api/external-drivers` returns current values; `POST /api/external-drivers/values` merges provided rows into the CSV; `POST /api/external-drivers/fetch` fetches from selected sources and populates the CSV.
- **Future:** The design allows an agent to guide users in choosing indices and populating values (e.g. suggest indices, recommend sources, or fill from external APIs).
