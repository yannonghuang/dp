"""
Backend i18n: translates registry schema text and dynamic response messages.
Keep en/zh in lockstep — every key in one must exist in the other.
"""

from __future__ import annotations

import copy

SUPPORTED_LANGS = {"en", "zh"}
DEFAULT_LANG = "en"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "indices_cleared": "Indices table cleared.",
        "no_drivers_file": "No external drivers file found; run populate or POST values.",
        "fetched_and_populated": "Fetched from sources and populated external_drivers.csv",
        "curated_from_ustr_fr": "Curated from USTR/FR effective dates",
        "us_semi_applied": "US import tax (semiconductor, China) applied to external_drivers.csv",
        "generated_from_doc_repo": "Generated indices for {applied} month(s) from doc repo.",
        "cancel_requested": "Cancel requested; crawl will stop after the current month.",
        "crawl_snapshot_saved": "Saved current snapshot to {ym} ({total} file(s)). Run monthly to build a time series.",
        "crawled_count": "Crawled {months} month(s), wrote {total} file(s).",
        "crawl_stopped_time_limit": "Crawl stopped after time limit ({months} month(s), {total} file(s)).",
        "crawl_cancelled": "Crawl cancelled after {months} month(s); wrote {total} file(s).",
        "no_files_written_errors": " No files written. Errors: {err_detail}",
    },
    "zh": {
        "indices_cleared": "指标表已清空。",
        "no_drivers_file": "未找到外部驱动因素文件；请先运行填充或提交数值。",
        "fetched_and_populated": "已从数据源获取并填充 external_drivers.csv",
        "curated_from_ustr_fr": "根据 USTR/FR 生效日期整理",
        "us_semi_applied": "已将美国进口关税（半导体，中国）应用到 external_drivers.csv",
        "generated_from_doc_repo": "已根据文档库为 {applied} 个月生成指标。",
        "cancel_requested": "已请求取消；抓取将在当前月份完成后停止。",
        "crawl_snapshot_saved": "已将当前快照保存到 {ym}（{total} 个文件）。请按月运行以构建时间序列。",
        "crawled_count": "已抓取 {months} 个月，写入 {total} 个文件。",
        "crawl_stopped_time_limit": "已因达到时间限制而停止抓取（{months} 个月，{total} 个文件）。",
        "crawl_cancelled": "已取消抓取，共处理 {months} 个月；写入 {total} 个文件。",
        "no_files_written_errors": " 未写入任何文件。错误：{err_detail}",
    },
}


def normalize_lang(lang: str | None) -> str:
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def t(key: str, lang: str | None = None, **kwargs) -> str:
    lang = normalize_lang(lang)
    template = MESSAGES.get(lang, {}).get(key) or MESSAGES[DEFAULT_LANG].get(key, key)
    return template.format(**kwargs) if kwargs else template


# Registry text (index names/descriptions, suggested/starter source labels) keyed by index id.
# English lives in the registry itself (external_drivers_subsystem.py); this only overlays zh.
REGISTRY_I18N: dict[str, dict] = {
    "zh": {
        "industry_sentiment": {
            "name": "行业景气度",
            "description": "全行业景气度或信心指数（如 0–100）。",
            "suggested_sources": {
                "mock": "占位符（示例数值）",
                "custom": "自定义（URL 或文件路径）",
            },
        },
        "trade_policy": {
            "name": "中美关系",
            "description": "更广泛的中美关系；定性指标（政策立场、紧张程度）。使用入门信息源或您自己的文本，将文本转换为数值分数。",
            "suggested_sources": {
                "mock": "占位符（示例数值）",
                "custom": "自定义（URL 或文件路径）",
            },
            "starter_sources": {
                "csis": {"label": "CSIS（中国）", "description": "关于中国的战略与经济分析；数据驱动的研究"},
                "cfr": {"label": "CFR（中国）", "description": "关于中国的政策分析、背景介绍与文章"},
                "pew": {"label": "皮尤研究中心（中国全球形象）", "description": "关于全球对中国看法的民意调查"},
            },
            "text_to_numeric_scale_description": "1 = 最为合作，5 = 最为对抗",
        },
        "us_semi_tariff_china": {
            "name": "美国进口关税（半导体，中国）",
            "description": "美国对来自中国的半导体产品（HTS 8541、8542）征收的从价关税税率（%）（第301条）。确定性指标：使用内置数据或 CSV。",
            "suggested_sources": {
                "builtin_ustr_fr": "根据 USTR/FR 生效日期整理（内置）",
            },
        },
    },
}


def translate_registry(registry: list[dict], lang: str | None) -> list[dict]:
    lang = normalize_lang(lang)
    if lang == DEFAULT_LANG:
        return registry
    overlay = REGISTRY_I18N.get(lang, {})
    out = copy.deepcopy(registry)
    for idx in out:
        idx_overlay = overlay.get(idx.get("id"))
        if not idx_overlay:
            continue
        if "name" in idx_overlay:
            idx["name"] = idx_overlay["name"]
        if "description" in idx_overlay:
            idx["description"] = idx_overlay["description"]
        src_labels = idx_overlay.get("suggested_sources", {})
        for s in idx.get("suggested_sources") or []:
            if s.get("id") in src_labels:
                s["label"] = src_labels[s["id"]]
        starter_overlay = idx_overlay.get("starter_sources", {})
        for s in idx.get("starter_sources") or []:
            s_overlay = starter_overlay.get(s.get("id"))
            if s_overlay:
                if "label" in s_overlay:
                    s["label"] = s_overlay["label"]
                if "description" in s_overlay:
                    s["description"] = s_overlay["description"]
        if "text_to_numeric_scale_description" in idx_overlay and idx.get("text_to_numeric_scale"):
            idx["text_to_numeric_scale"]["description"] = idx_overlay["text_to_numeric_scale_description"]
    return out
