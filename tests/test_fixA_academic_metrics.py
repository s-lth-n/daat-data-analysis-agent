"""
Fix A — resolver metrik GENERIK non-retail di _select_front_metrics().

Sebelum fix: dataset akademik → front=[] → primary jatuh ke numeric_now[0] (kolom
numerik SEMBARANG, mis. ukt_kelompok). Fix A mem-parse frasa metrik dari pertanyaan
("bobot nilai", "kehadiran") → kolom numerik yang BENAR-BENAR ADA via _find_numeric,
sehingga primary = kolom yang ditanya.

Test ini juga memuat TEST NEGATIF retail (no cross-regression): regex akademik tak
boleh ikut campur pada pertanyaan retail.
"""

import pandas as pd

from tools.groupby_analyzer import _resolve_followup_aggregation


# ── DF AKADEMIK mini ────────────────────────────────────────────────────────
# Kolom kategorik literal "fakultas" & "program_studi" supaya dimensi resolve via
# exact-name match di detect_groupby_intent. Numerik: ukt_kelompok SENGAJA kolom
# numerik PERTAMA → numeric_now[0]=ukt_kelompok = jebakan fallback yang harus
# DIHINDARI oleh Fix A.
ACA_PROFILE = {
    "fakultas":        "kategorik",
    "program_studi":   "kategorik",
    "ukt_kelompok":    "numerik_valid",
    "bobot_nilai":     "numerik_valid",
    "kehadiran_persen": "numerik_valid",
}
ACA_DF = pd.DataFrame({
    "fakultas":         ["FTI", "FTI", "FTE", "FTE", "FTI", "FTE"],
    "program_studi":    ["Tek Telkom", "Tek Telkom", "Informatika",
                         "Informatika", "Tek Telkom", "Informatika"],
    "ukt_kelompok":     [3, 5, 4, 2, 5, 1],          # jebakan numeric_now[0]
    "bobot_nilai":      [3.5, 3.8, 3.1, 2.9, 3.6, 3.3],
    "kehadiran_persen": [90, 85, 95, 80, 88, 92],
})


def _aca_primary(q):
    agg = _resolve_followup_aggregation(ACA_DF, q, ACA_PROFILE, None)
    return agg["primary"] if agg else None


def test_bobot_nilai_per_fakultas():
    """'rata-rata bobot nilai per fakultas' → primary bobot_nilai (BUKAN ukt_kelompok)."""
    assert _aca_primary("rata-rata bobot nilai per fakultas") == "bobot_nilai"


def test_kehadiran_per_program_studi():
    """'rata-rata kehadiran per program studi' → primary kehadiran_persen."""
    assert _aca_primary("rata-rata kehadiran per program studi") == "kehadiran_persen"


def test_no_metric_phrase_falls_back():
    """Pertanyaan TANPA frasa metrik → fallback lama numeric_now[0] (domain Fix B)."""
    # 'jumlah mahasiswa per fakultas' tak memuat frasa metrik akademik → front kosong
    # → fallback numeric_now[0]=ukt_kelompok tetap muncul (di luar scope Fix A).
    assert _aca_primary("daftar per fakultas") == "ukt_kelompok"


# ── TEST NEGATIF: retail TIDAK terpengaruh regex akademik ────────────────────
RETAIL_PROFILE = {
    "Description": "kategorik",
    "Country":     "kategorik",
    "Quantity":    "numerik_valid",
    "Price":       "numerik_valid",
}
RETAIL_DF = pd.DataFrame({
    "Description": ["A", "A", "B", "C", "B", "A"],
    "Country":     ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity":    [10, 5, 2, 4, 8, 1],
    "Price":       [2.0, 2.0, 5.0, 3.0, 5.0, 9.0],
})
RETAIL = {"domain_type": "retail", "preferred_aggregation": "sum"}


def test_retail_terlaris_stays_revenue():
    """'produk terlaris' retail → Revenue; resolver akademik tak ikut campur."""
    agg = _resolve_followup_aggregation(RETAIL_DF, "produk terlaris", RETAIL_PROFILE, RETAIL)
    assert agg is not None
    assert agg["primary"] == "Revenue"
