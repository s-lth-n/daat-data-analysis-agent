"""
tests/test_revisi2_chart_caption.py — Revisi #2 addendum.

_chart_caption_md(): the followup chart caption word follows `language`
("Grafik" for id, "Chart" otherwise), is never bilingual, and drops the number
when there is exactly one chart.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import _chart_caption_md


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
