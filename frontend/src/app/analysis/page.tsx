"use client";

import { useEffect, useState, useMemo } from "react";
import { useLanguage } from "@/i18n/LanguageContext";

const API_BASE =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || ""
    : process.env.NEXT_PUBLIC_API_URL || "http://backend:8000";

type SeriesItem = {
  key: string;
  label: string;
  historic: (number | null)[];
  forecast: (number | null)[];
};

type VolumeTimeseriesResponse = {
  level: string;
  model: string;
  year_months_historic: string[];
  year_months_forecast: string[];
  series: SeriesItem[];
};

const LEVELS = ["plant", "series", "model", "sku"];
const SERIES_COLORS = ["#38bdf8", "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#22d3ee"];
const MAX_CHART_SERIES = 12;

function VolumeChart({
  data,
  resolution,
  maxSeries = MAX_CHART_SERIES,
  width = 900,
  height = 400,
  padding = { top: 24, right: 24, bottom: 36, left: 56 },
}: {
  data: VolumeTimeseriesResponse | null;
  resolution: "month" | "quarter";
  maxSeries?: number;
  width?: number;
  height?: number;
  padding?: { top: number; right: number; bottom: number; left: number };
}) {
  const { t } = useLanguage();
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const { months, yMax, pointsBySeries, totalSeries, capped } = useMemo(() => {
    if (!data?.series?.length) {
      return {
        months: [] as string[],
        yMax: 0,
        pointsBySeries: [] as {
          key: string;
          label: string;
          historic: [number, number][];
          forecast: [number, number][];
        }[],
        totalSeries: 0,
        capped: false,
      };
    }
    const monthsHistoric = data.year_months_historic || [];
    const monthsForecast = data.year_months_forecast || [];
    const totalSeries = data.series.length;
    // Sort by total volume (historic + forecast) descending, then cap
    const seriesWithTotal = data.series.map((s) => {
      const hSum = (s.historic || []).reduce(
        (a, v) => a + (typeof v === "number" && !Number.isNaN(v) ? v : 0),
        0
      );
      const fSum = (s.forecast || []).reduce(
        (a, v) => a + (typeof v === "number" && !Number.isNaN(v) ? v : 0),
        0
      );
      return { s, total: hSum + fSum };
    });
    seriesWithTotal.sort((a, b) => b.total - a.total);
    const capped = totalSeries > maxSeries;
    const seriesToPlot = seriesWithTotal.slice(0, maxSeries).map(({ s }) => s);

    let yMax = 0;

    if (resolution === "month") {
      const allMonths = [...monthsHistoric, ...monthsForecast];
      const pointsBySeries = seriesToPlot.map((s) => {
        const historic: [number, number][] = [];
        const forecast: [number, number][] = [];
        (s.historic || []).forEach((v, i) => {
          const val = typeof v === "number" && !Number.isNaN(v) ? v : 0;
          if (val > yMax) yMax = val;
          historic.push([i, val]);
        });
        (s.forecast || []).forEach((v, i) => {
          const val = typeof v === "number" && !Number.isNaN(v) ? v : 0;
          if (val > yMax) yMax = val;
          forecast.push([monthsHistoric.length + i, val]);
        });
        return { key: s.key, label: s.label, historic, forecast };
      });
      if (yMax === 0) yMax = 1;
      return { months: allMonths, yMax, pointsBySeries, totalSeries, capped };
    }

    // Quarterly rollup
    const makeQuarterLabels = (yearMonths: string[]) => {
      if (!yearMonths.length) return [] as string[];
      const year = yearMonths[0].slice(0, 4);
      return [`${year}-Q1`, `${year}-Q2`, `${year}-Q3`, `${year}-Q4`];
    };
    const histQuarterLabels = makeQuarterLabels(monthsHistoric);
    const fcQuarterLabels = makeQuarterLabels(monthsForecast);
    const allMonths = [...histQuarterLabels, ...fcQuarterLabels];

    const sumQuarter = (vals: (number | null)[], qIndex: number) => {
      const start = qIndex * 3;
      let sum = 0;
      for (let i = 0; i < 3; i += 1) {
        const v = vals[start + i];
        if (typeof v === "number" && !Number.isNaN(v)) {
          sum += v;
        }
      }
      return sum;
    };

    const pointsBySeries = seriesToPlot.map((s) => {
      const historic: [number, number][] = [];
      const forecast: [number, number][] = [];
      if ((s.historic || []).length >= 12) {
        for (let q = 0; q < 4; q += 1) {
          const val = sumQuarter(s.historic || [], q);
          if (val > yMax) yMax = val;
          historic.push([q, val]);
        }
      }
      if ((s.forecast || []).length >= 12) {
        for (let q = 0; q < 4; q += 1) {
          const val = sumQuarter(s.forecast || [], q);
          if (val > yMax) yMax = val;
          forecast.push([4 + q, val]);
        }
      }
      return { key: s.key, label: s.label, historic, forecast };
    });

    if (yMax === 0) yMax = 1;
    return { months: allMonths, yMax, pointsBySeries, totalSeries, capped };
  }, [data, maxSeries, resolution]);

  const xScale = (i: number) =>
    padding.left + (i / Math.max(months.length - 1, 1)) * chartWidth;
  const yScale = (v: number) =>
    padding.top + chartHeight - (v / yMax) * chartHeight;

  const labelStep = resolution === "month" ? 3 : 1;
  const labelIndices = months.map((_, i) => i).filter((i) => i % labelStep === 0);

  if (!data?.series?.length) {
    return (
      <div className="rounded-lg border border-slate-600 bg-slate-800/50 flex items-center justify-center text-slate-500" style={{ width, height }}>
        {t("analysis.noSeriesData")}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/50 overflow-hidden">
      <svg width={width} height={height} className="overflow-visible">
        {/* Grid */}
        {[0.25, 0.5, 0.75].map((p) => (
          <line
            key={p}
            x1={padding.left}
            y1={padding.top + chartHeight - p * chartHeight}
            x2={width - padding.right}
            y2={padding.top + chartHeight - p * chartHeight}
            stroke="rgba(148,163,184,0.2)"
            strokeWidth={1}
          />
        ))}
        {labelIndices.map((idx) =>
          idx >= months.length ? null : (
            <line
              key={idx}
              x1={xScale(idx)}
              y1={padding.top}
              x2={xScale(idx)}
              y2={height - padding.bottom}
              stroke="rgba(148,163,184,0.2)"
              strokeWidth={1}
            />
          )
        )}
        {/* X-axis labels */}
        {labelIndices.map((idx) =>
          idx >= months.length ? null : (
            <text
              key={idx}
              x={xScale(idx)}
              y={height - 8}
              textAnchor="middle"
              className="fill-slate-500 text-[10px]"
            >
              {months[idx]}
            </text>
          )
        )}
        {/* Y-axis label */}
        <text x={12} y={padding.top + chartHeight / 2} textAnchor="middle" className="fill-slate-500 text-[10px]" transform={`rotate(-90, 12, ${padding.top + chartHeight / 2})`}>
          {t("analysis.volumeAxisLabel")}
        </text>
        {/* Lines: one color per series; historic solid, forecast dashed */}
        {pointsBySeries.map((s, seriesIdx) => {
          const color = SERIES_COLORS[seriesIdx % SERIES_COLORS.length];
          const historicPath =
            s.historic.length >= 1
              ? s.historic.map(([i, v], idx) => `${idx === 0 ? "M" : "L"} ${xScale(i)} ${yScale(v)}`).join(" ")
              : "";
          const forecastPath =
            s.forecast.length >= 1
              ? s.forecast.map(([i, v], idx) => `${idx === 0 ? "M" : "L"} ${xScale(i)} ${yScale(v)}`).join(" ")
              : "";
          return (
            <g key={s.key}>
              {historicPath && (
                <path
                  d={historicPath}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={0.9}
                />
              )}
              {forecastPath && (
                <path
                  d={forecastPath}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={0.9}
                />
              )}
            </g>
          );
        })}
      </svg>
      {/* Legend: solid = historic, dashed = forecast; series labels with colors */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 pb-2 text-xs items-center">
        {capped && (
          <span className="text-amber-500/90 mr-2">
            {t("analysis.showingTopOf", { n: pointsBySeries.length, total: totalSeries })}
          </span>
        )}
        <span className="text-slate-500 mr-1">{t("analysis.historicLegend")}</span>
        <span className="text-slate-500">{t("analysis.forecastLegend")}</span>
        {pointsBySeries.slice(0, 10).map((s, i) => (
          <span key={s.key} className="flex items-center gap-1.5" title={s.label}>
            <span className="inline-block w-3 h-0.5 rounded" style={{ backgroundColor: SERIES_COLORS[i % SERIES_COLORS.length] }} />
            <span className="text-slate-400 truncate max-w-[140px]">{s.label}</span>
          </span>
        ))}
        {pointsBySeries.length > 10 && <span className="text-slate-500">{t("analysis.moreCount", { n: pointsBySeries.length - 10 })}</span>}
      </div>
    </div>
  );
}

const MAX_SERIES_OPTIONS = [6, 12, 24];

export default function AnalysisPage() {
  const { t } = useLanguage();
  const [level, setLevel] = useState("plant");
  const [model, setModel] = useState("xgb");
  const [resolution, setResolution] = useState<"month" | "quarter">("month");
  const [maxSeries, setMaxSeries] = useState(MAX_CHART_SERIES);
  const [data, setData] = useState<VolumeTimeseriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/analysis/volume-timeseries?level=${encodeURIComponent(level)}&model=${encodeURIComponent(model)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then(setData)
      .catch((e) => {
        setError(e.message || "Failed to load volume time series");
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [level, model]);

  return (
    <main className="w-full min-h-screen flex flex-col p-4">
      <div className="shrink-0 flex items-center gap-4 mb-3">
        <h1 className="text-xl font-bold text-slate-100">{t("analysis.title")}</h1>
      </div>
      <p className="text-slate-500 text-sm mb-4">
        {t("analysis.subtitle")}
      </p>

      <div className="shrink-0 flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-400">{t("analysis.rollup")}</label>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="border border-slate-600 rounded px-2 py-1 text-sm bg-slate-800 text-slate-200"
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-400">{t("analysis.model")}</label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="border border-slate-600 rounded px-2 py-1 text-sm bg-slate-800 text-slate-200"
          >
            <option value="xgb">XGBoost</option>
            <option value="lgbm">LightGBM</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-400">{t("analysis.xAxis")}</label>
          <select
            value={resolution}
            onChange={(e) => setResolution(e.target.value as "month" | "quarter")}
            className="border border-slate-600 rounded px-2 py-1 text-sm bg-slate-800 text-slate-200"
          >
            <option value="month">{t("analysis.monthly")}</option>
            <option value="quarter">{t("analysis.quarterly")}</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-400">{t("analysis.maxSeries")}</label>
          <select
            value={maxSeries}
            onChange={(e) => setMaxSeries(Number(e.target.value))}
            className="border border-slate-600 rounded px-2 py-1 text-sm bg-slate-800 text-slate-200"
          >
            {MAX_SERIES_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
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
      ) : (
        <div className="flex-1 min-w-0">
          <VolumeChart
            data={data}
            resolution={resolution}
            maxSeries={maxSeries}
            width={900}
            height={420}
          />
        </div>
      )}
    </main>
  );
}
