"""
test_diagnosa6_context.py — Diagnosa #6 (perbaikan DETERMINISTIK konteks LLM).

Gejala: tabel deterministik BENAR & terurut by Revenue, TAPI prosa LLM salah
pilih/urut produk teratas — condong ke item ber-mean (rata-rata harga/revenue
satuan) tinggi (Memoboard, Doorstop) yang sum_Revenue-nya rendah.

Akar (terverifikasi): blok konteks-LLM (format_groupby_for_context) menampilkan
6 metrik/baris termasuk mean_* (distractor yang me-rank produk BERBEDA), TANPA
penanda rank, dan jalur "terlaris" polos diam-diam diurut by Quantity.

Penanganan deterministik (NOL instruksi prompt seleksi):
  1. Drop mean_* dari blok konteks-LLM (kecuali agg memang "mean").
  2. Prefix #1..#N + baris fakta "sudah diurutkan".
  3. Jalur "terlaris" polos retail → Revenue-default SAMA dengan tabel/chart.

Pagar: nilai metrik tak berubah; tabel user-facing tak berubah; anti-halusinasi utuh.
"""

import re
import pandas as pd

from tools.groupby_analyzer import (
    build_followup_context, build_deterministic_block, format_groupby_for_context,
    compute_groupby_stats,
)

PROFILE = {
    "Description": "kategorik",
    "Country":     "kategorik",
    "Quantity":    "numerik_valid",
    "Price":       "numerik_valid",
}
RETAIL = {"domain_type": "retail", "preferred_aggregation": "sum"}

# Memoboard: 1 transaksi ber-revenue per-baris TERTINGGI (mean distractor) tapi
# sum_Revenue RENDAH → mean-ranking ≠ sum-ranking. Regency = #1 by Revenue.
DF = pd.DataFrame({
    "Description": ["REGENCY CAKESTAND", "REGENCY CAKESTAND", "REGENCY CAKESTAND",
                    "WHITE HANGING HEART", "WHITE HANGING HEART",
                    "VINTAGE UNION JACK MEMOBOARD"],
    "Country":  ["UK", "UK", "UK", "UK", "Germany", "UK"],
    "Quantity": [100, 80, 60, 120, 100, 50],
    "Price":    [100.0, 100.0, 100.0, 50.0, 50.0, 200.0],
})
# sum_Revenue: Regency 24.000 (#1) > White 11.000 (#2) > Memoboard 10.000 (#3)
# mean_Revenue: Memoboard 10.000 (tertinggi!) — distractor yang HARUS hilang.


def _ctx(q):
    return build_followup_context(DF, q, PROFILE, RETAIL)


def _breakdown_lines(ctx):
    """Baris produk ber-prefix #n di blok breakdown."""
    return [ln.strip() for ln in ctx.splitlines() if re.match(r"\s*#\d+\s", ln)]


# ── Bagian 1: mean_* dibuang dari blok konteks LLM ────────────────────────────

def test_no_mean_tokens_in_llm_context():
    ctx = _ctx("produk terlaris berdasarkan revenue")
    assert "mean_Revenue" not in ctx
    assert "mean_Quantity" not in ctx
    assert "mean_Price" not in ctx


def test_sum_metric_retained():
    ctx = _ctx("produk terlaris berdasarkan revenue")
    assert "sum_Revenue" in ctx          # metrik ranking tetap ada


# ── Bagian 2: penanda RANK eksplisit + baris fakta urutan ─────────────────────

def test_rank_prefix_present_and_descending():
    ctx = _ctx("produk terlaris berdasarkan revenue")
    lines = _breakdown_lines(ctx)
    assert lines, "harus ada baris breakdown ber-#n"
    # Prefix #1..#N berurutan
    assert [int(re.match(r"#(\d+)", ln).group(1)) for ln in lines] == list(
        range(1, len(lines) + 1)
    )
    # #1 = produk Revenue tertinggi = Regency
    assert lines[0].startswith("#1 REGENCY CAKESTAND")
    # sum_Revenue menurun
    revs = [float(re.search(r"sum_Revenue=([\d,]+\.\d+)", ln).group(1).replace(",", ""))
            for ln in lines]
    assert revs == sorted(revs, reverse=True)


def test_ranked_by_fact_line():
    ctx = _ctx("produk terlaris berdasarkan revenue")
    assert "SUDAH diurutkan" in ctx and "sum_Revenue" in ctx
    assert "already ranked" in ctx       # faktual, bukan instruksi perilaku


def test_distractor_product_not_ranked_first():
    """Memoboard (mean tertinggi) TIDAK boleh #1 — itu pemicu gejala #6."""
    lines = _breakdown_lines(_ctx("produk terlaris berdasarkan revenue"))
    assert "MEMOBOARD" not in lines[0]
    assert lines[0].startswith("#1 REGENCY")


# ── Bagian 3: jalur "terlaris" POLOS retail → Revenue-sorted (bukan Quantity) ──

def test_terlaris_polos_is_revenue_sorted():
    """Tanpa kata 'revenue', retail 'terlaris' tetap by Revenue (Regency #1)."""
    ctx = _ctx("produk terlaris")
    assert "sum_Revenue" in ctx           # Revenue diturunkan (default retail)
    lines = _breakdown_lines(ctx)
    assert lines[0].startswith("#1 REGENCY CAKESTAND")


# ── Bagian 4: KONSISTENSI konteks-LLM == tabel user untuk query yang sama ─────

def _first_product(table_or_ctx, is_table):
    if is_table:
        # baris tabel pertama: | NAMA | ... |
        for ln in table_or_ctx.splitlines():
            m = re.match(r"\|\s*([A-Z].*?)\s*\|", ln)
            if m and "Description" not in m.group(1):
                return m.group(1).strip()
        return None
    return _breakdown_lines(table_or_ctx)[0].split(" ", 1)[1].split(":")[0]


def test_context_and_table_agree_on_top_product():
    for q in ("produk terlaris", "produk terlaris berdasarkan revenue"):
        ctx_top = _first_product(_ctx(q), is_table=False)
        tbl_top = _first_product(build_deterministic_block(DF, q, PROFILE, RETAIL, "id"), is_table=True)
        assert ctx_top == tbl_top == "REGENCY CAKESTAND", (q, ctx_top, tbl_top)


# ── Bagian 5: regresi — agg=mean MEMPERTAHANKAN metriknya (mean_ = utama) ──────

def test_mean_agg_keeps_its_metric():
    """Bila preferred_aggregation='mean', mean_ ADALAH metrik utama → tak boleh
    ikut terbuang (kalau salah-drop, baris jadi tanpa metrik)."""
    gb = compute_groupby_stats(DF, "Description", {"preferred_aggregation": "mean"})
    out = format_groupby_for_context(gb)
    assert "mean_" in out                 # metrik utama bertahan
    # tiap baris produk punya minimal satu metrik (bukan cuma count)
    for ln in _breakdown_lines(out):
        assert "mean_" in ln


# ── Bagian 6: regresi — tabel user-facing TIDAK berubah (Regency #1) ─────────

def test_user_table_unchanged_regency_first():
    block = build_deterministic_block(DF, "produk terlaris", PROFILE, RETAIL, "id")
    assert "REGENCY CAKESTAND" in block
    assert "#1" not in block              # tabel user TIDAK pakai penanda #n internal
    assert _first_product(block, is_table=True) == "REGENCY CAKESTAND"
