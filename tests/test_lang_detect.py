"""
tests/test_lang_detect.py — Revisi #2, COMMIT 1.

detect_language(): single source of truth for output language.
  - Clear Indonesian → "id"
  - Clear English    → "en"
  - Short / mixed / technical-term questions ("top 5 product?", "CVD?") → "en"
  - Empty / whitespace / non-string → "en" (never raises)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from tools.lang_detect import detect_language


# ── Clear Indonesian → "id" ──────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "Tampilkan total penjualan per negara berdasarkan data ini",
    "Berapa jumlah transaksi untuk tiap produk yang ada?",
    "Tolong sebutkan produk dengan pendapatan tertinggi dan jelaskan korelasinya",
])
def test_clear_indonesian(q):
    assert detect_language(q) == "id"


# ── Clear English → "en" ─────────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "Show the total revenue for each country in this dataset",
    "What is the average price per product and how many orders were placed?",
    "Compare sales across regions and highlight the top customer by revenue",
])
def test_clear_english(q):
    assert detect_language(q) == "en"


# ── Short / mixed / technical → default "en" ─────────────────────────────────

@pytest.mark.parametrize("q", [
    "top 5 product?",
    "CVD?",
    "revenue?",
    "negara?",            # short ID single word still defaults EN per decision (b)
    "id en",
])
def test_short_or_mixed_defaults_en(q):
    assert detect_language(q) == "en"


# ── Empty / invalid → "en", never raises ─────────────────────────────────────

@pytest.mark.parametrize("q", ["", "   ", "\n", "12345", "!?!?"])
def test_empty_or_invalid_defaults_en(q):
    assert detect_language(q) == "en"


def test_non_string_does_not_raise():
    # Defensive: helper must swallow bad input and fall back to "en".
    assert detect_language(None) == "en"          # type: ignore[arg-type]
    assert detect_language(12345) == "en"         # type: ignore[arg-type]


# ── Fallback wired to settings.default_language (single source of truth) ──────

def test_fallback_follows_settings_default_language(monkeypatch):
    """
    On a genuine id/en tie the fallback is decided by settings.default_language,
    proving lang_detect reads the config setting (single source of truth) rather
    than a literal baked into the module. Flipping the setting flips the tie.
    """
    from config import settings

    # 1 Indonesian marker ("penjualan") + 1 English marker ("revenue") → tie.
    tie_question = "penjualan revenue foobar"

    monkeypatch.setattr(settings, "default_language", "en")
    assert detect_language(tie_question) == "en"

    monkeypatch.setattr(settings, "default_language", "id")
    assert detect_language(tie_question) == "id"
