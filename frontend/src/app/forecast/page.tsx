"use client";

import { useEffect, useState, useMemo, useRef, useCallback } from "react";

const API_BASE =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || ""
    : process.env.NEXT_PUBLIC_API_URL || "http://backend:8000";

type ForecastRow = Record<string, number | string | null>;
type ModelKpis = { n?: number; mae?: number | null; rmse?: number | null; mape?: number | null };
type ComparisonState = {
  xgb: { kpis: ModelKpis; total_volume_2024: number };
  lgbm: { kpis: ModelKpis; total_volume_2024: number };
} | null;

const MONTH_COLS = Array.from({ length: 12 }, (_, i) => `2024-${String(i + 1).padStart(2, "0")}`);
const KEY_COLS = ["Plant", "Series", "Model", "Version", "PRODUCT_ID"];
const FILTER_SORT_COLS = ["Plant", "Series", "Model", "PRODUCT_ID"] as const;

function keyColsFor(rows: ForecastRow[]): string[] {
  if (!rows.length) return KEY_COLS;
  return KEY_COLS.filter((k) => k in rows[0]);
}

function applyFilter(rows: ForecastRow[], filters: Record<string, string>): ForecastRow[] {
  if (!rows.length) return rows;
  return rows.filter((row) => {
    for (const col of FILTER_SORT_COLS) {
      const q = (filters[col] ?? "").trim().toLowerCase();
      if (!q) continue;
      const s = row[col] == null ? "" : String(row[col]).toLowerCase();
      if (!s.includes(q)) return false;
    }
    return true;
  });
}

function applySort(rows: ForecastRow[], sortBy: string | null, sortDir: "asc" | "desc"): ForecastRow[] {
  if (!sortBy || !rows.length || !(sortBy in rows[0])) return [...rows];
  return [...rows].sort((a, b) => {
    const va = a[sortBy];
    const vb = b[sortBy];
    const numA = typeof va === "number" ? va : Number(va);
    const numB = typeof vb === "number" ? vb : Number(vb);
    const useNum = Number.isFinite(numA) && Number.isFinite(numB);
    const cmp = useNum ? numA - numB : String(va ?? "").localeCompare(String(vb ?? ""), undefined, { numeric: true });
    return sortDir === "asc" ? cmp : -cmp;
  });
}

function ForecastTable({
  title,
  rows,
  loading,
  scrollRef,
  onScrollSync,
  highlightedRowIndex,
  onRowHover,
}: {
  title: string;
  rows: ForecastRow[];
  loading: boolean;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  onScrollSync: () => void;
  highlightedRowIndex: number | null;
  onRowHover: (index: number | null) => void;
}) {
  const keyCols = keyColsFor(rows);
  return (
    <div className="flex flex-col h-full min-w-0">
      <h2 className="text-lg font-semibold text-slate-200 mb-2 shrink-0">{title}</h2>
      {loading ? (
        <div className="text-slate-400 py-8">Loading…</div>
      ) : (
        <div className="border border-slate-600 rounded-lg flex-1 min-h-0 flex flex-col overflow-hidden">
          <div
            ref={scrollRef}
            onScroll={onScrollSync}
            className="overflow-auto max-h-[calc(100vh-18rem)] min-h-0 flex-1"
          >
            <table className="w-full text-sm">
              <thead className="bg-slate-700/80 sticky top-0 z-10">
                <tr>
                  {keyCols.map((k) => (
                    <th key={k} className="text-left px-3 py-2 font-medium text-slate-200 whitespace-nowrap">{k}</th>
                  ))}
                  {MONTH_COLS.map((m) => (
                    <th key={m} className="text-right px-2 py-2 font-medium text-slate-200">{m}</th>
                  ))}
                  <th className="text-right px-3 py-2 font-medium text-slate-200">Total</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  const total = MONTH_COLS.reduce((s, c) => s + (Number(row[c]) || 0), 0);
                  const isHighlighted = highlightedRowIndex === i;
                  return (
                    <tr
                      key={i}
                      className={`border-t border-slate-600/50 ${isHighlighted ? "bg-sky-900/40" : "hover:bg-slate-700/30"}`}
                      onMouseEnter={() => onRowHover(i)}
                      onMouseLeave={() => onRowHover(null)}
                    >
                      {keyCols.map((k) => (
                        <td key={k} className="px-3 py-2 text-slate-200">{row[k] ?? "—"}</td>
                      ))}
                      {MONTH_COLS.map((m) => (
                        <td key={m} className="px-2 py-2 text-right tabular-nums text-slate-200">
                          {Number(row[m])?.toLocaleString() ?? "—"}
                        </td>
                      ))}
                      <td className="px-3 py-2 text-right font-medium tabular-nums text-slate-200">{total.toLocaleString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ForecastPage() {
  const [level, setLevel] = useState("sku");
  const [levels, setLevels] = useState<string[]>([]);
  const [rowsXgb, setRowsXgb] = useState<ForecastRow[]>([]);
  const [rowsLgbm, setRowsLgbm] = useState<ForecastRow[]>([]);
  const [comparison, setComparison] = useState<ComparisonState>(null);
  const [loading, setLoading] = useState(true);
  const [loadingCompare, setLoadingCompare] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({ Plant: "", Series: "", Model: "", PRODUCT_ID: "" });
  const [sortBy, setSortBy] = useState<string | null>("Plant");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [hoveredRowIndex, setHoveredRowIndex] = useState<number | null>(null);
  const scrollXgbRef = useRef<HTMLDivElement | null>(null);
  const scrollLgbmRef = useRef<HTMLDivElement | null>(null);
  const syncingScrollRef = useRef(false);

  const syncScrollFromXgb = useCallback(() => {
    if (syncingScrollRef.current || !scrollXgbRef.current || !scrollLgbmRef.current) return;
    syncingScrollRef.current = true;
    scrollLgbmRef.current.scrollTop = scrollXgbRef.current.scrollTop;
    scrollLgbmRef.current.scrollLeft = scrollXgbRef.current.scrollLeft;
    requestAnimationFrame(() => { syncingScrollRef.current = false; });
  }, []);
  const syncScrollFromLgbm = useCallback(() => {
    if (syncingScrollRef.current || !scrollLgbmRef.current || !scrollXgbRef.current) return;
    syncingScrollRef.current = true;
    scrollXgbRef.current.scrollTop = scrollLgbmRef.current.scrollTop;
    scrollXgbRef.current.scrollLeft = scrollLgbmRef.current.scrollLeft;
    requestAnimationFrame(() => { syncingScrollRef.current = false; });
  }, []);

  const filteredSortedXgb = useMemo(
    () => applySort(applyFilter(rowsXgb, filters), sortBy, sortDir),
    [rowsXgb, filters, sortBy, sortDir]
  );
  const filteredSortedLgbm = useMemo(
    () => applySort(applyFilter(rowsLgbm, filters), sortBy, sortDir),
    [rowsLgbm, filters, sortBy, sortDir]
  );

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch(`${API_BASE}/api/forecast?level=${level}&model=xgb`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText)))),
      fetch(`${API_BASE}/api/forecast?level=${level}&model=lgbm`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText)))),
    ])
      .then(([dataXgb, dataLgbm]) => {
        setRowsXgb(dataXgb.rows || []);
        setRowsLgbm(dataLgbm.rows || []);
      })
      .catch((e) => {
        setError(e.message || "Failed to load forecast");
        setRowsXgb([]);
        setRowsLgbm([]);
      })
      .finally(() => setLoading(false));
  }, [level]);

  useEffect(() => {
    setLoadingCompare(true);
    fetch(`${API_BASE}/api/forecast/compare`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data) => setComparison(data.comparison || null))
      .catch(() => setComparison(null))
      .finally(() => setLoadingCompare(false));
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/hierarchy`)
      .then((r) => r.json())
      .then((data) => setLevels(data.levels || ["sku", "model", "series", "plant"]))
      .catch(() => setLevels(["sku", "model", "series", "plant"]));
  }, []);

  const hasProductId = rowsXgb.length > 0 && "PRODUCT_ID" in rowsXgb[0];

  return (
    <main className="w-full min-h-screen flex flex-col p-4">
      <div className="shrink-0 flex items-center gap-4 mb-3">
        <h1 className="text-xl font-bold text-slate-100">Demand Forecast 2024</h1>
      </div>
      <p className="text-slate-500 text-sm mb-6">XGBoost vs LightGBM — side-by-side with comparison KPIs</p>

      <div className="shrink-0 flex flex-wrap items-center gap-3 mb-3">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-400">Level</label>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="border border-slate-600 rounded px-2 py-1 text-sm bg-slate-800 text-slate-200"
          >
            {levels.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>
        <span className="text-slate-600">|</span>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-400">Filter</span>
          {FILTER_SORT_COLS.filter((c) => c !== "PRODUCT_ID" || hasProductId).map((col) => (
            <input
              key={col}
              type="text"
              placeholder={col}
              value={filters[col] ?? ""}
              onChange={(e) => setFilters((prev) => ({ ...prev, [col]: e.target.value }))}
              className="w-24 border border-slate-600 rounded px-2 py-1 text-sm bg-slate-800 text-slate-200 placeholder-slate-500"
            />
          ))}
        </div>
        <span className="text-slate-600">|</span>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-400">Sort</label>
          <select
            value={sortBy ?? ""}
            onChange={(e) => setSortBy(e.target.value || null)}
            className="border border-slate-600 rounded px-2 py-1 text-sm bg-slate-800 text-slate-200"
          >
            {FILTER_SORT_COLS.filter((c) => c !== "PRODUCT_ID" || hasProductId).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
            className="border border-slate-600 rounded px-2 py-1 text-sm bg-slate-700 text-slate-200 hover:bg-slate-600"
          >
            {sortDir === "asc" ? "↑" : "↓"}
          </button>
        </div>
      </div>

      {error && (
        <div className="shrink-0 mb-3 p-2 bg-red-900/30 border border-red-600 rounded text-red-300 text-sm">{error}</div>
      )}

      <section className="shrink-0 grid grid-cols-2 gap-3 mb-3 max-w-2xl">
        {loadingCompare ? (
          <div className="text-slate-500 text-sm">Loading KPIs…</div>
        ) : comparison ? (
          <>
            <div className="border border-slate-600 rounded p-3 bg-slate-800/50 text-sm">
              <h3 className="font-medium text-slate-200 mb-2">XGBoost</h3>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <span className="text-slate-500">MAE</span><span className="font-mono text-slate-200">{comparison.xgb.kpis?.mae ?? "—"}</span>
                <span className="text-slate-500">RMSE</span><span className="font-mono text-slate-200">{comparison.xgb.kpis?.rmse ?? "—"}</span>
                <span className="text-slate-500">MAPE%</span><span className="font-mono text-slate-200">{comparison.xgb.kpis?.mape ?? "—"}</span>
                <span className="text-slate-500">Vol 2024</span><span className="font-mono text-slate-200">{comparison.xgb.total_volume_2024?.toLocaleString() ?? "—"}</span>
              </div>
            </div>
            <div className="border border-slate-600 rounded p-3 bg-slate-800/50 text-sm">
              <h3 className="font-medium text-slate-200 mb-2">LightGBM</h3>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <span className="text-slate-500">MAE</span><span className="font-mono text-slate-200">{comparison.lgbm.kpis?.mae ?? "—"}</span>
                <span className="text-slate-500">RMSE</span><span className="font-mono text-slate-200">{comparison.lgbm.kpis?.rmse ?? "—"}</span>
                <span className="text-slate-500">MAPE%</span><span className="font-mono text-slate-200">{comparison.lgbm.kpis?.mape ?? "—"}</span>
                <span className="text-slate-500">Vol 2024</span><span className="font-mono text-slate-200">{comparison.lgbm.total_volume_2024?.toLocaleString() ?? "—"}</span>
              </div>
            </div>
          </>
        ) : null}
      </section>

      <section className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ForecastTable
          title="XGBoost"
          rows={filteredSortedXgb}
          loading={loading}
          scrollRef={scrollXgbRef}
          onScrollSync={syncScrollFromXgb}
          highlightedRowIndex={hoveredRowIndex}
          onRowHover={setHoveredRowIndex}
        />
        <ForecastTable
          title="LightGBM"
          rows={filteredSortedLgbm}
          loading={loading}
          scrollRef={scrollLgbmRef}
          onScrollSync={syncScrollFromLgbm}
          highlightedRowIndex={hoveredRowIndex}
          onRowHover={setHoveredRowIndex}
        />
      </section>
    </main>
  );
}
