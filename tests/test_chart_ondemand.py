"""
test_chart_ondemand.py — Revisi #1: gerbang chart ON-DEMAND.

Memverifikasi tools.chart_intent.wants_chart():
  (a) pesan biasa non-groupby tanpa keyword grafik → False (teks-saja)
  (b) pesan minta grafik eksplisit (ID+EN)          → True
  (c) intent groupby/ranking (produk terlaris/...)  → True (pakai ulang resolver)
  (d) intent temporal (tren per bulan)              → True
Plus guard anti-false-match & fail-safe (exception → False).
"""

import pandas as pd
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from tools.chart_intent import wants_chart, has_explicit_chart_keyword
from tools.groupby_analyzer import (
    build_followup_chart_spec,
    build_deterministic_block,
)


MOCK_PROFILE = {
    "Country":     "kategorik",
    "Description": "kategorik",
    "InvoiceDate": "datetime",
    "Quantity":    "numerik_valid",
    "UnitPrice":   "numerik_valid",
}

MOCK_DF = pd.DataFrame({
    "Country":     ["UK", "UK", "Germany", "France", "UK"],
    "Description": ["Mug", "Mug", "Lamp", "Pen", "Lamp"],
    "InvoiceDate": pd.to_datetime(
        ["2011-01-05", "2011-02-10", "2011-02-15", "2011-03-01", "2011-03-20"]
    ),
    "Quantity":    [6, 3, 2, 4, 1],
    "UnitPrice":   [2.55, 3.39, 4.25, 1.65, 5.00],
})


# ── (a) Non-groupby tanpa keyword → tidak ada grafik ────────────────────────
@pytest.mark.parametrize("q", [
    "berapa rata-rata revenue?",
    "ringkas datanya dong",
    "apa kesimpulan dari analisis ini?",
    "what is the average unit price?",
])
def test_plain_question_no_chart(q):
    assert wants_chart(q, df=MOCK_DF, column_profile=MOCK_PROFILE) is False


# ── (b) Minta grafik eksplisit (ID+EN) → True ───────────────────────────────
@pytest.mark.parametrize("q", [
    "buatkan grafik penjualan",
    "tolong visualisasikan datanya",
    "visualisasi distribusi harga",     # 'distribusi' juga intent, tapi keyword sudah cukup
    "tampilkan grafik",
    "bikin diagram batang",
    "plot data ini",
    "show me a chart",
    "can you graph this?",
    "buatkan bagan",
])
def test_explicit_chart_keyword(q):
    assert wants_chart(q, df=MOCK_DF, column_profile=MOCK_PROFILE) is True


def test_explicit_keyword_works_without_dataframe():
    # Jalur keyword eksplisit tidak butuh df/profile.
    assert wants_chart("buatkan grafik") is True
    assert wants_chart("visualize this", df=None, column_profile=None) is True


# ── (c) Intent groupby/ranking → True (TANPA keyword grafik) ────────────────
@pytest.mark.parametrize("q", [
    "produk terlaris apa?",
    "top 10 produk",
    "penjualan per negara",
    "breakdown berdasarkan country",
])
def test_groupby_intent_triggers_chart(q):
    # Tidak mengandung kata 'grafik' dst → murni dari intent groupby.
    assert has_explicit_chart_keyword(q) is False
    assert wants_chart(q, df=MOCK_DF, column_profile=MOCK_PROFILE) is True


# ── (d) Intent temporal → True ──────────────────────────────────────────────
@pytest.mark.parametrize("q", [
    "tren per bulan",
    "bagaimana penjualan tiap bulan",
    "monthly sales trend",
])
def test_temporal_intent_triggers_chart(q):
    assert has_explicit_chart_keyword(q) is False
    assert wants_chart(q, df=MOCK_DF, column_profile=MOCK_PROFILE) is True


# ── Guard anti-false-match ──────────────────────────────────────────────────
@pytest.mark.parametrize("q", [
    "tuliskan paragraf kesimpulan",   # 'paragraf'/'paragraph' bukan 'graph'
    "is this an exploit?",            # 'exploit' bukan 'plot'
])
def test_no_false_positive_substring(q):
    assert has_explicit_chart_keyword(q) is False


# ── Fail-safe: input aneh → False, tidak raise ──────────────────────────────
def test_failsafe_none_and_empty():
    assert wants_chart(None) is False
    assert wants_chart("") is False
    assert has_explicit_chart_keyword(None) is False


# ════════════════════════════════════════════════════════════════════════════
# Phase 2 — chart RELEVAN untuk followup (build_followup_chart_spec)
# ════════════════════════════════════════════════════════════════════════════

import base64
import numpy as np

# Plotly to_json meng-encode array numerik sebagai typed-array {dtype, bdata(base64)}.
_NP_DTYPE = {"f8": "<f8", "f4": "<f4", "i8": "<i8", "i4": "<i4",
             "u8": "<u8", "u4": "<u4", "i2": "<i2", "i1": "<i1", "u1": "<u1"}


def _traces(spec):
    assert spec is not None and isinstance(spec, dict)
    return spec["data"]


def _arr(v):
    """Decode array Plotly: list biasa ATAU typed-array {dtype, bdata}."""
    if isinstance(v, dict) and "bdata" in v:
        raw = base64.b64decode(v["bdata"])
        return np.frombuffer(raw, dtype=_NP_DTYPE.get(v.get("dtype", "f8"), "<f8")).tolist()
    return list(v)


# followup intent groupby → bar chart relevan (bukan overview) ───────────────
def test_followup_groupby_generates_relevant_bar():
    spec = build_followup_chart_spec(
        MOCK_DF, "penjualan per negara", MOCK_PROFILE, None, "id"
    )
    data = _traces(spec)
    assert data[0]["type"] == "bar"
    # Sumbu kategori memuat negara hasil groupby (bukan judul overview generik).
    ys = [str(v) for v in _arr(data[0]["y"])]
    assert "UK" in ys and "Germany" in ys and "France" in ys


# followup temporal → line chart ────────────────────────────────────────────
def test_followup_temporal_generates_line():
    spec = build_followup_chart_spec(
        MOCK_DF, "tren per bulan", MOCK_PROFILE, None, "id"
    )
    data = _traces(spec)
    assert data[0]["type"] == "scatter"          # px.line → trace scatter
    xs = [str(v) for v in _arr(data[0]["x"])]
    assert len(xs) == 3 and xs == sorted(xs)     # 3 bulan, urut kronologis


# followup minta grafik eksplisit TANPA intent → None (caller pakai cache) ───
def test_followup_explicit_only_returns_none():
    # 'buatkan grafik' tak punya intent groupby/temporal → spec None →
    # main.py jatuh ke overview cache (keputusan final, tak berubah).
    assert build_followup_chart_spec(
        MOCK_DF, "buatkan grafik", MOCK_PROFILE, None, "id"
    ) is None


# followup non-chart → None (regresi Phase 1 aman) ──────────────────────────
@pytest.mark.parametrize("q", [
    "berapa rata-rata revenue?",
    "apa kesimpulannya?",
])
def test_followup_non_chart_returns_none(q):
    assert build_followup_chart_spec(MOCK_DF, q, MOCK_PROFILE, None, "id") is None


# Konsistensi angka: nilai chart == nilai blok deterministik ────────────────
def test_chart_numbers_match_deterministic_block():
    q = "penjualan per negara"
    spec = build_followup_chart_spec(MOCK_DF, q, MOCK_PROFILE, None, "id")
    data = _traces(spec)
    xs = [float(v) for v in _arr(data[0]["x"])]
    # Revenue = Quantity×UnitPrice; UK = 6*2.55 + 3*3.39 + 1*5.00 = 30.47 (tertinggi).
    assert max(xs) == pytest.approx(30.47, abs=0.01)
    # Blok deterministik (angka USER) harus menyebut nilai yang SAMA (format ID).
    det = build_deterministic_block(MOCK_DF, q, MOCK_PROFILE, None)
    assert "30,47" in det


# Fail-safe: input aneh → None, tidak raise ─────────────────────────────────
def test_chart_spec_failsafe():
    assert build_followup_chart_spec(None, "per negara", MOCK_PROFILE, None, "id") is None
    assert build_followup_chart_spec(MOCK_DF, None, MOCK_PROFILE, None, "id") is None
