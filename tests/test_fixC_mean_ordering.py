"""
Fix C — agregasi MEAN konsisten lintas blok/chart/konteks (gate = mean_intent).

Sebelum: pertanyaan "rata-rata ... tertinggi" diurut by SUM di ketiga jalur → grup
ber-n besar tampak #1 (padahal mean-nya bukan tertinggi), konteks LLM tanpa nilai
mean → narasi mengarang. Fix C: saat mean_intent, blok + chart + konteks SEMUA diurut
& bernilai MEAN per grup (identik), kolom Σ & % di tabel disembunyikan.

GATE = mean_intent LINTAS DOMAIN. Cabang sum (retail "terlaris") & count (CDC) tetap
byte-identik (uji negatif di bawah).
"""

import base64
import numpy as np
import pandas as pd

from tools.groupby_analyzer import (
    build_followup_context, build_deterministic_block,
    build_followup_chart_spec, _grand_total_context_line,
    compute_groupby_stats,
)
from tools.narrative_generator import _redact_unverified_numbers


def _arr(v):
    """Decode nilai sumbu Plotly (bisa base64 bdata atau list biasa)."""
    if isinstance(v, dict) and "bdata" in v:
        raw = base64.b64decode(v["bdata"])
        dt = {"f8": "<f8", "i8": "<i8"}.get(v.get("dtype", "f8"), "<f8")
        return np.frombuffer(raw, dtype=dt).tolist()
    return list(v)


# ── DF AKADEMIK: Teknik Sipil n=12 (Σ besar, mean 70 = TERENDAH);
#    Astronomi mean 85 (tertinggi), Biologi mean 84. ──────────────────────────
def _academic_df():
    rows = ([("Teknik Sipil", 70)] * 12 + [("Astronomi", 85)] * 3
            + [("Biologi", 84)] * 3)
    df = pd.DataFrame(rows, columns=["program_studi", "kehadiran_persen"])
    df["ukt_kelompok"] = 3
    return df


ACA_PROFILE = {
    "program_studi":    "kategorik",
    "kehadiran_persen": "numerik_valid",
    "ukt_kelompok":     "numerik_valid",
}
ACA_Q = "program studi dengan rata-rata kehadiran tertinggi"


def _table_rows(block: str) -> list:
    body = [ln for ln in block.splitlines() if ln.strip().startswith("|")]
    return body[2:]   # skip header + separator


# ── Jalur 1: tabel user diurut by mean, kolom Σ & % disembunyikan ────────────

def test_block_sorted_by_mean_astronomi_first():
    block = build_deterministic_block(_academic_df(), ACA_Q, ACA_PROFILE, None, "id")
    rows = _table_rows(block)
    # Baris #1 = Astronomi (mean 85), BUKAN Teknik Sipil (Σ besar, mean 70 terendah).
    assert rows[0].split("|")[1].strip() == "Astronomi"
    assert rows[-1].split("|")[1].strip() == "Teknik Sipil"


def test_block_mean_header_hides_sum_and_pct():
    block = build_deterministic_block(_academic_df(), ACA_Q, ACA_PROFILE, None, "id")
    assert "| program_studi | Rata-rata | n |" in block
    assert "%" not in block                       # kolom % hilang
    assert "Total kehadiran_persen" not in block  # headline Σ hilang
    assert "Rata-rata kehadiran_persen = 74,83" in block   # headline = mean keseluruhan


def test_block_mean_cell_values():
    block = build_deterministic_block(_academic_df(), ACA_Q, ACA_PROFILE, None, "id")
    assert "| Astronomi | 85,00 | 3 |" in block
    assert "| Teknik Sipil | 70,00 | 12 |" in block


# ── Jalur 2: chart bars = mean (Astronomi teratas) ──────────────────────────

def test_chart_bars_are_mean():
    spec = build_followup_chart_spec(_academic_df(), ACA_Q, ACA_PROFILE, None, "id")
    assert spec is not None
    cats = _arr(spec["data"][0]["y"])             # h-bar: kategori di sumbu y
    vals = _arr(spec["data"][0]["x"])
    # h-bar ascending → kategori terakhir = bar TERATAS = Astronomi (mean tertinggi).
    assert cats[-1] == "Astronomi"
    assert vals[-1] == 85.0
    assert max(vals) == 85.0                       # bukan Σ Teknik Sipil (840)


# ── Jalur 3: konteks LLM diurut by mean + nilai mean ADA ────────────────────

def test_context_mean_ordered_with_values():
    ctx = build_followup_context(_academic_df(), ACA_Q, ACA_PROFILE, None)
    assert "BREAKDOWN PER PROGRAM_STUDI (mean)" in ctx
    assert "by mean_kehadiran_persen" in ctx
    # #1 di konteks = Astronomi dengan nilai mean nyata.
    first_line = next(l for l in ctx.splitlines() if l.strip().startswith("#1"))
    assert "Astronomi" in first_line and "mean_kehadiran_persen=85.00" in first_line
    assert "MEAN kehadiran_persen (all rows) = 74.83" in ctx


def test_grand_total_line_is_mean():
    line = _grand_total_context_line(_academic_df(), ACA_Q, ACA_PROFILE, None)
    assert line == "MEAN kehadiran_persen (all rows) = 74.83"


# ── Anti-halusinasi tetap aktif di jalur mean ────────────────────────────────

def test_redactor_active_on_mean_path():
    ctx = build_followup_context(_academic_df(), ACA_Q, ACA_PROFILE, None)
    state = {"statistics": {"__followup_context__": ctx}}
    # Angka mean NYATA (ada di konteks) → dipertahankan.
    good, n_good = _redact_unverified_numbers(
        "Astronomi memimpin dengan rata-rata 85,00; Biologi 84,00.", state, "id")
    assert "85,00" in good and "84,00" in good and n_good == 0
    # Angka mean KARANGAN (tak ada di konteks) → diredaksi [?].
    bad, n_bad = _redact_unverified_numbers(
        "Teknik Tenaga Listrik unggul dengan rata-rata 86,72.", state, "id")
    assert "[?]" in bad and "86,72" not in bad and n_bad == 1


# ── Guard 1: force_agg OPSIONAL — default None = perilaku lama persis ─────────

def test_force_agg_default_is_byte_identical():
    df = _academic_df()
    a = compute_groupby_stats(df, "program_studi")
    b = compute_groupby_stats(df, "program_studi", force_agg=None)
    assert a == b
    assert a["agg_func"] == "sum"                 # default tetap sum (tak terpengaruh)
    c = compute_groupby_stats(df, "program_studi", force_agg="mean")
    assert c["agg_func"] == "mean"                # override eksplisit berfungsi


# ── Cross-domain: retail "rata-rata revenue" ikut layout mean baru ───────────
RETAIL_PROFILE = {
    "Description": "kategorik", "Country": "kategorik",
    "Quantity": "numerik_valid", "Price": "numerik_valid",
}
RETAIL_DF = pd.DataFrame({
    "Description": ["A", "A", "B", "C", "B", "A"],
    "Country":     ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity":    [10, 5, 2, 4, 8, 1],
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],
})
RETAIL = {"domain_type": "retail", "preferred_aggregation": "sum"}


def test_retail_mean_question_uses_mean_layout():
    """Bukti gate LINTAS DOMAIN: retail 'rata-rata revenue per negara' → layout mean."""
    block = build_deterministic_block(RETAIL_DF, "rata-rata revenue per negara",
                                      RETAIL_PROFILE, RETAIL, "id")
    assert "| Country | Rata-rata | Harga/unit | n |" in block
    assert "| Country | Revenue | % |" not in block


# ── NEGATIF: cabang SUM (retail terlaris) byte-identik ───────────────────────

def test_retail_terlaris_sum_unchanged():
    block = build_deterministic_block(RETAIL_DF, "produk terlaris",
                                      RETAIL_PROFILE, RETAIL, "id")
    # Σ Revenue per Description: A=20+10+9=39, B=10+40=50, C=12 → B (#1, 50) terlaris.
    assert "Total Revenue = 101,00" in block       # headline Σ tetap
    assert "| Description | Revenue | % |" in block # kolom Σ & % tetap ada
    rows = _table_rows(block)
    assert rows[0].split("|")[1].strip() == "B"     # diurut by Σ (B=50 #1)
    ctx = build_followup_context(RETAIL_DF, "produk terlaris", RETAIL_PROFILE, RETAIL)
    assert "(sum)" in ctx                           # konteks tetap sum


# ── NEGATIF: cabang COUNT (CDC distribusi) byte-identik ──────────────────────
CDC_PROFILE = {"Topic": "kategorik", "YearStart": "kategorik"}
CDC_DF = pd.DataFrame({
    "Topic":     ["Asthma", "Asthma", "Diabetes", "Asthma", "Diabetes", "Cancer"],
    "YearStart": [2019, 2020, 2019, 2021, 2020, 2019],
})


def test_cdc_distribution_count_unchanged():
    block = build_deterministic_block(CDC_DF, "distribusi topik", CDC_PROFILE, None, "id")
    assert "| Topic | Jumlah | % |" in block        # cabang count: header lama
    assert "Rata-rata" not in block                 # tak ada kolom mean
    rows = _table_rows(block)
    assert rows[0].split("|")[1].strip() == "Asthma"  # Asthma 3x #1
