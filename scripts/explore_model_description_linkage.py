#!/usr/bin/env python3
"""
Explore linkage between dp.csv (Model) and shipment.csv (Description).

- Rule-based: exact, model_contains_prefix, prefix_contains_model, token overlap.
- Similarity-based: best Model by string similarity (rapidfuzz token_set_ratio) above threshold.
- Compares both; writes output/linkage_report.csv with rule match, similarity match, and score.

Run from repo root: python scripts/explore_model_description_linkage.py

Similarity: Uses rapidfuzz.token_set_ratio when available (pip install rapidfuzz), else
difflib.SequenceMatcher. rapidfuzz typically yields more matches and fixes rule mistakes
(e.g. "100G AOC Gen3" -> AOC Gen3.0 not BiDi Gen3.0). Install rapidfuzz for best results.
"""

from pathlib import Path
import re
import pandas as pd

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

import difflib

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
MONTH_COLS = [f"2023-{m:02d}" for m in range(1, 13)]

# Similarity: accept best match if score >= this (0-100). token_set_ratio is lenient on word order.
SIMILARITY_THRESHOLD = 72
# Use similarity result as "best" when score >= this (high confidence).
SIMILARITY_HIGH_CONFIDENCE = 85


def normalize_desc_prefix(desc: str) -> str:
    """First segment before comma; normalize abbreviations and spacing for matching to Model."""
    if pd.isna(desc) or not str(desc).strip():
        return ""
    s = str(desc).strip()
    # Take before first comma (main product part)
    s = s.split(",")[0].strip()
    # Insert space after speed if missing: 100GQSFP28 -> 100G QSFP28, etc.
    s = re.sub(r"^(\d+G)(QSFP|OSFP|SFP)", r"\1 \2", s, flags=re.IGNORECASE)
    # Common abbreviations in Description that appear in Model as longer form
    s = re.sub(r"\bQ28\b", "QSFP28", s, flags=re.IGNORECASE)
    s = re.sub(r"\bG3\b", "Gen3", s, flags=re.IGNORECASE)
    s = re.sub(r"\bG2\b", "Gen2", s, flags=re.IGNORECASE)
    s = re.sub(r"\bG1\b", "Gen1", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    return s


def load_plan_models(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8", dtype=str, nrows=0)
    if "Model" not in df.columns:
        return pd.DataFrame(columns=["Model", "Series"])
    df = pd.read_csv(path, encoding="utf-8", dtype=str, usecols=["Plant", "Series", "Model", "Version"])
    df = df.drop_duplicates(subset=["Plant", "Series", "Model", "Version"])
    return df


def load_shipment_descriptions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]
    if "Description" not in df.columns or "PRODUCT_ID" not in df.columns:
        return pd.DataFrame(columns=["PRODUCT_ID", "Description", "desc_prefix"])
    df = df[["LOCATION_ID", "PRODUCT_ID", "Description"]].drop_duplicates()
    df["desc_prefix"] = df["Description"].map(normalize_desc_prefix)
    return df


def match_prefix_to_models(prefix: str, models: list[str]) -> list[tuple[str, str]]:
    """
    Return list of (model, match_type): 'exact' | 'model_contains_prefix' | 'prefix_contains_model' | 'fuzzy'.
    """
    if not prefix or not models:
        return []
    prefix_lower = prefix.lower()
    out = []
    # Exact (after normalizing case)
    for m in models:
        if m and m.strip().lower() == prefix_lower:
            out.append((m, "exact"))
    if out:
        return out
    # Model contains prefix (e.g. Model "100G QSFP28 SR4 Gen5.0" contains prefix "100G QSFP28 SR4")
    for m in models:
        if not m:
            continue
        if prefix_lower in m.strip().lower():
            out.append((m, "model_contains_prefix"))
    if out:
        return out
    # Prefix contains a significant part of Model (e.g. prefix "100G QSFP28 AOC V2M" vs Model "100G QSFP28 AOC Gen4.0")
    # Use "prefix starts with first N words of model" or "model stem in prefix"
    for m in models:
        if not m:
            continue
        ml = m.strip().lower()
        # Model stem: e.g. "100g qsfp28 aoc" from "100G QSFP28 AOC Gen4.0"
        parts = ml.replace(".", " ").split()
        stem = " ".join(parts[:4]) if len(parts) >= 4 else ml  # first 4 tokens as stem
        if stem in prefix_lower or (len(stem) > 8 and stem[:15] in prefix_lower):
            out.append((m, "prefix_contains_model"))
    if out:
        return out
    # Fuzzy: shared token set overlap (e.g. both have "100G", "QSFP28", "SR4")
    prefix_tokens = set(re.findall(r"[a-z0-9]+", prefix_lower))
    prefix_tokens.discard("v")
    prefix_tokens.discard("gen")
    fuzzy_out = []
    for m in models:
        if not m:
            continue
        ml = m.strip().lower()
        model_tokens = set(re.findall(r"[a-z0-9]+", ml))
        overlap = len(prefix_tokens & model_tokens) / max(len(prefix_tokens), 1)
        if overlap >= 0.5:
            fuzzy_out.append((m, "fuzzy"))
    return fuzzy_out


def _similarity_rapidfuzz(prefix: str, models: list[str], threshold: float) -> tuple[str | None, float]:
    """Best match using rapidfuzz token_set_ratio (0-100)."""
    prefix = prefix.strip()
    best_model = None
    best_score = 0.0
    for m in models:
        if not m or not str(m).strip():
            continue
        score = fuzz.token_set_ratio(prefix, m)
        if score > best_score:
            best_score = score
            best_model = m
    if best_score >= threshold:
        return (best_model, round(best_score, 1))
    return (None, round(best_score, 1))


def _similarity_difflib(prefix: str, models: list[str], threshold: float) -> tuple[str | None, float]:
    """Fallback: best match using difflib SequenceMatcher ratio (0-100)."""
    prefix = prefix.strip().lower()
    best_model = None
    best_score = 0.0
    for m in models:
        if not m or not str(m).strip():
            continue
        score = difflib.SequenceMatcher(None, prefix, m.strip().lower()).ratio() * 100
        if score > best_score:
            best_score = score
            best_model = m
    if best_score >= threshold:
        return (best_model, round(best_score, 1))
    return (None, round(best_score, 1))


def similarity_best_match(prefix: str, models: list[str], threshold: float = SIMILARITY_THRESHOLD) -> tuple[str | None, float]:
    """
    Return (best_model, score) for prefix vs models. Uses rapidfuzz token_set_ratio if
    available, else difflib ratio. Score 0-100; returns (None, best_score) if below threshold.
    """
    if not prefix or not models:
        return (None, 0.0)
    if HAS_RAPIDFUZZ:
        return _similarity_rapidfuzz(prefix, models, threshold)
    return _similarity_difflib(prefix, models, threshold)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plan_path = DATA_DIR / "dp.csv"
    ship_path = DATA_DIR / "shipment.csv"
    if not plan_path.exists() or not ship_path.exists():
        print("Missing data/dp.csv or data/shipment.csv")
        return

    plan = load_plan_models(plan_path)
    ship = load_shipment_descriptions(ship_path)
    models = plan["Model"].dropna().unique().tolist()
    models = [m for m in models if str(m).strip()]

    # Unique (desc_prefix, PRODUCT_ID, LOCATION_ID) with one representative Description
    ship_unique = (
        ship.groupby(["desc_prefix", "PRODUCT_ID", "LOCATION_ID"], as_index=False)["Description"]
        .first()
    )
    ship_unique = ship_unique[ship_unique["desc_prefix"].str.len() > 0]

    rows = []
    for _, r in ship_unique.iterrows():
        prefix = r["desc_prefix"]
        matches = match_prefix_to_models(prefix, models)
        rule_model = None
        rule_type = "no_match"
        if matches:
            order = {"exact": 0, "model_contains_prefix": 1, "prefix_contains_model": 2, "fuzzy": 3}
            matches.sort(key=lambda x: order.get(x[1], 99))
            rule_model, rule_type = matches[0]
        sim_model, sim_score = similarity_best_match(prefix, models)
        # Combined: prefer similarity when high confidence, else rule
        use_sim = sim_model is not None and (isinstance(sim_score, (int, float)) and sim_score >= SIMILARITY_HIGH_CONFIDENCE)
        best_model = sim_model if use_sim else rule_model
        rows.append({
            "LOCATION_ID": r["LOCATION_ID"],
            "PRODUCT_ID": r["PRODUCT_ID"],
            "Description": r["Description"][:80],
            "desc_prefix": prefix,
            "matched_Model": rule_model,
            "match_type": rule_type,
            "matched_Model_similarity": sim_model,
            "similarity_score": sim_score,
            "matched_Model_best": best_model,
        })

    report = pd.DataFrame(rows)
    out_path = OUT_DIR / "linkage_report.csv"
    report.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")

    n_total = len(report)
    n_rule = report["matched_Model"].notna().sum()
    n_sim = report["matched_Model_similarity"].notna().sum()
    rule_only = (report["matched_Model"].notna() & report["matched_Model_similarity"].isna()).sum()
    sim_only = (report["matched_Model"].isna() & report["matched_Model_similarity"].notna()).sum()
    both_same = (
        (report["matched_Model"] == report["matched_Model_similarity"]) &
        report["matched_Model"].notna()
    ).sum()
    both_diff = (
        report["matched_Model"].notna() & report["matched_Model_similarity"].notna() &
        (report["matched_Model"] != report["matched_Model_similarity"])
    ).sum()

    n_best = report["matched_Model_best"].notna().sum()
    engine = "rapidfuzz (token_set_ratio)" if HAS_RAPIDFUZZ else "difflib (ratio)"
    print(f"\nLinkage summary (unique Description prefixes): n = {n_total}")
    print(f"  Rule-based:       matched {n_rule} ({100 * n_rule / n_total:.1f}%)")
    print(f"  Similarity ({engine}): matched {n_sim} ({100 * n_sim / n_total:.1f}%)  (threshold >= {SIMILARITY_THRESHOLD})")
    print(f"  Best (sim if >={SIMILARITY_HIGH_CONFIDENCE} else rule): matched {n_best} ({100 * n_best / n_total:.1f}%)")
    print(f"  Rule only:        {rule_only}  (rule matched, similarity below threshold)")
    print(f"  Similarity only:  {sim_only}  (similarity matched, rule had no_match)")
    print(f"  Both agree:       {both_same}")
    print(f"  Both disagree:    {both_diff}")
    print(f"\nBy match_type (rule):")
    print(report["match_type"].value_counts().to_string())

    if sim_only > 0:
        print("\n--- Similarity-only wins (rule had no_match) ---")
        wins = report[report["matched_Model"].isna() & report["matched_Model_similarity"].notna()]
        for _, r in wins.head(15).iterrows():
            print(f"  prefix:  '{r['desc_prefix'][:50]}'")
            print(f"  -> sim:  {r['matched_Model_similarity'][:55]}  (score {r['similarity_score']})")
        if len(wins) > 15:
            print(f"  ... and {len(wins) - 15} more")

    if both_diff > 0:
        print("\n--- Rule vs similarity disagree (same prefix, different Model) ---")
        diff = report[report["matched_Model"].notna() & report["matched_Model_similarity"].notna() & (report["matched_Model"] != report["matched_Model_similarity"])]
        for _, r in diff.head(8).iterrows():
            sc = r["similarity_score"]
            sc_str = f"{sc:.0f}" if pd.notna(sc) and isinstance(sc, (int, float)) else str(sc)
            print(f"  prefix: '{r['desc_prefix'][:45]}'")
            print(f"    rule -> {str(r['matched_Model'])[:50]}")
            print(f"    sim  -> {str(r['matched_Model_similarity'])[:50]} (score {sc_str})")

    print("\nSample rule no_match:")
    sample_none = report[report["match_type"] == "no_match"].head(6)
    for _, r in sample_none.iterrows():
        sim_info = ""
        if pd.notna(r.get("matched_Model_similarity")):
            sim_info = f"  sim-> {str(r['matched_Model_similarity'])[:40]} ({r['similarity_score']})"
        print(f"  '{r['desc_prefix'][:52]}'{sim_info}")
    return report


if __name__ == "__main__":
    main()
