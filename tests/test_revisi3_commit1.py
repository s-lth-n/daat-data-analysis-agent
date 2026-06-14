"""
Revisi #3 — Commit 1 tests.
Refactor murni + domain_context dict di SessionData. Tidak boleh mengubah
output presentasi followup (byte-identik) maupun nilai metrik/persen.

Cakupan:
  A) _assemble_analysis_response — presentasi bersama (/analyze & followup):
     - format followup byte-identik dengan perakitan lama,
     - blok deterministik kosong → tidak ada section "---" ganda,
     - source_note kosong → banner tanpa anotasi (mode /analyze nanti).
  B) SessionData.domain_context — disimpan sebagai DICT (bukan cuma string),
     default None (backward-compat), dan menggerbangi unit count
     "transaksi" (retail) vs "baris" (None/non-retail) di build_deterministic_block.
"""

import pandas as pd

from main import _assemble_analysis_response
from session_store import SessionData
from tools.groupby_analyzer import build_deterministic_block


# ── A: presentation helper ──────────────────────────────────────────────────

def test_assemble_followup_byte_identical():
    """Helper harus mereproduksi PERSIS string perakitan followup lama."""
    file_name = "online_retail_50K.csv"
    row_count = 48708
    det = "**📊 Angka kunci**\n\n| A | B |\n| --- | --- |\n| x | 1 |"
    narrative = "Ini narasi analisis."
    chart_md = "\n\n**📊 Grafik**\n\n![Grafik](http://x/y.png)"
    sid = "abc123def456"

    got = _assemble_analysis_response(
        file_name           = file_name,
        row_count           = row_count,
        narrative           = narrative,
        session_id          = sid,
        deterministic_block = det,
        chart_md            = chart_md,
        source_note         = "(data dari sesi sebelumnya)",
    )

    # Rakit ulang persis dengan formula LAMA (sebelum refactor) sbg oracle.
    det_md = f"{det}\n\n---\n\n" if det else ""
    expected = (
        f"📄 **{file_name}** — {row_count} baris "
        f"(data dari sesi sebelumnya)\n\n"
        f"---\n\n"
        f"{det_md}"
        f"{narrative}"
        f"{chart_md}"
        f"\n\n[SESSION_ID: {sid}]"
    )
    assert got == expected


def test_assemble_no_deterministic_block():
    """Blok deterministik kosong → langsung narasi setelah banner, tanpa '---' kedua."""
    got = _assemble_analysis_response(
        file_name="f.csv", row_count=10, narrative="N",
        session_id="s", deterministic_block="", chart_md="",
        source_note="(data dari sesi sebelumnya)",
    )
    expected = (
        "📄 **f.csv** — 10 baris (data dari sesi sebelumnya)\n\n"
        "---\n\n"
        "N"
        "\n\n[SESSION_ID: s]"
    )
    assert got == expected


def test_assemble_empty_source_note_for_analyze():
    """Mode /analyze (Commit 2): source_note kosong → banner tanpa anotasi."""
    got = _assemble_analysis_response(
        file_name="f.csv", row_count=5, narrative="N", session_id="s",
    )
    assert got.startswith("📄 **f.csv** — 5 baris\n\n---\n\n")
    assert "(data dari sesi sebelumnya)" not in got
    assert got.endswith("[SESSION_ID: s]")


# ── B: SessionData domain_context dict ──────────────────────────────────────

def _make_session(domain_context):
    return SessionData(
        session_id="sid", dataframe=pd.DataFrame({"x": [1]}),
        column_profile={}, stats_result={}, cleaning_report={},
        chart_keys=[], file_name="f.csv", domain="retail",
        domain_context=domain_context,
    )


def test_sessiondata_stores_domain_context_dict():
    ctx = {"domain_type": "retail", "preferred_aggregation": "sum"}
    s = _make_session(ctx)
    assert s.domain_context == ctx
    assert isinstance(s.domain_context, dict)


def test_sessiondata_domain_context_defaults_none():
    """Backward-compat: session lama tanpa domain_context → None (tak crash)."""
    s = SessionData(
        session_id="sid", dataframe=pd.DataFrame({"x": [1]}),
        column_profile={}, stats_result={}, cleaning_report={},
        chart_keys=[], file_name="f.csv", domain="unknown",
    )
    assert s.domain_context is None


# DataFrame retail kecil untuk menguji penggerbangan unit count.
_DF = pd.DataFrame({
    "Topic":    ["A", "A", "B", "C", "B", "A"],
    "Quantity": [1, 2, 3, 4, 5, 6],
})
_PROFILE = {"Topic": "kategorik", "Quantity": "numerik_valid"}


def test_session_domain_context_drives_unit_transaksi_retail():
    """domain_context dict retail dari session → cabang count pakai 'transaksi'."""
    s = _make_session({"domain_type": "retail", "preferred_aggregation": "sum"})
    block = build_deterministic_block(
        _DF, "distribusi topik", _PROFILE, s.domain_context, "id"
    )
    assert "transaksi" in block and "Total baris" not in block


def test_session_none_domain_context_unit_baris_backward_compat():
    """domain_context None (session lama) → cabang count fallback 'baris', tak crash."""
    s = _make_session(None)
    block = build_deterministic_block(
        _DF, "distribusi topik", _PROFILE, s.domain_context, "id"
    )
    assert "baris" in block and "transaksi" not in block


def test_domain_context_does_not_change_metric_values():
    """domain_context HANYA label unit count — nilai metrik & persen IDENTIK."""
    q = "top topic by quantity"
    with_ctx = build_deterministic_block(
        _DF, q, _PROFILE, {"domain_type": "retail"}, "id"
    )
    without_ctx = build_deterministic_block(_DF, q, _PROFILE, None, "id")
    assert with_ctx == without_ctx
