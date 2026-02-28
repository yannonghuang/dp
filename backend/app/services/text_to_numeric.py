"""
Turn raw text into a numeric score for non-deterministic indices (e.g. US–China relationship).
Uses LLM when OPENAI_API_KEY is set; otherwise returns a stub value for development.
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
    Returns (value, year_month). Uses LLM if OPENAI_API_KEY is set; else stub.
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

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or not text or not text.strip():
        return _stub_value(index_id), year_month

    try:
        import openai
    except ImportError:
        return _stub_value(index_id), year_month

    try:
        client = openai.OpenAI(api_key=api_key)
        prompt = (
            f"You are scoring the US–China relationship from a short text. "
            f"Output a single number between {scale_min} and {scale_max}. "
            f"Scale: {scale_desc}. "
            f"Reply with only the number, no explanation.\n\nText:\n{text.strip()[:4000]}"
        )
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
        )
        content = (resp.choices[0].message.content or "").strip()
        value = _parse_scale_from_llm(content, scale_min, scale_max)
        if value is not None:
            return value, year_month
    except Exception:
        pass
    return _stub_value(index_id), year_month
