"""
Turn raw text into a numeric score for non-deterministic indices (e.g. US–China relationship).
Uses Qwen (DashScope) when DASHSCOPE_API_KEY is set, falling back to OpenAI when
OPENAI_API_KEY is set instead; otherwise returns a stub value for development.
"""

from __future__ import annotations

import os
import re
from app.services.external_drivers_subsystem import get_registry


def _stub_value(index_id: str) -> float:
    """Return a default numeric when no LLM is configured."""
    reg = next((r for r in get_registry() if r["id"] == index_id), None)
    if reg is not None:
        return float(reg.get("default_value", 1.0))
    return 1.0


def _parse_scale_from_llm(text: str, scale_min: float, scale_max: float) -> float | None:
    """Extract a single number in [scale_min, scale_max] from LLM output."""
    # Look for a number that might be in the scale (integer or decimal)
    numbers = re.findall(r"-?\d+\.?\d*", text)
    for n in numbers:
        try:
            v = float(n)
            if scale_min <= v <= scale_max:
                return v
        except ValueError:
            continue
    return None


def text_to_numeric(
    index_id: str,
    text: str,
    year_month: str | None = None,
) -> tuple[float, str | None]:
    """
    Convert raw text to a numeric score for the given non-deterministic index.
    Returns (value, year_month). Uses Qwen (DashScope) if DASHSCOPE_API_KEY is
    set, else OpenAI if OPENAI_API_KEY is set; else stub.
    """
    reg = next((r for r in get_registry() if r["id"] == index_id), None)
    if reg is None:
        return _stub_value(index_id), year_month
    if reg.get("deterministic", True):
        return float(reg.get("default_value", 1.0)), year_month

    scale = reg.get("text_to_numeric_scale") or {}
    scale_min = float(scale.get("min", 1))
    scale_max = float(scale.get("max", 5))
    scale_desc = scale.get("description", "1 = cooperative, 5 = confrontational")

    dashscope_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    extra_body: dict | None = None
    if dashscope_key:
        api_key = dashscope_key
        base_url = os.environ.get("DASHSCOPE_BASE_URL", "").strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        model = os.environ.get("ASSESSMENT_MODEL", "").strip() or "qwen3.7-plus"
        # Qwen3 models default to extended chain-of-thought reasoning, which is
        # unnecessary for a single-number score and adds 10x+ latency per call.
        extra_body = {"enable_thinking": False}
    elif openai_key:
        api_key = openai_key
        base_url = None
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    else:
        return _stub_value(index_id), year_month

    if not text or not text.strip():
        return _stub_value(index_id), year_month

    try:
        import openai
    except ImportError:
        return _stub_value(index_id), year_month

    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        prompt = (
            f"You are scoring the US–China relationship from a short text. "
            f"Output a single number between {scale_min} and {scale_max}. "
            f"Scale: {scale_desc}. "
            f"Reply with only the number, no explanation.\n\nText:\n{text.strip()[:4000]}"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            extra_body=extra_body,
        )
        content = (resp.choices[0].message.content or "").strip()
        value = _parse_scale_from_llm(content, scale_min, scale_max)
        if value is not None:
            return value, year_month
    except Exception:
        pass
    return _stub_value(index_id), year_month
