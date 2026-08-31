"use client";

import { useEffect, useMemo, useState } from "react";
import { useLanguage } from "@/i18n/LanguageContext";

const API_BASE =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || ""
    : process.env.NEXT_PUBLIC_API_URL || "http://backend:8000";

type ShipmentRow = Record<string, number | string>;

const LEVELS = ["sku", "model", "series", "plant"];

export default function HistoryPage() {
  const { t } = useLanguage();
  const [level, setLevel] = useState("plant");
  const [rows, setRows] = useState<ShipmentRow[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/history/shipments?level=${encodeURIComponent(level)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data) => {
        setRows(data.rows || []);
        setColumns(data.columns || []);
      })
      .catch((e) => {
        setError(e.message || "Failed to load shipment history");
        setRows([]);
        setColumns([]);
      })
      .finally(() => setLoading(false));
  }, [level]);

  const monthCols = useMemo(
    () => columns.filter((c) => c.includes("-")).sort(),
    [columns]
  );

  const keyCols = useMemo(
    () => columns.filter((c) => !c.includes("-")),
    [columns]
  );

  return (
    <main className="w-full min-h-screen flex flex-col p-4">
      <div className="shrink-0 flex items-center gap-4 mb-3">
        <h1 className="text-xl font-bold text-slate-100">{t("history.title")}</h1>
      </div>
      <p className="text-slate-500 text-sm mb-4">
        {t("history.subtitle")}
      </p>

      <div className="shrink-0 flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-400">{t("history.level")}</label>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="border border-slate-600 rounded px-2 py-1 text-sm bg-slate-800 text-slate-200"
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="shrink-0 mb-3 p-2 bg-red-900/30 border border-red-600 rounded text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-slate-500 py-8">{t("common.loading")}</div>
      ) : rows.length === 0 ? (
        <div className="text-slate-500 py-8">{t("history.noData")}</div>
      ) : (
        <section className="flex-1 min-h-0 border border-slate-600 rounded-lg overflow-auto bg-slate-900/40">
          <table className="w-full text-sm">
            <thead className="bg-slate-800 sticky top-0 z-10">
              <tr>
                {keyCols.map((k) => (
                  <th
                    key={k}
                    className="text-left px-3 py-2 font-medium text-slate-200 whitespace-nowrap"
                  >
                    {k}
                  </th>
                ))}
                {monthCols.map((m) => (
                  <th
                    key={m}
                    className="text-right px-2 py-2 font-medium text-slate-200"
                  >
                    {m}
                  </th>
                ))}
                <th className="text-right px-3 py-2 font-medium text-slate-200">
                  {t("common.total")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => {
                const total = monthCols.reduce(
                  (sum, m) => sum + (Number(row[m]) || 0),
                  0
                );
                return (
                  <tr
                    key={idx}
                    className="border-t border-slate-700/60 hover:bg-slate-800/40"
                  >
                    {keyCols.map((k) => (
                      <td key={k} className="px-3 py-2 text-slate-200">
                        {row[k] as string}
                      </td>
                    ))}
                    {monthCols.map((m) => (
                      <td
                        key={m}
                        className="px-2 py-2 text-right tabular-nums text-slate-200"
                      >
                        {Number(row[m])?.toLocaleString() ?? "0"}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-right font-medium tabular-nums text-slate-200">
                      {total.toLocaleString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}

