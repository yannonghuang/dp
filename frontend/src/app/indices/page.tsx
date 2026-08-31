"use client";

import { useEffect, useState } from "react";
import { useLanguage } from "@/i18n/LanguageContext";

const API_BASE =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || ""
    : process.env.NEXT_PUBLIC_API_URL || "http://backend:8000";

type SuggestedSource = { id: string; label: string; type: string; url?: string; path?: string; builder?: string };
type StarterSource = { id: string; label: string; url?: string; description?: string };
type DriverIndex = {
  id: string;
  name: string;
  description: string;
  default_value?: number;
  deterministic?: boolean;
  source?: { type?: string; label?: string };
  suggested_sources?: SuggestedSource[];
  starter_sources?: StarterSource[];
  text_to_numeric_scale?: { min: number; max: number; description?: string };
};

export default function IndicesPage() {
  const { t, lang } = useLanguage();
  const [schema, setSchema] = useState<{ indices: DriverIndex[] } | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [sourceChoice, setSourceChoice] = useState<Record<string, string>>({});
  const [customSource, setCustomSource] = useState<Record<string, { url?: string; path?: string }>>({});
  const [values, setValues] = useState<Record<string, unknown>[]>([]);
  const [fetching, setFetching] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageIsSuccess, setMessageIsSuccess] = useState(false);
  const showMessage = (text: string, isSuccess: boolean) => {
    setMessage(text);
    setMessageIsSuccess(isSuccess);
  };

  // Common effective dates for all indices (used for fetch & populate)
  const [effectiveStart, setEffectiveStart] = useState("2023-01");
  const [effectiveEnd, setEffectiveEnd] = useState("2024-12");

  // Non-deterministic: process text → numeric
  const [processText, setProcessText] = useState<Record<string, string>>({});
  const [processYearMonth, setProcessYearMonth] = useState<Record<string, string>>({});
  const [processResult, setProcessResult] = useState<Record<string, { value?: number; error?: string }>>({});
  const [processLoading, setProcessLoading] = useState<Record<string, boolean>>({});
  const [processApplyLoading, setProcessApplyLoading] = useState<Record<string, boolean>>({});
  // Batch import (CSV paste or file) for month-by-month volumes
  const [batchCsvPaste, setBatchCsvPaste] = useState<Record<string, string>>({});
  const [batchLoading, setBatchLoading] = useState<Record<string, boolean>>({});
  const [batchFileInputKey, setBatchFileInputKey] = useState<Record<string, number>>({});
  // Local doc repo (US–China): path + month folders; crawl & generate from repo
  const [docRepo, setDocRepo] = useState<{ path: string; month_folders: string[] } | null>(null);
  const [docRepoCrawlLoading, setDocRepoCrawlLoading] = useState(false);
  const [docRepoGenerateLoading, setDocRepoGenerateLoading] = useState(false);
  // Crawl condition-based halt (optional)
  const [crawlMaxMinutes, setCrawlMaxMinutes] = useState<string>("");
  const [crawlMaxHours, setCrawlMaxHours] = useState<string>("");
  const [crawlMaxArticlesPerMonth, setCrawlMaxArticlesPerMonth] = useState<string>("");
  const [crawlSnapshotOnly, setCrawlSnapshotOnly] = useState(true);
  // Collapsible config per index
  const [collapsedConfig, setCollapsedConfig] = useState<Record<string, boolean>>({});
  // US import tax (semiconductor, China): generate from USTR/FR
  const [usSemiGenerateLoading, setUsSemiGenerateLoading] = useState(false);
  // Industry sentiment: generate from KPMG+PMI composite (CSV)
  const [industryGenerateLoading, setIndustryGenerateLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/external-drivers/schema?lang=${lang}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data) => {
        setSchema(data);
        if (data?.indices?.length)
          setSelectedIds((prev) => (prev.size === 0 ? new Set(data.indices.map((i: DriverIndex) => i.id)) : prev));
      })
      .catch(() => setSchema(null));
    // Don't load values on mount so the indices table stays hidden until user populates (Fetch or Apply)
  }, [lang]);

  useEffect(() => {
    fetch(`${API_BASE}/api/external-drivers/doc-repo`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data) => setDocRepo({ path: data.path, month_folders: data.month_folders || [] }))
      .catch(() => setDocRepo(null));
  }, []);

  const buildSourceOverrides = (): Record<string, { type: string; url?: string; path?: string; builder?: string }> | undefined => {
    const overrides: Record<string, { type: string; url?: string; path?: string; builder?: string }> = {};
    schema?.indices?.forEach((idx) => {
      if (!selectedIds.has(idx.id)) return;
      const choice = sourceChoice[idx.id];
      const custom = customSource[idx.id];
      const suggested = idx.suggested_sources?.find((s) => s.id === choice);
      if (choice === "custom" && (custom?.url || custom?.path)) {
        overrides[idx.id] = { type: "custom", ...(custom.url && { url: custom.url }), ...(custom.path && { path: custom.path }) };
      } else if (suggested?.type === "builtin" && suggested.builder) {
        overrides[idx.id] = { type: "builtin", builder: suggested.builder };
      } else if (suggested?.type === "url" && suggested.url) {
        overrides[idx.id] = { type: "url", url: suggested.url };
      } else if (suggested?.type === "file" && suggested.path) {
        overrides[idx.id] = { type: "file", path: suggested.path };
      } else if (suggested?.type === "mock") {
        overrides[idx.id] = { type: "mock" };
      }
    });
    return Object.keys(overrides).length ? overrides : undefined;
  };

  const handleFetch = () => {
    const ids = Array.from(selectedIds);
    if (!ids.length) {
      setMessage(t("indices.selectAtLeastOne"));
      return;
    }
    setFetching(true);
    setMessage(null);
    const body: { indices: string[]; source_overrides?: Record<string, { type: string; url?: string; path?: string; builder?: string }>; start?: string; end?: string; lang: string } = { indices: ids, start: effectiveStart, end: effectiveEnd, lang };
    const overrides = buildSourceOverrides();
    if (overrides) body.source_overrides = overrides;
    fetch(`${API_BASE}/api/external-drivers/fetch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        const text = await r.text();
        let data: { message?: string; detail?: string };
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(r.ok ? "Invalid response" : text || r.statusText);
        }
        if (!r.ok) throw new Error(data.detail || data.message || r.statusText);
        return data;
      })
      .then((data) => {
        showMessage(data.message || t("indices.fetchedAndPopulated"), true);
        return fetch(`${API_BASE}/api/external-drivers`);
      })
      .then((r) => r.json())
      .then((data) => setValues(data.rows || []))
      .catch((e) => showMessage(e.message || t("indices.fetchFailed"), false))
      .finally(() => setFetching(false));
  };

  const handleReset = () => {
    setResetting(true);
    setMessage(null);
    fetch(`${API_BASE}/api/external-drivers/reset?lang=${lang}`, { method: "POST" })
      .then(async (r) => {
        const text = await r.text();
        let data: { message?: string; detail?: string };
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(r.ok ? "Invalid response" : text || r.statusText);
        }
        if (!r.ok) throw new Error(data.detail || data.message || r.statusText);
        return data;
      })
      .then(() => {
        setValues([]);
        showMessage(t("indices.indicesTableCleared"), true);
      })
      .catch((e) => showMessage(e.message || t("indices.resetFailed"), false))
      .finally(() => setResetting(false));
  };

  const toggleIndex = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const setSource = (indexId: string, sourceId: string) => {
    setSourceChoice((prev) => ({ ...prev, [indexId]: sourceId }));
  };

  const setCustom = (indexId: string, field: "url" | "path", value: string) => {
    setCustomSource((prev) => ({
      ...prev,
      [indexId]: { ...prev[indexId], [field]: value || undefined },
    }));
  };

  const handleProcessText = (indexId: string) => {
    const text = processText[indexId]?.trim() ?? "";
    if (!text) return;
    setProcessLoading((prev) => ({ ...prev, [indexId]: true }));
    setProcessResult((prev) => ({ ...prev, [indexId]: {} }));
    fetch(`${API_BASE}/api/external-drivers/process-text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index_id: indexId, text, year_month: processYearMonth[indexId] || null }),
    })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || r.statusText);
        return data;
      })
      .then((data) => setProcessResult((prev) => ({ ...prev, [indexId]: { value: data.value } })))
      .catch((e) => setProcessResult((prev) => ({ ...prev, [indexId]: { value: undefined, error: e.message } })))
      .finally(() => setProcessLoading((prev) => ({ ...prev, [indexId]: false })));
  };

  const handleProcessTextAndApply = (indexId: string) => {
    const text = processText[indexId]?.trim() ?? "";
    const ym = processYearMonth[indexId] || "2024-01";
    if (!text) return;
    setProcessApplyLoading((prev) => ({ ...prev, [indexId]: true }));
    fetch(`${API_BASE}/api/external-drivers/process-text-and-apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index_id: indexId, text, year_month: ym }),
    })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || r.statusText);
        return data;
      })
      .then(() => fetch(`${API_BASE}/api/external-drivers`))
      .then((r) => r.json())
      .then((data) => setValues(data.rows || []))
      .catch((e) => setProcessResult((prev) => ({ ...prev, [indexId]: { error: e.message } })))
      .finally(() => setProcessApplyLoading((prev) => ({ ...prev, [indexId]: false })));
  };

  /** Parse pasted CSV (header: year_month, text or raw_text) into items for batch API. */
  const parseBatchCsv = (csv: string): { year_month: string; text: string }[] => {
    const lines = csv.trim().split(/\r?\n/).filter((l) => l.trim());
    if (lines.length < 2) return [];
    const headerParts = lines[0].split(",").map((h) => h.trim().toLowerCase().replace("-", "_"));
    const ymIdx = headerParts.findIndex((h) => h === "year_month");
    const textIdx = headerParts.findIndex((h) => h === "text" || h === "raw_text");
    if (ymIdx < 0 || textIdx < 0) return [];
    const items: { year_month: string; text: string }[] = [];
    for (let i = 1; i < lines.length; i++) {
      const row = lines[i];
      const parts = row.match(/("([^"]*)"|[^,]*)/g) || [];
      const vals = parts.map((p) => (p.startsWith('"') ? p.slice(1, -1).replace(/""/g, '"') : p.trim()));
      const ym = vals[ymIdx]?.trim();
      const text = vals[textIdx]?.trim();
      if (ym && text) items.push({ year_month: ym, text });
    }
    return items;
  };

  const handleProcessTextBatch = (indexId: string) => {
    const csv = batchCsvPaste[indexId]?.trim() ?? "";
    const items = parseBatchCsv(csv);
    if (!items.length) {
      showMessage(t("indices.pasteCsvHeaderHint"), false);
      return;
    }
    setBatchLoading((prev) => ({ ...prev, [indexId]: true }));
    setMessage(null);
    fetch(`${API_BASE}/api/external-drivers/process-text-batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index_id: indexId, items }),
    })
      .then(async (r) => {
        const text = await r.text();
        let data: { applied?: number; detail?: string };
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(r.ok ? "Invalid response" : text || r.statusText);
        }
        if (!r.ok) throw new Error(data.detail || data.message || "Batch failed");
        return data;
      })
      .then((data) => {
        showMessage(t("indices.batchAppliedCount", { n: data.applied ?? 0 }), true);
        return fetch(`${API_BASE}/api/external-drivers`);
      })
      .then((r) => r.json())
      .then((data) => setValues(data.rows || []))
      .catch((e) => showMessage(e.message || t("indices.batchFailed"), false))
      .finally(() => setBatchLoading((prev) => ({ ...prev, [indexId]: false })));
  };

  const handleProcessTextFile = (indexId: string, file: File | null) => {
    if (!file) return;
    setBatchLoading((prev) => ({ ...prev, [indexId]: true }));
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    form.append("index_id", indexId);
    fetch(`${API_BASE}/api/external-drivers/process-text-file`, {
      method: "POST",
      body: form,
    })
      .then(async (r) => {
        const text = await r.text();
        let data: { applied?: number; detail?: string };
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(r.ok ? "Invalid response" : text || r.statusText);
        }
        if (!r.ok) throw new Error(data.detail || data.message || "File upload failed");
        return data;
      })
      .then((data) => {
        showMessage(t("indices.fileAppliedCount", { n: data.applied ?? 0 }), true);
        return fetch(`${API_BASE}/api/external-drivers`);
      })
      .then((r) => r.json())
      .then((data) => setValues(data.rows || []))
      .catch((e) => showMessage(e.message || t("indices.fileUploadFailed"), false))
      .finally(() => {
        setBatchLoading((prev) => ({ ...prev, [indexId]: false }));
        setBatchFileInputKey((prev) => ({ ...prev, [indexId]: (prev[indexId] ?? 0) + 1 }));
      });
  };

  const handleUsSemiGenerate = () => {
    setUsSemiGenerateLoading(true);
    setMessage(null);
    fetch(`${API_BASE}/api/external-drivers/us-semi-tariff-china/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start: effectiveStart, end: effectiveEnd, lang }),
    })
      .then(async (r) => {
        const text = await r.text();
        let data: { message?: string; detail?: string };
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(r.ok ? "Invalid response" : text || r.statusText);
        }
        if (!r.ok) throw new Error(data.detail || data.message || r.statusText);
        return data;
      })
      .then((data) => {
        showMessage(data.message || t("indices.generatedUsSemiTariff"), true);
        return fetch(`${API_BASE}/api/external-drivers`);
      })
      .then((r) => r.json())
      .then((data) => setValues(data.rows || []))
      .catch((e) => showMessage(e.message || t("indices.generateFailed"), false))
      .finally(() => setUsSemiGenerateLoading(false));
  };

  const handleIndustryGenerate = () => {
    setIndustryGenerateLoading(true);
    setMessage(null);
    const body: {
      indices: string[];
      source_overrides: Record<string, { type: string; builder: string }>;
      start?: string;
      end?: string;
      lang: string;
    } = {
      indices: ["industry_sentiment"],
      source_overrides: {
        industry_sentiment: { type: "builtin", builder: "industry_sentiment_composite" },
      },
      start: effectiveStart,
      end: effectiveEnd,
      lang,
    };
    fetch(`${API_BASE}/api/external-drivers/fetch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        const text = await r.text();
        let data: { message?: string; detail?: string };
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(r.ok ? "Invalid response" : text || r.statusText);
        }
        if (!r.ok) throw new Error(data.detail || data.message || r.statusText);
        return data;
      })
      .then((data) => {
        showMessage(data.message || t("indices.generatedIndustrySentiment"), true);
        return fetch(`${API_BASE}/api/external-drivers`);
      })
      .then((r) => r.json())
      .then((data) => setValues(data.rows || []))
      .catch((e) => showMessage(e.message || t("indices.generateFailed"), false))
      .finally(() => setIndustryGenerateLoading(false));
  };

  const handleDocRepoCrawl = () => {
    setDocRepoCrawlLoading(true);
    setMessage(null);
    const body: { start: string; end: string; snapshot_only?: boolean; max_minutes?: number; max_hours?: number; max_articles_per_month?: number; lang: string } = { start: effectiveStart, end: effectiveEnd, snapshot_only: crawlSnapshotOnly, lang };
    const mins = crawlMaxMinutes.trim() ? parseFloat(crawlMaxMinutes) : undefined;
    const hrs = crawlMaxHours.trim() ? parseFloat(crawlMaxHours) : undefined;
    const arts = crawlMaxArticlesPerMonth.trim() ? parseInt(crawlMaxArticlesPerMonth, 10) : undefined;
    if (hrs != null && !Number.isNaN(hrs) && hrs > 0) body.max_hours = hrs;
    else if (mins != null && !Number.isNaN(mins) && mins > 0) body.max_minutes = mins;
    if (arts != null && !Number.isNaN(arts) && arts >= 1) body.max_articles_per_month = arts;
    fetch(`${API_BASE}/api/external-drivers/doc-repo/crawl`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        const text = await r.text();
        let data: { message?: string; detail?: string; months?: number; files_written?: number; cancelled?: boolean; halt_reason?: string; errors?: unknown[] };
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(r.ok ? "Invalid response" : text || r.statusText);
        }
        if (!r.ok) throw new Error(data.detail || data.message || "Crawl failed");
        return data;
      })
      .then((data) => {
        const text = data.message || t("indices.crawledCount", { months: data.months ?? 0, files: data.files_written ?? 0 });
        const success = !(data.files_written === 0 && (data.errors?.length ?? 0) > 0);
        showMessage(text, success);
        return fetch(`${API_BASE}/api/external-drivers/doc-repo`);
      })
      .then((r) => r.json())
      .then((data) => setDocRepo({ path: data.path, month_folders: data.month_folders || [] }))
      .catch((e) => showMessage(e.message || t("indices.crawlFailed"), false))
      .finally(() => setDocRepoCrawlLoading(false));
  };

  const handleDocRepoCrawlCancel = () => {
    fetch(`${API_BASE}/api/external-drivers/doc-repo/crawl/cancel?lang=${lang}`, { method: "POST" }).catch(() => {});
    showMessage(t("indices.stoppingCrawl"), false);
  };

  const handleDocRepoGenerate = () => {
    setDocRepoGenerateLoading(true);
    setMessage(null);
    fetch(`${API_BASE}/api/external-drivers/process-doc-repo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index_id: "trade_policy", start: effectiveStart, end: effectiveEnd, lang }),
    })
      .then(async (r) => {
        const text = await r.text();
        let data: { applied?: number; rows?: number; detail?: string };
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(r.ok ? "Invalid response" : text || r.statusText);
        }
        if (!r.ok) throw new Error(data.detail || data.message || "Generate failed");
        return data;
      })
      .then((data) => {
        showMessage(data.message || t("indices.generatedIndicesForCount", { n: data.applied ?? 0 }), true);
        return fetch(`${API_BASE}/api/external-drivers`);
      })
      .then((r) => r.json())
      .then((data) => setValues(data.rows || []))
      .then(() => fetch(`${API_BASE}/api/external-drivers/doc-repo`))
      .then((r) => r.json())
      .then((data) => setDocRepo({ path: data.path, month_folders: data.month_folders || [] }))
      .catch((e) => showMessage(e.message || t("indices.generateFailed"), false))
      .finally(() => setDocRepoGenerateLoading(false));
  };

  const toggleConfig = (id: string) => {
    setCollapsedConfig((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <main className="w-full min-h-screen flex flex-col p-6">
      <div className="shrink-0 mb-6">
        <h1 className="text-xl font-bold text-slate-100">{t("indices.title")}</h1>
      </div>
      <p className="text-slate-500 text-sm mb-4 max-w-2xl">
        {t("indices.subtitle")}
      </p>
      {/* Common effective dates for all indices */}
      <div className="flex flex-wrap items-end gap-4 mb-6 p-4 rounded-lg border border-slate-600 bg-slate-800/40">
        <span className="text-slate-400 text-sm font-medium">{t("indices.effectiveDates")}</span>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 text-xs">{t("indices.startMonth")}</span>
          <input
            type="month"
            value={effectiveStart}
            onChange={(e) => setEffectiveStart(e.target.value)}
            min="2015-01"
            max="2030-12"
            className="px-2 py-1.5 rounded bg-slate-700 border border-slate-600 text-slate-200 text-sm [color-scheme:dark]"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 text-xs">{t("indices.endMonth")}</span>
          <input
            type="month"
            value={effectiveEnd}
            onChange={(e) => setEffectiveEnd(e.target.value)}
            min="2015-01"
            max="2030-12"
            className="px-2 py-1.5 rounded bg-slate-700 border border-slate-600 text-slate-200 text-sm [color-scheme:dark]"
          />
        </label>
      </div>
      {schema?.indices ? (
        <>
          <div className="space-y-4 mb-6">
            {schema.indices.map((idx) => (
              <div key={idx.id} className="border border-slate-600 rounded-lg p-4 bg-slate-800/40">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <label className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(idx.id)}
                      onChange={() => toggleIndex(idx.id)}
                      className="mt-1 rounded border-slate-500 bg-slate-800 text-slate-200"
                    />
                    <span>
                      <span className="text-slate-200 font-medium">{idx.name}</span>
                      <span className="text-slate-500 text-xs ml-1">({idx.id})</span>
                      {idx.description && (
                        <span className="block text-xs text-slate-500 mt-0.5">{idx.description}</span>
                      )}
                    </span>
                  </label>
                  <button
                    type="button"
                    onClick={() => toggleConfig(idx.id)}
                    className="mt-1 px-2 py-0.5 rounded border border-slate-600 text-slate-300 text-[11px] font-medium hover:bg-slate-700"
                  >
                    {collapsedConfig[idx.id] ? t("indices.showConfig") : t("indices.hideConfig")}
                  </button>
                </div>
                {selectedIds.has(idx.id) &&
                  !collapsedConfig[idx.id] &&
                  idx.suggested_sources &&
                  idx.suggested_sources.length > 0 && (
                  <div className="ml-6 mt-2">
                    <span className="text-slate-400 text-xs block mb-1">{t("indices.source")}</span>
                    <div className="flex flex-wrap gap-2 items-center">
                      {idx.suggested_sources.map((s) => {
                        const isCuratedBuiltin = idx.id === "us_semi_tariff_china" && s.id === "builtin_ustr_fr";
                        const label = isCuratedBuiltin
                          ? t("indices.curatedFrom", { start: effectiveStart, end: effectiveEnd })
                          : s.label;
                        return (
                          <label key={s.id} className="flex items-center gap-1.5 cursor-pointer">
                            <input
                              type="radio"
                              name={`source-${idx.id}`}
                              checked={(sourceChoice[idx.id] ?? (idx.suggested_sources?.[0]?.id || "")) === s.id}
                              onChange={() => setSource(idx.id, s.id)}
                              className="rounded border-slate-500 bg-slate-800 text-slate-200"
                            />
                            <span className="text-slate-300 text-sm">{label}</span>
                          </label>
                        );
                      })}
                      {idx.id === "industry_sentiment" && (
                        <button
                          type="button"
                          onClick={handleIndustryGenerate}
                          disabled={industryGenerateLoading}
                          className="ml-2 px-2 py-1 rounded bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-500 disabled:opacity-50"
                        >
                          {industryGenerateLoading ? t("indices.generating") : t("indices.generateFromKpmgPmi")}
                        </button>
                      )}
                    </div>
                    {(sourceChoice[idx.id] ?? idx.suggested_sources?.[0]?.id) === "custom" && (
                      <div className="mt-2 flex flex-wrap gap-3">
                        <input
                          type="text"
                          placeholder={t("indices.csvUrlPlaceholder")}
                          value={customSource[idx.id]?.url ?? ""}
                          onChange={(e) => setCustom(idx.id, "url", e.target.value)}
                          className="px-2 py-1 rounded bg-slate-700 border border-slate-600 text-slate-200 text-sm min-w-[200px] placeholder-slate-500"
                        />
                        <input
                          type="text"
                          placeholder={t("indices.filePathPlaceholder")}
                          value={customSource[idx.id]?.path ?? ""}
                          onChange={(e) => setCustom(idx.id, "path", e.target.value)}
                          className="px-2 py-1 rounded bg-slate-700 border border-slate-600 text-slate-200 text-sm min-w-[200px] placeholder-slate-500"
                        />
                      </div>
                    )}
                    {idx.id === "us_semi_tariff_china" && (
                      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-600/50 pt-3">
                        <span className="text-slate-400 text-xs">
                          {t("indices.generateFromUstrFr")}
                        </span>
                        <button
                          type="button"
                          onClick={handleUsSemiGenerate}
                          disabled={usSemiGenerateLoading}
                          className="px-2 py-1 rounded bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-500 disabled:opacity-50"
                        >
                          {usSemiGenerateLoading ? t("indices.generating") : t("indices.generateAndApply")}
                        </button>
                      </div>
                    )}
                    {/* Non-deterministic: starter sources + process text → numeric */}
                    {idx.deterministic === false && (
                      <div className="ml-6 mt-4 space-y-3 border-t border-slate-600/50 pt-3">
                        {/* Local doc repo (US–China): MM_YYYY folders → crawl & generate indices */}
                        {idx.id === "trade_policy" && (
                          <div className="mb-4 pb-4 border-b border-slate-600/50">
                            <span className="text-slate-400 text-xs block mb-1">{t("indices.localDocRepo")}</span>
                            <p className="text-slate-500 text-xs mb-2">
                              {t("indices.localDocRepoDesc")}
                            </p>
                            <label className="flex items-center gap-2 mb-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crawlSnapshotOnly}
                                onChange={(e) => setCrawlSnapshotOnly(e.target.checked)}
                                className="rounded border-slate-500 bg-slate-800 text-slate-200"
                              />
                              <span className="text-slate-400 text-xs">{t("indices.saveOnlyCurrentMonth")}</span>
                            </label>
                            {docRepo && (
                              <p className="text-slate-400 text-xs mb-2">
                                {t("indices.repoPath")} <code className="bg-slate-700 px-1 rounded break-all">{docRepo.path}</code>
                                {docRepo.month_folders.length > 0 && (
                                  <span className="ml-2">{t("indices.monthsWithDocs", { n: docRepo.month_folders.length })}</span>
                                )}
                              </p>
                            )}
                            <div className="flex flex-wrap items-center gap-3 mb-2">
                              <span className="text-slate-500 text-xs">{t("indices.conditionHalt")}</span>
                              <label className="flex items-center gap-1">
                                <span className="text-slate-400 text-xs">{t("indices.stopAfter")}</span>
                                <input
                                  type="number"
                                  min={0.1}
                                  step={0.5}
                                  placeholder="min"
                                  value={crawlMaxMinutes}
                                  onChange={(e) => setCrawlMaxMinutes(e.target.value)}
                                  className="w-16 px-1.5 py-0.5 rounded bg-slate-700 border border-slate-600 text-slate-200 text-xs [color-scheme:dark]"
                                />
                                <span className="text-slate-500 text-xs">{t("indices.minutes")}</span>
                              </label>
                              <label className="flex items-center gap-1">
                                <input
                                  type="number"
                                  min={0.1}
                                  step={0.5}
                                  placeholder="hrs"
                                  value={crawlMaxHours}
                                  onChange={(e) => setCrawlMaxHours(e.target.value)}
                                  className="w-16 px-1.5 py-0.5 rounded bg-slate-700 border border-slate-600 text-slate-200 text-xs [color-scheme:dark]"
                                />
                                <span className="text-slate-500 text-xs">{t("indices.hours")}</span>
                              </label>
                              <label className="flex items-center gap-1">
                                <span className="text-slate-400 text-xs">{t("indices.maxArticlesPerMonth")}</span>
                                <input
                                  type="number"
                                  min={1}
                                  max={20}
                                  placeholder="all"
                                  value={crawlMaxArticlesPerMonth}
                                  onChange={(e) => setCrawlMaxArticlesPerMonth(e.target.value)}
                                  className="w-14 px-1.5 py-0.5 rounded bg-slate-700 border border-slate-600 text-slate-200 text-xs [color-scheme:dark]"
                                />
                              </label>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <button
                                type="button"
                                onClick={handleDocRepoCrawl}
                                disabled={docRepoCrawlLoading}
                                className="px-2 py-1 rounded bg-slate-600 text-slate-200 text-sm hover:bg-slate-500 disabled:opacity-50"
                              >
                                {docRepoCrawlLoading ? t("indices.crawling") : t("indices.crawlAndSave")}
                              </button>
                              {docRepoCrawlLoading && (
                                <button
                                  type="button"
                                  onClick={handleDocRepoCrawlCancel}
                                  className="px-2 py-1 rounded bg-amber-600 text-white text-sm hover:bg-amber-500"
                                >
                                  {t("indices.stopCrawl")}
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={handleDocRepoGenerate}
                                disabled={docRepoGenerateLoading}
                                className="px-2 py-1 rounded bg-emerald-600 text-white text-sm hover:bg-emerald-500 disabled:opacity-50"
                              >
                                {docRepoGenerateLoading ? t("indices.generating") : t("indices.generateIndicesFromRepo")}
                              </button>
                              <span className="text-slate-500 text-xs">{t("indices.usesEffectiveDates")}</span>
                            </div>
                          </div>
                        )}
                        {idx.starter_sources && idx.starter_sources.length > 0 && (
                          <div>
                            <span className="text-slate-400 text-xs block mb-1">{t("indices.starterSources")}</span>
                            <ul className="flex flex-wrap gap-2">
                              {idx.starter_sources.map((s) => (
                                <li key={s.id}>
                                  {s.url ? (
                                    <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:text-sky-300 text-sm">
                                      {s.label}
                                    </a>
                                  ) : (
                                    <span className="text-slate-400 text-sm">{s.label}</span>
                                  )}
                                  {s.description && <span className="text-slate-500 text-xs ml-1">— {s.description}</span>}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        <div>
                          <span className="text-slate-400 text-xs block mb-1">{t("indices.yourOwnConvert")}</span>
                          <p className="text-slate-500 text-xs mb-2">
                            {t("indices.convertSteps")}
                          </p>
                          <textarea
                            placeholder={t("indices.pasteTextPlaceholder")}
                            value={processText[idx.id] ?? ""}
                            onChange={(e) => setProcessText((prev) => ({ ...prev, [idx.id]: e.target.value }))}
                            rows={3}
                            className="w-full px-2 py-1.5 rounded bg-slate-700 border border-slate-600 text-slate-200 text-sm placeholder-slate-500 resize-y"
                          />
                          <div className="flex flex-wrap items-center gap-2 mt-2">
                            <input
                              type="month"
                              value={processYearMonth[idx.id] ?? "2024-01"}
                              onChange={(e) => setProcessYearMonth((prev) => ({ ...prev, [idx.id]: e.target.value }))}
                              className="px-2 py-1 rounded bg-slate-700 border border-slate-600 text-slate-200 text-sm [color-scheme:dark]"
                            />
                            <button
                              type="button"
                              onClick={() => (processText[idx.id]?.trim() ? handleProcessText(idx.id) : setProcessResult((prev) => ({ ...prev, [idx.id]: { error: t("indices.pasteTextFirst") } })))}
                              disabled={processLoading[idx.id]}
                              className="px-2 py-1 rounded bg-slate-600 text-slate-200 text-sm hover:bg-slate-500 disabled:opacity-50"
                            >
                              {processLoading[idx.id] ? t("indices.converting") : t("indices.convertToNumber")}
                            </button>
                            {processResult[idx.id]?.value != null && (
                              <span className="text-slate-300 text-sm">{t("indices.score", { value: processResult[idx.id].value as number })}</span>
                            )}
                            {processResult[idx.id]?.error && (
                              <span className="text-amber-400 text-xs">{processResult[idx.id].error}</span>
                            )}
                            <button
                              type="button"
                              onClick={() => (processText[idx.id]?.trim() ? handleProcessTextAndApply(idx.id) : setProcessResult((prev) => ({ ...prev, [idx.id]: { error: t("indices.pasteAndConvertFirst") } })))}
                              disabled={processApplyLoading[idx.id]}
                              className="px-2 py-1 rounded bg-emerald-600 text-white text-sm hover:bg-emerald-500 disabled:opacity-50"
                            >
                              {processApplyLoading[idx.id] ? t("indices.applying") : t("indices.applyToDrivers")}
                            </button>
                          </div>
                          <div className="mt-4 pt-3 border-t border-slate-600/50">
                            <span className="text-slate-400 text-xs block mb-1">{t("indices.batchImportTitle")}</span>
                            <p className="text-slate-500 text-xs mb-2">
                              {t("indices.batchImportDesc")}
                            </p>
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              <input
                                type="file"
                                accept=".csv"
                                key={batchFileInputKey[idx.id] ?? 0}
                                onChange={(e) => handleProcessTextFile(idx.id, e.target.files?.[0] ?? null)}
                                disabled={batchLoading[idx.id]}
                                className="text-slate-400 text-xs file:mr-2 file:py-1 file:px-2 file:rounded file:bg-slate-600 file:text-slate-200 file:border-0 file:text-xs"
                              />
                              <span className="text-slate-500 text-xs">{t("indices.orPasteCsv")}</span>
                            </div>
                            <textarea
                              placeholder={t("indices.batchCsvPlaceholder")}
                              value={batchCsvPaste[idx.id] ?? ""}
                              onChange={(e) => setBatchCsvPaste((prev) => ({ ...prev, [idx.id]: e.target.value }))}
                              rows={4}
                              className="w-full px-2 py-1.5 rounded bg-slate-700 border border-slate-600 text-slate-200 text-sm placeholder-slate-500 resize-y mb-2"
                            />
                            <button
                              type="button"
                              onClick={() => handleProcessTextBatch(idx.id)}
                              disabled={batchLoading[idx.id]}
                              className="px-2 py-1 rounded bg-emerald-600 text-white text-sm hover:bg-emerald-500 disabled:opacity-50"
                            >
                              {batchLoading[idx.id] ? t("indices.processing") : t("indices.processBatch")}
                            </button>
                          </div>
                          {idx.text_to_numeric_scale?.description && (
                            <p className="text-slate-500 text-xs mt-1">{idx.text_to_numeric_scale.description}</p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 mb-6">
            <button
              type="button"
              onClick={handleFetch}
              disabled={fetching || selectedIds.size === 0}
              className="px-3 py-1.5 rounded bg-slate-600 text-slate-200 text-sm font-medium hover:bg-slate-500 disabled:opacity-50"
            >
              {fetching ? t("indices.fetching") : t("indices.fetchAndPopulate")}
            </button>
            <button
              type="button"
              onClick={handleReset}
              disabled={resetting || values.length === 0}
              className="px-3 py-1.5 rounded bg-slate-600 text-slate-200 text-sm font-medium hover:bg-slate-500 disabled:opacity-50"
            >
              {resetting ? t("indices.resetting") : t("indices.reset")}
            </button>
            {message && (
              <span className={`text-xs ${messageIsSuccess ? "text-green-400" : "text-amber-400"}`}>{message}</span>
            )}
          </div>
          {values.length === 0 && (
            <p className="text-slate-500 text-sm mb-4">
              {t("indices.noIndicesDataYet")}
            </p>
          )}
          {values.length > 0 && (
            <div className="overflow-x-auto max-h-[50vh] overflow-y-auto border border-slate-600 rounded text-xs">
              <table className="w-full">
                <thead className="bg-slate-700/80 sticky top-0">
                  <tr>
                    {Object.keys(values[0] as object).map((k) => (
                      <th key={k} className="text-left px-2 py-1 text-slate-300">
                        {k}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(values as Record<string, unknown>[]).map((row, i) => (
                    <tr key={i} className="border-t border-slate-600/50">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="px-2 py-1 text-slate-200">
                          {String(v ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : (
        <div className="text-slate-500 text-sm">{t("indices.loadingSchema")}</div>
      )}
    </main>
  );
}
