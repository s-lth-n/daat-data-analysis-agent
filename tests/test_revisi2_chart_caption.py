"""
tests/test_revisi2_chart_caption.py — Revisi #2 addendum.

_chart_caption_md(): the followup chart caption word follows `language`
("Grafik" for id, "Chart" otherwise), is never bilingual, and drops the number
when there is exactly one chart.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import _chart_caption_md, CHART_DIR


def test_id_caption_uses_grafik():
    md = _chart_caption_md(["abc123"], "id")
    assert "Grafik" in md
    assert "Chart" not in md

def test_en_caption_uses_chart():
    md = _chart_caption_md(["abc123"], "en")
    assert "Chart" in md
    assert "Grafik" not in md

def test_single_chart_has_no_number():
    md_id = _chart_caption_md(["k1"], "id")
    md_en = _chart_caption_md(["k1"], "en")
    assert "Grafik 1" not in md_id and "**📊 Grafik**" in md_id
    assert "Chart 1" not in md_en and "**📊 Chart**" in md_en

def test_multiple_charts_are_numbered_single_language():
    md_en = _chart_caption_md(["k1", "k2", "k3"], "en")
    assert "Chart 1" in md_en and "Chart 2" in md_en and "Chart 3" in md_en
    assert "Grafik" not in md_en                       # never bilingual

def test_unexpected_language_defaults_to_english():
    md = _chart_caption_md(["k1"], "fr")
    assert "Chart" in md and "Grafik" not in md

def test_empty_keys_yield_empty_string():
    assert _chart_caption_md([], "id") == ""
    assert _chart_caption_md([], "en") == ""


# ── Interactive-HTML link (ADDITIF): gated by .html existence ────────────────

def test_no_interactive_link_when_html_absent():
    # PNG selalu tampil; tanpa file .html → tak ada link (omission jujur).
    md = _chart_caption_md(["nohtml_key"], "id")
    assert "![" in md                      # PNG inline tetap ada
    assert "chart/image/nohtml_key.png" in md
    assert ".html" not in md
    assert "interaktif" not in md.lower()

def test_interactive_link_appended_when_html_exists():
    key = "ithtml01"
    f = CHART_DIR / f"{key}.html"
    f.write_text("<html><body>plotly</body></html>")
    try:
        md_id = _chart_caption_md([key], "id")
        assert f"chart/image/{key}.png" in md_id            # PNG tetap
        assert f"chart/image/{key}.html" in md_id           # link interaktif ADDITIF
        assert "🔍 [Buka grafik interaktif]" in md_id        # link word id
        md_en = _chart_caption_md([key], "en")
        assert "🔍 [Open interactive chart]" in md_en        # link word en, never bilingual
        assert "Buka grafik interaktif" not in md_en
    finally:
        f.unlink(missing_ok=True)
