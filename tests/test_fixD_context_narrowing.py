"""
Fix D — konteks LLM mode MEAN dipersempit ke metrik yang DIMINTA (front).

Akar bug: di mode mean, _build_breakdown_block mengirim ≤5 mean_* per grup ke konteks
(mean_kehadiran + sibling mean_nilai_tugas/uts/bobot/sks). LLM mengambil nilai sibling
(mis. mean_nilai_tugas=63,69) lalu me-relabel sbg metrik yang ditanya (kehadiran). Angka
itu SAH di valid_vals (validasi keberadaan, bukan ikatan metrik↔entitas) → lolos redactor.

Fix D: saat mean_intent DAN metrik teridentifikasi (front) → konteks emit HANYA
mean_<diminta>; sibling di-drop → hilang dari konteks DAN valid_vals.

GATE = mean_intent + front non-kosong. Sum/count & mean-tanpa-metrik byte-identik.
"""

import re
import numpy as np
import pandas as pd

from tools.groupby_analyzer import build_followup_context
from tools.narrative_generator import (
    _collect_valid_number_text, _canonical_number, _NUM_TOKEN_RE,
)


# ── DF AKADEMIK mini: 3 prodi, banyak kolom numerik (kehadiran + sibling) ────
#   Teknik Telekomunikasi sengaja punya nilai_tugas=63 (jebakan sibling 63,69-style).
def _academic_df():
    rows = []
    for _ in range(6):
        rows.append(("Astronomi", 90, 80, 70, 75))        # kehadiran tinggi
    for _ in range(6):
        rows.append(("Biologi", 84, 78, 68, 70))
    for _ in range(6):
        rows.append(("Teknik Telekomunikasi", 82, 63, 60, 64))  # kehadiran 82, tugas 63
    return pd.DataFrame(
        rows,
        columns=["program_studi", "kehadiran_persen",
                 "nilai_tugas", "nilai_uts", "nilai_uas"],
    )


ACA_PROFILE = {
    "program_studi":    "kategorik",
    "kehadiran_persen": "numerik_valid",
    "nilai_tugas":      "numerik_valid",
    "nilai_uts":        "numerik_valid",
    "nilai_uas":        "numerik_valid",
}


def _mean_metrics(ctx: str) -> set:
    return set(re.findall(r"mean_\w+", ctx))


def _valid_vals(ctx: str) -> list:
    """Rakit valid_vals seperti redactor (dari __followup_context__ saja, fokus)."""
    state = {"statistics": {"__followup_context__": ctx}}
    text = _collect_valid_number_text(state)
    return [round(v, 2) for v in
            (_canonical_number(t) for t in _NUM_TOKEN_RE.findall(text)) if v is not None]


# ── (a) SINGLE-METRIK: konteks hanya mean_<primary>, sibling absen ───────────

def test_single_metric_context_only_primary():
    ctx = build_followup_context(
        _academic_df(), "program studi dengan rata-rata kehadiran tertinggi",
        ACA_PROFILE, None)
    assert "(mean)" in ctx
    assert _mean_metrics(ctx) == {"mean_kehadiran_persen"}     # HANYA yang diminta
    # sibling mean_* TIDAK muncul
    for sib in ("mean_nilai_tugas", "mean_nilai_uts", "mean_nilai_uas"):
        assert sib not in ctx


def test_single_metric_sibling_value_absent_from_valid_vals():
    """mean_nilai_tugas Teknik Telekomunikasi = 63 → kini TIDAK di pool → bila LLM
    mengarang '63' sbg kehadiran, redactor bisa tangkap."""
    ctx = build_followup_context(
        _academic_df(), "program studi dengan rata-rata kehadiran tertinggi",
        ACA_PROFILE, None)
    vv = _valid_vals(ctx)
    assert 63.0 not in vv                # nilai_tugas Teknik Telekomunikasi absen
    assert 82.0 in vv                    # mean_kehadiran Teknik Telekomunikasi tetap ada
    assert 90.0 in vv and 84.0 in vv     # kehadiran Astronomi/Biologi ada


# ── (b) MULTI-METRIK eksplisit: emit kedua yang diminta, drop sisanya ────────

def test_multi_metric_explicit_emits_both():
    ctx = build_followup_context(
        _academic_df(), "rata-rata nilai uts dan nilai uas per program studi",
        ACA_PROFILE, None)
    assert _mean_metrics(ctx) == {"mean_nilai_uts", "mean_nilai_uas"}
    assert "mean_kehadiran_persen" not in ctx
    assert "mean_nilai_tugas" not in ctx


# ── (c) NEGATIF: sum byte-identik (sibling sum_ tetap, perilaku lama) ────────
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


def test_sum_terlaris_unchanged():
    ctx = build_followup_context(RETAIL_DF, "produk terlaris", RETAIL_PROFILE, RETAIL)
    assert "(sum)" in ctx
    # Mode sum tak terpengaruh Fix D → sibling sum_ tetap ada (perilaku lama).
    assert "sum_Revenue" in ctx and "sum_Quantity" in ctx and "sum_Price" in ctx


def test_count_distribution_unchanged():
    ctx = build_followup_context(RETAIL_DF, "distribusi negara", RETAIL_PROFILE, RETAIL)
    assert "BREAKDOWN PER COUNTRY (sum)" in ctx     # cabang count → agg sum, no metric
    assert "mean_" not in ctx


# ── (d) NEGATIF: mean TANPA metrik (front kosong) → perilaku lama ───────────

def test_mean_without_metric_keeps_all_columns():
    """'rata-rata per program studi' (tanpa metrik spesifik) → front kosong →
    kondisi Fix D false → konteks tetap memuat semua mean_ (perilaku lama, no regresi)."""
    ctx = build_followup_context(
        _academic_df(), "rata-rata per program studi", ACA_PROFILE, None)
    # front kosong → tak dipersempit → >1 mean_ metric muncul.
    assert len(_mean_metrics(ctx)) >= 2
