import pandas as pd
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from tools.groupby_analyzer import (
    detect_groupby_intent,
    compute_groupby_stats,
    format_groupby_for_context,
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
