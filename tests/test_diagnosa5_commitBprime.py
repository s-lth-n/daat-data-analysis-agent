"""
test_diagnosa5_commitBprime.py — Diagnosa #5, Commit B'.

Inject grand total deterministik ke __followup_context__ sehingga prosa BOLEH
menyebut total (mis. Revenue 1.058.314) tanpa diredaksi [?].

Guardrail UTAMA (diuji eksplisit): grand total di KONTEKS == grand total di blok
deterministik TABEL — keduanya dari _resolve_followup_aggregation yang SAMA (tak
ada basis ketiga). Nilai diekstrak dari kedua rendering lalu dibandingkan via
_canonical_number (bukan hardcode terpisah).

Memverifikasi:
  1. build_followup_context menambahkan baris "TOTAL <metric> (all groups) = …".
  2. Nilai grand total konteks == nilai head blok deterministik tabel.
  3. Redactor: grand total lolos (tidak [?]); angka karangan tetap [?].
  4. Untuk retail "terlaris" → metrik = Revenue (basis sama dgn tabel).
  5. Non-groupby retail → baris Revenue ringkas (fallback paritas), TAPI tak ada
     baris grand total "(all groups)" maupun BREAKDOWN (no regresi grand-total).
"""

import re
import pandas as pd
import pytest

from agents.data_agent import compute_statistics
from tools.groupby_analyzer import (
    build_followup_context, build_deterministic_block,
    _resolve_followup_aggregation,
)
from tools.narrative_generator import (
    _build_stats_context, _redact_unverified_numbers, _canonical_number,
)


PROFILE = {
    "Description": "kategorik",
    "Country":     "kategorik",
    "Quantity":    "numerik_valid",
    "Price":       "numerik_valid",
}
RETAIL = {"domain_type": "retail", "preferred_aggregation": "sum"}

# Revenue/baris = [12000, 8000, 2000, 600, 2500, 90] → total = 25.190 (Regency teratas)
DF = pd.DataFrame({
    "Description": ["REGENCY CAKESTAND 3 TIER", "REGENCY CAKESTAND 3 TIER",
                    "WHITE HANGING HEART", "JUMBO BAG", "WHITE HANGING HEART",
                    "JUMBO BAG"],
    "Country":  ["UK", "UK", "Germany", "France", "UK", "UK"],
    "Quantity": [120, 80, 40, 30, 50, 10],
    "Price":    [100.0, 100.0, 50.0, 20.0, 50.0, 9.0],
})

_Q = "what are the top products by revenue?"


def _table_total(block: str):
    """Ekstrak angka total dari head blok deterministik: '_Total Revenue = 25,190.00 …_'."""
    m = re.search(r"Total\s+\w+\s*=\s*([\d.,]+)", block)
    return _canonical_number(m.group(1)) if m else None


def _ctx_total(ctx: str):
    """Ekstrak angka dari baris 'TOTAL <metric> (all groups) = …'."""
    m = re.search(r"TOTAL .*?\(all groups\)\s*=\s*([\d.,]+)", ctx)
    return _canonical_number(m.group(1)) if m else None


# ── 1. Baris grand total muncul di konteks ────────────────────────────────────

def test_followup_context_has_grand_total_line():
    ctx = build_followup_context(DF, _Q, PROFILE, RETAIL)
    assert "all groups" in ctx
    assert _ctx_total(ctx) is not None


# ── 2. GUARDRAIL: total konteks == total tabel (sumber sama, bukan hardcode) ──

def test_grand_total_equals_deterministic_table_total():
    ctx   = build_followup_context(DF, _Q, PROFILE, RETAIL)
    block = build_deterministic_block(DF, _Q, PROFILE, RETAIL, "en")
    ctx_total   = _ctx_total(ctx)
    table_total = _table_total(block)
    assert ctx_total is not None and table_total is not None
    assert ctx_total == table_total            # kesetaraan eksplisit lintas-rendering


def test_grand_total_matches_resolver_source():
    """Tegaskan tak ada basis ketiga: total konteks == grp[primary].sum().sum()."""
    agg = _resolve_followup_aggregation(DF, _Q, PROFILE, RETAIL)
    expected = float(agg["grp"][agg["primary"]].sum().sum())
    ctx = build_followup_context(DF, _Q, PROFILE, RETAIL)
    assert _ctx_total(ctx) == pytest.approx(expected, abs=0.01)


# ── 4. Retail 'terlaris' (tanpa kata revenue) → metrik Revenue, basis sama ────

def test_retail_terlaris_grand_total_is_revenue():
    q = "produk terlaris"
    agg = _resolve_followup_aggregation(DF, q, PROFILE, RETAIL)
    assert agg["primary"] == "Revenue"
    ctx = build_followup_context(DF, q, PROFILE, RETAIL)
    assert "TOTAL Revenue (all groups)" in ctx
    assert _ctx_total(ctx) == _table_total(build_deterministic_block(DF, q, PROFILE, RETAIL, "en"))


# ── 3. Redactor: grand total lolos, karangan diredaksi ────────────────────────

def _state(q=_Q):
    out = compute_statistics({
        "prompt": q, "language": "en", "dataframe_loaded": True,
        "file_path": "x.csv", "dataframe": DF, "column_profile": PROFILE,
        "domain_context": RETAIL,
    })
    return {"statistics": out["statistics"], "cleaning_report": {}, "data_summary": ""}


def test_redactor_keeps_grand_total_drops_fabricated():
    state = _state()
    # 25,190.00 = grand total (kini di konteks) → lolos.
    # 88,888.00 = karangan → diredaksi.
    narr = ("Total revenue across all products is 25,190.00, "
            "though a fabricated 88,888.00 also appears.")
    clean, n = _redact_unverified_numbers(narr, state, "en")
    assert "25,190.00" in clean        # grand total terverifikasi → tetap
    assert "88,888.00" not in clean    # karangan → diredaksi
    assert n == 1


def test_grand_total_in_stats_context_via_compute_statistics():
    state = _state()
    sc = _build_stats_context(state["statistics"])
    assert "all groups" in sc
    assert _ctx_total(sc) is not None


# ── 5. Non-groupby retail → baris Revenue ringkas, tanpa grand total (no regresi) ─

def test_non_groupby_revenue_line_no_grand_total():
    # build_followup_context (layer groupby) tetap kosong → tak ada grand-total line.
    assert build_followup_context(DF, "ringkas data ini", PROFILE, RETAIL) == ""
    out = compute_statistics({
        "prompt": "ringkas data ini", "language": "en", "dataframe_loaded": True,
        "file_path": "x.csv", "dataframe": DF, "column_profile": PROFILE,
        "domain_context": RETAIL,
    })
    # Fallback node-level menyuntik SATU baris Revenue ringkas (25.190), TAPI tak ada
    # baris grand total "(all groups)" maupun BREAKDOWN per-grup (no regresi).
    ctx = out["statistics"]["__followup_context__"]
    assert "Total Revenue" in ctx and "25,190.00" in ctx
    assert _ctx_total(ctx) is None        # tak ada baris "(all groups)"
    assert "all groups" not in ctx
