import pandas as pd
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from tools.groupby_analyzer import (
    detect_groupby_intent,
    compute_groupby_stats,
    format_groupby_for_context,
    build_summary_revenue_line,
    _fmt_num,
)

MOCK_PROFILE = {
    "CustomerID": "id_kolom",
    "Country":    "kategorik",
    "Quantity":   "numerik_valid",
    "UnitPrice":  "numerik_valid",
    "Revenue":    "numerik_valid",
}

MOCK_DF = pd.DataFrame({
    "Country":   ["UK", "UK", "Germany", "France", "UK"],
    "Quantity":  [6, 3, 2, 4, 1],
    "UnitPrice": [2.55, 3.39, 4.25, 1.65, 5.00],
    "Revenue":   [15.30, 10.17, 8.50, 6.60, 5.00],
})

def test_detect_per_keyword():
    r = detect_groupby_intent("breakdown per Country", MOCK_PROFILE, list(MOCK_DF.columns))
    assert r is not None and r["group_col"] == "Country"

def test_detect_berdasarkan_keyword():
    r = detect_groupby_intent("analisis berdasarkan Country", MOCK_PROFILE, list(MOCK_DF.columns))
    assert r is not None and r["group_col"] == "Country"

def test_detect_no_intent():
    r = detect_groupby_intent("berapa rata-rata revenue?", MOCK_PROFILE, list(MOCK_DF.columns))
    assert r is None

def test_detect_no_categorical_col():
    profile_no_cat = {k: "numerik_valid" for k in MOCK_PROFILE}
    r = detect_groupby_intent("per Country", profile_no_cat, list(MOCK_DF.columns))
    assert r is None

def test_compute_output_structure():
    r = compute_groupby_stats(MOCK_DF, "Country", {"preferred_aggregation": "sum"})
    assert r["group_col"] == "Country"
    assert r["agg_func"] == "sum"
    assert len(r["results"]) == 3

def test_compute_sorted_descending():
    r = compute_groupby_stats(MOCK_DF, "Country")
    assert r["results"][0]


# ── build_summary_revenue_line (fallback paritas /analyze non-groupby) ──────

# Retail df TANPA kolom revenue → Revenue WAJIB diturunkan Quantity×Price.
RETAIL_NO_REV_DF = pd.DataFrame({
    "Country":  ["UK", "UK", "Germany", "France"],
    "Quantity": [6, 3, 2, 4],
    "Price":    [2.0, 4.0, 5.0, 1.0],
})
RETAIL_NO_REV_PROFILE = {
    "Country":  "kategorik",
    "Quantity": "numerik_valid",
    "Price":    "numerik_valid",
}

# CDC-like df: kolom numerik yang BUKAN quantity/price/revenue (YearStart kategorik).
CDC_DF = pd.DataFrame({
    "Topic":     ["A", "B", "A"],
    "YearStart": [2018, 2019, 2020],
    "DataValue": [12.5, 33.1, 7.0],
})
CDC_PROFILE = {
    "Topic":     "kategorik",
    "YearStart": "kategorik",
    "DataValue": "numerik_valid",
}


def test_summary_revenue_line_derived_retail():
    """Qty×Price disumkan jadi Revenue (bukan Σ Price)."""
    line = build_summary_revenue_line(
        RETAIL_NO_REV_DF, RETAIL_NO_REV_PROFILE, language="id"
    )
    assert line  # non-empty
    expected_total = float((RETAIL_NO_REV_DF["Quantity"] * RETAIL_NO_REV_DF["Price"]).sum())
    assert expected_total == 6 * 2 + 3 * 4 + 2 * 5 + 4 * 1  # 12+12+10+4 = 38
    assert _fmt_num(expected_total, "id") in line          # 38,00 muncul
    # Σ Price (12,00) BUKAN total penjualan → tak boleh sama dengan total Revenue.
    sum_price = float(RETAIL_NO_REV_DF["Price"].sum())
    assert sum_price != expected_total
    assert "Revenue" in line


def test_summary_revenue_line_cdc_returns_empty():
    """Tanpa Quantity/Price/revenue → "" (jangan karang metrik penjualan)."""
    line = build_summary_revenue_line(CDC_DF, CDC_PROFILE, language="id")
    assert line == ""


def test_summary_revenue_line_english():
    """language='en' → kalimat Inggris + angka gaya EN."""
    line = build_summary_revenue_line(
        RETAIL_NO_REV_DF, RETAIL_NO_REV_PROFILE, language="en"
    )
    assert line
    assert "from" in line and "rows" in line
    assert "total sales" in line.lower()
    expected_total = float((RETAIL_NO_REV_DF["Quantity"] * RETAIL_NO_REV_DF["Price"]).sum())
    assert _fmt_num(expected_total, "en") in line          # 38.00 muncul
