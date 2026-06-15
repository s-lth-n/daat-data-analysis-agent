"""
test_revisi2_langbleed_commitA.py — Commit A: netralkan sumber language-bleed.

Memverifikasi:
  1. metric_note language-aware: language=='en' → metric_note_en (teks Inggris)
     ter-inject ke prompt; language=='id' → metric_note ID seperti semula.
  2. Fallback aman: domain tanpa metric_note_en (sesi lama) → pakai metric_note ID;
     dict kosong / None → None (tak crash).
  3. Setiap domain di _DOMAIN_CONFIG punya varian metric_note_en yang bukan teks ID.
  4. Deskripsi field NarrativeSchema yang dirender di kedua bahasa (judul, domain_note)
     bersifat language-neutral (tak ada prosa ID yang memancing bleed).
"""

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures / helpers ────────────────────────────────────────────────────────

_VALID_SCHEMA_JSON = json.dumps({
    "judul": "Sales Analysis",
    "ringkasan_id": "Ringkasan singkat.",
    "ringkasan_en": "Short summary.",
    "temuan_utama": ["Temuan satu", "Temuan dua", "Temuan tiga"],
    "key_findings": ["Finding one", "Finding two", "Finding three"],
    "domain_note": None,
    "kesimpulan_id": "Kesimpulan.",
    "conclusion_en": "Conclusion.",
})


def _mock_llm(content):
    resp = MagicMock()
    resp.content = content
    inst = MagicMock()
    inst.invoke.return_value = resp
    return inst


def _retail_state(language):
    from tools.column_profiler import _DOMAIN_CONFIG
    return {
        "prompt": "analyze",
        "language": language,
        "statistics": {"total_rows": 100, "descriptive": {}},
        "domain_context": {"domain_type": "retail", **_DOMAIN_CONFIG["retail"]},
    }


def _captured_human_content(inst):
    """Ambil isi HumanMessage dari pemanggilan invoke([SystemMessage, HumanMessage])."""
    messages = inst.invoke.call_args[0][0]
    return messages[1].content


# ── 1. metric_note ter-inject sesuai bahasa ──────────────────────────────────

def test_constrained_injects_en_metric_note():
    from tools.narrative_generator import _constrained_narrative
    inst = _mock_llm(_VALID_SCHEMA_JSON)
    with patch("tools.narrative_generator.ChatOllama", return_value=inst):
        _constrained_narrative(_retail_state("en"), "en")
    human = _captured_human_content(inst)
    assert "total sales (sum)" in human            # varian EN ter-inject
    assert "Dataset ini adalah" not in human       # frasa ID khas TIDAK bocor
    assert "penjualan" not in human


def test_constrained_injects_id_metric_note_byte_compat():
    from tools.narrative_generator import _constrained_narrative
    inst = _mock_llm(_VALID_SCHEMA_JSON)
    with patch("tools.narrative_generator.ChatOllama", return_value=inst):
        _constrained_narrative(_retail_state("id"), "id")
    human = _captured_human_content(inst)
    assert "Dataset ini adalah data retail/transaksi" in human   # ID seperti semula
    assert "penjualan" in human
    assert "total sales (sum)" not in human


# ── 2. Selector unit + fallback aman ─────────────────────────────────────────

def test_select_metric_note_picks_by_language():
    from tools.narrative_generator import _select_metric_note
    ctx = {"metric_note": "ID note", "metric_note_en": "EN note"}
    assert _select_metric_note(ctx, "en") == "EN note"
    assert _select_metric_note(ctx, "id") == "ID note"


def test_select_metric_note_fallback_when_no_en():
    from tools.narrative_generator import _select_metric_note
    # Sesi lama / domain tak terdefinisi: hanya ada metric_note ID.
    ctx = {"metric_note": "ID note"}
    assert _select_metric_note(ctx, "en") == "ID note"


def test_select_metric_note_empty_and_none_safe():
    from tools.narrative_generator import _select_metric_note
    assert _select_metric_note({}, "en") is None
    assert _select_metric_note(None, "en") is None
    assert _select_metric_note({}, "id") is None


def test_constrained_undefined_domain_no_crash():
    """domain_context tanpa metric_note_en → fallback ID, tak crash, tak kosong."""
    from tools.narrative_generator import _constrained_narrative
    state = {
        "prompt": "analyze",
        "language": "en",
        "statistics": {"total_rows": 10, "descriptive": {}},
        "domain_context": {"domain_type": "general", "metric_note": "Catatan ID saja."},
    }
    inst = _mock_llm(_VALID_SCHEMA_JSON)
    with patch("tools.narrative_generator.ChatOllama", return_value=inst):
        out = _constrained_narrative(state, "en")
    assert isinstance(out, str) and out
    assert "Catatan ID saja." in _captured_human_content(inst)   # fallback ID


# ── 3. Konfigurasi domain punya varian EN ────────────────────────────────────

_ID_MARKERS = ("Gunakan", "gunakan", "adalah", " yang ", " untuk ", "Dataset ini")


def test_all_domains_have_english_variant():
    from tools.column_profiler import _DOMAIN_CONFIG
    expected = {"retail", "finance", "hr", "healthcare", "education", "general"}
    assert expected <= set(_DOMAIN_CONFIG)
    for d in expected:
        en = _DOMAIN_CONFIG[d].get("metric_note_en")
        assert en, f"{d} missing metric_note_en"
        assert en != _DOMAIN_CONFIG[d]["metric_note"]
        for m in _ID_MARKERS:
            assert m not in en, f"{d} metric_note_en contains ID marker {m!r}"


# ── 4. Deskripsi schema language-neutral ─────────────────────────────────────

def test_schema_descriptions_language_neutral():
    from tools.narrative_generator import NarrativeSchema
    fields = NarrativeSchema.model_fields

    domain_desc = fields["domain_note"].description
    assert "report language" in domain_desc
    for w in ("Catatan", "Kosongkan", "kapita", "relevan "):
        assert w not in domain_desc

    judul_desc = fields["judul"].description
    assert "Judul" not in judul_desc
    assert "report language" in judul_desc


def test_validate_numbers_unaffected_by_description_change():
    """Sanity: validator akses ATRIBUT field (temuan_utama/key_findings), bukan
    deskripsi — mengubah description tak mempengaruhinya."""
    from tools.narrative_generator import NarrativeSchema, _validate_numbers_in_narrative
    schema = NarrativeSchema(
        judul="t", ringkasan_id="r", ringkasan_en="r",
        temuan_utama=["mean=10.94"], key_findings=["mean=10.94"],
        domain_note=None, kesimpulan_id="k", conclusion_en="c",
    )
    stats = {"descriptive": {"Quantity": {"mean": 10.94}}}
    _, passed, mismatched = _validate_numbers_in_narrative(schema, stats)
    assert passed is True
    assert mismatched == []
