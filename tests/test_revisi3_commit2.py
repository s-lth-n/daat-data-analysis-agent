"""
Revisi #3 — Commit 2 tests.
/analyze memakai blok deterministik + Revenue-default cerdas untuk retail.

Fokus pada LOGIKA pemilihan metrik (shared resolver) + paritas chart↔tabel +
gating retail. Angka diuji pada DF sintetis kecil yang totalnya bisa dihitung
tangan: Revenue=Σ(Qty×Price)=101, Quantity=Σ=30, Price=Σ=26.
"""

import base64
import numpy as np
import pandas as pd
import pytest

from tools.groupby_analyzer import (
    build_deterministic_block, build_followup_chart_spec,
    _resolve_followup_aggregation,
)

PROFILE = {
    "Description": "kategorik",
    "Country":     "kategorik",
    "Quantity":    "numerik_valid",
    "Price":       "numerik_valid",
}
DF = pd.DataFrame({
    "Description": ["A", "A", "B", "C", "B", "A"],
    "Country":     ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity":    [10, 5, 2, 4, 8, 1],     # Σ = 30
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],  # Σ = 26
    # Revenue per row = [20, 10, 10, 12, 40, 9] → Σ = 101
})
RETAIL = {"domain_type": "retail", "preferred_aggregation": "sum"}


def _primary(q, ctx):
    agg = _resolve_followup_aggregation(DF, q, PROFILE, ctx)
    return agg["primary"] if agg else None


# ── Revenue-default cerdas (retail) ─────────────────────────────────────────

def test_terlaris_retail_defaults_to_revenue():
    """'produk terlaris' + retail → metrik Revenue (101), BUKAN Quantity/Price."""
    assert _primary("produk terlaris", RETAIL) == "Revenue"
    block = build_deterministic_block(DF, "produk terlaris", PROFILE, RETAIL, "id")
    assert "Total Revenue = 101,00" in block
    # Σ Price (26) TIDAK pernah jadi headline untuk 'terlaris'.
    assert "Total Price" not in block


@pytest.mark.parametrize("q", [
    "produk terbaik", "top 10 produk", "best-selling product", "produk paling laris",
])
def test_ranking_words_retail_revenue(q):
    assert _primary(q, RETAIL) == "Revenue"


# ── Metrik eksplisit tetap menang (default cerdas, bukan paksaan) ───────────

def test_explicit_quantity_stays_quantity():
    """'kuantitas terbanyak' eksplisit → Quantity (30), bukan Revenue."""
    assert _primary("produk dengan kuantitas terbanyak", RETAIL) == "Quantity"
    block = build_deterministic_block(
        DF, "produk dengan kuantitas terbanyak", PROFILE, RETAIL, "id"
    )
    assert "Total Quantity = 30" in block


def test_explicit_revenue_word_still_revenue():
    assert _primary("produk terlaris berdasarkan revenue", RETAIL) == "Revenue"


def test_explicit_price_stays_price():
    assert _primary("harga rata-rata per produk", RETAIL) == "Price"


# ── Gating: Revenue-default HANYA untuk retail ──────────────────────────────

def test_terlaris_non_retail_not_revenue():
    """Tanpa domain retail → fallback lama numeric_now[0]=Quantity (bukan Revenue)."""
    assert _primary("produk terlaris", None) == "Quantity"
    assert _primary("produk terlaris", {"domain_type": "healthcare"}) == "Quantity"


# ── Konsistensi chart ↔ tabel (derivasi Revenue tunggal) ────────────────────

def _arr(v):
    if isinstance(v, dict) and "bdata" in v:
        raw = base64.b64decode(v["bdata"])
        dt = {"f8": "<f8", "i8": "<i8"}.get(v.get("dtype", "f8"), "<f8")
        return np.frombuffer(raw, dtype=dt).tolist()
    return list(v)


def test_chart_matches_table_revenue_default():
    """Chart 'produk terlaris' retail memakai Revenue yang SAMA dgn tabel."""
    spec = build_followup_chart_spec(DF, "produk terlaris", PROFILE, RETAIL, "id")
    assert spec is not None
    xs = [float(v) for v in _arr(spec["data"][0]["x"])]
    # Revenue per Description: A=20+10+9=39, B=10+40=50, C=12 → max grup = 50.
    assert max(xs) == pytest.approx(50.0, abs=0.01)
    block = build_deterministic_block(DF, "produk terlaris", PROFILE, RETAIL, "id")
    assert "50,00" in block        # nilai grup tertinggi muncul di tabel juga


# ── Fallback non-groupby (tidak crash, blok kosong) ─────────────────────────

def test_non_groupby_returns_empty_block():
    """'ringkas data ini' bukan groupby → blok kosong → /analyze fallback narasi."""
    assert build_deterministic_block(DF, "ringkas data ini", PROFILE, RETAIL, "id") == ""
