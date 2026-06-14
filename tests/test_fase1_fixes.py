"""
tests/test_fase1_fixes.py — regression tests for DAAT Fase 1 bug fixes.

Covers:
  Bug 1 — stratified temporal sampler must PASS THROUGH (no truncation) when the
          dataset already fits within the target row cap.
  Bug 3 — groupby intent recognition ("per country" + average/total/top-N) and the
          anti-hallucination backstop: a segmentation request that cannot be
          recomputed must yield an honest "not available" notice WITHOUT inventing
          any numbers (never silently feed the LLM stale/fabricated figures).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pandas as pd

from tools.data_loader import _stratified_temporal_sample
from tools.groupby_analyzer import detect_groupby_intent, build_followup_context


# ── Bug 1: sampler pass-through ──────────────────────────────────────────────

PROFILE = {
    "Country": "kategorik",
    "Quantity": "numerik_valid",
    "Price": "numerik_valid",
    "CustomerID": "id_kolom",
    "InvoiceDate": "datetime",
}

DF = pd.DataFrame({
    "Country":    ["UK", "UK", "Germany", "France", "UK", "Germany"],
    "Quantity":   [6, 3, 2, 4, 1, 5],
    "Price":      [2.55, 3.39, 4.25, 1.65, 5.00, 2.00],
    "CustomerID": [111.0, 111.0, 222.0, 333.0, 111.0, 222.0],
    "InvoiceDate": ["2010-12-01", "2010-12-01", "2010-12-02",
                    "2010-12-03", "2010-12-03", "2010-12-04"],
})


def test_sampler_passthrough_when_under_target():
    """len(df) <= max_rows → ALL rows kept (this is the 50K→31K data-loss bug)."""
    out = _stratified_temporal_sample(DF, "InvoiceDate", max_rows=50_000)
    assert len(out) == len(DF)


def test_sampler_passthrough_at_exact_target():
    """len(df) == max_rows is still a pass-through (boundary)."""
    out = _stratified_temporal_sample(DF, "InvoiceDate", max_rows=len(DF))
    assert len(out) == len(DF)


def test_sampler_still_samples_when_over_target():
    """Genuinely-large datasets (> target) are still down-sampled."""
    big = pd.DataFrame({
        "y": (["2020"] * 100) + (["2021"] * 100) + (["2022"] * 100),
        "v": list(range(300)),
    })
    out = _stratified_temporal_sample(big, "y", max_rows=30)
    assert 0 < len(out) <= 30


# ── Bug 3: groupby recall ────────────────────────────────────────────────────

def test_detect_per_country_average():
    r = detect_groupby_intent("average revenue per country", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Country"


def test_detect_total_per_country():
    r = detect_groupby_intent("total sales per Country", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Country"


def test_detect_plural_top_n_by():
    """'top 5 countries by revenue' — plural + 'by' must still resolve to Country."""
    r = detect_groupby_intent("top 5 countries by revenue", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Country"


# ── Bug 3: anti-hallucination backstop ───────────────────────────────────────

def test_followup_context_recompute_has_real_numbers():
    """Detectable groupby → real per-group numbers injected (incl. count)."""
    ctx = build_followup_context(DF, "average price per country", PROFILE)
    assert "BREAKDOWN PER COUNTRY" in ctx
    assert "count=" in ctx
    # ID column must NOT be aggregated as a metric
    assert "CustomerID" not in ctx


def test_followup_context_unknown_group_refuses_without_numbers():
    """Segmentation requested but column unmappable → honest notice, NO numbers.

    NOTE: 'per negara' now maps to Country (Fase 1.6), so this uses a genuinely
    non-existent dimension ('per galaksi') to exercise the honest backstop.
    """
    ctx = build_followup_context(DF, "rata-rata transaksi per galaksi", PROFILE)
    assert ctx != ""
    assert "TIDAK TERSEDIA" in ctx.upper()
    # Critical: the notice must not hand the LLM any digits to copy as fabrication.
    assert not any(ch.isdigit() for ch in ctx)


def test_followup_context_non_segmentation_is_empty():
    """Plain stat question (no group-by) → no injection (normal stats answer)."""
    ctx = build_followup_context(DF, "berapa rata-rata revenue?", PROFILE)
    assert ctx == ""
