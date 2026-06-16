"""
tests/test_fase16_synonyms.py — ID<->EN column-synonym parity (DAAT Fase 1.6).

Maps common Indonesian/English terms to REAL columns by role:
  negara -> Country, produk/barang/item -> Description, harga -> Price,
  kuantitas/jumlah barang -> Quantity, bulan/tanggal -> datetime (per-month),
  transaksi -> COUNT. Anti-false-match: a synonym with no related column stays
  a backstop (never forced onto an unrelated column).
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
    "InvoiceDate": "datetime",
}

# Revenue/month: Jan = 10*2+5*2 = 30 ; Feb = 2*5+4*3 = 22 ; Mar = 8*5+1*9 = 49
DF = pd.DataFrame({
    "Description": ["WIDGET A", "WIDGET A", "GADGET B", "WIDGET A", "GADGET B", "TRINKET C"],
    "Country":     ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity":    [10, 5, 2, 4, 8, 1],
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],
    "CustomerID":  [111.0, 111.0, 222.0, 333.0, 111.0, 444.0],
    "InvoiceDate": ["2011-01-05", "2011-01-20", "2011-02-10",
                    "2011-02-15", "2011-03-01", "2011-03-22"],
})


# ── negara -> Country ────────────────────────────────────────────────────────

def test_detect_negara_maps_country():
    r = detect_groupby_intent("rata-rata revenue per negara", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Country"


def test_negara_real_numbers_not_backstop():
    ctx = build_followup_context(DF, "rata-rata revenue per negara", PROFILE)
    assert "BREAKDOWN PER COUNTRY" in ctx
    # Fix C — pertanyaan "rata-rata ..." → konteks diurut & bernilai MEAN (bukan sum).
    assert "mean_Revenue" in ctx
    assert "TIDAK TERSEDIA" not in ctx


def test_transaksi_per_negara_count():
    ctx = build_followup_context(DF, "transaksi per negara", PROFILE)
    assert "BREAKDOWN PER COUNTRY" in ctx
    assert "count=4" in ctx                       # UK appears 4x
    assert "jumlah transaksi" in ctx.lower()


# ── produk/barang/item -> Description ────────────────────────────────────────

def test_detect_produk_terlaris_maps_description():
    r = detect_groupby_intent("produk terlaris", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Description"


def test_top_produk_breakdown_description():
    ctx = build_followup_context(DF, "top 10 produk", PROFILE)
    assert "BREAKDOWN PER DESCRIPTION" in ctx


def test_barang_synonym_description():
    r = detect_groupby_intent("penjualan per barang", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Description"


# ── harga -> Price ; kuantitas/jumlah barang -> Quantity ─────────────────────

def test_harga_metric_per_negara():
    ctx = build_followup_context(DF, "rata-rata harga per negara", PROFILE)
    assert "BREAKDOWN PER COUNTRY" in ctx
    assert "sum_Price" in ctx or "mean_Price" in ctx


def test_kuantitas_metric_per_produk():
    ctx = build_followup_context(DF, "total kuantitas per produk", PROFILE)
    assert "BREAKDOWN PER DESCRIPTION" in ctx
    assert "sum_Quantity" in ctx


# ── bulan/tanggal/waktu -> datetime (per-month) ──────────────────────────────

def test_temporal_per_bulan_real_numbers():
    ctx = build_followup_context(DF, "penjualan per bulan", PROFILE)
    assert "BREAKDOWN PER PERIODE" in ctx
    assert "2011-03" in ctx                        # months actually bucketed
    assert "sum_Revenue" in ctx


# ── anti-false-match: synonym without a related column stays a backstop ───────

def test_no_region_column_stays_backstop():
    ctx = build_followup_context(DF, "rata-rata revenue per wilayah", PROFILE)
    assert "TIDAK TERSEDIA" in ctx
    assert not any(ch.isdigit() for ch in ctx)


def test_negara_without_country_column_stays_backstop():
    """A dataset with no country-like column must NOT mis-map 'negara'."""
    acad = pd.DataFrame({
        "Jurusan": ["TT", "TT", "IF", "EL"],
        "IPK":     [3.5, 3.2, 3.8, 2.9],
    })
    acad_prof = {"Jurusan": "kategorik", "IPK": "numerik_valid"}
    ctx = build_followup_context(acad, "rata-rata IPK per negara", acad_prof)
    assert "TIDAK TERSEDIA" in ctx
    assert not any(ch.isdigit() for ch in ctx)


def test_academic_jurusan_still_maps_by_name():
    """Sanity: a real categorical ('Jurusan') still resolves by direct name match."""
    acad = pd.DataFrame({"Jurusan": ["TT", "TT", "IF"], "IPK": [3.5, 3.2, 3.8]})
    acad_prof = {"Jurusan": "kategorik", "IPK": "numerik_valid"}
    r = detect_groupby_intent("rata-rata IPK per jurusan", acad_prof, list(acad.columns))
    assert r is not None and r["group_col"] == "Jurusan"


# ── regression: genuinely-uncomputable metric still flagged (Fase 1.5/B) ─────

def test_profit_metric_still_unavailable():
    ctx = build_followup_context(DF, "total revenue and profit per negara", PROFILE)
    assert "sum_Revenue" in ctx
    assert "'profit'" in ctx and "TIDAK TERSEDIA" in ctx
