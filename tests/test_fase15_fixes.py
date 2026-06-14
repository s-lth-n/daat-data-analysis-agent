"""
tests/test_fase15_fixes.py — regression tests for DAAT Fase 1.5.

Bagian A — semantic group mapping (products -> Description), Revenue derivation
           (Quantity x Price) for "top N by revenue", and COUNT per group for
           "transactions".
Bagian B — per-metric "not available" markers: a requested metric that cannot be
           computed must be flagged explicitly (no empty slot for the LLM to fill),
           while computable metrics still show real numbers.
Bagian d — regressions from Fase 1 must hold: English "countries"/"by revenue"
           still resolves to Country; Indonesian "per negara" STAYS a backstop
           (user decision: do not map negara->Country).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pandas as pd

from tools.groupby_analyzer import detect_groupby_intent, build_followup_context

PROFILE = {
    "Description": "kategorik",
    "Country":     "kategorik",
    "Quantity":    "numerik_valid",
    "Price":       "numerik_valid",
    "CustomerID":  "id_kolom",
}

# Revenue per product: WIDGET A = 10*2+5*2+4*3 = 42 ; GADGET B = 2*5+8*5 = 50 ;
# TRINKET C = 1*9 = 9  -> revenue order: GADGET B > WIDGET A > TRINKET C
DF = pd.DataFrame({
    "Description": ["WIDGET A", "WIDGET A", "GADGET B", "WIDGET A", "GADGET B", "TRINKET C"],
    "Country":     ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity":    [10, 5, 2, 4, 8, 1],
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],
    "CustomerID":  [111.0, 111.0, 222.0, 333.0, 111.0, 444.0],
})


# ── Bagian A: semantic product mapping + revenue derivation ──────────────────

def test_detect_products_maps_to_description():
    r = detect_groupby_intent("top 10 products by total revenue", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Description"


def test_products_by_revenue_real_numbers_not_backstop():
    ctx = build_followup_context(DF, "top products by total revenue", PROFILE)
    assert "BREAKDOWN PER DESCRIPTION" in ctx
    assert "sum_Revenue" in ctx                      # Revenue was derived
    assert "TIDAK TERSEDIA" not in ctx               # not the backstop
    # sorted descending by revenue: GADGET B (50) before WIDGET A (42)
    assert ctx.index("GADGET B") < ctx.index("WIDGET A")


# ── Bagian A: transactions = COUNT per group ─────────────────────────────────

def test_transactions_per_country_uses_count():
    ctx = build_followup_context(DF, "number of transactions per country", PROFILE)
    assert "BREAKDOWN PER COUNTRY" in ctx
    assert "count=4" in ctx                          # UK appears 4x
    assert "jumlah transaksi" in ctx.lower()         # count clarified as transactions


# ── Bagian B: per-metric "not available" marker ──────────────────────────────

def test_unavailable_metric_marked_without_numbers():
    """revenue computable + profit NOT computable -> profit flagged, no profit digits.

    (Transaction count is always computable, so an uncomputable metric like
    'profit' is used to exercise the per-metric marker.)
    """
    ctx = build_followup_context(DF, "total revenue and profit per country", PROFILE)
    assert "sum_Revenue" in ctx                      # real revenue numbers present
    assert "'profit'" in ctx and "TIDAK TERSEDIA" in ctx
    # The profit marker must never carry a fabricated number.
    for line in ctx.splitlines():
        if "profit" in line.lower():
            assert not any(ch.isdigit() for ch in line)


# ── Bagian d: Fase 1 regressions must hold ───────────────────────────────────

def test_regression_english_countries_by_revenue():
    r = detect_groupby_intent("top 5 countries by revenue", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Country"
    ctx = build_followup_context(DF, "top 5 countries by revenue", PROFILE)
    assert "BREAKDOWN PER COUNTRY" in ctx and "sum_Revenue" in ctx


def test_indonesian_negara_maps_to_country_fase16():
    """Fase 1.6 REVERSES the Fase 1.5 decision: 'per negara' now maps to Country
    and returns real per-Country numbers (Indonesia-first parity)."""
    ctx = build_followup_context(DF, "rata-rata transaksi per negara", PROFILE)
    assert "BREAKDOWN PER COUNTRY" in ctx
    assert "count=" in ctx
    assert "TIDAK TERSEDIA" not in ctx
