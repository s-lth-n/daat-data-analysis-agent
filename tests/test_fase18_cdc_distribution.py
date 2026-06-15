"""
tests/test_fase18_cdc_distribution.py — CDC/epidemiology categorical distribution.

Follow-up "distribusi/dominan/paling sering/proporsi" on CDC columns (Topic,
DataSource, DataValueType — all kategorik) must:
  1. resolve the right group dimension via ID synonyms (topik/sumber/jenis nilai),
  2. produce a COUNT+PROPORSI deterministic block (share = group/total real),
  3. NEVER sum the year columns (YearStart/YearEnd are kategorik but dtype int64),
  4. use the neutral unit "baris" for non-retail (not "transaksi").
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pandas as pd

from tools.groupby_analyzer import detect_groupby_intent, build_deterministic_block

# Year columns are kategorik-by-label but int64-by-dtype (the trap). DataValue is a
# real numeric metric that must NOT be summed when only a distribution is asked.
PROFILE = {
    "YearStart":     "kategorik",
    "YearEnd":       "kategorik",
    "Topic":         "kategorik",
    "DataSource":    "kategorik",
    "DataValueType": "kategorik",
    "DataValue":     "numerik_valid",
    "LocationID":    "id_kolom",
}

# 20 rows with clean target proportions:
#   Topic         : Cardiovascular 10 (50%), Diabetes 6 (30%), Asthma 4 (20%)
#   DataSource    : BRFSS 12 (60%), NVSS 8 (40%)
#   DataValueType : Crude Prevalence 14 (70%), Age-adjusted 6 (30%)
DF = pd.DataFrame({
    "YearStart": [2019, 2020, 2021, 2022] * 5,          # int64; sum=40410 if mis-summed
    "YearEnd":   [2019, 2020, 2021, 2022] * 5,
    "Topic": (["Cardiovascular Disease"] * 10
              + ["Diabetes"] * 6 + ["Asthma"] * 4),
    "DataSource": ["BRFSS"] * 12 + ["NVSS"] * 8,
    "DataValueType": ["Crude Prevalence"] * 14 + ["Age-adjusted Prevalence"] * 6,
    "DataValue": [float(i) for i in range(1, 21)],
    "LocationID": list(range(100, 120)),
})
HEALTHCARE = {"domain_type": "healthcare"}


# ── synonym resolution: topik/sumber/jenis nilai → real CDC columns ──────────

def test_detect_topik_maps_topic():
    r = detect_groupby_intent("distribusi topik", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Topic"


def test_detect_sumber_maps_datasource():
    r = detect_groupby_intent("sumber data yang paling sering", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "DataSource"


def test_detect_jenis_nilai_maps_datavaluetype():
    r = detect_groupby_intent("proporsi jenis nilai", PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "DataValueType"


# ── count + proporsi from the REAL total (Topic / DataSource / DataValueType) ─

def test_distribusi_topic_count_share():
    block = build_deterministic_block(DF, "distribusi topik", PROFILE, HEALTHCARE)
    assert "Angka kunci per Topic" in block
    assert "| Cardiovascular Disease | 10 | 50,00% |" in block
    assert "| Diabetes | 6 | 30,00% |" in block
    assert "| Asthma | 4 | 20,00% |" in block
    assert "Total baris = 20" in block


def test_dominan_topic_count_share():
    """'paling dominan' (no numeric metric) → same count+proporsi branch."""
    block = build_deterministic_block(DF, "topik apa yang paling dominan", PROFILE, HEALTHCARE)
    assert "Angka kunci per Topic" in block
    assert "| Cardiovascular Disease | 10 | 50,00% |" in block


def test_distribusi_datasource_count_share():
    block = build_deterministic_block(DF, "sumber data yang paling sering", PROFILE, HEALTHCARE)
    assert "Angka kunci per DataSource" in block
    assert "| BRFSS | 12 | 60,00% |" in block
    assert "| NVSS | 8 | 40,00% |" in block


def test_distribusi_datavaluetype_count_share():
    block = build_deterministic_block(DF, "proporsi jenis nilai", PROFILE, HEALTHCARE)
    assert "Angka kunci per DataValueType" in block
    assert "| Crude Prevalence | 14 | 70,00% |" in block
    assert "| Age-adjusted Prevalence | 6 | 30,00% |" in block


# ── the core regression: NO year is ever summed ──────────────────────────────

def test_no_year_sum_in_distribution_block():
    for q in ["distribusi topik", "topik apa yang paling dominan",
              "proporsi jenis nilai", "distribusi per topic"]:
        block = build_deterministic_block(DF, q, PROFILE, HEALTHCARE)
        assert block, f"expected a block for {q!r}"
        # No reference to year columns, no summed-year total, no inflated year sum.
        assert "YearStart" not in block, q
        assert "YearEnd" not in block, q
        assert "Total YearStart" not in block, q
        assert "40.410" not in block, q                 # = sum(YearStart) if mis-summed
        # DataValue (real metric) is also not summed for a pure distribution ask.
        assert "Total DataValue" not in block, q
        assert "Total baris" in block, q                # count branch instead


# ── superlative "paling banyak" (two-word) opens the gate (Fase 1.8.1) ───────

def test_paling_banyak_jumlah_baris_topic():
    """'paling banyak jumlah barisnya' (two-word superlative) → count+proporsi for
    Topic, NOT an empty block that leaves the LLM to fabricate→redact ([?])."""
    q = "topik apa yang paling banyak jumlah barisnya"
    r = detect_groupby_intent(q, PROFILE, list(DF.columns))
    assert r is not None and r["group_col"] == "Topic"
    block = build_deterministic_block(DF, q, PROFILE, HEALTHCARE)
    assert block, "expected a deterministic block, not an empty→fabrication fallback"
    assert "Angka kunci per Topic" in block
    assert "| Cardiovascular Disease | 10 | 50,00% |" in block
    assert "| Diabetes | 6 | 30,00% |" in block
    assert "Total baris = 20" in block
    assert "YearStart" not in block                       # still no year-sum


def test_bare_banyak_does_not_overtrigger():
    """A plain count question using 'banyak' but NO group dimension must stay empty
    (no spurious deterministic block) — the gate is 'paling banyak', not bare 'banyak'."""
    assert build_deterministic_block(
        DF, "berapa banyak baris dalam dataset ini", PROFILE, HEALTHCARE
    ) == ""


# ── neutral unit for non-retail; "transaksi" reserved for retail ─────────────

def test_unit_baris_for_non_retail():
    block = build_deterministic_block(DF, "distribusi topik", PROFILE, HEALTHCARE)
    assert "baris" in block and "transaksi" not in block


def test_unit_transaksi_when_retail():
    block = build_deterministic_block(DF, "distribusi topik", PROFILE, {"domain_type": "retail"})
    assert "transaksi" in block and "baris" not in block
