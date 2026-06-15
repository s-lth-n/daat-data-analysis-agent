"""
test_diagnosa5_commitA.py — Diagnosa #5, Commit A.

/analyze kini SADAR hasil GROUP BY: node compute_statistics meng-inject blok
breakdown (build_followup_context, helper yang SAMA dengan followup) ke
state["statistics"]["__followup_context__"], persis seperti /analyze/followup.

Memverifikasi:
  1. compute_statistics meng-set __followup_context__ untuk query groupby/ranking
     (mis. "top products by revenue") — pakai data yang sudah ada di state.
  2. Query non-groupby (mis. "ringkas data ini") → TIDAK ada __followup_context__
     → STATS_CONTEXT seperti semula (no regresi).
  3. _build_stats_context atas statistics ber-__followup_context__ → nama produk
     teratas (REGENCY) + nilai per-grup Revenue ikut masuk konteks.
  4. Anti-halusinasi: nilai per-grup teratas (kini DI konteks) TIDAK diredaksi [?];
     angka karangan TETAP diredaksi.

Catatan (terkonfirmasi empiris, SAMA dengan perilaku followup): build_followup_context
menyuntik angka PER-GRUP (produk teratas), BUKAN grand total. Grand total Revenue
tampil di blok deterministik (build_deterministic_block) di atas narasi, bukan di
konteks LLM. Test #4 karenanya menguji nilai per-grup, bukan grand total.
"""

import pandas as pd
import pytest

from agents.data_agent import compute_statistics
from tools.narrative_generator import _build_stats_context, _redact_unverified_numbers


# ── Fixtures ──────────────────────────────────────────────────────────────────

PROFILE = {
    "Description": "kategorik",
    "Country":     "kategorik",
    "Quantity":    "numerik_valid",
    "Price":       "numerik_valid",
}
RETAIL = {"domain_type": "retail", "preferred_aggregation": "sum"}

# Revenue per row = Qty×Price = [12000, 8000, 2000, 600, 2500, 90]
#   REGENCY = 20.000 (teratas) | WHITE HANGING = 4.500 | JUMBO = 690 | total = 25.190
DF = pd.DataFrame({
    "Description": ["REGENCY CAKESTAND 3 TIER", "REGENCY CAKESTAND 3 TIER",
                    "WHITE HANGING HEART", "JUMBO BAG", "WHITE HANGING HEART",
                    "JUMBO BAG"],
    "Country":  ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity": [120, 80, 40, 30, 50, 10],
    "Price":    [100.0, 100.0, 50.0, 20.0, 50.0, 9.0],
})


def _run_node(prompt: str) -> dict:
    """Jalankan node compute_statistics dgn state minimal (df sudah ada → tak reload)."""
    state = {
        "prompt":           prompt,
        "language":         "en",
        "dataframe_loaded": True,
        "file_path":        "dummy.csv",   # truthy; df ada → load_dataframe tak dipanggil
        "dataframe":        DF,
        "column_profile":   PROFILE,
        "domain_context":   RETAIL,
    }
    return compute_statistics(state)


# ── 1. Node meng-inject __followup_context__ untuk query groupby/ranking ──────

def test_compute_statistics_injects_groupby_context_for_ranking_query():
    out = _run_node("what are the top products by revenue?")
    stats = out["statistics"]
    assert "__followup_context__" in stats
    ctx = stats["__followup_context__"]
    assert "BREAKDOWN PER DESCRIPTION" in ctx
    assert "REGENCY CAKESTAND 3 TIER" in ctx
    # Nilai per-grup Revenue produk teratas (Qty×Price) ikut diturunkan.
    assert "sum_Revenue=20,000.00" in ctx


# ── 2. Query non-groupby → tidak ada injeksi (no regresi) ─────────────────────

def test_compute_statistics_no_context_for_non_groupby_query():
    out = _run_node("ringkas data ini")
    assert "__followup_context__" not in out["statistics"]
    # Deskriptif tetap ada seperti semula.
    assert "descriptive" in out["statistics"]
    assert "correlation" in out["statistics"]


def test_compute_statistics_descriptive_unchanged_shape():
    """Injeksi groupby bersifat ADITIF — struktur lama (descriptive/correlation) utuh."""
    out = _run_node("top products by revenue")
    assert set(["descriptive", "correlation"]).issubset(out["statistics"].keys())
    assert "Quantity" in out["statistics"]["descriptive"]


# ── 3. STATS_CONTEXT memuat blok breakdown setelah injeksi ────────────────────

def test_stats_context_includes_breakdown_after_injection():
    out = _run_node("top products by revenue")
    sc = _build_stats_context(out["statistics"])
    assert "BREAKDOWN PER DESCRIPTION" in sc
    assert "REGENCY CAKESTAND 3 TIER" in sc
    assert "20,000.00" in sc


# ── 4. Anti-halusinasi: nilai per-grup (di konteks) lolos, karangan diredaksi ─

def test_redactor_keeps_verified_group_value_drops_fabricated():
    out = _run_node("top products by revenue")
    state = {"statistics": out["statistics"], "cleaning_report": {}, "data_summary": ""}
    # 20,000.00 = nilai per-grup REGENCY (DI konteks) → harus lolos.
    # 99,999.00 = karangan (tak ada di konteks)        → harus diredaksi.
    narr = ("The top product REGENCY contributes 20,000.00 in revenue, "
            "while an invented 99,999.00 figure appears too.")
    clean, n = _redact_unverified_numbers(narr, state, "en")
    assert "20,000.00" in clean        # angka tabel terverifikasi → tetap
    assert "99,999.00" not in clean    # karangan → diredaksi
    assert n == 1
    assert "[?]" in clean


def test_redactor_no_false_positive_without_groupby_context():
    """Tanpa __followup_context__ (non-groupby), angka deskriptif sah tetap lolos."""
    out = _run_node("ringkas data ini")
    state = {"statistics": out["statistics"], "cleaning_report": {}, "data_summary": ""}
    # mean Quantity & Price ada di descriptive → contoh angka sah dari deskriptif.
    desc = out["statistics"]["descriptive"]
    qmean = desc["Quantity"]["mean"]
    narr = f"The mean quantity is {qmean}."
    clean, n = _redact_unverified_numbers(narr, state, "en")
    assert n == 0
    assert "[?]" not in clean
